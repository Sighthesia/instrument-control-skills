#!/usr/bin/env python3
"""Offline parsers for the GW Instek GDS-2000A series oscilloscope.

The module is transport-independent: it never opens a socket or serial port.
It preserves raw response bytes as SHA-256 evidence, separates framing,
metadata, payload extraction, normalization, and validation, and reports
conservative integrity statuses.

Manual: GDS-2000A Series Programming Manual, Version 1.4, August 2013.
The local evidence copy is a converted text file, so only page numbers from
its table of contents and List of Commands (pp. 24-34) are cited.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import re
import struct
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

PARSER_NAME = "gds2000a-protocol"
PARSER_VERSION = "0.1.0"
MAX_LINE_BYTES = 65_536
MAX_HEADER_BYTES = 65_536
MAX_POINTS = 10_000_000
MAX_PAYLOAD_BYTES = MAX_POINTS * 2
MAX_INLINE_SAMPLES = 1_000_000

_MODEL_RE = re.compile(r"^GDS-\d{4}A$", re.IGNORECASE)
_ERROR_QUEUE_RE = re.compile(r"^\s*(?P<code>[+-]?\d+)\s*,\s*(?P<message>.+?)\s*$")
_NUMERIC_RE = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(?P<unit>[A-Za-z%°µμμ]+)?$"
)
_QUOTES = "\"'“”‘’"

# Literal non-values are matched before any numeric conversion.  The `9.9E+37`
# token was observed on a GDS-2104A V1.18 when a slotted measurement was off;
# the manual does not document it.
MEASUREMENT_SENTINELS = {
    "ch off": ("source_channel_not_activated", "INCOMPLETE"),
    "chan off": ("source_channel_not_activated", "INCOMPLETE"),
    "9.9e+37": ("instrument_no_result", "INCOMPLETE"),
    "9.9e37": ("instrument_no_result", "INCOMPLETE"),
}

MEASUREMENT_UNITS = {
    "frequency": "Hz",
    "period": "s",
    "rise": "s",
    "fall": "s",
    "width": "s",
    "nwidth": "s",
    "pwidth": "s",
    "duty": "%",
    "pduty": "%",
    "amplitude": "V or A",
    "mean": "V or A",
    "cmean": "V or A",
    "high": "V or A",
    "low": "V or A",
    "max": "V or A",
    "min": "V or A",
    "pk2pk": "V or A",
    "rms": "V or A",
    "area": "V·s or A·s",
    "carea": "V·s or A·s",
    "overshoot": "%",
    "preshoot": "%",
    "fovshoot": "%",
    "fpreshoot": "%",
    "rovshoot": "%",
    "rpreshoot": "%",
    "phase": "deg",
    "delay": "s",
    "frrdelay": "s",
    "frfdelay": "s",
    "ffrdelay": "s",
    "fffdelay": "s",
    "lrrdelay": "s",
    "lrfdelay": "s",
    "lfrdelay": "s",
    "lffdelay": "s",
    "ppulse": None,
    "npulse": None,
    "pedge": None,
    "nedge": None,
}

MEASUREMENT_ALIASES = {
    "vpp": "pk2pk",
    "freq": "frequency",
    "trise": "rise",
    "tfall": "fall",
}

SOURCE_DEPENDENT_QUANTITIES = {
    "amplitude",
    "mean",
    "cmean",
    "high",
    "low",
    "max",
    "min",
    "pk2pk",
    "rms",
}
AREA_QUANTITIES = {"area", "carea"}
COUNT_QUANTITIES = {"ppulse", "npulse", "pedge", "nedge"}

MEASUREMENT_COMMANDS = {
    "frequency": ":MEASure:FREQuency?",
    "period": ":MEASure:PERiod?",
    "rise": ":MEASure:RISe?",
    "fall": ":MEASure:FALL?",
    "width": ":MEASure:PWIDth?",
    "nwidth": ":MEASure:NWIDth?",
    "pwidth": ":MEASure:PWIDth?",
    "duty": ":MEASure:PDUTy?",
    "pduty": ":MEASure:PDUTy?",
    "amplitude": ":MEASure:AMPlitude?",
    "mean": ":MEASure:MEAN?",
    "cmean": ":MEASure:CMEan?",
    "high": ":MEASure:HIGH?",
    "low": ":MEASure:LOW?",
    "max": ":MEASure:MAX?",
    "min": ":MEASure:MIN?",
    "pk2pk": ":MEASure:PK2PK?",
    "rms": ":MEASure:RMS?",
    "area": ":MEASure:AREa?",
    "carea": ":MEASure:CARea?",
    "overshoot": ":MEASure:ROVShoot?",
    "preshoot": ":MEASure:RPReshoot?",
    "fovshoot": ":MEASure:FOVShoot?",
    "fpreshoot": ":MEASure:FPReshoot?",
    "rovshoot": ":MEASure:ROVShoot?",
    "rpreshoot": ":MEASure:RPReshoot?",
    "phase": ":MEASure:PHAse?",
    "delay": ":MEASure:FRRDelay?",
    "frrdelay": ":MEASure:FRRDelay?",
    "frfdelay": ":MEASure:FRFDelay?",
    "ffrdelay": ":MEASure:FFRDelay?",
    "fffdelay": ":MEASure:FFFDelay?",
    "lrrdelay": ":MEASure:LRRDelay?",
    "lrfdelay": ":MEASure:LFRDelay?",
    "lfrdelay": ":MEASure:LFRDelay?",
    "lffdelay": ":MEASure:LFFDelay?",
    "ppulse": ":MEASure:PPULSE?",
    "npulse": ":MEASure:NPULSE?",
    "pedge": ":MEASure:PEDGE?",
    "nedge": ":MEASure:NEDGE?",
}


class ProtocolError(ValueError):
    """A protocol failure with a conservative integrity classification."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Frame:
    """One line response and its byte-exact framing evidence."""

    content: bytes
    terminator: bytes
    trailing: bytes = b""


