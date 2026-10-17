from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _example_support import check, report, sha256  # noqa: E402


class ParserError(ValueError):
    pass


def read_frame(raw: bytes) -> dict[str, Any]:
    marker = raw.find(b"#")
    if marker < 0 or len(raw) < marker + 2:
        raise ParserError("IEEE block marker or length digit is missing")
    digits_byte = raw[marker + 1 : marker + 2]
    if not digits_byte.isdigit() or digits_byte == b"0":
        raise ParserError("invalid IEEE length-of-length")
    digits = int(digits_byte)
    length_start = marker + 2
    length_end = length_start + digits
    if len(raw) < length_end:
        raise ParserError("truncated IEEE payload length")
    length_bytes = raw[length_start:length_end]
    if not length_bytes.isdigit():
        raise ParserError("invalid IEEE payload length")
    payload_length = int(length_bytes)
    payload_start = length_end
    payload_end = payload_start + payload_length
    if len(raw) < payload_end:
        raise ParserError("truncated IEEE payload")
    return {"prefix": raw[:marker], "header": raw[marker:payload_start], "payload": raw[payload_start:payload_end], "trailing": raw[payload_end:]}


def parse_metadata(frame: dict[str, Any]) -> dict[str, Any]:
    line, _, _ = frame["payload"].partition(b"\n")
    if not line.startswith(b"META "):
        raise ParserError("waveform metadata is missing")
    fields: dict[str, Any] = {}
    for token in line[5:].split():
        key, separator, value = token.partition(b"=")
        if not separator:
            raise ParserError("malformed waveform metadata")
        text = value.decode("ascii")
        fields[key.decode("ascii")] = int(text) if key in {b"points", b"bytes_per_point"} else float(text) if key == b"interval_s" else text
    return fields


def extract_payload(frame: dict[str, Any]) -> bytes:
    _, separator, data_line = frame["payload"].partition(b"\n")
    if not separator or not data_line.endswith(b"\n") or not data_line.startswith(b"DATA "):
        raise ParserError("waveform data line is missing")
    return data_line[5:-1]


def normalize(metadata: dict[str, Any], payload: bytes) -> dict[str, Any]:
    return {"kind": "waveform", "sample_count": metadata.get("points"), "bytes_per_point": metadata.get("bytes_per_point"), "sample_interval_s": metadata.get("interval_s"), "unit": metadata.get("unit"), "raw_payload_hex": payload.hex()}


def validate(artifact: dict[str, Any], raw: bytes, frame: dict[str, Any]) -> dict[str, Any]:
    points = artifact.get("sample_count")
    width = artifact.get("bytes_per_point")
    payload = bytes.fromhex(artifact["raw_payload_hex"])
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    if not isinstance(points, int) or not isinstance(width, int) or points < 0 or width <= 0:
        checks.append(check("metadata_is_valid", "fail", reason="point count or element width is invalid"))
        reasons.append("invalid_waveform_metadata")
        status = "INVALID"
    else:
        checks.append(check("metadata_is_valid", "pass", {"points": points, "bytes_per_point": width}))
        expected = points * width
        actual = len(payload)
        if expected == actual:
            checks.append(check("declared_payload_length_matches", "pass", {"expected_bytes": expected, "actual_bytes": actual}))
            status = "COMPLETE"
        else:
            checks.append(check("declared_payload_length_matches", "fail", {"expected_bytes": expected, "actual_bytes": actual}))
            reasons.append("payload_length_mismatch")
            status = "INCOMPLETE" if actual < expected else "INVALID"
    checks.append(check("voltage_calibration", "not_checked", reason="synthetic raw codes have no calibration evidence"))
    if frame["trailing"]:
        checks.append(check("trailing_bytes_absent", "fail", {"trailing_bytes": len(frame["trailing"])}))
        reasons.append("trailing_bytes_present")
        status = "UNVERIFIED" if status == "COMPLETE" else status
    return report(status, checks, reasons, {"raw_sha256": sha256(raw), "payload_bytes": len(payload), "trailing_bytes": len(frame["trailing"])}, {"example": "oscilloscope_ieee_block", "support_level": "replay-tested"}, ["calibration_status=UNVERIFIED"])


def parse(raw: bytes) -> dict[str, Any]:
    frame = read_frame(raw)
    metadata = parse_metadata(frame)
    payload = extract_payload(frame)
    artifact = normalize(metadata, payload)
    artifact["integrity"] = validate(artifact, raw, frame)
    return artifact
