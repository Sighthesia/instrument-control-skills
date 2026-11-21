#!/usr/bin/env python3
"""Offline tests for waveform_analysis: summary, events, structure, regimes."""

import hashlib
import inspect
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

import waveform_analysis
import waveform_bundle
from waveform_analysis import (
    AnalysisError,
    analyze_pulse_structure,
    analyze_ringing,
    bound_json,
    find_events,
    get_window,
    load_capture,
    m4_preview,
    summarize_capture,
    analyze_waveform_regimes,
    attach_three_way_status,
)


def _write_capture(root: Path, values, *, width: int = 1, stored_root: Path | None = None, snapshot_vdiv: float | None = None, sample_interval: float = 1e-6, snapshot_style: str = "firmware", preamble_start: int = 0) -> Path:
    channel = "C1"
    channel_dir = root / channel
    channel_dir.mkdir(parents=True)
    if width == 1:
        payload = bytes((int(value) % 256 for value in values))
        comm_type = 0
        nominal_bits = 8
    else:
        payload = b"".join(int(value).to_bytes(2, "little", signed=True) for value in values)
        comm_type = 1
        nominal_bits = 16
    waveform = channel_dir / "waveform.bin"
    waveform.write_bytes(payload)
    segment = channel_dir / "segment-000000.bin"
    segment.write_bytes(payload)
    points = len(values)
    preamble = {
        "description": "WAVEDESC",
        "comm_type": comm_type,
        "comm_order": 0,
        "byte_order": "LSB",
        "data_width_bytes": width,
        "nominal_bits": nominal_bits,
        "sparsing_factor": 1,
        "wave_array_count": points,
        "wave_array_1_bytes": len(payload),
        "sample_interval": sample_interval,
        "horizontal_offset": 0.0,
        "timebase_s": 1.0,
        "start": preamble_start,
        "vdiv": 2.0 if width == 1 else 1.0,
        "probe": 1.0,
        "offset": 0.0,
        "code_per_div": 10.0,
    }
    result = {
        "channel": channel,
        "frame_report": {"status": "COMPLETE"},
        "segment_report": {"status": "COMPLETE", "downloaded_points": points, "downloaded_payload_bytes": len(payload)},
        "merged_waveform": str((stored_root or root) / channel / "waveform.bin"),
        "merged_waveform_bytes": len(payload),
        "merged_waveform_sha256": hashlib.sha256(payload).hexdigest(),
        "preamble": preamble,
        "segments": [{
            "requested_start": 0,
            "requested_points": points,
            "actual_payload_bytes": len(payload),
            "payload": str((stored_root or root) / channel / "segment-000000.bin"),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }],
    }
    snapshot_vdiv = snapshot_vdiv if snapshot_vdiv is not None else preamble["vdiv"]
    # Real capture manifests store the decorated firmware reply, not a bare
    # float: "C1:VDIV 5.00E+00V" / "C1:OFST 0.00E+00V". A fixture that writes
    # str(2.0) never exercises the prefix stripping, so the snapshot cross-check
    # could silently stop running without a single failing test.
    if snapshot_style == "firmware":
        channel_snapshot = {
            "vdiv": f"{channel}:VDIV {snapshot_vdiv:.2E}V",
            "offset": f"{channel}:OFST 0.00E+00V",
        }
    elif snapshot_style == "unparseable":
        channel_snapshot = {"vdiv": "C1:VDIV <timeout>", "offset": "C1:OFST <timeout>"}
    elif snapshot_style == "missing":
        channel_snapshot = {}
    else:
        channel_snapshot = {"vdiv": str(snapshot_vdiv), "offset": "0"}
    manifest = {
        "idn": "synthetic,SDS824X HD,test,1",
        "capture_configuration": {"channels": {channel: channel_snapshot}},
        "results": [result],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root / "manifest.json"


def _write_modern_capture(
    root: Path,
    values,
    *,
    scope_points: int,
    scope_duration_s: float,
    sample_interval: float = 1e-6,
    preamble_start: int = 0,
    frame_status: str = "COMPLETE",
    reasons=(),
    screen_semantics: bool = True,
    mode: str = "configured_capture",
) -> Path:
    """Modern WAVEDESC manifest whose frame report may predate screen semantics.

    The transfer itself (preamble, merged bytes, segment metadata, hashes) is the
    same consistent payload `_write_capture` generates; only the frame report and
    the configured_capture mode are added, so a re-derived frame must reproduce
    exactly that record.
    """

    manifest_path = _write_capture(root, values, sample_interval=sample_interval, preamble_start=preamble_start)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mode"] = mode
    result = manifest["results"][0]
    result["mode"] = mode
    preamble = result["preamble"]
    points = preamble["wave_array_count"]
    payload_bytes = points * preamble["data_width_bytes"]
    scope_record = {"points": scope_points, "duration_s": scope_duration_s}
    if screen_semantics:
        scope_record["semantics"] = "screen"
    result["frame_report"] = {
        "status": frame_status,
        "reasons": list(reasons),
        "scope_record": scope_record,
        "wavedesc_record": {"points": points, "sample_interval_s": sample_interval},
        "downloaded": {"points": points, "duration_s": points * sample_interval},
        "waveform_format": {
            "bytes_per_point": preamble["data_width_bytes"],
            "expected_payload_bytes": payload_bytes,
            "downloaded_payload_bytes": payload_bytes,
            "byte_order": "LSB",
            "nominal_bits": preamble["nominal_bits"],
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_bundle(
    root: Path,
    samples,
    *,
    dtype: str = "u1",
    zero_code=127.0,
    code_scale_v=0.02,
    offset_v=0.0,
    vdiv=0.5,
    units: str = "V",
    scale_usable: bool = True,
    calibration_status: str = "VERIFIED",
    adc=(0, 255),
    sample_interval_s: float = 2e-7,
    time_origin_s: float = 0.0,
    channel: str = "CH1",
    instrument_measurements=None,
) -> Path:
    """Write one ``waveform-bundle/v1`` document plus the payload it names."""

    body = np.asarray(samples, dtype=np.dtype(dtype)).tobytes()
    (root / "waveform.bin").write_bytes(body)
    bundle = {
        "schema": "waveform-bundle/v1",
        "source": {
            "vendor": "test",
            "model": "TEST-SCOPE",
            "idn": "TEST,TEST-SCOPE,0,1.0",
            "channel": channel,
            "captured_at": "2026-11-21T00:00:00Z",
        },
        "data": {
            "file": "waveform.bin",
            "sha256": hashlib.sha256(body).hexdigest(),
            "dtype": dtype,
            "points": len(samples),
            "byte_offset": 0,
            "byte_length": len(body),
            "width_bytes": np.dtype(dtype).itemsize,
        },
        "time_axis": {
            "sample_interval_s": sample_interval_s,
            "time_origin_s": time_origin_s,
            "reference": "descriptor",
        },
        "vertical": {
            "units": units,
            "scale_usable": scale_usable,
            "zero_code": zero_code,
            "code_scale_v": code_scale_v,
            "offset_v": offset_v,
            "vdiv_v_per_div": vdiv,
            "adc_min_code": None if adc is None else adc[0],
            "adc_max_code": None if adc is None else adc[1],
            "calibration_status": calibration_status,
            "calibration_source": "test_adapter",
            "scale_reasons": [],
        },
        "integrity": {
            "status": "COMPLETE",
            "bytes_complete": True,
            "checks": ["payload framing"],
            "status_meaning": "payload framing/count integrity only",
        },
        "instrument_measurements": instrument_measurements,
    }
    path = root / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def _write_csv(path: Path, interval_s: float, values) -> Path:
    """Write ``time_s,value`` rows with enough digits to round-trip exactly."""

    rows = ["time_s,value"] + [f"{index * interval_s!r},{value!r}" for index, value in enumerate(values)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


class WaveformAnalysisTests(unittest.TestCase):
    def test_byte_summary_uses_integer_statistics_and_bounded_m4(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [-10, 0, 10, 20, 30, 40])
            capture = load_capture(root, "C1")
            summary = summarize_capture(capture, chunk_points=2, preview_buckets=3)
            self.assertEqual(summary["integrity"]["status"], "COMPLETE")
            self.assertEqual(summary["summary"]["count"], 6)
            self.assertEqual(summary["summary"]["min_v"], -2.0)
            self.assertEqual(summary["summary"]["max_v"], 8.0)
            self.assertEqual(summary["preview"]["bucket_count"], 3)
            self.assertLessEqual(summary["preview"]["selected_points"], 12)
            self.assertTrue(all(0 <= point["sample"] < 6 for point in summary["preview"]["points"]))

    def test_word_capture_is_code_only_without_external_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [-256, 0, 256, 512], width=2)
            capture = load_capture(root, "C1")
            self.assertEqual(capture["calibration"]["status"], "OBSERVED_UNVERIFIED")
            summary = summarize_capture(capture, preview_buckets=2)
            self.assertIn("min_code", summary["summary"])
            self.assertNotIn("min_v", summary["summary"])
            window = get_window(capture, 1, 2)
            self.assertEqual(window["window"]["codes"], [0, 256])
            self.assertNotIn("volts", window["window"])

    def test_word_external_calibration_requires_matching_capture_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [-256, 0, 256], width=2)
            capture = load_capture(root, "C1")
            calibration_path = root.parent / "calibration.json"
            calibration_path.write_text(json.dumps({"channels": {"C1": {
                "word_scale_verified": True,
                "capture_sha256": capture["raw_sha256"],
                "word_codes_per_div": 7680,
                "vdiv_v_per_div": 1.0,
                "offset_v": 0.0,
                "evidence": "known DC reference and BYTE/WORD comparison",
            }}}))
            calibrated = load_capture(root, "C1", calibration_file=calibration_path)
            self.assertEqual(calibrated["calibration"]["status"], "VALID")
            self.assertEqual(summarize_capture(calibrated, preview_buckets=1)["summary"]["min_v"], -256 / 7680)
            calibration_path.write_text(json.dumps({"channels": {"C1": {
                "word_scale_verified": True,
                "capture_sha256": "0" * 64,
                "word_codes_per_div": 7680,
                "vdiv_v_per_div": 1.0,
                "offset_v": 0.0,
                "evidence": "stale evidence",
            }}}))
            stale = load_capture(root, "C1", calibration_file=calibration_path)
            self.assertEqual(stale["calibration"]["status"], "OBSERVED_UNVERIFIED")
            self.assertIn("calibration_capture_sha256_mismatch", stale["calibration"]["verification_failures"])

    def test_firmware_decorated_snapshot_vdiv_overrides_placeholder_descriptor(self):
        # Legacy WAVEDESC on 4.8.12.1.1.5 reported vdiv=0.2/probe=10 on every
        # channel (a flat 2 V/div) while the panel ran something else. Reading
        # that descriptor with the decorated reply unparsed reported VALID with
        # the placeholder scale, scaling voltages by 2.5x on a 5 V/div channel.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 10, -10], snapshot_vdiv=5.0)
            capture = load_capture(root, "C1")
            calibration = capture["calibration"]
            self.assertEqual(calibration["status"], "VALID")
            self.assertEqual(calibration["snapshot_vdiv"], 5.0)
            # Descriptor says 2 V/div; the panel snapshot must win.
            self.assertEqual(calibration["effective_vdiv_v_per_div"], 5.0)
            self.assertAlmostEqual(calibration["code_scale_v"], 5.0 / 10.0)
            self.assertIn("panel_snapshot_vdiv_overrides_descriptor", calibration["checks"])
            self.assertNotIn("descriptor_scale_does_not_match_snapshot_vdiv", calibration["verification_failures"])
            self.assertEqual(summarize_capture(capture, preview_buckets=1)["summary"]["max_v"], 5.0)

    def test_unparseable_snapshot_fails_closed_instead_of_skipping_the_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 10, -10], snapshot_style="unparseable")
            capture = load_capture(root, "C1")
            calibration = capture["calibration"]
            self.assertNotEqual(calibration["status"], "VALID")
            self.assertEqual(calibration["units"], "code")
            self.assertIn("capture_snapshot_vdiv_unparseable", calibration["verification_failures"])
            self.assertIn("capture_snapshot_offset_unparseable", calibration["verification_failures"])
            self.assertNotIn("min_v", summarize_capture(capture, preview_buckets=1)["summary"])

    def test_bare_number_snapshot_still_parses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 10], snapshot_vdiv=2.0, snapshot_style="bare")
            calibration = load_capture(root, "C1")["calibration"]
            self.assertEqual(calibration["status"], "VALID")
            self.assertEqual(calibration["snapshot_vdiv"], 2.0)
            self.assertIn("descriptor_vdiv_times_probe_matches_capture_snapshot", calibration["checks"])

    def test_descriptor_start_offsets_the_reported_origin(self):
        # DAT2 can return a slice that does not start at record sample 0. Ignoring
        # `start` shifted every event time by start*interval while the capture
        # still counted as COMPLETE.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 10, -10], sample_interval=1e-3, preamble_start=1500)
            capture = load_capture(root, "C1")
            self.assertEqual(capture["time_origin_s"], 0.0 - 5.0 + 1500 * 1e-3)
            self.assertEqual(get_window(capture, 0, 3)["window"]["start_time_s"], -3.5)

    def test_relocated_manifest_falls_back_to_capture_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            moved = Path(directory) / "moved"
            _write_capture(source, [1, 2, 3, 4])
            shutil.move(str(source), str(moved))
            manifest = json.loads((moved / "manifest.json").read_text())
            manifest["results"][0]["merged_waveform"] = str(source / "C1" / "waveform.bin")
            manifest["results"][0]["segments"][0]["payload"] = str(source / "C1" / "segment-000000.bin")
            (moved / "manifest.json").write_text(json.dumps(manifest))
            capture = load_capture(moved, "C1")
            self.assertEqual(capture["path"], (moved / "C1" / "waveform.bin").resolve())

    def test_integrity_rejects_short_segment_even_when_requested_count_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_capture(root, [0, 1, 2, 3])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            segment = manifest["results"][0]["segments"][0]
            segment["actual_payload_bytes"] = 3
            segment["actual_points"] = 3
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "DESCRIPTOR_MISMATCH")

    def test_integrity_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [1, 2, 3])
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["results"][0]["merged_waveform_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(AnalysisError) as context:
                load_capture(root, "C1")
            self.assertEqual(context.exception.code, "HASH_MISMATCH")

    def test_screen_semantics_frame_loads_when_scope_points_differ_from_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(root, [0, 10, -10, 0], scope_points=2, scope_duration_s=1.0)
            capture = load_capture(root, "C1")
            result_frame = capture["result"]["frame_report"]
            self.assertEqual(capture["integrity"]["status"], "COMPLETE")
            self.assertEqual(capture["integrity"]["segments_verified"], 1)
            self.assertEqual(result_frame["scope_record"]["semantics"], "screen")
            self.assertNotEqual(result_frame["scope_record"]["points"], capture["points"])
            self.assertEqual(capture["screen_range"]["status"], "UNVERIFIED")
            self.assertIs(capture["screen_range"]["point_counts_equal"], False)
            self.assertEqual(capture["screen_range_revalidation"], {"applied": False})

    def test_attached_screen_record_without_declared_semantics_is_refused(self):
        # A `screen_record` block alone must not upgrade the frame: only an
        # explicit `scope_record.semantics = "screen"` declares the readback.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6, screen_semantics=False)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["results"][0]["frame_report"]["screen_record"] = {
                "points": 2,
                "duration_s": 4e-6,
                "source": "ACQ:POINts? screen waveform sample count",
                "semantics": "screen_display_record",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "DESCRIPTOR_MISMATCH")

    def test_legacy_screen_incomplete_needs_the_opt_in_flag(self):
        reasons = ["screen record 2 differs from WAVEDESC 4", "scope duration 1.0 s differs from WAVEDESC duration 4e-06 s"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=1.0,
                frame_status="INCOMPLETE", reasons=reasons, screen_semantics=False,
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            with self.assertRaises(AnalysisError):
                load_capture(root, "C1", revalidate_screen_range=False)

    def test_revalidation_flag_derives_screen_frame_and_keeps_manifest_recorded(self):
        reasons = ["screen record 2 differs from WAVEDESC 4", "scope duration 1.0 s differs from WAVEDESC duration 4e-06 s"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=1.0,
                frame_status="INCOMPLETE", reasons=reasons, screen_semantics=False,
            )
            original_bytes = manifest_path.read_bytes()
            manifest_sha256 = hashlib.sha256(original_bytes).hexdigest()
            capture = load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(capture["integrity"]["status"], "COMPLETE")
            derived = capture["result"]["frame_report"]
            self.assertEqual(derived["status"], "COMPLETE")
            self.assertEqual(derived["scope_record"]["semantics"], "screen")
            self.assertEqual(capture["result"]["original_frame_report"], {"status": "INCOMPLETE", "reasons": reasons})
            record = capture["screen_range_revalidation"]
            self.assertTrue(record["applied"])
            self.assertEqual(record["scope"], "in_memory_derived_report_only")
            self.assertEqual(record["original_frame_status"], "INCOMPLETE")
            self.assertEqual(record["original_frame_reasons"], reasons)
            self.assertEqual(record["source_manifest_sha256"], manifest_sha256)
            self.assertEqual(capture["manifest_sha256"], manifest_sha256)
            self.assertEqual(manifest_path.read_bytes(), original_bytes)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["results"][0]["frame_report"]["status"], "INCOMPLETE")

    def test_revalidation_flag_refuses_unknown_reason_and_wrong_mode(self):
        known = ["screen record 2 differs from WAVEDESC 4"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=known + ["downloaded 3 points, expected 4"],
                screen_semantics=False,
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            self.assertTrue(any("unknown frame reason" in reason for reason in caught.exception.reasons))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=known, screen_semantics=False,
                mode="immutable_capture",
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            self.assertIn("configured_capture", str(caught.exception))

    def test_revalidation_flag_refuses_reasons_that_do_not_match_the_recorded_fields(self):
        # A forged legacy-looking reason still has to be what the recorded frame
        # fields actually produce; the frame is re-derived, not trusted.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE",
                reasons=["screen record 3 differs from WAVEDESC 4"],
                screen_semantics=False,
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            self.assertIn("do not match the recorded fields", str(caught.exception))
            self.assertIn("screen record 2 differs from WAVEDESC 4", caught.exception.reasons)

    def test_revalidation_flag_refuses_attached_screen_record_without_declared_semantics(self):
        # A `screen_record` block without `scope_record.semantics = "screen"` is
        # contradictory evidence: the writer that emits one always declares the
        # other, so the flag must not relabel such a frame either.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=["screen record 2 differs from WAVEDESC 4"],
                screen_semantics=False,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["results"][0]["frame_report"]["screen_record"] = {
                "points": 2,
                "duration_s": 4e-6,
                "semantics": "screen_display_record",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")

    def test_revalidation_flag_refuses_hash_mismatch_and_missing_segment(self):
        reasons = ["screen record 2 differs from WAVEDESC 4"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=reasons, screen_semantics=False,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["results"][0]["merged_waveform_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "HASH_MISMATCH")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=reasons, screen_semantics=False,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["results"][0]["segments"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            self.assertTrue(any("segment metadata" in reason for reason in caught.exception.reasons))

    def test_revalidated_screen_frame_does_not_compensate_a_15_ms_origin(self):
        reasons = ["screen record 2 differs from WAVEDESC 4"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE", reasons=reasons, screen_semantics=False,
                sample_interval=1e-6, preamble_start=15_000,
            )
            capture = load_capture(root, "C1", revalidate_screen_range=True)
            # Descriptor coordinates only: horizontal_offset - timebase * 5 + start * interval.
            self.assertEqual(capture["time_origin_s"], -5.0 + 15_000 * 1e-6)
            window = get_window(capture, 0, 2)
            self.assertEqual(window["window"]["start_time_s"], capture["time_origin_s"])
            self.assertAlmostEqual(
                window["window"]["resolved_end_time_s"] - window["window"]["resolved_start_time_s"], 2e-6, delta=1e-12
            )
            # A 15 ms screen-time convention would move the origin; it is never applied.
            self.assertNotAlmostEqual(capture["time_origin_s"], -5.0 + 15_000 * 1e-6 - 0.015, places=9)

    def test_event_crosses_chunk_boundary_and_cursor_is_deterministic(self):
        values = [0] * 5 + [10] * 4 + [0] * 5 + [10] * 5 + [0] * 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            first = find_events(capture, low=2, high=8, chunk_points=6, min_pulse_s=6e-6, limit=2)
            self.assertGreaterEqual(first["events"]["total"], 4)
            self.assertTrue(first["events"]["page_truncated"])
            self.assertTrue(first["events"]["next_cursor"])
            second = find_events(capture, low=2, high=8, chunk_points=6, min_pulse_s=6e-6, limit=20, cursor=first["events"]["next_cursor"])
            first_keys = {(item["start_sample"], item["type"]) for item in first["events"]["items"]}
            second_keys = {(item["start_sample"], item["type"]) for item in second["events"]["items"]}
            self.assertTrue(first_keys.isdisjoint(second_keys))
            self.assertTrue(any(item["type"] == "runt_pulse" for item in first["events"]["items"] + second["events"]["items"]))
            repeat = find_events(capture, low=2, high=8, chunk_points=6, min_pulse_s=6e-6, limit=2)
            self.assertEqual(first["events"]["items"], repeat["events"]["items"])

    def test_event_scan_budget_reports_lower_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = [0, 10] * 100
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            report = find_events(capture, low=2, high=8, chunk_points=7, max_events_scanned=3)
            self.assertTrue(report["events"]["scan_truncated"])
            self.assertTrue(report["events"]["total_is_lower_bound"])
            self.assertIn("transition_density_exceeds_budget", report["coverage"]["limitations"])

    def test_event_detector_reports_insufficient_period_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 0, 10, 10, 0, 0])
            capture = load_capture(root, "C1")
            report = find_events(capture, low=2, high=8, chunk_points=3)
            self.assertEqual(report["detector"]["status"], "insufficient_evidence")
            self.assertIn("insufficient_period_evidence", report["coverage"]["limitations"])

    def test_time_ranged_window_resolves_display_time_to_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, list(range(20)))
            capture = load_capture(root, "C1")
            origin = capture["time_origin_s"]
            window = get_window(capture, start_time_s=origin + 3e-6, end_time_s=origin + 8e-6)
            self.assertEqual(window["window"]["start_sample"], 3)
            self.assertEqual(window["window"]["end_sample_exclusive"], 8)
            self.assertEqual(window["window"]["codes"], [3, 4, 5, 6, 7])
            self.assertEqual(window["window"]["resolved_start_time_s"], origin + 3e-6)
            self.assertEqual(window["window"]["resolved_end_time_s"], origin + 8e-6)

    def test_window_rejects_mixed_sample_and_time_selectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, list(range(20)))
            capture = load_capture(root, "C1")
            with self.assertRaises(AnalysisError) as context:
                get_window(capture, 3, 2, start_time_s=capture["time_origin_s"], end_time_s=capture["time_origin_s"] + 2e-6)
            self.assertEqual(context.exception.code, "LIMIT_INVALID")

    def test_time_ranged_event_scan_reports_limited_coverage(self):
        values = [0] * 3 + [10] * 3 + [0] * 3 + [10] * 3 + [0] * 3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            origin = capture["time_origin_s"]
            report = find_events(capture, low=2, high=8, start_time_s=origin + 3e-6, end_time_s=origin + 12e-6, limit=10)
            self.assertEqual(report["coverage"]["scanned_start"], 3)
            self.assertEqual(report["coverage"]["scanned_end_exclusive"], 12)
            self.assertFalse(report["coverage"]["full_record_scanned"])
            self.assertTrue(report["events"]["items"])

    def test_ringing_reports_edge_overshoot_and_frequency(self):
        values = [0] * 8 + [10, 24, 4, 19, 7, 15, 9, 12, 10, 10, 10, 10]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            origin = capture["time_origin_s"]
            report = analyze_ringing(capture, start_time_s=origin, end_time_s=origin + len(values) * 1e-6)
            self.assertEqual(report["ringing"]["status"], "evidence_found")
            self.assertGreater(report["ringing"]["positive_overshoot"], 0)
            self.assertIsNotNone(report["ringing"]["frequency_hz"])
            self.assertTrue(report["coverage"]["capture_right_boundary"])
            self.assertIn("analysis_window_touches_capture_boundary", report["coverage"]["limitations"])

    def test_ringing_rejects_too_small_window_and_flags_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10])
            capture = load_capture(root, "C1")
            with self.assertRaises(AnalysisError) as context:
                analyze_ringing(capture, start=0, count=8)
            self.assertEqual(context.exception.code, "INSUFFICIENT_DATA")
            report = analyze_ringing(capture, start=0, count=12)
            self.assertEqual(report["ringing"]["status"], "insufficient_evidence")

    def test_bounds_and_invalid_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [1, 2, 3, 4])
            capture = load_capture(root, "C1")
            with self.assertRaises(AnalysisError):
                get_window(capture, 3, 2)
            with self.assertRaises(AnalysisError):
                m4_preview(capture, 2001)
            with self.assertRaises(AnalysisError):
                bound_json({"events": {"items": [{"x": "a" * 1000}] * 100}}, 10)

    def test_json_bound_is_enforced_by_compact_serialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, list(range(-128, 128)) * 4)
            capture = load_capture(root, "C1")
            result = summarize_capture(capture, preview_buckets=256)
            bounded = bound_json(result, 16 * 1024)
            encoded = json.dumps(bounded, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
            self.assertLessEqual(len(encoded), 16 * 1024)
            self.assertTrue(bounded["truncated"])


class PulseStructureTests(unittest.TestCase):
    """Raw edge -> pulse -> cluster -> classification reconstruction tests."""

    def _structure(self, root: Path, **kwargs):
        capture = load_capture(root, "C1")
        kwargs.setdefault("low", 2)
        kwargs.setdefault("high", 8)
        return analyze_pulse_structure(capture, **kwargs)

    def test_twenty_narrow_pulses_are_all_found_where_sparse_sampling_misses_them(self):
        total = 600
        width = 2
        starts = [5 + 30 * index for index in range(20)]
        values = [0] * total
        for start in starts:
            for offset in range(width):
                values[start + offset] = 10
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            # A naive stride-25 view of the same record sees almost nothing.
            sparse_hits = sum(1 for value in values[::25] if value >= 8)
            self.assertLess(sparse_hits, 20)
            report = self._structure(root)
            complete = [pulse for pulse in report["pulses"]["items"] if pulse["status"] == "COMPLETE"]
            self.assertEqual(len(complete), 20)
            self.assertEqual(report["evidence"]["edge_count"], 40)
            self.assertEqual(
                [pulse["start_sample"] for pulse in complete],
                starts,
            )
            self.assertTrue(all(pulse["width_s"] == 2e-6 for pulse in complete))
            self.assertTrue(report["evidence"]["raw_scan"])
            self.assertEqual(report["evidence"]["stride_used"], 1)
            self.assertTrue(report["evidence"]["full_record_scanned"])

    def test_six_sample_narrow_pulse_is_found_while_stride_25_misses_it(self):
        values = [0] * 26 + [10] * 6 + [0] * 40
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            self.assertEqual(max(values[::25]), 0)
            report = self._structure(root)
            self.assertEqual(report["pulses"]["count"], 1)
            pulse = report["pulses"]["items"][0]
            self.assertEqual(pulse["status"], "COMPLETE")
            self.assertEqual(pulse["start_sample"], 26)
            self.assertEqual(pulse["end_sample"], 32)
            self.assertAlmostEqual(pulse["width_s"], 6e-6, places=15)
            self.assertEqual(report["classification"]["label"], "single_pulse")
            self.assertEqual(report["evidence"]["detection_resolution_s"], 1e-6)

    def test_continuous_carrier_and_short_burst_are_classified_differently(self):
        total = 1_000_000
        carrier = [0] * total
        for index in range(22):
            start = 1_000 + index * 45_400
            for offset in range(20_000):
                carrier[start + offset] = 10
        burst = [0] * total
        for index in range(6):
            start = 500_000 + index * 70
            for offset in range(20):
                burst[start + offset] = 10
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            carrier_root = root / "carrier"
            burst_root = root / "burst"
            carrier_root.mkdir()
            burst_root.mkdir()
            _write_capture(carrier_root, carrier)
            _write_capture(burst_root, burst)
            carrier_report = self._structure(carrier_root)
            burst_report = self._structure(burst_root)
            self.assertEqual(carrier_report["classification"]["label"], "continuous_carrier")
            self.assertEqual(burst_report["classification"]["label"], "short_burst")
            self.assertNotEqual(
                carrier_report["classification"]["label"], burst_report["classification"]["label"]
            )
            self.assertGreater(carrier_report["classification"]["metrics"]["duty_cycle"], 0.2)
            self.assertLess(burst_report["classification"]["metrics"]["presence_fraction"], 0.25)
            self.assertAlmostEqual(
                burst_report["pulse_clusters"]["items"][0]["duration_s"], 370e-6, places=12
            )
            self.assertEqual(carrier_report["pulse_clusters"]["count"], 1)
            self.assertEqual(burst_report["pulse_clusters"]["items"][0]["pulse_count"], 6)

    def test_low_duty_pulse_train_is_not_reported_as_no_signal(self):
        total = 900
        values = [0] * total
        for index in range(10):
            start = 10 + index * 80
            values[start] = 10
            values[start + 1] = 10
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            report = self._structure(root)
            self.assertEqual(report["classification"]["label"], "low_duty_pulse_train")
            self.assertEqual(report["classification"]["status"], "OBSERVED")
            self.assertEqual(report["evidence"]["observation_status"], "OBSERVED")
            self.assertNotEqual(report["classification"]["label"], "no_crossing_observed")
            self.assertNotIn(
                "absence_of_crossings_does_not_prove_absence_of_drive",
                report["evidence"]["limitations"],
            )
            self.assertLess(report["classification"]["metrics"]["duty_cycle"], 0.2)
            self.assertGreaterEqual(report["classification"]["metrics"]["coverage_fraction"], 0.5)

    def test_no_crossing_is_reported_with_detection_capability_not_as_no_drive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0] * 200)
            report = self._structure(root)
            self.assertEqual(report["classification"]["label"], "no_crossing_observed")
            self.assertEqual(
                report["evidence"]["observation_status"], "NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY"
            )
            self.assertIn(
                "absence_of_crossings_does_not_prove_absence_of_drive",
                report["evidence"]["limitations"],
            )
            self.assertEqual(report["pulses"]["count"], 0)

    def test_pulses_touching_record_edges_are_incomplete_and_never_padded(self):
        # high-low-high-low-high: the outer high intervals have no paired edge inside the record.
        values = [10] * 3 + [0] * 4 + [10] * 3 + [0] * 4 + [10] * 3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            report = self._structure(root)
            pulses = report["pulses"]["items"]
            self.assertEqual(len(pulses), 3)
            self.assertEqual(
                [pulse["status"] for pulse in pulses], ["INCOMPLETE", "COMPLETE", "INCOMPLETE"]
            )
            self.assertEqual(pulses[0]["start_sample"], 0)
            self.assertIn("starts_at_scan_window_start", pulses[0]["boundary_flags"])
            self.assertIsNone(pulses[0]["rising_edge_id"])
            self.assertIsNotNone(pulses[0]["falling_edge_id"])
            self.assertTrue(pulses[0]["width_is_lower_bound"])
            self.assertEqual(pulses[1]["start_sample"], 7)
            self.assertEqual(pulses[1]["end_sample"], 10)
            self.assertEqual(pulses[1]["width_s"], 3e-6)
            self.assertAlmostEqual(pulses[1]["interpolated_width_s"], 3e-6, places=15)
            self.assertFalse(pulses[1]["touches_capture_boundary"])
            self.assertEqual(pulses[2]["end_sample"], len(values) - 1)
            self.assertIn("ends_at_scan_window_end", pulses[2]["boundary_flags"])
            self.assertIsNone(pulses[2]["falling_edge_id"])
            self.assertTrue(pulses[2]["width_is_lower_bound"])
            self.assertEqual(report["pulses"]["incomplete_count"], 2)
            self.assertEqual(
                report["pulses"]["status"], "COMPLETE_WITH_INCOMPLETE_BOUNDARY_PULSES"
            )
            self.assertEqual(
                report["coverage"]["pulses_touching_capture_boundary"],
                [pulses[0]["pulse_id"], pulses[2]["pulse_id"]],
            )

    def test_edge_budget_overflow_is_unverified_lower_bound(self):
        values = [0, 10] * 100
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            report = self._structure(root, max_edges=10)
            self.assertEqual(report["evidence"]["observation_status"], "UNVERIFIED")
            self.assertEqual(report["classification"]["label"], "insufficient_evidence")
            self.assertEqual(report["classification"]["status"], "UNVERIFIED")
            self.assertTrue(report["edges"]["count_is_lower_bound"])
            self.assertTrue(report["edges"]["items_truncated"])
            self.assertFalse(report["edges"]["items_complete"])
            self.assertTrue(report["pulses"]["items_truncated"])
            self.assertFalse(report["pulses"]["items_complete"])
            self.assertTrue(report["pulse_clusters"]["items_truncated"])
            self.assertFalse(report["pulse_clusters"]["items_complete"])
            self.assertEqual(report["edges"]["lower_bound"], 11)
            self.assertEqual(report["edges"]["count"], 10)
            self.assertEqual(report["edges"]["returned"], 10)
            self.assertFalse(report["edges"]["items_complete"])
            self.assertFalse(report["evidence"]["full_record_scanned"])
            self.assertFalse(report["coverage"]["edge_scan_complete"])
            self.assertEqual(report["pulses"]["status"], "UNVERIFIED")
            self.assertEqual(report["pulse_clusters"]["status"], "UNVERIFIED")
            self.assertIn("edge_budget_exceeded_all_counts_are_lower_bounds", report["evidence"]["limitations"])
            # The same record scanned with a sufficient budget is complete, not a lower bound.
            complete = self._structure(root, max_edges=200)
            self.assertEqual(complete["edges"]["count"], 199)
            self.assertFalse(complete["edges"]["count_is_lower_bound"])
            self.assertIsNone(complete["edges"]["lower_bound"])
            self.assertTrue(complete["evidence"]["full_record_scanned"])

    def test_every_edge_and_pulse_traces_to_sample_and_time(self):
        values = [0] * 4 + [10] * 3 + [0] * 4 + [10] * 2 + [0] * 4
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            report = analyze_pulse_structure(capture, low=2, high=8)
            origin = capture["time_origin_s"]
            interval = capture["sample_interval_s"]
            edge_ids = {edge["event_id"] for edge in report["edges"]["items"]}
            for edge in report["edges"]["items"]:
                # Edge times are linear interpolations inside one sample interval.
                self.assertAlmostEqual(edge["time_s"], origin + edge["sample"] * interval, delta=interval)
                self.assertGreaterEqual(edge["time_s"], origin + (edge["sample"] - 1) * interval)
                self.assertLessEqual(edge["time_s"], origin + edge["sample"] * interval)
                self.assertEqual(edge["after_code"], values[edge["sample"]])
                self.assertEqual(edge["before_code"], values[edge["sample"] - 1])
                self.assertEqual(edge["time_uncertainty_s"], interval)
                self.assertEqual(edge["threshold_code"], 8 if edge["direction"] == "rising" else 2)
            rising = [edge for edge in report["edges"]["items"] if edge["direction"] == "rising"]
            self.assertIsNone(rising[0]["same_direction_interval_s"])
            self.assertAlmostEqual(rising[1]["same_direction_interval_s"], 7e-6, delta=2 * interval)
            for pulse in report["pulses"]["items"]:
                self.assertEqual(pulse["start_time_s"], origin + pulse["start_sample"] * interval)
                self.assertEqual(pulse["end_time_s"], origin + pulse["end_sample"] * interval)
                self.assertAlmostEqual(
                    pulse["width_s"], (pulse["end_sample"] - pulse["start_sample"]) * interval, places=15
                )
                self.assertEqual(pulse["start_code"], values[pulse["start_sample"]])
                self.assertEqual(pulse["end_code"], values[pulse["end_sample"]])
                if pulse["rising_edge_id"] is not None:
                    self.assertIn(pulse["rising_edge_id"], edge_ids)
                if pulse["falling_edge_id"] is not None:
                    self.assertIn(pulse["falling_edge_id"], edge_ids)
            self.assertEqual(report["classification"]["evidence"]["edge_ids"][0], report["edges"]["items"][0]["event_id"])
            self.assertEqual(report["classification"]["evidence"]["pulse_ids"][0], report["pulses"]["items"][0]["pulse_id"])

    def test_voltage_domain_thresholds_resolve_to_codes(self):
        values = [0] * 3 + [10] * 3 + [0] * 3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            self.assertEqual(capture["calibration"]["status"], "VALID")
            report = analyze_pulse_structure(capture, low=0.5, high=1.5, domain="voltage")
            thresholds = report["detector"]["thresholds"]
            self.assertEqual(thresholds["domain"], "voltage")
            self.assertAlmostEqual(thresholds["low_code"], 2.5, places=12)
            self.assertAlmostEqual(thresholds["high_code"], 7.5, places=12)
            self.assertEqual(report["pulses"]["count"], 1)
            pulse = report["pulses"]["items"][0]
            self.assertAlmostEqual(pulse["peak_v"], 2.0, places=12)
            self.assertAlmostEqual(pulse["min_v"], 0.0, places=12)
            self.assertAlmostEqual(report["edges"]["items"][0]["after_v"], 2.0, places=12)

    def test_time_limited_scan_reports_partial_coverage(self):
        values = [0] * 3 + [10] * 3 + [0] * 3 + [10] * 3 + [0] * 3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            capture = load_capture(root, "C1")
            origin = capture["time_origin_s"]
            report = analyze_pulse_structure(
                capture, low=2, high=8, start_time_s=origin + 3e-6, end_time_s=origin + 12e-6
            )
            self.assertEqual(report["coverage"]["scanned_start"], 3)
            self.assertEqual(report["coverage"]["scanned_end_exclusive"], 12)
            self.assertFalse(report["evidence"]["full_record_scanned"])
            self.assertIn("scan_limited_to_requested_sub_range", report["evidence"]["limitations"])
            self.assertEqual(report["pulses"]["count"], 2)

    def test_structure_json_bounding_flags_truncated_items(self):
        values = [0, 10] * 60
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, values)
            report = self._structure(root, max_edges=200)
            self.assertFalse(report["edges"]["items_truncated"])
            bounded = bound_json(report, 8 * 1024)
            encoded = json.dumps(bounded, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
            self.assertLessEqual(len(encoded), 8 * 1024)
            self.assertTrue(bounded["truncated"])
            self.assertTrue(bounded["edges"]["items_truncated"])
            self.assertFalse(bounded["edges"]["items_complete"])
            self.assertEqual(bounded["edges"]["count"], 119)
            self.assertLess(bounded["edges"]["returned"], bounded["edges"]["count"])
            self.assertEqual(bounded["edges"]["returned"], len(bounded["edges"]["items"]))

    def test_structure_rejects_invalid_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [0, 10, 0])
            capture = load_capture(root, "C1")
            with self.assertRaises(AnalysisError):
                analyze_pulse_structure(capture, low=8, high=2)
            with self.assertRaises(AnalysisError):
                analyze_pulse_structure(capture, low=2, high=8, cluster_gap_s=0.0)
            with self.assertRaises(AnalysisError):
                analyze_pulse_structure(capture, low=2, high=8, max_edges=0)
            with self.assertRaises(AnalysisError):
                analyze_pulse_structure(capture, low=2, high=8, start_time_s=0.0)


