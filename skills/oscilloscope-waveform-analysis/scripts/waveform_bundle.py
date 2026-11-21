#!/usr/bin/env python3
"""Load any supported oscilloscope capture into one canonical analysis dict.

Four input formats are auto-detected and normalized into the ``capture`` mapping
consumed by every analysis function:

* ``waveform-bundle/v1`` JSON (the primary, vendor-neutral interchange contract),
* generic ``.csv`` time series (one value column, or ``time_s,value``),
* generic ``.npz`` archives (``samples`` plus optional explicit metadata),
* legacy Siglent ``manifest.json`` captures (read-only adapter).

This module is deliberately standalone: Python standard library plus NumPy, no
import of any device Skill module. The SCPI scalar parser and the frame report
used by the legacy ``--revalidate-screen-range`` path are inlined here so the
universal analysis Skill keeps zero dependency while parsing firmware replies
exactly as ``scope_protocol`` does.

One vertical formula is used everywhere::

    voltage = (sample - zero_code) * code_scale_v + effective_offset_v

``effective_offset_v`` is therefore the offset *added* after scaling. A legacy
Siglent descriptor reports its panel offset, which the device-side conversion
subtracts (``code * vdiv / codes_per_div - offset``); the loader stores it here
as its negation so that this single formula reproduces the captured instrument's
own voltages. ``zero_code`` stays ``0.0`` for those captures, as recorded.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised by CLI packaging environments
    np = None


BUNDLE_SCHEMA = "waveform-bundle/v1"
SOURCE_FORMAT_BUNDLE = "waveform-bundle/v1"
SOURCE_FORMAT_SIGLENT = "siglent-manifest"
SOURCE_FORMAT_CSV = "csv"
SOURCE_FORMAT_NPZ = "npz"
# Sections a bundle must carry before any byte of it is trusted.
BUNDLE_REQUIRED_SECTIONS = ("source", "data", "time_axis", "vertical", "integrity")
BUNDLE_CALIBRATION_STATUSES = ("VERIFIED", "UNVERIFIED", "CODE_ONLY")
# Fractional-part tolerance for a CSV time column that must be a uniform grid.
CSV_UNIFORM_TIME_RELATIVE_TOLERANCE = 1e-6
CSV_TIME_COLUMNS = ("time_s", "time", "seconds", "second", "t_s", "t", "x", "x_s")
# Representative ADC code ranges for a legacy capture, keyed by data width. A
# bundle declares its own bounds; a legacy WORD/BYTE descriptor does not.
LEGACY_CODE_BOUNDS = {1: (-128, 127), 2: (-32768, 32767)}


class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, reasons: Optional[list[str]] = None):
        super().__init__(message)
        self.code = code
        self.reasons = reasons or [message]


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


def _int_field(value: Any, name: str, default: Optional[int] = None, *, code: str = "DESCRIPTOR_MISMATCH") -> int:
    if value is None:
        if default is not None:
            return default
        raise AnalysisError(code, f"Descriptor field {name} is missing")
    if isinstance(value, bool):
        raise AnalysisError(code, f"Descriptor field {name} is not an integer: {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisError(code, f"Descriptor field {name} is not an integer: {value!r}") from exc


# Firmware replies to queries are decorated, e.g. ``C1:VDIV 5.00E+00V``,
# ``SARA 1.00E+07Sa/s``, ``25.0 Mpts``. ``float()`` yields None for all of them
# and a left-to-right digit scan yields 1.0 from the ``C1`` prefix; either
# failure lets the panel-snapshot cross-check silently skip while calibration
# still reported VALID. Read the rightmost numeric token instead. This parser is
# inlined from ``scope_protocol.py`` so the two spellings cannot drift apart in
# behaviour even though the modules are independent.
_SCPI_NUMBER_PREFIX = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
# Multipliers are applied on top of the numeric part, so a suffixed magnitude
# such as ``MSa/s`` scales. Bare base units map to 1.0.
_UNIT_SCALES: dict[str, float] = {
    "gsa/s": 1e9, "gsa": 1e9, "msa/s": 1e6, "msa": 1e6, "ksa/s": 1e3, "ksa": 1e3, "sa/s": 1.0,
    "ghz": 1e9, "mhz": 1e6, "khz": 1e3, "hz": 1.0,
    "gpts": 1e9, "gpt": 1e9, "mpts": 1e6, "mpt": 1e6, "kpts": 1e3, "kpt": 1e3, "pts": 1.0, "pt": 1.0,
    "points": 1.0, "point": 1.0, "samples": 1.0, "sample": 1.0,
    "v": 1.0, "mv": 1e-3, "uv": 1e-6, "a": 1.0, "ma": 1e-3, "ua": 1e-6,
    "s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12,
    "w": 1.0, "mw": 1e-3, "uw": 1e-6,
    "vpp": 1.0, "vrms": 1.0, "ohm": 1.0, "deg": 1.0, "%": 1.0,
}
# ``M`` alone is deliberately absent: it is milli in SI and million in scope
# memory-depth replies, so an ambiguous suffix must not be guessed.


def parse_scpi_number(value: Any, *, default_unit: Optional[str] = None) -> Optional[float]:
    """Parse one SCPI scalar reply, tolerating a command echo and a unit suffix.

    Accepts a bare ``"0.2"``, a firmly decorated ``"C1:VDIV 2.00E-01V"``, and a
    space-separated magnitude ``"25.0 Mpts"``. Returns ``None`` when no numeric
    token exists, rather than reading stray digits out of a command echo.
    """

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    for index in range(len(tokens) - 1, -1, -1):
        match = _SCPI_NUMBER_PREFIX.match(tokens[index])
        if match is None:
            continue
        number = float(match.group(0))
        unit = tokens[index][match.end():].lower()
        if not unit and index + 1 < len(tokens):
            unit = tokens[index + 1].lower()
        if not unit:
            unit = default_unit.lower() if default_unit else ""
        if unit and unit not in _UNIT_SCALES:
            # The suffix is not one we can interpret, so this token was not a
            # value; keep scanning left before giving up.
            continue
        if not math.isfinite(number):
            continue
        return number * _UNIT_SCALES.get(unit, 1.0)
    return None


def validate_frame(
    *,
    scope_points: Optional[int],
    scope_duration_s: Optional[float],
    wavedesc_points: Optional[int],
    sample_interval_s: Optional[float],
    downloaded_points: int,
    trigger_relative_s: Optional[float] = None,
    downloaded_duration_s: Optional[float] = None,
    segment_report: Optional[dict[str, Any]] = None,
    bytes_per_point: Optional[int] = None,
    expected_payload_bytes: Optional[int] = None,
    downloaded_payload_bytes: Optional[int] = None,
    byte_order: Optional[str] = None,
    nominal_bits: Optional[int] = None,
    scope_points_semantics: str = "same_record",
) -> dict[str, Any]:
    """Compare the transfer against the WAVEDESC record it claims to reproduce.

    ``scope_points_semantics`` names what ``scope_points`` measures. The default
    ``same_record`` keeps the historical interpretation: the caller asserts the
    value is the same record as the WAVEDESC record, so a difference is a frame
    failure. ``screen`` marks an ``:ACQuire:POINts?`` readback, which the
    programming guide defines as the sample count of the current on-screen
    waveform - a different quantity from the WAVEDESC waveform record. In that
    mode the screen count is reported and never used as the record authority, so
    descriptor/download integrity can be ``COMPLETE`` while screen/waveform
    range correspondence stays ``UNVERIFIED``.
    """

    if scope_points_semantics not in ("same_record", "screen"):
        raise ValueError(
            "scope_points_semantics must be 'same_record' or 'screen', "
            f"got {scope_points_semantics!r}"
        )
    screen_mode = scope_points_semantics == "screen"
    reasons: list[str] = []
    if downloaded_payload_bytes is None and segment_report is not None:
        downloaded_payload_bytes = segment_report.get("downloaded_payload_bytes")
    if expected_payload_bytes is None and segment_report is not None:
        expected_payload_bytes = segment_report.get("expected_payload_bytes")

    def integer(value: Any, name: str, minimum: int) -> Optional[int]:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be a finite integer >= {minimum}") from exc
        if isinstance(value, bool) or not math.isfinite(number) or not number.is_integer() or number < minimum:
            raise ValueError(f"{name} must be a finite integer >= {minimum}")
        return int(number)

    def duration(value: Any, name: str, minimum: float = 0.0) -> Optional[float]:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be a finite duration") from exc
        if isinstance(value, bool) or not math.isfinite(number) or number < minimum:
            raise ValueError(f"{name} must be a finite duration >= {minimum}")
        return number

    # Both sides are optional: a caller may have only the descriptor, only the
    # screen count, or neither, and the reason list says which case it was. A
    # literal 0 stays invalid (it is not a point count); only None means absent.
    scope_points = integer(scope_points, "screen/scope point count", 1) if scope_points is not None else None
    wavedesc_points = (
        integer(wavedesc_points, "WAVEDESC point count", 1) if wavedesc_points is not None else None
    )
    downloaded_points = integer(downloaded_points, "downloaded point count", 0)
    if downloaded_points is None:
        raise ValueError("downloaded point count is required")
    bytes_per_point = integer(bytes_per_point, "bytes per point", 1)
    if bytes_per_point is not None and bytes_per_point not in (1, 2):
        raise ValueError("bytes per point must be 1 or 2")
    expected_payload_bytes = integer(expected_payload_bytes, "expected payload bytes", 1)
    downloaded_payload_bytes = integer(downloaded_payload_bytes, "downloaded payload bytes", 0)
    sample_interval_s = duration(sample_interval_s, "sample interval")
    if sample_interval_s == 0:
        raise ValueError("sample interval must be positive")
    scope_duration_s = duration(scope_duration_s, "screen/scope duration")
    downloaded_duration_s = duration(downloaded_duration_s, "downloaded duration")
    if trigger_relative_s is not None:
        # Trigger coordinates may legitimately be negative.
        trigger_relative_s = duration(trigger_relative_s, "trigger coordinate", -math.inf)
    if sample_interval_s is None:
        reasons.append("sample interval unavailable")
    if expected_payload_bytes is not None and wavedesc_points is not None and bytes_per_point is not None:
        if expected_payload_bytes != wavedesc_points * bytes_per_point:
            reasons.append("expected payload bytes disagree with WAVEDESC point count and width")
    if downloaded_payload_bytes is not None and bytes_per_point is not None:
        if downloaded_payload_bytes != downloaded_points * bytes_per_point:
            reasons.append("downloaded payload bytes disagree with downloaded point count and width")
    if screen_mode:
        # The screen record is not a fallback for a missing descriptor: without
        # WAVEDESC points there is no descriptor payload integrity to claim.
        expected = wavedesc_points
        if expected is None:
            reasons.append(
                "WAVEDESC point count unavailable; the screen record cannot stand in for descriptor integrity"
            )
    else:
        expected = wavedesc_points if wavedesc_points is not None else scope_points
        if scope_points is not None and wavedesc_points is not None and scope_points != wavedesc_points:
            reasons.append(f"screen record {scope_points} differs from WAVEDESC {wavedesc_points}")
    if expected is None:
        # With no point authority on either side the structure cannot be proven;
        # saying COMPLETE here would be a claim without evidence.
        reasons.append("no point-count authority (neither WAVEDESC nor screen record)")
    elif downloaded_points != expected:
        reasons.append(f"downloaded {downloaded_points} points, expected {expected}")
    if expected_payload_bytes is not None and downloaded_payload_bytes != expected_payload_bytes:
        reasons.append(f"downloaded {downloaded_payload_bytes} bytes, expected {expected_payload_bytes}")
    if not screen_mode and scope_duration_s is not None and sample_interval_s is not None and expected is not None:
        expected_duration = expected * sample_interval_s
        if abs(scope_duration_s - expected_duration) > max(1e-12, abs(expected_duration) * 1e-6):
            reasons.append(f"scope duration {scope_duration_s} s differs from WAVEDESC duration {expected_duration} s")
    if segment_report and segment_report.get("status") != "COMPLETE":
        reasons.extend(segment_report.get("reasons", []))
    if sample_interval_s is not None:
        actual_duration = downloaded_points * sample_interval_s
        if downloaded_duration_s is None:
            downloaded_duration_s = actual_duration
        elif abs(downloaded_duration_s - actual_duration) > max(1e-12, abs(actual_duration) * 1e-6):
            reasons.append("downloaded duration disagrees with downloaded point count and sample interval")
    status = "COMPLETE" if not reasons else "INCOMPLETE"
    if segment_report and segment_report.get("status") != "COMPLETE":
        status = "INVALID"
    report: dict[str, Any] = {
        "status": status,
        "scope_record": {"points": scope_points, "duration_s": scope_duration_s},
        "wavedesc_record": {"points": wavedesc_points, "sample_interval_s": sample_interval_s},
        "downloaded": {"points": downloaded_points, "duration_s": downloaded_duration_s},
        "waveform_format": {"bytes_per_point": bytes_per_point, "expected_payload_bytes": expected_payload_bytes, "downloaded_payload_bytes": downloaded_payload_bytes, "byte_order": byte_order, "nominal_bits": nominal_bits},
        "expected_duration_s": (expected * sample_interval_s) if expected is not None and sample_interval_s is not None else None,
        "trigger_relative_s": trigger_relative_s,
        "reasons": reasons,
        "segments": segment_report,
    }
    if screen_mode:
        report["scope_record"] = {"points": scope_points, "duration_s": scope_duration_s, "semantics": "screen"}
        report["screen_record"] = {
            "points": scope_points,
            "duration_s": scope_duration_s,
            "source": "ACQ:POINts? screen waveform sample count",
            "semantics": "screen_display_record",
        }
        point_counts_equal = (
            None if scope_points is None or wavedesc_points is None else scope_points == wavedesc_points
        )
        correspondence_reasons = [
            "screen record (ACQ:POINts?) and WAVEDESC waveform record are different quantities",
            "screen-to-waveform sample and time correspondence is UNVERIFIED",
        ]
        if point_counts_equal is False:
            correspondence_reasons.insert(
                0, f"screen record {scope_points} differs from WAVEDESC record {wavedesc_points}"
            )
        elif point_counts_equal is True:
            correspondence_reasons.append(
                "equal point counts do not prove identical samples or the same time range"
            )
        report["range_correspondence"] = {
            "status": "UNVERIFIED",
            "screen_points": scope_points,
            "wavedesc_points": wavedesc_points,
            "point_counts_equal": point_counts_equal,
            "reasons": correspondence_reasons,
        }
        report["status_meaning"] = (
            "descriptor/download payload integrity only; not whole screen or memory extent, "
            "and not screen/waveform time correspondence"
        )
    return report


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


SCREEN_FRAME_REASON_PATTERNS = (
    re.compile(r"^screen record \d+ differs from WAVEDESC \d+$"),
    re.compile(r"^scope duration [-+0-9.eE]+ s differs from WAVEDESC duration [-+0-9.eE]+ s$"),
)

# Reasons emitted only because a screen readback (`:ACQuire:POINts?`) was compared
# to the waveform record. They are the sole legacy frame failures the explicit
# revalidation flag may re-classify; every other reason stays a hard refusal.
SCREEN_RANGE_REVALIDATION_NOTE = (
    "in-memory derived frame report only; the raw manifest and its recorded status/reasons are unchanged"
)


def _frame_uses_screen_semantics(frame_report: dict[str, Any]) -> bool:
    scope_record = frame_report.get("scope_record") or {}
    return scope_record.get("semantics") == "screen"


def _is_known_screen_frame_reason(reason: Any) -> bool:
    text = str(reason or "").strip()
    return any(pattern.match(text) for pattern in SCREEN_FRAME_REASON_PATTERNS)


def _range_correspondence(frame_report: dict[str, Any]) -> dict[str, Any]:
    """Report screen-vs-waveform range correspondence; never more than UNVERIFIED."""

    recorded = frame_report.get("range_correspondence")
    scope_record = frame_report.get("scope_record") or {}
    wavedesc_record = frame_report.get("wavedesc_record") or {}
    screen_points = scope_record.get("points")
    wavedesc_points = wavedesc_record.get("points")
    if screen_points is None and isinstance(recorded, dict):
        screen_points = recorded.get("screen_points")
    if wavedesc_points is None and isinstance(recorded, dict):
        wavedesc_points = recorded.get("wavedesc_points")
    point_counts_equal = (
        None if screen_points is None or wavedesc_points is None else screen_points == wavedesc_points
    )
    reasons: list[str] = []
    if screen_points is None:
        reasons.append("no screen record count was recorded for this capture")
    if point_counts_equal is False:
        reasons.append(f"screen record {screen_points} differs from WAVEDESC record {wavedesc_points}")
    elif point_counts_equal is True:
        reasons.append("equal point counts do not prove identical samples or the same time range")
    reasons.append("screen-to-waveform sample and time correspondence is UNVERIFIED")
    return {
        "status": "UNVERIFIED",
        "screen_points": screen_points,
        "wavedesc_points": wavedesc_points,
        "point_counts_equal": point_counts_equal,
        "reasons": reasons,
    }


def _revalidate_screen_range_result(
    result: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    channel: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-derive one legacy INCOMPLETE frame with explicit screen semantics.

    This is opt-in and offline. It accepts only a modern ``configured_capture``
    result whose recorded frame failure is one of the known screen/duration
    comparisons; everything else (hash, length, segment, descriptor, unknown
    reason) still fails through the normal load path.
    """

    frame_report = result.get("frame_report") or {}
    original_status = frame_report.get("status")
    original_reasons = list(frame_report.get("reasons") or [])

    def refuse(message: str, reasons: list[str]) -> None:
        raise AnalysisError("CAPTURE_NOT_COMPLETE", message, reasons)

    if manifest.get("mode") != "configured_capture" or result.get("mode") != "configured_capture":
        refuse(
            f"Channel {channel}: screen-range revalidation is limited to modern configured_capture manifests",
            [f"required configured_capture; manifest mode={manifest.get('mode')!r}, result mode={result.get('mode')!r}"],
        )
    if result.get("error"):
        refuse(f"Channel {channel}: result records a failure", [str(result["error"])])
    preamble = result.get("preamble") or {}
    if preamble.get("description") != "WAVEDESC" or not result.get("segments"):
        refuse(
            f"Channel {channel}: screen-range revalidation requires a modern WAVEDESC capture with segments",
            ["no WAVEDESC preamble or no segment metadata"],
        )
    if "screen_record" in frame_report or (frame_report.get("scope_record") or {}).get("semantics") is not None:
        refuse(
            f"Channel {channel}: revalidation requires an unambiguous legacy same-record report",
            ["screen_record or explicit semantics already present in the original frame"],
        )
    if original_status != "INCOMPLETE":
        refuse(
            f"Channel {channel}: screen-range revalidation only applies to a legacy INCOMPLETE frame",
            [f"recorded frame status is {original_status!r}"],
        )
    if not original_reasons:
        refuse(f"Channel {channel}: recorded INCOMPLETE frame carries no reasons", ["frame reasons are empty"])
    unknown_reasons = [reason for reason in original_reasons if not _is_known_screen_frame_reason(reason)]
    if unknown_reasons:
        refuse(
            f"Channel {channel}: recorded frame failure includes reasons beyond the known screen/duration comparisons",
            [f"unknown frame reason: {reason}" for reason in unknown_reasons] + original_reasons,
        )

    scope_record = frame_report.get("scope_record") or {}
    wavedesc_record = frame_report.get("wavedesc_record") or {}
    downloaded = frame_report.get("downloaded") or {}
    waveform_format = frame_report.get("waveform_format") or {}
    segment_report = result.get("segment_report") or {}
    # Recorded descriptor fields must agree with the stored WAVEDESC and with
    # the stored segment report before the frame is re-derived; the relaxed
    # comparison is screen-vs-descriptor only.
    descriptor_points = preamble.get("wave_array_count")
    if wavedesc_record.get("points") is not None and descriptor_points is not None:
        if _int_field(wavedesc_record.get("points"), "frame_report.wavedesc_record.points") != _int_field(descriptor_points, "preamble.wave_array_count"):
            refuse(
                f"Channel {channel}: recorded WAVEDESC frame count disagrees with the stored descriptor",
                [f"frame WAVEDESC points {wavedesc_record.get('points')} vs preamble {descriptor_points}"],
            )
    if segment_report.get("status") != "COMPLETE":
        refuse(
            f"Channel {channel}: segment report is not COMPLETE; screen-range revalidation cannot relax it",
            list(segment_report.get("reasons") or ["segment report status is not COMPLETE"]),
        )

    for key, recorded, descriptor in (
        ("sample_interval_s", wavedesc_record.get("sample_interval_s"), preamble.get("sample_interval")),
        ("bytes_per_point", waveform_format.get("bytes_per_point"), preamble.get("data_width_bytes")),
        ("expected_payload_bytes", waveform_format.get("expected_payload_bytes"), preamble.get("wave_array_1_bytes")),
    ):
        if recorded is None or descriptor is None or recorded != descriptor:
            refuse(f"Channel {channel}: {key} disagrees with descriptor", [f"{recorded!r} vs {descriptor!r}"])
    frame_args = dict(
        scope_points=scope_record.get("points"),
        scope_duration_s=scope_record.get("duration_s"),
        wavedesc_points=wavedesc_record.get("points"),
        sample_interval_s=wavedesc_record.get("sample_interval_s"),
        downloaded_points=downloaded.get("points"),
        downloaded_duration_s=downloaded.get("duration_s"),
        trigger_relative_s=frame_report.get("trigger_relative_s"),
        segment_report=segment_report,
        bytes_per_point=waveform_format.get("bytes_per_point"),
        expected_payload_bytes=waveform_format.get("expected_payload_bytes"),
        downloaded_payload_bytes=waveform_format.get("downloaded_payload_bytes"),
        byte_order=waveform_format.get("byte_order"),
        nominal_bits=waveform_format.get("nominal_bits"),
    )
    historical = validate_frame(**frame_args, scope_points_semantics="same_record")
    if historical["status"] != original_status or sorted(historical["reasons"]) != sorted(original_reasons):
        refuse(
            f"Channel {channel}: original frame reasons do not match the recorded fields",
            historical["reasons"] + original_reasons,
        )
    derived_frame = validate_frame(**frame_args, scope_points_semantics="screen")
    if derived_frame.get("status") != "COMPLETE":
        refuse(
            f"Channel {channel}: re-derived screen frame is still not COMPLETE",
            list(derived_frame.get("reasons") or ["re-derived frame status is not COMPLETE"]),
        )
    record = {
        "applied": True,
        "scope": "in_memory_derived_report_only",
        "reason": "opt_in_screen_range_revalidation",
        "source_manifest_sha256": manifest_sha256,
        "original_frame_status": original_status,
        "original_frame_reasons": original_reasons,
        "original_frame_semantics": "same_record",
        "revalidated_frame_status": derived_frame.get("status"),
        "revalidated_frame_semantics": "screen",
        "note": SCREEN_RANGE_REVALIDATION_NOTE,
        "status_meaning": derived_frame.get("status_meaning"),
    }
    derived_result = dict(result)
    derived_result["frame_report"] = derived_frame
    derived_result["original_frame_report"] = {
        "status": original_status,
        "reasons": original_reasons,
    }
    derived_result["screen_range_revalidation"] = record
    return derived_result, record


