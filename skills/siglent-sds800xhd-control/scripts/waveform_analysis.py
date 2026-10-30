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

# The SCPI scalar parser lives in scope_protocol.py so capture_scope.py,
# waveform_analysis.py, and scope_protocol.py cannot drift apart. Firmware
# replies are decorated (``C1:VDIV 5.00E+00V``, ``SARA 1.00E+07Sa/s``); reading
# them with ``float()`` returns None and a left-to-right digit scan returns 1.0
# from the ``C1`` prefix. Both failure modes let the panel-snapshot cross-check
# silently skip while calibration still reported VALID.
from scope_protocol import parse_scpi_number

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
DEFAULT_REGIME_MIN_CYCLES_PER_SIDE = 5
DEFAULT_REGIME_RELATIVE_TOLERANCE = 0.08
DEFAULT_REGIME_ABSOLUTE_TOLERANCE = 0.0
DEFAULT_REGIME_TRANSITION_MARGIN_CYCLES = 1
DEFAULT_REGIME_ANOMALY_Z = 3.5
DEFAULT_REGIME_MAX_CYCLES = 5_000
DEFAULT_REGIME_MEASURES = "auto"
MAX_PREVIEW_BUCKETS = 2_000
MAX_EVENT_PAGE = 100
MAX_EVENT_SCAN_BUDGET = 20_000
MAX_STRUCTURE_EDGE_LIMIT = 200_000
MAX_WINDOW_POINTS = 2_000
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_REGIME_MIN_CYCLES_PER_SIDE = 1_000
MAX_REGIME_MAX_CYCLES = 200_000
MAX_REGIME_TRANSITION_MARGIN_CYCLES = 1_000
MAX_REGIME_UNRESOLVED_RECORDS = 2_000

REGIME_DETECTOR_ID = "robust_regime_step_v1"
REGIME_DETECTOR_VERSION = "1.0"
REGIME_CYCLE_DERIVATION = "adjacent_complete_rising_starts_on_sample_grid"
# Deterministic internal constants of the robust step detector.
_STEP_SCAN_GRID = 256
_STEP_ALTERNATIVE_CANDIDATES = 4
_STEP_FLATNESS_FRACTION = 0.4
_STEP_NOISE_SIGMA = 3.0
_STEP_UNCERTAINTY_SPAN_FACTOR = 0.5
_MAD_TO_SIGMA = 1.4826
_MODIFIED_Z_FACTOR = 0.6745
_DRIFT_MIN_FIT_QUALITY = 0.5
_DRIFT_MIN_MONOTONIC_FRACTION = 0.7


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


def _snapshot_number(snapshot: dict[str, Any], key: str) -> tuple[Optional[float], bool]:
    """Return ``(value, was_present)`` for one channel-snapshot field.

    ``was_present`` distinguishes "the manifest has no such field" from "the
    manifest has the field but it cannot be parsed". The second case must not
    silently skip the cross-check.
    """

    raw = snapshot.get(key)
    if raw is None:
        return None, False
    return parse_scpi_number(raw, default_unit="V"), True


def calibration_source(width: int, checks: list[str]) -> str:
    """Describe which reply supplied the voltage scale, for the JSON evidence."""

    if width != 1:
        return "WORD voltage scaling requires independent calibration"
    if "panel_snapshot_vdiv_overrides_descriptor" in checks:
        return "panel C<n>:VDIV?/OFST? snapshot (descriptor scale was a placeholder)"
    return "descriptor.vdiv * probe and descriptor.offset * probe"


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
    snapshot_vdiv, vdiv_present = _snapshot_number(snapshot, "vdiv")
    snapshot_offset, offset_present = _snapshot_number(snapshot, "offset")

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
    # A decorated reply that we cannot parse is a failed verification, never a
    # skipped one: SKILL.md requires the descriptor scale to be cross-checked
    # against the captured panel snapshot before voltage fields are emitted.
    if vdiv_present and snapshot_vdiv is None:
        issues.append("capture_snapshot_vdiv_unparseable")
    elif snapshot_vdiv is not None:
        if effective_vdiv is not None and math.isclose(effective_vdiv, snapshot_vdiv, rel_tol=0.02, abs_tol=1e-9):
            checks.append("descriptor_vdiv_times_probe_matches_capture_snapshot")
        else:
            # The legacy WAVEDESC can carry a placeholder scale that disagrees
            # with the panel (observed on 4.8.12.1.1.5: every channel reported
            # vdiv_with_probe=2 V/div while the panel ran 5/2/2/1 V/div). The
            # panel value is authoritative, so adopt it and record the choice.
            checks.append("panel_snapshot_vdiv_overrides_descriptor")
            effective_vdiv = snapshot_vdiv
    if offset_present and snapshot_offset is None:
        issues.append("capture_snapshot_offset_unparseable")
    elif snapshot_offset is not None:
        if effective_offset is not None and math.isclose(effective_offset, snapshot_offset, rel_tol=0.02, abs_tol=1e-9):
            checks.append("descriptor_offset_times_probe_matches_snapshot")
        else:
            checks.append("panel_snapshot_offset_overrides_descriptor")
            effective_offset = snapshot_offset

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
        "source": calibration_source(width, checks),
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
    # The descriptor reports where the downloaded slice starts inside the whole
    # record (`start`, a sample index). Ignoring it shifts every reported event
    # time by start*interval although the capture still counts as COMPLETE.
    # The window below is [-1.8, +0.2) s of the record with start=15000000; a
    # reader that drops it reports events 1.5 s too early.
    record_origin = horizontal_offset - timebase * 5.0
    record_start = _int_field(preamble.get("start"), "start", 0)
    origin = record_origin + record_start * interval
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
        "origin_formula": "horizontal_offset - timebase_s * 5 (10-division display) + start * sample_interval",
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


# ---------------------------------------------------------------------------
# Waveform regime analysis
#
# Regimes are built only from complete cycles reconstructed out of adjacent
# complete high pulses from ``analyze_pulse_structure``. Every detection step
# below is deterministic, reports its own evidence, and never derives a
# segmentation input from a preview, a stride, or a whole-record aggregate.
# ---------------------------------------------------------------------------

#: Supported per-cycle measures. Features sharing one ``dimension`` describe
#: the same physical evidence (period/frequency, code/voltage) and therefore
#: never count as independent segmentation evidence.
_REGIME_FEATURE_REGISTRY: dict[str, dict[str, Any]] = {
    "period_s": {
        "dimension": "period",
        "unit": "s",
        "value_domain": "time",
        "quantum": "sample_interval_s",
        "description": "cycle period from the sample difference between adjacent complete rising starts",
    },
    "frequency_hz": {
        "dimension": "period",
        "unit": "Hz",
        "value_domain": "time",
        "quantum": "sample_interval_s_at_observed_period",
        "description": "1/period_s; reciprocal representation of the period dimension",
    },
    "high_width_s": {
        "dimension": "high_width",
        "unit": "s",
        "value_domain": "time",
        "quantum": "sample_interval_s",
        "description": "high-pulse width from the sample-grid pulse extent (pulse.width_s), never interpolated",
    },
    "low_width_s": {
        "dimension": "low_width",
        "unit": "s",
        "value_domain": "time",
        "quantum": "sample_interval_s",
        "description": "low gap between the current pulse end sample and the next complete pulse start sample",
    },
    "duty_cycle": {
        "dimension": "duty",
        "unit": "ratio",
        "value_domain": "ratio",
        "quantum": "sample_interval_s_over_period",
        "description": "high_width_s / period_s on the sample grid",
    },
    "peak_code": {
        "dimension": "peak_code",
        "unit": "code",
        "value_domain": "code",
        "quantum": "one_code",
        "description": "maximum sample code inside the half-open cycle span",
    },
    "min_code": {
        "dimension": "min_code",
        "unit": "code",
        "value_domain": "code",
        "quantum": "one_code",
        "description": "minimum sample code inside the half-open cycle span",
    },
    "peak_to_peak_code": {
        "dimension": "peak_to_peak_code",
        "unit": "code",
        "value_domain": "code",
        "quantum": "one_code",
        "description": "peak_code - min_code inside the half-open cycle span",
    },
    "peak_v": {
        "dimension": "peak_code",
        "unit": "V",
        "value_domain": "voltage",
        "quantum": "code_scale_v",
        "requires_calibration": "VALID",
        "description": "calibrated voltage of peak_code; requires status VALID calibration",
    },
    "min_v": {
        "dimension": "min_code",
        "unit": "V",
        "value_domain": "voltage",
        "quantum": "code_scale_v",
        "requires_calibration": "VALID",
        "description": "calibrated voltage of min_code; requires status VALID calibration",
    },
    "peak_to_peak_v": {
        "dimension": "peak_to_peak_code",
        "unit": "V",
        "value_domain": "voltage",
        "quantum": "code_scale_v",
        "requires_calibration": "VALID",
        "description": "calibrated voltage of peak_to_peak_code; requires status VALID calibration",
    },
}

_REGIME_AUTO_FEATURE_ORDER = (
    "period_s",
    "duty_cycle",
    "high_width_s",
    "low_width_s",
    "peak_code",
    "min_code",
    "peak_to_peak_code",
)


def _regime_number(value: Any) -> Optional[float]:
    number = _finite_number(value)
    return None if number is None else float(number)


def _regime_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _regime_number(numerator / denominator)


def _regime_capped_ids(values: list[str], limit: int = 8) -> list[str]:
    if len(values) <= limit:
        return list(values)
    head = limit // 2
    return list(values[:head]) + list(values[-(limit - head) :])