class RegimeAnalysisTests(unittest.TestCase):
    @staticmethod
    def _capture(root: Path, periods: list[int], widths: list[int] | None = None, *, levels: list[int] | None = None):
        widths = widths or [20] * len(periods)
        levels = levels or [10] * len(periods)
        values: list[int] = []
        for period, width, level in zip(periods, widths, levels):
            values.extend([level] * width)
            values.extend([0] * (period - width))
        _write_capture(root, values, sample_interval=1e-4)
        return load_capture(root, "C1")

    @staticmethod
    def _run(capture, **kwargs):
        kwargs.setdefault("low", 2)
        kwargs.setdefault("high", 8)
        return analyze_waveform_regimes(capture, **kwargs)

    def test_regimes_exposes_auto_measures_and_support_controls(self):
        # The CLI flags of the ``regimes`` subcommand are these keyword defaults;
        # the parser lives in analyze_waveform.py and forwards them unchanged.
        defaults = {
            name: parameter.default
            for name, parameter in inspect.signature(analyze_waveform_regimes).parameters.items()
        }
        self.assertEqual(defaults["measures"], "auto")
        self.assertEqual(defaults["min_cycles_per_side"], 5)
        self.assertEqual(defaults["transition_margin_cycles"], 1)
        self.assertEqual(defaults["domain"], "code")

    def test_frequency_step_produces_two_traceable_regimes(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 12 + [50] * 12)
            report = self._run(capture)
            self.assertEqual(report["data_integrity_status"], "COMPLETE")
            self.assertEqual(report["coverage"]["count_reconciliation"]["reconciles"], True)
            self.assertEqual(len(report["transitions"]["items"]), 1)
            summaries = [regime["summaries"]["period_s"]["median"] for regime in report["regimes"]["items"]]
            self.assertEqual(summaries, [0.01, 0.005])
            self.assertEqual([regime["status"] for regime in report["regimes"]["items"]], ["stable", "stable"])
            self.assertTrue(report["measures"]["selected"])
            self.assertTrue(report["cycles"]["items"][0]["source"]["rising_edge_id"])

    def test_isolated_period_outlier_is_one_anomaly_not_a_regime(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 20 + [200] + [100] * 20)
            report = self._run(capture)
            self.assertEqual(len(report["regimes"]["items"]), 1)
            self.assertEqual(report["transitions"]["count"], 0)
            self.assertEqual(len(report["anomalies"]["items"]), 1)
            self.assertEqual(report["anomalies"]["items"][0]["measure_count"], 3)

    def test_auto_selects_duty_change_when_period_is_stable(self):
        widths = [20] * 15 + [40] * 15
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 30, widths)
            report = self._run(capture)
            self.assertEqual(len(report["regimes"]["items"]), 2)
            selected = {item["feature"] for item in report["measures"]["selected"]}
            self.assertTrue({"duty_cycle", "high_width_s"} & selected)
            self.assertEqual(report["regimes"]["items"][0]["summaries"]["period_s"]["median"], 0.01)

    def test_explicit_measures_and_unknown_measure(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 12 + [50] * 12)
            report = self._run(capture, measures="duty_cycle")
            self.assertEqual([item["feature"] for item in report["measures"]["selected"]], ["duty_cycle"])
            with self.assertRaises(AnalysisError) as caught:
                self._run(capture, measures="not_a_measure")
            self.assertEqual(caught.exception.code, "MEASURE_UNSUPPORTED")

    def test_four_cycle_middle_phase_is_explicitly_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 10 + [50] * 4 + [100] * 10)
            report = self._run(capture)
            self.assertEqual(report["transitions"]["count"], 0)
            self.assertTrue(any(item["kind"] == "short_phase_insufficient_support" for item in report["unresolved"]["items"]))
            self.assertTrue(any(item["classification"] == "unresolved_phase" for item in report["cycles"]["items"]))
            self.assertEqual(report["coverage"]["count_reconciliation"]["reconciles"], True)

    def test_five_cycle_middle_phase_is_not_asserted_as_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 10 + [50] * 5 + [100] * 10)
            report = self._run(capture)
            self.assertTrue(any(item["kind"] == "contains_unresolved_phase" for item in report["unresolved"]["items"]))
            self.assertEqual(report["transitions"]["count"], 2)
            middle = [item for item in report["regimes"]["items"] if item["status"] == "contains_unresolved_phase"]
            self.assertEqual(len(middle), 1)
            self.assertLess(middle[0]["stable_cycle_count"], 5)

    def test_six_cycle_middle_phase_remains_explicitly_unresolved_after_boundary_margin(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 10 + [50] * 6 + [100] * 10)
            report = self._run(capture)
            self.assertEqual(report["transitions"]["count"], 2)
            middle = [item for item in report["regimes"]["items"] if item["status"] == "contains_unresolved_phase"]
            self.assertEqual(len(middle), 1)
            self.assertEqual(middle[0]["stable_cycle_count"], 3)
            self.assertTrue(any(item["kind"] == "contains_unresolved_phase" for item in report["unresolved"]["items"]))

    def test_smooth_ramp_preserves_data_integrity_and_reports_trend(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100 - 2 * index for index in range(24)])
            report = self._run(capture)
            self.assertEqual(report["data_integrity_status"], "COMPLETE")
            self.assertEqual(report["transitions"]["count"], 0)
            self.assertTrue(any(item["kind"] == "drift_trend" for item in report["unresolved"]["items"]))

    def test_edge_and_cycle_budgets_lower_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 40)
            edge_limited = self._run(capture, max_edges=10)
            self.assertEqual(edge_limited["overall_status"], "UNVERIFIED")
            self.assertEqual(edge_limited["coverage"]["segmentation_scope"], "prefix_only")
            cycle_limited = self._run(capture, max_cycles=10)
            self.assertEqual(cycle_limited["overall_status"], "UNVERIFIED")
            self.assertTrue(cycle_limited["coverage"]["count_reconciliation"]["reconciles"])

    def test_uncalibrated_voltage_measure_is_unavailable_but_code_measure_works(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_capture(root, [10, 0] * 100, width=2)
            capture = load_capture(root, "C1")
            report = self._run(capture, measures="peak_v,period_s")
            self.assertIn("peak_v", {item["feature"] for item in report["measures"]["unavailable"]})
            self.assertIn("period_s", {item["feature"] for item in report["measures"]["evaluated"]})

    def test_regime_json_budget_never_returns_an_unflagged_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(Path(directory), [100] * 12 + [50] * 12)
            report = self._run(capture)
            bounded = bound_json(report, 8192)
            encoded = json.dumps(bounded, separators=(",", ":"), allow_nan=False).encode()
            self.assertLessEqual(len(encoded), 8192)
            self.assertTrue(bounded["truncated"])
            if bounded.get("summary_compacted") or (
                bounded.get("truncated") and bounded.get("regimes", {}).get("items")
            ):
                self.assertTrue(bounded["regimes"]["items"])
            else:
                self.assertTrue(bounded["required_summary_omitted"])
                self.assertEqual(bounded["overall_status"], "UNVERIFIED")


class ThreeWayStatusTests(unittest.TestCase):
    """A structural status must never stand in for a confirmed physical level."""

    def _calibration(self, **overrides):
        base = {
            "status": "VALID",
            "units": "V",
            "code_scale_v": 0.1,
            "effective_vdiv_v_per_div": 1.0,
            "effective_offset_v": 0.0,
            "verification_failures": [],
        }
        base.update(overrides)
        return base

    def _manifest(self, value=3.0, unit="V"):
        return {"instrument_measurements": {"C1": {"pkpk": {"value": value, "unit": unit, "raw": str(value)}}}}

    def test_agreement_inside_tolerance_confirms_the_level(self):
        result = attach_three_way_status(
            self._calibration(), manifest=self._manifest(3.0), channel="C1",
            reconstruction={"amplitude_v": 2.95},
        )
        self.assertEqual(result["bytes_complete"], "COMPLETE")
        self.assertEqual(result["scale_usable"], "VALID")
        self.assertEqual(result["level_confirmed"], "PASS")
        self.assertAlmostEqual(result["tolerance"], 2 * 0.1 + 0.02 * 3.0)

    def test_a_five_volt_reconstruction_for_a_three_volt_signal_fails(self):
        result = attach_three_way_status(
            self._calibration(), manifest=self._manifest(3.0), channel="C1",
            reconstruction={"amplitude_v": 5.0},
        )
        # The structural status is still VALID: that is exactly the defect.
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["level_confirmed"], "FAIL")
        self.assertEqual(result["level_reason"], "reconstructed_outside_tolerance")
        self.assertEqual(result["instrument_value"], 3.0)
        self.assertEqual(result["reconstructed_value"], 5.0)

    def test_missing_instrument_measurement_is_unknown_not_pass(self):
        result = attach_three_way_status(
            self._calibration(), manifest={}, channel="C1",
            reconstruction={"amplitude_v": 3.0},
        )
        self.assertEqual(result["level_confirmed"], "UNKNOWN")
        self.assertEqual(result["level_reason"], "instrument_measurement_absent")

    def test_ampere_scale_is_not_a_voltage_scale(self):
        result = attach_three_way_status(
            self._calibration(units="A"), manifest=self._manifest(), channel="C1",
            reconstruction={"amplitude_v": 3.0},
        )
        self.assertEqual(result["scale_usable"], "UNKNOWN")
        self.assertIn("units_a_not_volts", result["scale_reasons"])

    def test_unknown_offset_makes_the_scale_unusable(self):
        result = attach_three_way_status(
            self._calibration(effective_offset_v=None), manifest=self._manifest(), channel="C1",
            reconstruction={"amplitude_v": 3.0},
        )
        self.assertEqual(result["scale_usable"], "UNKNOWN")
        self.assertIn("offset_unknown", result["scale_reasons"])

    def test_measurement_in_other_units_fails_instead_of_converting(self):
        result = attach_three_way_status(
            self._calibration(), manifest=self._manifest(3.0, unit="A"), channel="C1",
            reconstruction={"amplitude_v": 3.0},
        )
        self.assertEqual(result["level_confirmed"], "FAIL")


