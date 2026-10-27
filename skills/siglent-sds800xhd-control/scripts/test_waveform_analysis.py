#!/usr/bin/env python3
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from waveform_analysis import (
    AnalysisError,
    analyze_ringing,
    bound_json,
    find_events,
    get_window,
    load_capture,
    m4_preview,
    summarize_capture,
)


def _write_capture(root: Path, values, *, width: int = 1, stored_root: Path | None = None, snapshot_vdiv: float | None = None) -> Path:
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
        "sample_interval": 1e-6,
        "horizontal_offset": 0.0,
        "timebase_s": 1.0,
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
    manifest = {
        "idn": "synthetic,SDS824X HD,test,1",
        "capture_configuration": {"channels": {channel: {"vdiv": str(snapshot_vdiv), "offset": "0"}}},
        "results": [result],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root / "manifest.json"


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


if __name__ == "__main__":
    unittest.main()