@dataclass(frozen=True)
class IEEEBlock:
    """One definite-length IEEE 488.2 block."""

    header: bytes
    declared_length: int
    payload: bytes
    trailing: bytes = b""


def _check(name: str, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _raw_evidence(raw: bytes, *, include_base64: bool = True) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
    }
    if include_base64:
        evidence["raw_response_base64"] = base64.b64encode(raw).decode("ascii")
    return evidence


def _support_level(provenance: str) -> str:
    if provenance == "hardware-verified":
        return "hardware-verified"
    return "documented"


def _check_provenance(provenance: str) -> None:
    if provenance not in {"documented", "synthetic", "hardware-verified"}:
        raise ProtocolError(
            "provenance must be documented, synthetic, or hardware-verified",
            "INVALID",
        )


def read_frame(raw: bytes) -> Frame:
    """Read one LF/CR/CRLF/LFCR-terminated line.

    Trailing bytes are rejected unless they are additional CR/LF characters.
    The GDS-2104A returned a double LF to `:TRIGger:FREQuency?`; that is kept
    as framing evidence rather than treated as a second response.
    """

    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("response must be bytes", "INVALID")
    raw = bytes(raw)
    if len(raw) > MAX_LINE_BYTES:
        raise ProtocolError("response exceeds the line-parser size limit", "UNSUPPORTED")
    if not raw:
        raise ProtocolError("response is empty", "INCOMPLETE")
    if raw.startswith(b"#"):
        raise ProtocolError("binary block data is not a line response", "UNSUPPORTED")

    positions = [position for delimiter in (b"\r", b"\n") if (position := raw.find(delimiter)) >= 0]
    if not positions:
        raise ProtocolError("response has no line terminator", "INCOMPLETE")

    start = min(positions)
    first = raw[start : start + 1]
    second = raw[start + 1 : start + 2]
    if first == b"\r" and second == b"\n":
        terminator = b"\r\n"
    elif first == b"\n" and second == b"\r":
        terminator = b"\n\r"
    else:
        terminator = first

    end = start + len(terminator)
    trailing = raw[end:]
    if trailing.strip(b"\r\n \t"):
        raise ProtocolError("extra non-whitespace bytes follow the response line", "INVALID")
    return Frame(content=raw[:start], terminator=terminator, trailing=trailing)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains invalid text bytes", "INVALID") from exc


def _is_identity_line(line: str) -> bool:
    parts = [part.strip() for part in line.split(",")]
    return len(parts) in {3, 4} and bool(_MODEL_RE.fullmatch(parts[1]))


