#!/usr/bin/env python3
"""Assemble one scoped evidence report from a validated SDS capture.

The report answers five independent questions instead of one verdict:

* ``payload_integrity`` - the downloaded descriptor record matches its own
  point, byte-width, segment and SHA-256 declarations. Nothing more.
* ``requested_range_coverage`` - the caller's explicit half-open descriptor
  sample range is fully present. Without a request this stays ``UNVERIFIED``.
* ``frame_association`` - whether the download, the display and any screenshot
  are the same acquisition. It always stays ``UNVERIFIED``: no command in this
  Skill returns a shared frame identifier, and equal bytes or a recorded stop
  state do not create one.
* ``time_correspondence`` - descriptor-relative sample time. It always stays
  ``UNVERIFIED`` for trigger or wall-clock alignment.
* ``analysis_capability`` - the claims the existing verdict actually supports.
  A refused verdict keeps the axis ``UNVERIFIED``; a task sampling requirement
  is reported as its own subfield and never promotes the axis.

Failures are attributed to one stage: ``input`` (caller arguments), ``load``
(stored data), ``analysis`` (the verdict), or ``output`` (file delivery). An
input or load failure never validates a payload, an analysis failure keeps an
already-validated payload ``COMPLETE``, and an output failure preserves the
whole report with a separate operation error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Optional

from waveform_analysis import MAX_JSON_BYTES, AnalysisError, load_capture
from waveform_scan import build_verdict

SCHEMA_VERSION = "1.1"
DEFAULT_CANDIDATE_WINDOWS = 4
DEFAULT_CANDIDATE_WINDOW_POINTS = 1024
MAX_CANDIDATE_WINDOWS = 32
MAX_CANDIDATE_WINDOW_POINTS = 4096
AXES = (
    "payload_integrity",
    "requested_range_coverage",
    "frame_association",
    "time_correspondence",
    "analysis_capability",
)
AXIS_STATUSES = ("COMPLETE", "INCOMPLETE", "INVALID", "UNVERIFIED", "UNSUPPORTED")
HASH_CHUNK_BYTES = 4 * 1024 * 1024
# A lost dependency or an unsupported stored layout is not corrupt data.
LOAD_STATUS_BY_CODE = {
    "MANIFEST_MISSING": "UNVERIFIED",
    # CAPTURE_NOT_COMPLETE covers any recorded manifest error (including
    # permission, connection and unknown failures) and a non-unique complete
    # result, so it alone never proves missing samples. Stay conservative.
    "CAPTURE_NOT_COMPLETE": "UNVERIFIED",
    "CHANNEL_MISSING": "UNVERIFIED",
    "AMBIGUOUS_CAPTURE": "UNVERIFIED",
    "CALIBRATION_INCONSISTENT": "UNVERIFIED",
    "WIDTH_UNSUPPORTED": "UNSUPPORTED",
    "NUMPY_UNAVAILABLE": "UNSUPPORTED",
    "DEPENDENCY_MISSING": "UNSUPPORTED",
}
HEX_DIGITS = set("0123456789abcdef")


class EvidenceStageError(AnalysisError):
    """An AnalysisError that names the stage that produced it."""

    def __init__(self, stage: str, code: str, message: str, reasons: Optional[list[str]] = None):
        super().__init__(code, message, reasons)
        self.stage = stage


def _strict_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _strict_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _strict_sha256(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if len(candidate) != 64 or any(character not in HEX_DIGITS for character in candidate):
        return None
    return candidate


def _require_int(name: str, value: Any, minimum: int, maximum: Optional[int] = None) -> int:
    number = _strict_int(value)
    if number is None:
        raise EvidenceStageError("input", "LIMIT_INVALID", f"{name} must be an integer, not {type(value).__name__}")
    if number < minimum or (maximum is not None and number > maximum):
        upper = "" if maximum is None else f"..{maximum}"
        raise EvidenceStageError("input", "LIMIT_INVALID", f"{name} must be in {minimum}{upper}")
    return number


def validate_inputs(
    *,
    range_start: Any = None,
    range_end: Any = None,
    max_sample_interval_s: Any = None,
    sampling_requirement_source: Any = None,
    candidate_windows: Any = DEFAULT_CANDIDATE_WINDOWS,
    candidate_window_points: Any = DEFAULT_CANDIDATE_WINDOW_POINTS,
) -> None:
    """Reject malformed caller input before any capture is read or written."""

    _require_int("candidate_windows", candidate_windows, 1, MAX_CANDIDATE_WINDOWS)
    _require_int("candidate_window_points", candidate_window_points, 1, MAX_CANDIDATE_WINDOW_POINTS)
    if range_start is not None:
        _require_int("range_start", range_start, 0)
    if range_end is not None:
        _require_int("range_end", range_end, 1)
    if (range_start is None) != (range_end is None):
        raise EvidenceStageError("input", "LIMIT_INVALID", "range_start and range_end must be given together")
    if range_start is not None and range_end is not None and int(range_end) <= int(range_start):
        raise EvidenceStageError("input", "LIMIT_INVALID", "requested range must satisfy start < end")
    if sampling_requirement_source is not None and not isinstance(sampling_requirement_source, str):
        raise EvidenceStageError("input", "LIMIT_INVALID", "sampling_requirement_source must be text")
    if max_sample_interval_s is not None:
        if isinstance(max_sample_interval_s, str) or _strict_float(max_sample_interval_s) is None:
            raise EvidenceStageError("input", "LIMIT_INVALID", "max_sample_interval_s must be a finite positive duration")
        if float(max_sample_interval_s) <= 0:
            raise EvidenceStageError("input", "LIMIT_INVALID", "max_sample_interval_s must be a finite positive duration")
    elif sampling_requirement_source is not None:
        raise EvidenceStageError("input", "LIMIT_INVALID", "sampling_requirement_source requires max_sample_interval_s")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _axis(status: str, scope: str, reasons: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    if status not in AXIS_STATUSES:
        raise RuntimeError(f"axis status {status!r} is outside {AXIS_STATUSES}")
    return {"status": status, "scope": scope, "reasons": reasons, "evidence": evidence}


def _section_sha256(capture: dict[str, Any], start: int, end: int) -> str:
    """Hash the stored bytes of one sample slice without copying the record."""

    digest = hashlib.sha256()
    samples = capture["samples"]
    index = start
    while index < end:
        stop = min(index + 1_048_576, end)
        digest.update(memoryview(samples[index:stop]).cast("B"))
        index = stop
    return digest.hexdigest()


def _payload_axis(capture: dict[str, Any]) -> dict[str, Any]:
    integrity = capture["integrity"]
    evidence = {
        "manifest_sha256": capture["manifest_sha256"],
        "record_sha256": capture["raw_sha256"],
        "points": capture["points"],
        "bytes": capture["bytes"],
        "bytes_per_point": capture["width"],
        "segments_verified": integrity.get("segments_verified"),
        "integrity_checks": integrity.get("checks", []),
        "status_meaning": integrity.get("status_meaning", "descriptor/download payload integrity only"),
        "record_frame": {
            "idn": capture["manifest"].get("idn"),
            "mode": capture["manifest"].get("mode"),
            "screen_range": capture["screen_range"],
        },
        "does_not_establish": [
            "coverage_of_the_whole_screen_or_acquisition_memory",
            "same_frame_identity_with_any_other_read_or_screenshot",
            "trigger_or_wall_clock_time_alignment",
            "event_of_interest_is_inside_the_record",
        ],
    }
    return _axis(
        str(integrity.get("status")),
        "descriptor_record_download_only",
        [
            "descriptor_point_count_byte_width_and_payload_hashes_agree",
            "every_segment_range_size_and_sha256_was_verified",
        ],
        evidence,
    )


def _requested_range_axis(capture: dict[str, Any], range_start: Optional[int], range_end: Optional[int]) -> dict[str, Any]:
    points = int(capture["points"])
    interval = float(capture["sample_interval_s"])
    origin = float(capture["time_origin_s"])
    common = {
        "coordinate": "descriptor_sample_index_half_open",
        "record_points": points,
        "record_sha256": capture["raw_sha256"],
    }
    if range_start is None and range_end is None:
        return _axis("UNVERIFIED", "no_requested_range", ["no_descriptor_sample_range_was_requested"], {**common, "requested": None})
    start = int(range_start)
    end = int(range_end)
    requested = {"start_sample": start, "end_sample_exclusive": end, "count": end - start}
    if end > points:
        return _axis(
            "INCOMPLETE",
            "descriptor_sample_index_half_open",
            ["requested_range_exceeds_the_validated_descriptor_record"],
            {
                **common,
                "requested": requested,
                "payload_integrity_unaffected": True,
                "note": "the requested target is not covered; the downloaded descriptor payload is still complete",
            },
        )
    return _axis(
        "COMPLETE",
        "descriptor_sample_index_half_open",
        ["requested_range_is_fully_present_in_the_validated_descriptor_record"],
        {
            **common,
            "requested": requested,
            "start_time_s": round(origin + start * interval, 12),
            "end_time_s": round(origin + end * interval, 12),
            "sample_range_sha256": _section_sha256(capture, start, end),
            "sample_range_sha256_basis": "stored raw bytes of the requested sample slice",
            "does_not_establish": [
                "acquisition_memory_beyond_the_descriptor_record",
                "the_event_of_interest_is_inside_the_requested_range",
                "trigger_or_wall_clock_time_alignment",
            ],
        },
    )


def _recorded_stop_state(manifest: dict[str, Any]) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    for key in ("stop_state", "existing_stop_state"):
        state = manifest.get(key)
        if isinstance(state, dict):
            observed[key] = {"raw": state.get("raw"), "normalized": state.get("normalized")}
    return observed


def _screenshot_file_check(record: dict[str, Any], manifest_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Check the recorded PNG against its own bytes/sha256 metadata.

    Both the byte count and the SHA-256 must be present and well typed before a
    match can be claimed. A missing field is ``UNVERIFIED``; a malformed field
    is ``INVALID``. Neither outcome touches ``payload_integrity``.
    """

    conflicts: list[dict[str, Any]] = []
    raw_bytes_value = record.get("raw_bytes")
    sha_value = record.get("sha256")
    recorded_bytes = _strict_int(raw_bytes_value)
    recorded_sha = _strict_sha256(sha_value)
    malformed: list[str] = []
    if raw_bytes_value is not None and recorded_bytes is None:
        malformed.append("raw_bytes_is_not_an_integer")
    if sha_value is not None and recorded_sha is None:
        malformed.append("sha256_is_not_64_hex_characters")
    if malformed:
        conflicts.append({"code": "screenshot_record_metadata_invalid", "detail": ", ".join(malformed)})
        return (
            {
                "status": "INVALID",
                "reasons": malformed,
                "recorded_bytes": raw_bytes_value,
                "recorded_sha256": sha_value if isinstance(sha_value, str) else None,
            },
            conflicts,
        )

    raw_path_value = record.get("raw_path")
    if not raw_path_value or not isinstance(raw_path_value, str):
        return {"status": "UNVERIFIED", "reasons": ["screenshot_record_has_no_raw_path"]}, conflicts
    raw_path = Path(raw_path_value)
    if not raw_path.is_absolute():
        raw_path = manifest_dir / raw_path
    if recorded_bytes is None or recorded_sha is None:
        return (
            {
                "status": "UNVERIFIED",
                "path": str(raw_path),
                "reasons": ["screenshot_record_missing_raw_bytes_or_sha256"],
                "recorded_bytes": recorded_bytes,
                "recorded_sha256": recorded_sha,
            },
            conflicts,
        )
    if not raw_path.is_file():
        if record.get("container_valid"):
            conflicts.append({"code": "screenshot_recorded_as_valid_but_file_is_missing", "detail": str(raw_path)})
        return {"status": "MISSING_FILE", "path": str(raw_path), "recorded_bytes": recorded_bytes}, conflicts
    size = raw_path.stat().st_size
    digest = _sha256_file(raw_path)
    matches = size == recorded_bytes and digest == recorded_sha
    if not matches:
        conflicts.append(
            {
                "code": "screenshot_file_does_not_match_its_record",
                "detail": f"{size} bytes sha256={digest[:16]}...",
            }
        )
    return (
        {
            "status": "MATCH" if matches else "MISMATCH",
            "path": str(raw_path),
            "bytes": size,
            "sha256": digest,
            "recorded_bytes": recorded_bytes,
            "recorded_sha256": recorded_sha,
        },
        conflicts,
    )


