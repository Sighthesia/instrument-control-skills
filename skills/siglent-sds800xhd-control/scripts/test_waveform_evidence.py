#!/usr/bin/env python3
"""Offline tests for the five-axis waveform evidence report.

Fixtures are written through the real capture manifest path
(``test_waveform_analysis._write_capture``) so ``load_capture`` validation,
including hash and segment checks, is genuinely exercised.
"""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import waveform_evidence
from test_waveform_analysis import _write_capture, _write_modern_capture
from waveform_analysis import AnalysisError, load_capture
from waveform_evidence import (
    AXES,
    AXIS_STATUSES,
    EvidenceStageError,
    build_evidence,
    collect_evidence,
    evidence_error_report,
    main,
)


def _dithered_square(points, period, low=0, high=19200, jitter=40):
    """Two levels with a deterministic dither so the noise band is measurable."""

    values = []
    for index in range(points):
        level = high if (index % period) >= period // 2 else low
        values.append(level + ((index * 2654435761) % (2 * jitter + 1)) - jitter)
    return values


def _narrow_pulse(before=150000, width=2000, after=48000, high=200):
    return [0] * before + [high] * width + [0] * after


def _capture(root: Path, values, **kwargs) -> dict:
    manifest = _write_capture(root, values, **kwargs)
    return load_capture(manifest, "C1")


def _capture_with_screenshot(root: Path, values, record: dict, **kwargs) -> dict:
    manifest_path = _write_capture(root, values, **kwargs)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["screenshot"] = record
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return load_capture(manifest_path, "C1")


def _screenshot_record(raw_path: Path, payload: bytes, **overrides) -> dict:
    record = {
        "schema_version": "screenshot-evidence-v1",
        "command": ":PRINt? PNG",
        "framing": "raw_png_chunks_through_iend_plus_lf_not_ieee4882",
        "raw_path": str(raw_path),
        "status": "COMPLETE",
        "container_valid": True,
        "image_decode_status": "UNVERIFIED",
        "image_decode_reasons": ["no PNG decoder ran"],
        "raw_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "frame_association": {"status": "UNVERIFIED", "reasons": ["no shared frame identifier"]},
    }
    record.update(overrides)
    return record


def _sibling(root: Path, suffix: str) -> Path:
    return root.parent / (root.name + suffix)


def _assert_axis_vocabulary(testcase: unittest.TestCase, report: dict) -> None:
    for name, axis in report["axes"].items():
        testcase.assertIn(axis["status"], AXIS_STATUSES, name)
        testcase.assertNotEqual(axis["status"], "UNKNOWN", name)