def parse_metadata(frame: Frame, *, response_type: str = "auto") -> dict[str, Any]:
    """Decode one line and classify identity, measurement, or error-queue tokens."""

    if response_type not in {"auto", "identity", "measurement", "error-queue"}:
        raise ProtocolError(
            "response_type must be auto, identity, measurement, or error-queue",
            "INVALID",
        )

    line = _text(frame)
    if not line:
        raise ProtocolError("response line is empty", "INCOMPLETE")

    if response_type == "auto":
        if _ERROR_QUEUE_RE.fullmatch(line):
            response_type = "error-queue"
        elif _is_identity_line(line):
            response_type = "identity"
        elif line.casefold() in MEASUREMENT_SENTINELS or _NUMERIC_RE.fullmatch(line):
            response_type = "measurement"
        else:
            raise ProtocolError(
                "automatic classification could not identify the response shape",
                "UNSUPPORTED",
            )
        mode = "auto"
    else:
        mode = "explicit"

    if response_type == "identity":
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 3:
            # A three-field reply is a missing firmware field, not a different
            # response shape; keep the position so normalization reports it as
            # INCOMPLETE instead of inventing a value.
            parts.append("")
        if len(parts) != 4:
            raise ProtocolError("identity response must have three or four comma-separated fields", "INVALID")
        return {"response_type": "identity", "line": line, "fields": parts, "mode": mode}

    if response_type == "measurement":
        if line.casefold() in MEASUREMENT_SENTINELS:
            return {
                "response_type": "measurement",
                "line": line,
                "sentinel": line.casefold(),
                "numeric_token": None,
                "raw_unit": None,
                "mode": mode,
            }
        match = _NUMERIC_RE.fullmatch(line)
        if not match:
            if re.search(r"\b(?:NAN|INF(?:INITY)?)\b", line, re.IGNORECASE):
                raise ProtocolError("non-finite measurement response", "INVALID")
            raise ProtocolError("response is not a supported NR3 measurement", "INVALID")
        return {
            "response_type": "measurement",
            "line": line,
            "sentinel": None,
            "numeric_token": match.group("number"),
            "raw_unit": match.group("unit"),
            "mode": mode,
        }

    match = _ERROR_QUEUE_RE.fullmatch(line)
    if not match:
        raise ProtocolError("error-queue response must be code, message", "INVALID")
    message_raw = match.group("message").strip()
    if not message_raw:
        raise ProtocolError("error-queue message is empty", "INVALID")
    quoted = message_raw[0] in _QUOTES
    if quoted:
        pairs = {'"': '"', "'": "'", "“": "”", "‘": "’"}
        opening = message_raw[0]
        closing = pairs.get(opening)
        if closing is None or len(message_raw) < 2 or message_raw[-1] != closing:
            raise ProtocolError("error-queue message has an unterminated quote", "INVALID")
        message = message_raw[1:-1].strip()
    else:
        message = message_raw
    return {
        "response_type": "error-queue",
        "line": line,
        "code": int(match.group("code")),
        "message": message,
        "quoted": quoted,
        "mode": mode,
    }


def extract_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    """Expose raw fields without unit conversion or semantic classification."""

    response_type = metadata.get("response_type")
    if response_type == "identity":
        fields = metadata["fields"]
        return {
            "vendor": fields[0],
            "model": fields[1],
            "serial": fields[2],
            "firmware": fields[3],
        }
    if response_type == "measurement":
        return {
            "sentinel": metadata["sentinel"],
            "numeric_token": metadata["numeric_token"],
            "raw_unit": metadata["raw_unit"],
        }
    if response_type == "error-queue":
        return {
            "code": metadata["code"],
            "message": metadata["message"],
            "quoted": metadata.get("quoted", False),
        }
    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED")