class RigolUnsignedBundleTests(unittest.TestCase):
    """A Rigol ``u1`` bundle: zero_code 127, 0.02 V/code, no additive offset."""

    @staticmethod
    def _volts(code: float) -> float:
        # The documented formula, not an implementation call: (sample - zero_code)
        # * code_scale_v + offset_v with zero_code 127.0 and offset 0.0.
        return (code - 127.0) * 0.02 + 0.0

    def test_summary_converts_unsigned_codes_without_wrapping_at_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _write_bundle(
                root, [0, 127, 255],
                instrument_measurements={
                    "metric": "PKPK", "value": "5.10E+00V", "unit": "V",
                    "source_query": "WAV:MEAS:PKPK?",
                },
            )
            capture = load_capture(path)
            self.assertEqual(capture["calibration"]["zero_code"], 127.0)
            result = summarize_capture(capture, preview_buckets=2)
            summary = result["summary"]
            # The absolute levels carry zero_code; a conversion that assumed the
            # legacy signed [-128, 127] code range would also overflow the
            # histogram on the 255 here.
            self.assertEqual(summary["min_v"], self._volts(0))
            self.assertEqual(summary["max_v"], self._volts(255))
            self.assertEqual(summary["min_v"], -2.54)
            self.assertAlmostEqual(summary["mean_v"], (self._volts(0) + self._volts(127) + self._volts(255)) / 3, places=12)
            self.assertAlmostEqual(summary["rms_v"], float(np.sqrt(np.mean(np.square([self._volts(0), self._volts(127), self._volts(255)])))), places=15)
            self.assertEqual(summary["percentiles_v"]["p50"], self._volts(127))
            self.assertEqual(summary["underlying_code_statistics"], {"min": 0, "max": 255, "mean": 127.33333333333333, "rms": float(np.sqrt((0 + 127**2 + 255**2) / 3))})
            # Peak-to-peak is a difference: 255 codes * 0.02 V/code, and the flat
            # bundle measurement of the same amplitude confirms the level.
            self.assertEqual(result["calibration"]["level_confirmed"], "PASS")
            self.assertAlmostEqual(result["calibration"]["reconstructed_value"], 255 * 0.02, places=12)
            self.assertEqual(result["calibration"]["instrument_value"], 5.1)
            self.assertEqual(result["capture"]["id"], "TEST,TEST-SCOPE,0,1.0")

    def test_events_and_window_use_the_unsigned_offset_for_voltage_thresholds(self):
        codes = [27] * 5 + [227] * 4 + [27] * 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(_write_bundle(root, codes))
            window = get_window(capture, 5, 4)
            self.assertEqual(window["window"]["codes"], [227] * 4)
            self.assertEqual(window["window"]["volts"], [self._volts(227)] * 4)
            self.assertAlmostEqual(self._volts(227), 2.0, places=12)
            report = find_events(capture, low=-1.0, high=1.0, domain="voltage")
            rising = [item for item in report["events"]["items"] if item["type"] == "rising"]
            falling = [item for item in report["events"]["items"] if item["type"] == "falling"]
            self.assertEqual(len(rising), 1)
            self.assertEqual(len(falling), 1)
            self.assertEqual(rising[0]["start_sample"], 5)
            self.assertEqual(rising[0]["threshold"], {"low_v": -1.0, "high_v": 1.0})
            self.assertAlmostEqual(rising[0]["value"], 2.0, places=12)
            self.assertAlmostEqual(falling[0]["value"], -2.0, places=12)
            self.assertEqual(report["detector"]["parameters"]["low"], -1.0)
            self.assertEqual(report["detector"]["parameters"]["high"], 1.0)
            # -1.0 V and +1.0 V are code 77 and code 177 in this capture, so both
            # domains must return exactly the same edges.
            code_domain = find_events(capture, low=77, high=177)
            self.assertEqual(
                [item["start_sample"] for item in code_domain["events"]["items"]],
                [item["start_sample"] for item in report["events"]["items"]],
            )

    def test_pulse_structure_and_regimes_read_unsigned_codes_once(self):
        high, low_code = 227, 27
        wide = ([high] * 20 + [low_code] * 80) * 12
        narrow = ([high] * 20 + [low_code] * 30) * 12
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(_write_bundle(root, wide + narrow))
            structure = analyze_pulse_structure(capture, low=-1.0, high=1.0, domain="voltage")
            # The record opens on a high interval, so that first pulse has no
            # observed rising edge and stays INCOMPLETE; the other 23 pair up.
            self.assertEqual(structure["pulses"]["complete_count"], 23)
            self.assertEqual(structure["pulses"]["incomplete_count"], 1)
            first = structure["pulses"]["items"][0]
            self.assertEqual((first["start_code"], first["end_code"]), (high, low_code))
            self.assertAlmostEqual(first["peak_v"], 2.0, places=12)
            self.assertEqual(structure["detector"]["thresholds"]["low_code"], 77.0)
            self.assertEqual(structure["detector"]["thresholds"]["high_code"], 177.0)
            report = analyze_waveform_regimes(capture, low=77, high=177)
            self.assertEqual(len(report["regimes"]["items"]), 2)
            self.assertEqual(report["transitions"]["count"], 1)
            medians = [regime["summaries"]["period_s"]["median"] for regime in report["regimes"]["items"]]
            self.assertAlmostEqual(medians[0], 100 * 2e-7, places=12)
            self.assertAlmostEqual(medians[1], 50 * 2e-7, places=12)
            # Codes stay codes in the regime feature table, and the voltage form
            # of the same peak is the offset conversion of that code.
            self.assertEqual(report["cycles"]["items"][0]["features"]["peak_code"], float(high))
            self.assertEqual(report["cycles"]["items"][0]["features"]["min_code"], float(low_code))
            self.assertEqual(report["cycles"]["items"][0]["features"]["peak_to_peak_code"], float(high - low_code))
            volts = analyze_waveform_regimes(capture, low=77, high=177, measures="peak_v,period_s")
            self.assertIn("peak_v", {item["feature"] for item in volts["measures"]["evaluated"]})
            self.assertAlmostEqual(volts["regimes"]["items"][0]["summaries"]["peak_v"]["median"], 2.0, places=12)

    def test_ringing_baseline_is_the_converted_level_not_the_raw_code(self):
        codes = [127] * 8 + [137, 157, 129, 151, 131, 147, 133, 143, 137, 137, 137, 137]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(_write_bundle(root, codes))
            report = analyze_ringing(capture, start=0, count=len(codes))
            self.assertEqual(report["value_domain"], "voltage")
            self.assertEqual(report["unit"], "V")
            # Baseline code 127 and final code 137 become 0.0 V and 0.2 V; the raw
            # codes would read 127 and 137 in a code-domain report.
            self.assertEqual(report["edge"]["baseline"], 0.0)
            self.assertAlmostEqual(report["edge"]["final_level"], 0.2, places=12)
            self.assertAlmostEqual(report["edge"]["step_amplitude"], 0.2, places=12)
            self.assertGreater(report["ringing"]["positive_overshoot"], 0.3)
            self.assertIsNotNone(report["ringing"]["frequency_hz"])


