from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _example_support import check, report, sha256  # noqa: E402


class ParserError(ValueError):
    pass


def read_frame(raw: bytes) -> bytes:
    if not raw.endswith(b"\n"):
        raise ParserError("scalar response has no line terminator")
    return raw[:-1]


def parse_metadata(frame: bytes) -> dict[str, Any]:
    fields = frame.decode("ascii").split(",")
    if len(fields) != 5:
        raise ParserError("scalar response requires five fields")
    value, unit, function, status, count = fields
    try:
        parsed_value = float(value)
        parsed_count = int(count)
    except ValueError as exc:
        raise ParserError("scalar value or count is not numeric") from exc
    return {"value": parsed_value, "unit": unit, "function": function, "status": status, "count": parsed_count}


def extract_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    return {"value": metadata["value"], "unit": metadata["unit"], "function": metadata["function"], "status": metadata["status"], "count": metadata["count"]}


def normalize(metadata: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "scalar-measurement", **payload}


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    if artifact["status"] == "UNSUPPORTED":
        checks.append(check("measurement_status", "fail", {"status": artifact["status"]}))
        return report("UNSUPPORTED", checks, ["instrument_reported_unsupported"], {"raw_sha256": sha256(raw)}, {"example": "multimeter_scalar_text", "support_level": "documented"})
    if artifact["status"] in {"OK", "VALID"}:
        checks.append(check("measurement_status", "pass", {"status": artifact["status"]}))
    else:
        checks.append(check("measurement_status", "fail", {"status": artifact["status"]}))
        reasons.append("instrument_status_is_not_valid")
    if artifact["unit"]:
        checks.append(check("unit_present", "pass", {"unit": artifact["unit"]}))
    else:
        checks.append(check("unit_present", "fail"))
        reasons.append("unit_missing")
    count_check = artifact["count"] == 1
    checks.append(check("expected_single_reading", "pass" if count_check else "fail", {"count": artifact["count"]}))
    if not count_check:
        reasons.append("reading_count_not_one")
    status = "COMPLETE" if not reasons else "UNVERIFIED" if "unit_missing" not in reasons else "INCOMPLETE"
    return report(status, checks, reasons, {"raw_sha256": sha256(raw)}, {"example": "multimeter_scalar_text", "support_level": "documented"}, ["acquisition_sequence_completeness=UNVERIFIED"])


def parse(raw: bytes) -> dict[str, Any]:
    frame = read_frame(raw)
    metadata = parse_metadata(frame)
    payload = extract_payload(metadata)
    artifact = normalize(metadata, payload)
    artifact["integrity"] = validate(artifact, raw)
    return artifact
