#!/usr/bin/env python3
"""Read-only, bounded analysis helpers for SDS waveform capture artifacts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised by CLI packaging environments
    np = None


SCHEMA_VERSION = "1.0"
DEFAULT_CHUNK_POINTS = 1_000_000
DEFAULT_PREVIEW_BUCKETS = 256
DEFAULT_EVENT_PAGE = 100
DEFAULT_EVENT_SCAN_BUDGET = 10_000
DEFAULT_STRUCTURE_EDGE_LIMIT = 20_000
DEFAULT_CLUSTER_GAP_PERIOD_FACTOR = 3.0
DEFAULT_CLUSTER_GAP_SAMPLE_INTERVALS = 8.0
DEFAULT_WINDOW_POINTS = 2_000
DEFAULT_JSON_BYTES = 256 * 1024
MAX_PREVIEW_BUCKETS = 2_000
MAX_EVENT_PAGE = 100
MAX_EVENT_SCAN_BUDGET = 20_000
MAX_STRUCTURE_EDGE_LIMIT = 200_000
MAX_WINDOW_POINTS = 2_000
MAX_JSON_BYTES = 4 * 1024 * 1024


class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, reasons: Optional[list[str]] = None):
        super().__init__(message)
        self.code = code
        self.reasons = reasons or [message]


def _int_field(value: Any, name: str, default: Optional[int] = None) -> int:
    if value is None:
        if default is not None:
            return default
        raise AnalysisError("DESCRIPTOR_MISMATCH", f"Descriptor field {name} is missing")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisError("DESCRIPTOR_MISMATCH", f"Descriptor field {name} is not an integer: {value!r}") from exc


def _require_numpy() -> None:
    if np is None:
        raise AnalysisError("NUMPY_UNAVAILABLE", "NumPy >= 2.0 is required for waveform analysis")
    major = int(np.__version__.split(".", 1)[0])
    if major < 2:
        raise AnalysisError("NUMPY_UNAVAILABLE", f"NumPy >= 2.0 is required; found {np.__version__}")


def _sha256_file(path: Path, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _resolve_artifact(stored_path: Any, manifest_dir: Path, fallback: Path) -> Path:
    candidates: list[Path] = []
    if stored_path:
        path = Path(str(stored_path)).expanduser()
        stored_candidate = path if path.is_absolute() else manifest_dir / path
        if stored_candidate.is_file():
            return stored_candidate.resolve()
    candidates.append(manifest_dir / fallback)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise AnalysisError(
        "PATH_UNRESOLVED",
        f"Could not resolve waveform artifact; tried: {', '.join(str(item) for item in candidates)}",
    )


def _select_result(manifest: dict[str, Any], channel: str) -> dict[str, Any]:
    matching = [item for item in manifest.get("results", []) if item.get("channel") == channel]
    declared_channels = set(manifest.get("channels", []))
    if not matching and channel not in declared_channels:
        raise AnalysisError("CHANNEL_MISSING", f"Channel {channel} is not present in the capture manifest")
    complete = [
        item
        for item in matching
        if item.get("frame_report", {}).get("status") == "COMPLETE"
        and item.get("segment_report", {}).get("status") == "COMPLETE"
        and item.get("merged_waveform")
    ]
    if len(complete) > 1:
        raise AnalysisError("AMBIGUOUS_CAPTURE", f"Multiple complete results exist for {channel}")
    if not complete:
        reasons = [
            f"result {index}: frame={item.get('frame_report', {}).get('status')}, "
            f"segments={item.get('segment_report', {}).get('status')}, "
            f"merged_waveform={'present' if item.get('merged_waveform') else 'missing'}"
            for index, item in enumerate(matching)
        ] or [f"No result exists for {channel}"]
        raise AnalysisError("CAPTURE_NOT_COMPLETE", f"No unique complete capture exists for {channel}", reasons)
    return complete[0]


def _channel_snapshot(manifest: dict[str, Any], channel: str) -> dict[str, Any]:
    for root_key in ("capture_configuration", "pre_capture_snapshot"):
        snapshot = manifest.get(root_key, {})
        found = snapshot.get("channels", {}).get(channel)
        if found:
            return found
    return {}


def _load_calibration(
    manifest: dict[str, Any],
    channel: str,
    preamble: dict[str, Any],
    width: int,
    *,
    calibration_file: Optional[Path],
    vdiv_override: Optional[float],
    offset_override: Optional[float],
    raw_sha256: str,
) -> dict[str, Any]:
    descriptor_vdiv = _finite_number(preamble.get("vdiv"))
    probe = _finite_number(preamble.get("probe"))
    descriptor_offset = _finite_number(preamble.get("offset"))
    codes_per_div = _finite_number(preamble.get("code_per_div"))
    snapshot = _channel_snapshot(manifest, channel)
    snapshot_vdiv = _finite_number(snapshot.get("vdiv"))
    snapshot_offset = _finite_number(snapshot.get("offset"))

    issues: list[str] = []
    if descriptor_vdiv is None or descriptor_vdiv <= 0:
        issues.append("descriptor_vdiv_missing_or_invalid")
    if probe is None or probe <= 0:
        issues.append("descriptor_probe_missing_or_invalid")
    if descriptor_offset is None:
        issues.append("descriptor_offset_missing_or_invalid")
    if codes_per_div is None or codes_per_div <= 0:
        issues.append("descriptor_codes_per_div_missing_or_invalid")

    effective_vdiv = descriptor_vdiv * probe if descriptor_vdiv and probe else None
    effective_offset = descriptor_offset * probe if descriptor_offset is not None and probe else None
    checks: list[str] = []
    if snapshot_vdiv is not None:
        if effective_vdiv is not None and math.isclose(effective_vdiv, snapshot_vdiv, rel_tol=0.02, abs_tol=1e-9):
            checks.append("descriptor_vdiv_times_probe_matches_capture_snapshot")
        else:
            issues.append("descriptor_scale_does_not_match_snapshot_vdiv")
    if snapshot_offset is not None:
        if effective_offset is not None and math.isclose(effective_offset, snapshot_offset, rel_tol=0.02, abs_tol=1e-9):
            checks.append("descriptor_offset_times_probe_matches_snapshot")
        else:
            issues.append("descriptor_offset_does_not_match_snapshot_offset")

    if vdiv_override is not None:
        if not math.isfinite(vdiv_override) or vdiv_override <= 0:
            raise AnalysisError("CALIBRATION_INCONSISTENT", "--vdiv must be a finite positive physical V/div value")
        effective_vdiv = vdiv_override
        issues = [item for item in issues if item != "descriptor_scale_does_not_match_snapshot_vdiv"]
    if offset_override is not None:
        if not math.isfinite(offset_override):
            raise AnalysisError("CALIBRATION_INCONSISTENT", "--offset must be a finite physical voltage")
        effective_offset = offset_override
        issues = [item for item in issues if item != "descriptor_offset_does_not_match_snapshot_offset"]

    calibration: dict[str, Any] = {
        "status": "UNKNOWN" if width == 1 else "OBSERVED_UNVERIFIED",
        "units": "V" if width == 1 and not issues else "code",
        "source": "descriptor.vdiv * probe and descriptor.offset * probe" if width == 1 else "WORD voltage scaling requires independent calibration",
        "descriptor_vdiv": descriptor_vdiv,
        "probe_factor": probe,
        "descriptor_offset": descriptor_offset,
        "snapshot_vdiv": snapshot_vdiv,
        "snapshot_offset": snapshot_offset,
        "effective_vdiv_v_per_div": effective_vdiv,
        "effective_offset_v": effective_offset,
        "codes_per_div": codes_per_div,
        "checks": checks,
        "verification_failures": issues,
        "word_scale_verified": False if width == 2 else None,
    }

    if vdiv_override is not None:
        calibration["effective_vdiv_v_per_div"] = effective_vdiv
        calibration["vdiv_source"] = "explicit probe-compensated --vdiv"
    else:
        calibration["vdiv_source"] = calibration["source"]
    if offset_override is not None:
        calibration["effective_offset_v"] = effective_offset
        calibration["offset_source"] = "explicit physical --offset"
    else:
        calibration["offset_source"] = calibration["source"]

    if width == 1 and not issues and effective_vdiv is not None and effective_offset is not None and codes_per_div is not None and codes_per_div > 0:
        calibration["status"] = "VALID"
        calibration["units"] = "V"
        calibration["code_scale_v"] = effective_vdiv / codes_per_div
        return calibration

    if calibration_file is not None:
        try:
            external = json.loads(calibration_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AnalysisError("CALIBRATION_INCONSISTENT", f"Cannot read calibration file: {exc}") from exc
        channel_cal = external.get("channels", {}).get(channel, {})
        divisor = _finite_number(channel_cal.get("word_codes_per_div"))
        external_vdiv = _finite_number(channel_cal.get("vdiv_v_per_div"))
        external_offset = _finite_number(channel_cal.get("offset_v", effective_offset))
        evidence = channel_cal.get("evidence")
        if (
            channel_cal.get("word_scale_verified") is True
            and str(channel_cal.get("capture_sha256", "")).lower() == raw_sha256.lower()
            and divisor
            and divisor > 0
            and external_vdiv
            and external_vdiv > 0
            and external_offset is not None
            and isinstance(evidence, str)
            and evidence.strip()
        ):
            calibration.update(
                {
                    "status": "VALID",
                    "units": "V",
                    "source": f"calibration file: {calibration_file.name}",
                    "word_scale_verified": True,
                    "word_codes_per_div": divisor,
                    "effective_vdiv_v_per_div": external_vdiv,
                    "effective_offset_v": external_offset,
                    "evidence": evidence,
                    "capture_sha256": raw_sha256,
                    "code_scale_v": external_vdiv / divisor,
                }
            )
        else:
            failures = []
            if str(channel_cal.get("capture_sha256", "")).lower() != raw_sha256.lower():
                failures.append("calibration_capture_sha256_mismatch")
            if channel_cal.get("word_scale_verified") is not True:
                failures.append("word_scale_verified_not_true")
            if not divisor or divisor <= 0:
                failures.append("word_codes_per_div_missing_or_invalid")
            if not external_vdiv or external_vdiv <= 0:
                failures.append("calibration_vdiv_missing_or_invalid")
            if not isinstance(evidence, str) or not evidence.strip():
                failures.append("independent_evidence_missing")
            calibration["verification_failures"] = issues + failures
    return calibration


def load_capture(
    capture: Path,
    channel: str,
    *,
    calibration_file: Optional[Path] = None,
    vdiv_override: Optional[float] = None,
    offset_override: Optional[float] = None,
) -> dict[str, Any]:
    _require_numpy()
    capture = capture.expanduser().resolve()
    if capture.is_dir():
        manifest_path = capture / "manifest.json"
        failed_path = capture / "manifest.failed.json"
    else:
        manifest_path = capture
        failed_path = capture.with_name("manifest.failed.json")
    if not manifest_path.is_file():
        if failed_path.is_file():
            raise AnalysisError("CAPTURE_NOT_COMPLETE", f"Only failed capture manifest exists: {failed_path}")
        raise AnalysisError("MANIFEST_MISSING", f"Capture manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError("MANIFEST_MISSING", f"Cannot read capture manifest: {exc}") from exc
    if manifest.get("error"):
        raise AnalysisError("CAPTURE_NOT_COMPLETE", f"Capture manifest records failure: {manifest['error']}")
    result = _select_result(manifest, channel)
    manifest_dir = manifest_path.parent
    preamble = result.get("preamble") or {}
    width = _int_field(preamble.get("data_width_bytes") or result.get("waveform_format", {}).get("bytes_per_point"), "data_width_bytes", 0)
    if width not in (1, 2):
        raise AnalysisError("WIDTH_UNSUPPORTED", f"Unsupported waveform width: {width}")
    comm_type = preamble.get("comm_type")
    if comm_type is not None and _int_field(comm_type, "comm_type") != width - 1:
        raise AnalysisError("DESCRIPTOR_MISMATCH", f"COMM_TYPE={comm_type} disagrees with {width} bytes/point")
    if width == 2:
        if preamble.get("byte_order") != "LSB" or _int_field(preamble.get("comm_order"), "comm_order", -1) != 0:
            raise AnalysisError("WIDTH_UNSUPPORTED", "WORD capture must be explicitly LSB")
    sparsing = preamble.get("sparsing_factor")
    if sparsing is None:
        sparsing = preamble.get("interval", 1)
    if _int_field(sparsing, "sparsing_factor", 1) != 1:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Only un-sparsed WAV data (SPARSING_FACTOR=1) is supported")

    points = _int_field(preamble.get("wave_array_count"), "wave_array_count", 0)
    expected_bytes = points * width
    sample_interval = _finite_number(preamble.get("sample_interval"))
    horizontal_offset = _finite_number(preamble.get("horizontal_offset"))
    timebase = _finite_number(preamble.get("timebase_s"))
    if points <= 0 or sample_interval is None or sample_interval <= 0 or horizontal_offset is None or timebase is None:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "WAVEDESC point count or sample interval is invalid")
    if _int_field(preamble.get("wave_array_1_bytes"), "wave_array_1_bytes", -1) != expected_bytes:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "WAVEDESC payload byte count disagrees with point count and width")
    if _int_field(result.get("merged_waveform_bytes"), "merged_waveform_bytes", -1) != expected_bytes:
        raise AnalysisError("LENGTH_MISMATCH", "Manifest merged byte count disagrees with WAVEDESC")
    segment_report = result.get("segment_report", {})
    report_bytes = segment_report.get("downloaded_payload_bytes")
    if report_bytes is None:
        report_bytes = sum(int(item.get("payload_length", 0)) for item in segment_report.get("segments", []))
    if _int_field(segment_report.get("downloaded_points"), "segment_report.downloaded_points", -1) != points or _int_field(report_bytes, "segment_report.downloaded_payload_bytes", -1) != expected_bytes:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Segment report does not cover the WAVEDESC point and byte counts")
    frame_report = result.get("frame_report", {})
    for field_name, observed in (
        ("frame_report.scope_record.points", frame_report.get("scope_record", {}).get("points")),
        ("frame_report.wavedesc_record.points", frame_report.get("wavedesc_record", {}).get("points")),
        ("frame_report.downloaded.points", frame_report.get("downloaded", {}).get("points")),
        ("frame_report.segments.downloaded_points", frame_report.get("segments", {}).get("downloaded_points")),
        ("frame_report.segments.expected_points", frame_report.get("segments", {}).get("expected_points")),
    ):
        if observed is not None and _int_field(observed, field_name) != points:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"{field_name} disagrees with WAVEDESC point count")

    waveform_path = _resolve_artifact(
        result.get("merged_waveform"), manifest_dir, Path(channel) / "waveform.bin"
    )
    if waveform_path.stat().st_size != expected_bytes:
        raise AnalysisError("LENGTH_MISMATCH", f"Waveform file has {waveform_path.stat().st_size} bytes; expected {expected_bytes}")
    expected_hash = result.get("merged_waveform_sha256")
    actual_hash = _sha256_file(waveform_path)
    if not expected_hash or actual_hash.lower() != str(expected_hash).lower():
        raise AnalysisError("HASH_MISMATCH", "Merged waveform SHA-256 does not match manifest")

    segments = result.get("segments", [])
    if not segments:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Complete merged capture has no segment metadata")
    cursor = 0
    segment_checks = 0
    concatenated_digest = hashlib.sha256()
    for segment in segments:
        start = int(segment.get("requested_start", segment.get("start", -1)))
        requested_points = int(segment.get("requested_points", 0))
        actual_bytes = int(segment.get("actual_payload_bytes", segment.get("payload_length", -1)))
        if actual_bytes < 0 or actual_bytes % width:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"Segment payload width mismatch at point {cursor}")
        actual_points = actual_bytes // width
        if start != cursor or requested_points <= 0 or actual_points != requested_points:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"Segment continuity/size mismatch at point {cursor}")
        manifest_actual_points = segment.get("actual_points")
        if manifest_actual_points is not None and _int_field(manifest_actual_points, "segment.actual_points", -1) != actual_points:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"Segment actual point count mismatch at point {cursor}")
        cursor += actual_points
        segment_path_value = segment.get("payload")
        if segment_path_value:
            segment_path = _resolve_artifact(segment_path_value, manifest_dir, Path(channel) / Path(segment_path_value).name)
            if segment_path.stat().st_size != actual_bytes:
                raise AnalysisError("LENGTH_MISMATCH", f"Segment payload size mismatch: {segment_path}")
            expected_segment_hash = segment.get("sha256")
            if not expected_segment_hash or _sha256_file(segment_path).lower() != str(expected_segment_hash).lower():
                raise AnalysisError("HASH_MISMATCH", f"Segment SHA-256 mismatch: {segment_path}")
            with segment_path.open("rb") as stream:
                while chunk := stream.read(4 * 1024 * 1024):
                    concatenated_digest.update(chunk)
            segment_checks += 1
    if cursor != points:
        raise AnalysisError("DESCRIPTOR_MISMATCH", f"Segments cover {cursor} points; descriptor expects {points}")
    if concatenated_digest.hexdigest().lower() != actual_hash.lower():
        raise AnalysisError("HASH_MISMATCH", "Ordered segment concatenation does not match merged waveform SHA-256")

    dtype = np.dtype("i1") if width == 1 else np.dtype("<i2")
    samples = np.memmap(waveform_path, dtype=dtype, mode="r", shape=(points,))
    calibration = _load_calibration(
        manifest,
        channel,
        preamble,
        width,
        calibration_file=calibration_file,
        vdiv_override=vdiv_override,
        offset_override=offset_override,
        raw_sha256=actual_hash,
    )
    interval = sample_interval
    origin = horizontal_offset - timebase * 5.0
    return {
        "manifest_path": manifest_path,
        "manifest_dir": manifest_dir,
        "manifest": manifest,
        "result": result,
        "channel": channel,
        "path": waveform_path,
        "samples": samples,
        "points": points,
        "bytes": expected_bytes,
        "width": width,
        "dtype": str(dtype),
        "preamble": preamble,
        "sample_interval_s": interval,
        "sample_rate_hz": 1.0 / interval,
        "time_origin_s": origin,
        "calibration": calibration,
        "raw_sha256": actual_hash,
        "integrity": {
            "status": "COMPLETE",
            "checks": ["capture_reports_complete", "descriptor_point_byte_width_agree", "merged_file_size", "merged_sha256", "segment_ranges_and_sizes", "segment_sha256"],
            "segments_verified": segment_checks,
        },
    }


def _calibrated(code: float, capture: dict[str, Any]) -> float:
    cal = capture["calibration"]
    return code * cal["code_scale_v"] - cal["effective_offset_v"]


def _percentile_code(histogram: Any, count: int, percentile: float, code_min: int) -> int:
    rank = max(1, int(math.ceil(percentile * count)))
    index = int(np.searchsorted(np.cumsum(histogram, dtype=np.int64), rank, side="left"))
    return code_min + index


def summarize_capture(
    capture: dict[str, Any],
    *,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
    preview_buckets: int = DEFAULT_PREVIEW_BUCKETS,
) -> dict[str, Any]:
    _require_numpy()
    if chunk_points <= 0 or preview_buckets <= 0 or preview_buckets > MAX_PREVIEW_BUCKETS:
        raise AnalysisError("LIMIT_INVALID", "chunk_points and preview_buckets must be positive and within limits")
    samples = capture["samples"]
    width = capture["width"]
    code_min, code_max = (-128, 127) if width == 1 else (-32768, 32767)
    histogram = np.zeros(code_max - code_min + 1, dtype=np.int64)
    total_sum = 0
    total_square_sum = 0
    minimum = code_max
    maximum = code_min
    count = len(samples)
    for start in range(0, count, chunk_points):
        block = np.asarray(samples[start : min(start + chunk_points, count)], dtype=np.int64)
        if not block.size:
            continue
        total_sum += int(np.sum(block, dtype=np.int64))
        total_square_sum += int(np.sum(block * block, dtype=np.int64))
        minimum = min(minimum, int(block.min()))
        maximum = max(maximum, int(block.max()))
        histogram += np.bincount(block - code_min, minlength=len(histogram)).astype(np.int64, copy=False)
    mean_code = total_sum / count
    rms_code = math.sqrt(total_square_sum / count)
    percentiles = {f"p{int(p * 100):02d}": _percentile_code(histogram, count, p, code_min) for p in (0.01, 0.05, 0.5, 0.95, 0.99)}
    calibrated = capture["calibration"]["status"] == "VALID"
    if calibrated:
        scale = capture["calibration"]["code_scale_v"]
        offset = capture["calibration"]["effective_offset_v"]
        summary: dict[str, Any] = {
            "count": count,
            "min_v": _calibrated(minimum, capture),
            "max_v": _calibrated(maximum, capture),
            "mean_v": mean_code * scale - offset,
            "rms_v": math.sqrt(max(0.0, (total_square_sum / count) * scale * scale - 2 * scale * offset * mean_code + offset * offset)),
            "percentiles_v": {key: _calibrated(value, capture) for key, value in percentiles.items()},
            "underlying_code_statistics": {"min": minimum, "max": maximum, "mean": mean_code, "rms": rms_code},
        }
    else:
        summary = {"count": count, "min_code": minimum, "max_code": maximum, "mean_code": mean_code, "rms_code": rms_code, "percentiles_code": percentiles}
    preview = m4_preview(capture, preview_buckets)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "summarize",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "sampling": _sampling_envelope(capture),
        "calibration": capture["calibration"],
        "summary": summary,
        "percentile_method": "nearest_rank_no_interpolation_exact_for_discrete_codes",
        "preview": preview,
        "coverage": {"scanned_start": 0, "scanned_end_exclusive": count, "full_record_scanned": True, "chunk_points": chunk_points, "limitations": ["M4 preview is visualization-only and may omit narrow events"]},
    }


def m4_preview(capture: dict[str, Any], bucket_count: int) -> dict[str, Any]:
    _require_numpy()
    points = capture["points"]
    if bucket_count <= 0 or bucket_count > MAX_PREVIEW_BUCKETS:
        raise AnalysisError("LIMIT_INVALID", f"preview bucket count must be in 1..{MAX_PREVIEW_BUCKETS}")
    bucket_count = min(bucket_count, points)
    samples = capture["samples"]
    chosen: list[dict[str, Any]] = []
    for bucket in range(bucket_count):
        start = bucket * points // bucket_count
        end = (bucket + 1) * points // bucket_count
        if end <= start:
            continue
        minimum_index = start
        maximum_index = start
        minimum_value = int(samples[start])
        maximum_value = minimum_value
        for scan_start in range(start, end, DEFAULT_CHUNK_POINTS):
            scan_end = min(scan_start + DEFAULT_CHUNK_POINTS, end)
            values = np.asarray(samples[scan_start:scan_end])
            if not values.size:
                continue
            local_minimum = int(values.min())
            local_maximum = int(values.max())
            if local_minimum < minimum_value:
                minimum_value = local_minimum
                minimum_index = scan_start + int(np.argmin(values))
            if local_maximum > maximum_value:
                maximum_value = local_maximum
                maximum_index = scan_start + int(np.argmax(values))
        indices = {start, end - 1, minimum_index, maximum_index}
        for index in sorted(indices):
            code = int(samples[index])
            row: dict[str, Any] = {"sample": index, "code": code}
            if capture["calibration"]["status"] == "VALID":
                row["volts"] = _calibrated(code, capture)
            chosen.append(row)
    return {
        "kind": "M4",
        "semantics": "visualization_only_lossy",
        "value_domain": "voltage" if capture["calibration"]["status"] == "VALID" else "code",
        "bucket_count": bucket_count,
        "selected_points": len(chosen),
        "source_points": points,
        "points": chosen,
    }


def _capture_envelope(capture: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": capture["manifest"].get("idn", capture["manifest_path"].parent.name),
        "channel": capture["channel"],
        "raw_sha256": capture["raw_sha256"],
        "points": capture["points"],
        "bytes": capture["bytes"],
        "bytes_per_point": capture["width"],
        "path": str(capture["path"]),
    }


def _sampling_envelope(capture: dict[str, Any]) -> dict[str, Any]:
    preamble = capture["preamble"]
    return {
        "interval_s": capture["sample_interval_s"],
        "rate_hz": capture["sample_rate_hz"],
        "origin_s": capture["time_origin_s"],
        "delay_s": preamble.get("horizontal_offset"),
        "timebase_s": preamble.get("timebase_s"),
        "origin_formula": "horizontal_offset - timebase_s * 5 (10-division display)",
        "time_reference": "relative waveform/display time, not wall-clock time",
    }


def _crossing_time(left: float, right: float, threshold: float, left_index: int, interval: float, origin: float) -> float:
    delta = right - left
    fraction = 0.0 if delta == 0 else (threshold - left) / delta
    fraction = min(1.0, max(0.0, fraction))
    return origin + (left_index + fraction) * interval


def _resolve_time_range(capture: dict[str, Any], start_time_s: Optional[float], end_time_s: Optional[float]) -> tuple[int, int]:
    if start_time_s is None or end_time_s is None:
        raise AnalysisError("LIMIT_INVALID", "Both start_time_s and end_time_s are required")
    if not math.isfinite(start_time_s) or not math.isfinite(end_time_s) or start_time_s >= end_time_s:
        raise AnalysisError("LIMIT_INVALID", "Time range must be finite and start_time_s < end_time_s")
    origin = capture["time_origin_s"]
    interval = capture["sample_interval_s"]
    record_end = origin + capture["points"] * interval
    tolerance = max(interval * 1e-9, 1e-15)
    if start_time_s < origin - tolerance or end_time_s > record_end + tolerance:
        raise AnalysisError(
            "WINDOW_OUT_OF_RANGE",
            f"Requested time range [{start_time_s}, {end_time_s}) exceeds [{origin}, {record_end})",
        )

    def sample_index(time_s: float) -> int:
        raw = (time_s - origin) / interval
        nearest = round(raw)
        if abs(raw - nearest) <= 1e-9:
            raw = float(nearest)
        return max(0, min(capture["points"], int(math.ceil(raw))))

    start = sample_index(start_time_s)
    end = sample_index(end_time_s)
    if end <= start:
        raise AnalysisError("WINDOW_TOO_SMALL", "Time range does not contain a complete sample")
    return start, end


def _scan_edges(
    capture: dict[str, Any],
    low: float,
    high: float,
    *,
    domain: str,
    chunk_points: int,
    budget: int,
    scan_start: int = 0,
    scan_end: Optional[int] = None,
) -> tuple[list[dict[str, Any]], bool, int]:
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise AnalysisError("LIMIT_INVALID", "Thresholds must be finite and low < high")
    if domain not in ("code", "voltage"):
        raise AnalysisError("LIMIT_INVALID", "Threshold domain must be code or voltage")
    requested_low, requested_high = low, high
    cal = capture["calibration"]
    if domain == "voltage":
        if cal["status"] != "VALID":
            raise AnalysisError("CALIBRATION_INCONSISTENT", "Voltage thresholds require independently valid voltage calibration")
        scale = cal["code_scale_v"]
        offset = cal["effective_offset_v"]
        low = (low + offset) / scale
        high = (high + offset) / scale
    if chunk_points <= 1 or budget <= 0:
        raise AnalysisError("LIMIT_INVALID", "chunk_points must exceed 1 and scan budget must be positive")

    if scan_end is None:
        scan_end = capture["points"]
    if scan_start < 0 or scan_end > capture["points"] or scan_start >= scan_end:
        raise AnalysisError("WINDOW_OUT_OF_RANGE", "Event scan range is outside the captured record")

    samples = capture["samples"]
    edges: list[dict[str, Any]] = []
    previous_code: Optional[float] = float(samples[scan_start - 1]) if scan_start > 0 else None
    if previous_code is not None and previous_code <= low:
        state: Optional[str] = "low"
    elif previous_code is not None and previous_code >= high:
        state = "high"
    else:
        state = None
    scanned_edges = 0
    truncated = False
    for block_start in range(scan_start, scan_end, chunk_points):
        block_end = min(block_start + chunk_points, scan_end)
        values = np.asarray(samples[block_start:block_end], dtype=np.int32)
        if not values.size:
            continue
        high_indices = np.flatnonzero(values >= high)
        low_indices = np.flatnonzero(values <= low)
        if state is None:
            if values[0] <= low:
                state = "low"
            elif values[0] >= high:
                state = "high"
            previous_code = float(values[0])
            local_cursor = 1
        else:
            local_cursor = 0
        while local_cursor < len(values):
            if state == "low":
                position = int(np.searchsorted(high_indices, local_cursor, side="left"))
                event_offset = int(high_indices[position]) if position < len(high_indices) else None
                direction, threshold, next_state = "rising", high, "high"
            elif state == "high":
                position = int(np.searchsorted(low_indices, local_cursor, side="left"))
                event_offset = int(low_indices[position]) if position < len(low_indices) else None
                direction, threshold, next_state = "falling", low, "low"
            else:
                low_position = int(np.searchsorted(low_indices, local_cursor, side="left"))
                high_position = int(np.searchsorted(high_indices, local_cursor, side="left"))
                first_below = int(low_indices[low_position]) if low_position < len(low_indices) else len(values)
                first_above = int(high_indices[high_position]) if high_position < len(high_indices) else len(values)
                if first_below == len(values) and first_above == len(values):
                    previous_code = float(values[-1])
                    break
                if first_below < first_above:
                    state = "low"
                    local_cursor = first_below + 1
                    continue
                state = "high"
                local_cursor = first_above + 1
                continue
            if event_offset is None:
                previous_code = float(values[-1])
                break
            absolute_index = block_start + event_offset
            left_value = float(values[event_offset - 1]) if event_offset > 0 else (previous_code if previous_code is not None else float(values[0]))
            right_value = float(values[event_offset])
            left_index = absolute_index - 1
            event_time = _crossing_time(left_value, right_value, threshold, left_index, capture["sample_interval_s"], capture["time_origin_s"])
            if domain == "voltage":
                event_threshold: dict[str, Any] = {"low_v": requested_low, "high_v": requested_high}
                event_value = _calibrated(right_value, capture)
                unit = "V"
            else:
                event_threshold = {"low_code": low, "high_code": high}
                event_value = right_value
                unit = "code"
            edges.append(
                {
                    "detector_id": "threshold_edge_v1",
                    "type": direction,
                    "start_sample": absolute_index,
                    "end_sample": absolute_index + 1,
                    "time_s": event_time,
                    "threshold": event_threshold,
                    "value": event_value,
                    "unit": unit,
                    "evidence_quality": "threshold_crossing_linear_interpolation",
                    "window": {"start_sample": max(0, absolute_index - 16), "count": min(64, capture["points"] - max(0, absolute_index - 16))},
                }
            )
            scanned_edges += 1
            if scanned_edges >= budget:
                truncated = absolute_index < scan_end - 1
                return edges, truncated, scanned_edges
            state = next_state
            previous_code = right_value
            local_cursor = event_offset + 1
        previous_code = float(values[-1])
    return edges, truncated, scanned_edges


def _event_cursor_key(event: dict[str, Any]) -> tuple[int, str, str]:
    return int(event["start_sample"]), str(event["type"]), str(event.get("event_id", ""))


def _encode_cursor(raw_hash: str, key: tuple[int, str, str]) -> str:
    body = json.dumps({"sha256": raw_hash, "sample": key[0], "type": key[1], "event_id": key[2]}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def _decode_cursor(cursor: str, raw_hash: str) -> tuple[int, str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if data.get("sha256") != raw_hash:
            raise ValueError("cursor capture hash differs")
        return int(data["sample"]), str(data["type"]), str(data["event_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise AnalysisError("LIMIT_INVALID", f"Invalid event cursor: {exc}") from exc


def find_events(
    capture: dict[str, Any],
    *,
    low: float,
    high: float,
    domain: str = "code",
    min_pulse_s: Optional[float] = None,
    expected_period_s: Optional[float] = None,
    period_tolerance: float = 0.1,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
    max_events_scanned: int = DEFAULT_EVENT_SCAN_BUDGET,
    limit: int = DEFAULT_EVENT_PAGE,
    cursor: Optional[str] = None,
    start_time_s: Optional[float] = None,
    end_time_s: Optional[float] = None,
) -> dict[str, Any]:
    if limit <= 0 or limit > MAX_EVENT_PAGE or max_events_scanned <= 0 or max_events_scanned > MAX_EVENT_SCAN_BUDGET:
        raise AnalysisError("LIMIT_INVALID", f"limit must be 1..{MAX_EVENT_PAGE}; scan budget must be 1..{MAX_EVENT_SCAN_BUDGET}")
    if min_pulse_s is not None and (not math.isfinite(min_pulse_s) or min_pulse_s <= 0):
        raise AnalysisError("LIMIT_INVALID", "min_pulse_s must be finite and positive")
    if expected_period_s is not None and (not math.isfinite(expected_period_s) or expected_period_s <= 0):
        raise AnalysisError("LIMIT_INVALID", "expected_period_s must be finite and positive")
    if not math.isfinite(period_tolerance) or period_tolerance < 0 or period_tolerance > 1:
        raise AnalysisError("LIMIT_INVALID", "period_tolerance must be between 0 and 1")

    if (start_time_s is None) != (end_time_s is None):
        raise AnalysisError("LIMIT_INVALID", "Both start_time_s and end_time_s are required for a time-limited scan")
    if start_time_s is None:
        scan_start, scan_end = 0, capture["points"]
    else:
        scan_start, scan_end = _resolve_time_range(capture, start_time_s, end_time_s)

    edges, scan_truncated, scanned_edges = _scan_edges(
        capture,
        low,
        high,
        domain=domain,
        chunk_points=chunk_points,
        budget=max_events_scanned,
        scan_start=scan_start,
        scan_end=scan_end,
    )
    events = []
    previous_rising: Optional[dict[str, Any]] = None
    for index, edge in enumerate(edges):
        edge["event_id"] = hashlib.sha256(f"{capture['raw_sha256']}:{edge['detector_id']}:{edge['start_sample']}:{edge['type']}".encode()).hexdigest()[:24]
        events.append(edge)
        if edge["type"] == "rising":
            previous_rising = edge
        if edge["type"] == "falling":
            preceding = previous_rising
            if preceding is not None:
                width_s = edge["time_s"] - preceding["time_s"]
                if min_pulse_s is not None and width_s < min_pulse_s:
                    events.append(
                        {
                            "event_id": hashlib.sha256(f"{capture['raw_sha256']}:runt:{preceding['start_sample']}:{edge['start_sample']}".encode()).hexdigest()[:24],
                            "detector_id": "runt_pulse_v1",
                            "type": "runt_pulse",
                            "start_sample": preceding["start_sample"],
                            "end_sample": edge["start_sample"],
                            "time_start_s": preceding["time_s"],
                            "time_end_s": edge["time_s"],
                            "pulse_width_s": width_s,
                            "minimum_valid_pulse_s": min_pulse_s,
                            "evidence_quality": "hysteretic_threshold_pair",
                            "window": {"start_sample": max(0, preceding["start_sample"] - 16), "count": min(256, capture["points"] - max(0, preceding["start_sample"] - 16))},
                        }
                    )

    same_edges = [edge for edge in edges if edge["type"] == "rising"]
    intervals = [b["time_s"] - a["time_s"] for a, b in zip(same_edges, same_edges[1:])]
    expected = expected_period_s
    period_source = "explicit" if expected is not None else None
    period_status = "valid" if expected is not None else "insufficient_evidence"
    if expected is None and len(intervals) >= 3:
        expected = float(np.median(np.asarray(intervals, dtype=np.float64)))
        period_source = "median_of_observed_rising_edge_intervals"
        period_status = "valid"
    if expected is not None:
        for first, second, interval_s in zip(same_edges, same_edges[1:], intervals):
            if interval_s > expected * (1 + period_tolerance):
                missing = max(1, int(round(interval_s / expected)) - 1)
                events.append(
                    {
                        "event_id": hashlib.sha256(f"{capture['raw_sha256']}:long_interval:{first['start_sample']}:{second['start_sample']}".encode()).hexdigest()[:24],
                        "detector_id": "long_interval_v1",
                        "type": "long_interval",
                        "start_sample": first["start_sample"],
                        "end_sample": second["start_sample"],
                        "time_start_s": first["time_s"],
                        "time_end_s": second["time_s"],
                        "observed_interval_s": interval_s,
                        "expected_period_s": expected,
                        "estimated_missing_pulses": missing,
                        "period_source": period_source,
                        "tolerance_fraction": period_tolerance,
                        "evidence_quality": "edge_interval_exceeds_configured_tolerance",
                        "window": {"start_sample": max(0, first["start_sample"] - 16), "count": min(256, capture["points"] - max(0, first["start_sample"] - 16))},
                    }
                )
    events.sort(key=_event_cursor_key)
    cursor_key = _decode_cursor(cursor, capture["raw_sha256"]) if cursor else None
    candidates = [item for item in events if cursor_key is None or _event_cursor_key(item) > cursor_key]
    page = candidates[:limit]
    next_cursor = _encode_cursor(capture["raw_sha256"], _event_cursor_key(page[-1])) if len(candidates) > len(page) and page else None
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "events",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "sampling": _sampling_envelope(capture),
        "detector": {
            "id": "threshold_edge_v1",
            "status": period_status,
            "parameters": {"low": low, "high": high, "domain": domain, "min_pulse_s": min_pulse_s, "expected_period_s": expected, "period_tolerance": period_tolerance, "chunk_points": chunk_points, "max_events_scanned": max_events_scanned, "start_time_s": start_time_s, "end_time_s": end_time_s},
        },
        "events": {"total": len(events), "returned": len(page), "items": page, "next_cursor": next_cursor, "scan_truncated": scan_truncated, "page_truncated": len(candidates) > len(page), "total_is_lower_bound": scan_truncated, "scanned_edges": scanned_edges},
        "coverage": {"scanned_start": scan_start, "scanned_end_exclusive": scan_end, "scanned_start_time_s": capture["time_origin_s"] + scan_start * capture["sample_interval_s"], "scanned_end_time_s": capture["time_origin_s"] + scan_end * capture["sample_interval_s"], "full_record_scanned": scan_start == 0 and scan_end == capture["points"] and not scan_truncated, "limitations": (["transition_density_exceeds_budget"] if scan_truncated else []) + (["insufficient_period_evidence"] if period_status == "insufficient_evidence" else [])},
    }


def _structure_threshold_codes(capture: dict[str, Any], low: float, high: float, domain: str) -> tuple[float, float]:
    if domain != "voltage":
        return float(low), float(high)
    calibration = capture["calibration"]
    if calibration["status"] != "VALID":
        raise AnalysisError("CALIBRATION_INCONSISTENT", "Voltage thresholds require independently valid voltage calibration")
    scale = calibration["code_scale_v"]
    offset = calibration["effective_offset_v"]
    return (low + offset) / scale, (high + offset) / scale


def _structure_state_at(samples: Any, index: int, low_code: float, high_code: float) -> Optional[str]:
    code = float(samples[index])
    if code <= low_code:
        return "low"
    if code >= high_code:
        return "high"
    return None


def analyze_pulse_structure(
    capture: dict[str, Any],
    *,
    low: float,
    high: float,
    domain: str = "code",
    cluster_gap_s: Optional[float] = None,
    max_edges: int = DEFAULT_STRUCTURE_EDGE_LIMIT,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
    start_time_s: Optional[float] = None,
    end_time_s: Optional[float] = None,
) -> dict[str, Any]:
    """Rebuild edges, high pulses, and pulse clusters from raw samples only.

    This is the fact layer of waveform analysis. It scans every original sample
    (``stride_used == 1``) and never consumes the M4 preview, a decimated view,
    or any window/aggregate count. The edge table is complete for the scanned
    range, or the result is reported as ``UNVERIFIED`` with an explicit lower
    bound when the edge budget is exceeded; edges are never silently truncated
    into a seemingly complete table.
    """

    _require_numpy()
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise AnalysisError("LIMIT_INVALID", "Thresholds must be finite and low < high")
    if domain not in ("code", "voltage"):
        raise AnalysisError("LIMIT_INVALID", "Threshold domain must be code or voltage")
    if cluster_gap_s is not None and (not math.isfinite(cluster_gap_s) or cluster_gap_s <= 0):
        raise AnalysisError("LIMIT_INVALID", "cluster_gap_s must be finite and positive")
    if max_edges <= 0 or max_edges > MAX_STRUCTURE_EDGE_LIMIT:
        raise AnalysisError("LIMIT_INVALID", f"max_edges must be in 1..{MAX_STRUCTURE_EDGE_LIMIT}")
    if chunk_points <= 1:
        raise AnalysisError("LIMIT_INVALID", "chunk_points must exceed 1")
    if (start_time_s is None) != (end_time_s is None):
        raise AnalysisError("LIMIT_INVALID", "Both start_time_s and end_time_s are required for a time-limited scan")
    if start_time_s is None:
        scan_start, scan_end = 0, capture["points"]
    else:
        scan_start, scan_end = _resolve_time_range(capture, start_time_s, end_time_s)

    samples = capture["samples"]
    interval = capture["sample_interval_s"]
    origin = capture["time_origin_s"]
    calibration = capture["calibration"]
    voltage_domain = domain == "voltage"
    low_code, high_code = _structure_threshold_codes(capture, low, high, domain)

    raw_edges, _edge_scan_truncated, _scanned_edges = _scan_edges(
        capture,
        low,
        high,
        domain=domain,
        chunk_points=chunk_points,
        budget=max_edges + 1,
        scan_start=scan_start,
        scan_end=scan_end,
    )
    edge_budget_exceeded = len(raw_edges) > max_edges
    edge_lower_bound = len(raw_edges) if edge_budget_exceeded else None
    if edge_budget_exceeded:
        raw_edges = raw_edges[:max_edges]

    edge_items: list[dict[str, Any]] = []
    previous_same_direction: dict[str, Optional[dict[str, Any]]] = {"rising": None, "falling": None}
    for position, edge in enumerate(raw_edges):
        sample = int(edge["start_sample"])
        direction = str(edge["type"])
        before_code = int(samples[sample - 1]) if sample > 0 else None
        after_code = int(samples[sample]) if sample < capture["points"] else None
        prior = previous_same_direction[direction]
        item: dict[str, Any] = {
            "event_id": hashlib.sha256(
                f"{capture['raw_sha256']}:pulse_structure_v1:{sample}:{direction}".encode()
            ).hexdigest()[:24],
            "index": position,
            "direction": direction,
            "sample": sample,
            "time_s": float(edge["time_s"]),
            "before_code": before_code,
            "after_code": after_code,
            "threshold_code": float(high_code if direction == "rising" else low_code),
            "same_direction_interval_s": None if prior is None else float(edge["time_s"] - prior["time_s"]),
            "evidence_quality": "hysteretic_threshold_crossing_linear_interpolation",
            "time_uncertainty_s": interval,
        }
        if voltage_domain:
            item["threshold_v"] = float(high if direction == "rising" else low)
            if before_code is not None:
                item["before_v"] = _calibrated(before_code, capture)
            if after_code is not None:
                item["after_v"] = _calibrated(after_code, capture)
        edge_items.append(item)
        previous_same_direction[direction] = item

    last_scan_sample = scan_end - 1
    pulse_items: list[dict[str, Any]] = []

    def _append_pulse(
        start_sample: int,
        end_sample: int,
        *,
        status: str,
        integrity: str,
        rising_edge: Optional[dict[str, Any]],
        falling_edge: Optional[dict[str, Any]],
        boundary_flags: list[str],
        width_is_lower_bound: bool,
    ) -> None:
        region = np.asarray(samples[start_sample : end_sample + 1], dtype=np.int32)
        # Pulse times stay on the raw sample grid so sample and time always agree
        # exactly; the interpolated crossing times remain available per edge.
        start_time = origin + start_sample * interval
        end_time = origin + end_sample * interval
        pulse: dict[str, Any] = {
            "pulse_id": f"p{len(pulse_items):05d}",
            "index": len(pulse_items),
            "status": status,
            "integrity": integrity,
            "start_sample": int(start_sample),
            "end_sample": int(end_sample),
            "start_time_s": start_time,
            "end_time_s": end_time,
            # Width is derived from the sample difference so it stays exact for
            # integer sample spans instead of absorbing float cancellation in
            # (origin + n * interval) - origin.
            "width_s": (end_sample - start_sample) * interval,
            "width_is_lower_bound": bool(width_is_lower_bound),
            "start_code": int(samples[start_sample]),
            "end_code": int(samples[end_sample]),
            "peak_code": int(region.max()) if region.size else None,
            "min_code": int(region.min()) if region.size else None,
            "threshold_codes": {"low": float(low_code), "high": float(high_code)},
            "rising_edge_id": rising_edge["event_id"] if rising_edge else None,
            "falling_edge_id": falling_edge["event_id"] if falling_edge else None,
            "rising_sample": rising_edge["sample"] if rising_edge else None,
            "falling_sample": falling_edge["sample"] if falling_edge else None,
            "rising_edge_time_s": rising_edge["time_s"] if rising_edge else None,
            "falling_edge_time_s": falling_edge["time_s"] if falling_edge else None,
            "interpolated_width_s": (
                falling_edge["time_s"] - rising_edge["time_s"]
                if rising_edge is not None and falling_edge is not None
                else None
            ),
            "time_uncertainty_s": interval,
            "touches_capture_boundary": bool(boundary_flags),
            "boundary_flags": list(boundary_flags),
            "detection_resolution_s": interval,
        }
        if voltage_domain:
            pulse["peak_v"] = _calibrated(pulse["peak_code"], capture) if pulse["peak_code"] is not None else None
            pulse["min_v"] = _calibrated(pulse["min_code"], capture) if pulse["min_code"] is not None else None
        pulse_items.append(pulse)

    pending_rising: Optional[dict[str, Any]] = None
    for item in edge_items:
        if item["direction"] == "rising":
            if pending_rising is not None:
                _append_pulse(
                    pending_rising["sample"],
                    item["sample"] - 1,
                    status="INCOMPLETE",
                    integrity="rising_edge_without_observed_falling_edge",
                    rising_edge=pending_rising,
                    falling_edge=None,
                    boundary_flags=["ends_before_next_rising_edge"],
                    width_is_lower_bound=True,
                )
            pending_rising = item
            continue
        if pending_rising is None:
            if item["sample"] > scan_start:
                _append_pulse(
                    scan_start,
                    item["sample"],
                    status="INCOMPLETE",
                    integrity="high_level_at_scan_start_without_observed_rising_edge",
                    rising_edge=None,
                    falling_edge=item,
                    boundary_flags=["starts_at_scan_window_start"],
                    width_is_lower_bound=True,
                )
            continue
        _append_pulse(
            pending_rising["sample"],
            item["sample"],
            status="COMPLETE",
            integrity="rising_then_falling_pair_in_raw_order",
            rising_edge=pending_rising,
            falling_edge=item,
            boundary_flags=[],
            width_is_lower_bound=False,
        )
        pending_rising = None
    if pending_rising is not None:
        _append_pulse(
            pending_rising["sample"],
            last_scan_sample,
            status="INCOMPLETE",
            integrity="no_falling_edge_observed_before_scan_window_end",
            rising_edge=pending_rising,
            falling_edge=None,
            boundary_flags=["ends_at_scan_window_end"],
            width_is_lower_bound=True,
        )
    if not edge_items:
        state_index = scan_start - 1 if scan_start > 0 else scan_start
        if _structure_state_at(samples, state_index, low_code, high_code) == "high":
            _append_pulse(
                scan_start,
                last_scan_sample,
                status="INCOMPLETE",
                integrity="high_level_observed_for_entire_scan_without_threshold_crossing",
                rising_edge=None,
                falling_edge=None,
                boundary_flags=["starts_at_scan_window_start", "ends_at_scan_window_end"],
                width_is_lower_bound=True,
            )

    for position, pulse in enumerate(pulse_items):
        if position == 0:
            pulse["low_gap_before_s"] = None
            pulse["start_to_start_s"] = None
            continue
        previous = pulse_items[position - 1]
        pulse["low_gap_before_s"] = (pulse["start_sample"] - previous["end_sample"]) * interval
        pulse["start_to_start_s"] = (pulse["start_sample"] - previous["start_sample"]) * interval

    complete_pulses = [pulse for pulse in pulse_items if pulse["status"] == "COMPLETE"]
    incomplete_pulses = [pulse for pulse in pulse_items if pulse["status"] != "COMPLETE"]

    if cluster_gap_s is None:
        reference = complete_pulses if len(complete_pulses) >= 3 else pulse_items
        reference_starts = [pulse["start_sample"] for pulse in reference]
        if len(reference_starts) >= 3:
            observed = np.diff(np.asarray(reference_starts, dtype=np.float64)) * interval
            effective_gap_s = float(DEFAULT_CLUSTER_GAP_PERIOD_FACTOR * float(np.median(observed)))
            cluster_gap_source = "observed_median_start_to_start_interval_times_3"
        else:
            effective_gap_s = float(DEFAULT_CLUSTER_GAP_SAMPLE_INTERVALS * interval)
            cluster_gap_source = "sample_interval_times_8_fallback_without_period_evidence"
    else:
        effective_gap_s = float(cluster_gap_s)
        cluster_gap_source = "explicit_cluster_gap_s"
    if effective_gap_s <= 0:
        effective_gap_s = float(interval)
        cluster_gap_source = cluster_gap_source + "_clamped_to_one_sample_interval"

    cluster_groups: list[dict[str, Any]] = []
    for pulse in pulse_items:
        if cluster_groups:
            gap_s = (pulse["start_sample"] - cluster_groups[-1]["pulses"][-1]["end_sample"]) * interval
            if gap_s <= effective_gap_s:
                cluster_groups[-1]["gaps"].append(gap_s)
                cluster_groups[-1]["pulses"].append(pulse)
                continue
        cluster_groups.append({"pulses": [pulse], "gaps": []})

    cluster_items: list[dict[str, Any]] = []
    for position, group in enumerate(cluster_groups):
        members = group["pulses"]
        gaps = group["gaps"]
        start_sample = members[0]["start_sample"]
        end_sample = members[-1]["end_sample"]
        cluster_items.append(
            {
                "cluster_id": f"c{position:05d}",
                "index": position,
                "start_sample": start_sample,
                "end_sample": end_sample,
                "start_time_s": members[0]["start_time_s"],
                "end_time_s": members[-1]["end_time_s"],
                "duration_s": (end_sample - start_sample) * interval,
                "pulse_count": len(members),
                "complete_pulse_count": sum(1 for pulse in members if pulse["status"] == "COMPLETE"),
                "edge_count": sum(
                    (1 if pulse["rising_edge_id"] else 0) + (1 if pulse["falling_edge_id"] else 0)
                    for pulse in members
                ),
                "pulse_ids": [pulse["pulse_id"] for pulse in members[:16]],
                "pulse_ids_truncated": len(members) > 16,
                "internal_gaps_s": [float(gap) for gap in gaps[:16]],
                "internal_gaps_truncated": len(gaps) > 16,
                "gap_summary_s": {
                    "count": len(gaps),
                    "min": min(gaps) if gaps else None,
                    "median": float(np.median(gaps)) if gaps else None,
                    "max": max(gaps) if gaps else None,
                },
            }
        )

    span_s = (scan_end - scan_start) * interval
    if span_s <= 0:
        span_s = interval
    metrics: dict[str, Any] = {
        "scan_span_s": span_s,
        "edge_count": len(edge_items),
        "pulse_count": len(pulse_items),
        "complete_pulse_count": len(complete_pulses),
        "incomplete_pulse_count": len(incomplete_pulses),
        "cluster_count": len(cluster_items),
        "active_span_s": None,
        "coverage_fraction": None,
        "duty_cycle": None,
        "presence_fraction": None,
        "median_period_s": None,
        "min_pulse_width_s": None,
        "max_pulse_width_s": None,
        "max_internal_gap_s": None,
        "max_low_gap_s": None,
    }
    if complete_pulses:
        widths = [pulse["width_s"] for pulse in complete_pulses]
        active_span_s = (complete_pulses[-1]["end_sample"] - complete_pulses[0]["start_sample"]) * interval
        metrics["min_pulse_width_s"] = min(widths)
        metrics["max_pulse_width_s"] = max(widths)
        metrics["active_span_s"] = active_span_s
        metrics["coverage_fraction"] = min(1.0, max(0.0, active_span_s / span_s))
        if active_span_s > 0:
            metrics["duty_cycle"] = sum(widths) / active_span_s
        if len(complete_pulses) >= 2:
            starts = np.asarray([pulse["start_sample"] for pulse in complete_pulses], dtype=np.float64)
            metrics["median_period_s"] = float(np.median(np.diff(starts) * interval))
        internal_gaps = [gap for group in cluster_groups for gap in group["gaps"]]
        if internal_gaps:
            metrics["max_internal_gap_s"] = max(internal_gaps)
        low_gaps = [pulse["low_gap_before_s"] for pulse in complete_pulses[1:] if pulse["low_gap_before_s"] is not None]
        if low_gaps:
            metrics["max_low_gap_s"] = max(low_gaps)
    if cluster_items:
        occupied_s = sum(cluster["duration_s"] for cluster in cluster_items)
        metrics["presence_fraction"] = min(1.0, max(0.0, occupied_s / span_s))

    reasons: list[str] = []
    if edge_budget_exceeded:
        label = "insufficient_evidence"
        observation_status = "UNVERIFIED"
        reasons.append(
            f"edge_budget_exceeded: at least {edge_lower_bound} threshold crossings exist with max_edges={max_edges}, "
            "so the edge table and every downstream count are a lower bound"
        )
    elif not complete_pulses:
        if not edge_items:
            label = "no_crossing_observed"
            observation_status = "NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY"
            reasons.append(
                f"no crossing of low={low} / high={high} in {domain} domain was observed while scanning every "
                f"original sample of the requested range (resolution {interval:.6g} s)"
            )
            reasons.append("absence of observed crossings is not proof that no drive exists")
        else:
            label = "insufficient_evidence"
            observation_status = "OBSERVED"
            reasons.append(
                f"{len(edge_items)} threshold crossings were observed, but no high interval has both a rising and a "
                "falling edge inside the scanned range"
            )
    else:
        observation_status = "OBSERVED"
        if len(complete_pulses) == 1:
            label = "single_pulse"
            reasons.append(
                f"exactly one complete high interval: {complete_pulses[0]['pulse_id']} "
                f"width={complete_pulses[0]['width_s']:.6g} s"
            )
        else:
            presence_fraction = metrics["presence_fraction"] or 0.0
            coverage_fraction = metrics["coverage_fraction"] or 0.0
            duty_cycle = metrics["duty_cycle"]
            largest_cluster = max(cluster["pulse_count"] for cluster in cluster_items)
            burst_like = presence_fraction <= 0.25 and len(cluster_items) <= 3 and largest_cluster >= 2
            if burst_like:
                label = "short_burst"
                reasons.append(
                    f"presence_fraction={presence_fraction:.6f} <= 0.25 across {len(cluster_items)} cluster(s) with "
                    f"{largest_cluster} pulses in the largest cluster: high activity is confined to a short interval"
                )
            elif len(complete_pulses) >= 3 and duty_cycle is not None and duty_cycle >= 0.2 and coverage_fraction >= 0.6:
                label = "continuous_carrier"
                reasons.append(
                    f"duty_cycle={duty_cycle:.6f} >= 0.20 and coverage_fraction={coverage_fraction:.6f} >= 0.60: "
                    "the high level repeats across the record without a long absence"
                )
            elif len(complete_pulses) >= 3 and duty_cycle is not None and duty_cycle <= 0.2 and coverage_fraction >= 0.5:
                label = "low_duty_pulse_train"
                reasons.append(
                    f"duty_cycle={duty_cycle:.6f} <= 0.20 with coverage_fraction={coverage_fraction:.6f} >= 0.50: "
                    "narrow pulses repeat across the record instead of being absent"
                )
            else:
                label = "pulse_train"
                reasons.append(
                    "pulses repeat, but the duty/coverage combination matches neither a continuous carrier nor a "
                    "time-confined burst"
                )
    reasons.append(
        f"structure is derived from {len(edge_items)} raw edges and {len(pulse_items)} pulses "
        f"(complete={len(complete_pulses)}, incomplete={len(incomplete_pulses)})"
    )

    def _capped_ids(values: list[str]) -> list[str]:
        if len(values) <= 8:
            return list(values)
        return values[:4] + values[-4:]

    reference_edge_ids = _capped_ids([edge["event_id"] for edge in edge_items])
    reference_pulse_ids = _capped_ids([pulse["pulse_id"] for pulse in pulse_items])

    full_record_scanned = scan_start == 0 and scan_end == capture["points"] and not edge_budget_exceeded
    limitations: list[str] = [
        "threshold_crossing_detection_only_no_shape_inference",
        f"detection_resolution_s={interval:.6g}: features narrower than one sample interval between the two thresholds may be missed",
        "M4_preview_and_stride_subsampling_are_visualization_only_and_were_not_used",
    ]
    if edge_budget_exceeded:
        limitations.append("edge_budget_exceeded_all_counts_are_lower_bounds")
    if not full_record_scanned and not edge_budget_exceeded:
        limitations.append("scan_limited_to_requested_sub_range")
    if incomplete_pulses:
        limitations.append("capture_boundary_incomplete_pulses_reported_not_padded")
    if label == "no_crossing_observed":
        limitations.append("absence_of_crossings_does_not_prove_absence_of_drive")

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "structure",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "sampling": _sampling_envelope(capture),
        "calibration": calibration,
        "detector": {
            "id": "pulse_structure_v1",
            "status": observation_status,
            "thresholds": {
                "domain": domain,
                "requested_low": float(low),
                "requested_high": float(high),
                "low_code": float(low_code),
                "high_code": float(high_code),
                "hysteresis": "rising at high threshold, falling at low threshold",
            },
            "parameters": {
                "cluster_gap_s": effective_gap_s,
                "cluster_gap_source": cluster_gap_source,
                "max_edges": max_edges,
                "chunk_points": chunk_points,
                "start_time_s": start_time_s,
                "end_time_s": end_time_s,
            },
        },
        "edges": {
            "count": len(edge_items),
            "returned": len(edge_items),
            "count_is_lower_bound": edge_budget_exceeded,
            "lower_bound": edge_lower_bound,
            "items_truncated": edge_budget_exceeded,
            "items_complete": not edge_budget_exceeded,
            "items": edge_items,
        },
        "pulses": {
            "count": len(pulse_items),
            "returned": len(pulse_items),
            "complete_count": len(complete_pulses),
            "incomplete_count": len(incomplete_pulses),
            "status": "UNVERIFIED"
            if edge_budget_exceeded
            else ("COMPLETE" if not incomplete_pulses else "COMPLETE_WITH_INCOMPLETE_BOUNDARY_PULSES"),
            "items_truncated": edge_budget_exceeded,
            "items_complete": not edge_budget_exceeded,
            "items": pulse_items,
        },
        "pulse_clusters": {
            "count": len(cluster_items),
            "returned": len(cluster_items),
            "cluster_gap_s": effective_gap_s,
            "cluster_gap_source": cluster_gap_source,
            "status": "UNVERIFIED" if edge_budget_exceeded else "OBSERVED",
            "items_truncated": edge_budget_exceeded,
            "items_complete": not edge_budget_exceeded,
            "items": cluster_items,
        },
        "classification": {
            "label": label,
            "status": observation_status,
            "basis": reasons,
            "metrics": metrics,
            "evidence": {
                "edge_ids": reference_edge_ids,
                "pulse_ids": reference_pulse_ids,
                "sample_range": [scan_start, last_scan_sample] if edge_items or pulse_items else None,
                "edge_sample_range": [edge_items[0]["sample"], edge_items[-1]["sample"]] if edge_items else None,
            },
        },
        "evidence": {
            "raw_scan": True,
            "stride_used": 1,
            "stride_source": "original_resolution_raw_samples",
            "source_points": capture["points"],
            "scanned_points": scan_end - scan_start,
            "full_record_scanned": full_record_scanned,
            "edge_count": len(edge_items),
            "edge_count_is_lower_bound": edge_budget_exceeded,
            "edge_count_lower_bound": edge_lower_bound,
            "pulse_count": len(pulse_items),
            "complete_pulse_count": len(complete_pulses),
            "incomplete_pulse_count": len(incomplete_pulses),
            "cluster_count": len(cluster_items),
            "detection_resolution_s": interval,
            "minimum_detectable_pulse_s": interval,
            "observation_status": observation_status,
            "limitations": limitations,
        },
        "coverage": {
            "scanned_start": scan_start,
            "scanned_end_exclusive": scan_end,
            "scanned_start_time_s": origin + scan_start * interval,
            "scanned_end_time_s": origin + scan_end * interval,
            "full_record_scanned": full_record_scanned,
            "edge_scan_complete": not edge_budget_exceeded,
            "pulses_touching_capture_boundary": [
                pulse["pulse_id"] for pulse in pulse_items if pulse["touches_capture_boundary"]
            ],
            "limitations": limitations,
        },
    }


def get_window(
    capture: dict[str, Any],
    start: Optional[int] = None,
    count: Optional[int] = None,
    *,
    start_time_s: Optional[float] = None,
    end_time_s: Optional[float] = None,
    max_points: int = DEFAULT_WINDOW_POINTS,
) -> dict[str, Any]:
    if start_time_s is not None or end_time_s is not None:
        if start is not None or count is not None:
            raise AnalysisError("LIMIT_INVALID", "Use either sample indices or a time range, not both")
        start, end = _resolve_time_range(capture, start_time_s, end_time_s)
        count = end - start
        requested_start_time = start_time_s
        requested_end_time = end_time_s
    else:
        if start is None or count is None:
            raise AnalysisError("LIMIT_INVALID", "Sample window requires start and count")
        requested_start_time = capture["time_origin_s"] + start * capture["sample_interval_s"]
        requested_end_time = capture["time_origin_s"] + (start + count) * capture["sample_interval_s"]
    if start < 0 or count <= 0 or count > max_points or max_points > MAX_WINDOW_POINTS:
        raise AnalysisError("LIMIT_INVALID", f"window must have start >= 0 and count in 1..{min(max_points, MAX_WINDOW_POINTS)}")
    if start + count > capture["points"]:
        raise AnalysisError("WINDOW_OUT_OF_RANGE", f"Requested [{start}, {start + count}) exceeds {capture['points']} samples")
    codes = [int(value) for value in capture["samples"][start : start + count]]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": "window",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "sampling": _sampling_envelope(capture),
        "window": {
            "start_sample": start,
            "count": count,
            "end_sample_exclusive": start + count,
            "start_time_s": requested_start_time,
            "end_time_s": requested_end_time,
            "resolved_start_time_s": capture["time_origin_s"] + start * capture["sample_interval_s"],
            "resolved_end_time_s": capture["time_origin_s"] + (start + count) * capture["sample_interval_s"],
            "codes": codes,
        },
    }
    if capture["calibration"]["status"] == "VALID":
        result["window"]["volts"] = [_calibrated(code, capture) for code in codes]
    else:
        result["window"]["value_domain"] = "code"
        result["window"]["limitations"] = ["voltage scaling is not independently verified"]
    return result


def analyze_ringing(
    capture: dict[str, Any],
    *,
    start: Optional[int] = None,
    count: Optional[int] = None,
    start_time_s: Optional[float] = None,
    end_time_s: Optional[float] = None,
    max_points: int = DEFAULT_WINDOW_POINTS,
) -> dict[str, Any]:
    """Estimate edge overshoot and ring-down from one bounded local window.

    This is a screening measurement, not a substitute for a scope bandwidth
    or probe-quality assessment. The raw window remains available through the
    ``window`` tool when the estimate needs review.
    """

    _require_numpy()
    if start_time_s is not None or end_time_s is not None:
        if start is not None or count is not None:
            raise AnalysisError("LIMIT_INVALID", "Use either sample indices or a time range, not both")
        start, end = _resolve_time_range(capture, start_time_s, end_time_s)
        count = end - start
        requested_start_time = start_time_s
        requested_end_time = end_time_s
    else:
        if start is None or count is None:
            raise AnalysisError("LIMIT_INVALID", "Ringing analysis requires a sample window or time range")
        requested_start_time = capture["time_origin_s"] + start * capture["sample_interval_s"]
        requested_end_time = capture["time_origin_s"] + (start + count) * capture["sample_interval_s"]
    if start < 0 or count <= 0 or count > max_points or max_points > MAX_WINDOW_POINTS:
        raise AnalysisError("LIMIT_INVALID", f"ringing window must have start >= 0 and count in 1..{min(max_points, MAX_WINDOW_POINTS)}")
    if start + count > capture["points"]:
        raise AnalysisError("WINDOW_OUT_OF_RANGE", f"Requested [{start}, {start + count}) exceeds {capture['points']} samples")
    if count < 12:
        raise AnalysisError("INSUFFICIENT_DATA", "Ringing analysis requires at least 12 samples")

    raw = np.asarray(capture["samples"][start : start + count], dtype=np.float64)
    calibrated = capture["calibration"]["status"] == "VALID"
    values = raw * capture["calibration"]["code_scale_v"] - capture["calibration"]["effective_offset_v"] if calibrated else raw
    unit = "V" if calibrated else "code"
    value_domain = "voltage" if calibrated else "code"

    baseline_count = max(2, min(values.size // 4, 64))
    baseline = float(np.median(values[:baseline_count]))
    final_count = max(2, min(values.size // 4, 64))
    final_level = float(np.median(values[-final_count:]))
    step = final_level - baseline
    pre_values = values[:baseline_count]
    pre_residual = pre_values - baseline
    mad = float(np.median(np.abs(pre_residual - np.median(pre_residual)))) if pre_residual.size else 0.0
    noise_floor = max(4.0 * 1.4826 * mad, abs(step) * 0.005, 1.0 if not calibrated else abs(step) * 0.001)
    midpoint = baseline + step * 0.5
    if step > 0:
        crossings = np.flatnonzero((values[:-1] < midpoint) & (values[1:] >= midpoint)) + 1
    elif step < 0:
        crossings = np.flatnonzero((values[:-1] > midpoint) & (values[1:] <= midpoint)) + 1
    else:
        crossings = np.asarray([], dtype=np.int64)
    if crossings.size:
        edge_relative = int(crossings[0])
        edge_detection = "first_baseline_to_final_midpoint_crossing"
    else:
        differences = np.abs(np.diff(values))
        edge_relative = int(np.argmax(differences)) + 1
        edge_detection = "largest_absolute_adjacent_sample_difference_fallback"
    edge_sample = start + edge_relative
    post_values = values[edge_relative:]
    post_residual = post_values - final_level
    post_max = float(np.max(post_values))
    post_min = float(np.min(post_values))
    if step >= 0:
        overshoot = max(0.0, post_max - final_level)
        undershoot = max(0.0, final_level - post_min)
    else:
        overshoot = max(0.0, final_level - post_min)
        undershoot = max(0.0, post_max - final_level)

    peak_indices: list[int] = []
    if post_residual.size >= 3:
        derivative = np.diff(post_residual)
        turns = np.flatnonzero((derivative[:-1] >= 0) != (derivative[1:] >= 0)) + 1
        peak_indices = [int(index) for index in turns if abs(float(post_residual[index])) >= noise_floor]
    peak_amplitudes = [abs(float(post_residual[index])) for index in peak_indices]
    crossing_indices = np.flatnonzero(post_residual[:-1] * post_residual[1:] < 0) + 1 if post_residual.size >= 2 else np.asarray([], dtype=np.int64)
    crossing_indices = [int(index) for index in crossing_indices]
    period_s = None
    frequency_hz = None
    if len(crossing_indices) >= 3:
        half_period_samples = float(np.median(np.diff(np.asarray(crossing_indices, dtype=np.float64))))
        if half_period_samples > 0:
            period_s = 2.0 * half_period_samples * capture["sample_interval_s"]
            frequency_hz = 1.0 / period_s

    decay_tau_s = None
    decay_status = "insufficient_evidence"
    if len(peak_amplitudes) >= 3:
        peak_times = np.asarray([index * capture["sample_interval_s"] for index in peak_indices], dtype=np.float64)
        log_amplitudes = np.log(np.asarray(peak_amplitudes, dtype=np.float64))
        slope, _intercept = np.polyfit(peak_times, log_amplitudes, 1)
        if math.isfinite(float(slope)) and slope < 0:
            decay_tau_s = -1.0 / float(slope)
            decay_status = "estimated_exponential_envelope"
    tail_sample_count = max(2, min(post_residual.size, post_residual.size // 10))
    tail_above_noise = bool(np.median(np.abs(post_residual[-tail_sample_count:])) > noise_floor)
    capture_left_boundary = start == 0
    capture_right_boundary = start + count >= capture["points"]
    edge_near_left = edge_relative < 4
    edge_near_right = edge_relative >= count - 4
    limitations = ["heuristic_local_edge_and_ringdown_estimate", "sampling_and_probe_bandwidth_limit_physical_ringing_claims"]
    if edge_near_left:
        limitations.append("insufficient_pre_edge_context")
    if edge_near_right or tail_above_noise:
        limitations.append("ringing_tail_may_be_truncated_by_analysis_window")
    if capture_left_boundary or capture_right_boundary:
        limitations.append("analysis_window_touches_capture_boundary")

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "ringing",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "sampling": _sampling_envelope(capture),
        "calibration": capture["calibration"],
        "value_domain": value_domain,
        "unit": unit,
        "window": {
            "start_sample": start,
            "count": count,
            "end_sample_exclusive": start + count,
            "start_time_s": requested_start_time,
            "end_time_s": requested_end_time,
            "resolved_start_time_s": capture["time_origin_s"] + start * capture["sample_interval_s"],
            "resolved_end_time_s": capture["time_origin_s"] + (start + count) * capture["sample_interval_s"],
        },
        "edge": {
            "sample": edge_sample,
            "time_s": capture["time_origin_s"] + edge_sample * capture["sample_interval_s"],
            "relative_sample": edge_relative,
            "step_amplitude": step,
            "baseline": baseline,
            "final_level": final_level,
            "detection": edge_detection,
        },
        "ringing": {
            "status": "evidence_found" if len(crossing_indices) >= 3 or len(peak_amplitudes) >= 3 else "insufficient_evidence",
            "positive_overshoot": overshoot,
            "negative_undershoot": undershoot,
            "overshoot_fraction_of_step": overshoot / abs(step) if step else None,
            "post_max": post_max,
            "post_min": post_min,
            "noise_floor": noise_floor,
            "zero_crossings": len(crossing_indices),
            "significant_peaks": len(peak_amplitudes),
            "period_s": period_s,
            "frequency_hz": frequency_hz,
            "decay_tau_s": decay_tau_s,
            "decay_status": decay_status,
            "tail_above_noise": tail_above_noise,
        },
        "coverage": {
            "capture_left_boundary": capture_left_boundary,
            "capture_right_boundary": capture_right_boundary,
            "edge_near_left_boundary": edge_near_left,
            "edge_near_right_boundary": edge_near_right,
            "ringing_tail_reaches_window_end": tail_above_noise,
            "limitations": limitations,
        },
    }


def bound_json(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if max_bytes <= 0 or max_bytes > MAX_JSON_BYTES:
        raise AnalysisError("LIMIT_INVALID", f"max_json_bytes must be in 1..{MAX_JSON_BYTES}")
    result["truncated"] = False
    if len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")) <= max_bytes:
        return result
    result["truncated"] = True

    def size() -> int:
        return len(json.dumps(result, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8"))

    # Bounded list sections. Every section keeps its authoritative ``count``; a
    # shortened ``items`` list is always flagged so a bounded response can never
    # be mistaken for a complete edge/pulse/cluster table.
    sections = (
        ("events", "items", "returned"),
        ("edges", "items", "returned"),
        ("pulses", "items", "returned"),
        ("pulse_clusters", "items", "returned"),
        ("preview", "points", "selected_points"),
    )
    for section_key, list_key, counter_key in sections:
        parent = result.get(section_key)
        if not isinstance(parent, dict):
            continue
        values = parent.get(list_key)
        if not isinstance(values, list) or not values:
            continue
        is_events = section_key == "events"

        def _event_cursor(items: list[Any]) -> Optional[str]:
            # Cursor generation requires real event items and a returned counter;
            # synthetic or partially populated sections must not raise here.
            if "returned" not in parent or not items:
                return None
            last = items[-1]
            if not isinstance(last, dict) or "start_sample" not in last or "type" not in last:
                return None
            return _encode_cursor(result.get("capture", {}).get("raw_sha256", ""), _event_cursor_key(last))

        while values:
            if size() <= max_bytes:
                return result
            values.pop()
            if counter_key in parent:
                parent[counter_key] = len(values)
            if list_key == "items" and not is_events:
                parent["items_truncated"] = True
                parent["items_complete"] = False
            if is_events:
                parent["next_cursor"] = _event_cursor(values)
        if counter_key in parent:
            parent[counter_key] = len(values)
        if list_key == "items" and not is_events:
            parent["items_truncated"] = True
            parent["items_complete"] = False
        if is_events:
            parent["next_cursor"] = None
        if size() <= max_bytes:
            return result
    window = result.get("window")
    if isinstance(window, dict) and isinstance(window.get("codes"), list):
        codes = window["codes"]
        volts = window.get("volts")
        while codes:
            window["returned_count"] = len(codes)
            window["end_sample_exclusive"] = window.get("start_sample", 0) + len(codes)
            window["truncated"] = len(codes) < window.get("count", len(codes))
            if size() <= max_bytes:
                return result
            codes.pop()
            if isinstance(volts, list):
                volts.pop()
        window["returned_count"] = len(codes)
        window["end_sample_exclusive"] = window.get("start_sample", 0) + len(codes)
        window["truncated"] = len(codes) < window.get("count", len(codes))
        if size() <= max_bytes:
            return result
    raise AnalysisError("LIMIT_INVALID", "Required integrity/summary fields exceed max_json_bytes")


def error_envelope(tool: str, channel: Optional[str], error: AnalysisError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "capture": {"channel": channel} if channel else {},
        "error": {"code": error.code, "message": str(error), "reasons": error.reasons[:16]},
    }