class GdsWordBundleTests(unittest.TestCase):
    """A GDS-1000B style ``>i2`` bundle: zero_code 0, vdiv / 25 V per code."""

    def test_summary_and_window_use_the_word_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _write_bundle(
                root, [-100, 0, 100], dtype=">i2", zero_code=0.0, code_scale_v=1.0 / 25.0,
                vdiv=1.0, adc=(-32768, 32767),
            )
            capture = load_capture(path)
            self.assertEqual(capture["samples"].dtype.str, ">i2")
            summary = summarize_capture(capture, preview_buckets=1)["summary"]
            self.assertAlmostEqual(summary["min_v"], -4.0, places=12)
            self.assertAlmostEqual(summary["max_v"], 4.0, places=12)
            self.assertAlmostEqual(summary["mean_v"], 0.0, places=12)
            self.assertAlmostEqual(summary["rms_v"], float(np.sqrt(32.0 / 3.0)), places=12)
            self.assertEqual(summary["underlying_code_statistics"]["max"], 100)
            window = get_window(capture, 0, 3)
            self.assertEqual(window["window"]["codes"], [-100, 0, 100])
            np.testing.assert_allclose(window["window"]["volts"], [-4.0, 0.0, 4.0])

    def test_events_and_structure_resolve_voltage_thresholds_to_word_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codes = [-100] * 3 + [100] * 4 + [-100] * 3
            capture = load_capture(
                _write_bundle(
                    root, codes, dtype=">i2", zero_code=0.0, code_scale_v=1.0 / 25.0,
                    vdiv=1.0, adc=(-32768, 32767),
                )
            )
            report = find_events(capture, low=-2.0, high=2.0, domain="voltage")
            self.assertEqual([item["type"] for item in report["events"]["items"]], ["rising", "falling"])
            self.assertEqual(report["events"]["items"][0]["start_sample"], 3)
            self.assertAlmostEqual(report["events"]["items"][0]["value"], 4.0, places=12)
            self.assertAlmostEqual(report["events"]["items"][1]["value"], -4.0, places=12)
            structure = analyze_pulse_structure(capture, low=-2.0, high=2.0, domain="voltage")
            self.assertEqual(structure["pulses"]["complete_count"], 1)
            pulse = structure["pulses"]["items"][0]
            # A complete pulse spans rising sample to first sample back at the low
            # level, so its end code is the low code, not another high one.
            self.assertEqual((pulse["start_sample"], pulse["end_sample"]), (3, 7))
            self.assertAlmostEqual(pulse["peak_v"], 4.0, places=12)
            self.assertAlmostEqual(pulse["min_v"], -4.0, places=12)
            self.assertEqual((pulse["start_code"], pulse["end_code"]), (100, -100))
            # -2 V and +2 V are code -50 and code 50 at 1/25 V per code.
            self.assertEqual(structure["detector"]["thresholds"]["low_code"], -50.0)
            self.assertEqual(structure["detector"]["thresholds"]["high_code"], 50.0)
            self.assertEqual(
                report["detector"]["parameters"]["low"],
                structure["detector"]["thresholds"]["requested_low"],
            )

    def test_regimes_of_a_word_capture_measure_period_and_peak_volts(self):
        wide = ([100] * 20 + [-100] * 80) * 12
        narrow = ([100] * 20 + [-100] * 30) * 12
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(
                _write_bundle(
                    root, wide + narrow, dtype=">i2", zero_code=0.0, code_scale_v=1.0 / 25.0,
                    vdiv=1.0, adc=(-32768, 32767),
                )
            )
            report = analyze_waveform_regimes(capture, low=-2.0, high=2.0, domain="voltage", measures="period_s,peak_v")
            self.assertEqual(len(report["regimes"]["items"]), 2)
            medians = [regime["summaries"]["period_s"]["median"] for regime in report["regimes"]["items"]]
            self.assertAlmostEqual(medians[0], 100 * 2e-7, places=12)
            self.assertAlmostEqual(medians[1], 50 * 2e-7, places=12)
            self.assertAlmostEqual(report["regimes"]["items"][0]["summaries"]["peak_v"]["median"], 4.0, places=12)


