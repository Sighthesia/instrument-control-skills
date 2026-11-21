#!/usr/bin/env python3
"""Offline tests for waveform_bundle: bundle-v1, CSV/NPZ and legacy manifests."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

import waveform_bundle
from waveform_bundle import (
    BUNDLE_SCHEMA,
    SCREEN_RANGE_REVALIDATION_NOTE,
    AnalysisError,
    attach_three_way_status,
    load_capture,
    parse_scpi_number,
    samples_to_volts,
    validate_frame,
    volts_to_codes,
)


def _bundle(
    root: Path,
    samples,
    *,
    dtype: str = "u1",
    bundle_name: str = "bundle.json",
    payload_name: str = "waveform.bin",
    channel: str = "CH1",
    zero_code=127.0,
    code_scale_v=0.02,
    offset_v=0.0,
    vdiv=0.5,
    units: str = "V",
    scale_usable: bool = True,
    calibration_status: str = "VERIFIED",
    adc=(0, 255),
    full_scale_code=None,
    sample_interval_s=2e-7,
    time_origin_s=0.0,
    timebase_s=1e-4,
    horizontal_offset_s=0.0,
    reference: str = "descriptor",
    integrity_status: str = "COMPLETE",
    instrument_measurements=None,
    provenance=None,
    payload: bytes = None,
    byte_offset: int = 0,
    schema: str = BUNDLE_SCHEMA,
    drop_section: str = None,
    data_overrides: dict = None,
    vertical_overrides: dict = None,
    time_overrides: dict = None,
) -> Path:
    """Write one waveform-bundle/v1 document plus its payload file."""

    body = payload if payload is not None else np.asarray(samples, dtype=np.dtype(dtype)).tobytes()
    # A leading gap and trailing junk prove the slice — not the file — is what
    # data.sha256 addresses.
    (root / payload_name).write_bytes(bytes(byte_offset) + body + b"\x7f" * 3)
    data = {
        "file": payload_name,
        "sha256": hashlib.sha256(body).hexdigest(),
        "file_sha256": hashlib.sha256((root / payload_name).read_bytes()).hexdigest(),
        "dtype": dtype,
        "points": len(samples),
        "byte_offset": byte_offset,
        "byte_length": len(body),
        "width_bytes": np.dtype(dtype).itemsize,
    }
    if data_overrides:
        data.update(data_overrides)
    vertical = {
        "units": units,
        "scale_usable": scale_usable,
        "zero_code": zero_code,
        "code_scale_v": code_scale_v,
        "offset_v": offset_v,
        "vdiv_v_per_div": vdiv,
        "adc_min_code": adc[0] if adc else None,
        "adc_max_code": adc[1] if adc else None,
        "full_scale_code": full_scale_code,
        "calibration_status": calibration_status,
        "calibration_source": "test_adapter",
        "scale_reasons": [],
    }
    if vertical_overrides:
        vertical.update(vertical_overrides)
    time_axis = {
        "sample_interval_s": sample_interval_s,
        "time_origin_s": time_origin_s,
        "timebase_s": timebase_s,
        "horizontal_offset_s": horizontal_offset_s,
        "reference": reference,
        "origin_formula": "time_origin_s + sample_index * sample_interval_s",
    }
    if time_overrides:
        time_axis.update(time_overrides)
    bundle = {
        "schema": schema,
        "source": {
            "vendor": "test",
            "model": "TEST-SCOPE",
            "idn": "TEST,TEST-SCOPE,0,1.0",
            "channel": channel,
            "captured_at": "2026-11-21T00:00:00Z",
        },
        "data": data,
        "time_axis": time_axis,
        "vertical": vertical,
        "integrity": {
            "status": integrity_status,
            "bytes_complete": True,
            "checks": ["payload framing"],
            "status_meaning": "payload framing/count integrity only",
        },
        "provenance": {
            "raw_file": "waveform-norm-ch1.raw",
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "new_transition_proven": None,
            "screen_range": None,
            "screenshot": None,
        }
        if provenance is None
        else provenance,
        "instrument_measurements": instrument_measurements,
    }
    if drop_section:
        bundle.pop(drop_section)
    path = root / bundle_name
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def _write_legacy_capture(
    root: Path,
    values,
    *,
    width: int = 1,
    snapshot_vdiv: float = None,
    sample_interval: float = 1e-6,
    preamble_start: int = 0,
    vdiv: float = None,
    offset: float = 0.0,
    codes_per_div: float = 10.0,
) -> Path:
    """Write a legacy Siglent manifest with the same shape capture_scope emits."""

    channel = "C1"
    channel_dir = root / channel
    channel_dir.mkdir(parents=True)
    if width == 1:
        body = bytes((int(value) % 256 for value in values))
        comm_type = 0
        nominal_bits = 8
    else:
        body = b"".join(int(value).to_bytes(2, "little", signed=True) for value in values)
        comm_type = 1
        nominal_bits = 16
    waveform = channel_dir / "waveform.bin"
    waveform.write_bytes(body)
    segment = channel_dir / "segment-000000.bin"
    segment.write_bytes(body)
    points = len(values)
    channel_vdiv = vdiv if vdiv is not None else (2.0 if width == 1 else 1.0)
    preamble = {
        "description": "WAVEDESC",
        "comm_type": comm_type,
        "comm_order": 0,
        "byte_order": "LSB",
        "data_width_bytes": width,
        "nominal_bits": nominal_bits,
        "sparsing_factor": 1,
        "wave_array_count": points,
        "wave_array_1_bytes": len(body),
        "sample_interval": sample_interval,
        "horizontal_offset": 0.0,
        "timebase_s": 1.0,
        "start": preamble_start,
        "vdiv": channel_vdiv,
        "probe": 1.0,
        "offset": offset,
        "code_per_div": codes_per_div,
    }
    result = {
        "channel": channel,
        "frame_report": {"status": "COMPLETE"},
        "segment_report": {"status": "COMPLETE", "downloaded_points": points, "downloaded_payload_bytes": len(body)},
        "merged_waveform": str(root / channel / "waveform.bin"),
        "merged_waveform_bytes": len(body),
        "merged_waveform_sha256": hashlib.sha256(body).hexdigest(),
        "preamble": preamble,
        "segments": [
            {
                "requested_start": 0,
                "requested_points": points,
                "actual_payload_bytes": len(body),
                "payload": str(root / channel / "segment-000000.bin"),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ],
    }
    # Real manifests store the decorated firmware reply, not a bare float.
    snapshot_vdiv = snapshot_vdiv if snapshot_vdiv is not None else channel_vdiv
    manifest = {
        "idn": "synthetic,SDS824X HD,test,1",
        "capture_configuration": {
            "channels": {channel: {"vdiv": f"{channel}:VDIV {snapshot_vdiv:.2E}V", "offset": f"C1:OFST {offset:.2E}V"}}
        },
        "results": [result],
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_modern_capture(
    root: Path,
    values,
    *,
    scope_points: int,
    scope_duration_s: float,
    sample_interval: float = 1e-6,
    frame_status: str = "COMPLETE",
    reasons=(),
) -> Path:
    """Modern configured_capture manifest whose frame report predates screen semantics."""

    manifest_path = _write_legacy_capture(root, values, sample_interval=sample_interval)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mode"] = "configured_capture"
    result = manifest["results"][0]
    result["mode"] = "configured_capture"
    preamble = result["preamble"]
    points = preamble["wave_array_count"]
    payload_bytes = points * preamble["data_width_bytes"]
    result["frame_report"] = {
        "status": frame_status,
        "reasons": list(reasons),
        "scope_record": {"points": scope_points, "duration_s": scope_duration_s},
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


class BundleHappyPathTests(unittest.TestCase):
    def test_rigol_style_unsigned_byte_bundle_loads_volts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [0, 127, 255], dtype="u1", zero_code=127.0, code_scale_v=0.02, adc=(0, 255))
            capture = load_capture(path)
            self.assertEqual(capture["source_format"], BUNDLE_SCHEMA)
            self.assertEqual(capture["channel"], "CH1")
            self.assertEqual(capture["points"], 3)
            self.assertEqual(capture["width"], 1)
            self.assertEqual(capture["dtype"], "uint8")
            calibration = capture["calibration"]
            self.assertEqual(calibration["status"], "VALID")
            self.assertEqual(calibration["units"], "V")
            self.assertEqual(calibration["zero_code"], 127.0)
            self.assertAlmostEqual(calibration["code_scale_v"], 0.02)
            self.assertEqual(calibration["effective_offset_v"], 0.0)
            self.assertEqual(calibration["adc_min_code"], 0)
            self.assertEqual(calibration["adc_max_code"], 255)
            self.assertEqual(calibration["scale_usable"], "VALID")
            self.assertEqual(calibration["bytes_complete"], "COMPLETE")
            volts = samples_to_volts(capture["samples"], calibration)
            np.testing.assert_allclose(volts, [-2.54, 0.0, 2.56])

    def test_gds_style_big_endian_word_bundle_loads_volts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vdiv = 1.0
            path = _bundle(
                root, [-100, 0, 100], dtype=">i2", zero_code=0.0,
                code_scale_v=vdiv / 25.0, vdiv=vdiv, adc=(-32768, 32767),
            )
            capture = load_capture(path)
            self.assertEqual(capture["samples"].dtype.str, ">i2")
            self.assertEqual(capture["width"], 2)
            # Byte order is real: the stored payload is big-endian.
            self.assertEqual((root / "waveform.bin").read_bytes()[:2], (-100).to_bytes(2, "big", signed=True))
            self.assertEqual(list(capture["samples"]), [-100, 0, 100])
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], capture["calibration"]), [-4.0, 0.0, 4.0]
            )

    def test_siglent_style_little_endian_word_and_byte_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            word = load_capture(
                _bundle(root, [-300, 0, 300], dtype="<i2", zero_code=0.0, code_scale_v=2.0 / 30.0,
                        vdiv=2.0, adc=(-32768, 32767), bundle_name="word.json", payload_name="word.bin")
            )
            self.assertEqual(word["dtype"], "int16")
            self.assertEqual(word["samples"].dtype.str, "<i2")
            np.testing.assert_allclose(samples_to_volts(word["samples"], word["calibration"]), [-20.0, 0.0, 20.0])
            byte = load_capture(
                _bundle(root, [-30, 0, 30], dtype="i1", zero_code=0.0, code_scale_v=2.0 / 30.0,
                        vdiv=2.0, adc=(-128, 127), full_scale_code=150.0,
                        bundle_name="byte.json", payload_name="byte.bin")
            )
            self.assertEqual(byte["dtype"], "int8")
            self.assertEqual(byte["calibration"]["adc_min_code"], -128)
            self.assertEqual(byte["calibration"]["full_scale_code"], 150.0)
            np.testing.assert_allclose(samples_to_volts(byte["samples"], byte["calibration"]), [-2.0, 0.0, 2.0])

    def test_float_bundle_is_already_volts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [0.0, 1.5, -2.25], dtype="<f8", zero_code=None, code_scale_v=None,
                           offset_v=None, vdiv=None, adc=None)
            capture = load_capture(path)
            self.assertEqual(capture["width"], 8)
            self.assertEqual(capture["calibration"]["status"], "VALID")
            self.assertAlmostEqual(capture["calibration"]["code_scale_v"], 1.0)
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], capture["calibration"]), [0.0, 1.5, -2.25]
            )
            # A generic float capture records no V/div, so the three-way scale
            # claim stays UNKNOWN even though the identity scale is complete.
            self.assertEqual(capture["calibration"]["scale_usable"], "UNKNOWN")
            self.assertIn("vdiv_unknown", capture["calibration"]["scale_reasons"])

    def test_bundle_byte_offset_reads_only_the_declared_slice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3, 4], dtype="u1", byte_offset=8, zero_code=0.0,
                           code_scale_v=0.5, adc=(0, 255))
            capture = load_capture(path)
            self.assertEqual(list(capture["samples"]), [1, 2, 3, 4])
            np.testing.assert_allclose(samples_to_volts(capture["samples"], capture["calibration"]), [0.5, 1.0, 1.5, 2.0])

    def test_bundle_populates_the_canonical_capture_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provenance = {
                "raw_file": "waveform.raw",
                "raw_sha256": "ab" * 32,
                "new_transition_proven": False,
                "screen_range": {"status": "UNVERIFIED", "screen_points": 4, "wavedesc_points": 4},
                "screenshot": {"present": False},
            }
            path = _bundle(root, [1, 2, 3, 4], dtype="u1", zero_code=0.0, code_scale_v=0.5,
                           time_origin_s=-1e-6, timebase_s=2e-4, horizontal_offset_s=3e-6,
                           provenance=provenance)
            capture = load_capture(path)
            for key in (
                "manifest_path", "manifest_dir", "manifest", "manifest_sha256", "source_format",
                "channel", "path", "samples", "points", "bytes", "width", "dtype", "raw_sha256",
                "sample_interval_s", "sample_rate_hz", "time_origin_s", "preamble", "calibration",
                "integrity", "screen_range", "time_correspondence", "screen_range_revalidation",
                "provenance",
            ):
                self.assertIn(key, capture)
            self.assertEqual(capture["manifest"], json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(capture["manifest_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(capture["raw_sha256"], capture["manifest"]["data"]["sha256"])
            self.assertEqual(capture["preamble"]["horizontal_offset"], 3e-6)
            self.assertEqual(capture["preamble"]["timebase_s"], 2e-4)
            self.assertEqual(capture["time_origin_s"], -1e-6)
            self.assertAlmostEqual(capture["sample_rate_hz"], 1.0 / 2e-7)
            self.assertEqual(capture["integrity"]["status"], "COMPLETE")
            self.assertIn("payload_slice_sha256", capture["integrity"]["checks"])
            self.assertIn("payload_file_sha256", capture["integrity"]["checks"])
            self.assertEqual(capture["integrity"]["recorded_checks"], ["payload framing"])
            self.assertEqual(capture["time_correspondence"]["status"], "UNVERIFIED")
            self.assertEqual(capture["time_correspondence"]["time_reference"], "descriptor")
            self.assertEqual(capture["screen_range"], provenance["screen_range"])
            self.assertEqual(capture["screen_range_revalidation"], {"applied": False})
            self.assertEqual(capture["provenance"]["new_transition_proven"], False)
            self.assertEqual(capture["provenance"]["raw_file"], "waveform.raw")
            self.assertEqual(capture["provenance"]["raw_sha256"], "ab" * 32)
            self.assertEqual(capture["provenance"]["screenshot"], {"present": False})

    def test_bundle_without_file_sha256_still_verifies_the_slice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", data_overrides={"file_sha256": None})
            capture = load_capture(path)
            self.assertNotIn("payload_file_sha256", capture["integrity"]["checks"])
            self.assertEqual(capture["points"], 2)

    def test_code_domain_bundle_stays_in_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [-2, 0, 2], dtype="<i2", units="code", scale_usable=False,
                           calibration_status="CODE_ONLY", code_scale_v=None, zero_code=None,
                           offset_v=None, vdiv=None, adc=(-32768, 32767))
            capture = load_capture(path)
            calibration = capture["calibration"]
            self.assertEqual(calibration["units"], "code")
            self.assertEqual(calibration["status"], "CODE_ONLY")
            self.assertEqual(calibration["scale_usable"], "UNKNOWN")
            self.assertIsNone(calibration["code_scale_v"])
            self.assertEqual(calibration["adc_min_code"], -32768)
            self.assertIn("bundle_declares_scale_unusable", calibration["recorded_scale_reasons"])
            with self.assertRaises(AnalysisError) as caught:
                samples_to_volts(capture["samples"], calibration)
            self.assertEqual(caught.exception.code, "SCALE_UNUSABLE")

    def test_declared_channel_is_accepted_and_a_different_one_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", channel="CH3")
            self.assertEqual(load_capture(path, "CH3")["channel"], "CH3")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path, "CH1")
            self.assertEqual(caught.exception.code, "CHANNEL_MISSING")

    def test_sample_interval_can_come_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", sample_interval_s=None)
            capture = load_capture(path, sample_rate_hz=1e6)
            self.assertAlmostEqual(capture["sample_interval_s"], 1e-6)
            agreeing = load_capture(path, sample_interval_s=1e-6)
            self.assertAlmostEqual(agreeing["sample_interval_s"], 1e-6)


class BundleFailClosedTests(unittest.TestCase):
    def _load(self, root: Path, path: Path, **kwargs):
        return load_capture(path, **kwargs)

    def test_slice_hash_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="u1", data_overrides={"sha256": "0" * 64})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "HASH_MISMATCH")

    def test_file_hash_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="u1", data_overrides={"file_sha256": "0" * 64})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "HASH_MISMATCH")

    def test_byte_range_past_the_end_of_the_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="u1", data_overrides={"byte_length": 7, "points": 7})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
            self.assertIn("byte_length", str(caught.exception))

    def test_truncated_payload_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3, 4], dtype="<i2", byte_offset=0)
            (root / "waveform.bin").write_bytes((root / "waveform.bin").read_bytes()[:5])
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")

    def test_point_count_and_byte_length_must_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="<i2", data_overrides={"byte_length": 3})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
            self.assertIn("need 6", str(caught.exception))

    def test_width_bytes_must_match_the_dtype(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="<i2", data_overrides={"width_bytes": 1})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
            self.assertIn("width_bytes", str(caught.exception))

    def test_incomplete_integrity_status_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2, 3], dtype="u1", integrity_status="INCOMPLETE")
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")

    def test_non_positive_sample_interval_is_refused(self):
        for interval in (0.0, -1e-6, float("nan")):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = _bundle(root, [1, 2, 3], dtype="u1", sample_interval_s=interval)
                with self.assertRaises(AnalysisError) as caught:
                    self._load(root, path)
                self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")

    def test_missing_sample_interval_needs_an_explicit_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", sample_interval_s=None)
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")
            self.assertIn("--sample-interval-s", str(caught.exception))

    def test_command_line_interval_must_agree_with_the_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", sample_interval_s=2e-7)
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path, sample_interval_s=5e-7)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")
            self.assertIn("was requested", str(caught.exception))
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path, sample_interval_s=2e-7, sample_rate_hz=1e6)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")

    def test_unknown_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", schema="waveform-bundle/v2")
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "SCHEMA_UNSUPPORTED")
            other = root / "notes.json"
            other.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, other)
            self.assertEqual(caught.exception.code, "SCHEMA_UNSUPPORTED")

    def test_missing_required_section_is_refused(self):
        for section in ("source", "data", "time_axis", "vertical", "integrity"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = _bundle(root, [1, 2], dtype="u1", drop_section=section)
                with self.assertRaises(AnalysisError) as caught:
                    self._load(root, path)
                self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
                self.assertIn(section, str(caught.exception))

    def test_unsupported_dtype_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", data_overrides={"dtype": "c8", "width_bytes": 8})
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "DTYPE_UNSUPPORTED")

    def test_volts_bundle_without_code_scale_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="<i2", code_scale_v=None)
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
            self.assertIn("code_scale_v", str(caught.exception))

    def test_unrecognized_calibration_status_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1", calibration_status="MAYBE")
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "BUNDLE_INVALID")
            self.assertIn("calibration_status", str(caught.exception))

    def test_missing_payload_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1")
            (root / "waveform.bin").unlink()
            with self.assertRaises(AnalysisError) as caught:
                self._load(root, path)
            self.assertEqual(caught.exception.code, "PATH_UNRESOLVED")

    def test_legacy_override_flags_are_refused_for_a_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _bundle(root, [1, 2], dtype="u1")
            for kwargs in ({"vdiv": 1.0}, {"offset": 0.5}, {"calibration_file": root / "cal.json"}):
                with self.assertRaises(AnalysisError) as caught:
                    self._load(root, path, **kwargs)
                self.assertEqual(caught.exception.code, "CALIBRATION_INCONSISTENT")

    def test_missing_capture_path_is_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root)
            self.assertEqual(caught.exception.code, "MANIFEST_MISSING")
            self.assertIn("manifest.json", str(caught.exception))
            (root / "manifest.failed.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")


class BundleInstrumentMeasurementTests(unittest.TestCase):
    def _capture(self, root: Path, measurement, *, zero_code=0.0, code_scale_v=0.02):
        path = _bundle(root, [0, 150], dtype="u1", zero_code=zero_code, code_scale_v=code_scale_v,
                       instrument_measurements=measurement)
        return load_capture(path)

    def test_flat_measurement_is_translated_and_confirms_the_level(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(
                root, {"metric": "PKPK", "value": 3.0, "unit": "V", "source_query": "C1:PAVA? PKPK"}
            )
            nested = waveform_bundle._bundle_instrument_measurements(capture["manifest"], "CH1")
            self.assertEqual(nested["instrument_measurements"]["CH1"]["pkpk"]["value"], 3.0)
            result = attach_three_way_status(
                dict(capture["calibration"]), manifest=nested, channel="CH1",
                reconstruction={"amplitude_v": 2.98},
            )
            self.assertEqual(result["level_confirmed"], "PASS")
            self.assertAlmostEqual(result["tolerance"], 2 * 0.02 + 0.02 * 3.0)

    def test_reconstruction_outside_tolerance_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(root, {"metric": "PKPK", "value": 3.0, "unit": "V"})
            nested = waveform_bundle._bundle_instrument_measurements(capture["manifest"], "CH1")
            result = attach_three_way_status(
                dict(capture["calibration"]), manifest=nested, channel="CH1",
                reconstruction={"amplitude_v": 5.0},
            )
            self.assertEqual(result["level_confirmed"], "FAIL")
            self.assertEqual(result["level_reason"], "reconstructed_outside_tolerance")
            self.assertEqual(result["status"], "VALID")

    def test_load_time_status_is_unknown_without_an_amplitude(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(root, {"metric": "PKPK", "value": 3.0, "unit": "V"})
            self.assertEqual(capture["calibration"]["level_confirmed"], "UNKNOWN")
            self.assertEqual(capture["calibration"]["level_reason"], "no_reconstructed_amplitude")
            self.assertEqual(capture["calibration"]["instrument_value"], 3.0)

    def test_absent_measurement_is_unknown_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(root, None)
            self.assertEqual(capture["calibration"]["level_confirmed"], "UNKNOWN")
            self.assertEqual(capture["calibration"]["level_reason"], "instrument_measurement_absent")

    def test_ampere_measurement_fails_instead_of_converting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(root, {"metric": "PKPK", "value": 3.0, "unit": "A"})
            nested = waveform_bundle._bundle_instrument_measurements(capture["manifest"], "CH1")
            result = attach_three_way_status(
                dict(capture["calibration"]), manifest=nested, channel="CH1",
                reconstruction={"amplitude_v": 3.0},
            )
            self.assertEqual(result["level_confirmed"], "FAIL")
            self.assertEqual(result["level_reason"], "instrument_measurement_in_a_not_volts")

    def test_decorated_measurement_value_is_parsed_from_the_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(root, {"metric": "top", "value": "3.04E+00V", "unit": "V"})
            nested = waveform_bundle._bundle_instrument_measurements(capture["manifest"], "CH1")
            self.assertEqual(nested["instrument_measurements"]["CH1"]["top"]["value"], 3.04)
            self.assertEqual(capture["calibration"]["instrument_value"], 3.04)

    def test_per_channel_measurement_shape_passes_through(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            measurement = {"CH1": {"pkpk": {"value": 3.0, "unit": "V", "raw": "3.0"}}}
            capture = self._capture(root, measurement)
            nested = waveform_bundle._bundle_instrument_measurements(capture["manifest"], "CH1")
            self.assertEqual(nested["instrument_measurements"], measurement)
            self.assertEqual(capture["calibration"]["instrument_value"], 3.0)


class CsvCaptureTests(unittest.TestCase):
    def _csv(self, root: Path, text: str, name: str = "capture.csv") -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_one_column_values_need_an_explicit_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0.0\n1.5\n-2.25\n")
            capture = load_capture(path, sample_interval_s=1e-3)
            self.assertEqual(capture["source_format"], "csv")
            self.assertEqual(capture["points"], 3)
            self.assertEqual(capture["time_origin_s"], 0.0)
            self.assertAlmostEqual(capture["sample_interval_s"], 1e-3)
            self.assertEqual(capture["calibration"]["units"], "V")
            self.assertEqual(capture["calibration"]["status"], "VALID")
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], capture["calibration"]), [0.0, 1.5, -2.25]
            )

    def test_one_column_values_without_an_interval_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0.0\n1.5\n")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")

    def test_two_columns_with_a_header_derive_interval_and_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "time_s,value_v\n1e-6,0.0\n3e-6,1.0\n5e-6,2.0\n")
            capture = load_capture(path)
            self.assertEqual(capture["points"], 3)
            self.assertAlmostEqual(capture["sample_interval_s"], 2e-6)
            self.assertAlmostEqual(capture["sample_rate_hz"], 5e5)
            self.assertAlmostEqual(capture["time_origin_s"], 1e-6)
            self.assertEqual(capture["manifest"]["columns"], 2)
            self.assertEqual(capture["manifest"]["header"], ["time_s", "value_v"])
            np.testing.assert_allclose(capture["samples"], [0.0, 1.0, 2.0])

    def test_two_columns_without_a_header_and_reversed_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plain = self._csv(root, "0,1.0\n1e-6,2.0\n", name="plain.csv")
            capture = load_capture(plain)
            self.assertAlmostEqual(capture["sample_interval_s"], 1e-6)
            np.testing.assert_allclose(capture["samples"], [1.0, 2.0])
            reversed_header = self._csv(root, "value,time\n5.0,0\n6.0,2e-6\n", name="reversed.csv")
            capture = load_capture(reversed_header)
            self.assertAlmostEqual(capture["sample_interval_s"], 2e-6)
            np.testing.assert_allclose(capture["samples"], [5.0, 6.0])

    def test_non_uniform_time_column_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0,1.0\n1e-6,2.0\n3e-6,3.0\n")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")
            self.assertIn("uniformly sampled", str(caught.exception))

    def test_command_line_interval_must_agree_with_the_time_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0,1.0\n1e-6,2.0\n")
            agreeing = load_capture(path, sample_interval_s=1e-6)
            self.assertAlmostEqual(agreeing["sample_interval_s"], 1e-6)
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path, sample_rate_hz=1e3)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")

    def test_non_finite_value_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0.0\nnan\n1.0\n")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path, sample_interval_s=1e-6)
            self.assertEqual(caught.exception.code, "CAPTURE_INVALID")

    def test_three_columns_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0,1.0,2.0\n1e-6,2.0,3.0\n")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path, sample_interval_s=1e-6)
            self.assertEqual(caught.exception.code, "CAPTURE_INVALID")

    def test_header_without_data_rows_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "time_s,value_v\n")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "CAPTURE_INVALID")

    def test_units_flag_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, "0\n1\n")
            capture = load_capture(path, sample_interval_s=1e-6, units="code")
            self.assertEqual(capture["calibration"]["units"], "code")
            self.assertEqual(capture["calibration"]["status"], "CODE_ONLY")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path, sample_interval_s=1e-6, units="dBm")
            self.assertEqual(caught.exception.code, "UNITS_UNSUPPORTED")


class NpzCaptureTests(unittest.TestCase):
    def test_float_samples_with_sample_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(path, samples=np.array([0.0, 1.0, 2.0]), sample_interval_s=1e-6)
            capture = load_capture(path)
            self.assertEqual(capture["source_format"], "npz")
            self.assertAlmostEqual(capture["sample_interval_s"], 1e-6)
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], capture["calibration"]), [0.0, 1.0, 2.0]
            )

    def test_sample_rate_metadata_is_inverted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(path, samples=np.array([0.0, 1.0]), sample_rate_hz=4e6, time_origin_s=-2e-6)
            capture = load_capture(path)
            self.assertAlmostEqual(capture["sample_interval_s"], 0.25e-6)
            self.assertAlmostEqual(capture["time_origin_s"], -2e-6)

    def test_integer_codes_with_an_explicit_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(
                path,
                samples=np.array([-100, 0, 100], dtype=np.int16),
                sample_interval_s=1e-6,
                code_scale_v=0.04,
                zero_code=0.0,
                offset_v=0.5,
                units="V",
            )
            capture = load_capture(path)
            self.assertEqual(capture["dtype"], "int16")
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], capture["calibration"]), [-3.5, 0.5, 4.5]
            )
            self.assertEqual(capture["calibration"]["source"], "NPZ metadata: explicit units and vertical scale")

    def test_missing_samples_array_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(path, values=np.array([0.0, 1.0]), sample_interval_s=1e-6)
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "METADATA_MISSING")

    def test_missing_interval_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(path, samples=np.array([0.0, 1.0]))
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "TIME_AXIS_INVALID")
            self.assertAlmostEqual(load_capture(path, sample_interval_s=1e-6)["sample_interval_s"], 1e-6)

    def test_integer_samples_need_a_declared_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "capture.npz"
            np.savez(path, samples=np.array([1, 2], dtype=np.int16), sample_interval_s=1e-6)
            with self.assertRaises(AnalysisError) as caught:
                load_capture(path)
            self.assertEqual(caught.exception.code, "METADATA_MISSING")
            coded = load_capture(path, units="code")
            self.assertEqual(coded["calibration"]["status"], "CODE_ONLY")


class LegacySiglentCompatibilityTests(unittest.TestCase):
    def test_byte_capture_still_loads_with_the_recorded_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_legacy_capture(root, [-10, 0, 10])
            capture = load_capture(root, "C1")
            self.assertEqual(capture["source_format"], "siglent-manifest")
            self.assertEqual(capture["manifest_path"], (root / "manifest.json").resolve())
            calibration = capture["calibration"]
            self.assertEqual(calibration["status"], "VALID")
            self.assertEqual(calibration["units"], "V")
            self.assertEqual(calibration["zero_code"], 0.0)
            self.assertEqual(calibration["adc_min_code"], -128)
            self.assertEqual(calibration["adc_max_code"], 127)
            self.assertIsNone(calibration["full_scale_code"])
            self.assertIn("descriptor_vdiv_times_probe_matches_capture_snapshot", calibration["checks"])
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], calibration), [-2.0, 0.0, 2.0]
            )

    def test_channel_may_be_omitted_when_the_manifest_has_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_legacy_capture(root, [1, 2])
            self.assertEqual(load_capture(root)["channel"], "C1")
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C2")
            self.assertEqual(caught.exception.code, "CHANNEL_MISSING")

    def test_panel_offset_is_stored_as_the_additive_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_legacy_capture(root, [0, 10], vdiv=2.0, offset=0.5, codes_per_div=10.0)
            capture = load_capture(root, "C1")
            calibration = capture["calibration"]
            self.assertAlmostEqual(calibration["code_scale_v"], 0.2)
            # The device-side conversion subtracts the panel offset; the canonical
            # formula adds effective_offset_v, so it must reproduce that voltage.
            self.assertAlmostEqual(calibration["effective_offset_v"], -0.5)
            np.testing.assert_allclose(
                samples_to_volts(capture["samples"], calibration),
                [code * 0.2 - 0.5 for code in (0, 10)],
            )

    def test_word_capture_without_independent_calibration_is_code_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_legacy_capture(root, [-256, 0, 256], width=2)
            capture = load_capture(root, "C1")
            calibration = capture["calibration"]
            self.assertEqual(calibration["status"], "OBSERVED_UNVERIFIED")
            self.assertEqual(calibration["units"], "code")
            self.assertNotIn("code_scale_v", calibration)
            self.assertEqual(calibration["adc_min_code"], -32768)
            self.assertEqual(calibration["adc_max_code"], 32767)
            # The three-way claims are attached by the analysis step, exactly as
            # the legacy loader did, so they are not present on a raw load.
            self.assertNotIn("scale_usable", calibration)
            with self.assertRaises(AnalysisError) as caught:
                samples_to_volts(capture["samples"], calibration)
            self.assertEqual(caught.exception.code, "SCALE_UNUSABLE")

    def test_word_capture_with_a_bound_calibration_file_loads_volts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_legacy_capture(root, [-256, 0, 256], width=2)
            capture = load_capture(root, "C1")
            calibration_path = root.parent / f"calibration-{root.name}.json"
            calibration_path.write_text(
                json.dumps(
                    {
                        "channels": {
                            "C1": {
                                "word_scale_verified": True,
                                "capture_sha256": capture["raw_sha256"],
                                "word_codes_per_div": 7680,
                                "vdiv_v_per_div": 1.0,
                                "offset_v": 0.5,
                                "evidence": "known DC reference and BYTE/WORD comparison",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            calibrated = load_capture(root, "C1", calibration_file=calibration_path)
            self.assertEqual(calibrated["calibration"]["status"], "VALID")
            self.assertAlmostEqual(calibrated["calibration"]["effective_offset_v"], -0.5)
            np.testing.assert_allclose(
                samples_to_volts(calibrated["samples"], calibrated["calibration"]),
                [-256 / 7680 - 0.5, -0.5, 256 / 7680 - 0.5],
            )
            calibration_path.write_text(
                json.dumps({"channels": {"C1": {
                    "word_scale_verified": True,
                    "capture_sha256": "0" * 64,
                    "word_codes_per_div": 7680,
                    "vdiv_v_per_div": 1.0,
                    "offset_v": 0.0,
                    "evidence": "known DC reference",
                }}}),
                encoding="utf-8",
            )
            stale = load_capture(root, "C1", calibration_file=calibration_path)
            self.assertIn("calibration_capture_sha256_mismatch", stale["calibration"]["verification_failures"])
            self.assertEqual(stale["calibration"]["status"], "OBSERVED_UNVERIFIED")

    def test_relocated_manifest_falls_back_to_capture_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            moved = Path(directory) / "moved"
            _write_legacy_capture(source, [1, 2, 3, 4])
            shutil.move(str(source), str(moved))
            manifest = json.loads((moved / "manifest.json").read_text())
            manifest["results"][0]["merged_waveform"] = str(moved.parent / "source" / "C1" / "waveform.bin")
            manifest["results"][0]["segments"][0]["payload"] = str(
                moved.parent / "source" / "C1" / "segment-000000.bin"
            )
            (moved / "manifest.json").write_text(json.dumps(manifest))
            capture = load_capture(moved, "C1")
            self.assertEqual(capture["path"], (moved / "C1" / "waveform.bin").resolve())

    def test_hash_mismatch_is_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_legacy_capture(root, [1, 2, 3])
            manifest = json.loads(manifest_path.read_text())
            manifest["results"][0]["merged_waveform_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "HASH_MISMATCH")

    def test_segment_payload_size_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_legacy_capture(root, [0, 1, 2, 3])
            manifest = json.loads(manifest_path.read_text())
            manifest["results"][0]["segments"][0]["actual_payload_bytes"] = 3
            manifest["results"][0]["segments"][0]["actual_points"] = 3
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "DESCRIPTOR_MISMATCH")

    def test_provenance_reports_the_recorded_stop_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_legacy_capture(root, [1, 2])
            manifest = json.loads(manifest_path.read_text())
            manifest["existing_stop_claims_new_transition"] = False
            manifest_path.write_text(json.dumps(manifest))
            capture = load_capture(root, "C1")
            self.assertIs(capture["provenance"]["new_transition_proven"], False)
            self.assertEqual(capture["provenance"]["raw_sha256"], capture["raw_sha256"])
            self.assertIsNone(capture["provenance"]["screenshot"])
            self.assertEqual(capture["time_correspondence"]["status"], "UNVERIFIED")
            self.assertEqual(capture["screen_range"]["status"], "UNVERIFIED")

    def test_screen_range_revalidation_still_needs_the_opt_in_flag(self):
        reasons = [
            "screen record 2 differs from WAVEDESC 4",
            "scope duration 1.0 s differs from WAVEDESC duration 4e-06 s",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=1.0,
                frame_status="INCOMPLETE", reasons=reasons,
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1")
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            original_bytes = manifest_path.read_bytes()
            capture = load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(capture["integrity"]["status"], "COMPLETE")
            record = capture["screen_range_revalidation"]
            self.assertTrue(record["applied"])
            self.assertEqual(record["scope"], "in_memory_derived_report_only")
            self.assertEqual(record["original_frame_status"], "INCOMPLETE")
            self.assertEqual(record["original_frame_reasons"], reasons)
            self.assertEqual(record["note"], SCREEN_RANGE_REVALIDATION_NOTE)
            self.assertEqual(record["source_manifest_sha256"], hashlib.sha256(original_bytes).hexdigest())
            self.assertEqual(manifest_path.read_bytes(), original_bytes)
            self.assertEqual(capture["result"]["frame_report"]["scope_record"]["semantics"], "screen")

    def test_screen_range_revalidation_refuses_unknown_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_modern_capture(
                root, [0, 1, 2, 3], scope_points=2, scope_duration_s=4e-6,
                frame_status="INCOMPLETE",
                reasons=["screen record 2 differs from WAVEDESC 4", "downloaded 3 points, expected 4"],
            )
            with self.assertRaises(AnalysisError) as caught:
                load_capture(root, "C1", revalidate_screen_range=True)
            self.assertEqual(caught.exception.code, "CAPTURE_NOT_COMPLETE")
            self.assertTrue(any("unknown frame reason" in reason for reason in caught.exception.reasons))


class FormulaAndParserTests(unittest.TestCase):
    def _calibration(self, **overrides):
        base = {
            "status": "VALID",
            "units": "V",
            "zero_code": 127.0,
            "code_scale_v": 0.5,
            "effective_offset_v": -1.0,
        }
        base.update(overrides)
        return base

    def test_samples_to_volts_applies_zero_code_scale_and_offset(self):
        calibration = self._calibration()
        np.testing.assert_allclose(
            samples_to_volts(np.array([127, 129, 125], dtype=np.uint8), calibration),
            [-1.0, 0.0, -2.0],
        )

    def test_volts_to_codes_inverts_samples_to_volts(self):
        calibration = self._calibration()
        codes = np.array([0.0, 37.0, 255.0])
        np.testing.assert_allclose(
            volts_to_codes(samples_to_volts(codes, calibration), calibration), codes
        )

    def test_float_identity_scale_is_a_direct_passthrough(self):
        calibration = self._calibration(zero_code=0.0, code_scale_v=1.0, effective_offset_v=0.0)
        values = np.array([0.0, 1.5, -2.5])
        result = samples_to_volts(values, calibration)
        np.testing.assert_allclose(result, values)
        self.assertEqual(result.dtype, np.float64)

    def test_samples_to_volts_refuses_an_unknown_scale(self):
        with self.assertRaises(AnalysisError) as caught:
            samples_to_volts(np.array([1]), {"zero_code": 0.0})
        self.assertEqual(caught.exception.code, "SCALE_UNUSABLE")
        with self.assertRaises(AnalysisError) as caught:
            volts_to_codes(np.array([1.0]), self._calibration(code_scale_v=0.0))
        self.assertEqual(caught.exception.code, "SCALE_UNUSABLE")

    def test_parse_scpi_number_matches_the_device_parser(self):
        self.assertEqual(parse_scpi_number("C1:VDIV 5.00E+00V"), 5.0)
        self.assertEqual(parse_scpi_number("C1:OFST -1.50E-01V"), -0.15)
        self.assertEqual(parse_scpi_number("SARA 1.00E+07Sa/s"), 1e7)
        self.assertEqual(parse_scpi_number("25.0 Mpts"), 25e6)
        self.assertEqual(parse_scpi_number("5.00E-01", default_unit="V"), 0.5)
        self.assertIsNone(parse_scpi_number("C1:VDIV <timeout>"))
        self.assertIsNone(parse_scpi_number(None))

    def test_validate_frame_separates_screen_semantics_from_the_descriptor(self):
        common = dict(
            scope_points=2,
            scope_duration_s=1.0,
            wavedesc_points=4,
            sample_interval_s=1e-6,
            downloaded_points=4,
            downloaded_duration_s=4e-6,
            bytes_per_point=1,
            expected_payload_bytes=4,
            downloaded_payload_bytes=4,
        )
        same_record = validate_frame(**common)
        self.assertEqual(same_record["status"], "INCOMPLETE")
        self.assertIn("screen record 2 differs from WAVEDESC 4", same_record["reasons"])
        screen = validate_frame(**common, scope_points_semantics="screen")
        self.assertEqual(screen["status"], "COMPLETE")
        self.assertEqual(screen["scope_record"]["semantics"], "screen")
        self.assertEqual(screen["range_correspondence"]["status"], "UNVERIFIED")
        self.assertIs(screen["range_correspondence"]["point_counts_equal"], False)
        with self.assertRaises(ValueError):
            validate_frame(**common, scope_points_semantics="some_record")

    def test_module_carries_no_device_skill_dependency(self):
        source = Path(waveform_bundle.__file__).read_text(encoding="utf-8")
        for forbidden in ("import scope_protocol", "from scope_protocol", "capture_scope", "ds1000z", "gds1000b"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("scope_protocol", sys.modules)


if __name__ == "__main__":
    unittest.main()