class EvidenceAxisTests(unittest.TestCase):
    def test_complete_capture_reports_all_five_axes_with_separate_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture)
        self.assertEqual(report["tool"], "evidence")
        self.assertEqual(report["stage"], "complete")
        self.assertEqual(set(report["axes"]), set(AXES))
        _assert_axis_vocabulary(self, report)
        for name, axis in report["axes"].items():
            self.assertEqual(set(axis), {"status", "scope", "reasons", "evidence"}, name)
            self.assertTrue(axis["scope"], name)
            self.assertTrue(axis["reasons"], name)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
        self.assertEqual(report["axes"]["requested_range_coverage"]["status"], "UNVERIFIED")
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")
        self.assertEqual(report["axes"]["time_correspondence"]["status"], "UNVERIFIED")
        # This fixture's verdict refuses the level split, so capability stays
        # unverified and the sampling requirement is reported separately.
        self.assertEqual(report["axes"]["analysis_capability"]["status"], "UNVERIFIED")
        self.assertIn("refused_verdict_capability_unverified", report["axes"]["analysis_capability"]["reasons"])
        payload_evidence = report["axes"]["payload_integrity"]["evidence"]
        self.assertIn("same_frame_identity_with_any_other_read_or_screenshot", payload_evidence["does_not_establish"])
        self.assertIn("coverage_of_the_whole_screen_or_acquisition_memory", payload_evidence["does_not_establish"])
        self.assertEqual(report["axes"]["time_correspondence"]["evidence"]["status"], "UNVERIFIED")
        self.assertIn("screenshot_absence_does_not_block_payload_integrity", report["screenshot"]["reasons"])
        self.assertEqual(report["screenshot"]["present"], False)
        self.assertIn("refused_verdict_capability_unverified", report["limitations"])

    def test_screen_range_difference_is_reported_without_vetoing_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_modern_capture(
                root,
                _dithered_square(20000, 1000),
                scope_points=5000,
                scope_duration_s=5000 * 1e-6,
            )
            capture = load_capture(manifest, "C1")
            report = build_evidence(capture)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
        self.assertNotEqual(report["axes"]["payload_integrity"]["evidence"]["record_frame"]["screen_range"]["status"], "COMPLETE")
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")
        self.assertEqual(report["capture"]["points"], 20000)

    def test_observed_verdict_is_exposed_as_capability_evidence_only(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(200000, 2000), width=2, sample_interval=50e-9)
            report = build_evidence(capture)
        axis = report["axes"]["analysis_capability"]
        verdict = axis["evidence"]["verdict"]
        self.assertEqual(verdict["status"], "OBSERVED")
        self.assertIn("levels", verdict["can_claim"])
        self.assertIn("multi_channel_causality", verdict["cannot_claim"])
        self.assertIn("absolute_voltage_accuracy", verdict["cannot_claim"])
        self.assertEqual(axis["status"], "COMPLETE")
        self.assertIn("protocol_decodability_or_option_availability", axis["evidence"]["does_not_establish"])
        # No sampling specification was stated, so the completed verdict must
        # not read as task-ready.
        self.assertEqual(axis["evidence"]["task_readiness"]["status"], "UNVERIFIED")
        self.assertIn("task_readiness_not_established", axis["reasons"])
        self.assertIn("task_readiness_not_established", report["limitations"])

    def test_observed_verdict_with_insufficient_sampling_downgrades_the_axis(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(200000, 2000), width=2, sample_interval=50e-9)
            report = build_evidence(
                capture,
                max_sample_interval_s=1e-9,
                sampling_requirement_source="datasheet: 1 ns bit period",
            )
        axis = report["axes"]["analysis_capability"]
        requirement = axis["evidence"]["sampling_requirement"]
        self.assertEqual(requirement["status"], "INSUFFICIENT")
        # The verdict stays visible as sub-evidence, but the axis itself drops.
        self.assertEqual(axis["evidence"]["verdict"]["status"], "OBSERVED")
        self.assertIn("levels", axis["evidence"]["verdict"]["can_claim"])
        self.assertEqual(axis["status"], "UNVERIFIED")
        self.assertIn("verdict_observed_but_the_stated_sampling_requirement_is_not_met", axis["reasons"])
        self.assertEqual(axis["evidence"]["task_readiness"]["status"], "UNVERIFIED")
        self.assertIn("task_readiness_not_established", report["limitations"])
        _assert_axis_vocabulary(self, report)

    def test_requested_range_without_a_target_stays_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture)
        axis = report["axes"]["requested_range_coverage"]
        self.assertEqual(axis["status"], "UNVERIFIED")
        self.assertIsNone(axis["evidence"]["requested"])

    def test_requested_range_is_hashed_and_boundary_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture, range_start=100, range_end=600)
            expected = hashlib.sha256(capture["samples"][100:600].tobytes()).hexdigest()
        axis = report["axes"]["requested_range_coverage"]
        self.assertEqual(axis["status"], "COMPLETE")
        self.assertEqual(axis["evidence"]["requested"], {"start_sample": 100, "end_sample_exclusive": 600, "count": 500})
        self.assertEqual(axis["evidence"]["sample_range_sha256"], expected)

    def test_out_of_range_target_is_incomplete_without_downgrading_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture, range_start=19500, range_end=20001)
        range_axis = report["axes"]["requested_range_coverage"]
        self.assertEqual(range_axis["status"], "INCOMPLETE")
        self.assertTrue(range_axis["evidence"]["payload_integrity_unaffected"])
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")