def _build_regime_cycles(
    capture: dict[str, Any], structure: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build complete cycles from adjacent complete pulses only.

    A cycle spans ``[pulse.start_sample, next_pulse.start_sample)`` and exists
    only when *both* bounding pulses are ``COMPLETE`` (each therefore has its
    own observed rising and falling edge inside the scanned range) and they are
    adjacent in the pulse table. Pulses that are incomplete, unpaired, or
    separated by an incomplete pulse never contribute a period or width, so no
    missing edge is inferred and no boundary pulse is padded.
    """

    samples = capture["samples"]
    interval = float(capture["sample_interval_s"])
    origin = float(capture["time_origin_s"])
    calibrated = capture["calibration"]["status"] == "VALID"
    pulses = structure.get("pulses", {}).get("items", [])
    cycles: list[dict[str, Any]] = []
    incomplete_pulses: list[dict[str, Any]] = []
    unpaired_pulses: list[dict[str, Any]] = []
    for position, pulse in enumerate(pulses):
        if pulse.get("status") != "COMPLETE":
            incomplete_pulses.append(pulse)
            continue
        following = pulses[position + 1] if position + 1 < len(pulses) else None
        if following is None or following.get("status") != "COMPLETE":
            unpaired_pulses.append(pulse)
            continue
        start_sample = int(pulse["start_sample"])
        next_start = int(following["start_sample"])
        end_sample = int(pulse["end_sample"])
        if next_start <= start_sample or end_sample < start_sample or end_sample >= next_start:
            unpaired_pulses.append(pulse)
            continue
        high_width_s = float(pulse["width_s"])
        period_s = (next_start - start_sample) * interval
        low_width_s = (next_start - end_sample) * interval
        if period_s <= 0 or high_width_s < 0 or low_width_s < 0:
            unpaired_pulses.append(pulse)
            continue
        region = np.asarray(samples[start_sample:next_start], dtype=np.int32)
        if not region.size:
            unpaired_pulses.append(pulse)
            continue
        peak_code = int(region.max())
        min_code = int(region.min())
        features: dict[str, Any] = {
            "period_s": period_s,
            "frequency_hz": 1.0 / period_s,
            "high_width_s": high_width_s,
            "low_width_s": low_width_s,
            "duty_cycle": high_width_s / period_s,
            "peak_code": float(peak_code),
            "min_code": float(min_code),
            "peak_to_peak_code": float(peak_code - min_code),
        }
        if calibrated:
            features["peak_v"] = _calibrated(peak_code, capture)
            features["min_v"] = _calibrated(min_code, capture)
            features["peak_to_peak_v"] = features["peak_v"] - features["min_v"]
        cycle_index = len(cycles)
        cycles.append(
            {
                "cycle_id": f"g{cycle_index:05d}",
                "index": cycle_index,
                "start_sample": start_sample,
                "end_sample_exclusive": next_start,
                "sample_span": next_start - start_sample,
                "start_time_s": origin + start_sample * interval,
                "end_time_s": origin + next_start * interval,
                "feature_basis": "sample_grid",
                "features": features,
                "pulse_id": pulse["pulse_id"],
                "next_pulse_id": following["pulse_id"],
                "rising_edge_id": pulse.get("rising_edge_id"),
                "falling_edge_id": pulse.get("falling_edge_id"),
                "next_rising_edge_id": following.get("rising_edge_id"),
                "high_width_is_lower_bound": bool(pulse.get("width_is_lower_bound")),
                "touches_capture_boundary": bool(pulse.get("touches_capture_boundary"))
                or bool(following.get("touches_capture_boundary")),
                "source_pulse_status": [pulse.get("status"), following.get("status")],
            }
        )
    diagnostics = {
        "incomplete_pulse_count": len(incomplete_pulses),
        "incomplete_pulse_ids": _regime_capped_ids([str(pulse.get("pulse_id")) for pulse in incomplete_pulses]),
        "incomplete_pulse_windows": [
            {
                "pulse_id": pulse.get("pulse_id"),
                "status": pulse.get("status"),
                "sample_range": [int(pulse.get("start_sample", 0)), int(pulse.get("end_sample", 0))],
                "boundary_flags": list(pulse.get("boundary_flags") or []),
            }
            for pulse in incomplete_pulses[:4]
        ],
        "unpaired_complete_pulse_count": len(unpaired_pulses),
        "unpaired_complete_pulse_ids": _regime_capped_ids([str(pulse.get("pulse_id")) for pulse in unpaired_pulses]),
        "complete_pulse_count": structure.get("pulses", {}).get("complete_count"),
        "pulse_count": structure.get("pulses", {}).get("count"),
    }
    return cycles, diagnostics


def _regime_measure_plan(
    requested: Any, capture: dict[str, Any]
) -> tuple[str, list[str], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Validate requested measures and deduplicate evidence dimensions."""

    calibrated = capture["calibration"]["status"] == "VALID"
    if isinstance(requested, str):
        text = requested.strip()
        if text.lower() == "auto" or not text:
            mode = "auto"
            names: list[str] = list(_REGIME_AUTO_FEATURE_ORDER)
        else:
            mode = "explicit"
            names = [item.strip() for item in text.split(",") if item.strip()]
    elif isinstance(requested, (list, tuple)):
        mode = "explicit"
        names = [str(item).strip() for item in requested if str(item).strip()]
    else:
        raise AnalysisError("LIMIT_INVALID", "measures must be 'auto' or a list of supported feature names")
    if not names:
        raise AnalysisError("LIMIT_INVALID", "measures must contain at least one feature name")

    unknown = [name for name in names if name not in _REGIME_FEATURE_REGISTRY]
    if unknown:
        raise AnalysisError(
            "MEASURE_UNSUPPORTED",
            f"Unsupported regime measure(s): {', '.join(unknown)}",
            [
                f"unknown_measure:{name}" for name in unknown
            ]
            + [f"supported_measures:{', '.join(sorted(_REGIME_FEATURE_REGISTRY))}"],
        )

    rejected: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    ordered: list[str] = []
    dimension_owner: dict[str, str] = {}
    for name in names:
        spec = _REGIME_FEATURE_REGISTRY[name]
        if spec.get("requires_calibration") == "VALID" and not calibrated:
            unavailable.append(
                {
                    "feature": name,
                    "dimension": spec["dimension"],
                    "reason": "voltage_calibration_not_valid",
                    "detail": (
                        f"{name} needs calibration.status == VALID; "
                        f"observed status is {capture['calibration']['status']} so code-domain measures continue unaudited"
                    ),
                    "evidence": {"calibration_status": capture["calibration"]["status"]},
                }
            )
            continue
        owner = dimension_owner.get(spec["dimension"])
        if owner is not None:
            rejected.append(
                {
                    "feature": name,
                    "dimension": spec["dimension"],
                    "reason": f"duplicate_dimension_of:{owner}",
                    "detail": (
                        f"{name} and {owner} measure the same evidence dimension "
                        f"'{spec['dimension']}' and therefore cannot be independent segmentation evidence"
                    ),
                    "evidence": {"duplicate_of": owner},
                }
            )
            continue
        dimension_owner[spec["dimension"]] = name
        ordered.append(name)
    return mode, ordered, rejected, unavailable, names


def _regime_feature_resolution(
    feature: str,
    values: Any,
    capture: dict[str, Any],
    period_median: Optional[float],
) -> Optional[float]:
    """One-sample resolution of a per-cycle measure."""

    interval = float(capture["sample_interval_s"])
    spec = _REGIME_FEATURE_REGISTRY[feature]
    quantum = spec["quantum"]
    if quantum in ("sample_interval_s",):
        return interval
    if quantum == "sample_interval_s_at_observed_period":
        if not period_median or period_median <= 0:
            return None
        observed = float(np.median(np.asarray(values, dtype=np.float64)))
        if observed <= 0:
            return None
        return abs(1.0 / observed - 1.0 / (observed + interval))
    if quantum == "sample_interval_s_over_period":
        if not period_median or period_median <= 0:
            return None
        return interval / period_median
    if quantum == "one_code":
        return 1.0
    if quantum == "code_scale_v":
        scale = _finite_number(capture["calibration"].get("code_scale_v"))
        return scale if scale and scale > 0 else None
    return None


def _step_candidate(
    values: Any, segment_lo: int, segment_hi: int, split: int, single_deviance: float
) -> dict[str, Any]:
    left = values[segment_lo:split]
    right = values[split:segment_hi]
    left_median = float(np.median(left))
    right_median = float(np.median(right))
    left_mad = float(np.median(np.abs(left - left_median)))
    right_mad = float(np.median(np.abs(right - right_median)))
    loss = float(np.sum(np.abs(left - left_median)) + np.sum(np.abs(right - right_median)))
    return {
        "cycle_index": int(split),
        "segment": [int(segment_lo), int(segment_hi)],
        "left_median": left_median,
        "right_median": right_median,
        "left_mad": left_mad,
        "right_mad": right_mad,
        "loss": loss,
        "single_deviance": single_deviance,
        "loss_reduction": float(single_deviance - loss),
        "effect": abs(right_median - left_median),
    }


def _ranked_split_candidates(
    values: Any, segment_lo: int, segment_hi: int, min_side: int
) -> list[dict[str, Any]]:
    """Deterministic L1 step candidates for one segment, best first."""

    span = segment_hi - segment_lo
    if span < 2 * min_side:
        return []
    segment = values[segment_lo:segment_hi]
    single_median = float(np.median(segment))
    single_deviance = float(np.sum(np.abs(segment - single_median)))
    first = segment_lo + min_side
    last = segment_hi - min_side
    count = last - first + 1
    stride = max(1, count // _STEP_SCAN_GRID)
    grid = list(range(first, last + 1, stride))
    if grid[-1] != last:
        grid.append(last)
    scored: list[dict[str, Any]] = []
    best: Optional[dict[str, Any]] = None
    for split in grid:
        candidate = _step_candidate(values, segment_lo, segment_hi, split, single_deviance)
        scored.append(candidate)
        if best is None or candidate["loss_reduction"] > best["loss_reduction"]:
            best = candidate
    if best is None:
        return []
    # Full-resolution refinement around the best grid point only; ties keep the
    # smaller split index so the result is reproducible.
    refine_lo = max(first, best["cycle_index"] - stride)
    refine_hi = min(last, best["cycle_index"] + stride)
    for split in range(refine_lo, refine_hi + 1):
        candidate = _step_candidate(values, segment_lo, segment_hi, split, single_deviance)
        scored.append(candidate)
        if candidate["loss_reduction"] > best["loss_reduction"]:
            best = candidate
    scored.sort(key=lambda item: (-item["loss_reduction"], item["cycle_index"]))
    distinct: list[dict[str, Any]] = []
    for candidate in scored:
        if all(abs(candidate["cycle_index"] - kept["cycle_index"]) >= min_side for kept in distinct):
            distinct.append(candidate)
        if len(distinct) >= _STEP_ALTERNATIVE_CANDIDATES:
            break
    return distinct


def _step_gates(
    values: Any,
    candidate: dict[str, Any],
    *,
    threshold: float,
    resolution: float,
    minimum_effect: Optional[float] = None,
) -> dict[str, Any]:
    """Explicit, per-feature gates for a sustained step. No composite score."""

    effect = candidate["effect"]
    segment_lo, segment_hi = candidate["segment"]
    split = candidate["cycle_index"]
    required_effect = float(minimum_effect) if minimum_effect is not None else float(resolution)
    noise = _MAD_TO_SIGMA * max(candidate["left_mad"], candidate["right_mad"])
    flat_left = _regime_half_drift(values, segment_lo, split)
    flat_right = _regime_half_drift(values, split, segment_hi)
    flatness_limit = _STEP_FLATNESS_FRACTION * effect
    reasons: list[str] = []
    if effect <= 0 or effect < threshold:
        reasons.append("effect_below_tolerance")
    if resolution > 0 and effect < resolution:
        reasons.append("effect_below_resolution")
    elif required_effect > resolution and effect < required_effect:
        reasons.append("effect_below_quantization_guard")
    if noise > 0 and effect < _STEP_NOISE_SIGMA * noise:
        reasons.append("effect_within_robust_noise")
    for drift in (flat_left, flat_right):
        if drift is not None and effect > 0 and drift > flatness_limit:
            reasons.append("monotonic_drift_not_a_step")
            break
    return {
        "pass": not reasons,
        "reasons": reasons,
        "effect": effect,
        "threshold": threshold,
        "resolution": resolution,
        "minimum_effect": required_effect,
        "robust_noise": noise,
        "noise_gate": _STEP_NOISE_SIGMA * noise,
        "flatness_left": flat_left,
        "flatness_right": flat_right,
        "flatness_limit": flatness_limit,
        "flatness_fraction": _STEP_FLATNESS_FRACTION,
    }


def _regime_half_drift(values: Any, segment_lo: int, segment_hi: int) -> Optional[float]:
    span = segment_hi - segment_lo
    if span < 4:
        return None
    middle = segment_lo + span // 2
    lower = float(np.median(values[segment_lo:middle]))
    upper = float(np.median(values[middle:segment_hi]))
    return abs(upper - lower)


def _boundary_uncertainty_run(
    values: Any,
    boundary: dict[str, Any],
    *,
    min_side: int,
    resolution: float,
) -> tuple[int, int, float]:
    """Full contiguous interval of near-equivalent change-point evidence."""

    segment_lo, segment_hi = boundary["segment"]
    split = boundary["cycle_index"]
    span = segment_hi - segment_lo
    noise = _MAD_TO_SIGMA * max(boundary["left_mad"], boundary["right_mad"])
    scale = max(noise, 0.5 * resolution)
    delta = _STEP_UNCERTAINTY_SPAN_FACTOR * span * scale
    first = max(segment_lo + min_side, split - 2 * min_side)
    last = min(segment_hi - min_side, split + 2 * min_side)
    losses: dict[int, float] = {}
    for index in range(first, last + 1):
        candidate = _step_candidate(values, segment_lo, segment_hi, index, boundary["single_deviance"])
        losses[index] = candidate["loss"]
    base = losses[split]
    run_lo = split
    run_hi = split
    while run_lo - 1 >= first and losses[run_lo - 1] <= base + delta:
        run_lo -= 1
    while run_hi + 1 <= last and losses[run_hi + 1] <= base + delta:
        run_hi += 1
    return run_lo, run_hi, float(delta)


def _regime_mad(values: Any, center: float) -> float:
    if not values.size:
        return 0.0
    return float(np.median(np.abs(values - float(center))))


def _l1_deviance(values: Any) -> float:
    if not values.size:
        return 0.0
    return float(np.sum(np.abs(values - float(np.median(values)))))


def _phase_part_loss(
    values: Any, segment_lo: int, run_start: int, run_end: int, segment_hi: int
) -> tuple[float, float, float, float, float]:
    """L1 loss and the three robust medians of a three-part (left/phase/right) model."""

    left = values[segment_lo:run_start]
    phase = values[run_start:run_end]
    right = values[run_end:segment_hi]
    loss = _l1_deviance(left) + _l1_deviance(phase) + _l1_deviance(right)
    to_median = lambda part: float(np.median(part)) if part.size else float("nan")  # noqa: E731
    return loss, to_median(left), to_median(phase), to_median(right), float(
        max(
            _regime_mad(left, np.median(left)) if left.size else 0.0,
            _regime_mad(phase, np.median(phase)) if phase.size else 0.0,
            _regime_mad(right, np.median(right)) if right.size else 0.0,
        )
    )


def _refine_phase_bounds(
    values: Any, segment_lo: int, segment_hi: int, run_start: int, run_end: int, min_side: int
) -> tuple[int, int]:
    """Coordinate descent on the two phase bounds with an L1 three-part loss."""

    best = _phase_part_loss(values, segment_lo, run_start, run_end, segment_hi)[0]
    for _ in range(2):
        improved = False
        tuned_start = run_start
        for candidate in range(
            max(segment_lo + 1, run_start - min_side), min(run_end - 1, run_start + min_side) + 1
        ):
            loss = _phase_part_loss(values, segment_lo, candidate, run_end, segment_hi)[0]
            if loss < best - 1e-18:
                best, tuned_start, improved = loss, candidate, True
        run_start = tuned_start
        tuned_end = run_end
        for candidate in range(
            max(run_start + 1, run_end - min_side), min(segment_hi - 1, run_end + min_side) + 1
        ):
            loss = _phase_part_loss(values, segment_lo, run_start, candidate, segment_hi)[0]
            if loss < best - 1e-18:
                best, tuned_end, improved = loss, candidate, True
        run_end = tuned_end
        if not improved:
            break
    return run_start, run_end


def _phase_candidate_gates(
    values: Any,
    segment_lo: int,
    segment_hi: int,
    run_start: int,
    run_end: int,
    *,
    min_side: int,
    threshold: float,
    resolution: float,
    minimum_effect: float,
) -> dict[str, Any]:
    """Gates for a middle phase bracketed by two regimes. No composite score."""

    loss, left_median, phase_median, right_median, part_mad = _phase_part_loss(
        values, segment_lo, run_start, run_end, segment_hi
    )
    effect_left = phase_median - left_median
    effect_right = phase_median - right_median
    magnitude = min(abs(effect_left), abs(effect_right))
    noise = _MAD_TO_SIGMA * part_mad
    flat_left = _regime_half_drift(values, segment_lo, run_start)
    flat_phase = _regime_half_drift(values, run_start, run_end)
    flat_right = _regime_half_drift(values, run_end, segment_hi)
    flatness_limit = _STEP_FLATNESS_FRACTION * magnitude
    left_count = run_start - segment_lo
    phase_count = run_end - run_start
    right_count = segment_hi - run_end
    reasons: list[str] = []
    if effect_left * effect_right <= 0:
        reasons.append("phase_not_bracketed_by_same_level")
    if magnitude <= 0 or magnitude < threshold:
        reasons.append("effect_below_tolerance")
    if resolution > 0 and magnitude < resolution:
        reasons.append("effect_below_resolution")
    elif minimum_effect > resolution and magnitude < minimum_effect:
        reasons.append("effect_below_quantization_guard")
    if noise > 0 and magnitude < _STEP_NOISE_SIGMA * noise:
        reasons.append("effect_within_robust_noise")
    for drift in (flat_left, flat_phase, flat_right):
        if drift is not None and magnitude > 0 and drift > flatness_limit:
            reasons.append("monotonic_drift_not_a_step")
            break
    support_reasons: list[str] = []
    if phase_count < min_side:
        support_reasons.append("phase_support_below_min_cycles")
    if left_count < min_side:
        support_reasons.append("left_regime_support_below_min_cycles")
    if right_count < min_side:
        support_reasons.append("right_regime_support_below_min_cycles")
    return {
        "pass": not reasons,
        "reasons": reasons,
        "supportable": not support_reasons,
        "support_reasons": support_reasons,
        "effect": magnitude,
        "effect_left": effect_left,
        "effect_right": effect_right,
        "threshold": threshold,
        "resolution": resolution,
        "minimum_effect": minimum_effect,
        "robust_noise": noise,
        "noise_gate": _STEP_NOISE_SIGMA * noise,
        "flatness_left": flat_left,
        "flatness_phase": flat_phase,
        "flatness_right": flat_right,
        "flatness_limit": flatness_limit,
        "flatness_fraction": _STEP_FLATNESS_FRACTION,
        "left_median": left_median,
        "phase_median": phase_median,
        "right_median": right_median,
        "phase_loss": loss,
        "counts": {"left": left_count, "phase": phase_count, "right": right_count},
        "run": [int(run_start), int(run_end)],
    }


def _intermediate_phase_candidate(
    values: Any,
    segment_lo: int,
    segment_hi: int,
    *,
    min_side: int,
    threshold: float,
    resolution: float,
    minimum_effect: float,
) -> Optional[dict[str, Any]]:
    """Find a middle phase of any length bracketed by a common outer level.

    A plain two-median split cannot see a short phase between two regimes at the
    same level, because both outer sides dominate the median. This detector
    seeds on a ``min_side`` window, extends the phase by level membership, and
    refines both bounds with a three-part L1 loss.
    """

    span = segment_hi - segment_lo
    if span < 2 * min_side + 1:
        return None
    first = segment_lo + min_side
    last = segment_hi - min_side - 1
    stride = max(1, (last - first + 1) // _STEP_SCAN_GRID)
    seeds: list[tuple[float, int, int]] = []
    for start in range(first, last + 1, stride):
        end = min(start + min_side, segment_hi - min_side)
        window = values[start:end]
        if window.size < 2:
            continue
        outside = np.concatenate((values[segment_lo:start], values[end:segment_hi]))
        if outside.size < 2:
            continue
        effect = abs(float(np.median(window)) - float(np.median(outside)))
        if effect <= 0:
            continue
        seeds.append((effect, start, end))
    if not seeds:
        return None
    seeds.sort(key=lambda item: (-item[0], item[1]))
    level_tolerance = max(threshold, resolution)
    best: Optional[dict[str, Any]] = None
    for _seed_effect, start, end in seeds[:_STEP_ALTERNATIVE_CANDIDATES]:
        phase_level = float(np.median(values[start:end]))
        run_start, run_end = start, end
        while run_start - 1 >= segment_lo and abs(float(values[run_start - 1]) - phase_level) <= level_tolerance:
            run_start -= 1
        while run_end < segment_hi and abs(float(values[run_end]) - phase_level) <= level_tolerance:
            run_end += 1
        run_start, run_end = _refine_phase_bounds(values, segment_lo, segment_hi, run_start, run_end, min_side)
        if run_end - run_start < 2:
            # A single deviating cycle stays an isolated anomaly, not a phase.
            continue
        gates = _phase_candidate_gates(
            values,
            segment_lo,
            segment_hi,
            run_start,
            run_end,
            min_side=min_side,
            threshold=threshold,
            resolution=resolution,
            minimum_effect=minimum_effect,
        )
        if not gates["pass"]:
            continue
        if best is None or gates["effect"] > best["gates"]["effect"]:
            best = {
                "segment": [int(segment_lo), int(segment_hi)],
                "run": [int(run_start), int(run_end)],
                "gates": gates,
            }
    return best


def _phase_boundary_run(
    values: Any,
    segment_lo: int,
    segment_hi: int,
    run_start: int,
    run_end: int,
    *,
    which: str,
    min_side: int,
    resolution: float,
) -> tuple[int, int, float]:
    """Near-equivalent interval for one bound of an intermediate phase."""

    _loss, _left, _phase, _right, part_mad = _phase_part_loss(values, segment_lo, run_start, run_end, segment_hi)
    # L1-loss ambiguity should scale with accumulated robust noise, not record
    # length times one sample quantum. The latter makes exact synthetic steps
    # look uncertain across many cycles and can consume an entire short phase.
    scale = max(_MAD_TO_SIGMA * part_mad, 0.5 * resolution)
    delta = _STEP_UNCERTAINTY_SPAN_FACTOR * math.sqrt(max(1, segment_hi - segment_lo)) * scale
    accepted = run_start if which == "start" else run_end
    if which == "start":
        scan_lo = max(segment_lo + 1, run_start - 2 * min_side)
        scan_hi = min(run_end - 1, run_start + 2 * min_side)
        losses = {
            index: _phase_part_loss(values, segment_lo, index, run_end, segment_hi)[0]
            for index in range(scan_lo, scan_hi + 1)
        }
    else:
        scan_lo = max(run_start + 1, run_end - 2 * min_side)
        scan_hi = min(segment_hi - 1, run_end + 2 * min_side)
        losses = {
            index: _phase_part_loss(values, segment_lo, run_start, index, segment_hi)[0]
            for index in range(scan_lo, scan_hi + 1)
        }
    base = losses[accepted]
    run_lo = accepted
    run_hi = accepted
    while run_lo - 1 >= scan_lo and losses[run_lo - 1] <= base + delta:
        run_lo -= 1
    while run_hi + 1 <= scan_hi and losses[run_hi + 1] <= base + delta:
        run_hi += 1
    return run_lo, run_hi, float(delta)


def _detect_feature_boundaries(
    values: Any,
    *,
    min_side: int,
    threshold: float,
    resolution: float,
    minimum_effect: Optional[float] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Recursive robust step detection for one feature.

    Returns accepted boundaries, rejected step candidates, and middle phases
    that are real level changes but cannot be supported (or bracketed) with
    ``min_side`` complete cycles per side.
    """

    count = values.size
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    short_phases: list[dict[str, Any]] = []
    if count < 2 * min_side:
        return accepted, rejected, short_phases
    effective_minimum = float(minimum_effect) if minimum_effect is not None else float(resolution)
    stack: list[tuple[int, int]] = [(0, int(count))]
    while stack:
        segment_lo, segment_hi = stack.pop()
        if segment_hi - segment_lo < 2 * min_side:
            continue
        candidates = _ranked_split_candidates(values, segment_lo, segment_hi, min_side)
        chosen: Optional[dict[str, Any]] = None
        chosen_gates: Optional[dict[str, Any]] = None
        for candidate in candidates:
            gates = _step_gates(
                values,
                candidate,
                threshold=threshold,
                resolution=resolution,
                minimum_effect=minimum_effect,
            )
            if gates["pass"]:
                chosen = candidate
                chosen_gates = gates
                break
            if len(rejected) < 64:
                rejected.append(
                    {
                        "cycle_index": candidate["cycle_index"],
                        "segment": list(candidate["segment"]),
                        "effect": _regime_number(candidate["effect"]),
                        "threshold": _regime_number(threshold),
                        "loss": _regime_number(candidate["loss"]),
                        "reasons": gates["reasons"],
                        "flatness_left": _regime_number(gates["flatness_left"]),
                        "flatness_right": _regime_number(gates["flatness_right"]),
                    }
                )
        if chosen is not None and chosen_gates is not None:
            run_lo, run_hi, delta = _boundary_uncertainty_run(
                values, chosen, min_side=min_side, resolution=resolution
            )
            accepted.append(
                {
                    **chosen,
                    "gates": chosen_gates,
                    "threshold": threshold,
                    "resolution": resolution,
                    "uncertain_run": [int(run_lo), int(run_hi)],
                    "uncertainty_loss_threshold": _regime_number(delta),
                    "detection": "step",
                }
            )
            stack.append((chosen["cycle_index"], segment_hi))
            stack.append((segment_lo, chosen["cycle_index"]))
            continue
        phase = _intermediate_phase_candidate(
            values,
            segment_lo,
            segment_hi,
            min_side=min_side,
            threshold=threshold,
            resolution=resolution,
            minimum_effect=effective_minimum,
        )
        if phase is None:
            continue
        run_start, run_end = phase["run"]
        gates = phase["gates"]
        if not gates["supportable"]:
            short_phases.append(
                {
                    "segment": phase["segment"],
                    "run": [int(run_start), int(run_end)],
                    "counts": gates["counts"],
                    "effect": _regime_number(gates["effect"]),
                    "left_median": _regime_number(gates["left_median"]),
                    "phase_median": _regime_number(gates["phase_median"]),
                    "right_median": _regime_number(gates["right_median"]),
                    "threshold": _regime_number(threshold),
                    "reasons": list(gates["support_reasons"]),
                }
            )
            continue
        single_deviance = _l1_deviance(values[segment_lo:segment_hi])
        for which, split in (("start", run_start), ("end", run_end)):
            run_lo, run_hi, delta = _phase_boundary_run(
                values,
                segment_lo,
                segment_hi,
                run_start,
                run_end,
                which=which,
                min_side=min_side,
                resolution=resolution,
            )
            # The stable-side support rule is applied to the full uncertain
            # interval, not only its midpoint; keep at least min_side cycles
            # outside each candidate phase boundary when clamping ambiguity.
            if which == "start":
                run_lo = min(run_lo, max(segment_lo + min_side, run_start))
                run_hi = min(run_hi, max(run_lo, run_start))
            else:
                run_lo = max(run_lo, min(run_end, segment_hi - min_side))
                run_hi = max(run_hi, min(run_end, segment_hi - min_side))
            base = _step_candidate(values, segment_lo, segment_hi, split, single_deviance)
            accepted.append(
                {
                    **base,
                    "effect": float(gates["effect"]),
                    "left_median": float(gates["left_median"]),
                    "right_median": float(gates["right_median"]),
                    "gates": gates,
                    "threshold": threshold,
                    "resolution": resolution,
                    "uncertain_run": [int(run_lo), int(run_hi)],
                    "uncertainty_loss_threshold": _regime_number(delta),
                    "detection": "intermediate_phase",
                    "phase": {
                        "run": [int(run_start), int(run_end)],
                        "bound": which,
                        "counts": gates["counts"],
                    },
                }
            )
        stack.append((segment_lo, run_start))
        stack.append((run_end, segment_hi))
    accepted.sort(key=lambda item: item["cycle_index"])
    return accepted, rejected, short_phases


def _merge_feature_boundaries(
    per_feature: dict[str, list[dict[str, Any]]],
    *,
    margin: int,
    min_side: int,
    count: int,
) -> list[dict[str, Any]]:
    """Merge per-feature boundaries into transitions with explicit support."""

    windows: list[dict[str, Any]] = []
    for order, (feature, boundaries) in enumerate(per_feature.items()):
        for boundary in boundaries:
            run_lo, run_hi = boundary["uncertain_run"]
            # The change-point uncertainty interval is already expressed in
            # cycle indexes; apply the configured margin once, without an
            # additional hidden +/-1 expansion.
            window_lo = max(0, run_lo - margin)
            window_hi = min(count - 1, run_hi + margin)
            score = _regime_ratio(boundary["effect"], boundary["threshold"] if boundary["threshold"] > 0 else None)
            windows.append(
                {
                    "feature": feature,
                    "order": order,
                    "boundary": boundary,
                    "window": [window_lo, window_hi],
                    "score": score if score is not None else float("inf"),
                }
            )
    windows.sort(key=lambda item: (item["window"][0], item["window"][1], item["order"], item["boundary"]["cycle_index"]))
    clusters: list[dict[str, Any]] = []
    for item in windows:
        if clusters and item["window"][0] <= clusters[-1]["window"][1]:
            cluster = clusters[-1]
            cluster["members"].append(item)
            cluster["window"][1] = max(cluster["window"][1], item["window"][1])
        else:
            clusters.append({"window": list(item["window"]), "members": [item]})
    transitions: list[dict[str, Any]] = []
    for cluster in clusters:
        representative = min(
            cluster["members"],
            key=lambda item: (-item["score"], item["order"], item["boundary"]["cycle_index"]),
        )
        transitions.append(
            {
                "cycle_index": representative["boundary"]["cycle_index"],
                "window": list(cluster["window"]),
                "members": cluster["members"],
                "representative_feature": representative["feature"],
                "representative_boundary": representative["boundary"],
                "score": representative["score"],
            }
        )
    transitions.sort(key=lambda item: item["cycle_index"])
    # Deterministic de-duplication: whenever two kept boundaries violate the
    # configured complete-cycle support window, keep the stronger representative.
    changed = True
    while changed and transitions:
        changed = False
        previous: Optional[dict[str, Any]] = None
        for position, transition in enumerate(transitions):
            if previous is None:
                if transition["cycle_index"] < min_side:
                    transitions.pop(position)
                    changed = True
                    break
                previous = transition
                continue
            if transition["cycle_index"] - previous["cycle_index"] < min_side:
                if transition["score"] > previous["score"]:
                    transitions.remove(previous)
                else:
                    transitions.remove(transition)
                changed = True
                break
            previous = transition
        if changed:
            continue
        if transitions and count - transitions[-1]["cycle_index"] < min_side:
            transitions.pop()
            changed = True
    return transitions


def _regime_stats(values: Any) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if not array.size:
        return {"count": 0, "median": None, "mad": None, "min": None, "max": None}
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    return {
        "count": int(array.size),
        "median": _regime_number(median),
        "mad": _regime_number(mad),
        "min": _regime_number(float(array.min())),
        "max": _regime_number(float(array.max())),
    }


def _robust_slope(xs: Any, ys: Any) -> Optional[float]:
    count = ys.size
    if count < 4:
        return None
    half = count // 2
    x_low = float(np.median(xs[:half]))
    x_high = float(np.median(xs[count - half :]))
    y_low = float(np.median(ys[:half]))
    y_high = float(np.median(ys[count - half :]))
    if x_high == x_low:
        return None
    return _regime_number((y_high - y_low) / (x_high - x_low))


def _linear_fit_quality(xs: Any, ys: Any) -> Optional[float]:
    if ys.size < 3:
        return None
    try:
        slope, intercept = np.polyfit(xs, ys, 1)
    except (np.linalg.LinAlgError, ValueError):  # pragma: no cover - defensive
        return None
    predicted = slope * xs + intercept
    residual = float(np.sum((ys - predicted) ** 2))
    total = float(np.sum((ys - float(np.mean(ys))) ** 2))
    if total <= 0:
        return 1.0 if residual <= 0 else 0.0
    return _regime_number(1.0 - residual / total)


def _monotonic_fraction(values: Any) -> Optional[float]:
    if values.size < 2:
        return None
    scale = max(abs(float(np.median(values))), 1.0)
    epsilon = 1e-12 * scale
    differences = np.diff(values)
    usable = np.abs(differences) > epsilon
    if not usable.any():
        return None
    increasing = float(np.count_nonzero(differences[usable] > 0))
    decreasing = float(np.count_nonzero(differences[usable] < 0))
    return _regime_number(max(increasing, decreasing) / float(np.count_nonzero(usable)))


def _regime_trend(cycle_indexes: Any, times: Any, values: Any) -> Optional[dict[str, Any]]:
    """Slope and fit quality for one feature inside one regime."""

    if values.size < 4:
        return None
    slope_per_cycle = _robust_slope(np.asarray(cycle_indexes, dtype=np.float64), values)
    slope_per_s = _robust_slope(np.asarray(times, dtype=np.float64), values)
    fit_quality = _linear_fit_quality(np.asarray(cycle_indexes, dtype=np.float64), values)
    total_change = None
    if slope_per_cycle is not None and cycle_indexes.size >= 2:
        total_change = _regime_number(slope_per_cycle * float(cycle_indexes[-1] - cycle_indexes[0]))
    direction = None
    if slope_per_cycle is not None:
        direction = "increasing" if slope_per_cycle > 0 else ("decreasing" if slope_per_cycle < 0 else "flat")
    return {
        "slope_per_cycle": slope_per_cycle,
        "slope_per_s": slope_per_s,
        "fit_quality_r2": fit_quality,
        "total_change": total_change,
        "direction": direction,
        "monotonic_fraction": _monotonic_fraction(values),
        "basis": "robust_half_median_slope_with_least_squares_fit_quality",
    }


def analyze_waveform_regimes(
    capture: dict[str, Any],
    *,
    low: float,
    high: float,
    domain: str = "code",
    measures: Any = DEFAULT_REGIME_MEASURES,
    min_cycles_per_side: int = DEFAULT_REGIME_MIN_CYCLES_PER_SIDE,
    relative_tolerance: float = DEFAULT_REGIME_RELATIVE_TOLERANCE,
    absolute_tolerance: float = DEFAULT_REGIME_ABSOLUTE_TOLERANCE,
    transition_margin_cycles: int = DEFAULT_REGIME_TRANSITION_MARGIN_CYCLES,
    anomaly_z: float = DEFAULT_REGIME_ANOMALY_Z,
    max_edges: int = DEFAULT_STRUCTURE_EDGE_LIMIT,
    max_cycles: int = DEFAULT_REGIME_MAX_CYCLES,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
    cluster_gap_s: Optional[float] = None,
    start_time_s: Optional[float] = None,
    end_time_s: Optional[float] = None,
) -> dict[str, Any]:
    """Split an original-resolution pulse record into stable measurement regimes.

    Cycles are rebuilt from adjacent complete high pulses of
    :func:`analyze_pulse_structure`; period and low width come from sample
    differences of complete rising starts, high width uses the sample-grid
    ``width_s``, and interpolated edge times are never used for an incomplete
    pulse. Boundaries require ``min_cycles_per_side`` complete cycles on both
    sides, a configured absolute/relative effect tolerance, and a resolution
    that is not limited by one-sample quantization. Isolated cycles stay
    anomalies (robust modified-Z, default 3.5), a smooth monotonic change stays
    one regime with a trend plus an ``unresolved`` drift annotation, and
    transition-uncertain cycles are listed and excluded from stable counts.
    """

    _require_numpy()
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise AnalysisError("LIMIT_INVALID", "Thresholds must be finite and low < high")
    if domain not in ("code", "voltage"):
        raise AnalysisError("LIMIT_INVALID", "Threshold domain must be code or voltage")
    if not isinstance(min_cycles_per_side, int) or not (1 <= min_cycles_per_side <= MAX_REGIME_MIN_CYCLES_PER_SIDE):
        raise AnalysisError(
            "LIMIT_INVALID", f"min_cycles_per_side must be an integer in 1..{MAX_REGIME_MIN_CYCLES_PER_SIDE}"
        )
    if not isinstance(transition_margin_cycles, int) or not (
        0 <= transition_margin_cycles <= MAX_REGIME_TRANSITION_MARGIN_CYCLES
    ):
        raise AnalysisError(
            "LIMIT_INVALID",
            f"transition_margin_cycles must be an integer in 0..{MAX_REGIME_TRANSITION_MARGIN_CYCLES}",
        )
    if not math.isfinite(relative_tolerance) or relative_tolerance < 0 or relative_tolerance > 1:
        raise AnalysisError("LIMIT_INVALID", "relative_tolerance must be in 0..1")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0:
        raise AnalysisError("LIMIT_INVALID", "absolute_tolerance must be finite and non-negative")
    if not math.isfinite(anomaly_z) or anomaly_z <= 0:
        raise AnalysisError("LIMIT_INVALID", "anomaly_z must be finite and positive")
    if not isinstance(max_cycles, int) or not (2 <= max_cycles <= MAX_REGIME_MAX_CYCLES):
        raise AnalysisError("LIMIT_INVALID", f"max_cycles must be an integer in 2..{MAX_REGIME_MAX_CYCLES}")

    interval = float(capture["sample_interval_s"])
    origin = float(capture["time_origin_s"])
    structure = analyze_pulse_structure(
        capture,
        low=low,
        high=high,
        domain=domain,
        cluster_gap_s=cluster_gap_s,
        max_edges=max_edges,
        chunk_points=chunk_points,
        start_time_s=start_time_s,
        end_time_s=end_time_s,
    )
    edge_budget_exceeded = bool(structure["edges"].get("items_truncated")) or bool(
        structure["evidence"].get("edge_count_is_lower_bound")
    )
    cycles_all, cycle_diagnostics = _build_regime_cycles(capture, structure)
    observed_cycle_count = len(cycles_all)
    cycle_budget_exceeded = observed_cycle_count > max_cycles
    cycles = cycles_all[:max_cycles]
    analyzed_cycle_count = len(cycles)

    mode, candidate_features, rejected_measures, unavailable_measures, requested_names = _regime_measure_plan(
        measures, capture
    )

    unresolved: list[dict[str, Any]] = []
    for entry in unavailable_measures:
        unresolved.append(
            {
                "kind": "unsupported_measure",
                "feature": entry["feature"],
                "reason": entry["reason"],
                "detail": entry["detail"],
                "evidence": entry.get("evidence", {}),
                "status": "unavailable",
                "degrading": False,
            }
        )

    # ---- per-cycle feature series -----------------------------------------
    usable_features: list[str] = []
    evaluated: list[dict[str, Any]] = []
    series: dict[str, Any] = {}
    quantization_limited: list[str] = []
    period_median: Optional[float] = None
    if analyzed_cycle_count:
        period_values = np.asarray(
            [cycle["features"]["period_s"] for cycle in cycles], dtype=np.float64
        )
        period_median = float(np.median(period_values))

    for feature in candidate_features:
        spec = _REGIME_FEATURE_REGISTRY[feature]
        raw = [cycle["features"].get(feature) for cycle in cycles]
        missing = sum(1 for value in raw if value is None)
        if not analyzed_cycle_count or missing == analyzed_cycle_count:
            rejected_measures.append(
                {
                    "feature": feature,
                    "dimension": spec["dimension"],
                    "reason": "feature_unavailable_for_analyzed_cycles",
                    "detail": f"{feature} has no value for any of the {analyzed_cycle_count} analyzed complete cycles",
                    "evidence": {"missing_cycles": missing, "analyzed_cycle_count": analyzed_cycle_count},
                }
            )
            continue
        values = np.asarray([value for value in raw if value is not None], dtype=np.float64)
        stats = _regime_stats(values)
        median_value = stats["median"] or 0.0
        resolution = _regime_feature_resolution(feature, values, capture, period_median)
        threshold = max(absolute_tolerance, relative_tolerance * abs(median_value))
        entry: dict[str, Any] = {
            "feature": feature,
            "dimension": spec["dimension"],
            "unit": spec["unit"],
            "value_domain": spec["value_domain"],
            "description": spec["description"],
            "cycle_count": int(values.size),
            "missing_cycle_count": missing,
            "median": stats["median"],
            "mad": stats["mad"],
            "min": stats["min"],
            "max": stats["max"],
            "range": _regime_number(stats["max"] - stats["min"]) if stats["max"] is not None and stats["min"] is not None else None,
            "resolution": _regime_number(resolution),
            "tolerance": {
                "relative_tolerance": relative_tolerance,
                "absolute_tolerance": absolute_tolerance,
                "reference": "max(absolute_tolerance, relative_tolerance * |median|)",
                "effective": _regime_number(threshold),
            },
            "relative_variability": _regime_ratio(stats["max"] - stats["min"], abs(median_value)) if stats["max"] is not None and stats["min"] is not None else None,
        }
        usable_features.append(feature)
        series[feature] = values
        # Quantization tier: the one-sample quantum of the measure decides what
        # can be resolved at the requested tolerance. A measure whose quantum is
        # coarser than the tolerance is not discarded (a real, sustained step can
        # still be far larger than one quantum); it is flagged and additionally
        # requires the change to exceed two quantization steps so that one-step
        # sample-grid jitter can never be split into false stages.
        limited = resolution is not None and threshold > 0 and resolution > threshold
        minimum_effect = (2.0 * resolution) if (limited and resolution) else float(resolution or 0.0)
        entry["quantization"] = {
            "limited": bool(limited),
            "reason": "resolution_below_tolerance" if limited else None,
            "quantum": spec["quantum"],
            "one_sample_resolution": _regime_number(resolution),
            "tolerance": _regime_number(threshold),
            "minimum_detectable_effect": _regime_number(minimum_effect),
            "rule": (
                "one-sample resolution exceeds the requested tolerance, so an accepted boundary must exceed "
                "two quantization steps and one-step sample jitter can never create a stage"
                if limited
                else "one-sample resolution is finer than the requested tolerance"
            ),
        }
        if resolution is None:
            entry["segmentation_usable"] = False
            entry["segmentation_rejection_reason"] = "resolution_unknown"
            rejected_measures.append(
                {
                    "feature": feature,
                    "dimension": spec["dimension"],
                    "reason": "resolution_unknown",
                    "detail": f"could not derive a one-sample resolution for {feature}",
                    "evidence": {"quantum": spec["quantum"]},
                }
            )
            evaluated.append(entry)
            continue
        entry["segmentation_usable"] = True
        entry["segmentation_rejection_reason"] = "resolution_below_tolerance" if limited else None
        entry["segmentation_evidence"] = entry["quantization"]["rule"]
        evaluated.append(entry)
        if limited:
            quantization_limited.append(feature)

    detector_features = [
        entry["feature"] for entry in evaluated if entry.get("segmentation_usable")
    ]

    # ---- per-feature robust step detection --------------------------------
    per_feature_boundaries: dict[str, list[dict[str, Any]]] = {}
    per_feature_rejected: dict[str, list[dict[str, Any]]] = {}
    per_feature_short_phases: dict[str, list[dict[str, Any]]] = {}
    for feature in detector_features:
        values = series[feature]
        entry = next(item for item in evaluated if item["feature"] == feature)
        threshold = float(entry["tolerance"]["effective"] or 0.0)
        resolution = float(entry["resolution"] or 0.0)
        boundaries, rejected_candidates, short_phases = _detect_feature_boundaries(
            values,
            min_side=min_cycles_per_side,
            threshold=threshold,
            resolution=resolution,
            minimum_effect=float(entry["quantization"]["minimum_detectable_effect"] or 0.0),
        )
        per_feature_boundaries[feature] = boundaries
        per_feature_rejected[feature] = rejected_candidates
        per_feature_short_phases[feature] = short_phases

    transitions_raw = (
        _merge_feature_boundaries(
            per_feature_boundaries,
            margin=transition_margin_cycles,
            min_side=min_cycles_per_side,
            count=analyzed_cycle_count,
        )
        if analyzed_cycle_count
        else []
    )

    # ---- middle phases that are real but unsupported ----------------------
    # A level change shorter than min_cycles_per_side cannot form an accepted
    # boundary; it is reported as one unresolved short phase (never silently
    # absorbed, never exploded into one anomaly per cycle) and its cycles are
    # excluded from anomaly judging.
    short_phase_clusters: list[dict[str, Any]] = []
    for feature, phases in per_feature_short_phases.items():
        for phase in phases:
            entry = next(item for item in evaluated if item["feature"] == feature)
            target = None
            for cluster in short_phase_clusters:
                if phase["run"][0] < cluster["run"][1] and cluster["run"][0] < phase["run"][1]:
                    target = cluster
                    break
            if target is None:
                target = {
                    "run": list(phase["run"]),
                    "features": [],
                    "reasons": [],
                    "detail": {},
                }
                short_phase_clusters.append(target)
            target["run"] = [min(target["run"][0], phase["run"][0]), max(target["run"][1], phase["run"][1])]
            target["features"].append(feature)
            target["reasons"].extend(phase["reasons"])
            target["detail"][feature] = {
                "unit": entry["unit"],
                "cycle_count": phase["counts"]["phase"],
                "left_cycle_count": phase["counts"]["left"],
                "right_cycle_count": phase["counts"]["right"],
                "left_median": phase["left_median"],
                "phase_median": phase["phase_median"],
                "right_median": phase["right_median"],
                "effect": phase["effect"],
                "tolerance": phase["threshold"],
                "reasons": list(phase["reasons"]),
            }
    short_phase_clusters.sort(key=lambda item: item["run"][0])
    short_phase_cycles: set[int] = set()
    for cluster in short_phase_clusters:
        short_phase_cycles.update(range(cluster["run"][0], cluster["run"][1]))

    # ---- regime spans ------------------------------------------------------
    boundaries_indexes = [transition["cycle_index"] for transition in transitions_raw]
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary_index in boundaries_indexes:
        spans.append((start, boundary_index))
        start = boundary_index
    spans.append((start, analyzed_cycle_count))

    transitions: list[dict[str, Any]] = []
    uncertain_cycles: set[int] = set()
    transition_by_cycle: dict[int, str] = {}
    for position, transition in enumerate(transitions_raw):
        transition_id = f"t{position:05d}"
        window_lo, window_hi = transition["window"]
        left_span = spans[position]
        right_span = spans[position + 1]
        split = transition["cycle_index"]
        for cycle_index in range(window_lo, window_hi + 1):
            uncertain_cycles.add(cycle_index)
            transition_by_cycle.setdefault(cycle_index, transition_id)
        per_measure: dict[str, Any] = {}
        supporting: list[str] = []
        disagreeing: list[str] = []
        changed_measures: list[str] = []
        for feature in detector_features:
            values = series[feature]
            entry = next(item for item in evaluated if item["feature"] == feature)
            threshold = float(entry["tolerance"]["effective"] or 0.0)
            before = float(np.median(values[left_span[0] : split])) if split > left_span[0] else None
            after = float(np.median(values[split : right_span[1]])) if right_span[1] > split else None
            effect = abs(after - before) if before is not None and after is not None else None
            own = [boundary["cycle_index"] for boundary in per_feature_boundaries.get(feature, [])]
            own_inside = [index for index in own if window_lo <= index <= window_hi]
            supports = bool(own_inside) and effect is not None and effect >= threshold
            distance = None
            if own:
                nearest = min(own, key=lambda index: abs(index - split))
                distance = int(nearest - split)
            disagreement = (
                effect is not None
                and effect >= threshold
                and not supports
                and (distance is None or abs(distance) <= 2 * min_cycles_per_side + transition_margin_cycles)
            )
            if supports:
                supporting.append(feature)
            if disagreement:
                disagreeing.append(feature)
            if effect is not None and effect >= threshold:
                changed_measures.append(feature)
            per_measure[feature] = {
                "unit": entry["unit"],
                "dimension": entry["dimension"],
                "before_median": _regime_number(before),
                "after_median": _regime_number(after),
                "effect": _regime_number(effect),
                "effect_relative": _regime_ratio(effect, abs(before) if before else None),
                "threshold": _regime_number(threshold),
                "resolution": entry["resolution"],
                "own_boundary_cycle_indexes": own,
                "own_boundary_inside_uncertainty": own_inside,
                "supports_boundary": supports,
                "disagrees": bool(disagreement),
                "distance_cycles": distance,
            }
        transitions.append(
            {
                "transition_id": transition_id,
                "index": position,
                "left_regime_id": f"r{position:04d}",
                "right_regime_id": f"r{position + 1:04d}",
                "boundary": {
                    "cycle_index": split,
                    "left_cycle_id": cycles[split - 1]["cycle_id"] if split - 1 < analyzed_cycle_count else None,
                    "right_cycle_id": cycles[split]["cycle_id"] if split < analyzed_cycle_count else None,
                    "sample": int(cycles[split]["start_sample"]) if split < analyzed_cycle_count else None,
                    "time_s": float(cycles[split]["start_time_s"]) if split < analyzed_cycle_count else None,
                    "definition": "half-open: cycles[start:split] are left, cycles[split:end] are right",
                },
                "uncertainty": {
                    "cycle_index_range": [window_lo, window_hi],
                    "cycle_ids": [cycles[index]["cycle_id"] for index in range(window_lo, window_hi + 1)],
                    "cycle_count": window_hi - window_lo + 1,
                    "margin_cycles": transition_margin_cycles,
                    "basis": "contiguous_near_equivalent_l1_change_point_evidence_plus_margin",
                    "loss_threshold": transition["representative_boundary"].get("uncertainty_loss_threshold"),
                },
                "changed_measures": changed_measures,
                "per_measure": per_measure,
                "support": {
                    "rule": "explicit_or_over_selected_measures_no_composite_score",
                    "supporting_features": supporting,
                    "supporting_count": len(supporting),
                    "disagreement": {
                        "features": disagreeing,
                        "detail": [
                            {
                                "feature": feature,
                                "own_boundary_cycle_indexes": per_measure[feature]["own_boundary_cycle_indexes"],
                                "distance_cycles": per_measure[feature]["distance_cycles"],
                            }
                            for feature in disagreeing
                        ],
                    },
                },
                "effect_size": {
                    "representative_feature": transition["representative_feature"],
                    "max_relative_effect": _regime_number(
                        max(
                            (
                                value["effect_relative"]
                                for value in per_measure.values()
                                if value["effect_relative"] is not None
                            ),
                            default=None,
                        )
                    )
                    if any(value["effect_relative"] is not None for value in per_measure.values())
                    else None,
                    "measured_per_feature": {
                        feature: {
                            "effect": per_measure[feature]["effect"],
                            "effect_relative": per_measure[feature]["effect_relative"],
                            "threshold": per_measure[feature]["threshold"],
                        }
                        for feature in changed_measures
                    },
                },
                "step_evidence": {
                    "l1_loss": _regime_number(transition["representative_boundary"]["loss"]),
                    "l1_loss_reduction": _regime_number(transition["representative_boundary"]["loss_reduction"]),
                    "flatness_left": _regime_number(transition["representative_boundary"]["gates"]["flatness_left"]),
                    "flatness_right": _regime_number(transition["representative_boundary"]["gates"]["flatness_right"]),
                    "flatness_limit": _regime_number(transition["representative_boundary"]["gates"]["flatness_limit"]),
                    "robust_noise": _regime_number(transition["representative_boundary"]["gates"]["robust_noise"]),
                    "noise_gate": _regime_number(transition["representative_boundary"]["gates"]["noise_gate"]),
                },
                "confidence": "multi_feature" if len(supporting) > 1 else ("single_feature" if supporting else "unsupported"),
                "status": "accepted" if supporting else "accepted_representative_without_feature_support",
                "source": {
                    "cycle_ids": [
                        cycles[index]["cycle_id"]
                        for index in range(max(0, split - 1), min(analyzed_cycle_count, split + 1))
                    ],
                    "pulse_ids": [
                        cycles[index]["pulse_id"]
                        for index in range(max(0, split - 1), min(analyzed_cycle_count, split + 1))
                    ],
                    "rising_edge_ids": [
                        edge
                        for edge in (
                            cycles[index]["next_rising_edge_id"]
                            for index in range(max(0, split - 1), min(analyzed_cycle_count, split))
                        )
                        if edge
                    ],
                },
            }
        )
        if not supporting:
            unresolved.append(
                {
                    "kind": "ambiguous_boundary",
                    "transition_id": transition_id,
                    "feature": transition["representative_feature"],
                    "reason": "boundary_accepted_without_per_feature_support",
                    "detail": (
                        "the merged change point is retained, but no single measure both localizes it inside the "
                        "uncertainty interval and exceeds its tolerance, so support is reported as absent"
                    ),
                    "cycle_index_range": [window_lo, window_hi],
                    "sample_range": [
                        int(cycles[window_lo]["start_sample"]),
                        int(cycles[min(analyzed_cycle_count - 1, window_hi)]["end_sample_exclusive"]),
                    ],
                    "time_range_s": [
                        float(cycles[window_lo]["start_time_s"]),
                        float(cycles[min(analyzed_cycle_count - 1, window_hi)]["end_time_s"]),
                    ],
                    "status": "unresolved",
                    "degrading": True,
                }
            )

    # Short candidate phases are evidence, but fail the minimum support rule;
    # keep them distinct from both stable regimes and isolated anomalies.
    short_phase_ids: dict[int, str] = {}
    for position, cluster in enumerate(short_phase_clusters):
        phase_id = f"s{position:04d}"
        run_start, run_end = cluster["run"]
        feature_details = cluster["detail"]
        unresolved.append(
            {
                "phase_id": phase_id,
                "kind": "short_phase_insufficient_support",
                "reason": "candidate_phase_below_min_cycles_per_side",
                "detail": (
                    f"candidate phase spans cycles [{run_start}, {run_end}) but lacks the configured stable support "
                    f"of {min_cycles_per_side} complete cycles on each adjacent side; it is preserved as unresolved"
                ),
                "features": list(dict.fromkeys(cluster["features"])),
                "reasons": list(dict.fromkeys(cluster["reasons"])),
                "feature_evidence": feature_details,
                "cycle_index_range": [run_start, run_end - 1],
                "cycle_count": run_end - run_start,
                "cycle_ids": [cycles[index]["cycle_id"] for index in range(run_start, run_end)],
                "sample_range": [
                    int(cycles[run_start]["start_sample"]),
                    int(cycles[run_end - 1]["end_sample_exclusive"]),
                ] if run_end > run_start else None,
                "time_range_s": [
                    float(cycles[run_start]["start_time_s"]),
                    float(cycles[run_end - 1]["end_time_s"]),
                ] if run_end > run_start else None,
                "status": "unresolved",
                "degrading": True,
            }
        )
        for cycle_index in range(run_start, run_end):
            short_phase_ids[cycle_index] = phase_id

    # ---- regimes, trends, anomalies ---------------------------------------
    regimes: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    cycle_assignment: dict[int, dict[str, Any]] = {}
    low_support_regimes: set[int] = set()
    for position, (span_lo, span_hi) in enumerate(spans):
        regime_id = f"r{position:04d}"
        countable = [
            index
            for index in range(span_lo, span_hi)
            if index not in uncertain_cycles and index not in short_phase_ids
        ]
        unresolved_phase_in_span = [
            index for index in range(span_lo, span_hi) if index in short_phase_ids
        ]
        uncertain_in_span = [
            index for index in range(span_lo, span_hi) if index in uncertain_cycles
        ]
        stable_count = len(countable)
        bounded_by_transitions = position > 0 and position < len(transitions_raw)
        has_unresolved_phase = bool(unresolved_phase_in_span) or (
            bounded_by_transitions and stable_count < min_cycles_per_side
        )
        if stable_count >= min_cycles_per_side and not has_unresolved_phase:
            status = "stable"
        elif has_unresolved_phase:
            status = "contains_unresolved_phase"
        elif stable_count > 0:
            status = "low_stable_support"
        else:
            status = "transition_dominated"
        summaries: dict[str, Any] = {}
        drift_annotations: list[dict[str, Any]] = []
        for feature in usable_features:
            entry = next(item for item in evaluated if item["feature"] == feature)
            values = series[feature]
            subset = values[countable] if countable else np.asarray([], dtype=np.float64)
            stats = _regime_stats(subset)
            times = np.asarray([cycles[index]["start_time_s"] for index in countable], dtype=np.float64)
            cycle_indexes = np.asarray(countable, dtype=np.float64)
            trend = _regime_trend(cycle_indexes, times, subset) if subset.size >= 4 else None
            summaries[feature] = {
                "unit": entry["unit"],
                "segment_count": stats["count"],
                "median": stats["median"],
                "mad": stats["mad"],
                "min": stats["min"],
                "max": stats["max"],
                "resolution": entry["resolution"],
                "trend": trend,
                "frequency_hz": _regime_ratio(1.0, stats["median"]) if feature == "period_s" else None,
            }
            threshold = float(entry["tolerance"]["effective"] or 0.0)
            resolution = float(entry["resolution"] or 0.0)
            if trend is None or status != "stable":
                continue
            total_change = trend["total_change"]
            fit_quality = trend["fit_quality_r2"]
            monotonic = trend["monotonic_fraction"]
            if (
                total_change is not None
                and abs(total_change) >= max(threshold, resolution)
                and fit_quality is not None
                and fit_quality >= _DRIFT_MIN_FIT_QUALITY
                and monotonic is not None
                and monotonic >= _DRIFT_MIN_MONOTONIC_FRACTION
            ):
                drift_annotations.append(
                    {
                        "feature": feature,
                        "unit": entry["unit"],
                        "slope_per_cycle": trend["slope_per_cycle"],
                        "slope_per_s": trend["slope_per_s"],
                        "fit_quality_r2": fit_quality,
                        "total_change": total_change,
                        "monotonic_fraction": monotonic,
                        "tolerance": _regime_number(threshold),
                        "resolution": entry["resolution"],
                        "direction": trend["direction"],
                    }
                )
        if drift_annotations:
            primary_drift = max(
                drift_annotations,
                key=lambda item: abs(item["total_change"] or 0.0),
            )
            unresolved.append(
                {
                    "kind": "drift_trend",
                    "regime_id": regime_id,
                    "feature": primary_drift["feature"],
                    "reason": "smooth_monotonic_drift_reported_as_one_regime",
                    "detail": (
                        "smooth monotonic change inside one regime: reported as trend evidence instead of "
                        "fabricated step regimes; drifting features: "
                        + ", ".join(item["feature"] for item in drift_annotations)
                    ),
                    "features": [item["feature"] for item in drift_annotations],
                    "feature_count": len(drift_annotations),
                    "drift": drift_annotations,
                    "cycle_index_range": [countable[0], countable[-1]] if countable else None,
                    "cycle_ids": _regime_capped_ids([cycles[index]["cycle_id"] for index in countable]),
                    "sample_range": [
                        int(cycles[countable[0]]["start_sample"]),
                        int(cycles[countable[-1]]["end_sample_exclusive"]),
                    ]
                    if countable
                    else None,
                    "time_range_s": [
                        float(cycles[countable[0]]["start_time_s"]),
                        float(cycles[countable[-1]]["end_time_s"]),
                    ]
                    if countable
                    else None,
                    "evidence": {
                        "per_feature": {
                            item["feature"]: {
                                "slope_per_cycle": item["slope_per_cycle"],
                                "slope_per_s": item["slope_per_s"],
                                "fit_quality_r2": item["fit_quality_r2"],
                                "total_change": item["total_change"],
                                "monotonic_fraction": item["monotonic_fraction"],
                            }
                            for item in drift_annotations
                        }
                    },
                    "status": "unresolved",
                    "degrading": True,
                }
            )
        # Anomalies use the regime's own robust reference. Cycles inside the
        # transition uncertainty interval are never judged as anomalies. All
        # measures that trip on the same cycle are merged into one record so a
        # single abnormal cycle produces one anomaly event, not one per measure.
        regime_anomaly_by_cycle: dict[int, list[dict[str, Any]]] = {}
        anomaly_reference: dict[int, dict[str, Any]] = {}
        for feature in usable_features:
            entry = next(item for item in evaluated if item["feature"] == feature)
            values = series[feature]
            subset = values[countable] if countable else np.asarray([], dtype=np.float64)
            if subset.size < 3 or has_unresolved_phase:
                continue
            median = float(np.median(subset))
            mad = float(np.median(np.abs(subset - median)))
            scale = _MAD_TO_SIGMA * mad
            resolution = float(entry["resolution"] or 0.0)
            for cycle_index in countable:
                observed = float(values[cycle_index])
                residual = observed - median
                if scale > 0:
                    score = _MODIFIED_Z_FACTOR * residual / scale
                    if abs(score) < anomaly_z:
                        continue
                    basis = "modified_z_0.6745_median_mad"
                    reported_threshold: Optional[float] = anomaly_z
                else:
                    if resolution <= 0 or abs(residual) < resolution:
                        continue
                    score = residual / resolution
                    basis = "quantization_units_excess_deviation"
                    reported_threshold = 1.0
                regime_anomaly_by_cycle.setdefault(cycle_index, []).append(
                    {
                        "feature": feature,
                        "unit": entry["unit"],
                        "observed": _regime_number(observed),
                        "residual": _regime_number(residual),
                        "score": _regime_number(score),
                        "score_basis": basis,
                        "threshold": _regime_number(reported_threshold),
                    }
                )
                anomaly_reference[cycle_index] = {
                    "kind": "regime_median_mad",
                    "regime_id": regime_id,
                    "median": _regime_number(median),
                    "mad": _regime_number(mad),
                    "cycle_count": int(subset.size),
                }
        for cycle_index in sorted(regime_anomaly_by_cycle):
            measures = regime_anomaly_by_cycle[cycle_index]
            primary = max(
                measures,
                key=lambda item: abs(item["score"] or 0.0),
            )
            cycle = cycles[cycle_index]
            anomalies.append(
                {
                    "anomaly_id": f"a{len(anomalies):05d}",
                    "cycle_id": cycle["cycle_id"],
                    "cycle_index": cycle_index,
                    "feature": primary["feature"],
                    "unit": primary["unit"],
                    "observed": primary["observed"],
                    "residual": primary["residual"],
                    "score": primary["score"],
                    "score_basis": primary["score_basis"],
                    "threshold": primary["threshold"],
                    "measure_count": len(measures),
                    "measures": measures,
                    "reference": anomaly_reference[cycle_index],
                    "classification": "isolated_outlier_not_a_regime",
                    "sample": int(cycle["start_sample"]),
                    "time_s": float(cycle["start_time_s"]),
                    "source": {
                        "pulse_id": cycle["pulse_id"],
                        "next_pulse_id": cycle["next_pulse_id"],
                        "rising_edge_id": cycle["rising_edge_id"],
                        "next_rising_edge_id": cycle["next_rising_edge_id"],
                    },
                }
            )
        if status != "stable":
            low_support_regimes.add(position)
            unresolved.append(
                {
                    "kind": "contains_unresolved_phase" if has_unresolved_phase else ("low_stable_support" if stable_count else "transition_dominated_insufficient_support"),
                    "regime_id": regime_id,
                    "reason": "short_phase_is_not_asserted_as_stable" if has_unresolved_phase else "stable_complete_cycles_below_min_cycles_per_side",
                    "detail": (
                        f"regime {regime_id} has {stable_count} stable complete cycles after excluding "
                        f"{len(uncertain_in_span)} transition-uncertain cycles and "
                        f"{len(unresolved_phase_in_span)} unresolved-phase cycles, below min_cycles_per_side="
                        f"{min_cycles_per_side}; it is reported but never asserted as a stable regime"
                    ),
                    "cycle_index_range": [span_lo, span_hi - 1] if span_hi > span_lo else None,
                    "stable_cycle_count": stable_count,
                    "transition_uncertain_cycle_count": len(uncertain_in_span),
                    "unresolved_phase_cycle_count": len(unresolved_phase_in_span),
                    "sample_range": [
                        int(cycles[span_lo]["start_sample"]),
                        int(cycles[span_hi - 1]["end_sample_exclusive"]),
                    ]
                    if span_hi > span_lo
                    else None,
                    "time_range_s": [
                        float(cycles[span_lo]["start_time_s"]),
                        float(cycles[span_hi - 1]["end_time_s"]),
                    ]
                    if span_hi > span_lo
                    else None,
                    "status": "unresolved",
                    "degrading": True,
                }
            )
        regimes.append(
            {
                "regime_id": regime_id,
                "index": position,
                "status": status,
                "start_sample": int(cycles[span_lo]["start_sample"]) if span_hi > span_lo else None,
                "end_sample_exclusive": int(cycles[span_hi - 1]["end_sample_exclusive"]) if span_hi > span_lo else None,
                "start_time_s": float(cycles[span_lo]["start_time_s"]) if span_hi > span_lo else None,
                "end_time_s": float(cycles[span_hi - 1]["end_time_s"]) if span_hi > span_lo else None,
                "cycle_index_range": [span_lo, span_hi - 1] if span_hi > span_lo else None,
                "complete_cycle_count": max(0, span_hi - span_lo),
                "stable_cycle_count": stable_count,
                "transition_uncertain_cycle_count": len(uncertain_in_span),
                "unresolved_phase_cycle_count": len(unresolved_phase_in_span),
                "anomaly_cycle_count": len({item["cycle_index"] for item in anomalies if item["reference"]["regime_id"] == regime_id}),
                "neighbor_transition_ids": {
                    "left": transitions[position - 1]["transition_id"] if position > 0 and position - 1 < len(transitions) else None,
                    "right": transitions[position]["transition_id"] if position < len(transitions) else None,
                },
                "summaries": summaries,
                "drift": drift_annotations,
                "source": {
                    "cycle_ids": _regime_capped_ids([cycles[index]["cycle_id"] for index in range(span_lo, span_hi)]),
                    "pulse_ids": _regime_capped_ids([cycles[index]["pulse_id"] for index in range(span_lo, span_hi)]),
                    "rising_edge_ids": _regime_capped_ids(
                        [cycles[index]["rising_edge_id"] for index in range(span_lo, span_hi) if cycles[index]["rising_edge_id"]]
                    ),
                },
            }
        )
        for index in range(span_lo, span_hi):
            if index in uncertain_cycles:
                cycle_assignment[index] = {
                    "classification": "transition_uncertain",
                    "regime_id": None,
                    "transition_id": transition_by_cycle.get(index),
                }
            elif index in short_phase_ids:
                cycle_assignment[index] = {
                    "classification": "unresolved_phase",
                    "regime_id": None,
                    "phase_id": short_phase_ids[index],
                    "transition_id": None,
                }
            elif status == "stable":
                cycle_assignment[index] = {"classification": "stable", "regime_id": regime_id, "transition_id": None}
            else:
                cycle_assignment[index] = {
                    "classification": "unresolved_phase",
                    "regime_id": regime_id,
                    "transition_id": None,
                }

    # ---- cycle records -----------------------------------------------------
    anomaly_flags: dict[int, list[dict[str, Any]]] = {}
    for item in anomalies:
        anomaly_flags.setdefault(item["cycle_index"], []).append(
            {
                "anomaly_id": item["anomaly_id"],
                "features": [measure["feature"] for measure in item["measures"]],
                "primary_feature": item["feature"],
                "primary_score": item["score"],
            }
        )
    cycle_items: list[dict[str, Any]] = []
    for cycle in cycles:
        index = cycle["index"]
        assigned = cycle_assignment.get(index, {"classification": "unassigned", "regime_id": None, "transition_id": None})
        cycle_items.append(
            {
                "cycle_id": cycle["cycle_id"],
                "index": index,
                "start_sample": cycle["start_sample"],
                "end_sample_exclusive": cycle["end_sample_exclusive"],
                "start_time_s": cycle["start_time_s"],
                "end_time_s": cycle["end_time_s"],
                "sample_span": cycle["sample_span"],
                "feature_basis": cycle["feature_basis"],
                "features": {
                    feature: _regime_number(cycle["features"][feature])
                    for feature in usable_features
                    if feature in cycle["features"]
                },
                "classification": assigned["classification"],
                "regime_id": assigned["regime_id"],
                "transition_id": assigned["transition_id"],
                "phase_id": assigned.get("phase_id"),
                "transition_uncertain": assigned["classification"] == "transition_uncertain",
                "anomalies": anomaly_flags.get(index, []),
                "source": {
                    "pulse_id": cycle["pulse_id"],
                    "next_pulse_id": cycle["next_pulse_id"],
                    "rising_edge_id": cycle["rising_edge_id"],
                    "next_rising_edge_id": cycle["next_rising_edge_id"],
                },
            }
        )

    # ---- measures report ---------------------------------------------------
    selected: list[dict[str, Any]] = []
    for entry in evaluated:
        feature = entry["feature"]
        supporting_transitions = [
            transition["transition_id"]
            for transition in transitions
            if feature in transition["support"]["supporting_features"]
        ]
        own_boundaries = [boundary["cycle_index"] for boundary in per_feature_boundaries.get(feature, [])]
        rejected_candidates = per_feature_rejected.get(feature, [])
        entry["own_boundary_cycle_indexes"] = own_boundaries
        entry["change_evidence"] = {
            "boundaries_detected": len(own_boundaries),
            "strongest_effect": _regime_number(
                max((boundary["effect"] for boundary in per_feature_boundaries.get(feature, [])), default=None)
            )
            if own_boundaries
            else None,
            "rejected_candidate_count": len(rejected_candidates),
            "rejected_candidates": rejected_candidates[:4],
            "selected_for_segmentation": bool(supporting_transitions),
        }
        if supporting_transitions:
            entry["reason"] = "supported_accepted_boundary"
            entry["supports_transition_ids"] = supporting_transitions
            selected.append(
                {
                    "feature": feature,
                    "dimension": entry["dimension"],
                    "unit": entry["unit"],
                    "reason": "supported_accepted_boundary",
                    "supports_transition_ids": supporting_transitions,
                    "boundary_cycle_indexes": own_boundaries,
                    "evidence": {
                        "median": entry["median"],
                        "resolution": entry["resolution"],
                        "tolerance": entry["tolerance"]["effective"],
                        "strongest_effect": entry["change_evidence"]["strongest_effect"],
                    },
                }
            )
        else:
            if own_boundaries:
                entry["reason"] = "own_boundary_superseded_by_merged_transition"
            elif rejected_candidates:
                entry["reason"] = "candidate_change_rejected:" + ",".join(
                    sorted({reason for candidate in rejected_candidates for reason in candidate["reasons"]})
                )
            else:
                entry["reason"] = "stable_no_change_evidence"
            entry["supports_transition_ids"] = []

    # Quantization bookkeeping: a measure whose one-sample quantum is coarser
    # than the requested tolerance is only reported as rejected when nothing in
    # the record could be resolved with it. When it still supports an accepted
    # boundary the change is above the quantum and is not jitter, so the measure
    # stays evaluated/selected with an explicit quantization note.
    for feature in quantization_limited:
        entry = next(item for item in evaluated if item["feature"] == feature)
        selected_for_segmentation = bool(entry.get("supports_transition_ids"))
        entry["quantization"]["selected_for_segmentation"] = selected_for_segmentation
        if not selected_for_segmentation:
            rejected_measures.append(
                {
                    "feature": feature,
                    "dimension": entry["dimension"],
                    "reason": "resolution_below_tolerance",
                    "detail": entry["quantization"]["rule"],
                    "evidence": {
                        "resolution": entry["resolution"],
                        "tolerance": entry["quantization"]["tolerance"],
                        "median": entry["median"],
                        "minimum_detectable_effect": entry["quantization"]["minimum_detectable_effect"],
                    },
                }
            )
        unresolved.append(
            {
                "kind": "measure_resolution_limited",
                "feature": feature,
                "reason": "resolution_below_tolerance",
                "detail": (
                    f"one-sample resolution {entry['resolution']} {entry['unit']} exceeds the "
                    f"{entry['quantization']['tolerance']} {entry['unit']} tolerance, so a boundary from this "
                    "measure must exceed two quantization steps"
                ),
                "evidence": {
                    "resolution": entry["resolution"],
                    "tolerance": entry["quantization"]["tolerance"],
                    "quantum": entry["quantization"]["quantum"],
                    "minimum_detectable_effect": entry["quantization"]["minimum_detectable_effect"],
                    "selected_for_segmentation": selected_for_segmentation,
                    "supports_transition_ids": entry.get("supports_transition_ids") or [],
                },
                "status": "informational" if selected_for_segmentation else "unresolved",
                "degrading": False,
            }
        )

    measures_section = {
        "mode": mode,
        "requested": requested_names,
        "selected": selected,
        "selected_count": len(selected),
        "evaluated": evaluated,
        "evaluated_count": len(evaluated),
        "rejected": rejected_measures,
        "unavailable": unavailable_measures,
        "detector_features_used": detector_features,
        "dimension_rule": "features sharing a dimension (period/frequency, code/voltage) are one evidence channel",
    }

    # ---- reconciliation and integrity -------------------------------------
    stable_cycles = sum(1 for item in cycle_items if item["classification"] == "stable")
    uncertain_cycle_count = sum(1 for item in cycle_items if item["classification"] == "transition_uncertain")
    unresolved_phase_cycles = sum(1 for item in cycle_items if item["classification"] == "unresolved_phase")
    unassigned_cycles = analyzed_cycle_count - stable_cycles - uncertain_cycle_count - unresolved_phase_cycles
    reconciliation_total = stable_cycles + uncertain_cycle_count + unresolved_phase_cycles + unassigned_cycles
    reconciles = reconciliation_total == analyzed_cycle_count
    if cycle_diagnostics["incomplete_pulse_count"] or cycle_diagnostics["unpaired_complete_pulse_count"]:
        excluded_window = (
            cycles_all[0]["start_sample"] if cycles_all else None
        )
        unresolved.append(
            {
                "kind": "incomplete_boundary_cycles",
                "reason": "capture_boundary_or_unpaired_pulses_do_not_form_complete_cycles",
                "detail": (
                    f"{cycle_diagnostics['incomplete_pulse_count']} incomplete pulse(s) and "
                    f"{cycle_diagnostics['unpaired_complete_pulse_count']} unpaired complete pulse(s) were excluded "
                    "from cycle construction; no width, period, or edge is inferred for them"
                ),
                "evidence": cycle_diagnostics,
                "sample_range": [excluded_window, int(capture["points"]) - 1] if excluded_window is not None else None,
                "status": "informational",
                "degrading": False,
            }
        )
    if cycle_budget_exceeded:
        unresolved.append(
            {
                "kind": "cycle_budget_exceeded",
                "reason": "max_cycles_budget_reached",
                "detail": (
                    f"{observed_cycle_count} complete cycles were observed but only the first {max_cycles} were "
                    "analyzed; the reported segmentation is a prefix of the record, not a complete partition"
                ),
                "evidence": {
                    "observed_complete_cycle_count": observed_cycle_count,
                    "analyzed_cycle_count": analyzed_cycle_count,
                    "max_cycles": max_cycles,
                },
                "status": "unresolved",
                "degrading": True,
            }
        )
    if edge_budget_exceeded:
        unresolved.append(
            {
                "kind": "edge_budget_exceeded",
                "reason": "max_edges_budget_reached",
                "detail": (
                    f"the edge table reached max_edges={max_edges}, so the edge, pulse, and cycle tables are lower "
                    "bounds and the segmentation covers only the analyzed prefix"
                ),
                "evidence": {
                    "edge_count": structure["edges"].get("count"),
                    "edge_lower_bound": structure["edges"].get("lower_bound"),
                    "max_edges": max_edges,
                },
                "status": "unresolved",
                "degrading": True,
            }
        )
    if observed_cycle_count and analyzed_cycle_count < 2 * min_cycles_per_side:
        unresolved.append(
            {
                "kind": "insufficient_cycles",
                "reason": "fewer_complete_cycles_than_required_support",
                "detail": (
                    f"only {analyzed_cycle_count} complete cycle(s) are available; at least "
                    f"{2 * min_cycles_per_side} are needed to test a boundary with "
                    f"min_cycles_per_side={min_cycles_per_side}"
                ),
                "evidence": {"analyzed_cycle_count": analyzed_cycle_count},
                "status": "unresolved",
                "degrading": True,
            }
        )
    unresolved = unresolved[:MAX_REGIME_UNRESOLVED_RECORDS]
    for position, entry in enumerate(unresolved):
        entry["unresolved_id"] = f"u{position:05d}"

    degrading_unresolved = [entry for entry in unresolved if entry.get("degrading")]
    if not reconciles:
        data_integrity_status = "INVALID"
    elif edge_budget_exceeded or cycle_budget_exceeded:
        data_integrity_status = "UNVERIFIED"
    else:
        data_integrity_status = str(capture.get("integrity", {}).get("status", "COMPLETE"))
        if data_integrity_status not in {"COMPLETE", "INCOMPLETE", "INVALID", "UNVERIFIED", "UNSUPPORTED"}:
            data_integrity_status = "UNVERIFIED"
    if edge_budget_exceeded or cycle_budget_exceeded:
        segmentation_status = "UNVERIFIED"
    elif analyzed_cycle_count == 0 or not detector_features:
        segmentation_status = "UNSUPPORTED"
    elif degrading_unresolved:
        segmentation_status = "INCOMPLETE"
    else:
        segmentation_status = "COMPLETE"
    overall_status = (
        "INVALID" if data_integrity_status == "INVALID" else
        "UNVERIFIED" if "UNVERIFIED" in (data_integrity_status, segmentation_status) else
        "INCOMPLETE" if "INCOMPLETE" in (data_integrity_status, segmentation_status) else
        "UNSUPPORTED" if "UNSUPPORTED" in (data_integrity_status, segmentation_status) else
        "COMPLETE"
    )
    # Keep the legacy field at the data-artifact layer: a fully captured ramp is
    # data COMPLETE even when its discrete regime interpretation is unresolved.
    integrity_status = data_integrity_status

    limitations: list[str] = [
        "regimes_are_built_only_from_raw_original_resolution_pulses",
        "cycle_features_use_sample_grid_values_never_interpolated_boundary_widths",
        "no_missing_edge_or_pulse_is_inferred_at_capture_boundaries",
        "quantization_limits_detectable_change_one_sample_resolution_is_reported_per_measure",
    ]
    if edge_budget_exceeded:
        limitations.append("edge_budget_exceeded_all_cycle_counts_are_lower_bounds_and_the_segmentation_is_a_prefix")
    if cycle_budget_exceeded:
        limitations.append("cycle_budget_exceeded_segmentation_covers_analyzed_prefix_only")
    if not structure["evidence"].get("full_record_scanned", False):
        limitations.append("scan_limited_to_requested_sub_range")
    if not detector_features:
        limitations.append("no_feature_could_support_segmentation")
    if any(entry["kind"] == "drift_trend" for entry in unresolved):
        limitations.append("monotonic_drift_is_trend_evidence_not_a_step_regime")
    if any(entry["kind"] == "measure_resolution_limited" for entry in unresolved):
        limitations.append("some_measures_are_quantization_limited_and_were_not_used_for_boundaries")
    if transitions:
        limitations.append("transition_uncertain_cycles_are_excluded_from_stable_regime_counts")

    coverage = {
        "source_sha256": capture["raw_sha256"],
        "raw_scan": True,
        "stride_used": 1,
        "stride_source": "original_resolution_raw_samples",
        "source_points": capture["points"],
        "scanned_start": structure["coverage"]["scanned_start"],
        "scanned_end_exclusive": structure["coverage"]["scanned_end_exclusive"],
        "scanned_start_time_s": structure["coverage"]["scanned_start_time_s"],
        "scanned_end_time_s": structure["coverage"]["scanned_end_time_s"],
        "full_record_scanned": bool(structure["coverage"]["full_record_scanned"]),
        "point_count": capture["points"],
        "sampled_point_count": structure["evidence"].get("scanned_points"),
        "edge_count": structure["edges"].get("count"),
        "edge_count_is_lower_bound": edge_budget_exceeded,
        "edge_count_lower_bound": structure["edges"].get("lower_bound"),
        "pulse_count": structure["pulses"].get("count"),
        "complete_pulse_count": structure["pulses"].get("complete_count"),
        "incomplete_pulse_count": structure["pulses"].get("incomplete_count"),
        "complete_cycle_count": observed_cycle_count,
        "complete_cycle_count_is_lower_bound": edge_budget_exceeded,
        "analyzed_cycle_count": analyzed_cycle_count,
        "unanalyzed_cycle_count": max(0, observed_cycle_count - analyzed_cycle_count),
        "stable_cycle_count": stable_cycles,
        "transition_uncertain_cycle_count": uncertain_cycle_count,
        "unresolved_phase_cycle_count": unresolved_phase_cycles,
        "unassigned_cycle_count": unassigned_cycles,
        "anomaly_record_count": len(anomalies),
        "anomaly_cycle_count": len({item["cycle_index"] for item in anomalies}),
        "regime_count": len(regimes),
        "transition_count": len(transitions),
        "boundary_incomplete_pulses": cycle_diagnostics["incomplete_pulse_windows"],
        "boundary_incomplete_pulse_ids": cycle_diagnostics["incomplete_pulse_ids"],
        "budgets": {
            "max_edges": max_edges,
            "max_cycles": max_cycles,
            "edge_budget_exceeded": edge_budget_exceeded,
            "cycle_budget_exceeded": cycle_budget_exceeded,
        },
        "segmentation_scope": "full_analyzed_range" if not (edge_budget_exceeded or cycle_budget_exceeded) else "prefix_only",
        "count_reconciliation": {
            "rule": "stable + transition_uncertain + unresolved_phase + unassigned = analyzed_complete_cycles",
            "analyzed_complete_cycles": analyzed_cycle_count,
            "stable_cycles": stable_cycles,
            "transition_uncertain_cycles": uncertain_cycle_count,
            "unresolved_phase_cycles": unresolved_phase_cycles,
            "unassigned_cycles": unassigned_cycles,
            "total": reconciliation_total,
            "reconciles": reconciles,
        },
        "limitations": limitations,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "regimes",
        "capture": _capture_envelope(capture),
        "integrity": capture["integrity"],
        "integrity_status": data_integrity_status,
        "data_integrity_status": data_integrity_status,
        "segmentation_status": segmentation_status,
        "overall_status": overall_status,
        "sampling": _sampling_envelope(capture),
        "calibration": capture["calibration"],
        "detector": {
            "id": REGIME_DETECTOR_ID,
            "version": REGIME_DETECTOR_VERSION,
            "cycle_derivation": REGIME_CYCLE_DERIVATION,
            "parameters": {
                "domain": domain,
                "requested_low": float(low),
                "requested_high": float(high),
                "low_code": structure["detector"]["thresholds"]["low_code"],
                "high_code": structure["detector"]["thresholds"]["high_code"],
                "measures": mode,
                "min_cycles_per_side": min_cycles_per_side,
                "relative_tolerance": relative_tolerance,
                "absolute_tolerance": absolute_tolerance,
                "transition_margin_cycles": transition_margin_cycles,
                "anomaly_z": anomaly_z,
                "anomaly_score": "0.6745 * (value - regime_median) / (1.4826 * MAD) with quantization fallback",
                "max_edges": max_edges,
                "max_cycles": max_cycles,
                "chunk_points": chunk_points,
                "cluster_gap_s": cluster_gap_s,
                "start_time_s": start_time_s,
                "end_time_s": end_time_s,
                "structure_detector_id": structure["detector"]["id"],
            },
            "internal_constants": {
                "step_scan_grid": _STEP_SCAN_GRID,
                "step_alternative_candidates": _STEP_ALTERNATIVE_CANDIDATES,
                "step_flatness_fraction": _STEP_FLATNESS_FRACTION,
                "step_noise_sigma": _STEP_NOISE_SIGMA,
                "uncertainty_span_factor": _STEP_UNCERTAINTY_SPAN_FACTOR,
                "mad_to_sigma": _MAD_TO_SIGMA,
                "drift_min_fit_quality": _DRIFT_MIN_FIT_QUALITY,
                "drift_min_monotonic_fraction": _DRIFT_MIN_MONOTONIC_FRACTION,
                "change_point_loss": "L1 loss against left/right robust medians",
            },
            "status": segmentation_status,
        },
        "regimes": {
            "count": len(regimes),
            "returned": len(regimes),
            "items_truncated": False,
            "items_complete": True,
            "items": regimes,
        },
        "transitions": {
            "count": len(transitions),
            "returned": len(transitions),
            "items_truncated": False,
            "items_complete": True,
            "items": transitions,
        },
        "cycles": {
            "count": len(cycle_items),
            "observed_complete_count": observed_cycle_count,
            "observed_count_is_lower_bound": edge_budget_exceeded,
            "analyzed_count": analyzed_cycle_count,
            "returned": len(cycle_items),
            "items_truncated": False,
            "items_complete": True,
            "items": cycle_items,
        },
        "anomalies": {
            "count": len(anomalies),
            "returned": len(anomalies),
            "items_truncated": False,
            "items_complete": True,
            "threshold_basis": "modified_z_median_mad_or_quantization_units",
            "anomaly_z": anomaly_z,
            "items": anomalies,
        },
        "unresolved": {
            "count": len(unresolved),
            "returned": len(unresolved),
            "items_truncated": False,
            "items_complete": True,
            "items": unresolved,
        },
        "measures": measures_section,
        "coverage": coverage,
        "evidence": {
            "raw_scan": True,
            "stride_used": 1,
            "source_sha256": capture["raw_sha256"],
            "source_points": capture["points"],
            "cycle_feature_basis": "sample_grid",
            "cycle_derivation": REGIME_CYCLE_DERIVATION,
            "cycle_diagnostics": cycle_diagnostics,
            "integrity_status": data_integrity_status,
            "data_integrity_status": data_integrity_status,
            "segmentation_status": segmentation_status,
            "overall_status": overall_status,
            "limitations": limitations,
        },
    }


def bound_json(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if max_bytes <= 0 or max_bytes > MAX_JSON_BYTES:
        raise AnalysisError("LIMIT_INVALID", f"max_json_bytes must be in 1..{MAX_JSON_BYTES}")
    compact_regimes: list[dict[str, Any]] = []
    compact_transitions: list[dict[str, Any]] = []
    if result.get("tool") == "regimes":
        regime_section = result.get("regimes", {})
        for regime in regime_section.get("items", []) if isinstance(regime_section, dict) else []:
            compact_regimes.append(
                {
                    key: regime.get(key)
                    for key in (
                        "regime_id", "status", "start_sample", "end_sample_exclusive",
                        "start_time_s", "end_time_s", "stable_cycle_count",
                    )
                }
                | {
                    "measure_medians": {
                        feature: values.get("median")
                        for feature, values in regime.get("summaries", {}).items()
                    }
                }
            )
        transition_section = result.get("transitions", {})
        for transition in transition_section.get("items", []) if isinstance(transition_section, dict) else []:
            boundary = transition.get("boundary", {})
            if not isinstance(boundary, dict):
                boundary = {}
            compact_transitions.append(
                {
                    "transition_id": transition.get("transition_id"),
                    "boundary_sample": boundary.get("sample"),
                    "boundary_time_s": boundary.get("time_s"),
                    "changed_measures": transition.get("changed_measures"),
                    "confidence": transition.get("confidence"),
                }
            )
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
        ("cycles", "items", "returned"),
        ("anomalies", "items", "returned"),
        ("transitions", "items", "returned"),
        ("unresolved", "items", "returned"),
        ("regimes", "items", "returned"),
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

    # Preserve compact regime summaries by pruning verbose candidate diagnostics
    # and explanatory text before falling back to a minimal UNVERIFIED envelope.
    if result.get("tool") == "regimes":
        detector = result.get("detector")
        if isinstance(detector, dict):
            detector.pop("internal_constants", None)
        measures = result.get("measures")
        if isinstance(measures, dict):
            for entry in measures.get("evaluated", []):
                if isinstance(entry, dict):
                    evidence = entry.get("change_evidence")
                    if isinstance(evidence, dict):
                        evidence["rejected_candidates_omitted_for_json_budget"] = len(
                            evidence.pop("rejected_candidates", [])
                        )
            for entry in measures.get("rejected", []):
                if isinstance(entry, dict):
                    entry.pop("detail", None)
        for entry in result.get("transitions", {}).get("items", []):
            if isinstance(entry, dict):
                entry.pop("step_evidence", None)
                for measure in entry.get("per_measure", {}).values():
                    if isinstance(measure, dict):
                        measure.pop("own_boundary_cycle_indexes", None)
        for entry in result.get("unresolved", {}).get("items", []):
            if isinstance(entry, dict):
                entry.pop("detail", None)
                entry.pop("rejected_candidates", None)
        for section_name in ("cycles", "anomalies"):
            parent = result.get(section_name)
            values = parent.get("items") if isinstance(parent, dict) else None
            while isinstance(values, list) and values and size() > max_bytes:
                values.pop()
                parent["returned"] = len(values)
                parent["items_truncated"] = True
                parent["items_complete"] = False
        if size() > max_bytes:
            for section_name in ("cycles", "anomalies"):
                parent = result.get(section_name)
                if isinstance(parent, dict) and parent.get("items"):
                    parent["items"].clear()
                    parent["returned"] = 0
                    parent["items_truncated"] = True
                    parent["items_complete"] = False
            if compact_transitions:
                section = result.get("transitions", {})
                section["items"] = compact_transitions
                section["returned"] = len(compact_transitions)
                section["items_truncated"] = False
                section["items_complete"] = True
            if compact_regimes:
                section = result.get("regimes", {})
                section["items"] = compact_regimes
                section["returned"] = len(compact_regimes)
                section["items_truncated"] = False
                section["items_complete"] = True
        if size() <= max_bytes:
            result.setdefault("coverage", {}).setdefault("limitations", []).append(
                "json_output_pruned_diagnostics_or_detailed_records_to_preserve_regime_summaries"
            )
            if size() <= max_bytes:
                return result
        # If full regime objects still dominate, replace them with compact
        # summaries before omitting segmentation summaries entirely.
        if result.get("tool") == "regimes":
            for section_name, compact_items in (("regimes", compact_regimes), ("transitions", compact_transitions)):
                section = result.get(section_name)
                if isinstance(section, dict) and compact_items:
                    section["items"] = compact_items
                    section["returned"] = len(compact_items)
                    section["items_truncated"] = False
                    section["items_complete"] = True
            for section_name in ("cycles", "anomalies", "unresolved"):
                section = result.get(section_name)
                if isinstance(section, dict) and section.get("items"):
                    section["items"].clear()
                    section["returned"] = 0
                    section["items_truncated"] = True
                    section["items_complete"] = False
            if size() <= max_bytes:
                result.setdefault("coverage", {}).setdefault("limitations", []).append(
                    "json_output_compacted_regime_and_transition_summaries"
                )
                if size() <= max_bytes:
                    return result
            # Keep structured compact stage summaries while shedding verbose
            # intermediate feature diagnostics and repeated envelopes.
            measures_section = result.get("measures")
            if isinstance(measures_section, dict):
                measures_section["evaluated"] = []
                measures_section["rejected"] = []
                measures_section["unavailable"] = []
                measures_section["evaluated_details_omitted"] = True
            evidence_section = result.get("evidence")
            if isinstance(evidence_section, dict):
                evidence_section["cycle_diagnostics"] = {}
            coverage_section = result.get("coverage")
            if isinstance(coverage_section, dict):
                coverage_section["boundary_incomplete_pulses"] = []
                coverage_section["boundary_incomplete_pulse_ids"] = []
                coverage_section["count_reconciliation"].pop("rule", None)
            if size() <= max_bytes:
                result.setdefault("coverage", {}).setdefault("limitations", []).append(
                    "json_output_compacted_measure_details"
                )
                if size() <= max_bytes:
                    return result

    # If full details still exceed the caller budget, try a compact but useful
    # stage summary before omitting regime summaries entirely.
    if result.get("tool") == "regimes" and compact_regimes:
        def compact_section(name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
            source = result.get(name, {})
            return {
                "count": source.get("count", len(items)),
                "returned": len(items),
                "items_truncated": False,
                "items_complete": True,
                "summary_compacted": True,
                "items": items,
            }

        compact_summary = {
            "schema_version": result.get("schema_version", SCHEMA_VERSION),
            "tool": "regimes",
            "capture": {
                key: result.get("capture", {}).get(key)
                for key in ("channel", "raw_sha256", "points")
                if key in result.get("capture", {})
            },
            "integrity_status": result.get("data_integrity_status", result.get("integrity_status")),
            "data_integrity_status": result.get("data_integrity_status", result.get("integrity_status")),
            "segmentation_status": "UNVERIFIED",
            "overall_status": "UNVERIFIED",
            "truncated": True,
            "summary_compacted": True,
            "required_summary_omitted": False,
            "regimes": compact_section("regimes", compact_regimes),
            "transitions": compact_section("transitions", compact_transitions),
            "cycles": {
                "count": result.get("cycles", {}).get("count"), "returned": 0,
                "items_truncated": True, "items_complete": False, "items": [],
            },
            "anomalies": {
                "count": result.get("anomalies", {}).get("count"), "returned": 0,
                "items_truncated": True, "items_complete": False, "items": [],
            },
            "unresolved": {
                "count": result.get("unresolved", {}).get("count"), "returned": 0,
                "items_truncated": True, "items_complete": False, "items": [],
            },
            "measures": {
                "mode": result.get("measures", {}).get("mode"),
                "selected_features": [item.get("feature") for item in result.get("measures", {}).get("selected", [])],
                "evaluated_count": result.get("measures", {}).get("evaluated_count"),
                "details_omitted": True,
            },
            "coverage": {
                key: result.get("coverage", {}).get(key)
                for key in (
                    "source_sha256", "raw_scan", "stride_used", "source_points", "sampled_point_count",
                    "edge_count", "complete_cycle_count", "analyzed_cycle_count", "full_record_scanned",
                    "stable_cycle_count", "transition_uncertain_cycle_count", "unresolved_phase_cycle_count",
                    "count_reconciliation",
                )
                if key in result.get("coverage", {})
            },
            "evidence": {
                "raw_scan": result.get("evidence", {}).get("raw_scan"),
                "stride_used": result.get("evidence", {}).get("stride_used"),
                "source_sha256": result.get("evidence", {}).get("source_sha256"),
                "segmentation_status": "UNVERIFIED",
                "limitations": ["json_output_compacted_regime_cycle_and_diagnostic_details"],
            },
        }
        if len(json.dumps(compact_summary, separators=(",", ":"), allow_nan=False).encode("utf-8")) <= max_bytes:
            return compact_summary

    # Regime reports can contain several independently large evidence tables.
    # If trimming every list still cannot fit, return a small explicit envelope
    # rather than a generic error or an apparently complete partial result.
    if result.get("tool") == "regimes":
        source_capture = result.get("capture", {})
        source_coverage = result.get("coverage", {})
        source_evidence = result.get("evidence", {})
        source_detector = result.get("detector", {})

        def omitted_section(name: str) -> dict[str, Any]:
            parent = result.get(name, {})
            observed_count = parent.get("observed_complete_count", parent.get("count")) if isinstance(parent, dict) else None
            return {
                "count": parent.get("count") if isinstance(parent, dict) else None,
                "observed_count": observed_count,
                "returned": 0,
                "items_truncated": True,
                "items_complete": False,
                "items": [],
            }

        minimal = {
            "schema_version": result.get("schema_version", SCHEMA_VERSION),
            "tool": "regimes",
            "capture": {
                key: source_capture[key]
                for key in ("id", "channel", "raw_sha256", "points", "bytes", "bytes_per_point")
                if key in source_capture
            },
            "integrity": result.get("integrity"),
            "integrity_status": result.get("integrity_status"),
            "data_integrity_status": result.get("data_integrity_status", result.get("integrity_status")),
            "segmentation_status": "UNVERIFIED",
            "overall_status": "UNVERIFIED",
            "truncated": True,
            "required_summary_omitted": True,
            "detector": {
                "id": source_detector.get("id"),
                "version": source_detector.get("version"),
                "status": "UNVERIFIED",
            },
            "regimes": omitted_section("regimes"),
            "transitions": omitted_section("transitions"),
            "cycles": omitted_section("cycles"),
            "anomalies": omitted_section("anomalies"),
            "unresolved": omitted_section("unresolved"),
            "measures": {
                "mode": result.get("measures", {}).get("mode"),
                "selected_count": result.get("measures", {}).get("selected_count"),
                "evaluated_count": result.get("measures", {}).get("evaluated_count"),
                "details_omitted": True,
            },
            "coverage": {
                key: source_coverage[key]
                for key in (
                    "source_sha256", "raw_scan", "stride_used", "source_points", "sampled_point_count",
                    "edge_count", "edge_count_is_lower_bound", "complete_cycle_count",
                    "analyzed_cycle_count", "full_record_scanned", "segmentation_scope",
                )
                if key in source_coverage
            },
            "evidence": {
                "raw_scan": source_evidence.get("raw_scan"),
                "stride_used": source_evidence.get("stride_used"),
                "source_sha256": source_evidence.get("source_sha256"),
                "source_points": source_evidence.get("source_points"),
                "data_integrity_status": result.get("data_integrity_status", result.get("integrity_status")),
                "segmentation_status": "UNVERIFIED",
                "limitations": ["required_summary_omitted_to_fit_json_budget"],
            },
        }
        encoded_minimal = json.dumps(minimal, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded_minimal) <= max_bytes:
            return minimal
        # Very small caller budgets may not fit the usual compact envelope.
        # Fall back again to a minimal status/source header that still says the
        # required regime summary was omitted and cannot be used as a complete
        # segmentation result.
        fallback = {
            "schema_version": result.get("schema_version", SCHEMA_VERSION),
            "tool": "regimes",
            "capture": {
                key: source_capture[key]
                for key in ("channel", "raw_sha256")
                if key in source_capture
            },
            "integrity_status": result.get("integrity_status"),
            "segmentation_status": "UNVERIFIED",
            "overall_status": "UNVERIFIED",
            "truncated": True,
            "required_summary_omitted": True,
        }
        encoded_fallback = json.dumps(fallback, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded_fallback) <= max_bytes:
            return fallback
    raise AnalysisError("LIMIT_INVALID", "Required integrity/summary fields exceed max_json_bytes")


def error_envelope(tool: str, channel: Optional[str], error: AnalysisError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "capture": {"channel": channel} if channel else {},
        "error": {"code": error.code, "message": str(error), "reasons": error.reasons[:16]},
    }