def _screenshot_evidence(capture: dict[str, Any]) -> dict[str, Any]:
    manifest = capture["manifest"]
    record = manifest.get("screenshot")
    if not isinstance(record, dict):
        return {
            "present": False,
            "status": "UNVERIFIED",
            "reasons": [
                "manifest_carries_no_screenshot_record",
                "screenshot_absence_does_not_block_payload_integrity",
            ],
            "evidence": None,
            "conflicts": [],
        }

    conflicts: list[dict[str, Any]] = []
    container_status = record.get("status")
    container_valid = record.get("container_valid")
    if bool(container_valid) != (container_status == "COMPLETE"):
        conflicts.append(
            {
                "code": "screenshot_container_flag_disagrees_with_status",
                "detail": f"status={container_status!r} container_valid={container_valid!r}",
            }
        )
    if record.get("image_decode_status") not in (None, "UNVERIFIED"):
        conflicts.append(
            {
                "code": "screenshot_claims_decoded_image",
                "detail": f"image_decode_status={record.get('image_decode_status')!r}",
            }
        )
    recorded_association = record.get("frame_association")
    if isinstance(recorded_association, dict) and recorded_association.get("status") not in (None, "UNVERIFIED"):
        conflicts.append(
            {
                "code": "screenshot_claims_frame_association",
                "detail": f"recorded status={recorded_association.get('status')!r}",
            }
        )
    file_check, file_conflicts = _screenshot_file_check(record, capture["manifest_dir"])
    conflicts.extend(file_conflicts)

    return {
        "present": True,
        "status": "UNVERIFIED",
        "reasons": [
            "screenshot_records_carry_no_shared_frame_identifier",
            "a_valid_png_container_never_establishes_same_frame_or_pixel_to_sample_mapping",
        ],
        "container": {
            "status": container_status,
            "container_valid": container_valid,
            "image_decode_status": record.get("image_decode_status"),
            "image_decode_reasons": record.get("image_decode_reasons"),
        },
        "file_check": file_check,
        "frame_association": {
            "status": "UNVERIFIED",
            "reasons": ["screenshot_container_validity_does_not_upgrade_same_frame_identity"],
        },
        "evidence": {
            "command": record.get("command"),
            "framing": record.get("framing"),
            "raw_path": record.get("raw_path"),
            "recorded_bytes": record.get("raw_bytes"),
            "recorded_sha256": record.get("sha256"),
            "recorded_frame_association": recorded_association,
        },
        "conflicts": conflicts,
    }