class EvidenceInputValidationTests(unittest.TestCase):
    def _capture(self, root):
        return _capture(root, _dithered_square(20000, 1000))

    def test_range_rejects_bool_fraction_and_string(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory))
            for start, end in ((True, 10), (1.5, 10), ("1", 10), (1, True), (1, 2.5), (1, "2"), (-1, 10), (10, 10), (5, None)):
                with self.subTest(start=start, end=end):
                    with self.assertRaises(EvidenceStageError) as caught:
                        build_evidence(capture, range_start=start, range_end=end)
                    self.assertEqual(caught.exception.code, "LIMIT_INVALID")
                    self.assertEqual(caught.exception.stage, "input")

    def test_candidate_limits_reject_bool_fraction_string_and_out_of_range(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory))
            cases = (
                {"candidate_windows": True},
                {"candidate_windows": 2.0},
                {"candidate_windows": "4"},
                {"candidate_windows": 0},
                {"candidate_windows": 33},
                {"candidate_window_points": False},
                {"candidate_window_points": 10.5},
                {"candidate_window_points": "10"},
                {"candidate_window_points": 4097},
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    with self.assertRaises(EvidenceStageError) as caught:
                        build_evidence(capture, **arguments)
                    self.assertEqual(caught.exception.stage, "input")

    def test_sampling_requirement_rejects_bool_string_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory))
            for value in (True, "1e-3", float("nan"), float("inf"), 0.0, -1.0):
                with self.subTest(value=value):
                    with self.assertRaises(EvidenceStageError) as caught:
                        build_evidence(capture, max_sample_interval_s=value, sampling_requirement_source="stated")
                    self.assertEqual(caught.exception.code, "LIMIT_INVALID")

    def test_non_text_source_is_a_structured_input_error(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory))
            with self.assertRaises(EvidenceStageError) as caught:
                build_evidence(capture, max_sample_interval_s=1e-3, sampling_requirement_source=5)
            self.assertEqual(caught.exception.stage, "input")

    def test_input_error_report_does_not_call_the_payload_invalid(self):
        error = EvidenceStageError("input", "LIMIT_INVALID", "range_start must be an integer, not bool")
        report = evidence_error_report(Path("/tmp/capture"), "C1", error)
        self.assertEqual(report["stage"], "input")
        self.assertEqual(report["error"]["stage"], "input")
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "UNVERIFIED")
        _assert_axis_vocabulary(self, report)
        self.assertNotIn("INVALID", {axis["status"] for axis in report["axes"].values()})