def _select_result(
    manifest: dict[str, Any],
    channel: str,
    *,
    revalidate_screen_range: bool = False,
    manifest_sha256: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    if complete:
        return complete[0], {}
    if revalidate_screen_range:
        # Opt-in offline path for manifests written before screen semantics were
        # recorded. Only the approved modern/screen case is re-derived; any
        # unrecognized failure still raises through this same function.
        candidates = [
            item
            for item in matching
            if (item.get("frame_report") or {}).get("status") == "INCOMPLETE"
            and (item.get("segment_report") or {}).get("status") == "COMPLETE"
            and item.get("merged_waveform")
        ]
        if len(candidates) > 1:
            raise AnalysisError("AMBIGUOUS_CAPTURE", f"Multiple INCOMPLETE results exist for {channel}")
        if candidates:
            return _revalidate_screen_range_result(
                candidates[0], manifest, manifest_sha256, channel
            )
    reasons = [
        f"result {index}: frame={item.get('frame_report', {}).get('status')}, "
        f"segments={item.get('segment_report', {}).get('status')}, "
        f"merged_waveform={'present' if item.get('merged_waveform') else 'missing'}"
        for index, item in enumerate(matching)
    ] or [f"No result exists for {channel}"]
    raise AnalysisError("CAPTURE_NOT_COMPLETE", f"No unique complete capture exists for {channel}", reasons)


def _channel_snapshot(manifest: dict[str, Any], channel: str) -> dict[str, Any]:
    for root_key in ("capture_configuration", "pre_capture_snapshot"):
        snapshot = manifest.get(root_key, {})
        found = snapshot.get("channels", {}).get(channel)
        if found:
            return found
    return {}


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


def _level_cross_check(
    calibration: dict[str, Any],
    manifest: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    """Compare the reconstructed amplitude with the instrument's own reading.

    Structural completeness never proves a physical level: a wrong V/div source,
    an ampere scale read as volts, or a dropped panel offset all keep every
    structural check green. The only available independent number is the scope's
    own ``:MEASure:SIMPle:VALue?`` reply recorded by the capture step.

    Tolerance is ``2*lsb + 0.02*|instrument|`` where ``lsb`` is ``code_scale_v``:
    two codes cover the quantisation of both ends of a peak-to-peak reading, and
    the 2% term covers the instrument's own measurement chain. The verdict is
    ``UNKNOWN`` when the manifest carries no reading — never a silent pass.
    """

    result: dict[str, Any] = {
        "verdict": "UNKNOWN",
        "reason": "instrument_measurement_absent",
        "instrument_value": None,
        "reconstructed_value": None,
        "tolerance": None,
        "lsb": None,
    }
    measurements = manifest.get("instrument_measurements")
    if not isinstance(measurements, dict):
        return result
    per_channel = measurements.get(channel)
    if not isinstance(per_channel, dict):
        result["reason"] = f"instrument_measurement_absent_for_{channel}"
        return result
    for key in ("pkpk", "top", "base"):
        entry = per_channel.get(key)
        if not isinstance(entry, dict):
            continue
        instrument = _finite_number(entry.get("value"))
        if instrument is None:
            continue
        lsb = _finite_number(calibration.get("code_scale_v"))
        unit = str(entry.get("unit", "")).strip().lower()
        result["instrument_metric"] = key
        result["instrument_value"] = instrument
        result["instrument_unit"] = unit or None
        if unit and unit != "v":
            result["verdict"] = "FAIL"
            result["reason"] = f"instrument_measurement_in_{unit}_not_volts"
            return result
        if lsb is None:
            result["reason"] = "code_scale_unknown"
            return result
        tolerance = 2.0 * lsb + 0.02 * abs(instrument)
        result["lsb"] = lsb
        result["tolerance"] = tolerance
        # The comparison itself belongs to attach_three_way_status, which holds
        # the reconstructed amplitude.
        result["verdict"] = "COMPARABLE"
        result["reason"] = "measured"
        return result
    return result


def attach_three_way_status(
    calibration: dict[str, Any],
    *,
    manifest: dict[str, Any],
    channel: str,
    reconstruction: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add the three separate claims this artifact can make.

    ``bytes_complete`` — structural/count integrity of the downloaded record.
    ``scale_usable``   — the V/div, offset and unit needed for a conversion are
                         present and not contradicted by the record.
    ``level_confirmed`` — the reconstructed amplitude agrees with the instrument's
                         own reading inside the documented tolerance.

    A reader must ask for each one; ``status == "VALID"`` is only the second.
    """

    issues = calibration.get("verification_failures") or []
    calibration["bytes_complete"] = "COMPLETE" if not issues else "INCOMPLETE"

    scale_reasons: list[str] = []
    if calibration.get("status") != "VALID":
        scale_reasons.append("calibration_status_not_valid")
    if calibration.get("effective_vdiv_v_per_div") in (None, 0):
        scale_reasons.append("vdiv_unknown")
    if calibration.get("effective_offset_v") is None:
        scale_reasons.append("offset_unknown")
    units = str(calibration.get("units", "")).strip().lower()
    if units not in ("v", "volts"):
        scale_reasons.append(f"units_{units or 'missing'}_not_volts")
    calibration["scale_usable"] = "VALID" if not scale_reasons else "UNKNOWN"
    if scale_reasons:
        calibration["scale_reasons"] = scale_reasons

    check = _level_cross_check(calibration, manifest, channel)
    if check["verdict"] == "UNKNOWN":
        calibration["level_confirmed"] = "UNKNOWN"
        calibration["level_reason"] = check.get("reason")
        return calibration
    if check["verdict"] == "FAIL":
        # The instrument reported the metric in a unit that is not a voltage, so
        # there is nothing to compare: refuse instead of converting silently.
        calibration["level_confirmed"] = "FAIL"
        calibration["level_reason"] = check.get("reason")
        calibration["instrument_value"] = check.get("instrument_value")
        calibration["instrument_unit"] = check.get("instrument_unit")
        return calibration

    instrument = check["instrument_value"]
    tolerance = check["tolerance"]
    reconstructed = None
    if reconstruction is not None:
        reconstructed = _finite_number(reconstruction.get("amplitude_v"))
    if reconstructed is None:
        calibration["level_confirmed"] = "UNKNOWN"
        calibration["level_reason"] = "no_reconstructed_amplitude"
        calibration["instrument_value"] = instrument
        calibration["tolerance"] = tolerance
        return calibration

    calibration["instrument_value"] = instrument
    calibration["reconstructed_value"] = reconstructed
    calibration["tolerance"] = tolerance
    calibration["lsb"] = check["lsb"]
    calibration["instrument_metric"] = check.get("instrument_metric")
    if abs(reconstructed - instrument) <= tolerance:
        calibration["level_confirmed"] = "PASS"
    else:
        calibration["level_confirmed"] = "FAIL"
        calibration["level_reason"] = "reconstructed_outside_tolerance"
    return calibration


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
    # ``descriptor_offset``/``snapshot_offset`` are the instrument's own panel
    # offset, which the device-side conversion subtracts. The capture dict must
    # carry the additive offset of ``samples_to_volts``, so the stored value is
    # its negation; comparisons below stay in the instrument's own convention.
    def additive(offset: Optional[float]) -> Optional[float]:
        return None if offset is None else -offset

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

    code_min, code_max = LEGACY_CODE_BOUNDS.get(width, (None, None))
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
        "effective_offset_v": additive(effective_offset),
        "codes_per_div": codes_per_div,
        "zero_code": 0.0,
        "adc_min_code": code_min,
        "adc_max_code": code_max,
        "full_scale_code": None,
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
        calibration["effective_offset_v"] = additive(effective_offset)
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
                    "effective_offset_v": additive(external_offset),
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


def samples_to_volts(samples: Any, calibration: dict[str, Any]) -> Any:
    """Convert raw samples to volts with the one formula this Skill uses.

    ``(sample - zero_code) * code_scale_v + effective_offset_v``. A float sample
    array whose scale is the identity is returned unchanged (``code_scale_v``
    1.0, ``zero_code`` 0.0, ``effective_offset_v`` 0.0 means it is already in
    physical units). Raises ``SCALE_UNUSABLE`` rather than guessing a scale that
    the calibration does not carry.
    """

    _require_numpy()
    zero_code = _finite_number(calibration.get("zero_code"))
    if zero_code is None:
        zero_code = 0.0
    code_scale_v = _finite_number(calibration.get("code_scale_v"))
    effective_offset_v = _finite_number(calibration.get("effective_offset_v"))
    missing = [
        name
        for name, value in (("code_scale_v", code_scale_v), ("effective_offset_v", effective_offset_v))
        if value is None
    ]
    if missing:
        raise AnalysisError(
            "SCALE_UNUSABLE",
            f"Calibration does not carry {', '.join(missing)}; absolute voltages cannot be computed",
            [f"{name}_unknown" for name in missing],
        )
    values = np.asarray(samples)
    if values.dtype.kind not in "iuf":
        raise AnalysisError("DTYPE_UNSUPPORTED", f"Samples of dtype {values.dtype} are not numeric")
    if values.dtype.kind == "f" and code_scale_v == 1.0 and zero_code == 0.0 and effective_offset_v == 0.0:
        return values.astype(np.float64, copy=False)
    return (values.astype(np.float64) - zero_code) * code_scale_v + effective_offset_v


def volts_to_codes(volts: Any, calibration: dict[str, Any]) -> Any:
    """Inverse of :func:`samples_to_volts`.

    Returns float64 codes: whether a code is rounded, clipped or compared is the
    caller's decision, and rounding here would hide a scale that disagrees.
    """

    _require_numpy()
    zero_code = _finite_number(calibration.get("zero_code"))
    if zero_code is None:
        zero_code = 0.0
    code_scale_v = _finite_number(calibration.get("code_scale_v"))
    effective_offset_v = _finite_number(calibration.get("effective_offset_v"))
    reasons = [
        reason
        for reason, broken in (
            ("code_scale_v_unknown", code_scale_v is None),
            ("code_scale_v_zero", code_scale_v == 0),
            ("effective_offset_v_unknown", effective_offset_v is None),
        )
        if broken
    ]
    if reasons:
        raise AnalysisError(
            "SCALE_UNUSABLE",
            f"Calibration cannot be inverted: {', '.join(reasons)}",
            reasons,
        )
    return (np.asarray(volts, dtype=np.float64) - effective_offset_v) / code_scale_v + zero_code


def _resolve_capture_path(capture: Path) -> Path:
    """Resolve a ``--capture`` argument to the single file that must be read.

    A directory means its ``manifest.json``; a captured-but-failed run is
    reported as an incomplete capture instead of as a missing manifest.
    """

    capture = Path(capture).expanduser().resolve()
    failed_path = capture / "manifest.failed.json" if capture.is_dir() else capture.with_name("manifest.failed.json")
    manifest_path = capture / "manifest.json" if capture.is_dir() else capture
    if manifest_path.is_file():
        return manifest_path
    if failed_path.is_file():
        raise AnalysisError("CAPTURE_NOT_COMPLETE", f"Only failed capture manifest exists: {failed_path}")
    raise AnalysisError("MANIFEST_MISSING", f"Capture manifest not found: {manifest_path}")


def _manifest_channels(manifest: dict[str, Any]) -> list[str]:
    """Every channel name the manifest declares, in recording order."""

    declared = manifest.get("channels") or []
    if isinstance(declared, dict):
        declared = list(declared)
    names = [str(name) for name in declared]
    for item in manifest.get("results", []):
        name = item.get("channel")
        if name is not None and str(name) not in names:
            names.append(str(name))
    return names


def _resolve_manifest_channel(manifest: dict[str, Any], channel: Optional[str]) -> str:
    """Name the channel to read; an omitted channel is only valid when unambiguous."""

    if channel:
        return str(channel)
    declared = _manifest_channels(manifest)
    if len(declared) == 1:
        return declared[0]
    if not declared:
        raise AnalysisError("CHANNEL_MISSING", "Capture manifest declares no channel")
    raise AnalysisError(
        "CHANNEL_MISSING",
        f"--channel is required for a capture manifest with channels {', '.join(declared)}",
    )


def _extract_channel_result(
    manifest: dict[str, Any],
    channel: Optional[str] = None,
    *,
    revalidate_screen_range: bool = False,
    manifest_sha256: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(result, screen_range_revalidation)`` for one legacy channel.

    The single place that decides which recorded channel result is the capture;
    an omitted channel is resolved only when the manifest declares exactly one.
    """

    return _select_result(
        manifest,
        _resolve_manifest_channel(manifest, channel),
        revalidate_screen_range=revalidate_screen_range,
        manifest_sha256=manifest_sha256,
    )


def _requested_interval(sample_interval_s: Optional[float], sample_rate_hz: Optional[float]) -> Optional[float]:
    """Turn the two mutually exclusive CLI time-base flags into a sample interval."""

    if sample_interval_s is not None and sample_rate_hz is not None:
        raise AnalysisError("TIME_AXIS_INVALID", "Give either --sample-interval-s or --sample-rate-hz, not both")
    if sample_rate_hz is not None:
        rate = _finite_number(sample_rate_hz)
        if rate is None or rate <= 0:
            raise AnalysisError("TIME_AXIS_INVALID", f"--sample-rate-hz must be finite and positive, got {sample_rate_hz!r}")
        return 1.0 / rate
    if sample_interval_s is not None:
        interval = _finite_number(sample_interval_s)
        if interval is None or interval <= 0:
            raise AnalysisError("TIME_AXIS_INVALID", f"--sample-interval-s must be finite and positive, got {sample_interval_s!r}")
        return interval
    return None


def _merge_interval(declared: Optional[float], requested: Optional[float], *, context: str) -> float:
    """Pick the one sample interval, refusing a file and a flag that disagree."""

    if declared is None and requested is None:
        raise AnalysisError(
            "TIME_AXIS_INVALID",
            f"{context} records no sample interval; give --sample-interval-s or --sample-rate-hz",
        )
    if declared is None:
        return requested
    if requested is None:
        return declared
    if abs(declared - requested) > max(abs(declared), abs(requested)) * CSV_UNIFORM_TIME_RELATIVE_TOLERANCE:
        raise AnalysisError(
            "TIME_AXIS_INVALID",
            f"{context} records a sample interval of {declared!r} s but {requested!r} s was requested",
        )
    return declared


def _normalise_units(value: Optional[Any]) -> str:
    """Collapse a units label to the two domains the analysis distinguishes."""

    if value is None:
        return "V"
    text = str(value).strip().lower()
    if text in ("v", "volt", "volts"):
        return "V"
    if text == "code":
        return "code"
    raise AnalysisError("UNITS_UNSUPPORTED", f"Unsupported capture units {value!r}: expected volts or code")


def _read_json_document(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisError("MANIFEST_MISSING", f"Cannot read capture manifest: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnalysisError("MANIFEST_MISSING", f"Cannot read capture manifest: {exc}") from exc
    if not isinstance(document, dict):
        raise AnalysisError("SCHEMA_UNSUPPORTED", f"Capture document {path.name} is not a JSON object")
    return document, raw


def _reject_legacy_overrides(
    *,
    source_format: str,
    vdiv: Optional[float],
    offset: Optional[float],
    calibration_file: Optional[Path],
) -> None:
    """Refuse legacy physical-override flags instead of applying them partially.

    ``--vdiv``/``--offset`` are probe-compensated descriptor overrides and
    ``--calibration-file`` binds an external WORD scale to one payload hash, so
    neither has a meaning for a self-describing file; silently ignoring them
    would let the caller believe a physical correction was applied.
    """

    supplied = [
        name
        for name, value in (
            ("--vdiv", vdiv),
            ("--offset", offset),
            ("--calibration-file", calibration_file),
        )
        if value is not None
    ]
    if supplied:
        raise AnalysisError(
            "CALIBRATION_INCONSISTENT",
            f"{', '.join(supplied)} only applies to a legacy Siglent manifest capture, not to a {source_format} file",
            [f"{name}_not_applicable_to_{source_format}" for name in supplied],
        )


def _declared_number(
    value: Any,
    name: str,
    *,
    allow_none: bool = False,
    code: str = "BUNDLE_INVALID",
    label: str = "Bundle field",
) -> Optional[float]:
    """Read one declared numeric field, refusing a value that is not finite."""

    if value is None:
        if allow_none:
            return None
        raise AnalysisError(code, f"{label} {name} is required")
    number = _finite_number(value)
    if number is None:
        raise AnalysisError(code, f"{label} {name} is not a finite number: {value!r}")
    return number


def _bundle_code_limit(vertical: dict[str, Any], name: str) -> Optional[Any]:
    """Return one declared ADC code bound unchanged, so ints stay ints."""

    value = vertical.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AnalysisError("BUNDLE_INVALID", f"Bundle field vertical.{name} is not a finite code: {value!r}")
    return value


def _bundle_dtype(data: dict[str, Any]) -> Any:
    dtype_text = data.get("dtype")
    if not isinstance(dtype_text, str) or not dtype_text.strip():
        raise AnalysisError("BUNDLE_INVALID", "Bundle field data.dtype is required")
    try:
        dtype = np.dtype(dtype_text)
    except TypeError as exc:
        raise AnalysisError("DTYPE_UNSUPPORTED", f"Bundle dtype {dtype_text!r} is not a numpy dtype: {exc}") from exc
    if dtype.kind not in "iuf" or dtype.itemsize not in (1, 2, 4, 8):
        raise AnalysisError(
            "DTYPE_UNSUPPORTED",
            f"Bundle dtype {dtype_text!r} cannot be interpreted as integer or floating-point samples",
        )
    return dtype


def _bundle_calibration(
    vertical: dict[str, Any],
    *,
    dtype: Any,
    units: Optional[str],
    source: str,
) -> dict[str, Any]:
    """Translate the bundle's vertical block into the canonical calibration dict.

    A bundle states two separate things and they are kept separate: whether the
    scale fields are usable (``vertical.scale_usable``) and how far its voltage
    scale was verified (``vertical.calibration_status``). ``status`` carries the
    second in the vocabulary the rest of this Skill reads, while
    ``recorded_scale_reasons`` preserves the exporter's own reasons.
    """

    recorded_units = vertical.get("units")
    resolved_units = _normalise_units(units if units is not None else recorded_units)
    recorded_status = vertical.get("calibration_status")
    if not isinstance(recorded_status, str) or recorded_status.strip().upper() not in BUNDLE_CALIBRATION_STATUSES:
        raise AnalysisError(
            "BUNDLE_INVALID",
            "Bundle field vertical.calibration_status must be one of "
            f"{', '.join(BUNDLE_CALIBRATION_STATUSES)}; got {recorded_status!r}",
        )
    recorded_status = recorded_status.strip().upper()
    reason_list = [str(item) for item in vertical.get("scale_reasons") or []]
    scale_declared_usable = vertical.get("scale_usable", True)
    if not isinstance(scale_declared_usable, bool):
        raise AnalysisError(
            "BUNDLE_INVALID",
            f"Bundle field vertical.scale_usable must be true or false; got {scale_declared_usable!r}",
        )
    if not scale_declared_usable:
        # §2.1: an unusable scale keeps the analysis in the code domain, whatever
        # the recorded calibration status claims.
        reason_list.append("bundle_declares_scale_unusable")
        if resolved_units == "V":
            resolved_units = "code"
    if recorded_status == "CODE_ONLY" and resolved_units != "code":
        resolved_units = "code"
        reason_list.append("bundle_records_code_only_calibration")

    code_scale_v = _declared_number(vertical.get("code_scale_v"), "vertical.code_scale_v", allow_none=True)
    zero_code = _declared_number(vertical.get("zero_code"), "vertical.zero_code", allow_none=True)
    offset_v = _declared_number(vertical.get("offset_v"), "vertical.offset_v", allow_none=True)
    vdiv = _declared_number(vertical.get("vdiv_v_per_div"), "vertical.vdiv_v_per_div", allow_none=True)
    if vdiv is not None and vdiv <= 0:
        raise AnalysisError("BUNDLE_INVALID", f"Bundle field vertical.vdiv_v_per_div must be positive, got {vdiv!r}")
    if zero_code is None:
        zero_code = 0.0
    if offset_v is None:
        offset_v = 0.0
    if resolved_units == "V":
        if code_scale_v is None and dtype.kind == "f":
            # §2.1: float samples with the identity scale are already in volts.
            code_scale_v = 1.0
        if code_scale_v is None:
            raise AnalysisError(
                "BUNDLE_INVALID",
                "Bundle field vertical.code_scale_v is required when vertical.units is volts",
            )
        if code_scale_v <= 0:
            raise AnalysisError(
                "BUNDLE_INVALID",
                f"Bundle field vertical.code_scale_v must be positive when vertical.units is volts, got {code_scale_v!r}",
            )

    status = {"VERIFIED": "VALID", "UNVERIFIED": "OBSERVED_UNVERIFIED", "CODE_ONLY": "CODE_ONLY"}[recorded_status]
    if resolved_units == "code" and status == "VALID":
        status = "CODE_ONLY"
    calibration: dict[str, Any] = {
        "status": status,
        "units": resolved_units,
        "source": source,
        "recorded_status": recorded_status,
        "zero_code": zero_code,
        "code_scale_v": code_scale_v,
        "effective_offset_v": offset_v,
        "effective_vdiv_v_per_div": vdiv,
        "lsb": code_scale_v,
        "adc_min_code": _bundle_code_limit(vertical, "adc_min_code"),
        "adc_max_code": _bundle_code_limit(vertical, "adc_max_code"),
        "full_scale_code": _bundle_code_limit(vertical, "full_scale_code"),
        "recorded_scale_reasons": reason_list,
        "verification_failures": [],
        # Seeded so every canonical calibration block carries the three-way keys
        # even before an analysis step re-attaches a reconstructed amplitude.
        "bytes_complete": None,
        "scale_usable": None,
        "scale_reasons": [],
        "level_confirmed": None,
        "level_reason": None,
        "instrument_metric": None,
        "instrument_value": None,
        "instrument_unit": None,
        "reconstructed_value": None,
        "tolerance": None,
    }
    return calibration


def _bundle_instrument_measurements(bundle: dict[str, Any], channel: str) -> dict[str, Any]:
    """Return ``instrument_measurements`` in the per-channel shape the gate reads.

    §2.4 records one flat measurement (``metric``/``value``/``unit``); the legacy
    manifests nest it per channel. Both spellings are accepted, and an already
    nested mapping is passed through untouched.
    """

    measurements = bundle.get("instrument_measurements")
    if not isinstance(measurements, dict) or not measurements:
        return {}
    per_channel = measurements.get(channel)
    if isinstance(per_channel, dict):
        return {"instrument_measurements": measurements}
    metric = measurements.get("metric")
    if metric is None:
        return {}
    value = measurements.get("value")
    if isinstance(value, str):
        value = parse_scpi_number(value)
    entry = {"value": value, "unit": measurements.get("unit"), "raw": measurements.get("source_query")}
    return {"instrument_measurements": {channel: {str(metric).strip().lower(): entry}}}


def _load_waveform_bundle(
    bundle_path: Path,
    bundle: dict[str, Any],
    bundle_bytes: bytes,
    *,
    channel: Optional[str],
    vdiv: Optional[float],
    offset: Optional[float],
    calibration_file: Optional[Path],
    sample_interval_s: Optional[float],
    sample_rate_hz: Optional[float],
    units: Optional[str],
) -> dict[str, Any]:
    """Validate and load one ``waveform-bundle/v1`` document, failing closed."""

    _reject_legacy_overrides(
        source_format=BUNDLE_SCHEMA, vdiv=vdiv, offset=offset, calibration_file=calibration_file
    )
    for section in BUNDLE_REQUIRED_SECTIONS:
        if not isinstance(bundle.get(section), dict):
            raise AnalysisError("BUNDLE_INVALID", f"Bundle is missing the required {section!r} section")
    source = bundle["source"]
    data = bundle["data"]
    time_axis = bundle["time_axis"]
    vertical = bundle["vertical"]
    integrity = bundle["integrity"]

    recorded_channel = str(source.get("channel") or "").strip()
    if channel is not None and recorded_channel and str(channel) != recorded_channel:
        raise AnalysisError(
            "CHANNEL_MISSING",
            f"Channel {channel} is not present in this bundle; it records {recorded_channel}",
        )
    channel_name = str(channel) if channel is not None else recorded_channel

    stored_file = data.get("file")
    if not isinstance(stored_file, str) or not stored_file.strip():
        raise AnalysisError("BUNDLE_INVALID", "Bundle field data.file is required")
    payload_path = _resolve_artifact(stored_file, bundle_path.parent, Path(stored_file).name)

    points = _int_field(data.get("points"), "data.points", code="BUNDLE_INVALID")
    if points <= 0:
        raise AnalysisError("BUNDLE_INVALID", f"Bundle field data.points must be positive, got {points}")
    dtype = _bundle_dtype(data)
    itemsize = dtype.itemsize
    byte_length = _int_field(data.get("byte_length", points * itemsize), "data.byte_length", code="BUNDLE_INVALID")
    byte_offset = _int_field(data.get("byte_offset", 0), "data.byte_offset", code="BUNDLE_INVALID")
    if byte_offset < 0:
        raise AnalysisError("BUNDLE_INVALID", f"Bundle field data.byte_offset must not be negative, got {byte_offset}")
    if points * itemsize != byte_length:
        raise AnalysisError(
            "BUNDLE_INVALID",
            f"Bundle data.byte_length is {byte_length} but {points} points of {dtype} need {points * itemsize}",
        )
    if data.get("width_bytes") is not None:
        declared_width = _int_field(data.get("width_bytes"), "data.width_bytes", code="BUNDLE_INVALID")
        if declared_width != itemsize:
            raise AnalysisError(
                "BUNDLE_INVALID",
                f"Bundle data.width_bytes is {declared_width} but dtype {dtype} is {itemsize} bytes",
            )

    expected_slice_sha = data.get("sha256")
    if not isinstance(expected_slice_sha, str) or not expected_slice_sha.strip():
        raise AnalysisError("BUNDLE_INVALID", "Bundle field data.sha256 is required")
    expected_file_sha = data.get("file_sha256")
    try:
        payload_bytes = payload_path.read_bytes()
    except OSError as exc:
        raise AnalysisError("PATH_UNRESOLVED", f"Cannot read bundle payload {payload_path}: {exc}") from exc
    if points < 0 or byte_offset < 0:
        raise AnalysisError(
            "BUNDLE_INVALID",
            f"Bundle data.points and data.byte_offset must not be negative: {points}, {byte_offset}",
        )
    # The structural byte range is checked before any hash so a truncated file is
    # reported as a length problem rather than as a hash mismatch.
    if byte_offset + byte_length > len(payload_bytes):
        raise AnalysisError(
            "BUNDLE_INVALID",
            f"Bundle data.byte_offset + data.byte_length is {byte_offset + byte_length} bytes "
            f"but {payload_path.name} holds {len(payload_bytes)}",
        )
    if expected_file_sha is not None:
        if not isinstance(expected_file_sha, str) or not expected_file_sha.strip():
            raise AnalysisError("BUNDLE_INVALID", f"Bundle field data.file_sha256 is not a string: {expected_file_sha!r}")
        if hashlib.sha256(payload_bytes).hexdigest().lower() != expected_file_sha.strip().lower():
            raise AnalysisError(
                "HASH_MISMATCH",
                f"Bundle payload file SHA-256 does not match data.file_sha256: {payload_path.name}",
            )
    raw = payload_bytes[byte_offset:byte_offset + byte_length]
    slice_sha = hashlib.sha256(raw).hexdigest()
    if slice_sha != expected_slice_sha.strip().lower():
        raise AnalysisError(
            "HASH_MISMATCH",
            f"Bundle sample slice SHA-256 does not match data.sha256: {payload_path.name}",
        )
    samples = np.frombuffer(raw, dtype=dtype)
    if samples.size != points:
        raise AnalysisError(
            "BUNDLE_INVALID",
            f"Bundle payload decoded to {samples.size} samples but data.points is {points}",
        )

    recorded_status = str(integrity.get("status") or "missing").strip() or "missing"
    if recorded_status != "COMPLETE":
        raise AnalysisError(
            "CAPTURE_NOT_COMPLETE",
            f"Bundle records integrity status {recorded_status!r}; analysis requires COMPLETE",
            list(integrity.get("reasons") or [f"recorded integrity status is {recorded_status!r}"]),
        )

    declared_interval = time_axis.get("sample_interval_s")
    interval: Optional[float] = None
    if declared_interval is not None:
        interval = _finite_number(declared_interval)
        if interval is None or interval <= 0:
            raise AnalysisError(
                "TIME_AXIS_INVALID",
                f"Bundle time_axis.sample_interval_s must be finite and positive, got {declared_interval!r}",
            )
    interval = _merge_interval(
        interval,
        _requested_interval(sample_interval_s, sample_rate_hz),
        context=f"Bundle {bundle_path.name}",
    )
    time_origin_s = _declared_number(time_axis.get("time_origin_s"), "time_axis.time_origin_s", allow_none=True)
    if time_origin_s is None:
        time_origin_s = 0.0

    calibration = _bundle_calibration(
        vertical,
        dtype=dtype,
        units=units,
        source=str(vertical.get("calibration_source") or "waveform bundle vertical block"),
    )
    attach_three_way_status(
        calibration,
        manifest=_bundle_instrument_measurements(bundle, channel_name),
        channel=channel_name,
    )

    recorded_provenance = bundle.get("provenance") if isinstance(bundle.get("provenance"), dict) else {}
    checks = ["bundle_schema_waveform_bundle_v1", "integer_point_width_agreement", "byte_range_within_file", "payload_slice_sha256", "integrity_reports_complete"]
    if expected_file_sha is not None:
        checks.insert(3, "payload_file_sha256")
    return {
        "manifest_path": bundle_path,
        "manifest_dir": bundle_path.parent,
        "manifest": bundle,
        "manifest_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "source_format": SOURCE_FORMAT_BUNDLE,
        "channel": channel_name,
        "path": payload_path,
        "samples": samples,
        "points": points,
        "bytes": byte_length,
        "width": itemsize,
        "dtype": str(dtype),
        "raw_sha256": slice_sha,
        "sample_interval_s": interval,
        "sample_rate_hz": 1.0 / interval,
        "time_origin_s": time_origin_s,
        "preamble": {
            "horizontal_offset": _declared_number(time_axis.get("horizontal_offset_s"), "time_axis.horizontal_offset_s", allow_none=True) or 0.0,
            "timebase_s": _declared_number(time_axis.get("timebase_s"), "time_axis.timebase_s", allow_none=True),
        },
        "calibration": calibration,
        "integrity": {
            "status": "COMPLETE",
            "checks": checks,
            "recorded_checks": list(integrity.get("checks") or []),
            "status_meaning": str(integrity.get("status_meaning") or "bundle payload integrity only"),
        },
        "screen_range": recorded_provenance.get("screen_range"),
        "time_correspondence": {
            "status": "UNVERIFIED",
            "time_reference": str(time_axis.get("reference") or "unverified"),
            "origin_formula": str(
                time_axis.get("origin_formula") or "time_origin_s + sample_index * sample_interval_s"
            ),
            "note": "sample index and relative descriptor time are analyzable; absolute and trigger time are UNVERIFIED",
        },
        "screen_range_revalidation": {"applied": False},
        "provenance": {
            "new_transition_proven": recorded_provenance.get("new_transition_proven"),
            "screenshot": recorded_provenance.get("screenshot"),
            "raw_file": recorded_provenance.get("raw_file"),
            "raw_sha256": recorded_provenance.get("raw_sha256"),
        },
    }


def _csv_number(text: str) -> Optional[float]:
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _read_csv_rows(path: Path) -> list[list[str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AnalysisError("CAPTURE_INVALID", f"Cannot read CSV capture {path}: {exc}") from exc
    rows: list[list[str]] = []
    for cells in csv.reader(text.splitlines()):
        stripped = [cell.strip() for cell in cells]
        if not stripped or all(not cell for cell in stripped):
            continue
        if stripped[0].startswith("#"):
            continue
        rows.append(stripped)
    return rows


def _uniform_interval_from_times(times: list[float]) -> float:
    """Return the step of a strictly increasing, uniform time column."""

    if len(times) < 2:
        raise AnalysisError(
            "TIME_AXIS_INVALID",
            "CSV time column needs at least two rows to derive a sample interval",
        )
    steps = [later - earlier for earlier, later in zip(times, times[1:])]
    first = steps[0]
    if first <= 0:
        raise AnalysisError("TIME_AXIS_INVALID", f"CSV time column is not strictly increasing: first step {first!r}")
    for index, step in enumerate(steps[1:], start=1):
        if step <= 0 or abs(step - first) > abs(first) * CSV_UNIFORM_TIME_RELATIVE_TOLERANCE:
            raise AnalysisError(
                "TIME_AXIS_INVALID",
                f"CSV time column is not uniformly sampled: step {index} is {step!r} s but step 0 is {first!r} s",
            )
    return first


def _load_csv(
    path: Path,
    *,
    channel: Optional[str],
    sample_interval_s: Optional[float],
    sample_rate_hz: Optional[float],
    units: Optional[str],
    vdiv: Optional[float],
    offset: Optional[float],
    calibration_file: Optional[Path],
) -> dict[str, Any]:
    """Load a one- or two-column CSV time series."""

    _reject_legacy_overrides(
        source_format=SOURCE_FORMAT_CSV, vdiv=vdiv, offset=offset, calibration_file=calibration_file
    )
    rows = _read_csv_rows(path)
    if not rows:
        raise AnalysisError("CAPTURE_INVALID", f"CSV capture {path.name} has no data rows")
    header: Optional[list[str]] = None
    if any(_csv_number(cell) is None for cell in rows[0]):
        header = [cell.lower() for cell in rows.pop(0)]
    if not rows:
        raise AnalysisError("CAPTURE_INVALID", f"CSV capture {path.name} has a header but no data rows")
    columns = len(rows[0])
    if columns not in (1, 2):
        raise AnalysisError(
            "CAPTURE_INVALID",
            f"CSV capture {path.name} has {columns} columns; one value column or time_s,value is required",
        )
    if header is not None and len(header) != columns:
        raise AnalysisError(
            "CAPTURE_INVALID",
            f"CSV capture {path.name} header has {len(header)} columns but the data rows have {columns}",
        )
    for index, row in enumerate(rows):
        if len(row) != columns:
            raise AnalysisError(
                "CAPTURE_INVALID",
                f"CSV capture {path.name} row {index + 1} has {len(row)} columns but the first data row has {columns}",
            )
    time_index: Optional[int] = None
    value_index = 0
    if columns == 2:
        if header and header[0] in CSV_TIME_COLUMNS and header[1] not in CSV_TIME_COLUMNS:
            time_index, value_index = 0, 1
        elif header and header[1] in CSV_TIME_COLUMNS and header[0] not in CSV_TIME_COLUMNS:
            time_index, value_index = 1, 0
        else:
            time_index, value_index = 0, 1
    elif header and header[0] in CSV_TIME_COLUMNS:
        raise AnalysisError(
            "METADATA_MISSING",
            f"CSV capture {path.name} has only a {header[0]!r} column; a value column is required",
        )

    values = np.empty(len(rows), dtype=np.float64)
    times: list[float] = []
    for index, row in enumerate(rows):
        number = _csv_number(row[value_index])
        if number is None:
            raise AnalysisError(
                "CAPTURE_INVALID",
                f"CSV capture {path.name} row {index + 1} value {row[value_index]!r} is not a finite number",
            )
        values[index] = number
        if time_index is not None:
            stamp = _csv_number(row[time_index])
            if stamp is None:
                raise AnalysisError(
                    "CAPTURE_INVALID",
                    f"CSV capture {path.name} row {index + 1} time {row[time_index]!r} is not a finite number",
                )
            times.append(stamp)

    declared = _uniform_interval_from_times(times) if time_index is not None else None
    interval = _merge_interval(
        declared,
        _requested_interval(sample_interval_s, sample_rate_hz),
        context=f"CSV capture {path.name}",
    )
    time_origin_s = times[0] if times else 0.0
    resolved_units = _normalise_units(units)
    raw_sha256 = _sha256_file(path)
    calibration: dict[str, Any] = {
        "status": "VALID" if resolved_units == "V" else "CODE_ONLY",
        "units": resolved_units,
        "source": "CSV value column declared as volts" if resolved_units == "V" else "CSV value column declared as codes",
        "zero_code": 0.0,
        "code_scale_v": 1.0 if resolved_units == "V" else None,
        "effective_offset_v": 0.0,
        "effective_vdiv_v_per_div": None,
        "lsb": 1.0 if resolved_units == "V" else None,
        "adc_min_code": None,
        "adc_max_code": None,
        "full_scale_code": None,
        "recorded_scale_reasons": [],
        "verification_failures": [],
        "bytes_complete": None,
        "scale_usable": None,
        "scale_reasons": [],
        "level_confirmed": None,
        "level_reason": None,
        "instrument_metric": None,
        "instrument_value": None,
        "instrument_unit": None,
        "reconstructed_value": None,
        "tolerance": None,
    }
    attach_three_way_status(calibration, manifest={}, channel=str(channel or ""))
    time_reference = (
        "CSV time column; no absolute time reference is recorded"
        if time_index is not None
        else "uniform sample grid starting at 0 s; no time column or absolute time reference is recorded"
    )
    return {
        "manifest_path": path,
        "manifest_dir": path.parent,
        "manifest": {
            "source_format": SOURCE_FORMAT_CSV,
            "file": path.name,
            "sha256": raw_sha256,
            "columns": 2 if time_index is not None else 1,
            "header": header,
            "units": resolved_units,
            "sample_interval_s": interval,
            "time_origin_s": time_origin_s,
        },
        "manifest_sha256": raw_sha256,
        "source_format": SOURCE_FORMAT_CSV,
        "channel": str(channel or ""),
        "path": path,
        "samples": values,
        "points": int(values.size),
        "bytes": int(values.size) * int(values.dtype.itemsize),
        "width": int(values.dtype.itemsize),
        "dtype": str(values.dtype),
        "raw_sha256": raw_sha256,
        "sample_interval_s": interval,
        "sample_rate_hz": 1.0 / interval,
        "time_origin_s": time_origin_s,
        "preamble": {"horizontal_offset": 0.0, "timebase_s": None},
        "calibration": calibration,
        "integrity": {
            "status": "COMPLETE",
            "checks": ["csv_column_count", "csv_finite_values"]
            + (["csv_uniform_time_grid"] if time_index is not None else []),
            "status_meaning": "file parse integrity only",
        },
        "screen_range": None,
        "time_correspondence": {
            "status": "UNVERIFIED",
            "time_reference": time_reference,
            "origin_formula": "time_origin_s + sample_index * sample_interval_s",
            "note": "sample index and relative file time are analyzable; absolute and trigger time are UNVERIFIED",
        },
        "screen_range_revalidation": {"applied": False},
        "provenance": {
            "new_transition_proven": None,
            "screenshot": None,
            "raw_file": path.name,
            "raw_sha256": raw_sha256,
        },
    }


def _npz_metadata(archive: Any) -> dict[str, Any]:
    """Read the optional scalar metadata an NPZ capture may carry."""

    metadata: dict[str, Any] = {}
    for key in ("sample_interval_s", "sample_rate_hz", "time_origin_s", "units", "code_scale_v", "zero_code", "offset_v"):
        if key not in archive.files:
            continue
        array = archive[key]
        if array.ndim != 0:
            raise AnalysisError("CAPTURE_INVALID", f"NPZ metadata {key!r} must be a scalar")
        value = array.item()
        metadata[key] = value.decode("utf-8") if isinstance(value, bytes) else value
    return metadata


def _load_npz(
    path: Path,
    *,
    channel: Optional[str],
    sample_interval_s: Optional[float],
    sample_rate_hz: Optional[float],
    units: Optional[str],
    vdiv: Optional[float],
    offset: Optional[float],
    calibration_file: Optional[Path],
) -> dict[str, Any]:
    """Load a ``samples`` array plus optional explicit metadata from an NPZ file."""

    _reject_legacy_overrides(
        source_format=SOURCE_FORMAT_NPZ, vdiv=vdiv, offset=offset, calibration_file=calibration_file
    )
    try:
        with np.load(path, allow_pickle=False) as archive:
            if "samples" not in archive.files:
                raise AnalysisError(
                    "METADATA_MISSING",
                    f"NPZ capture {path.name} has no 'samples' array; found {', '.join(sorted(archive.files)) or 'nothing'}",
                )
            metadata = _npz_metadata(archive)
            samples = np.array(archive["samples"])
    except AnalysisError:
        raise
    except (OSError, ValueError, EOFError) as exc:
        raise AnalysisError("CAPTURE_INVALID", f"Cannot read NPZ capture {path.name}: {exc}") from exc
    if samples.ndim != 1:
        raise AnalysisError("CAPTURE_INVALID", f"NPZ samples must be one-dimensional; found shape {samples.shape}")
    if samples.size == 0:
        raise AnalysisError("CAPTURE_INVALID", f"NPZ capture {path.name} holds no samples")
    if samples.dtype.kind not in "iuf":
        raise AnalysisError("DTYPE_UNSUPPORTED", f"NPZ samples of dtype {samples.dtype} are not numeric")

    declared_interval: Optional[float] = None
    for key in ("sample_interval_s", "sample_rate_hz"):
        if key not in metadata:
            continue
        number = _finite_number(metadata[key])
        if number is None or number <= 0:
            raise AnalysisError("TIME_AXIS_INVALID", f"NPZ metadata {key!r} must be finite and positive, got {metadata[key]!r}")
        declared_interval = number if key == "sample_interval_s" else 1.0 / number
        break
    interval = _merge_interval(
        declared_interval,
        _requested_interval(sample_interval_s, sample_rate_hz),
        context=f"NPZ capture {path.name}",
    )
    time_origin_s = _declared_number(
        metadata.get("time_origin_s"), "time_origin_s", allow_none=True,
        code="METADATA_INVALID", label="NPZ metadata",
    )
    if time_origin_s is None:
        time_origin_s = 0.0

    resolved_units = _normalise_units(units if units is not None else metadata.get("units"))
    npz_label = dict(code="METADATA_INVALID", label="NPZ metadata")
    code_scale_v = _declared_number(metadata.get("code_scale_v"), "code_scale_v", allow_none=True, **npz_label)
    zero_code = _declared_number(metadata.get("zero_code"), "zero_code", allow_none=True, **npz_label)
    offset_v = _declared_number(metadata.get("offset_v"), "offset_v", allow_none=True, **npz_label)
    if resolved_units == "V" and code_scale_v is None:
        if samples.dtype.kind != "f":
            raise AnalysisError(
                "METADATA_MISSING",
                f"NPZ capture {path.name} stores {samples.dtype} samples; code_scale_v or units='code' is required",
            )
        code_scale_v = 1.0
    if code_scale_v is not None and code_scale_v <= 0:
        raise AnalysisError("METADATA_MISSING", f"NPZ metadata code_scale_v must be positive, got {code_scale_v!r}")
    raw_sha256 = _sha256_file(path)
    declared_scale = any(key in metadata for key in ("code_scale_v", "zero_code", "offset_v"))
    calibration: dict[str, Any] = {
        "status": "CODE_ONLY" if resolved_units == "code" else "VALID",
        "units": resolved_units,
        "source": (
            "NPZ metadata: samples already in volts"
            if resolved_units == "V" and not declared_scale
            else "NPZ metadata: explicit units and vertical scale"
            if resolved_units == "V"
            else "NPZ metadata: samples are raw codes"
        ),
        "zero_code": 0.0 if zero_code is None else zero_code,
        "code_scale_v": code_scale_v,
        "effective_offset_v": 0.0 if offset_v is None else offset_v,
        "effective_vdiv_v_per_div": None,
        "lsb": code_scale_v,
        "adc_min_code": None,
        "adc_max_code": None,
        "full_scale_code": None,
        "recorded_scale_reasons": [],
        "verification_failures": [],
        "bytes_complete": None,
        "scale_usable": None,
        "scale_reasons": [],
        "level_confirmed": None,
        "level_reason": None,
        "instrument_metric": None,
        "instrument_value": None,
        "instrument_unit": None,
        "reconstructed_value": None,
        "tolerance": None,
    }
    attach_three_way_status(calibration, manifest={}, channel=str(channel or ""))
    return {
        "manifest_path": path,
        "manifest_dir": path.parent,
        "manifest": {
            "source_format": SOURCE_FORMAT_NPZ,
            "file": path.name,
            "sha256": raw_sha256,
            "metadata": metadata,
        },
        "manifest_sha256": raw_sha256,
        "source_format": SOURCE_FORMAT_NPZ,
        "channel": str(channel or ""),
        "path": path,
        "samples": samples,
        "points": int(samples.size),
        "bytes": int(samples.size) * int(samples.dtype.itemsize),
        "width": int(samples.dtype.itemsize),
        "dtype": str(samples.dtype),
        "raw_sha256": raw_sha256,
        "sample_interval_s": interval,
        "sample_rate_hz": 1.0 / interval,
        "time_origin_s": time_origin_s,
        "preamble": {"horizontal_offset": 0.0, "timebase_s": None},
        "calibration": calibration,
        "integrity": {
            "status": "COMPLETE",
            "checks": ["npz_samples_array", "npz_scalar_metadata"],
            "status_meaning": "archive parse integrity only",
        },
        "screen_range": None,
        "time_correspondence": {
            "status": "UNVERIFIED",
            "time_reference": "uniform sample grid; no absolute time reference is recorded",
            "origin_formula": "time_origin_s + sample_index * sample_interval_s",
            "note": "sample index and relative file time are analyzable; absolute and trigger time are UNVERIFIED",
        },
        "screen_range_revalidation": {"applied": False},
        "provenance": {
            "new_transition_proven": None,
            "screenshot": None,
            "raw_file": path.name,
            "raw_sha256": raw_sha256,
        },
    }


def _load_siglent_manifest(
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    *,
    channel: Optional[str],
    vdiv: Optional[float],
    offset: Optional[float],
    calibration_file: Optional[Path],
    revalidate_screen_range: bool,
) -> dict[str, Any]:
    """Load one legacy Siglent capture manifest with every recorded check intact."""

    if manifest.get("error"):
        raise AnalysisError("CAPTURE_NOT_COMPLETE", f"Capture manifest records failure: {manifest['error']}")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    channel = _resolve_manifest_channel(manifest, channel)
    result, screen_revalidation = _extract_channel_result(
        manifest,
        channel,
        revalidate_screen_range=revalidate_screen_range,
        manifest_sha256=manifest_sha256,
    )
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
    screen_frame = _frame_uses_screen_semantics(frame_report)
    if screen_frame:
        screen_declaration = (frame_report.get("screen_record") or {}).get("semantics")
        if screen_declaration not in (None, "screen_display_record", "screen"):
            raise AnalysisError("DESCRIPTOR_MISMATCH", "Conflicting screen record semantics")
    for field_name, observed in (
        ("frame_report.wavedesc_record.points", frame_report.get("wavedesc_record", {}).get("points")),
        ("frame_report.downloaded.points", frame_report.get("downloaded", {}).get("points")),
        ("frame_report.segments.downloaded_points", frame_report.get("segments", {}).get("downloaded_points")),
        ("frame_report.segments.expected_points", frame_report.get("segments", {}).get("expected_points")),
    ):
        if observed is not None and _int_field(observed, field_name) != points:
            raise AnalysisError("DESCRIPTOR_MISMATCH", f"{field_name} disagrees with WAVEDESC point count")
    # The screen readback (`ACQ:POINts?`) is a different quantity, so it is
    # reported and never allowed to veto the descriptor record it cannot speak
    # for. A same-record frame keeps the strict equality check.
    if not screen_frame:
        scope_points = frame_report.get("scope_record", {}).get("points")
        if scope_points is not None and _int_field(scope_points, "frame_report.scope_record.points") != points:
            raise AnalysisError("DESCRIPTOR_MISMATCH", "frame_report.scope_record.points disagrees with WAVEDESC point count")

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
        vdiv_override=vdiv,
        offset_override=offset,
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
        "manifest_sha256": manifest_sha256,
        "source_format": SOURCE_FORMAT_SIGLENT,
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
            "status_meaning": "descriptor/download payload integrity only",
        },
        "screen_range": _range_correspondence(frame_report),
        "time_correspondence": {
            "status": "UNVERIFIED",
            "time_reference": "descriptor-reported coordinates, not wall-clock or trigger-locked absolute time",
            "origin_formula": "horizontal_offset - timebase_s * 5 + start * sample_interval",
            "note": "sample index and relative descriptor time are analyzable; absolute and trigger time are UNVERIFIED",
        },
        "screen_range_revalidation": screen_revalidation or {"applied": False},
        "provenance": {
            "new_transition_proven": manifest.get("existing_stop_claims_new_transition"),
            "screenshot": manifest.get("screenshot"),
            "raw_file": str(result.get("merged_waveform") or waveform_path.name),
            "raw_sha256": actual_hash,
        },
    }


def load_capture(
    capture: Path,
    channel: Optional[str] = None,
    *,
    vdiv: Optional[float] = None,
    offset: Optional[float] = None,
    calibration_file: Optional[Path] = None,
    revalidate_screen_range: bool = False,
    sample_interval_s: Optional[float] = None,
    sample_rate_hz: Optional[float] = None,
    units: Optional[str] = None,
) -> dict[str, Any]:
    """Load one capture of any supported format into the canonical dict.

    ``channel`` is required only when the source records more than one channel.
    ``vdiv``/``offset``/``calibration_file`` are legacy Siglent overrides and are
    refused for self-describing formats. ``sample_interval_s``/``sample_rate_hz``
    supply the time base a CSV or NPZ file does not record, and are checked
    against one that it does. ``units`` overrides a file's own units label.
    """

    _require_numpy()
    path = _resolve_capture_path(Path(capture))
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(
            path,
            channel=channel,
            sample_interval_s=sample_interval_s,
            sample_rate_hz=sample_rate_hz,
            units=units,
            vdiv=vdiv,
            offset=offset,
            calibration_file=calibration_file,
        )
    if suffix == ".npz":
        return _load_npz(
            path,
            channel=channel,
            sample_interval_s=sample_interval_s,
            sample_rate_hz=sample_rate_hz,
            units=units,
            vdiv=vdiv,
            offset=offset,
            calibration_file=calibration_file,
        )
    document, raw = _read_json_document(path)
    schema = document.get("schema")
    if schema is not None:
        if schema != BUNDLE_SCHEMA:
            raise AnalysisError(
                "SCHEMA_UNSUPPORTED",
                f"Unsupported capture schema {schema!r}; only {BUNDLE_SCHEMA!r} bundles are accepted",
            )
        return _load_waveform_bundle(
            path,
            document,
            raw,
            channel=channel,
            vdiv=vdiv,
            offset=offset,
            calibration_file=calibration_file,
            sample_interval_s=sample_interval_s,
            sample_rate_hz=sample_rate_hz,
            units=units,
        )
    if not document.get("results") and not document.get("channels"):
        raise AnalysisError(
            "SCHEMA_UNSUPPORTED",
            f"Capture document {path.name} is neither a {BUNDLE_SCHEMA!r} bundle nor a Siglent capture manifest",
        )
    return _load_siglent_manifest(
        path,
        document,
        raw,
        channel=channel,
        vdiv=vdiv,
        offset=offset,
        calibration_file=calibration_file,
        revalidate_screen_range=revalidate_screen_range,
    )
