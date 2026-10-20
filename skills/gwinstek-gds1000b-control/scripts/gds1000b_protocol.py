#!/usr/bin/env python3
"""Offline parsers for the GW Instek GDS-1000B series oscilloscope.

The module is transport-independent: it never opens a socket or serial port.
It preserves raw response bytes as SHA-256 evidence, separates framing,
metadata, payload extraction, normalization, and validation, and reports
conservative integrity statuses.

Manual: GDS-1000B Series Programming Manual, Version 1.00, March 2015.
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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterator

PARSER_NAME = "gds1000b-protocol"
PARSER_VERSION = "0.1.0"
SUPPORT_LEVEL = "documented"
AD_FACTOR = Decimal(25)
MAX_POINTS = 10_000_000
MAX_PAYLOAD_BYTES = MAX_POINTS * 2
MAX_INLINE_SAMPLES = 1_000_000
MAX_LINE_BYTES = 65_536
MAX_HEADER_BYTES = 65_536

MODEL_PROFILES = {
    "GDS-1054B": {"channels": 4, "bandwidth_mhz": 50, "ethernet": True, "external_trigger": False},
    "GDS-1072B": {"channels": 2, "bandwidth_mhz": 70, "ethernet": False, "external_trigger": True},
    "GDS-1074B": {"channels": 4, "bandwidth_mhz": 70, "ethernet": True, "external_trigger": False},
    "GDS-1102B": {"channels": 2, "bandwidth_mhz": 100, "ethernet": False, "external_trigger": True},
    "GDS-1104B": {"channels": 4, "bandwidth_mhz": 100, "ethernet": True, "external_trigger": False},
    "GDS-1202B": {"channels": 2, "bandwidth_mhz": 200, "ethernet": False, "external_trigger": True},
}
KNOWN_MODELS = set(MODEL_PROFILES)

# Quantity -> implied unit when the instrument returns a unitless NR3 value.
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
    "crms": "V or A",
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
    "ppulse": "",
    "npulse": "",
    "pedge": "",
    "nedge": "",
}

MEASUREMENT_ALIASES = {
    "freq": "frequency",
    "vpp": "pk2pk",
    "trise": "rise",
    "tfall": "fall",
}

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
    "crms": ":MEASure:CRMS?",
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
    "lrfdelay": ":MEASure:LRFDelay?",
    "lfrdelay": ":MEASure:LFRDelay?",
    "lffdelay": ":MEASure:LFFDelay?",
    "ppulse": ":MEASure:PPULSE?",
    "npulse": ":MEASure:NPULSE?",
    "pedge": ":MEASure:PEDGE?",
    "nedge": ":MEASure:NEDGE?",
}

COUNT_QUANTITIES = {"ppulse", "npulse", "pedge", "nedge"}
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
    "crms",
}
AREA_QUANTITIES = {"area", "carea"}

MEASUREMENT_ALLOWED_UNITS = {
    "frequency": {"Hz"},
    "period": {"s"},
    "rise": {"s"},
    "fall": {"s"},
    "width": {"s"},
    "nwidth": {"s"},
    "pwidth": {"s"},
    "duty": {"%"},
    "pduty": {"%"},
    "amplitude": {"V", "A"},
    "mean": {"V", "A"},
    "cmean": {"V", "A"},
    "high": {"V", "A"},
    "low": {"V", "A"},
    "max": {"V", "A"},
    "min": {"V", "A"},
    "pk2pk": {"V", "A"},
    "rms": {"V", "A"},
    "crms": {"V", "A"},
    "area": {"V·s", "A·s"},
    "carea": {"V·s", "A·s"},
    "overshoot": {"%"},
    "preshoot": {"%"},
    "fovshoot": {"%"},
    "fpreshoot": {"%"},
    "rovshoot": {"%"},
    "rpreshoot": {"%"},
    "phase": {"deg"},
    "delay": {"s"},
    "frrdelay": {"s"},
    "frfdelay": {"s"},
    "ffrdelay": {"s"},
    "fffdelay": {"s"},
    "lrrdelay": {"s"},
    "lrfdelay": {"s"},
    "lfrdelay": {"s"},
    "lffdelay": {"s"},
    "ppulse": {None},
    "npulse": {None},
    "pedge": {None},
    "nedge": {None},
}

UNIT_DEFINITIONS: dict[str, tuple[str, Decimal]] = {
    "hz": ("Hz", Decimal(1)),
    "khz": ("Hz", Decimal(1000)),
    "mhz": ("Hz", Decimal(1_000_000)),
    "v": ("V", Decimal(1)),
    "mv": ("V", Decimal("0.001")),
    "a": ("A", Decimal(1)),
    "v·s": ("V·s", Decimal(1)),
    "a·s": ("A·s", Decimal(1)),
    "s": ("s", Decimal(1)),
    "ms": ("s", Decimal("0.001")),
    "us": ("s", Decimal("0.000001")),
    "µs": ("s", Decimal("0.000001")),
    "μs": ("s", Decimal("0.000001")),
    "ns": ("s", Decimal("0.000000001")),
    "%": ("%", Decimal(1)),
    "deg": ("deg", Decimal(1)),
    "degree": ("deg", Decimal(1)),
    "degrees": ("deg", Decimal(1)),
    "vs": ("Vs", Decimal(1)),
}

_NUMERIC_RE = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(?P<unit>[A-Za-z%°µμμ]+)?$"
)
_ERROR_QUEUE_RE = re.compile(r"^\s*(?P<code>[+-]?\d+)\s*,\s*(?P<message>.+?)\s*$")
_QUOTES = "\"'“”‘’"


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


def _raw_evidence(raw: bytes) -> dict[str, str]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
    }


def _check(name: str, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _normalize_unit(unit: str) -> tuple[str, Decimal] | None:
    key = unit.strip().lower()
    if key in {"µs", "μs"}:
        key = "us"
    return UNIT_DEFINITIONS.get(key)


def read_frame(raw: bytes) -> Frame:
    """Read one LF/CR/CRLF/LFCR-terminated line and reject trailing bytes."""

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
    next_byte = raw[start + 1 : start + 2]
    if first == b"\r" and next_byte == b"\n":
        terminator = b"\r\n"
    elif first == b"\n" and next_byte == b"\r":
        terminator = b"\n\r"
    else:
        terminator = first

    end = start + len(terminator)
    trailing = raw[end:]
    if trailing:
        raise ProtocolError("extra bytes follow the first response line", "INVALID")
    return Frame(content=raw[:start], terminator=terminator)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains invalid text bytes", "INVALID") from exc


def _is_identity_line(line: str) -> bool:
    parts = [part.strip() for part in line.split(",")]
    return len(parts) == 4 and bool(re.fullmatch(r"GDS-\d{4}B", parts[1], re.IGNORECASE))


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
        elif line.casefold() == "chan off" or _NUMERIC_RE.fullmatch(line):
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
        if len(parts) != 4:
            raise ProtocolError(
                "identity response must have four comma-separated fields",
                "INVALID",
            )
        return {"response_type": "identity", "line": line, "fields": parts, "mode": mode}

    if response_type == "measurement":
        if line.casefold() == "chan off":
            return {
                "response_type": "measurement",
                "line": line,
                "chan_off": True,
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
            "chan_off": False,
            "numeric_token": match.group("number"),
            "raw_unit": match.group("unit"),
            "mode": mode,
        }

    match = _ERROR_QUEUE_RE.fullmatch(line)
    if not match:
        raise ProtocolError(
            "error-queue response must be code, message",
            "INVALID",
        )
    message_raw = match.group("message").strip()
    if not message_raw:
        raise ProtocolError("error-queue message is empty", "INVALID")
    quoted = message_raw[0] in "\"'“”‘’"
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
            "chan_off": metadata["chan_off"],
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
        if model not in KNOWN_MODELS:
            raise ProtocolError(f"unsupported GDS-1000B model {model!r}", "INVALID")
        if not serial:
            raise ProtocolError("serial number is missing", "INCOMPLETE")
        if not re.fullmatch(r"P[0-9A-Za-z]+", serial, re.IGNORECASE):
            raise ProtocolError(f"unexpected serial field {serial!r}", "INVALID")
        if not firmware:
            raise ProtocolError("firmware version is missing", "INCOMPLETE")
        if not re.fullmatch(r"V\d+\.[0-9A-Za-z]+", firmware, re.IGNORECASE):
            raise ProtocolError(f"malformed firmware version {firmware!r}", "INVALID")

        profile = dict(MODEL_PROFILES[model])
        # The Ethernet command is documented only for GDS-1074B/GDS-1104B
        # (manual p. 169), although GDS-1054B also has an Ethernet port.
        profile["ethernet_dhcp_command"] = model in {"GDS-1074B", "GDS-1104B"}
        return {
            "schema_version": "gds1000b-protocol-v1",
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
            "profile": profile,
            "status": "COMPLETE",
            "checks": [_check("identity_parse", "pass", {"model": model})],
            "reasons": [],
        }

    if response_type == "measurement":
        if payload["chan_off"]:
            raise ProtocolError("Chan Off: measurement source channel is not activated", "INCOMPLETE")
        if not isinstance(quantity, str) or not quantity.strip():
            raise ProtocolError("quantity is required for measurement normalization", "INVALID")

        token = payload["numeric_token"]
        suffix = payload["raw_unit"]
        if suffix:
            # The instrument's measurement responses are unitless NR3 values.
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

        allowed = MEASUREMENT_ALLOWED_UNITS[quantity_key]
        if unit is not None:
            if quantity_key in COUNT_QUANTITIES:
                raise ProtocolError("count measurements are unitless", "INVALID")
            normalized_unit = _normalize_unit(unit)
            if normalized_unit is None:
                raise ProtocolError(f"unsupported supplied unit {unit!r}", "INVALID")
            display_unit = normalized_unit[0]
            if display_unit not in allowed:
                raise ProtocolError(
                    "supplied unit does not belong to the declared quantity",
                    "INVALID",
                )
            unit_status = "documented"
        else:
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

        try:
            raw_float = float(value)
        except (OverflowError, ValueError) as exc:
            raise ProtocolError(
                "measurement value is outside the supported finite range",
                "INVALID",
            ) from exc
        if not math.isfinite(raw_float):
            raise ProtocolError(
                "measurement value is outside the supported finite range",
                "INVALID",
            )

        return {
            "schema_version": "gds1000b-protocol-v1",
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
            "checks": [
                _check(
                    "measurement_parse",
                    "pass",
                    {"token": token, "unit": display_unit},
                )
            ],
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

        checks = [_check("error_queue_record", "pass", {"code": code})]
        if metadata.get("mode") == "auto" and code != 0 and abs(code) != 350:
            return {
                "schema_version": "gds1000b-protocol-v1",
                "kind": "unknown",
                "code": code,
                "message": message,
                "quoted": payload.get("quoted", False),
                "record_type": None,
                "status": "UNSUPPORTED",
                "checks": [
                    _check(
                        "error_queue_classification",
                        "fail",
                        {"reason": "explicit_error_queue_mode_required"},
                    )
                ],
                "reasons": ["explicit_error_queue_mode_required"],
            }

        return {
            "schema_version": "gds1000b-protocol-v1",
            "kind": "status-record",
            "record_type": "error-queue",
            "code": code,
            "message": message,
            "quoted": payload.get("quoted", False),
            "status": status,
            "checks": checks,
            "reasons": reasons,
        }

    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED")


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    """Attach raw evidence and the integrity block to a normalized artifact."""

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
        "support_level": SUPPORT_LEVEL,
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
    }
    return artifact


def _identity_failure(raw: bytes, status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "gds1000b-protocol-v1",
        "kind": "identity",
        "vendor": None,
        "model": None,
        "serial": None,
        "firmware": None,
        "identity": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [_check("identity_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def _measurement_failure(raw: bytes, status: str, reason: str, quantity) -> dict[str, Any]:
    return {
        "schema_version": "gds1000b-protocol-v1",
        "kind": "scalar-measurement",
        "quantity": quantity,
        "value": None,
        "raw_value": None,
        "numeric_token": None,
        "unit": None,
        "raw_unit": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [_check("measurement_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def _error_queue_failure(raw: bytes, status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "gds1000b-protocol-v1",
        "kind": "unknown",
        "code": None,
        "message": None,
        "record_type": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [_check("error_queue_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def parse_identity(raw: bytes) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _identity_failure(raw, exc.status, str(exc))


def parse_measurement(raw: bytes, *, quantity: str, unit: str | None = None) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="measurement")
        artifact = normalize(metadata, extract_payload(metadata), quantity=quantity, unit=unit)
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _measurement_failure(raw, exc.status, str(exc), quantity)


def parse_error_queue(raw: bytes, *, response_type: str = "auto") -> dict[str, Any]:
    raw = bytes(raw)
    if response_type not in {"auto", "error-queue"}:
        return _error_queue_failure(raw, "INVALID", "response_type must be auto or error-queue")
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type=response_type)
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _error_queue_failure(raw, exc.status, str(exc))


# ---------------------------------------------------------------------------
# Waveform block parsing
# ---------------------------------------------------------------------------


def parse_ieee_block(raw: bytes, *, allow_terminator: bool = False) -> IEEEBlock:
    """Parse one definite-length IEEE 488.2 block.

    Extra bytes are rejected unless they are a single LF, CR, or CRLF and
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
        raise ProtocolError(
            "waveform response has no 'Waveform Data;' marker",
            "INVALID",
        )
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

    header: dict[str, str] = {}
    header_norm: dict[str, str] = {}
    for part in header_text.split(";"):
        part = part.strip()
        if not part:
            continue
        if "," not in part:
            raise ProtocolError(f"header field has no comma: {part!r}", "INVALID")
        name, value = part.split(",", 1)
        name = name.strip()
        key = " ".join(name.lower().split())
        if not key:
            raise ProtocolError("header field has an empty name", "INVALID")
        if key in header_norm:
            raise ProtocolError(f"duplicate header field {name!r}", "INVALID")
        header[name] = value.strip()
        header_norm[key] = value.strip()

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