class EvidenceLoadFailureTests(unittest.TestCase):
    def test_short_payload_is_invalid_with_the_specific_error_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = _capture(root, _dithered_square(20000, 1000))
            waveform = Path(capture["path"])
            waveform.write_bytes(waveform.read_bytes()[:-4])
            with self.assertRaises(EvidenceStageError) as caught:
                collect_evidence(root / "manifest.json", "C1")
            self.assertEqual(caught.exception.code, "LENGTH_MISMATCH")
            self.assertEqual(caught.exception.stage, "load")
            report = evidence_error_report(root / "manifest.json", "C1", caught.exception)
        self.assertEqual(report["stage"], "load")
        self.assertEqual(report["error"]["code"], "LENGTH_MISMATCH")
        self.assertEqual(report["error"]["stage"], "load")
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "INVALID")
        self.assertNotIn("COMPLETE", {axis["status"] for axis in report["axes"].values()})
        self.assertIn("load_failed:LENGTH_MISMATCH", report["limitations"])
        self.assertIn("a_refused_run_is_not_evidence_of_absence", report["limitations"])
        _assert_axis_vocabulary(self, report)

    def test_corrupt_payload_reports_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = _capture(root, _dithered_square(20000, 1000))
            waveform = Path(capture["path"])
            data = bytearray(waveform.read_bytes())
            data[len(data) // 2] ^= 0xFF
            waveform.write_bytes(bytes(data))
            with self.assertRaises(EvidenceStageError) as caught:
                collect_evidence(root / "manifest.json", "C1")
        self.assertEqual(caught.exception.code, "HASH_MISMATCH")
        report = evidence_error_report(root / "manifest.json", "C1", caught.exception)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "INVALID")

    def test_missing_manifest_is_unverified_not_invalid_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(EvidenceStageError) as caught:
                collect_evidence(root / "manifest.json", "C1")
            report = evidence_error_report(root / "manifest.json", "C1", caught.exception)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "UNVERIFIED")
        self.assertEqual(report["error"]["code"], "MANIFEST_MISSING")

    def test_failed_capture_manifest_is_unverified_not_incomplete(self):
        # CAPTURE_NOT_COMPLETE is also raised for manifest.error values that may
        # be permission, connection or unknown failures, so it must not be
        # reported as confirmed missing data.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.failed.json").write_text(json.dumps({"error": "capture failed"}), encoding="utf-8")
            with self.assertRaises(EvidenceStageError) as caught:
                collect_evidence(root, "C1")
            report = evidence_error_report(root, "C1", caught.exception)
        self.assertEqual(report["error"]["code"], "CAPTURE_NOT_COMPLETE")
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "UNVERIFIED")
        self.assertIn("load_failed:CAPTURE_NOT_COMPLETE", report["axes"]["payload_integrity"]["reasons"])
        self.assertEqual(report["error"]["reasons"], caught.exception.reasons)

    def test_missing_numpy_maps_to_unsupported(self):
        error = EvidenceStageError("load", "NUMPY_UNAVAILABLE", "NumPy >= 2.0 is required")
        report = evidence_error_report(Path("/tmp/capture"), "C1", error)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "UNSUPPORTED")

    def test_analysis_failure_keeps_the_payload_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            with mock.patch.object(
                waveform_evidence,
                "build_verdict",
                side_effect=AnalysisError("LIMIT_INVALID", "chunk_points must be positive"),
            ):
                report = build_evidence(capture)
        self.assertEqual(report["stage"], "analysis")
        self.assertEqual(report["error"]["stage"], "analysis")
        self.assertEqual(report["error"]["code"], "LIMIT_INVALID")
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
        self.assertEqual(report["axes"]["analysis_capability"]["status"], "UNVERIFIED")
        self.assertIsNone(report["sparse_candidates"])
        self.assertIn("analysis_failed:LIMIT_INVALID", report["axes"]["analysis_capability"]["reasons"])
        _assert_axis_vocabulary(self, report)

    def test_cli_input_error_keeps_the_payload_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, _dithered_square(20000, 1000))
            stdout = io.StringIO()
            with mock.patch.object(sys, "stdout", stdout):
                code = main(["--capture", str(root), "--channel", "C1", "--candidate-windows", "0"])
            self.assertEqual(code, 2)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["stage"], "input")
            self.assertEqual(report["error"]["code"], "LIMIT_INVALID")
            self.assertEqual(report["axes"]["payload_integrity"]["status"], "UNVERIFIED")
            _assert_axis_vocabulary(self, report)

    def test_cli_refused_load_exits_2_with_an_explained_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = _capture(root, _dithered_square(20000, 1000))
            Path(capture["path"]).write_bytes(b"")
            output = _sibling(root, "-evidence.json")
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(["--capture", str(root), "--channel", "C1", "--out", str(output)])
                self.assertEqual(code, 2)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(report["tool"], "evidence")
                self.assertEqual(report["stage"], "load")
                self.assertEqual(report["error"]["code"], "LENGTH_MISMATCH")
                self.assertEqual(report["axes"]["payload_integrity"]["status"], "INVALID")
            finally:
                output.unlink(missing_ok=True)

    def test_cli_analysis_failure_still_delivers_the_verified_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, _dithered_square(20000, 1000))
            output = _sibling(root, "-analysis-failed.json")
            try:
                with mock.patch.object(
                    waveform_evidence,
                    "build_verdict",
                    side_effect=AnalysisError("LIMIT_INVALID", "boom"),
                ):
                    with mock.patch.object(sys, "stdout", io.StringIO()):
                        code = main(["--capture", str(root), "--channel", "C1", "--out", str(output)])
                self.assertEqual(code, 2)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(report["stage"], "analysis")
                self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
            finally:
                output.unlink(missing_ok=True)


