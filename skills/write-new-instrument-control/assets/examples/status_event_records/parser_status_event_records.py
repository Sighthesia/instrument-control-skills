from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _example_support import check, report, sha256  # noqa: E402


class ParserError(ValueError):
    pass


def read_frame(raw: bytes) -> list[str]:
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ParserError("event stream is not ASCII JSON-lines") from exc
    if not lines:
        raise ParserError("event stream is empty")
    return lines


def parse_metadata(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ParserError("event line is not valid JSON") from exc
    return records


def extract_payload(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return records


def normalize(metadata: list[dict[str, Any]], payload: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "status-record", "records": payload}


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    records = artifact["records"]
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    end_marker = bool(records and records[-1].get("end") is True)
    checks.append(check("end_marker_present", "pass" if end_marker else "fail"))
    if not end_marker:
        reasons.append("end_marker_missing")
    events = [record for record in records if record.get("end") is not True]
    sequence_ok = [record.get("sequence") for record in events] == list(range(len(events)))
    checks.append(check("sequence_contiguous", "pass" if sequence_ok else "fail"))
    if not sequence_ok:
        reasons.append("sequence_gap_or_duplicate")
    timestamp_ok = True
    timestamps: list[datetime] = []
    for record in events:
        if not isinstance(record.get("event"), str) or not isinstance(record.get("timestamp"), str):
            timestamp_ok = False
            continue
        try:
            timestamps.append(datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")))
        except ValueError:
            timestamp_ok = False
    if timestamps and timestamps != sorted(timestamps):
        timestamp_ok = False
    checks.append(check("timestamps_parse_and_order", "pass" if timestamp_ok else "fail"))
    if not timestamp_ok:
        reasons.append("timestamp_invalid_or_out_of_order")
    status = "COMPLETE" if not reasons else "INCOMPLETE" if "end_marker_missing" in reasons else "INVALID"
    return report(status, checks, reasons, {"raw_sha256": sha256(raw), "event_count": len(events)}, {"example": "status_event_records", "support_level": "documented"})


def parse(raw: bytes) -> dict[str, Any]:
    lines = read_frame(raw)
    metadata = parse_metadata(lines)
    payload = extract_payload(metadata)
    artifact = normalize(metadata, payload)
    artifact["integrity"] = validate(artifact, raw)
    return artifact
