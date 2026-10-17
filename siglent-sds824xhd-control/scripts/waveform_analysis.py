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
DEFAULT_WINDOW_POINTS = 2_000
DEFAULT_JSON_BYTES = 256 * 1024
MAX_PREVIEW_BUCKETS = 2_000
MAX_EVENT_PAGE = 100
MAX_EVENT_SCAN_BUDGET = 20_000
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
        count = int(segment.get("requested_points", 0))
        actual_bytes = int(segment.get("actual_payload_bytes", segment.get("payload_length", -1)))
        if start != cursor or count <= 0 or actual_bytes != count * width:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"Segment continuity/size mismatch at point {cursor}")
        cursor += count
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


def _scan_edges(capture: dict[str, Any], low: float, high: float, *, domain: str, chunk_points: int, budget: int) -> tuple[list[dict[str, Any]], bool, int]:
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

    samples = capture["samples"]
    edges: list[dict[str, Any]] = []
    state: Optional[str] = None
    scanned_edges = 0
    truncated = False
    previous_code: Optional[float] = None
    for block_start in range(0, capture["points"], chunk_points):
        block_end = min(block_start + chunk_points, capture["points"])
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
                truncated = absolute_index < capture["points"] - 1
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
) -> dict[str, Any]:
    if limit <= 0 or limit > MAX_EVENT_PAGE or max_events_scanned <= 0 or max_events_scanned > MAX_EVENT_SCAN_BUDGET:
        raise AnalysisError("LIMIT_INVALID", f"limit must be 1..{MAX_EVENT_PAGE}; scan budget must be 1..{MAX_EVENT_SCAN_BUDGET}")
    if min_pulse_s is not None and (not math.isfinite(min_pulse_s) or min_pulse_s <= 0):
        raise AnalysisError("LIMIT_INVALID", "min_pulse_s must be finite and positive")
    if expected_period_s is not None and (not math.isfinite(expected_period_s) or expected_period_s <= 0):
        raise AnalysisError("LIMIT_INVALID", "expected_period_s must be finite and positive")
    if not math.isfinite(period_tolerance) or period_tolerance < 0 or period_tolerance > 1:
        raise AnalysisError("LIMIT_INVALID", "period_tolerance must be between 0 and 1")

    edges, scan_truncated, scanned_edges = _scan_edges(
        capture, low, high, domain=domain, chunk_points=chunk_points, budget=max_events_scanned
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
            "parameters": {"low": low, "high": high, "domain": domain, "min_pulse_s": min_pulse_s, "expected_period_s": expected, "period_tolerance": period_tolerance, "chunk_points": chunk_points, "max_events_scanned": max_events_scanned},
        },
        "events": {"total": len(events), "returned": len(page), "items": page, "next_cursor": next_cursor, "scan_truncated": scan_truncated, "page_truncated": len(candidates) > len(page), "total_is_lower_bound": scan_truncated, "scanned_edges": scanned_edges},
        "coverage": {"scanned_start": 0, "scanned_end_exclusive": capture["points"], "full_record_scanned": not scan_truncated, "limitations": (["transition_density_exceeds_budget"] if scan_truncated else []) + (["insufficient_period_evidence"] if period_status == "insufficient_evidence" else [])},
    }


def get_window(capture: dict[str, Any], start: int, count: int, *, max_points: int = DEFAULT_WINDOW_POINTS) -> dict[str, Any]:
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
        "window": {"start_sample": start, "count": count, "end_sample_exclusive": start + count, "codes": codes},
    }
    if capture["calibration"]["status"] == "VALID":
        result["window"]["volts"] = [_calibrated(code, capture) for code in codes]
    else:
        result["window"]["value_domain"] = "code"
        result["window"]["limitations"] = ["voltage scaling is not independently verified"]
    return result


def bound_json(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if max_bytes <= 0 or max_bytes > MAX_JSON_BYTES:
        raise AnalysisError("LIMIT_INVALID", f"max_json_bytes must be in 1..{MAX_JSON_BYTES}")
    result["truncated"] = False
    if len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")) <= max_bytes:
        return result
    result["truncated"] = True

    def size() -> int:
        return len(json.dumps(result, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8"))

    for list_path in (("events", "items"), ("preview", "points")):
        parent = result
        for key in list_path[:-1]:
            parent = parent.get(key, {})
        key = list_path[-1]
        values = parent.get(key)
        if not isinstance(values, list):
            continue
        while values:
            if key == "items" and "returned" in parent:
                parent["returned"] = len(values)
                parent["next_cursor"] = _encode_cursor(result.get("capture", {}).get("raw_sha256", ""), _event_cursor_key(values[-1]))
            if key == "points" and "selected_points" in parent:
                parent["selected_points"] = len(values)
            if size() <= max_bytes:
                return result
            values.pop()
        if key == "items" and "returned" in parent:
            parent["returned"] = len(values)
            parent["next_cursor"] = None
        if key == "points" and "selected_points" in parent:
            parent["selected_points"] = len(values)
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