class EvidenceScreenshotTests(unittest.TestCase):
    def test_absent_screenshot_does_not_block_payload_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
        self.assertFalse(report["screenshot"]["present"])
        self.assertIn("screenshot_absence_does_not_block_payload_integrity", report["screenshot"]["reasons"])
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")

    def test_matching_screenshot_file_still_never_upgrades_same_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shot = _sibling(root, "-shot.png")
            payload = b"\x89PNG\r\n\x1a\ncontainer-bytes"
            shot.write_bytes(payload)
            try:
                capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), _screenshot_record(shot, payload))
                report = build_evidence(capture)
            finally:
                shot.unlink(missing_ok=True)
        self.assertEqual(report["screenshot"]["file_check"]["status"], "MATCH")
        self.assertEqual(report["screenshot"]["container"]["image_decode_status"], "UNVERIFIED")
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")
        self.assertEqual(report["screenshot"]["frame_association"]["status"], "UNVERIFIED")
        self.assertEqual(report["conflicts"], [])

    def test_missing_screenshot_hash_or_length_cannot_match(self):
        payload = b"\x89PNG\r\n\x1a\ncontainer-bytes"
        for overrides in (
            {"sha256": None},
            {"raw_bytes": None},
            {"sha256": None, "raw_bytes": None},
        ):
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    shot = _sibling(root, "-shot.png")
                    shot.write_bytes(payload)
                    try:
                        capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), _screenshot_record(shot, payload, **overrides))
                        report = build_evidence(capture)
                        self.assertEqual(report["screenshot"]["file_check"]["status"], "UNVERIFIED")
                        self.assertIn("screenshot_record_missing_raw_bytes_or_sha256", report["screenshot"]["file_check"]["reasons"])
                        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
                        self.assertEqual(report["conflicts"], [])
                    finally:
                        shot.unlink(missing_ok=True)

    def test_malformed_screenshot_metadata_is_invalid_but_screenshot_only(self):
        payload = b"\x89PNG\r\n\x1a\ncontainer-bytes"
        for overrides in (
            {"raw_bytes": True},
            {"raw_bytes": 12.5},
            {"raw_bytes": "12"},
            {"sha256": 12345},
            {"sha256": "not-a-sha"},
        ):
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    shot = _sibling(root, "-shot.png")
                    shot.write_bytes(payload)
                    try:
                        capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), _screenshot_record(shot, payload, **overrides))
                        report = build_evidence(capture)
                        self.assertEqual(report["screenshot"]["file_check"]["status"], "INVALID")
                        codes = {entry["code"] for entry in report["conflicts"]}
                        self.assertIn("screenshot_record_metadata_invalid", codes)
                        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
                        _assert_axis_vocabulary(self, report)
                    finally:
                        shot.unlink(missing_ok=True)

    def test_modified_screenshot_file_is_a_visible_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shot = _sibling(root, "-shot.png")
            payload = b"\x89PNG\r\n\x1a\ncontainer-bytes"
            shot.write_bytes(payload)
            record = _screenshot_record(shot, payload)
            try:
                capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), record)
                shot.write_bytes(payload + b"tampered")
                report = build_evidence(capture)
            finally:
                shot.unlink(missing_ok=True)
        self.assertEqual(report["screenshot"]["file_check"]["status"], "MISMATCH")
        codes = {entry["code"] for entry in report["conflicts"]}
        self.assertIn("screenshot_file_does_not_match_its_record", codes)
        self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")

    def test_screenshot_record_claiming_a_frame_or_decoded_image_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shot = _sibling(root, "-shot.png")
            payload = b"\x89PNG\r\n\x1a\ncontainer-bytes"
            shot.write_bytes(payload)
            record = _screenshot_record(
                shot,
                payload,
                frame_association={"status": "COMPLETE"},
                image_decode_status="DECODED",
            )
            try:
                capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), record)
                report = build_evidence(capture)
            finally:
                shot.unlink(missing_ok=True)
        codes = {entry["code"] for entry in report["conflicts"]}
        self.assertIn("screenshot_claims_frame_association", codes)
        self.assertIn("screenshot_claims_decoded_image", codes)
        self.assertEqual(report["axes"]["frame_association"]["status"], "UNVERIFIED")

    def test_missing_screenshot_file_for_a_valid_record_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = _sibling(root, "-absent.png")
            record = _screenshot_record(missing, b"\x89PNG\r\n\x1a\ncontainer-bytes")
            capture = _capture_with_screenshot(root, _dithered_square(20000, 1000), record)
            report = build_evidence(capture)
        self.assertEqual(report["screenshot"]["file_check"]["status"], "MISSING_FILE")
        codes = {entry["code"] for entry in report["conflicts"]}
        self.assertIn("screenshot_recorded_as_valid_but_file_is_missing", codes)


