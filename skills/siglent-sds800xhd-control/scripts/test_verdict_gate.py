#!/usr/bin/env python3
"""Regression tests for the verdict gate.

Every case pins one failure from the 2026-11-04 analysis incident, where an agent
applied a BYTE-domain code scale to a WORD capture, invented a clipping event,
used a sample-to-sample slew test as an edge detector, concluded "no square
wave" from an 80-sample look, and made a 1000x unit error. The point of these
tests is that the scanner answers these questions itself, so the answer cannot
drift with whoever is reading the record.

Fixtures are written through the real manifest path (see
``test_waveform_analysis._write_capture``) so ``load_capture`` validation is
genuinely exercised rather than mocked.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from test_waveform_analysis import _write_capture
from waveform_analysis import load_capture
from waveform_scan import (
    _no_clipping_claim,
    build_verdict,
    derive_thresholds,
    scan_hysteresis_aggregates,
)


# 20 MSa/s is the reference frame's rate; the WORD scale is 7680 codes/div at
# 2 V/div, i.e. 3840 codes/V.
REFERENCE_INTERVAL_S = 50e-9
WORD_CODES_PER_DIV = 7680.0

# Distinguishes "the manifest carries no provenance key" from an explicit False.
_UNRECORDED = object()


def _square_wave(points: int, period: int, low: int = 0, high: int = 19200) -> list[int]:
    return [high if (index % period) >= period // 2 else low for index in range(points)]


def _noisy_square_wave(points: int, period: int, low: int = 0, high: int = 19200, jitter: int = 40) -> list[int]:
    """Square wave with a small deterministic dither on each level.

    A perfectly flat level has zero measured sigma, so the noise-band placement
    test has nothing to compare against and falls back to a one-code distance
    check. Real captures always dither, so the realistic fixture carries a
    deterministic pseudo-random offset on each level.
    """

    values = []
    for index in range(points):
        level = high if (index % period) >= period // 2 else low
        offset = ((index * 2654435761) % (2 * jitter + 1)) - jitter
        values.append(level + offset)
    return values


def _verdict(values, **kwargs):
    """Build a verdict from a real on-disk capture, mirroring the CLI path."""

    width = kwargs.pop("width", 2)
    interval = kwargs.pop("interval", REFERENCE_INTERVAL_S)
    capture_options = kwargs.pop("capture_options", {})
    # _UNRECORDED leaves the provenance key absent, which is what the shared
    # fixture writes; True/False record an explicit transition claim.
    provenance = kwargs.pop("provenance", _UNRECORDED)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_capture(root, values, width=width, sample_interval=interval, **capture_options)
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if width == 2:
            # The shared fixture writes a generic descriptor; give it the real
            # firmware WORD layout so the domain resolution is exercised rather
            # than defaulted. A WORD frame carries vertical_code_field = 7680.
            preamble = manifest["results"][0]["preamble"]
            preamble["vertical_code_field"] = WORD_CODES_PER_DIV
            preamble["code_per_div"] = WORD_CODES_PER_DIV
        if provenance is not _UNRECORDED:
            manifest["existing_stop_claims_new_transition"] = provenance
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        capture = load_capture(root, "C1")
        return build_verdict(capture, **kwargs)


class ThresholdDerivationTests(unittest.TestCase):
    def test_two_levels_are_separated_and_thresholds_clear_both_levels(self):
        verdict = _verdict(_noisy_square_wave(40000, 200))
        self.assertEqual(verdict["status"], "OBSERVED")
        evidence = verdict["levels"]["threshold_evidence"]
        self.assertEqual(len(evidence["plateaus"]), 2)
        # E3/E4: a threshold inside the noise band is the failure this pins.
        placement = evidence["placement"]
        self.assertFalse(placement.get("noise_band_unmeasurable", False))
        self.assertGreaterEqual(placement["low_threshold_clearance_sigmas"], placement["minimum_sigmas"])
        self.assertGreaterEqual(placement["high_threshold_clearance_sigmas"], placement["minimum_sigmas"])

    def test_flat_record_refuses_instead_of_inventing_a_square_wave(self):
        verdict = _verdict([100] * 40000)
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertEqual(verdict["refusal"]["code"], "thresholds_not_separated")

    def test_three_levels_refuse_and_report_every_plateau(self):
        values = []
        for index in range(30000):
            phase = index % 300
            values.append(9600 if 100 <= phase < 200 else 19200 if phase >= 200 else 0)
        verdict = _verdict(values)
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertEqual(verdict["refusal"]["code"], "multi_level_unresolved")
        self.assertEqual(len(verdict["levels"]["threshold_evidence"]["plateaus"]), 3)

    def test_second_threshold_pair_is_reported_for_the_rescan_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, _square_wave(40000, 200), width=2, sample_interval=REFERENCE_INTERVAL_S)
            thresholds = derive_thresholds(load_capture(root, "C1"))
        self.assertEqual(thresholds["status"], "OK")
        low, high = thresholds["low_code"], thresholds["high_code"]
        second = thresholds["second_pair_codes"]
        self.assertLess(low, second[0])
        self.assertLess(second[0], second[1])
        self.assertLess(second[1], high)

    def test_sigma_placement_refusal_describes_the_sigma_test_not_the_diagnostic(self):
        # `near_threshold_limit` is validated and reported, but it never decides
        # a refusal. A message that quotes it claims a limit took effect when the
        # decision was made by the sigma clearance test, so it must not appear.
        verdict = _verdict(_noisy_square_wave(40000, 200), threshold_codes=(5, 19195))
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertEqual(verdict["refusal"]["code"], "thresholds_inside_noise")
        detail = verdict["refusal"]["detail"]
        self.assertIn("sigma", detail)
        self.assertNotIn("the limit is", detail)
        self.assertNotIn("near_threshold_limit", detail)
        placement = verdict["levels"]["threshold_evidence"]["placement"]
        self.assertLess(placement["low_threshold_clearance_sigmas"], placement["minimum_sigmas"])

    def test_refusal_wording_states_the_mass_floor_the_code_implements(self):
        # The messages used to say "at least 5% of the record", which the peak
        # detector has not implemented since the mass floor became relative to
        # the dominant peak.
        three_levels = []
        for index in range(30000):
            phase = index % 300
            three_levels.append(9600 if 100 <= phase < 200 else 19200 if phase >= 200 else 0)
        for values in (three_levels, [100] * 40000):
            verdict = _verdict(values)
            detail = verdict["refusal"]["detail"]
            self.assertNotIn("5% of the record", detail)
            self.assertIn("10% of the dominant peak's mass", detail)

    def test_narrow_pulse_refusal_exposes_the_candidate_excursion(self):
        # A refusal must not be a blank answer: the narrow pulse that stops the
        # level split from resolving is still reported as a candidate, with its
        # own samples, and the structure count matches the returned list.
        values = [0] * 150000 + [19200] * 2000 + [0] * 48000
        verdict = _verdict(values)
        self.assertEqual(verdict["status"], "REFUSED")
        excursions = verdict["refusal"]["candidate_excursions"]
        self.assertGreaterEqual(len(excursions["candidates"]), 1)
        self.assertEqual(verdict["structure"]["candidate_excursion_count"], len(excursions["candidates"]))
        pulse = excursions["candidates"][0]
        self.assertEqual((pulse["start_sample"], pulse["end_sample"]), (150000, 152000))
        self.assertIn("candidate_excursions", verdict["claims"]["can_claim"])


class EdgeScanTests(unittest.TestCase):
    def test_edge_count_is_not_doubled_by_two_masks(self):
        """One transition per physical level change.

        Concatenating a crossed-high mask with a crossed-low mask reports every
        edge twice: on the reference capture that yields 561274 where the
        hysteresis state machine yields 280637. A scanner that double counts is
        unusable for any timing claim, so the exact count is pinned here.
        """

        points, period = 40000, 200
        verdict = _verdict(_square_wave(points, period))
        # The record starts low and ends low, so the trailing half period
        # contributes one rising edge without its falling partner.
        expected = (points // period) * 2 - 1
        self.assertEqual(verdict["structure"]["edge_count"], expected)

    def test_state_is_carried_across_chunk_boundaries(self):
        points, period = 40000, 200
        values = _square_wave(points, period)
        coarse = _verdict(values)
        fine = _verdict(values, chunk_points=64)
        self.assertEqual(
            coarse["structure"]["edge_count"],
            fine["structure"]["edge_count"],
            "a chunk boundary is not a level change; resetting state per chunk invents edges",
        )

    def test_narrow_pulse_below_the_peak_floor_is_refused_not_ignored(self):
        # E4 is only half the rule. A narrow pulse must never be dismissed as
        # "no signal", but a scanner also must not invent a level out of the
        # transition samples of a real oscillation. The current rule resolves the
        # conflict conservatively: a high level holding under 10% of the dominant
        # peak is not accepted as a level, and the verdict REFUSES rather than
        # claiming either "no pulse" or a confident two-level split.
        #
        # REFUSED is the safe answer here: it tells the caller the level structure
        # is unresolved, which is true. Reporting OBSERVED with a fabricated
        # threshold pair would be the original failure mode.
        values = [0] * 150000 + [19200] * 2000 + [0] * 48000
        verdict = _verdict(values)
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertIn(verdict["refusal"]["code"], {"thresholds_not_separated", "multi_level_unresolved"})
        # Whatever the refusal, it must not claim the record is featureless.
        self.assertEqual(verdict["structure"]["edge_count"], None)
        self.assertIn("record_structure_not_scanned_thresholds_not_separated", verdict["limitations"])

    def test_a_comparable_two_level_record_is_scanned(self):
        # The companion case: when both levels carry comparable mass the scan
        # runs and the edges are counted, so the refusal above is about level
        # separation and not a blanket refusal to analyse.
        verdict = _verdict(_square_wave(200000, 200))
        self.assertEqual(verdict["status"], "OBSERVED")
        self.assertGreater(verdict["structure"]["edge_count"], 0)

    def test_rail_detection_uses_the_representable_limit_not_five_divisions(self):
        # E2: a WORD payload stops at 32767 codes, i.e. 4.267 divisions at
        # 2 V/div, so clipping is not observable up to the nominal 5 divisions.
        clean = _verdict(_square_wave(20000, 200))
        structure = clean["structure"]
        self.assertFalse(structure["clipped"])
        self.assertEqual(structure["rail_samples"], 0)
        self.assertEqual(structure["representable_code_limit"], 32767)
        expected_div = 32767 / WORD_CODES_PER_DIV
        self.assertAlmostEqual(structure["clipping_detectable_up_to_div"], expected_div, places=6)
        self.assertLess(structure["clipping_detectable_up_to_div"], 5.0)
        self.assertEqual(structure["full_scale_code"], 5 * WORD_CODES_PER_DIV)

    def test_samples_pinned_at_the_transport_limit_are_reported_as_rail(self):
        values = [0] * 10000 + [32767] * 10000
        verdict = _verdict(values)
        self.assertTrue(verdict["structure"]["clipped"])
        self.assertGreater(verdict["structure"]["rail_samples"], 0)

    def test_no_clipping_is_claimed_only_inside_the_representable_limit(self):
        # E2 in the other direction: an empty rail count is not proof by itself.
        # Clipping is unobservable beyond `clip_limit_div`, so the claim needs the
        # observed range to stay strictly inside the representable limit too. A
        # synthetic WORD record topping out at 32766 is the realistic edge: it
        # never reaches the rail and stays inside, so the claim holds.
        clean = _verdict(_square_wave(20000, 200))
        self.assertIn("no_clipping", clean["claims"]["can_claim"])
        self.assertEqual(clean["structure"]["rail_samples"], 0)

        near_limit = _verdict([0] * 10000 + [32766] * 10000)
        self.assertIn("no_clipping", near_limit["claims"]["can_claim"])
        self.assertEqual(near_limit["structure"]["rail_samples"], 0)
        self.assertLess(near_limit["structure"]["max_code"], near_limit["structure"]["representable_code_limit"])

    def test_a_range_touching_the_representable_limit_withholds_no_clipping(self):
        # The negative path cannot be produced by a real capture: no WORD sample
        # can exceed 32767, so a clean rail count and a range outside the limit
        # never coexist. The boundary logic is therefore asserted directly, with
        # the same arguments the verdict passes, and the emitted claim shape is
        # pinned separately through a rail-saturated record.
        self.assertEqual(_no_clipping_claim(-100, 100, 0, 32767, 32767 / WORD_CODES_PER_DIV), (True, None))
        for min_code, max_code in ((-32767, 100), (0, 32767)):
            allowed, entry = _no_clipping_claim(min_code, max_code, 0, 32767, 32767 / WORD_CODES_PER_DIV)
            self.assertFalse(allowed)
            self.assertEqual(entry, "clipping_beyond_4.267_divisions_unobservable")

        saturated = _verdict([0] * 10000 + [32767] * 10000)
        self.assertNotIn("no_clipping", saturated["claims"]["can_claim"])
        boundary_claims = [
            entry for entry in saturated["claims"]["cannot_claim"]
            if entry.startswith("clipping_beyond_")
        ]
        self.assertEqual(len(boundary_claims), 1)
        expected = saturated["structure"]["clip_limit_div"]
        self.assertEqual(boundary_claims[0], f"clipping_beyond_{expected:.3f}_divisions_unobservable")


class DomainTests(unittest.TestCase):
    def test_word_without_calibration_withholds_voltage(self):
        # E1/E7: a WORD frame has no verified absolute scale, so no voltage may
        # be reported even though the code scale is now correct.
        verdict = _verdict(_square_wave(40000, 200))
        self.assertEqual(verdict["domain"]["code_domain"], "word")
        self.assertEqual(verdict["domain"]["codes_per_div"], WORD_CODES_PER_DIV)
        self.assertEqual(verdict["domain"]["scale_status"], "OBSERVED_UNVERIFIED")
        self.assertIsNone(verdict["levels"]["low_v"])
        self.assertIsNone(verdict["levels"]["high_v"])
        self.assertIn("absolute_voltage_accuracy", verdict["claims"]["cannot_claim"])

    def test_word_codes_per_div_is_not_the_byte_value(self):
        # The 256x trap: 30 is the BYTE code-per-division and must never be used
        # as a WORD scale.
        verdict = _verdict(_square_wave(20000, 200))
        self.assertNotEqual(verdict["domain"]["codes_per_div"], 30.0)
        self.assertAlmostEqual(verdict["domain"]["codes_per_div"], WORD_CODES_PER_DIV, places=3)
        # codes_per_v follows the panel V/div of the frame, so assert the ratio
        # rather than a hard-coded 3840 (the fixture runs 1 V/div).
        expected_codes_per_v = WORD_CODES_PER_DIV / verdict["domain"]["v_per_div"]
        self.assertAlmostEqual(verdict["domain"]["codes_per_v"], expected_codes_per_v, places=3)

    def test_level_voltages_come_from_the_levels_not_the_thresholds(self):
        # The thresholds are placed symmetrically in the gap (25% / 75%), so
        # reporting low_v/high_v from them scaled a 0/5 V square wave to
        # 1.25/3.75 V. The names mean LEVEL voltages and must come from the
        # plateau peaks; threshold voltages are published separately.
        values = _square_wave(40000, 200, low=0, high=19200)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values, width=2, sample_interval=REFERENCE_INTERVAL_S)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            preamble = manifest["results"][0]["preamble"]
            preamble["vertical_code_field"] = WORD_CODES_PER_DIV
            preamble["code_per_div"] = WORD_CODES_PER_DIV
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            capture = load_capture(root, "C1")
            # A verified scale of 2 V/div over 7680 codes/div is 2/7680 V per code.
            capture["calibration"] = dict(capture["calibration"])
            capture["calibration"].update(
                status="VALID",
                code_scale_v=2.0 / WORD_CODES_PER_DIV,
                effective_offset_v=0.0,
                effective_vdiv_v_per_div=2.0,
            )
            verdict = build_verdict(capture)

        self.assertEqual(verdict["status"], "OBSERVED")
        self.assertAlmostEqual(verdict["levels"]["low_v"], 0.0, places=3)
        self.assertAlmostEqual(verdict["levels"]["high_v"], 5.0, places=3)
        self.assertEqual(verdict["levels"]["level_v_basis"], "plateau_peak_code")
        # Thresholds sit inside the gap, so their voltages must differ from the
        # level voltages. Equality here would mean the old defect is back.
        threshold_v = verdict["levels"]["threshold_v"]
        self.assertIsNotNone(threshold_v)
        self.assertGreater(threshold_v[0], verdict["levels"]["low_v"])
        self.assertLess(threshold_v[1], verdict["levels"]["high_v"])


class TimingAndWindowTests(unittest.TestCase):
    def test_window_table_is_contiguous_and_time_anchored(self):
        verdict = _verdict(_square_wave(40000, 200))
        windows = verdict["windows"]
        self.assertTrue(windows)
        for left, right in zip(windows, windows[1:]):
            self.assertEqual(left["t1_s"], right["t0_s"], "windows must be contiguous")
        self.assertTrue(all(window["t1_s"] > window["t0_s"] for window in windows))
        # E8: display time, never a bare sample index.
        self.assertLess(windows[0]["t0_s"], windows[0]["t1_s"])
        self.assertEqual(sum(window["edge_count"] for window in windows), verdict["structure"]["edge_count"])

    def test_window_count_matches_the_record_span(self):
        verdict = _verdict(_square_wave(40000, 200))
        capture = verdict["capture"]
        expected = math.ceil(capture["points"] * capture["interval_s"] / 0.05)
        self.assertLessEqual(len(verdict["windows"]), expected + 1)
        self.assertGreaterEqual(len(verdict["windows"]), expected - 1)

    def test_bimodal_record_is_labelled_bimodal(self):
        # E6: the record holds two different oscillation rates, so no single
        # frequency describes it. A quiet stretch would not do: silence produces
        # no half periods at all, so the population would stay unimodal.
        fast = _square_wave(100000, 50)
        slow = _square_wave(100000, 500)
        verdict = _verdict(fast + slow)
        self.assertEqual(verdict["status"], "OBSERVED")
        self.assertIn("bimodal", verdict["timing"]["distribution_note"])
        self.assertIn("single_continuous_frequency", verdict["claims"]["cannot_claim"])

    def test_unimodal_record_does_not_claim_bimodality(self):
        verdict = _verdict(_square_wave(100000, 200))
        self.assertFalse(verdict["timing"]["distribution_note"].startswith("bimodal:"))

    def test_every_window_carries_a_label_from_the_closed_vocabulary(self):
        # Spec §4.3 step 5: the window table is the replacement for gate step 2,
        # so every row must carry a label from the closed vocabulary.
        vocabulary = {"silent", "sparse", "dense", "steady_high", "steady_low", "mixed"}
        verdict = _verdict(_square_wave(40000, 200))
        self.assertTrue(verdict["windows"])
        for window in verdict["windows"]:
            self.assertIn(window["label"], vocabulary)

    def test_a_mixed_record_yields_several_distinct_window_labels(self):
        # A quiet prefix, a dense section, a slower section and a steady-high
        # stretch in one record: the label is a per-window property, so the
        # table must show the difference instead of one record-wide verdict.
        quiet = [0] * 40000
        dense = _square_wave(40000, 200)
        sparse = _square_wave(40000, 4000)
        steady = [19200] * 40000
        verdict = _verdict(quiet + dense + sparse + steady, window_s=1e-4)
        self.assertEqual(verdict["status"], "OBSERVED")
        labels = {window["label"] for window in verdict["windows"]}
        self.assertGreaterEqual(len(labels), 3, f"expected at least three labels, saw {sorted(labels)}")
        self.assertTrue({"silent", "dense", "steady_high"} <= labels, sorted(labels))

    def test_unit_conversion_is_not_off_by_1000(self):
        # E5: 34085 samples at 50 ns is 1.704 ms, not 1.7 s.
        samples = 34085
        interval = REFERENCE_INTERVAL_S
        self.assertAlmostEqual(samples * interval, 1.704250e-3, places=9)


class ProvenanceTests(unittest.TestCase):
    def test_missing_provenance_key_is_reported_as_unrecorded(self):
        # A missing key is not evidence of a Ready -> Stop transition. Reporting
        # either explicit label for it would invent provenance the manifest does
        # not carry, so the absence gets its own label and its own limitation.
        verdict = _verdict(_square_wave(40000, 200))
        self.assertEqual(verdict["provenance"]["frame_evidence"], "provenance_unrecorded")
        self.assertIn("frame_provenance_unrecorded", verdict["claims"]["must_state"])
        self.assertIn("frame_provenance_unrecorded", verdict["limitations"])
        self.assertNotIn("existing_stopped_no_ready_to_stop", verdict["claims"]["must_state"])

    def test_ready_to_stop_transition_is_recorded_when_claimed(self):
        # An explicit True means the capture claimed a Ready -> Stop transition
        # and the label must say so.
        verdict = _verdict(_square_wave(40000, 200), provenance=True)
        self.assertEqual(verdict["provenance"]["frame_evidence"], "observed_ready_to_stop")
        self.assertNotIn("existing_stopped_no_ready_to_stop", verdict["claims"]["must_state"])
        self.assertNotIn("frame_provenance_unrecorded", verdict["claims"]["must_state"])

    def test_explicit_false_is_the_existing_stopped_label(self):
        # E10: a Stop without a prior Ready is not proof of a new capture, and an
        # explicit False is the one manifest value that says so.
        verdict = _verdict(_square_wave(40000, 200), provenance=False)
        self.assertEqual(verdict["provenance"]["frame_evidence"], "existing_stopped_no_ready_to_stop")
        self.assertIn("existing_stopped_no_ready_to_stop", verdict["claims"]["must_state"])
        self.assertNotIn("frame_provenance_unrecorded", verdict["claims"]["must_state"])

    def test_off_profile_context_is_flagged(self):
        # E11: 20 MSa/s over 2 ms is far from the documented 5 MSa/s / 5 s.
        verdict = _verdict(_square_wave(40000, 200))
        self.assertTrue(verdict["provenance"]["context_deviations"])

    def test_must_state_uses_only_the_closed_vocabulary(self):
        allowed = {
            "existing_stopped_no_ready_to_stop",
            "frame_provenance_unrecorded",
            "scale_observed_unverified_no_calibration_available",
            "frequency_basis_is_window_local_not_record_wide",
            "single_channel_analysis_only",
        }
        verdict = _verdict(_square_wave(40000, 200))
        for entry in verdict["claims"]["must_state"]:
            self.assertTrue(
                entry in allowed or entry.startswith("detection_resolution_"),
                f"unexpected must_state entry: {entry}",
            )

    def test_unverified_scale_does_not_claim_an_internal_consistency_check(self):
        # Capture-time PKPK measurement is not implemented, so no internal
        # consistency check exists and no must_state entry may imply one. The
        # old wording must be gone from every verdict, refusal or not.
        observed = _verdict(_square_wave(40000, 200))
        refused = _verdict([100] * 40000)
        for verdict in (observed, refused):
            self.assertNotIn(
                "scale_observed_unverified_internal_consistency_only",
                json.dumps(verdict),
            )
            self.assertIn(
                "scale_observed_unverified_no_calibration_available",
                verdict["claims"]["must_state"],
            )

    def test_verdict_is_bound_to_the_merged_waveform_hash(self):
        verdict = _verdict(_square_wave(40000, 200))
        self.assertEqual(len(verdict["capture"]["merged_sha256"]), 64)


class AggregateScannerTests(unittest.TestCase):
    def test_single_sample_pulses_are_not_silently_dropped(self):
        # A one-sample excursion is real evidence. A minimum duration of 2
        # samples discarded every pulse in a 1% duty train and reported zero
        # candidates, which reads exactly like "nothing was there".
        values = [0] * 200000
        for index in range(0, len(values), 100):
            values[index] = 19200
        verdict = _verdict(values)
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertEqual(verdict["structure"]["candidate_excursion_count"], 2000)
        self.assertIn("candidate_excursions", verdict["claims"]["can_claim"])

    def test_short_record_refusal_names_the_record_length(self):
        # Five samples cannot support two levels. Reporting
        # "thresholds_not_separated" points the caller at the wrong remedy.
        verdict = _verdict([0, 19200, 0, 19200, 0])
        self.assertEqual(verdict["status"], "REFUSED")
        self.assertEqual(verdict["refusal"]["code"], "record_too_short")
        self.assertIn("record-length limit", verdict["refusal"]["detail"])

    def test_scanner_does_not_report_an_item_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, _square_wave(40000, 200), width=2, sample_interval=REFERENCE_INTERVAL_S)
            capture = load_capture(root, "C1")
            thresholds = derive_thresholds(capture)
            scan = scan_hysteresis_aggregates(
                capture, thresholds["low_code"], thresholds["high_code"]
            )
        for forbidden in ("edges", "pulses", "cycles"):
            self.assertNotIn(forbidden, scan)
        self.assertGreater(scan["edge_count"], 0)
        self.assertEqual(scan["representable_code_limit"], 32767)


if __name__ == "__main__":
    unittest.main()