def iter_samples(payload: bytes) -> Iterator[int]:
    """Yield signed big-endian 16-bit samples from a waveform payload."""

    if len(payload) % 2:
        raise ProtocolError("waveform payload has an odd byte count", "INVALID")
    for (code,) in struct.iter_unpack(">h", payload):
        yield code


def sample_value(code: int, vertical_scale: float, ad_factor: float = 25.0) -> float:
    """Documented conversion: (code / AD factor) * vertical scale."""

    if isinstance(code, bool) or not isinstance(code, int):
        raise ProtocolError("sample code must be an integer", "INVALID")
    if code < -32768 or code > 32767:
        raise ProtocolError("sample code is outside signed 16-bit range", "INVALID")
    if not math.isfinite(vertical_scale) or vertical_scale <= 0:
        raise ProtocolError("vertical scale is not a finite positive value", "INVALID")
    if not math.isfinite(ad_factor) or ad_factor <= 0:
        raise ProtocolError("AD factor must be a finite positive value", "INVALID")
    return (code / ad_factor) * vertical_scale


def _waveform_failure(raw: bytes, status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "gds1000b-protocol-v1",
        "kind": "waveform",
        "status": status,
        "integrity": {
            "status": status,
            "checks": [_check("waveform_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def parse_waveform(raw: bytes, *, include_samples: bool = False) -> dict[str, Any]:
    """Parse a `:ACQuire<X>:MEMory?` response into a waveform artifact."""

    raw = bytes(raw)
    try:
        envelope = parse_waveform_header(raw)
        block = envelope["block"]
        header = envelope["header"]
        header_norm = envelope["header_norm"]
    except ProtocolError as exc:
        return _waveform_failure(raw, exc.status, str(exc))

    payload = block.payload
    if not payload:
        return _waveform_failure(raw, "INCOMPLETE", "waveform payload is empty")
    if len(payload) % 2:
        return _waveform_failure(raw, "INVALID", "waveform payload has an odd byte count")

    points = len(payload) // 2
    if points > MAX_POINTS:
        return _waveform_failure(raw, "UNSUPPORTED", "waveform exceeds 10,000,000 points")
    if include_samples and points > MAX_INLINE_SAMPLES:
        return _waveform_failure(
            raw,
            "UNSUPPORTED",
            "inline samples are limited to 1,000,000 points; use --csv-out",
        )

    checks: list[dict[str, Any]] = [
        _check("ieee_block_length", "pass", {"declared_bytes": block.declared_length, "observed_bytes": len(payload)}),
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
            return _waveform_failure(raw, "INVALID", "Memory Length is not an integer")
        if declared_points != points:
            return _waveform_failure(
                raw,
                "INVALID",
                f"declared Memory Length {declared_points} does not match {points} points",
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
            status = "INCOMPLETE"
            reasons.append("declared_point_count_missing")

    if envelope["headerless"]:
        status = "UNVERIFIED"
        if "headerless_block_has_no_scale_or_units" not in reasons:
            reasons.append("headerless_block_has_no_scale_or_units")

    vertical_scale: float | None = None
    if header_norm.get("vertical scale"):
        try:
            vertical_scale = float(header_norm["vertical scale"])
        except ValueError:
            return _waveform_failure(raw, "INVALID", "Vertical Scale is not numeric")
        if not math.isfinite(vertical_scale) or vertical_scale <= 0:
            return _waveform_failure(raw, "INVALID", "Vertical Scale is not finite positive")
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
            return _waveform_failure(raw, "INVALID", "Sampling Period is not numeric")
        if not math.isfinite(sampling_period) or sampling_period <= 0:
            return _waveform_failure(raw, "INVALID", "Sampling Period is not finite positive")
        checks.append(_check("sampling_period", "pass", {"value": sampling_period}))
    else:
        reasons.append("sampling_period_missing")

    trigger_address: int | None = None
    if header_norm.get("trigger address"):
        try:
            trigger_address = int(header_norm["trigger address"])
        except ValueError:
            reasons.append("trigger_address_not_integer")

    samples = list(iter_samples(payload)) if include_samples else None
    documented_values = None
    if include_samples and vertical_scale is not None:
        documented_values = [
            sample_value(code, vertical_scale, float(AD_FACTOR)) for code in samples or []
        ]

    artifact = {
        "schema_version": "gds1000b-protocol-v1",
        "kind": "waveform",
        "artifact": "acquisition-memory",
        "points": points,
        "point_count": points,
        "bytes_per_point": 2,
        "sample_encoding": "signed-16-bit-big-endian",
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
        "ad_factor": 25,
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "calibration": {
            "status": "UNVERIFIED",
            "ad_factor": 25,
            "vertical_scale": vertical_scale,
        },
        "analysis_allowed": "code-domain-only",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "support_level": SUPPORT_LEVEL,
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
    }
    if samples is not None:
        artifact["samples"] = samples
    if documented_values is not None:
        artifact["sample_voltages_documented"] = documented_values
        artifact["values"] = documented_values
    artifact["integrity"] = {
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "calibration": "UNVERIFIED",
        "analysis_allowed": "code-domain-only",
        "support_level": SUPPORT_LEVEL,
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        "raw_sha256": artifact["raw_sha256"],
        "payload_sha256": artifact["payload_sha256"],
    }
    return artifact


def normalize_waveform(raw: bytes, *, include_samples: bool = False) -> dict[str, Any]:
    """Compatibility wrapper for the waveform normalization stage."""

    return parse_waveform(raw, include_samples=include_samples)


def waveform_to_csv(
    raw: bytes,
    path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Stream a waveform payload to CSV without materializing all samples."""

    artifact = parse_waveform(raw, include_samples=False)
    if artifact["status"] in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}:
        raise ProtocolError("waveform cannot be exported", artifact["status"])
    envelope = parse_waveform_header(bytes(raw))
    payload = envelope["block"].payload
    vertical_scale = artifact["vertical_scale"]
    vertical_unit = artifact["vertical_units"] or ""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()

    class HashingWriter:
        def __init__(self, handle) -> None:
            self.handle = handle

        def write(self, text: str) -> int:
            hasher.update(text.encode("utf-8"))
            return self.handle.write(text)

    rows = 0
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(HashingWriter(handle), lineterminator="\n")
            writer.writerow(["index", "code", "voltage_documented", "voltage_unit"])
            for index, code in enumerate(iter_samples(payload)):
                if vertical_scale is None:
                    value = ""
                    unit = ""
                else:
                    value = f"{sample_value(code, vertical_scale):g}"
                    unit = vertical_unit
                writer.writerow([index, code, value, unit])
                rows += 1
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "path": str(destination),
        "points": artifact["points"],
        "rows": rows,
        "csv_sha256": hasher.hexdigest(),
        "status": artifact["status"],
        "calibration_status": artifact["calibration"]["status"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _status_exit_code(status: str) -> int:
    return 1 if status in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser("identity", help="parse a saved *IDN? response")
    p_id.add_argument("response", type=Path)

    p_meas = sub.add_parser("measure", help="parse a saved :MEASure:*? response")
    p_meas.add_argument("response", type=Path)
    p_meas.add_argument("--quantity", required=True)

    p_err = sub.add_parser("error-queue", help="parse a saved :SYSTem:ERRor? response")
    p_err.add_argument("response", type=Path)
    p_err.add_argument("--response-type", choices=("auto", "error-queue"), default="auto")

    p_wave = sub.add_parser("waveform", help="parse a saved :ACQuire<X>:MEMory? response")
    p_wave.add_argument("response", type=Path)
    p_wave.add_argument("--samples", action="store_true", help="include all sample codes/values")
    p_wave.add_argument("--csv-out", type=Path)
    p_wave.add_argument("--overwrite", action="store_true")

    p_hdr = sub.add_parser("waveform-header", help="print only the waveform ASCII header")
    p_hdr.add_argument("response", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "identity":
        raw = args.response.read_bytes()
        result = parse_identity(raw)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "measure":
        raw = args.response.read_bytes()
        result = parse_measurement(raw, quantity=args.quantity)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "error-queue":
        raw = args.response.read_bytes()
        result = parse_error_queue(raw, response_type=args.response_type)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "waveform":
        raw = args.response.read_bytes()
        result = parse_waveform(raw, include_samples=args.samples)
        if args.csv_out and result["status"] not in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}:
            result["csv"] = waveform_to_csv(raw, args.csv_out, overwrite=args.overwrite)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "waveform-header":
        raw = args.response.read_bytes()
        envelope = parse_waveform_header(raw)
        json.dump(
            {
                "header": envelope["header"],
                "header_text": envelope["header_text"],
                "header_present": envelope["header_present"],
                "headerless": envelope["headerless"],
                "marker": envelope["marker"],
                "separator": envelope["separator"].decode("ascii", "replace"),
                "points": envelope["points"],
                "block_header": envelope["block"].header.decode("ascii"),
                "block_bytes": envelope["block"].declared_length,
                "trailing_bytes": len(envelope["block"].trailing),
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