class EvidenceSparseCandidateTests(unittest.TestCase):
    def test_refusal_exposes_bounded_candidate_windows_without_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _narrow_pulse(width=200))
            report = build_evidence(capture, candidate_windows=2, candidate_window_points=512)
        sparse = report["sparse_candidates"]
        self.assertIsNotNone(sparse)
        self.assertEqual(sparse["status"], "CANDIDATES_ONLY")
        self.assertEqual(sparse["parent_verdict"]["status"], "REFUSED")
        self.assertIn("candidate_excursions", sparse["parent_verdict"]["can_claim"])
        self.assertIn("stability_and_transition_analysis", sparse["parent_verdict"]["cannot_claim"])
        self.assertGreaterEqual(sparse["candidate_count"], 1)
        self.assertEqual(sparse["scan"], "full_record_original_resolution")
        self.assertEqual(sparse["coverage"]["record_points"], capture["points"])
        self.assertEqual(sparse["coverage"]["record_sha256"], capture["raw_sha256"])
        self.assertEqual(sparse["selection"]["policy"], "first_n_candidates_in_record_order")
        self.assertFalse(sparse["selection"]["all_candidates_reviewed"])
        self.assertFalse(sparse["all_candidates_reviewed"])
        self.assertLessEqual(len(sparse["windows"]), 2)
        self.assertEqual(len(sparse["observations"]), len(sparse["windows"]))
        self.assertIn("no_additional_threshold_was_introduced", sparse["reasons"])
        for window in sparse["windows"]:
            self.assertLessEqual(len(window["codes"]), 512)
            self.assertEqual(window["record_sha256"], capture["raw_sha256"])
            recomputed = hashlib.sha256(
                b"".join(int(code).to_bytes(4, "little", signed=True) for code in window["codes"])
            ).hexdigest()
            self.assertEqual(window["codes_sha256"], recomputed)
            self.assertEqual(window["window_points"], len(window["codes"]))
        first = sparse["windows"][0]
        self.assertEqual((first["candidate_start_sample"], first["candidate_end_sample"]), (150000, 150200))
        self.assertTrue(first["covers_candidate"])
        self.assertIn("not a level", sparse["observations"][0]["observation"])

    def test_window_list_truncation_is_flagged(self):
        values = [0] * 50000 + [200] * 200 + [0] * 20000 + [200] * 200 + [0] * 20000
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), values)
            report = build_evidence(capture, candidate_windows=1, candidate_window_points=256)
        sparse = report["sparse_candidates"]
        self.assertEqual(len(sparse["windows"]), 1)
        self.assertEqual(len(sparse["observations"]), 1)
        self.assertTrue(sparse["windows_truncated"])
        self.assertEqual(sparse["selection"]["windows_selected"], 1)

    def test_capped_candidate_list_is_surfaced(self):
        values = [100] * 150000
        for index in range(300):
            values[index * 500] = 200
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), values)
            report = build_evidence(capture, candidate_windows=2)
        sparse = report["sparse_candidates"]
        self.assertEqual(sparse["parent_verdict"]["status"], "REFUSED")
        self.assertGreaterEqual(sparse["candidate_count"], 300)
        self.assertTrue(sparse["candidates_truncated"])
        self.assertLessEqual(sparse["candidates_returned"], 200)
        self.assertGreater(sparse["candidate_count"], sparse["candidates_returned"])
        self.assertIn("candidates_capped_to_200", " ".join(sparse["limitations"]))
        self.assertFalse(sparse["all_candidates_reviewed"])

    def test_observed_verdict_has_no_sparse_candidate_block(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(200000, 2000), width=2, sample_interval=50e-9)
            report = build_evidence(capture, candidate_windows=2, candidate_window_points=256)
        self.assertIsNone(report["sparse_candidates"])


class EvidenceSamplingRequirementTests(unittest.TestCase):
    def test_missing_requirement_is_a_limitation_not_a_capability_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _narrow_pulse(width=200))
            report = build_evidence(capture)
        axis = report["axes"]["analysis_capability"]
        requirement = axis["evidence"]["sampling_requirement"]
        self.assertEqual(requirement["status"], "MISSING")
        self.assertIn("task_sampling_requirement_not_stated", requirement["reasons"])
        self.assertEqual(axis["status"], "UNVERIFIED")
        self.assertIn("sampling_requirement_not_stated", report["limitations"])
        self.assertIn("sampling_requirement_not_stated", axis["reasons"])

    def test_requirement_without_source_is_missing_with_its_own_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            report = build_evidence(capture, max_sample_interval_s=1e-3)
        requirement = report["axes"]["analysis_capability"]["evidence"]["sampling_requirement"]
        self.assertEqual(requirement["status"], "MISSING")
        self.assertEqual(requirement["reasons"], ["task_sampling_requirement_stated_without_source_text"])

    def test_satisfied_requirement_never_promotes_the_capability_axis(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _narrow_pulse(width=200))
            report = build_evidence(
                capture,
                max_sample_interval_s=1e-3,
                sampling_requirement_source="datasheet: bit period 100 us",
            )
        axis = report["axes"]["analysis_capability"]
        requirement = axis["evidence"]["sampling_requirement"]
        self.assertEqual(requirement["status"], "SATISFIED")
        self.assertEqual(requirement["source"], "datasheet: bit period 100 us")
        self.assertEqual(requirement["max_sample_interval_s"], 1e-3)
        self.assertEqual(axis["status"], "UNVERIFIED")
        self.assertIn("refused_verdict_capability_unverified", axis["reasons"])
        self.assertNotIn("protocol_decodability_or_option_availability", axis["evidence"]["verdict"]["can_claim"])

    def test_satisfied_requirement_with_observed_verdict_keeps_claims_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(200000, 2000), width=2, sample_interval=50e-9)
            report = build_evidence(
                capture,
                max_sample_interval_s=2e-6,
                sampling_requirement_source="task states 500 kSa/s minimum",
            )
        axis = report["axes"]["analysis_capability"]
        self.assertEqual(axis["status"], "COMPLETE")
        self.assertEqual(axis["evidence"]["sampling_requirement"]["status"], "SATISFIED")
        self.assertEqual(axis["evidence"]["verdict"]["status"], "OBSERVED")

    def test_insufficient_sampling_adds_blocked_task_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _narrow_pulse(width=200))
            report = build_evidence(
                capture,
                max_sample_interval_s=1e-9,
                sampling_requirement_source="datasheet: 1 ns bit period",
            )
        axis = report["axes"]["analysis_capability"]
        requirement = axis["evidence"]["sampling_requirement"]
        self.assertEqual(requirement["status"], "INSUFFICIENT")
        self.assertEqual(requirement["blocked_task_claims"], ["sampling_requirement_insufficient_for_the_stated_task"])
        self.assertIn("sampling_requirement_insufficient", axis["reasons"])
        self.assertIn("sampling_requirement_insufficient", report["limitations"])
        self.assertEqual(axis["status"], "UNVERIFIED")
        self.assertTrue(axis["evidence"]["verdict"]["cannot_claim"])

    def test_orphan_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = _capture(Path(directory), _dithered_square(20000, 1000))
            with self.assertRaises(EvidenceStageError) as caught:
                build_evidence(capture, sampling_requirement_source="orphan statement")
        self.assertEqual(caught.exception.code, "LIMIT_INVALID")


class EvidenceOutputTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        _write_capture(root, _narrow_pulse(width=200))

    def test_success_report_respects_the_json_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            output = _sibling(root, "-ok.json")
            svg = _sibling(root, "-ok.svg")
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(
                        [
                            "--capture",
                            str(root),
                            "--channel",
                            "C1",
                            "--candidate-windows",
                            "2",
                            "--candidate-window-points",
                            "512",
                            "--max-json-bytes",
                            "12000",
                            "--svg",
                            str(svg),
                            "--out",
                            str(output),
                        ]
                    )
                self.assertEqual(code, 0)
                self.assertLessEqual(len(output.read_bytes()), 12000)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertLessEqual(len(json.dumps(report, separators=(",", ":"), sort_keys=True).encode()), 12000)
            finally:
                output.unlink(missing_ok=True)
                svg.unlink(missing_ok=True)

    def test_budget_trimming_keeps_windows_observations_and_svg_in_sync(self):
        values = [0] * 50000 + [200] * 200 + [0] * 20000 + [200] * 200 + [0] * 20000
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            output = _sibling(root, "-trim.json")
            svg = _sibling(root, "-trim.svg")
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(
                        [
                            "--capture",
                            str(root),
                            "--channel",
                            "C1",
                            "--candidate-windows",
                            "2",
                            "--candidate-window-points",
                            "1024",
                            "--max-json-bytes",
                            "12500",
                            "--svg",
                            str(svg),
                            "--out",
                            str(output),
                        ]
                    )
                self.assertEqual(code, 0)
                report = json.loads(output.read_text(encoding="utf-8"))
                sparse = report["sparse_candidates"]
                self.assertTrue(report["truncated"])
                self.assertEqual(len(sparse["observations"]), len(sparse["windows"]))
                self.assertEqual(
                    [entry["candidate_index"] for entry in sparse["observations"]],
                    [window["candidate_index"] for window in sparse["windows"]],
                )
                self.assertEqual(sparse["selection"]["windows_selected"], len(sparse["windows"]))
                if report["svg"]["written"]:
                    self.assertEqual(report["svg"]["windows_plotted"], len(sparse["windows"]))
                    self.assertEqual(
                        report["svg"]["points_plotted"],
                        sum(len(window["codes"]) for window in sparse["windows"]),
                    )
                    self.assertTrue(svg.exists())
                else:
                    self.assertEqual(sparse["windows"], [])
                    self.assertFalse(svg.exists())
                self.assertLessEqual(len(output.read_bytes()), 12500)
            finally:
                output.unlink(missing_ok=True)
                svg.unlink(missing_ok=True)

    def test_impossible_budget_fails_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            output = _sibling(root, "-tiny.json")
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
                    code = main(["--capture", str(root), "--channel", "C1", "--max-json-bytes", "1500", "--out", str(output)])
                self.assertEqual(code, 2)
                self.assertFalse(output.exists())
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn("does not fit", stderr.getvalue())
            finally:
                output.unlink(missing_ok=True)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            output = _sibling(root, "-exists.json")
            output.write_text("previous", encoding="utf-8")
            stdout = io.StringIO()
            try:
                with mock.patch.object(sys, "stdout", stdout):
                    code = main(["--capture", str(root), "--channel", "C1", "--out", str(output)])
                self.assertEqual(code, 2)
                self.assertEqual(output.read_text(encoding="utf-8"), "previous")
                report = json.loads(stdout.getvalue())
                self.assertEqual(report["stage"], "output")
                self.assertEqual(report["operation_error"]["stage"], "output")
                self.assertEqual(report["axes"]["payload_integrity"]["status"], "COMPLETE")
            finally:
                output.unlink(missing_ok=True)

    def test_symlink_output_is_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            target = _sibling(root, "-target.txt")
            link = _sibling(root, "-link.json")
            target.write_text("keep", encoding="utf-8")
            os.symlink(target, link)
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(["--capture", str(root), "--channel", "C1", "--out", str(link)])
                self.assertEqual(code, 2)
                self.assertTrue(link.is_symlink())
                self.assertEqual(target.read_text(encoding="utf-8"), "keep")
            finally:
                link.unlink(missing_ok=True)
                target.unlink(missing_ok=True)

    def test_hardlinked_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            target = _sibling(root, "-hard-target.txt")
            link = _sibling(root, "-hard-link.json")
            target.write_text("keep", encoding="utf-8")
            os.link(target, link)
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(["--capture", str(root), "--channel", "C1", "--out", str(link)])
                self.assertEqual(code, 2)
                self.assertEqual(target.read_text(encoding="utf-8"), "keep")
            finally:
                link.unlink(missing_ok=True)
                target.unlink(missing_ok=True)

    def test_out_equal_to_svg_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            same = _sibling(root, "-same.out")
            stdout = io.StringIO()
            try:
                with mock.patch.object(sys, "stdout", stdout):
                    code = main(
                        [
                            "--capture",
                            str(root),
                            "--channel",
                            "C1",
                            "--out",
                            str(same),
                            "--svg",
                            str(same),
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertFalse(same.exists())
                report = json.loads(stdout.getvalue())
                self.assertEqual(report["stage"], "input")
                self.assertIn("must be different", report["error"]["message"])
            finally:
                same.unlink(missing_ok=True)

    def test_output_inside_the_capture_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, _dithered_square(20000, 1000))
            stdout = io.StringIO()
            with mock.patch.object(sys, "stdout", stdout):
                code = main(["--capture", str(root), "--channel", "C1", "--out", str(root / "evidence.json")])
            self.assertEqual(code, 2)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["stage"], "input")
            self.assertFalse((root / "evidence.json").exists())

    def test_bad_max_json_bytes_is_an_input_error_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
                code = main(["--capture", str(root), "--channel", "C1", "--max-json-bytes", "0"])
            self.assertEqual(code, 2)
            self.assertIn("does not fit", stderr.getvalue())

    def test_svg_markers_are_the_raw_samples_and_the_line_is_a_display_aid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            output = _sibling(root, "-svg.json")
            svg = _sibling(root, "-svg.svg")
            try:
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = main(
                        [
                            "--capture",
                            str(root),
                            "--channel",
                            "C1",
                            "--candidate-windows",
                            "1",
                            "--candidate-window-points",
                            "128",
                            "--svg",
                            str(svg),
                            "--out",
                            str(output),
                        ]
                    )
                self.assertEqual(code, 0)
                report = json.loads(output.read_text(encoding="utf-8"))
                document = svg.read_text(encoding="utf-8")
                window = report["sparse_candidates"]["windows"][0]
                self.assertEqual(report["svg"]["sha256"], hashlib.sha256(document.encode("utf-8")).hexdigest())
                self.assertEqual(report["svg"]["markers"], "one_circle_per_raw_sample")
                self.assertEqual(document.count("<circle"), len(window["codes"]))
                self.assertEqual(document.count("<polyline"), 1)
                self.assertIn("the line only connects them", document)
                self.assertNotIn("no interpolation", document)
                self.assertNotIn("V/div", document)
            finally:
                output.unlink(missing_ok=True)
                svg.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
