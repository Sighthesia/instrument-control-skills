from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _example_support import check, report, sha256  # noqa: E402


class ParserError(ValueError):
    pass


def read_frame(raw: bytes) -> list[str]:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ParserError("segment record is not ASCII") from exc
    lines = [line for line in text.splitlines() if line]
    if not lines:
        raise ParserError("segment record is empty")
    return lines


def parse_metadata(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        fields = line.split("|")
        if len(fields) != 5 or fields[0] != "SEG":
            raise ParserError("malformed segment header")
        try:
            records.append({"sequence": int(fields[1]), "start": int(fields[2]), "count": int(fields[3]), "hex": fields[4]})
        except ValueError as exc:
            raise ParserError("segment metadata is not numeric") from exc
    return records


def extract_payload(records: list[dict[str, Any]]) -> list[bytes]:
    try:
        return [bytes.fromhex(record["hex"]) for record in records]
    except ValueError as exc:
        raise ParserError("segment payload is not hexadecimal") from exc


def normalize(records: list[dict[str, Any]], payloads: list[bytes]) -> dict[str, Any]:
    return {"kind": "waveform", "segments": [{**record, "payload_hex": payload.hex()} for record, payload in zip(records, payloads)]}


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    segments = artifact["segments"]
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    sequences = [segment["sequence"] for segment in segments]
    unique_sequences = len(sequences) == len(set(sequences))
    checks.append(check("sequence_unique", "pass" if unique_sequences else "fail", {"sequences": sequences}))
    if not unique_sequences:
        reasons.append("duplicate_sequence")
    ordered = sequences == list(range(len(sequences)))
    checks.append(check("sequence_ordered", "pass" if ordered else "fail"))
    if not ordered:
        reasons.append("sequence_gap_or_reordering")
    ranges_ok = True
    expected_start = 0
    total_payload = 0
    for segment in segments:
        payload = bytes.fromhex(segment["payload_hex"])
        expected_bytes = segment["count"]
        if segment["start"] != expected_start or len(payload) != expected_bytes:
            ranges_ok = False
        expected_start = segment["start"] + segment["count"]
        total_payload += len(payload)
    checks.append(check("ranges_contiguous_and_payload_lengths_match", "pass" if ranges_ok else "fail", {"points": expected_start, "payload_bytes": total_payload}))
    if not ranges_ok:
        reasons.append("segment_gap_overlap_or_short_payload")
    status = "COMPLETE" if not reasons else "INVALID"
    return report(status, checks, reasons, {"raw_sha256": sha256(raw), "segment_count": len(segments), "point_count": expected_start}, {"example": "segmented_binary_records", "support_level": "documented"})


def parse(raw: bytes) -> dict[str, Any]:
    lines = read_frame(raw)
    records = parse_metadata(lines)
    payloads = extract_payload(records)
    artifact = normalize(records, payloads)
    artifact["integrity"] = validate(artifact, raw)
    return artifact