def _frame_axis(capture: dict[str, Any], screenshot: dict[str, Any], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = capture["manifest"]
    stop_states = _recorded_stop_state(manifest)
    for key, state in stop_states.items():
        if state.get("normalized") not in (None, "STOP"):
            conflicts.append(
                {
                    "code": "recorded_stop_state_is_not_stop",
                    "detail": f"{key}.normalized={state.get('normalized')!r}",
                }
            )
    evidence = {
        "record_sha256": capture["raw_sha256"],
        "manifest_sha256": capture["manifest_sha256"],
        "frame_provenance": {
            "existing_stop_claims_new_transition": manifest.get("existing_stop_claims_new_transition"),
            "recorded_stop_states": stop_states,
            "ready_state": manifest.get("ready_state"),
        },
        "acquisition_counters": {
            "note": "acquisition counters and stop states describe instrument activity, not the identity of the downloaded frame",
        },
        "screenshot": {
            "present": screenshot["present"],
            "recorded_association": screenshot["evidence"].get("recorded_frame_association") if screenshot["evidence"] else None,
        },
        "does_not_establish": [
            "the_downloaded_frame_is_the_one_shown_on_the_display",
            "the_downloaded_frame_is_the_one_in_any_screenshot",
            "two_reads_with_equal_hashes_are_the_same_acquisition",
        ],
    }
    reasons = [
        "no_command_in_this_skill_returns_a_shared_frame_identifier",
        "stop_state_and_acquisition_counters_do_not_identify_the_downloaded_frame",
        "matching_hashes_only_prove_the_downloaded_bytes_were_not_altered",
    ]
    return _axis("UNVERIFIED", "waveform_record_to_display_and_screenshot", reasons, evidence)


def _time_axis(capture: dict[str, Any]) -> dict[str, Any]:
    correspondence = dict(capture["time_correspondence"])
    evidence = {
        **correspondence,
        "sample_interval_s": capture["sample_interval_s"],
        "time_origin_s": capture["time_origin_s"],
        "screen_range": capture["screen_range"],
        "does_not_establish": [
            "absolute_wall_clock_time",
            "trigger_instant_alignment",
            "decoder_bit_boundary_alignment",
        ],
    }
    return _axis(
        str(correspondence.get("status", "UNVERIFIED")),
        "descriptor_relative_time_only",
        [
            "descriptor_reports_relative_sample_time_not_trigger_locked_time",
            "screen_and_trigger_alignment_remain_unverified",
        ],
        evidence,
    )


def _sampling_requirement(capture: dict[str, Any], max_sample_interval_s: Optional[float], source: Optional[str]) -> dict[str, Any]:
    interval = float(capture["sample_interval_s"])
    requirement: dict[str, Any] = {
        "status": "MISSING",
        "observed_sample_interval_s": interval,
        "max_sample_interval_s": None,
        "source": None,
        "reasons": ["task_sampling_requirement_not_stated"],
        "blocked_task_claims": [],
    }
    if max_sample_interval_s is None:
        return requirement
    requirement["max_sample_interval_s"] = float(max_sample_interval_s)
    if source is None or not source.strip():
        requirement["status"] = "MISSING"
        requirement["reasons"] = ["task_sampling_requirement_stated_without_source_text"]
        return requirement
    requirement["source"] = source.strip()
    if interval <= float(max_sample_interval_s):
        requirement["status"] = "SATISFIED"
        requirement["reasons"] = ["observed_sample_interval_is_within_the_stated_requirement"]
    else:
        requirement["status"] = "INSUFFICIENT"
        requirement["reasons"] = ["observed_sample_interval_exceeds_the_stated_requirement"]
        requirement["blocked_task_claims"] = ["sampling_requirement_insufficient_for_the_stated_task"]
    return requirement


def _analysis_axis(
    capture: dict[str, Any],
    verdict: Optional[dict[str, Any]],
    requirement: dict[str, Any],
    analysis_error: Optional[AnalysisError],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "sampling_requirement": requirement,
        "does_not_establish": [
            "protocol_decodability_or_option_availability",
            "sampling_sufficiency_beyond_the_stated_inequality",
            "any_claim_outside_the_verdict_can_claim_list",
        ],
    }
    reasons: list[str] = []
    if verdict is None:
        status = "UNVERIFIED"
        scope = "verdict_unavailable"
        reasons = [f"analysis_failed:{analysis_error.code if analysis_error else 'UNRECORDED'}"]
        evidence["analysis_error"] = {
            "code": analysis_error.code if analysis_error else None,
            "message": str(analysis_error) if analysis_error else None,
        }
    else:
        claims = verdict["claims"]
        evidence["verdict"] = {
            "status": verdict["status"],
            "refusal_code": (verdict.get("refusal") or {}).get("code"),
            "can_claim": list(claims.get("can_claim", [])),
            "cannot_claim": list(claims.get("cannot_claim", [])),
            "must_state": list(claims.get("must_state", [])),
        }
        evidence["calibration"] = {
            "status": capture["calibration"].get("status"),
            "source": capture["calibration"].get("source"),
            "scale_status": verdict["domain"].get("scale_status"),
        }
        evidence["structure_scan"] = verdict["structure"].get("scan")
        evidence["detection_resolution_s"] = verdict["structure"].get("detection_resolution_s")
        if verdict["status"] == "REFUSED":
            # A refusal never becomes capability evidence, whatever the
            # sampling comparison says.
            status = "UNVERIFIED"
            scope = "verdict_claims_only"
            reasons = ["refused_verdict_capability_unverified"]
            evidence["task_readiness"] = {
                "status": "UNVERIFIED",
                "reasons": ["refused_verdict_capability_unverified"],
            }
        elif requirement["status"] == "INSUFFICIENT":
            # An observed verdict on a record that cannot meet the stated
            # sampling requirement is not task capability, so the axis drops
            # even though the verdict itself stays visible as sub-evidence.
            status = "UNVERIFIED"
            scope = "verdict_claims_only"
            reasons = ["verdict_observed_but_the_stated_sampling_requirement_is_not_met"]
            evidence["task_readiness"] = {
                "status": "UNVERIFIED",
                "reasons": ["observed_sample_interval_exceeds_the_stated_requirement"],
            }
        else:
            status = "COMPLETE"
            scope = "verdict_claims_only"
            reasons = ["verdict_observed_its_claims_are_available"]
            if requirement["status"] == "MISSING":
                reasons.append("sampling_requirement_not_stated")
                # The verdict completed, but no sampling specification exists,
                # so this axis must not read as task-ready.
                reasons.append("task_readiness_not_established")
                evidence["task_readiness"] = {
                    "status": "UNVERIFIED",
                    "reasons": ["task_sampling_requirement_not_stated"],
                }
            else:
                evidence["task_readiness"] = {
                    "status": "SATISFIED_FOR_STATED_REQUIREMENT",
                    "reasons": ["only_the_stated_sampling_inequality_is_met"],
                }
    if requirement["status"] == "INSUFFICIENT":
        reasons.append("sampling_requirement_insufficient")
    elif requirement["status"] == "MISSING" and verdict is not None and verdict["status"] == "REFUSED":
        reasons.append("sampling_requirement_not_stated")
    return _axis(status, scope, reasons, evidence)


def _window_bounds(points: int, candidate_start: int, window_points: int) -> tuple[int, int]:
    span = min(window_points, points)
    start = max(0, min(candidate_start - span // 4, points - span))
    return start, start + span


def _codes_sha256(codes: list[int]) -> str:
    digest = hashlib.sha256()
    for code in codes:
        digest.update(int(code).to_bytes(4, "little", signed=True))
    return digest.hexdigest()


def _sparse_candidates(
    verdict: dict[str, Any],
    capture: dict[str, Any],
    *,
    max_windows: int,
    window_points: int,
) -> Optional[dict[str, Any]]:
    if verdict["status"] != "REFUSED":
        return None
    refusal = verdict.get("refusal") or {}
    excursions = refusal.get("candidate_excursions")
    parent_claims = verdict["claims"]
    if not isinstance(excursions, dict):
        return {
            "status": "NOT_SCANNED",
            "reasons": ["candidate_excursion_scan_did_not_run"],
            "candidate_count": None,
            "windows": [],
            "observations": [],
            "windows_truncated": False,
            "all_candidates_reviewed": False,
            "parent_verdict": {
                "status": verdict["status"],
                "refusal_code": refusal.get("code"),
                "cannot_claim": list(parent_claims.get("cannot_claim", [])),
            },
        }

    points = int(capture["points"])
    interval = float(capture["sample_interval_s"])
    origin = float(capture["time_origin_s"])
    candidates = list(excursions.get("candidates", []))
    selected = candidates[:max_windows]
    windows: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected):
        start, end = _window_bounds(points, int(candidate["start_sample"]), window_points)
        codes = [int(value) for value in capture["samples"][start:end]]
        covers = start <= int(candidate["start_sample"]) and end >= int(candidate["end_sample"])
        windows.append(
            {
                "candidate_index": index,
                "candidate_start_sample": int(candidate["start_sample"]),
                "candidate_end_sample": int(candidate["end_sample"]),
                "window_start_sample": start,
                "window_end_sample_exclusive": end,
                "window_points": len(codes),
                "covers_candidate": covers,
                "start_time_s": round(origin + start * interval, 12),
                "end_time_s": round(origin + end * interval, 12),
                "record_sha256": capture["raw_sha256"],
                "codes_sha256": _codes_sha256(codes),
                "codes": codes,
                "limitations": ["raw_code_domain_only"]
                + ([] if covers else ["window_is_shorter_than_the_candidate_excursion"]),
            }
        )
        observations.append(
            {
                "candidate_index": index,
                "window_start_sample": start,
                "window_end_sample_exclusive": end,
                "min_code": min(codes),
                "max_code": max(codes),
                "observation": "raw samples inside this window leave the record-median reference band; this is not a level, edge, pulse, protocol, or record-wide claim",
            }
        )

    windows_truncated = len(selected) < len(candidates)
    return {
        "status": "CANDIDATES_ONLY",
        "scan": excursions.get("scan"),
        "coverage": {
            "record_points": points,
            "record_sha256": capture["raw_sha256"],
            "detection_resolution_s": interval,
            "scan_scope": excursions.get("scan"),
        },
        "reference_code": excursions.get("reference_code"),
        "noise_sigma": excursions.get("noise_sigma"),
        "deviation_threshold_sigmas": excursions.get("deviation_threshold_sigmas"),
        "candidate_count": excursions.get("candidate_count"),
        "candidates_returned": len(candidates),
        "candidates_truncated": excursions.get("candidates_truncated"),
        "limitations": list(excursions.get("limitations", [])),
        "selection": {
            "policy": "first_n_candidates_in_record_order",
            "max_windows": max_windows,
            "window_points": window_points,
            "windows_selected": len(windows),
            "all_candidates_reviewed": False,
            "note": "the returned windows are a bounded subset of the localised candidates and never a review of every candidate or of the whole record",
        },
        "parent_verdict": {
            "status": verdict["status"],
            "refusal_code": refusal.get("code"),
            "can_claim": list(parent_claims.get("can_claim", [])),
            "cannot_claim": list(parent_claims.get("cannot_claim", [])),
        },
        "observations": observations,
        "windows": windows,
        "windows_truncated": windows_truncated,
        "all_candidates_reviewed": False,
        "reasons": [
            "parent_verdict_was_refused_and_is_preserved",
            "candidate_localisation_is_not_a_level_or_protocol_claim",
            "no_additional_threshold_was_introduced",
        ],
    }


def _windows(report: dict[str, Any]) -> list[dict[str, Any]]:
    sparse = report.get("sparse_candidates")
    if not isinstance(sparse, dict):
        return []
    windows = sparse.get("windows")
    return windows if isinstance(windows, list) else []


def _svg_document_from_report(report: dict[str, Any]) -> str:
    """Render the selected raw-code windows.

    The marker circles are the raw samples. The connecting polyline is a display
    aid for eye guidance only; nothing about the signal between markers is
    claimed.
    """

    channel = report["capture"]["channel"]
    record_sha256 = report["capture"]["raw_sha256"]
    windows = _windows(report)
    width = 720
    plot_height = 200
    left = 56
    right = 16
    top = 34
    row_gap = 30
    height = top + max(1, len(windows)) * (plot_height + row_gap) + 48
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<!-- raw ADC sample markers at original sample resolution; the connecting line is a display aid; no voltage, protocol, decoding or same-frame inference -->",
        f"<title>candidate windows, channel {channel}, record sha256 {record_sha256}</title>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="20" font-family="monospace" font-size="12">candidate windows: raw sample markers (circles) vs sample index</text>',
    ]
    all_codes = [code for window in windows for code in window["codes"]]
    low = min(all_codes) if all_codes else 0
    high = max(all_codes) if all_codes else 1
    span = max(1, high - low)
    for row, window in enumerate(windows):
        codes = window["codes"]
        row_top = top + row * (plot_height + row_gap)
        plot_width = width - left - right
        lines.append(
            f'<text x="{left}" y="{row_top - 6}" font-family="monospace" font-size="11">'
            f"candidate {window['candidate_index']}: samples [{window['window_start_sample']}, {window['window_end_sample_exclusive']}) "
            f"codes [{min(codes)}, {max(codes)}] sha256 {window['codes_sha256'][:12]}</text>"
        )
        lines.append(
            f'<rect x="{left}" y="{row_top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#888888" stroke-width="1"/>'
        )
        count = len(codes)
        denominator = max(1, count - 1)
        positions = []
        for index, code in enumerate(codes):
            x = left + (index * plot_width / denominator if count > 1 else 0.0)
            y = row_top + plot_height - ((code - low) * plot_height / span)
            positions.append((x, y))
        lines.append(
            '<polyline fill="none" stroke="#9db7dd" stroke-width="0.7" points="'
            + " ".join(f"{x:.2f},{y:.2f}" for x, y in positions)
            + '"/>'
        )
        for x, y in positions:
            lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.2" fill="#1f4e9c"/>')
        lines.append(
            f'<text x="{left}" y="{row_top + plot_height + 14}" font-family="monospace" font-size="10">'
            f"x: sample index {window['window_start_sample']}..{window['window_end_sample_exclusive'] - 1}; "
            f"y: code {low}..{high}; circles are the raw samples, the line only connects them"
            "</text>"
        )
    if not windows:
        lines.append(
            f'<text x="{left}" y="{top + 20}" font-family="monospace" font-size="12">no candidate window was selected</text>'
        )
    lines.append(
        f'<text x="{left}" y="{height - 14}" font-family="monospace" font-size="10">'
        f"record sha256 {record_sha256}; channel {channel}; generated by waveform_evidence.py</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _svg_metadata(document: Optional[str], windows: list[dict[str, Any]]) -> dict[str, Any]:
    if document is None or not windows:
        return {
            "written": False,
            "reasons": ["no_candidate_window_was_selected"],
            "windows_plotted": 0,
            "points_plotted": 0,
        }
    encoded = document.encode("utf-8")
    return {
        "written": True,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "axes": {"x": "sample_index", "y": "raw_adc_code"},
        "markers": "one_circle_per_raw_sample",
        "polyline": "display_aid_only_connects_the_markers",
        "windows_plotted": len(windows),
        "points_plotted": sum(len(window["codes"]) for window in windows),
        "does_not_establish": [
            "voltage_or_protocol_behaviour",
            "any_sample_between_the_plotted_indices",
            "a_hardware_screenshot_or_display_state",
        ],
    }


def _compact_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8"))


def _drop_last_window(report: dict[str, Any]) -> bool:
    """Drop the last window and its observation together, then fix every count."""

    sparse = report.get("sparse_candidates")
    if not isinstance(sparse, dict):
        return False
    windows = sparse.get("windows")
    observations = sparse.get("observations")
    if not isinstance(windows, list) or not windows:
        return False
    windows.pop()
    if isinstance(observations, list) and observations:
        observations.pop()
    sparse["windows_truncated"] = True
    sparse["all_candidates_reviewed"] = False
    selection = sparse.get("selection")
    if isinstance(selection, dict):
        selection["windows_selected"] = len(windows)
        selection["all_candidates_reviewed"] = False
    report["truncated"] = True
    return True


def _fit_report(report: dict[str, Any], limit: int, *, svg_requested: bool) -> bool:
    """Trim windows (and their observations) until the report plus SVG metadata fit."""

    if _strict_int(limit) is None or not 1 <= int(limit) <= MAX_JSON_BYTES:
        return False
    report["truncated"] = bool(report.get("truncated"))
    while True:
        report.pop("svg", None)
        while _compact_size(report) > limit:
            if not _drop_last_window(report):
                break
        if _compact_size(report) > limit:
            return False
        if not svg_requested:
            return True
        windows = _windows(report)
        document = _svg_document_from_report(report) if windows else None
        report["svg"] = _svg_metadata(document, windows)
        if _compact_size(report) <= limit:
            return True
        report.pop("svg", None)
        if not _drop_last_window(report):
            return False


def _validate_output_paths(capture_path: Path, out: Optional[Path], svg: Optional[Path]) -> tuple[Optional[Path], Optional[Path]]:
    capture_dir = (capture_path if capture_path.is_dir() else capture_path.parent).expanduser().resolve()
    resolved_out = out.expanduser().resolve() if out is not None else None
    resolved_svg = svg.expanduser().resolve() if svg is not None else None
    if resolved_out is not None and resolved_svg is not None and resolved_out == resolved_svg:
        raise EvidenceStageError("input", "LIMIT_INVALID", "--out and --svg must be different paths")
    for label, value in (("--out", resolved_out), ("--svg", resolved_svg)):
        if value is None:
            continue
        try:
            value.relative_to(capture_dir)
        except ValueError:
            continue
        raise EvidenceStageError("input", "LIMIT_INVALID", f"{label} must be written outside the raw capture directory")
    return resolved_out, resolved_svg


def build_evidence(
    capture: dict[str, Any],
    *,
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
    max_sample_interval_s: Optional[float] = None,
    sampling_requirement_source: Optional[str] = None,
    candidate_windows: int = DEFAULT_CANDIDATE_WINDOWS,
    candidate_window_points: int = DEFAULT_CANDIDATE_WINDOW_POINTS,
) -> dict[str, Any]:
    """Build the five-axis evidence report for one validated capture."""

    validate_inputs(
        range_start=range_start,
        range_end=range_end,
        max_sample_interval_s=max_sample_interval_s,
        sampling_requirement_source=sampling_requirement_source,
        candidate_windows=candidate_windows,
        candidate_window_points=candidate_window_points,
    )
    verdict: Optional[dict[str, Any]] = None
    analysis_error: Optional[AnalysisError] = None
    try:
        verdict = build_verdict(capture)
    except AnalysisError as exc:
        # The payload already loaded and passed validation, so an analysis
        # failure is reported as its own stage and never downgrades payload.
        analysis_error = exc

    conflicts: list[dict[str, Any]] = []
    screenshot = _screenshot_evidence(capture)
    conflicts.extend(screenshot["conflicts"])
    frame_axis = _frame_axis(capture, screenshot, conflicts)
    requirement = _sampling_requirement(capture, max_sample_interval_s, sampling_requirement_source)
    axes = {
        "payload_integrity": _payload_axis(capture),
        "requested_range_coverage": _requested_range_axis(capture, range_start, range_end),
        "frame_association": frame_axis,
        "time_correspondence": _time_axis(capture),
        "analysis_capability": _analysis_axis(capture, verdict, requirement, analysis_error),
    }
    sparse = (
        None
        if verdict is None
        else _sparse_candidates(verdict, capture, max_windows=candidate_windows, window_points=candidate_window_points)
    )
    limitations = list(verdict.get("limitations", [])) if verdict is not None else []
    limitations.extend(
        [
            "payload_integrity_is_scoped_to_the_descriptor_record",
            "frame_association_and_time_correspondence_are_never_upgraded_by_this_report",
        ]
    )
    if requirement["status"] == "MISSING":
        limitations.append("sampling_requirement_not_stated")
        limitations.append("task_readiness_not_established")
    elif requirement["status"] == "INSUFFICIENT":
        limitations.append("sampling_requirement_insufficient")
        limitations.append("task_readiness_not_established")
    if verdict is not None and verdict["status"] == "REFUSED":
        limitations.append("refused_verdict_capability_unverified")
    if sparse is not None:
        limitations.extend(
            [
                "candidate_windows_are_bounded_local_observations_not_a_full_review",
                "parent_refusal_is_preserved_and_no_new_threshold_was_added",
            ]
        )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": "evidence",
        "stage": "complete",
        "capture": {
            "id": capture["manifest"].get("idn", capture["manifest_path"].parent.name),
            "channel": capture["channel"],
            "path": str(capture["path"]),
            "raw_sha256": capture["raw_sha256"],
            "points": capture["points"],
            "bytes": capture["bytes"],
            "bytes_per_point": capture["width"],
            "sample_interval_s": capture["sample_interval_s"],
            "time_origin_s": capture["time_origin_s"],
            "source_manifest_sha256": capture["manifest_sha256"],
        },
        "axes": axes,
        "sparse_candidates": sparse,
        "screenshot": screenshot,
        "conflicts": conflicts,
        "limitations": limitations,
        "truncated": False,
    }
    if analysis_error is not None:
        report["stage"] = "analysis"
        report["error"] = {
            "stage": "analysis",
            "code": analysis_error.code,
            "message": str(analysis_error),
            "reasons": analysis_error.reasons[:16],
        }
    return report


def evidence_error_report(
    capture_path: Path,
    channel: str,
    error: EvidenceStageError,
) -> dict[str, Any]:
    """Explain a refused stage without presenting any integrity axis as satisfied."""

    stage = error.stage
    payload_status = LOAD_STATUS_BY_CODE.get(error.code, "INVALID") if stage == "load" else "UNVERIFIED"
    reason = f"{stage}_failed:{error.code}"
    evidence = {
        "path": str(capture_path),
        "error_code": error.code,
        "error_message": str(error),
        "error_reasons": error.reasons[:16],
    }
    payload_reasons = [reason] + [f"loader_reason:{item}" for item in error.reasons[:8]]
    axes = {
        "payload_integrity": _axis(
            payload_status,
            "no_validated_payload",
            payload_reasons,
            evidence,
        ),
        "requested_range_coverage": _axis(
            "UNVERIFIED",
            "no_validated_payload",
            [f"range_coverage_not_evaluated_because_{stage}_failed"],
            evidence,
        ),
        "frame_association": _axis(
            "UNVERIFIED",
            "no_validated_payload",
            ["no_frame_identifier_exists_even_for_a_validated_payload"],
            evidence,
        ),
        "time_correspondence": _axis(
            "UNVERIFIED",
            "no_validated_payload",
            ["no_descriptor_time_is_available_without_a_validated_payload"],
            evidence,
        ),
        "analysis_capability": _axis(
            "UNVERIFIED",
            "no_validated_payload",
            [f"analysis_not_attempted_because_{stage}_failed"],
            evidence,
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "evidence",
        "stage": stage,
        "capture": {"channel": channel, "path": str(capture_path)},
        "error": {"stage": stage, "code": error.code, "message": str(error), "reasons": error.reasons[:16]},
        "axes": axes,
        "sparse_candidates": None,
        "screenshot": {
            "present": False,
            "status": "UNVERIFIED",
            "reasons": [f"capture_not_usable_because_{stage}_failed"],
            "evidence": None,
            "conflicts": [],
        },
        "conflicts": [{"code": f"{stage}_failed", "detail": f"{error.code}: {error}"}],
        "limitations": [
            reason,
            "no_axis_was_satisfied_by_this_run",
            "a_refused_run_is_not_evidence_of_absence",
        ],
        "truncated": False,
    }


def collect_evidence(
    capture_path: Path,
    channel: str,
    *,
    calibration_file: Optional[Path] = None,
    vdiv_override: Optional[float] = None,
    offset_override: Optional[float] = None,
    revalidate_screen_range: bool = False,
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
    max_sample_interval_s: Optional[float] = None,
    sampling_requirement_source: Optional[str] = None,
    candidate_windows: int = DEFAULT_CANDIDATE_WINDOWS,
    candidate_window_points: int = DEFAULT_CANDIDATE_WINDOW_POINTS,
) -> dict[str, Any]:
    """Load the capture strictly, then build the evidence report."""

    validate_inputs(
        range_start=range_start,
        range_end=range_end,
        max_sample_interval_s=max_sample_interval_s,
        sampling_requirement_source=sampling_requirement_source,
        candidate_windows=candidate_windows,
        candidate_window_points=candidate_window_points,
    )
    try:
        capture = load_capture(
            capture_path,
            channel,
            calibration_file=calibration_file,
            vdiv_override=vdiv_override,
            offset_override=offset_override,
            revalidate_screen_range=revalidate_screen_range,
        )
    except AnalysisError as exc:
        raise EvidenceStageError("load", exc.code, str(exc), exc.reasons) from exc
    return build_evidence(
        capture,
        range_start=range_start,
        range_end=range_end,
        max_sample_interval_s=max_sample_interval_s,
        sampling_requirement_source=sampling_requirement_source,
        candidate_windows=candidate_windows,
        candidate_window_points=candidate_window_points,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="capture directory or manifest.json")
    parser.add_argument("--channel", required=True, help="channel name present in the capture manifest, normally C1-C4")
    parser.add_argument("--calibration", type=Path, help="explicit calibration JSON, including independent WORD evidence")
    parser.add_argument("--vdiv", type=float, help="explicit probe-compensated physical V/div")
    parser.add_argument("--offset", type=float, help="explicit physical offset in volts")
    parser.add_argument("--revalidate-screen-range", action="store_true", help="re-derive recorded screen-count comparison failures offline")
    parser.add_argument("--range-start", type=int, help="first descriptor sample index of the requested half-open range")
    parser.add_argument("--range-end", type=int, help="exclusive descriptor sample index of the requested half-open range")
    parser.add_argument("--max-sample-interval-s", type=float, help="explicit task sampling requirement; proves only its own inequality")
    parser.add_argument("--sampling-requirement-source", help="required provenance text for --max-sample-interval-s")
    parser.add_argument("--candidate-windows", type=int, default=DEFAULT_CANDIDATE_WINDOWS, help="bounded number of candidate windows to extract")
    parser.add_argument("--candidate-window-points", type=int, default=DEFAULT_CANDIDATE_WINDOW_POINTS, help="bounded raw points per candidate window")
    parser.add_argument("--svg", type=Path, help="write a bounded raw-sample SVG of the selected windows outside the capture directory")
    parser.add_argument("--max-json-bytes", type=int, default=256 * 1024)
    parser.add_argument("--out", type=Path, help="write the JSON report outside the capture directory instead of stdout")
    return parser


def _reserve(path: Path) -> None:
    """Create a new empty file exclusively; never touch an existing path."""

    descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(descriptor)


def _write_reserved(path: Path, data: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()


def _remove_created(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _safe_out_path(args: argparse.Namespace) -> Optional[Path]:
    """Resolve the requested JSON path, or None when it may not be written."""

    if args.out is None:
        return None
    try:
        resolved, _ = _validate_output_paths(args.capture, args.out, args.svg)
        return resolved
    except EvidenceStageError:
        return None


def _emit_error_report(args: argparse.Namespace, report: dict[str, Any]) -> int:
    """Deliver a small stage-error report without ever overwriting a file."""

    out_path = _safe_out_path(args)
    if args.out is not None and out_path is None:
        report["operation_error"] = {
            "stage": "output",
            "code": "OUTPUT_REJECTED",
            "message": "the requested --out path is not writable for evidence output",
            "path": str(args.out),
        }
    if not _fit_report(report, args.max_json_bytes, svg_requested=False):
        stage = report.get("stage")
        code = (report.get("error") or {}).get("code")
        sys.stderr.write(f"evidence {stage} error ({code}) does not fit --max-json-bytes; nothing was written\n")
        return 2
    encoded = json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
    if out_path is None:
        sys.stdout.write(encoded.decode("utf-8"))
        return 2
    try:
        _reserve(out_path)
    except OSError as exc:
        report["operation_error"] = {
            "stage": "output",
            "code": "OUTPUT_UNAVAILABLE",
            "message": f"{type(exc).__name__}: {exc}",
            "path": str(out_path),
        }
        if not _fit_report(report, args.max_json_bytes, svg_requested=False):
            stage = report.get("stage")
            code = (report.get("error") or {}).get("code")
            sys.stderr.write(f"evidence {stage} error ({code}) does not fit --max-json-bytes; nothing was written\n")
            return 2
        sys.stdout.write(json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False))
        return 2
    try:
        _write_reserved(out_path, encoded)
    except OSError as exc:
        out_path.unlink(missing_ok=True)
        sys.stderr.write(f"evidence error report could not be written: {type(exc).__name__}: {exc}\n")
    return 2


def _emit_success_report(args: argparse.Namespace, report: dict[str, Any]) -> int:
    """Reserve every target first, then write the budgeted report and SVG."""

    created: list[Path] = []
    try:
        if args.out is not None:
            _reserve(args.out)
            created.append(args.out)
        if args.svg is not None:
            _reserve(args.svg)
            created.append(args.svg)
    except OSError as exc:
        _remove_created(created)
        report["stage"] = "output"
        report["operation_error"] = {
            "stage": "output",
            "code": "OUTPUT_UNAVAILABLE",
            "message": f"{type(exc).__name__}: {exc}",
            "path": getattr(exc, "filename", None),
        }
        if not _fit_report(report, args.max_json_bytes, svg_requested=False):
            sys.stderr.write("evidence report does not fit --max-json-bytes; nothing was written\n")
            return 2
        sys.stdout.write(json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False))
        return 2

    if not _fit_report(report, args.max_json_bytes, svg_requested=args.svg is not None):
        _remove_created(created)
        sys.stderr.write("evidence report does not fit --max-json-bytes; nothing was written\n")
        return 2

    svg_document = _svg_document_from_report(report) if args.svg is not None and _windows(report) else None
    try:
        if args.svg is not None:
            if svg_document is not None:
                _write_reserved(args.svg, svg_document.encode("utf-8"))
            else:
                args.svg.unlink(missing_ok=True)
                created.remove(args.svg)
        encoded = json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
        if len(encoded) > args.max_json_bytes:
            raise ValueError("report exceeds --max-json-bytes after enrichment")
        if args.out is not None:
            _write_reserved(args.out, encoded)
        else:
            sys.stdout.write(encoded.decode("utf-8"))
    except (OSError, ValueError) as exc:
        _remove_created(created)
        report.pop("svg", None)
        report["stage"] = "output"
        report["operation_error"] = {
            "stage": "output",
            "code": "OUTPUT_WRITE_FAILED",
            "message": f"{type(exc).__name__}: {exc}",
        }
        if not _fit_report(report, args.max_json_bytes, svg_requested=False):
            sys.stderr.write("evidence report does not fit --max-json-bytes; nothing was written\n")
            return 2
        sys.stdout.write(json.dumps(report, separators=(",", ":"), sort_keys=True, allow_nan=False))
        return 2
    return 0 if report.get("stage") == "complete" else 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_int("max_json_bytes", args.max_json_bytes, 1, MAX_JSON_BYTES)
        validate_inputs(
            range_start=args.range_start,
            range_end=args.range_end,
            max_sample_interval_s=args.max_sample_interval_s,
            sampling_requirement_source=args.sampling_requirement_source,
            candidate_windows=args.candidate_windows,
            candidate_window_points=args.candidate_window_points,
        )
        args.out, args.svg = _validate_output_paths(args.capture, args.out, args.svg)
        report = collect_evidence(
            args.capture,
            args.channel,
            calibration_file=args.calibration,
            vdiv_override=args.vdiv,
            offset_override=args.offset,
            revalidate_screen_range=args.revalidate_screen_range,
            range_start=args.range_start,
            range_end=args.range_end,
            max_sample_interval_s=args.max_sample_interval_s,
            sampling_requirement_source=args.sampling_requirement_source,
            candidate_windows=args.candidate_windows,
            candidate_window_points=args.candidate_window_points,
        )
    except EvidenceStageError as exc:
        return _emit_error_report(args, evidence_error_report(args.capture, args.channel, exc))
    except AnalysisError as exc:
        stage_error = EvidenceStageError(getattr(exc, "stage", "load"), exc.code, str(exc), exc.reasons)
        return _emit_error_report(args, evidence_error_report(args.capture, args.channel, stage_error))
    except ModuleNotFoundError as exc:
        stage_error = EvidenceStageError("load", "DEPENDENCY_MISSING", str(exc))
        return _emit_error_report(args, evidence_error_report(args.capture, args.channel, stage_error))
    except (OSError, ValueError, OverflowError) as exc:
        stage_error = EvidenceStageError("load", "EVIDENCE_FAILED", str(exc))
        return _emit_error_report(args, evidence_error_report(args.capture, args.channel, stage_error))
    return _emit_success_report(args, report)


if __name__ == "__main__":
    raise SystemExit(main())