def normalize(
    metadata: dict[str, Any],
    payload: dict[str, Any],
    *,
    quantity: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Normalize extracted fields; semantic failures raise ProtocolError."""

    response_type = metadata.get("response_type")

    if response_type == "identity":
        vendor = payload["vendor"].strip()
        model = payload["model"].strip().upper()
        serial = payload["serial"].strip()
        firmware = payload["firmware"].strip()

        if vendor.upper() != "GW":
            raise ProtocolError(f"unexpected vendor {vendor!r}", "INVALID")
        if not _MODEL_RE.fullmatch(model):
            raise ProtocolError(f"not a GDS-2000A model {model!r}", "INVALID")
        if not serial:
            raise ProtocolError("serial number is missing", "INCOMPLETE")
        if not re.fullmatch(r"P?[0-9A-Za-z]+", serial, re.IGNORECASE):
            raise ProtocolError(f"unexpected serial field {serial!r}", "INVALID")
        if not firmware:
            raise ProtocolError("firmware version is missing", "INCOMPLETE")
        if not re.fullmatch(r"V\d+\.[0-9A-Za-z]+", firmware, re.IGNORECASE):
            raise ProtocolError(f"malformed firmware version {firmware!r}", "INVALID")

        channels = 4 if model[-2] == "4" else 2
        return {
            "schema_version": "gds2000a-protocol-v1",
            "kind": "identity",
            "vendor": "GW",
            "model": model,
            "serial": serial,
            "firmware": firmware,
            "identity": {
                "vendor": "GW",
                "model": model,
                "serial": serial,
                "firmware": firmware,
            },
            "profile": {
                "channels": channels,
                "channel_count_source": "inferred from the model number's last digit",
            },
            "status": "COMPLETE",
            "checks": [_check("identity_parse", "pass", {"model": model})],
            "reasons": [],
        }

    if response_type == "measurement":
        if payload["sentinel"] is not None:
            reason, status = MEASUREMENT_SENTINELS[payload["sentinel"]]
            raise ProtocolError(reason, status)
        if not isinstance(quantity, str) or not quantity.strip():
            raise ProtocolError("quantity is required for measurement normalization", "INVALID")

        token = payload["numeric_token"]
        suffix = payload["raw_unit"]
        if suffix:
            raise ProtocolError("measurement response must not carry a unit suffix", "INVALID")
        try:
            value = Decimal(token)
        except (InvalidOperation, TypeError) as exc:
            raise ProtocolError("measurement token is not valid", "INVALID") from exc
        if not value.is_finite():
            raise ProtocolError("non-finite measurement response", "INVALID")

        quantity_key = MEASUREMENT_ALIASES.get(quantity.lower().strip(), quantity.lower().strip())
        if quantity_key not in MEASUREMENT_UNITS:
            raise ProtocolError(f"unsupported measurement quantity {quantity!r}", "INVALID")

        if quantity_key in COUNT_QUANTITIES:
            display_unit = None
            unit_status = "unitless"
        elif quantity_key in AREA_QUANTITIES:
            display_unit = "V·s or A·s"
            unit_status = "source-dependent"
        elif quantity_key in SOURCE_DEPENDENT_QUANTITIES:
            display_unit = "V or A"
            unit_status = "source-dependent"
        else:
            display_unit = MEASUREMENT_UNITS[quantity_key]
            unit_status = "documented"

        if unit is not None:
            if quantity_key in COUNT_QUANTITIES:
                raise ProtocolError("count measurements are unitless", "INVALID")
            if unit.strip() not in {"V", "A", "%", "Hz", "s", "deg", "V·s", "A·s"}:
                raise ProtocolError(f"unsupported supplied unit {unit!r}", "INVALID")
            display_unit = unit.strip()
            unit_status = "caller-supplied"

        try:
            raw_float = float(value)
        except (OverflowError, ValueError) as exc:
            raise ProtocolError("measurement value is outside the supported finite range", "INVALID") from exc
        if not math.isfinite(raw_float):
            raise ProtocolError("measurement value is outside the supported finite range", "INVALID")

        return {
            "schema_version": "gds2000a-protocol-v1",
            "kind": "scalar-measurement",
            "quantity": quantity_key,
            "command": MEASUREMENT_COMMANDS[quantity_key],
            "value": raw_float,
            "raw_value": raw_float,
            "numeric_token": token,
            "unit": display_unit,
            "unit_status": unit_status,
            "raw_unit": suffix,
            "status": "COMPLETE",
            "checks": [_check("measurement_parse", "pass", {"token": token, "unit": display_unit})],
            "reasons": [],
        }

    if response_type == "error-queue":
        code = payload["code"]
        message = payload["message"]
        normalized_message = message.strip().strip(_QUOTES).strip().rstrip(".").casefold()

        if code == 0 and normalized_message == "no error":
            status = "COMPLETE"
            reasons: list[str] = []
        elif abs(code) == 350 and "queue overflow" in normalized_message:
            status = "INCOMPLETE"
            reasons = ["instrument_error_queue_overflow"]
        else:
            status = "UNVERIFIED"
            reasons = ["instrument_reported_error_or_status"]

        return {
            "schema_version": "gds2000a-protocol-v1",
            "kind": "status-record",
            "record_type": "error-queue",
            "code": code,
            "message": message,
            "quoted": payload.get("quoted", False),
            "status": status,
            "checks": [_check("error_queue_record", "pass", {"code": code})],
            "reasons": reasons,
        }

    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED")


def validate(artifact: dict[str, Any], raw: bytes, *, provenance: str = "documented") -> dict[str, Any]:
    """Attach raw evidence and the integrity block to a normalized artifact."""

    _check_provenance(provenance)
    artifact = dict(artifact)
    status = artifact.get("status")
    if status not in {"COMPLETE", "INCOMPLETE", "INVALID", "UNVERIFIED", "UNSUPPORTED"}:
        raise ProtocolError("artifact has no supported integrity status", "INVALID")
    checks = artifact.pop("checks", [])
    reasons = artifact.pop("reasons", [])
    artifact["integrity"] = {
        "status": status,
        "checks": checks,
        "reasons": reasons,
        **_raw_evidence(raw),
        "input_provenance": provenance,
        "support_level": _support_level(provenance),
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
    }
    return artifact


def _failure(
    kind: str,
    raw: bytes,
    status: str,
    reason: str,
    *,
    provenance: str,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "schema_version": "gds2000a-protocol-v1",
        "kind": kind,
        **fields,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [_check(f"{kind}_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_raw_evidence(raw),
            "input_provenance": provenance,
            "support_level": _support_level(provenance),
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def parse_identity(raw: bytes, *, provenance: str = "documented") -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw, provenance=provenance)
    except ProtocolError as exc:
        return _failure("identity", raw, exc.status, str(exc), provenance=provenance)


def parse_measurement(
    raw: bytes,
    *,
    quantity: str,
    unit: str | None = None,
    provenance: str = "documented",
) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="measurement")
        artifact = normalize(metadata, extract_payload(metadata), quantity=quantity, unit=unit)
        return validate(artifact, raw, provenance=provenance)
    except ProtocolError as exc:
        return _failure(
            "scalar-measurement",
            raw,
            exc.status,
            str(exc),
            provenance=provenance,
            quantity=quantity,
            value=None,
            raw_value=None,
            numeric_token=None,
            sentinel=None,
            unit=None,
            raw_unit=None,
        )


def parse_error_queue(raw: bytes, *, provenance: str = "documented") -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="error-queue")
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw, provenance=provenance)
    except ProtocolError as exc:
        return _failure(
            "unknown",
            raw,
            exc.status,
            str(exc),
            provenance=provenance,
            record_type="error-queue",
            code=None,
            message=None,
        )


def drain_error_queue(
    responses: list[bytes],
    *,
    provenance: str = "documented",
) -> dict[str, Any]:
    """Normalize a sequence of `:SYSTem:ERRor?` replies through the first +0."""

    records = [parse_error_queue(raw, provenance=provenance) for raw in responses]
    complete = any(record.get("code") == 0 for record in records)
    return {
        "schema_version": "gds2000a-protocol-v1",
        "kind": "status-record",
        "record_type": "error-queue-drain",
        "records": records,
        "complete": complete,
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "reasons": [] if complete else ["no_no_error_record_observed"],
    }


# ---------------------------------------------------------------------------
# Waveform block parsing
# ---------------------------------------------------------------------------


def parse_ieee_block(raw: bytes, *, allow_terminator: bool = False) -> IEEEBlock:
    """Parse one definite-length IEEE 488.2 block.

    Extra bytes are rejected unless they are a single LF, CR, CRLF, or LFCR and
    ``allow_terminator`` is set.
    """

    raw = bytes(raw)
    if not raw or raw[:1] != b"#":
        raise ProtocolError("IEEE block is missing the # prefix", "INVALID")
    if len(raw) < 2 or not raw[1:2].isdigit():
        raise ProtocolError("IEEE block is missing the digit count", "INVALID")
    digit_count = int(raw[1:2])
    if digit_count == 0:
        raise ProtocolError("indefinite IEEE blocks are not supported", "UNSUPPORTED")
    if len(raw) < 2 + digit_count:
        raise ProtocolError("IEEE block header is truncated", "INCOMPLETE")
    length_text = raw[2 : 2 + digit_count]
    if not length_text.isdigit():
        raise ProtocolError("IEEE block length field is not numeric", "INVALID")
    declared_length = int(length_text)
    if declared_length > MAX_PAYLOAD_BYTES:
        raise ProtocolError("IEEE payload exceeds the waveform size limit", "UNSUPPORTED")
    header_end = 2 + digit_count
    payload_end = header_end + declared_length
    if len(raw) < payload_end:
        raise ProtocolError(
            f"IEEE payload is truncated: declared {declared_length}, received {len(raw) - header_end}",
            "INCOMPLETE",
        )
    payload = raw[header_end:payload_end]
    trailing = raw[payload_end:]
    if trailing and not (allow_terminator and trailing in {b"\n", b"\r", b"\r\n", b"\n\r"}):
        raise ProtocolError("extra bytes follow the IEEE payload", "INVALID")
    return IEEEBlock(
        header=raw[:header_end],
        declared_length=declared_length,
        payload=payload,
        trailing=trailing,
    )


def encode_ieee_block(payload: bytes) -> bytes:
    """Encode one definite-length IEEE 488.2 block (used by tests/fixtures)."""

    if not isinstance(payload, (bytes, bytearray)):
        raise ProtocolError("IEEE block payload must be bytes", "INVALID")
    payload = bytes(payload)
    if not payload:
        raise ProtocolError("IEEE block payload must not be empty", "INVALID")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError("IEEE block payload is too large", "UNSUPPORTED")
    length_text = str(len(payload))
    return b"#" + str(len(length_text)).encode("ascii") + length_text.encode("ascii") + payload


def _parse_header_fields(header_text: str) -> tuple[dict[str, str], dict[str, str]]:
    header: dict[str, str] = {}
    header_norm: dict[str, str] = {}

    if ";" in header_text:
        parts = [part.strip() for part in header_text.split(";") if part.strip()]
        pairs: list[tuple[str, str]] = []
        for part in parts:
            if "," not in part:
                raise ProtocolError(f"header field has no comma: {part!r}", "INVALID")
            name, value = part.split(",", 1)
            pairs.append((name, value))
    else:
        tokens = [token.strip() for token in header_text.split(",")]
        if len(tokens) % 2:
            raise ProtocolError(
                "comma-separated header has an odd token count; cannot pair names and values",
                "UNVERIFIED",
            )
        pairs = list(zip(tokens[0::2], tokens[1::2]))

    for name, value in pairs:
        name = name.strip()
        key = " ".join(name.lower().split())
        if not key:
            raise ProtocolError("header field has an empty name", "INVALID")
        if key in header_norm:
            raise ProtocolError(f"duplicate header field {name!r}", "INVALID")
        header[name] = value.strip()
        header_norm[key] = value.strip()
    return header, header_norm


def parse_waveform_header(raw: bytes) -> dict[str, Any]:
    """Separate the ASCII acquisition header from the raw waveform block."""

    raw = bytes(raw)
    if not raw:
        raise ProtocolError("waveform response is empty", "INCOMPLETE")

    if raw.startswith(b"#"):
        block = parse_ieee_block(raw, allow_terminator=True)
        return {
            "header_text": None,
            "header": {},
            "header_norm": {},
            "header_present": False,
            "headerless": True,
            "marker": None,
            "separator": b"",
            "block": block,
            "points": block.declared_length // 2,
        }

    marker_index = raw.find(b"Waveform Data;")
    if marker_index < 0:
        raise ProtocolError("waveform response has no 'Waveform Data;' marker", "INVALID")
    if marker_index > MAX_HEADER_BYTES:
        raise ProtocolError("waveform ASCII header is too large", "UNSUPPORTED")
    header_bytes = raw[:marker_index]
    try:
        header_text = header_bytes.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("waveform header contains non-ASCII bytes", "INVALID") from exc

    after_marker = marker_index + len(b"Waveform Data;")
    hash_index = raw.find(b"#", after_marker)
    if hash_index < 0:
        raise ProtocolError("waveform block does not start with #", "INVALID")
    separator = raw[after_marker:hash_index]
    if separator.strip(b" \r\n\t"):
        raise ProtocolError("unexpected bytes between header marker and block", "INVALID")
    block = parse_ieee_block(raw[hash_index:], allow_terminator=True)
    header, header_norm = _parse_header_fields(header_text)

    return {
        "header_text": header_text,
        "header": header,
        "header_norm": header_norm,
        "header_present": True,
        "headerless": False,
        "marker": "Waveform Data;",
        "separator": separator,
        "block": block,
        "points": block.declared_length // 2,
    }


def iter_samples(payload: bytes, *, byte_order: str = "little") -> Iterator[int]:
    """Yield signed 16-bit samples from a waveform payload.

    The manual does not state byte order.  The GDS-2104A capture is consistent
    with little-endian signed 16-bit codes; big-endian interpretation produces
    codes far outside the displayed range.  The choice is therefore recorded as
    observed, not documented.
    """

    if len(payload) % 2:
        raise ProtocolError("waveform payload has an odd byte count", "INVALID")
    if byte_order not in {"little", "big"}:
        raise ProtocolError("byte_order must be little or big", "INVALID")
    fmt = "<h" if byte_order == "little" else ">h"
    for (code,) in struct.iter_unpack(fmt, payload):
        yield code


def _waveform_failure(
    raw: bytes,
    status: str,
    reason: str,
    *,
    provenance: str,
) -> dict[str, Any]:
    return _failure(
        "waveform",
        raw,
        status,
        reason,
        provenance=provenance,
        artifact="acquisition-memory",
        points=None,
        point_count=None,
        sample_encoding=None,
        calibration={"status": "UNVERIFIED", "reason": "waveform could not be parsed"},
        analysis_allowed="none",
    )


def parse_waveform(
    raw: bytes,
    *,
    include_samples: bool = False,
    sample_byte_order: str = "little",
    provenance: str = "documented",
) -> dict[str, Any]:
    """Parse an `:ACQuire<n>:MEMory?` response into a waveform artifact."""

    raw = bytes(raw)
    try:
        envelope = parse_waveform_header(raw)
    except ProtocolError as exc:
        return _waveform_failure(raw, exc.status, str(exc), provenance=provenance)

    block = envelope["block"]
    header = envelope["header"]
    header_norm = envelope["header_norm"]
    payload = block.payload

    if not payload:
        return _waveform_failure(raw, "INCOMPLETE", "waveform payload is empty", provenance=provenance)
    if len(payload) % 2:
        return _waveform_failure(raw, "INVALID", "waveform payload has an odd byte count", provenance=provenance)

    points = len(payload) // 2
    if points > MAX_POINTS:
        return _waveform_failure(raw, "UNSUPPORTED", "waveform exceeds 10,000,000 points", provenance=provenance)
    if include_samples and points > MAX_INLINE_SAMPLES:
        return _waveform_failure(
            raw,
            "UNSUPPORTED",
            "inline samples are limited to 1,000,000 points; use --csv-out",
            provenance=provenance,
        )

    checks: list[dict[str, Any]] = [
        _check(
            "ieee_block_length",
            "pass",
            {"declared_bytes": block.declared_length, "observed_bytes": len(payload)},
        ),
        _check("sample_width", "pass", {"bytes_per_point": 2}),
    ]
    reasons: list[str] = []
    status = "COMPLETE"

    declared_points_text = header_norm.get("memory length")
    declared_points: int | None = None
    if declared_points_text:
        try:
            declared_points = int(declared_points_text)
        except ValueError:
            return _waveform_failure(raw, "INVALID", "Memory Length is not an integer", provenance=provenance)
        if declared_points != points:
            return _waveform_failure(
                raw,
                "INVALID",
                f"declared Memory Length {declared_points} does not match {points} points",
                provenance=provenance,
            )
        checks.append(
            _check(
                "declared_points",
                "pass",
                {"declared_points": declared_points, "observed_points": points},
            )
        )
    else:
        if envelope["headerless"]:
            status = "UNVERIFIED"
            reasons.append("headerless_block_has_no_scale_or_units")
        else:
            return _waveform_failure(raw, "INCOMPLETE", "declared point count missing", provenance=provenance)

    vertical_scale: float | None = None
    if header_norm.get("vertical scale"):
        try:
            vertical_scale = float(header_norm["vertical scale"])
        except ValueError:
            return _waveform_failure(raw, "INVALID", "Vertical Scale is not numeric", provenance=provenance)
        if not math.isfinite(vertical_scale) or vertical_scale <= 0:
            return _waveform_failure(raw, "INVALID", "Vertical Scale is not finite positive", provenance=provenance)
        checks.append(_check("vertical_scale", "pass", {"value": vertical_scale}))
    else:
        if status == "COMPLETE":
            status = "UNVERIFIED"
        reasons.append("vertical_scale_missing")

    sampling_period: float | None = None
    if header_norm.get("sampling period"):
        try:
            sampling_period = float(header_norm["sampling period"])
        except ValueError:
            return _waveform_failure(raw, "INVALID", "Sampling Period is not numeric", provenance=provenance)
        if not math.isfinite(sampling_period) or sampling_period <= 0:
            return _waveform_failure(
                raw,
                "INVALID",
                "Sampling Period is not finite positive",
                provenance=provenance,
            )
        checks.append(_check("sampling_period", "pass", {"value": sampling_period}))
    else:
        reasons.append("sampling_period_missing")

    trigger_address: int | None = None
    if header_norm.get("trigger address"):
        try:
            trigger_address = int(header_norm["trigger address"])
        except ValueError:
            reasons.append("trigger_address_not_integer")

    samples: list[int] | None = list(iter_samples(payload, byte_order=sample_byte_order)) if include_samples else None
    code_min = code_max = None
    code_mean = None
    if points:
        if samples is not None:
            code_min = min(samples)
            code_max = max(samples)
            code_mean = sum(samples) / len(samples)
        else:
            total = 0
            code_min = 32768
            code_max = -32768
            for code in iter_samples(payload, byte_order=sample_byte_order):
                total += code
                if code < code_min:
                    code_min = code
                if code > code_max:
                    code_max = code
            code_mean = total / points

    artifact = {
        "schema_version": "gds2000a-protocol-v1",
        "kind": "waveform",
        "artifact": "acquisition-memory",
        "points": points,
        "point_count": points,
        "bytes_per_point": 2,
        "sample_encoding": "signed-16-bit",
        "sample_byte_order": sample_byte_order,
        "sample_byte_order_status": "observed",
        "sample_byte_order_note": "The manual does not state byte order; little-endian is inferred from the GDS-2104A capture.",
        "block_length": len(payload),
        "block_bytes": len(payload),
        "declared_block_bytes": block.declared_length,
        "trailing_bytes": len(block.trailing),
        "trailing_hex": block.trailing.hex(),
        "headerless": envelope["headerless"],
        "header_present": envelope["header_present"],
        "header": header,
        "header_text": envelope["header_text"],
        "source": header_norm.get("source"),
        "vertical_units": header_norm.get("vertical units"),
        "vertical_scale": vertical_scale,
        "sampling_period": sampling_period,
        "trigger_address": trigger_address,
        "firmware": header_norm.get("firmware"),
        "device_time": header_norm.get("time"),
        "code_min": code_min,
        "code_max": code_max,
        "code_mean": code_mean,
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "calibration": {
            "status": "UNVERIFIED",
            "vertical_scale": vertical_scale,
            "reason": "The programming manual does not document a code-to-volts conversion.",
        },
        "analysis_allowed": "code-domain-only",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
    }
    if samples is not None:
        artifact["samples"] = samples
    artifact["integrity"] = {
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "calibration": "UNVERIFIED",
        "analysis_allowed": "code-domain-only",
        "input_provenance": provenance,
        "support_level": _support_level(provenance),
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        "raw_sha256": artifact["raw_sha256"],
        "payload_sha256": artifact["payload_sha256"],
    }
    return artifact


def waveform_to_csv(raw: bytes, path: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    """Stream a waveform payload to `index,code` CSV without materializing samples."""

    artifact = parse_waveform(raw, include_samples=False)
    if artifact["status"] in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}:
        raise ProtocolError("waveform cannot be exported", artifact["status"])
    envelope = parse_waveform_header(bytes(raw))
    payload = envelope["block"].payload

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "code"])
        for index, code in enumerate(iter_samples(payload)):
            writer.writerow([index, code])
            hasher.update(f"{index},{code}\n".encode("ascii"))
    return {
        "path": str(destination),
        "csv_sha256": hasher.hexdigest(),
        "points": artifact["points"],
        "status": artifact["status"],
        "calibration": "UNVERIFIED",
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _read(path: str) -> bytes:
    return Path(path).read_bytes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    identity = subparsers.add_parser("identity", help="parse an *IDN? response")
    identity.add_argument("path")
    identity.add_argument("--provenance", default="documented", choices=["documented", "synthetic", "hardware-verified"])

    measurement = subparsers.add_parser("measurement", help="parse one :MEASure:*? response")
    measurement.add_argument("path")
    measurement.add_argument("--quantity", required=True)
    measurement.add_argument("--unit")
    measurement.add_argument("--provenance", default="documented", choices=["documented", "synthetic", "hardware-verified"])

    error_queue = subparsers.add_parser("error-queue", help="parse one :SYSTem:ERRor? response")
    error_queue.add_argument("path")
    error_queue.add_argument("--provenance", default="documented", choices=["documented", "synthetic", "hardware-verified"])

    waveform = subparsers.add_parser("waveform", help="parse an :ACQuire<n>:MEMory? response")
    waveform.add_argument("path")
    waveform.add_argument("--samples", action="store_true")
    waveform.add_argument("--byte-order", default="little", choices=["little", "big"])
    waveform.add_argument("--csv-out")
    waveform.add_argument("--overwrite", action="store_true")
    waveform.add_argument("--provenance", default="documented", choices=["documented", "synthetic", "hardware-verified"])

    header = subparsers.add_parser("waveform-header", help="print only the waveform framing metadata")
    header.add_argument("path")

    args = parser.parse_args(argv)
    raw = _read(args.path)
    if args.command == "identity":
        result = parse_identity(raw, provenance=args.provenance)
    elif args.command == "measurement":
        result = parse_measurement(raw, quantity=args.quantity, unit=args.unit, provenance=args.provenance)
    elif args.command == "error-queue":
        result = parse_error_queue(raw, provenance=args.provenance)
    elif args.command == "waveform-header":
        try:
            envelope = parse_waveform_header(raw)
        except ProtocolError as exc:
            _print_json({"status": exc.status, "reason": str(exc)})
            return 1
        _print_json(
            {
                "header_present": envelope["header_present"],
                "header": envelope["header"],
                "header_text": envelope["header_text"],
                "points": envelope["points"],
                "declared_block_bytes": envelope["block"].declared_length,
                "trailing_bytes": len(envelope["block"].trailing),
            }
        )
        return 0
    else:
        result = parse_waveform(
            raw,
            include_samples=args.samples,
            sample_byte_order=args.byte_order,
            provenance=args.provenance,
        )
        if args.csv_out:
            try:
                result["csv"] = waveform_to_csv(raw, args.csv_out, overwrite=args.overwrite)
            except (ProtocolError, FileExistsError) as exc:
                result["csv_error"] = str(exc)
                _print_json(result)
                return 1
    _print_json(result)
    return 0 if result.get("status") in {"COMPLETE", "UNVERIFIED"} else 1


if __name__ == "__main__":
    sys.exit(main())
