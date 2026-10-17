#!/usr/bin/env python3
"""Small parser template for a length-prefixed scalar response.

Replace this example framing and fields with the target instrument format. Keep
the stage boundaries and return statuses; do not copy the example wire format as
if it were a vendor standard.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


class ParserError(ValueError):
    """Raised for structurally invalid parser input."""


@dataclass(frozen=True)
class Frame:
    prefix: bytes
    header: bytes
    payload: bytes
    trailing: bytes


def read_frame(raw: bytes) -> Frame:
    """Read ``#<4 decimal length><payload>`` without decoding payload bytes."""

    marker = raw.find(b"#")
    if marker < 0:
        raise ParserError("frame marker '#' was not found")
    length_start = marker + 1
    length_end = length_start + 4
    if len(raw) < length_end:
        raise ParserError("truncated length field")
    length_bytes = raw[length_start:length_end]
    if not length_bytes.isdigit():
        raise ParserError(f"invalid length field: {length_bytes!r}")
    payload_length = int(length_bytes)
    payload_start = length_end
    payload_end = payload_start + payload_length
    if len(raw) < payload_end:
        raise ParserError(
            f"truncated payload: declared {payload_length}, received {len(raw) - payload_start}"
        )
    return Frame(
        prefix=raw[:marker],
        header=raw[marker:payload_start],
        payload=raw[payload_start:payload_end],
        trailing=raw[payload_end:],
    )


def parse_metadata(frame: Frame) -> dict[str, str]:
    """Parse the example metadata line; replace with manual-defined fields."""

    lines = frame.payload.splitlines()
    if not lines or not lines[0].startswith(b"META "):
        raise ParserError("metadata line is missing")
    metadata: dict[str, str] = {}
    for field in lines[0][5:].decode("ascii").split():
        key, separator, value = field.partition("=")
        if not separator or not key or not value:
            raise ParserError(f"invalid metadata field: {field!r}")
        metadata[key] = value
    return metadata


def extract_payload(frame: Frame) -> list[float]:
    """Extract example scalar values; retain raw bytes before this conversion."""

    lines = frame.payload.splitlines()
    if len(lines) < 2 or not lines[1].startswith(b"DATA "):
        raise ParserError("data line is missing")
    try:
        return [float(token) for token in lines[1][5:].split()]
    except ValueError as exc:
        raise ParserError("data contains a non-numeric value") from exc


def normalize(metadata: dict[str, str], values: list[float]) -> dict[str, Any]:
    """Create a small normalized scalar-measurement artifact."""

    return {
        "kind": metadata.get("kind", "unknown"),
        "unit": metadata.get("unit"),
        "values": values,
        "declared_count": int(metadata["count"]) if "count" in metadata else None,
    }


def validate(artifact: dict[str, Any], *, raw: bytes, trailing: bytes = b"") -> dict[str, Any]:
    """Validate only claims supported by the example response."""

    reasons: list[str] = []
    declared_count = artifact.get("declared_count")
    actual_count = len(artifact.get("values", []))
    if declared_count is None:
        reasons.append("declared_count_missing")
    elif declared_count != actual_count:
        reasons.append("declared_count_does_not_match_values")
    if not artifact.get("unit"):
        reasons.append("unit_missing")
    status = "COMPLETE" if not reasons else "INCOMPLETE"
    if trailing:
        reasons.append("trailing_bytes_present")
        status = "UNVERIFIED"
    return {
        "status": status,
        "reasons": reasons,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "declared_count": declared_count,
        "actual_count": actual_count,
    }


def parse(raw: bytes) -> dict[str, Any]:
    """Run all parser stages and return normalized data plus validation evidence."""

    frame = read_frame(raw)
    metadata = parse_metadata(frame)
    values = extract_payload(frame)
    artifact = normalize(metadata, values)
    artifact["integrity"] = validate(artifact, raw=raw, trailing=frame.trailing)
    artifact["metadata"] = metadata
    return artifact