class FloatCaptureTests(unittest.TestCase):
    """Float captures are already in volts and must never be truncated to int."""

    def test_csv_values_are_already_volts_in_summary_window_and_events(self):
        values = [0.0] * 5 + [2.0] * 4 + [0.0] * 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(_write_csv(root / "capture.csv", 1e-6, values))
            summary = summarize_capture(capture, preview_buckets=1)
            self.assertAlmostEqual(summary["summary"]["min_v"], 0.0, places=15)
            self.assertAlmostEqual(summary["summary"]["max_v"], 2.0, places=15)
            self.assertAlmostEqual(summary["summary"]["mean_v"], float(np.mean(values)), places=15)
            self.assertAlmostEqual(summary["summary"]["percentiles_v"]["p50"], 0.0, places=15)
            self.assertIsInstance(summary["preview"]["points"][0]["code"], float)
            window = get_window(capture, 6, 2)
            self.assertEqual(window["window"]["codes"], [2.0, 2.0])
            self.assertEqual(window["window"]["volts"], [2.0, 2.0])
            report = find_events(capture, low=0.5, high=1.5, domain="voltage")
            self.assertEqual([item["type"] for item in report["events"]["items"]], ["rising", "falling"])
            self.assertEqual(report["events"]["items"][0]["value"], 2.0)

    def test_float_csv_ringing_and_structure_report_volts(self):
        values = [0.0] * 8 + [1.0, 2.4, 0.4, 1.9, 0.7, 1.5, 0.9, 1.2, 1.0, 1.0, 1.0, 1.0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = load_capture(_write_csv(root / "ring.csv", 1e-6, values))
            ringing = analyze_ringing(capture, start=0, count=len(values))
            self.assertEqual(ringing["unit"], "V")
            self.assertEqual(ringing["ringing"]["status"], "evidence_found")
            self.assertGreater(ringing["ringing"]["positive_overshoot"], 1.0)
            self.assertGreater(ringing["ringing"]["positive_overshoot"], 0.0)
            structure = analyze_pulse_structure(capture, low=0.25, high=0.75, domain="voltage")
            self.assertEqual(structure["detector"]["thresholds"]["low_code"], 0.25)
            self.assertEqual(structure["pulses"]["items"][0]["start_code"], 1.0)

    def test_float_bundle_events_window_and_regimes_keep_float_samples(self):
        wide = ([1.0] * 20 + [-1.0] * 80) * 12
        narrow = ([1.0] * 20 + [-1.0] * 30) * 12
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _write_bundle(
                root, wide + narrow, dtype="<f8", zero_code=None, code_scale_v=None,
                offset_v=None, vdiv=None, adc=None, sample_interval_s=1e-6,
            )
            capture = load_capture(path)
            self.assertEqual(capture["dtype"], "float64")
            window = get_window(capture, 0, 2)
            self.assertEqual(window["window"]["codes"], [1.0, 1.0])
            self.assertEqual(window["window"]["volts"], [1.0, 1.0])
            report = find_events(capture, low=-0.5, high=0.5, domain="voltage", limit=4)
            rising = next(item for item in report["events"]["items"] if item["type"] == "rising")
            self.assertEqual(rising["value"], 1.0)
            self.assertEqual(rising["threshold"], {"low_v": -0.5, "high_v": 0.5})
            regimes = analyze_waveform_regimes(capture, low=0, high=0.5)
            self.assertEqual(len(regimes["regimes"]["items"]), 2)
            self.assertAlmostEqual(regimes["regimes"]["items"][0]["summaries"]["period_s"]["median"], 100 * 1e-6, places=12)
            self.assertAlmostEqual(regimes["regimes"]["items"][1]["summaries"]["period_s"]["median"], 50 * 1e-6, places=12)


class CodeDomainBundleTests(unittest.TestCase):
    def test_unusable_scale_keeps_analysis_in_codes(self):
        codes = [27] * 3 + [227] * 3 + [27] * 3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _write_bundle(
                root, codes, units="code", scale_usable=False, calibration_status="CODE_ONLY",
                code_scale_v=None, zero_code=None, offset_v=None, vdiv=None,
            )
            capture = load_capture(path)
            summary = summarize_capture(capture, preview_buckets=1)["summary"]
            self.assertEqual(summary["min_code"], 27)
            self.assertEqual(summary["max_code"], 227)
            self.assertNotIn("min_v", summary)
            self.assertNotIn("volts", get_window(capture, 0, 2)["window"])
            self.assertEqual(find_events(capture, low=77, high=177)["events"]["total"], 2)
            with self.assertRaises(AnalysisError) as caught:
                find_events(capture, low=-1.0, high=1.0, domain="voltage")
            self.assertEqual(caught.exception.code, "CALIBRATION_INCONSISTENT")


class ModuleBoundaryTests(unittest.TestCase):
    """The engine imports no device Skill and re-exports one loader surface."""

    def test_module_carries_no_device_skill_dependency(self):
        source = Path(waveform_analysis.__file__).read_text(encoding="utf-8")
        for forbidden in ("import scope_protocol", "from scope_protocol", "capture_scope", "ds1000z", "gds1000b"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("scope_protocol", sys.modules)

    def test_loader_symbols_are_the_waveform_bundle_objects(self):
        # Callers that imported the loader from the device Skill's analysis module
        # must keep the identical object, not a copy that can drift.
        for name in (
            "SCREEN_RANGE_REVALIDATION_NOTE",
            "AnalysisError",
            "attach_three_way_status",
            "calibration_source",
            "load_capture",
            "parse_scpi_number",
            "samples_to_volts",
            "validate_frame",
            "volts_to_codes",
            "_extract_channel_result",
            "_finite_number",
            "_int_field",
            "_level_cross_check",
            "_load_calibration",
            "_require_numpy",
            "_resolve_capture_path",
        ):
            self.assertIs(getattr(waveform_analysis, name), getattr(waveform_bundle, name), name)


if __name__ == "__main__":
    unittest.main()
