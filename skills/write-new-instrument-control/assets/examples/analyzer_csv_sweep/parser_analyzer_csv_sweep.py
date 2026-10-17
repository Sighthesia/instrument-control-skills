from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _example_support import check, report, sha256  # noqa: E402


class ParserError(ValueError):
    pass


def read_frame(raw: bytes) -> str:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ParserError("CSV response is not ASCII") from exc


def parse_metadata(frame: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(frame))
    if reader.fieldnames != ["frequency_hz", "magnitude_db"]:
        raise ParserError("CSV requires frequency_hz,magnitude_db columns")
    rows = list(reader)
    return {"rows": rows, "columns": reader.fieldnames}


def extract_payload(metadata: dict[str, Any]) -> dict[str, list[float]]:
    frequency: list[float] = []
    magnitude: list[float] = []
    try:
        for row in metadata["rows"]:
            frequency.append(float(row["frequency_hz"]))
            magnitude.append(float(row["magnitude_db"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ParserError("CSV contains a malformed numeric row") from exc
    return {"frequency_hz": frequency, "magnitude_db": magnitude}


def normalize(metadata: dict[str, Any], payload: dict[str, list[float]]) -> dict[str, Any]:
    return {"kind": "spectrum", "columns": metadata["columns"], **payload}


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    axis = artifact["frequency_hz"]
    values = artifact["magnitude_db"]
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    equal = len(axis) == len(values) and bool(axis)
    checks.append(check("axis_value_lengths_match", "pass" if equal else "fail", {"axis": len(axis), "values": len(values)}))
    if not equal:
        reasons.append("axis_value_length_mismatch")
    monotonic = axis == sorted(axis)
    checks.append(check("frequency_axis_monotonic", "pass" if monotonic else "fail"))
    if not monotonic:
        reasons.append("frequency_axis_not_monotonic")
    unique = len(axis) == len(set(axis))
    checks.append(check("frequency_points_unique", "pass" if unique else "fail"))
    if not unique:
        reasons.append("duplicate_frequency_point")
    status = "COMPLETE" if not reasons else "INVALID"
    return report(status, checks, reasons, {"raw_sha256": sha256(raw), "point_count": len(axis)}, {"example": "analyzer_csv_sweep", "support_level": "documented"})


def parse(raw: bytes) -> dict[str, Any]:
    frame = read_frame(raw)
    metadata = parse_metadata(frame)
    payload = extract_payload(metadata)
    artifact = normalize(metadata, payload)
    artifact["integrity"] = validate(artifact, raw)
    return artifact
