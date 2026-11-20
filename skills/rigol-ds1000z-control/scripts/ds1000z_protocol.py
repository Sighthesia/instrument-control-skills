#!/usr/bin/env python3
"""Offline parsers for the RIGOL DS1000Z series oscilloscope.

The module is transport-independent: it never opens a socket or serial port.
It preserves raw response bytes as SHA-256 evidence, separates framing,
metadata, payload extraction, normalization, and validation, and reports
conservative integrity statuses.

Every rule marked "measured" was observed on the bench instrument
(RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4, raw TCP port 5555).
The rest follows the MSO1000Z/DS1000Z Programming Guide (PGA19108-1110,
software version 00.04.03.SP2, December 2015).

Measured wire rules this module encodes:

* One command per write; a single write carrying two commands is answered for
  the first command only.
* Responses end with LF and contain no CR; commands accept LF or CRLF.
* An undefined command header answers the literal ``command error``
  (13 bytes, **no terminator**) and queues ``-113``. A reader that waits for LF
  blocks until its idle timeout, so framing must not require a terminator for
  that one literal.
* ``9.9E37`` is the "no result" sentinel, not a value.
* Waveform payloads are one unsigned byte per point; the TMC header is
  ``#9`` + nine ASCII digits. Volts are ``(code - yorigin - yreference) *
  yincrement`` (manual p. 2-221; reproduces :MEASure:VPP? on this firmware).
* ``yincrement`` differs between NORM (0.02 at 0.5 V/div) and RAW (0.0209375 at
  the same scale); the two must never be mixed.
* NORM returns the 1200-point screen record. Leaving ``:WAVeform:STOP`` at a
  RAW value and switching back to NORM yields metadata that reports a large
  point count with a screen increment; that contradiction is INVALID here.
* ``:DISPlay:DATA?`` returns the declared BMP followed by three extra bytes
  ``;0\\n``; only the declared length belongs to the image.
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

PARSER_NAME = "ds1000z-protocol"
PARSER_VERSION = "0.1.0"
SCHEMA_VERSION = "ds1000z-protocol-v1"
SUPPORT_LEVEL = "firmware-scoped"

# Evidence scope: the exact instrument/interface this repository verified.
EVIDENCE_MODEL = "DS1074Z"
EVIDENCE_SERIAL = "DS1ZA171004155"
EVIDENCE_FIRMWARE = "00.04.02.SP4"
EVIDENCE_TRANSPORT = "raw TCP 5555"

MANUAL = {
    "title": "MSO1000Z/DS1000Z Programming Guide",
    "part_number": "PGA19108-1110",
    "revision": "software version 00.04.03.SP2, December 2015",
    "url": (
        "https://www.rigol.com/dam/global/downloads/brochures/en/program-guide/"
        "oscilloscopes/DS1000Z_ProgrammingGuide_EN.pdf"
    ),
    "location": "local copy ref/DS1000Z_ProgrammingGuide_EN_Dec2015.pdf",
}

STATUSES = ("COMPLETE", "INCOMPLETE", "INVALID", "UNVERIFIED", "UNSUPPORTED")
FAILING_STATUSES = ("INCOMPLETE", "INVALID", "UNSUPPORTED")

MAX_LINE_BYTES = 65_536
MAX_BLOCK_BYTES = 16 * 1024 * 1024
MAX_POINTS = MAX_BLOCK_BYTES
MAX_INLINE_SAMPLES = 1_000_000
MAX_INLINE_RAW_BYTES = 4096

# Measured: the literal 13-byte reply to an undefined command header. It has no
# terminator, so it must be classified before looking for a line ending.
COMMAND_ERROR = b"command error"
COMMAND_ERROR_REPLIES = {COMMAND_ERROR, COMMAND_ERROR + b"\n", COMMAND_ERROR + b"\r\n"}

# Measured: 9.9E37 is "no measurement result" (channel off, no signal, or a
# measurement item that has no value). It is not a reading.
NO_RESULT_SENTINEL = Decimal("9.9E37")

# Measured: NORM mode returns the fixed 1200-point screen record.
NORM_SCREEN_POINTS = 1200

# Measured: :DISPlay:DATA? appends three bytes past the declared block length.
SCREENSHOT_TRAILING_QUIRK = b";0\n"
SCREENSHOT_PANEL = (800, 480)

# Measured: block framing of :WAVeform:DATA? and :DISPlay:DATA? on this
# firmware always uses "#9" plus nine ASCII decimal digits.
TMC_LENGTH_DIGITS = 9

# Manual p. 2-226: <format> 0=BYTE, 1=WORD, 2=ASC.
WAVEFORM_FORMATS = {0: "BYTE", 1: "WORD", 2: "ASC"}
WAVEFORM_FORMAT_BYTES = {0: 1, 1: 2, 2: 1}
# Manual p. 2-226: <type> 0=NORMal, 1=MAXimum, 2=RAW.
WAVEFORM_MODES = {0: "NORM", 1: "MAX", 2: "RAW"}

# Manual p. 2-226: preamble field order.
PREAMBLE_FIELDS = (
    "format",
    "mode",
    "points",
    "count",
    "xincrement",
    "xorigin",
    "xreference",
    "yincrement",
    "yorigin",
    "yreference",
)

MODEL_PROFILES = {
    "DS1054Z": {"channels": 4, "bandwidth_mhz": 50, "series": "DS1000Z"},
    "DS1074Z": {"channels": 4, "bandwidth_mhz": 70, "series": "DS1000Z"},
    "DS1104Z": {"channels": 4, "bandwidth_mhz": 100, "series": "DS1000Z"},
    "MSO1074Z": {"channels": 4, "bandwidth_mhz": 70, "series": "MSO1000Z"},
    "MSO1104Z": {"channels": 4, "bandwidth_mhz": 100, "series": "MSO1000Z"},
}

_MODEL_RE = re.compile(r"^(?P<prefix>MSO|DS)1(?P<digits>\d{3})Z$", re.IGNORECASE)
_SERIAL_RE = re.compile(r"^DS1[A-Z0-9]{6,20}$")
_FIRMWARE_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*(?:\.[A-Za-z][A-Za-z0-9]*)?$")
_NR3_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_ERROR_QUEUE_RE = re.compile(r"^(?P<code>[+-]?\d+)\s*,\s*(?P<message>.*)$")

MEASUREMENT_COMMANDS = {
    "vpp": ":MEASure:VPP?",
    "vmax": ":MEASure:VMAX?",
    "vmin": ":MEASure:VMIN?",
    "vavg": ":MEASure:VAVG?",
    "vamp": ":MEASure:VAMP?",
    "vrms": ":MEASure:VRMS?",
    "vtop": ":MEASure:VTOP?",
    "vbase": ":MEASure:VBASe?",
    "overshoot": ":MEASure:OVERshoot?",
    "preshoot": ":MEASure:PREShoot?",
    "frequency": ":MEASure:FREQuency?",
    "period": ":MEASure:PERiod?",
    "pduty": ":MEASure:PDUTy?",
    "nduty": ":MEASure:NDUTy?",
    "pwidth": ":MEASure:PWIDth?",
    "nwidth": ":MEASure:NWIDth?",
    "counter": ":MEASure:COUNter:VALue?",
    # Manual p. 2-125 spells the transition items RTIMe/FTIMe; this firmware
    # rejects :MEASure:RISetime?/:MEASure:FALLtime? with "command error" but
    # accepts :MEASure:ITEM? RTIMe (measured, and it answers 9.9E37 on a square
    # wave, i.e. "no result" rather than an error).
    "rtime": ":MEASure:ITEM? RTIMe",
    "ftime": ":MEASure:ITEM? FTIMe",
}

MEASUREMENT_UNITS = {
    "vpp": "V",
    "vmax": "V",
    "vmin": "V",
    "vavg": "V",
    "vamp": "V",
    "vrms": "V",
    "vtop": "V",
    "vbase": "V",
    "overshoot": "%",
    "preshoot": "%",
    "frequency": "Hz",
    "period": "s",
    "pduty": "%",
    "nduty": "%",
    "pwidth": "s",
    "nwidth": "s",
    "counter": "Hz",
    "rtime": "s",
    "ftime": "s",
}

MEASUREMENT_ALIASES = {
    "pk2pk": "vpp",
    "freq": "frequency",
}

# IEEE 488.2 error classes; the queue reports the negative standard codes.
ERROR_CLASSES = {
    "command": (-199, -100),
    "execution": (-299, -200),
    "device": (-399, -300),
    "query": (-499, -400),
}


class ProtocolError(ValueError):
    """A protocol failure with a conservative integrity classification."""

    def __init__(self, message: str, status: str, reason: str | None = None) -> None:
        super().__init__(message)
        if status not in STATUSES:
            raise ValueError(f"unknown integrity status {status!r}")
        self.status = status
        self.reason = reason or "protocol_error"


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


def _raw_evidence(raw: bytes) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
    }
    if len(raw) <= MAX_INLINE_RAW_BYTES:
        evidence["raw_response_base64"] = base64.b64encode(raw).decode("ascii")
    else:
        evidence["raw_response_base64"] = None
        evidence["raw_inline_omitted"] = True
    return evidence


def _check(name: str, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _integrity(
    status: str,
    checks: list[dict[str, Any]],
    reasons: list[str],
    raw: bytes,
    *,
    limitations: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "status": status,
        "checks": checks,
        "reasons": reasons,
        **_raw_evidence(raw),
        "support_level": SUPPORT_LEVEL,
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        "evidence": {
            "model": EVIDENCE_MODEL,
            "serial": EVIDENCE_SERIAL,
            "firmware": EVIDENCE_FIRMWARE,
            "transport": EVIDENCE_TRANSPORT,
            "manual": MANUAL,
        },
    }
    if limitations:
        block["limitations"] = limitations
    if extra:
        block.update(extra)
    return block


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def is_command_error(raw: bytes) -> bool:
    """True for the literal ``command error`` reply (measured, no terminator)."""

    return bytes(raw) in COMMAND_ERROR_REPLIES


def read_frame(raw: bytes, *, allow_trailing: bool = False) -> Frame:
    """Read one LF-terminated line and classify the terminator exactly.

    ``command error`` is raised as UNSUPPORTED before any terminator is
    required, because that reply has none on this firmware.
    """

    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("response must be bytes", "INVALID", "response_not_bytes")
    raw = bytes(raw)
    if len(raw) > MAX_LINE_BYTES:
        raise ProtocolError("response exceeds the line-parser size limit", "UNSUPPORTED", "line_too_long")
    if not raw:
        raise ProtocolError("response is empty", "INCOMPLETE", "empty_response")
    if is_command_error(raw):
        raise ProtocolError(
            'instrument answered "command error": the command header is undefined',
            "UNSUPPORTED",
            "instrument_command_error",
        )
    if raw[:1] == b"#":
        raise ProtocolError("binary block data is not a line response", "UNSUPPORTED", "binary_block_not_line")

    lf = raw.find(b"\n")
    if lf < 0:
        raise ProtocolError("response has no LF terminator", "INCOMPLETE", "missing_terminator")
    terminator = b"\n"
    content = raw[:lf]
    if content.endswith(b"\r"):
        terminator = b"\r\n"
        content = content[:-1]
    if b"\r" in content:
        # Measured: the instrument terminates lines with LF and emits no CR.
        raise ProtocolError("response contains a CR byte before the terminator", "INVALID", "unexpected_cr")
    trailing = raw[lf + 1 :]
    if trailing and not allow_trailing:
        raise ProtocolError("extra bytes follow the response line", "INVALID", "trailing_bytes")
    return Frame(content=content, terminator=terminator, trailing=trailing)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains non-ASCII bytes", "INVALID", "non_ascii_response") from exc


def _split_fields(line: str) -> list[str]:
    return [part.strip() for part in line.split(",")]


def _all_nr3(fields: list[str]) -> bool:
    return all(_NR3_RE.fullmatch(field) for field in fields)


# ---------------------------------------------------------------------------
# Metadata, payload extraction, normalization
# ---------------------------------------------------------------------------


def parse_metadata(frame: Frame, *, response_type: str = "auto") -> dict[str, Any]:
    """Decode one line and classify identity, measurement, error-queue, preamble."""

    if response_type not in {"auto", "identity", "measurement", "error-queue", "preamble"}:
        raise ProtocolError(
            "response_type must be auto, identity, measurement, error-queue, or preamble",
            "INVALID",
            "unknown_response_type",
        )

    line = _text(frame)
    if not line:
        raise ProtocolError("response line is empty", "INCOMPLETE", "empty_response")

    mode = "explicit"
    if response_type == "auto":
        mode = "auto"
        fields = _split_fields(line)
        if len(fields) == 4 and not _NR3_RE.fullmatch(fields[0]):
            response_type = "identity"
        elif len(fields) == len(PREAMBLE_FIELDS) and _all_nr3(fields):
            response_type = "preamble"
        elif _ERROR_QUEUE_RE.fullmatch(line):
            response_type = "error-queue"
        elif _NR3_RE.fullmatch(line):
            response_type = "measurement"
        else:
            raise ProtocolError(
                "automatic classification could not identify the response shape",
                "UNSUPPORTED",
                "unclassified_response",
            )

    if response_type == "identity":
        fields = _split_fields(line)
        if len(fields) == 3:
            # The four-field contract is not met: the trailing firmware field
            # is absent rather than wrong.
            raise ProtocolError(
                "identity response has no firmware field",
                "INCOMPLETE",
                "identity_firmware_missing",
            )
        if len(fields) != 4:
            raise ProtocolError(
                "identity response must have four comma-separated fields",
                "INVALID",
                "identity_field_count",
            )
        return {"response_type": "identity", "line": line, "fields": fields, "mode": mode}

    if response_type == "measurement":
        if not _NR3_RE.fullmatch(line):
            raise ProtocolError(
                "response is not a supported NR3 measurement",
                "INVALID",
                "measurement_not_nr3",
            )
        return {"response_type": "measurement", "line": line, "numeric_token": line, "mode": mode}

    if response_type == "preamble":
        fields = _split_fields(line)
        if len(fields) != len(PREAMBLE_FIELDS):
            raise ProtocolError(
                f"preamble must have {len(PREAMBLE_FIELDS)} fields, got {len(fields)}",
                "INVALID",
                "preamble_field_count",
            )
        if not _all_nr3(fields):
            raise ProtocolError(
                "preamble contains a field that is not a number",
                "INVALID",
                "preamble_field_not_numeric",
            )
        return {
            "response_type": "preamble",
            "line": line,
            "fields": fields,
            "field_count": len(fields),
            "mode": mode,
        }

    match = _ERROR_QUEUE_RE.fullmatch(line)
    if not match:
        raise ProtocolError(
            "error-queue response must be code,message",
            "INVALID",
            "error_queue_shape",
        )
    message_raw = match.group("message").strip()
    if not message_raw:
        raise ProtocolError("error-queue message is empty", "INVALID", "error_queue_empty_message")
    quoted = message_raw[0] in "\"'"
    if quoted:
        if len(message_raw) < 2 or message_raw[-1] != message_raw[0]:
            raise ProtocolError(
                "error-queue message has an unterminated quote",
                "INVALID",
                "error_queue_unterminated_quote",
            )
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
        return {"numeric_token": metadata["numeric_token"]}
    if response_type == "error-queue":
        return {
            "code": metadata["code"],
            "message": metadata["message"],
            "quoted": metadata.get("quoted", False),
        }
    if response_type == "preamble":
        return {"fields": list(metadata["fields"]), "field_count": metadata["field_count"]}
    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED", "unknown_response_type")


def _error_class(code: int) -> str | None:
    if code == 0:
        return "none"
    for name, (low, high) in ERROR_CLASSES.items():
        if low <= code <= high:
            return name
    return "device"


def _normalize_identity(payload: dict[str, Any]) -> dict[str, Any]:
    vendor = payload["vendor"].strip()
    model = payload["model"].strip().upper()
    serial = payload["serial"].strip()
    firmware = payload["firmware"].strip()
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    status = "COMPLETE"

    if "RIGOL" not in vendor.upper():
        raise ProtocolError(f"unexpected vendor {vendor!r}", "INVALID", "unexpected_vendor")
    checks.append(_check("vendor_recognized", "pass", {"vendor": vendor}))

    profile = MODEL_PROFILES.get(model)
    if profile is None:
        if _MODEL_RE.fullmatch(model):
            status = "UNVERIFIED"
            reasons.append("model_profile_unavailable")
            checks.append(_check("model_profile", "not_checked", {"model": model}))
        else:
            raise ProtocolError(f"unexpected DS1000Z model {model!r}", "INVALID", "unexpected_model")
    else:
        checks.append(_check("model_profile", "pass", {"model": model, "profile": profile}))

    if not serial:
        raise ProtocolError("serial number is missing", "INCOMPLETE", "serial_missing")
    if not _SERIAL_RE.fullmatch(serial):
        raise ProtocolError(f"unexpected serial field {serial!r}", "INVALID", "serial_malformed")
    checks.append(_check("serial", "pass", {"serial": serial}))

    if not firmware:
        raise ProtocolError("firmware version is missing", "INCOMPLETE", "firmware_missing")
    if not _FIRMWARE_RE.fullmatch(firmware):
        raise ProtocolError(f"malformed firmware version {firmware!r}", "INVALID", "firmware_malformed")
    checks.append(_check("firmware", "pass", {"firmware": firmware}))

    identity = {
        "vendor": vendor,
        "model": model,
        "serial": serial,
        "firmware": firmware,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "identity",
        **identity,
        "identity": identity,
        "profile": profile,
        "command": "*IDN?",
        "status": status,
        "checks": checks,
        "reasons": reasons,
    }


def _normalize_measurement(payload: dict[str, Any], quantity: str | None) -> dict[str, Any]:
    if not isinstance(quantity, str) or not quantity.strip():
        raise ProtocolError("quantity is required for measurement normalization", "INVALID", "quantity_missing")
    quantity_key = MEASUREMENT_ALIASES.get(quantity.lower().strip(), quantity.lower().strip())
    if quantity_key not in MEASUREMENT_COMMANDS:
        raise ProtocolError(
            f"unsupported measurement quantity {quantity!r}",
            "INVALID",
            "quantity_unknown",
        )

    token = payload["numeric_token"]
    try:
        value = Decimal(token)
    except (InvalidOperation, TypeError) as exc:
        raise ProtocolError("measurement token is not valid", "INVALID", "measurement_not_nr3") from exc
    if not value.is_finite():
        raise ProtocolError("non-finite measurement response", "INVALID", "measurement_not_finite")

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": "scalar-measurement",
        "quantity": quantity_key,
        "command": MEASUREMENT_COMMANDS[quantity_key],
        "unit": MEASUREMENT_UNITS[quantity_key],
        "unit_status": "documented",
        "numeric_token": token,
        "value": None,
        "raw_value": None,
        "sentinel": None,
        "status": "COMPLETE",
        "checks": [],
        "reasons": [],
    }

    if value == NO_RESULT_SENTINEL:
        # Measured: the firmware answers 9.9E37 when the source is off, has no
        # signal, or the item has no value. Report it as evidence, not a value.
        artifact["sentinel"] = "9.9E37"
        artifact["status"] = "INCOMPLETE"
        artifact["reasons"] = ["no_measurement_result_sentinel"]
        artifact["checks"] = [
            _check(
                "measurement_sentinel",
                "fail",
                {"token": token, "sentinel": "9.9E37", "meaning": "no measurement result"},
            )
        ]
        return artifact

    raw_float = float(value)
    if not math.isfinite(raw_float):
        raise ProtocolError("measurement value is outside the finite range", "INVALID", "measurement_not_finite")
    artifact["value"] = raw_float
    artifact["raw_value"] = raw_float
    artifact["checks"] = [_check("measurement_parse", "pass", {"token": token, "value": raw_float})]
    return artifact


def _normalize_error_queue(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload["code"]
    message = payload["message"]
    normalized_message = message.strip().strip("\"'").strip().rstrip(".").casefold()
    error_class = _error_class(code)

    if code == 0 and normalized_message == "no error":
        status = "COMPLETE"
        reasons: list[str] = []
        checks = [_check("error_queue_record", "pass", {"code": code})]
    elif abs(code) == 350 and "queue overflow" in normalized_message:
        status = "INCOMPLETE"
        reasons = ["instrument_error_queue_overflow"]
        checks = [_check("error_queue_record", "fail", {"code": code, "message": message})]
    else:
        status = "UNVERIFIED"
        reasons = ["instrument_reported_error"]
        checks = [_check("error_queue_record", "fail", {"code": code, "message": message})]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "status-record",
        "record_type": "error-queue",
        "code": code,
        "message": message,
        "quoted": payload.get("quoted", False),
        "error_class": error_class,
        "status": status,
        "checks": checks,
        "reasons": reasons,
    }


def normalize(metadata: dict[str, Any], payload: dict[str, Any], *, quantity: str | None = None) -> dict[str, Any]:
    """Normalize extracted fields; semantic failures raise ProtocolError."""

    response_type = metadata.get("response_type")
    if response_type == "identity":
        return _normalize_identity(payload)
    if response_type == "measurement":
        return _normalize_measurement(payload, quantity)
    if response_type == "error-queue":
        return _normalize_error_queue(payload)
    if response_type == "preamble":
        return normalize_preamble(payload["fields"])
    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED", "unknown_response_type")


def validate(artifact: dict[str, Any], raw: bytes) -> dict[str, Any]:
    """Attach raw evidence and the integrity block to a normalized artifact."""

    artifact = dict(artifact)
    status = artifact.get("status")
    if status not in STATUSES:
        raise ProtocolError("artifact has no supported integrity status", "INVALID", "unknown_status")
    checks = artifact.pop("checks", [])
    reasons = artifact.pop("reasons", [])
    limitations = artifact.pop("limitations", [])
    artifact["integrity"] = _integrity(status, checks, reasons, raw, limitations=limitations or None)
    return artifact


def _failure(
    kind: str,
    raw: bytes,
    status: str,
    reason: str,
    detail: str,
    **fields: Any,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        **fields,
        "status": status,
        "integrity": _integrity(
            status,
            [_check(f"{kind.replace('-', '_')}_parse", "fail", {"reason": reason, "message": detail})],
            [reason],
            bytes(raw),
        ),
    }
    return artifact


def parse_identity(raw: bytes) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _failure(
            "identity",
            raw,
            exc.status,
            exc.reason,
            str(exc),
            vendor=None,
            model=None,
            serial=None,
            firmware=None,
            identity=None,
        )


def parse_measurement(raw: bytes, *, quantity: str) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="measurement")
        artifact = normalize(metadata, extract_payload(metadata), quantity=quantity)
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _failure(
            "scalar-measurement",
            raw,
            exc.status,
            exc.reason,
            str(exc),
            quantity=quantity,
            command=MEASUREMENT_COMMANDS.get(str(quantity).lower().strip()),
            unit=None,
            value=None,
            raw_value=None,
            numeric_token=None,
            sentinel=None,
            command_error=exc.reason == "instrument_command_error",
        )


def parse_error_queue(raw: bytes, *, response_type: str = "auto") -> dict[str, Any]:
    raw = bytes(raw)
    if response_type not in {"auto", "error-queue"}:
        return _failure(
            "status-record",
            raw,
            "INVALID",
            "unknown_response_type",
            "response_type must be auto or error-queue",
            record_type=None,
            code=None,
            message=None,
        )
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type=response_type)
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _failure(
            "status-record",
            raw,
            exc.status,
            exc.reason,
            str(exc),
            record_type=None,
            code=None,
            message=None,
        )


# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------


def _number(
    fields: list[str],
    name: str,
    *,
    integral: bool = False,
) -> float:
    text = fields[PREAMBLE_FIELDS.index(name)]
    try:
        value = float(text)
    except ValueError as exc:
        raise ProtocolError(f"preamble field {name} is not a number", "INVALID", "preamble_field_not_numeric") from exc
    if not math.isfinite(value):
        raise ProtocolError(f"preamble field {name} is not finite", "INVALID", "preamble_field_not_finite")
    if integral and value != int(value):
        raise ProtocolError(f"preamble field {name} is not an integer", "INVALID", "preamble_field_not_integral")
    return value


def normalize_preamble(fields: list[str]) -> dict[str, Any]:
    """Type the ten preamble fields and validate mode/format/window coherence."""

    if len(fields) != len(PREAMBLE_FIELDS):
        raise ProtocolError(
            f"preamble must have {len(PREAMBLE_FIELDS)} fields, got {len(fields)}",
            "INVALID",
            "preamble_field_count",
        )

    raw_format = _number(fields, "format", integral=True)
    raw_mode = _number(fields, "mode", integral=True)
    points = _number(fields, "points", integral=True)
    count = _number(fields, "count", integral=True)
    xincrement = _number(fields, "xincrement")
    xorigin = _number(fields, "xorigin")
    xreference = _number(fields, "xreference")
    yincrement = _number(fields, "yincrement")
    yorigin = _number(fields, "yorigin", integral=True)
    yreference = _number(fields, "yreference", integral=True)

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    status = "COMPLETE"

    format_code = int(raw_format)
    if format_code not in WAVEFORM_FORMATS:
        raise ProtocolError(
            f"preamble format {format_code} is not 0 (BYTE), 1 (WORD), or 2 (ASC)",
            "INVALID",
            "preamble_format_unknown",
        )
    mode_code = int(raw_mode)
    if mode_code not in WAVEFORM_MODES:
        raise ProtocolError(
            f"preamble mode {mode_code} is not 0 (NORM), 1 (MAX), or 2 (RAW)",
            "INVALID",
            "preamble_mode_unknown",
        )
    if points < 1:
        raise ProtocolError("preamble points must be at least 1", "INVALID", "preamble_points_invalid")
    if points > MAX_POINTS:
        raise ProtocolError("preamble points exceed the supported limit", "UNSUPPORTED", "preamble_points_too_large")
    if count < 1:
        raise ProtocolError("preamble count must be at least 1", "INVALID", "preamble_count_invalid")
    if xincrement <= 0:
        raise ProtocolError("preamble xincrement must be positive", "INVALID", "preamble_xincrement_invalid")
    if yincrement <= 0:
        raise ProtocolError("preamble yincrement must be positive", "INVALID", "preamble_yincrement_invalid")

    checks.append(_check("preamble_field_count", "pass", {"fields": len(fields)}))
    checks.append(
        _check(
            "preamble_format",
            "pass" if format_code == 0 else "not_checked",
            {"format": format_code, "name": WAVEFORM_FORMATS[format_code]},
        )
    )
    checks.append(
        _check("preamble_mode", "pass", {"mode": mode_code, "name": WAVEFORM_MODES[mode_code]})
    )
    checks.append(_check("preamble_yincrement", "pass", {"yincrement": yincrement}))
    checks.append(
        _check(
            "preamble_count",
            "pass",
            # Manual p. 2-226: count is the number of averages in average mode
            # and 1 in every other mode, so a value above 1 is legal.
            {"count": count, "averages": count > 1},
        )
    )

    if format_code != 0:
        # WORD (2 bytes/point) and ASC (comma separated voltages) are not
        # implemented; do not decode them as bytes.
        status = "UNSUPPORTED"
        reasons.append("waveform_format_not_supported")

    zero_code = yorigin + yreference
    if format_code == 0:
        if not 0 <= zero_code <= 255:
            raise ProtocolError(
                f"zero code {zero_code:g} is outside the 8-bit code range",
                "INVALID",
                "preamble_zero_code_out_of_range",
            )
        checks.append(_check("preamble_zero_code", "pass", {"zero_code": zero_code}))

    if mode_code == 0 and points != NORM_SCREEN_POINTS:
        # Measured: NORM returns the fixed 1200-point screen record. A NORM
        # preamble reporting more points is the stale-window contradiction seen
        # after leaving :WAVeform:STOP at a RAW value.
        if status == "COMPLETE":
            status = "INVALID"
        reasons.append("norm_mode_point_count_contradicts_window")
        checks.append(
            _check(
                "preamble_mode_points",
                "fail",
                {"mode": "NORM", "points": int(points), "expected_points": NORM_SCREEN_POINTS},
            )
        )
    else:
        checks.append(
            _check(
                "preamble_mode_points",
                "pass",
                {"mode": WAVEFORM_MODES[mode_code], "points": int(points)},
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "waveform-preamble",
        "command": ":WAVeform:PREamble?",
        "raw_fields": list(fields),
        "format": format_code,
        "format_name": WAVEFORM_FORMATS[format_code],
        "bytes_per_point": WAVEFORM_FORMAT_BYTES[format_code],
        "mode": mode_code,
        "mode_name": WAVEFORM_MODES[mode_code],
        "points": int(points),
        "count": int(count),
        "averages": int(count),
        "xincrement": xincrement,
        "xorigin": xorigin,
        "xreference": xreference,
        "yincrement": yincrement,
        "yorigin": yorigin,
        "yreference": yreference,
        "zero_code": zero_code,
        "zero_volts_formula": "(code - yorigin - yreference) * yincrement",
        "time_axis_formula": "xorigin + index * xincrement",
        "status": status,
        "checks": checks,
        "reasons": reasons,
    }


def parse_preamble(raw: bytes) -> dict[str, Any]:
    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="preamble")
        artifact = normalize(metadata, extract_payload(metadata))
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _failure("waveform-preamble", raw, exc.status, exc.reason, str(exc))


# ---------------------------------------------------------------------------
# IEEE 488.2 definite-length blocks
# ---------------------------------------------------------------------------


def parse_ieee_block(raw: bytes, *, allow_trailing: bool = True) -> IEEEBlock:
    """Parse one ``#<n><length><payload>`` block; keep every trailing byte."""

    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("block response must be bytes", "INVALID", "response_not_bytes")
    raw = bytes(raw)
    if not raw or raw[:1] != b"#":
        raise ProtocolError("IEEE block is missing the # prefix", "INVALID", "block_marker_missing")
    if len(raw) < 2 or not raw[1:2].isdigit():
        raise ProtocolError("IEEE block is missing the digit count", "INVALID", "block_digit_count_missing")
    digit_count = int(raw[1:2])
    if digit_count == 0:
        raise ProtocolError("indefinite IEEE blocks are not supported", "UNSUPPORTED", "indefinite_block")
    if len(raw) < 2 + digit_count:
        raise ProtocolError("IEEE block header is truncated", "INCOMPLETE", "block_header_truncated")
    length_text = raw[2 : 2 + digit_count]
    if not length_text.isdigit():
        raise ProtocolError("IEEE block length field is not numeric", "INVALID", "block_length_not_numeric")
    declared = int(length_text)
    if declared > MAX_BLOCK_BYTES:
        raise ProtocolError(
            f"IEEE payload of {declared} bytes exceeds the {MAX_BLOCK_BYTES}-byte limit",
            "UNSUPPORTED",
            "block_too_large",
        )
    header_end = 2 + digit_count
    payload_end = header_end + declared
    if len(raw) < payload_end:
        raise ProtocolError(
            f"IEEE payload is truncated: declared {declared} bytes, received {len(raw) - header_end}",
            "INCOMPLETE",
            "block_payload_truncated",
        )
    trailing = raw[payload_end:]
    if trailing and not allow_trailing:
        raise ProtocolError("extra bytes follow the IEEE payload", "INVALID", "block_trailing_bytes")
    return IEEEBlock(
        header=raw[:header_end],
        declared_length=declared,
        payload=raw[header_end:payload_end],
        trailing=trailing,
    )


def encode_ieee_block(payload: bytes, *, length_digits: int = TMC_LENGTH_DIGITS) -> bytes:
    """Encode one definite-length block (used by tests and fixture tooling)."""

    if not isinstance(payload, (bytes, bytearray)):
        raise ProtocolError("IEEE block payload must be bytes", "INVALID", "payload_not_bytes")
    payload = bytes(payload)
    if len(payload) > MAX_BLOCK_BYTES:
        raise ProtocolError("IEEE block payload is too large", "UNSUPPORTED", "block_too_large")
    length_text = str(len(payload))
    if len(length_text) > length_digits:
        raise ProtocolError("IEEE block length does not fit the digit count", "INVALID", "block_length_overflow")
    return (
        b"#"
        + str(length_digits).encode("ascii")
        + length_text.rjust(length_digits, "0").encode("ascii")
        + payload
    )


def parse_block(raw: bytes) -> dict[str, Any]:
    """Describe one generic IEEE 488.2 block without interpreting the payload."""

    raw = bytes(raw)
    try:
        block = parse_ieee_block(raw)
    except ProtocolError as exc:
        return _failure(
            "binary-block", raw, exc.status, exc.reason, str(exc), declared_bytes=None, payload_bytes=None
        )
    trailing = block.trailing
    status = "COMPLETE"
    reasons: list[str] = []
    checks = [
        _check(
            "ieee_block_header",
            "pass",
            {
                "header": block.header.decode("ascii", "replace"),
                "length_digits": int(block.header[1:2]),
            },
        ),
        _check(
            "ieee_block_length",
            "pass",
            {"declared_bytes": block.declared_length, "observed_bytes": len(block.payload)},
        ),
    ]
    if trailing in {b"", b"\n", b"\r\n"}:
        checks.append(_check("trailing_bytes", "pass", {"trailing_hex": trailing.hex()}))
    elif trailing == SCREENSHOT_TRAILING_QUIRK:
        checks.append(_check("trailing_bytes", "pass", {"trailing_hex": trailing.hex(), "known_quirk": True}))
        reasons.append("firmware_trailing_bytes_after_block")
    else:
        status = "INVALID"
        reasons.append("unexpected_trailing_bytes")
        checks.append(_check("trailing_bytes", "fail", {"trailing_hex": trailing.hex()}))

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": "binary-block",
        "declared_bytes": block.declared_length,
        "payload_bytes": len(block.payload),
        "header": block.header.decode("ascii", "replace"),
        "trailing_bytes": len(trailing),
        "trailing_hex": trailing.hex(),
        "payload_sha256": hashlib.sha256(block.payload).hexdigest(),
        "status": status,
        "checks": checks,
        "reasons": reasons,
    }
    return validate(artifact, raw)


# ---------------------------------------------------------------------------
# Waveform
# ---------------------------------------------------------------------------


def iter_codes(payload: bytes) -> Iterator[int]:
    """Yield the unsigned 8-bit waveform codes of a BYTE-format payload."""

    for code in bytes(payload):
        yield code


def sample_voltage(code: int, *, yorigin: float, yreference: float, yincrement: float) -> float:
    """Manual p. 2-221: (code - YORigin - YREFerence) * YINCrement."""

    if isinstance(code, bool) or not isinstance(code, int):
        raise ProtocolError("sample code must be an integer", "INVALID", "code_not_integer")
    if not 0 <= code <= 255:
        raise ProtocolError("sample code is outside the unsigned 8-bit range", "INVALID", "code_out_of_range")
    for name, value in (("yincrement", yincrement), ("yorigin", yorigin), ("yreference", yreference)):
        if not math.isfinite(value):
            raise ProtocolError(f"{name} is not finite", "INVALID", "scale_not_finite")
    if yincrement <= 0:
        raise ProtocolError("yincrement must be positive", "INVALID", "yincrement_not_positive")
    return (code - yorigin - yreference) * yincrement


def sample_time(index: int, *, xorigin: float, xincrement: float) -> float:
    """Manual p. 2-226: xorigin + index * xincrement."""

    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ProtocolError("sample index must be a non-negative integer", "INVALID", "index_invalid")
    for name, value in (("xorigin", xorigin), ("xincrement", xincrement)):
        if not math.isfinite(value):
            raise ProtocolError(f"{name} is not finite", "INVALID", "axis_not_finite")
    if xincrement <= 0:
        raise ProtocolError("xincrement must be positive", "INVALID", "xincrement_not_positive")
    return xorigin + index * xincrement


def summarize_codes(
    payload: bytes,
    *,
    yorigin: float,
    yreference: float,
    yincrement: float,
) -> dict[str, Any]:
    """Code-domain extremes and their converted volts for one payload."""

    payload = bytes(payload)
    if not payload:
        raise ProtocolError("waveform payload is empty", "INCOMPLETE", "empty_payload")
    minimum = min(payload)
    maximum = max(payload)
    min_volts = sample_voltage(minimum, yorigin=yorigin, yreference=yreference, yincrement=yincrement)
    max_volts = sample_voltage(maximum, yorigin=yorigin, yreference=yreference, yincrement=yincrement)
    return {
        "points": len(payload),
        "min_code": minimum,
        "max_code": maximum,
        "min_volts": min_volts,
        "max_volts": max_volts,
        "vpp_volts": (maximum - minimum) * yincrement,
    }


def _split_block_prefix(raw: bytes) -> tuple[bytes, bytes]:
    """Split an optional ASCII preamble prefix from the IEEE block."""

    index = raw.find(b"#")
    if index < 0:
        raise ProtocolError("response has no IEEE 488.2 block", "INVALID", "block_marker_missing")
    return raw[:index], raw[index:]


def parse_waveform(
    raw: bytes,
    *,
    preamble_raw: bytes | None = None,
    include_samples: bool = False,
    window_start: int | None = None,
    window_stop: int | None = None,
) -> dict[str, Any]:
    """Parse a `:WAVeform:DATA?` block with an optional `:WAVeform:PREamble?` line.

    ``preamble_raw`` overrides the ASCII prefix of ``raw``; when neither is
    present the codes are still reported but voltages stay unavailable and the
    artifact is UNVERIFIED.
    """

    raw = bytes(raw)
    if not raw:
        return _failure(
            "waveform", raw, "INCOMPLETE", "empty_response", "waveform response is empty", points=None
        )
    try:
        prefix, block_bytes = _split_block_prefix(raw)
        block = parse_ieee_block(block_bytes)
    except ProtocolError as exc:
        return _failure("waveform", raw, exc.status, exc.reason, str(exc), points=None)

    payload = block.payload
    checks: list[dict[str, Any]] = [
        _check(
            "ieee_block_header",
            "pass",
            {"header": block.header.decode("ascii", "replace"), "length_digits": int(block.header[1:2])},
        ),
        _check(
            "ieee_block_length",
            "pass",
            {"declared_bytes": block.declared_length, "observed_bytes": len(payload)},
        ),
    ]
    reasons: list[str] = []
    limitations: list[str] = []
    status = "COMPLETE"

    if block.trailing in {b"", b"\n", b"\r\n"}:
        checks.append(_check("response_terminator", "pass", {"trailing_hex": block.trailing.hex()}))
    else:
        return _failure(
            "waveform",
            raw,
            "INVALID",
            "unexpected_trailing_bytes",
            f"{len(block.trailing)} unexpected bytes follow the waveform payload",
            points=None,
        )

    if not payload:
        return _failure("waveform", raw, "INCOMPLETE", "empty_payload", "waveform payload is empty", points=None)

    preamble_source: bytes | None = preamble_raw if preamble_raw is not None else (prefix or None)
    preamble: dict[str, Any] | None = None
    if preamble_source is None:
        status = "UNVERIFIED"
        reasons.append("preamble_missing")
        checks.append(_check("preamble", "not_checked", {"reason": "preamble_missing"}))
    else:
        parsed_preamble = parse_preamble(bytes(preamble_source))
        if parsed_preamble["status"] == "COMPLETE":
            preamble = parsed_preamble
            checks.append(
                _check(
                    "preamble",
                    "pass",
                    {
                        "mode": preamble["mode_name"],
                        "format": preamble["format_name"],
                        "points": preamble["points"],
                        "yincrement": preamble["yincrement"],
                        "zero_code": preamble["zero_code"],
                        "raw_sha256": preamble["integrity"]["raw_sha256"],
                    },
                )
            )
            checks.extend(
                {**check, "name": f"preamble.{check['name']}"} for check in preamble["integrity"]["checks"]
            )
        else:
            status = parsed_preamble["status"]
            reasons.extend(parsed_preamble["integrity"]["reasons"])
            checks.append(
                _check(
                    "preamble",
                    "fail",
                    {
                        "status": parsed_preamble["status"],
                        "reasons": parsed_preamble["integrity"]["reasons"],
                        "raw_sha256": parsed_preamble["integrity"]["raw_sha256"],
                    },
                )
            )
            if "format" in parsed_preamble:
                # The fields parsed but the format cannot be decoded (WORD or
                # ASC). Keep the width/point metadata; never derive codes.
                preamble = parsed_preamble

    points = len(payload)
    bytes_per_point = 1
    if preamble is not None:
        bytes_per_point = preamble["bytes_per_point"]
        if preamble["format"] in (0, 1):
            expected_points = len(payload) // bytes_per_point
            if preamble["points"] != expected_points:
                if status == "COMPLETE":
                    status = "INVALID"
                reasons.append("declared_points_do_not_match_payload")
                checks.append(
                    _check(
                        "declared_points",
                        "fail",
                        {"declared_points": preamble["points"], "observed_points": expected_points},
                    )
                )
            else:
                checks.append(
                    _check(
                        "declared_points",
                        "pass",
                        {"declared_points": preamble["points"], "observed_points": expected_points},
                    )
                )
            points = expected_points
            if len(payload) % bytes_per_point:
                if status == "COMPLETE":
                    status = "INVALID"
                reasons.append("payload_not_a_whole_number_of_points")
                checks.append(
                    _check(
                        "sample_width",
                        "fail",
                        {"bytes_per_point": bytes_per_point, "payload_bytes": len(payload)},
                    )
                )
            else:
                checks.append(_check("sample_width", "pass", {"bytes_per_point": bytes_per_point}))
        else:
            # ASC format carries comma-separated volt strings, not fixed-width
            # codes; the payload byte count says nothing about the point count.
            checks.append(
                _check("sample_width", "not_checked", {"format": preamble["format_name"]})
            )

    if window_start is not None or window_stop is not None:
        if window_start is None or window_stop is None:
            raise ProtocolError(
                "window_start and window_stop must be supplied together",
                "INVALID",
                "window_incomplete",
            )
        if window_start < 1 or window_stop < window_start:
            raise ProtocolError(
                "waveform window must satisfy 1 <= start <= stop",
                "INVALID",
                "window_invalid",
            )
        expected = window_stop - window_start + 1
        if expected != points:
            if status == "COMPLETE":
                status = "INVALID"
            reasons.append("window_points_do_not_match_payload")
            checks.append(
                _check(
                    "window_consistency",
                    "fail",
                    {
                        "window_start": window_start,
                        "window_stop": window_stop,
                        "expected_points": expected,
                        "observed_points": points,
                    },
                )
            )
        else:
            checks.append(
                _check(
                    "window_consistency",
                    "pass",
                    {"window_start": window_start, "window_stop": window_stop, "points": points},
                )
            )
    else:
        checks.append(_check("window_consistency", "not_checked", {"reason": "window_not_supplied"}))

    codes: list[int] | None = None
    voltages: list[float] | None = None
    summary: dict[str, Any] | None = None
    if preamble is not None and preamble["format"] == 0:
        summary = summarize_codes(
            payload,
            yorigin=preamble["yorigin"],
            yreference=preamble["yreference"],
            yincrement=preamble["yincrement"],
        )
        checks.append(
            _check(
                "code_range",
                "pass" if summary["max_code"] >= summary["min_code"] else "fail",
                {"min_code": summary["min_code"], "max_code": summary["max_code"]},
            )
        )
        if include_samples:
            if points > MAX_INLINE_SAMPLES:
                return _failure(
                    "waveform",
                    raw,
                    "UNSUPPORTED",
                    "inline_samples_too_large",
                    f"inline samples are limited to {MAX_INLINE_SAMPLES} points; use --csv-out",
                    points=points,
                )
            codes = list(iter_codes(payload))
            voltages = [
                sample_voltage(
                    code,
                    yorigin=preamble["yorigin"],
                    yreference=preamble["yreference"],
                    yincrement=preamble["yincrement"],
                )
                for code in codes
            ]

    if preamble is None:
        limitations.append("no_preamble_no_time_or_voltage_axis")

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "waveform",
        "command": ":WAVeform:DATA?",
        "points": points,
        "point_count": points,
        "bytes_per_point": bytes_per_point,
        "sample_encoding": "unsigned-8-bit",
        "block_length": len(payload),
        "block_bytes": len(payload),
        "declared_block_bytes": block.declared_length,
        "trailing_bytes": len(block.trailing),
        "trailing_hex": block.trailing.hex(),
        "preamble_present": preamble is not None,
        "mode": None if preamble is None else preamble["mode_name"],
        "format": None if preamble is None else preamble["format_name"],
        "xincrement": None if preamble is None else preamble["xincrement"],
        "xorigin": None if preamble is None else preamble["xorigin"],
        "yincrement": None if preamble is None else preamble["yincrement"],
        "yorigin": None if preamble is None else preamble["yorigin"],
        "yreference": None if preamble is None else preamble["yreference"],
        "zero_code": None if preamble is None else preamble["zero_code"],
        "codes": summary,
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "limitations": limitations,
        "calibration": {
            "status": "UNVERIFIED",
            "formula": "(code - yorigin - yreference) * yincrement",
            "note": "no voltage calibration was performed; code and relative claims only",
        },
        "analysis_allowed": "code-domain-only" if status == "COMPLETE" and preamble is not None else "none",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if preamble is not None:
        artifact["preamble"] = {
            key: preamble[key]
            for key in (
                "format",
                "format_name",
                "mode",
                "mode_name",
                "points",
                "count",
                "xincrement",
                "xorigin",
                "xreference",
                "yincrement",
                "yorigin",
                "yreference",
                "zero_code",
                "raw_fields",
            )
        }
    if codes is not None:
        artifact["samples"] = codes
    if voltages is not None:
        artifact["sample_voltages"] = voltages

    artifact["integrity"] = _integrity(
        status,
        checks,
        reasons,
        raw,
        limitations=limitations or None,
        extra={
            "payload_sha256": artifact["payload_sha256"],
            "calibration": artifact["calibration"]["status"],
            "analysis_allowed": artifact["analysis_allowed"],
        },
    )
    return artifact


def normalize_waveform(
    raw: bytes,
    *,
    preamble_raw: bytes | None = None,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper for the waveform normalization stage."""

    return parse_waveform(raw, preamble_raw=preamble_raw, include_samples=include_samples)


def _format_number(value: float) -> str:
    return f"{value:.6g}"


def waveform_to_csv(
    raw: bytes,
    path: str | Path,
    *,
    preamble_raw: bytes | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write index,time,code,voltage rows for one waveform block."""

    artifact = parse_waveform(raw, preamble_raw=preamble_raw, include_samples=False)
    if artifact["status"] in FAILING_STATUSES:
        raise ProtocolError("waveform cannot be exported", artifact["status"], "waveform_not_exportable")

    prefix, block_bytes = _split_block_prefix(bytes(raw))
    block = parse_ieee_block(block_bytes)
    preamble_source = preamble_raw if preamble_raw is not None else (prefix or None)
    preamble = None if preamble_source is None else parse_preamble(bytes(preamble_source))
    if preamble is not None and preamble["status"] in FAILING_STATUSES:
        raise ProtocolError("preamble cannot be used for export", preamble["status"], "preamble_not_exportable")

    unit = "V" if preamble is not None and preamble["format"] == 0 else ""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    rows = 0
    temporary = destination.with_name(destination.name + ".tmp")

    class HashingWriter:
        def __init__(self, handle) -> None:
            self.handle = handle

        def write(self, text: str) -> int:
            hasher.update(text.encode("utf-8"))
            return self.handle.write(text)

    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(HashingWriter(handle), lineterminator="\n")
            writer.writerow(["index", "t_seconds", "code", "voltage", "voltage_unit"])
            for index, code in enumerate(iter_codes(block.payload)):
                if preamble is None:
                    t_text = ""
                    voltage_text = ""
                else:
                    t_text = _format_number(
                        sample_time(index, xorigin=preamble["xorigin"], xincrement=preamble["xincrement"])
                    )
                    voltage_text = _format_number(
                        sample_voltage(
                            code,
                            yorigin=preamble["yorigin"],
                            yreference=preamble["yreference"],
                            yincrement=preamble["yincrement"],
                        )
                    )
                writer.writerow([index, t_text, code, voltage_text, unit])
                rows += 1
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    return {
        "path": str(destination),
        "rows": rows,
        "points": artifact["points"],
        "csv_sha256": hasher.hexdigest(),
        "status": artifact["status"],
        "calibration_status": artifact["calibration"]["status"],
        "preamble_present": preamble is not None,
    }


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------


def parse_bmp_header(payload: bytes) -> dict[str, Any]:
    """Validate the structural consistency of one uncompressed BMP payload."""

    payload = bytes(payload)
    if len(payload) < 54:
        raise ProtocolError("BMP payload is shorter than a bitmap file header", "INCOMPLETE", "bmp_header_truncated")
    if payload[:2] != b"BM":
        raise ProtocolError("BMP payload does not start with BM", "INVALID", "bmp_signature_missing")
    file_size, = struct.unpack_from("<I", payload, 2)
    pixel_offset, = struct.unpack_from("<I", payload, 10)
    dib_size, = struct.unpack_from("<I", payload, 14)
    if dib_size < 40:
        raise ProtocolError(f"unsupported DIB header size {dib_size}", "UNSUPPORTED", "bmp_dib_unsupported")
    width, height = struct.unpack_from("<ii", payload, 18)
    planes, bits_per_pixel = struct.unpack_from("<HH", payload, 26)
    compression, = struct.unpack_from("<I", payload, 30)
    image_size, = struct.unpack_from("<I", payload, 34)

    if planes != 1:
        raise ProtocolError(f"BMP plane count is {planes}, expected 1", "INVALID", "bmp_planes_invalid")
    if compression != 0:
        raise ProtocolError(
            f"BMP compression {compression} is not BI_RGB", "UNSUPPORTED", "bmp_compression_unsupported"
        )
    if width <= 0 or height == 0:
        raise ProtocolError("BMP width/height are not usable", "INVALID", "bmp_geometry_invalid")
    if file_size != len(payload):
        raise ProtocolError(
            f"BMP file size field {file_size} does not match the {len(payload)}-byte payload",
            "INVALID",
            "bmp_file_size_mismatch",
        )
    if not 14 + dib_size <= pixel_offset <= file_size:
        raise ProtocolError("BMP pixel offset is outside the payload", "INVALID", "bmp_pixel_offset_invalid")
    row_size = ((width * bits_per_pixel + 31) // 32) * 4
    expected_pixels = row_size * abs(height)
    if file_size - pixel_offset != expected_pixels:
        raise ProtocolError(
            f"BMP pixel array is {file_size - pixel_offset} bytes, expected {expected_pixels}",
            "INVALID",
            "bmp_pixel_bytes_mismatch",
        )

    return {
        "width": width,
        "height": abs(height),
        "top_down": height < 0,
        "bits_per_pixel": bits_per_pixel,
        "compression": compression,
        "file_size": file_size,
        "pixel_offset": pixel_offset,
        "dib_size": dib_size,
        "image_size": image_size,
        "row_bytes": row_size,
        "pixel_bytes": expected_pixels,
        "matches_scope_panel": (width, abs(height)) == SCREENSHOT_PANEL,
    }


def parse_screenshot(raw: bytes, *, out: str | Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    """Parse `:DISPlay:DATA?`, trimming the declared image from any trailing bytes."""

    raw = bytes(raw)
    if not raw:
        return _failure("screenshot", raw, "INCOMPLETE", "empty_response", "screenshot response is empty")
    try:
        block = parse_ieee_block(raw)
    except ProtocolError as exc:
        return _failure("screenshot", raw, exc.status, exc.reason, str(exc))

    checks = [
        _check(
            "ieee_block_header",
            "pass",
            {"header": block.header.decode("ascii", "replace"), "length_digits": int(block.header[1:2])},
        ),
        _check(
            "ieee_block_length",
            "pass",
            {"declared_bytes": block.declared_length, "observed_bytes": len(block.payload)},
        ),
    ]
    reasons: list[str] = []

    trailing = block.trailing
    limitations: list[str] = []
    if trailing in {b"", b"\n", b"\r\n"}:
        checks.append(_check("trailing_bytes", "pass", {"trailing_hex": trailing.hex()}))
    elif trailing == SCREENSHOT_TRAILING_QUIRK:
        # Measured: three bytes ";0\n" follow the declared BMP on this firmware.
        # The image is exactly the declared length; the extra bytes are
        # reported, never appended to the file. The check passes because the
        # payload length is satisfied and the trailer is a known, constant
        # defect; the defect itself is carried as a reason and a limitation so
        # the overall COMPLETE status stays consistent with a passing check set.
        checks.append(
            _check(
                "trailing_bytes",
                "pass",
                {
                    "trailing_hex": trailing.hex(),
                    "declared_bytes": block.declared_length,
                    "observed_bytes": len(raw),
                    "firmware_quirk": True,
                },
            )
        )
        reasons.append("firmware_trailing_bytes_after_block")
        limitations.append("screenshot_stream_has_three_trailing_bytes")
    else:
        return _failure(
            "screenshot",
            raw,
            "INVALID",
            "unexpected_trailing_bytes",
            f"{len(trailing)} unexpected bytes follow the screenshot payload",
            declared_bytes=block.declared_length,
        )

    try:
        bmp = parse_bmp_header(block.payload)
    except ProtocolError as exc:
        return _failure(
            "screenshot",
            raw,
            exc.status,
            exc.reason,
            str(exc),
            declared_bytes=block.declared_length,
            payload_bytes=len(block.payload),
        )

    checks.append(_check("bmp_signature", "pass", {"signature": "BM"}))
    checks.append(
        _check(
            "bmp_file_size",
            "pass",
            {"file_size": bmp["file_size"], "payload_bytes": len(block.payload)},
        )
    )
    checks.append(
        _check(
            "bmp_pixel_array",
            "pass",
            {
                "width": bmp["width"],
                "height": bmp["height"],
                "bits_per_pixel": bmp["bits_per_pixel"],
                "pixel_bytes": bmp["pixel_bytes"],
            },
        )
    )

    if not bmp["matches_scope_panel"]:
        limitations.append("panel_geometry_differs_from_800x480")

    written: dict[str, Any] | None = None
    if out is not None:
        written = write_payload(block.payload, Path(out), overwrite=overwrite)

    status = "COMPLETE"
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "screenshot",
        "command": ":DISPlay:DATA?",
        "image_format": "BMP",
        "declared_bytes": block.declared_length,
        "payload_bytes": len(block.payload),
        "trailing_bytes": len(trailing),
        "trailing_hex": trailing.hex(),
        "panel": [bmp["width"], bmp["height"]],
        "matches_scope_panel": bmp["matches_scope_panel"],
        "bits_per_pixel": bmp["bits_per_pixel"],
        "compression": bmp["compression"],
        "bmp_file_size": bmp["file_size"],
        "bmp_pixel_bytes": bmp["pixel_bytes"],
        "bmp_pixel_offset": bmp["pixel_offset"],
        "trimmed_bmp_sha256": hashlib.sha256(block.payload).hexdigest(),
        "written": written,
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "limitations": limitations,
        "calibration": {"status": "not_applicable"},
    }
    artifact["integrity"] = _integrity(
        status,
        checks,
        reasons,
        raw,
        limitations=limitations or None,
        extra={
            "image_sha256": artifact["trimmed_bmp_sha256"],
            "image_bytes": len(block.payload),
        },
    )
    return artifact


def write_payload(payload: bytes, path: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    """Write exact payload bytes atomically; never overwrite by default."""

    payload = bytes(payload)
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "path": str(destination),
        "bytes": len(payload),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _status_exit_code(status: str) -> int:
    return 1 if status in FAILING_STATUSES else 0


def _dump(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser("identity", help="parse a saved *IDN? response")
    p_id.add_argument("response", type=Path)

    p_meas = sub.add_parser("measurement", help="parse a saved :MEASure:*? response")
    p_meas.add_argument("response", type=Path)
    p_meas.add_argument("--quantity", required=True, help="vpp, vmax, vavg, frequency, pduty, rtime, ...")

    p_err = sub.add_parser("error-queue", help="parse a saved :SYSTem:ERRor? response")
    p_err.add_argument("response", type=Path)
    p_err.add_argument("--response-type", choices=("auto", "error-queue"), default="auto")

    p_pre = sub.add_parser("preamble", help="parse a saved :WAVeform:PREamble? response")
    p_pre.add_argument("response", type=Path)

    p_wave = sub.add_parser("waveform", help="parse a saved :WAVeform:DATA? block")
    p_wave.add_argument("response", type=Path)
    p_wave.add_argument("--preamble", type=Path, help="separate :WAVeform:PREamble? response")
    p_wave.add_argument("--samples", action="store_true", help="include every code/voltage inline")
    p_wave.add_argument("--csv-out", type=Path)
    p_wave.add_argument("--window-start", type=int)
    p_wave.add_argument("--window-stop", type=int)
    p_wave.add_argument("--overwrite", action="store_true")

    p_shot = sub.add_parser("screenshot", help="parse a saved :DISPlay:DATA? block")
    p_shot.add_argument("response", type=Path)
    p_shot.add_argument("--out", type=Path, help="write the declared BMP bytes here")
    p_shot.add_argument("--overwrite", action="store_true")

    p_block = sub.add_parser("block", help="describe a generic IEEE 488.2 block")
    p_block.add_argument("response", type=Path)
    p_block.add_argument("--payload-out", type=Path)
    p_block.add_argument("--overwrite", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (OSError, ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "identity":
        result = parse_identity(args.response.read_bytes())
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "measurement":
        result = parse_measurement(args.response.read_bytes(), quantity=args.quantity)
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "error-queue":
        result = parse_error_queue(args.response.read_bytes(), response_type=args.response_type)
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "preamble":
        result = parse_preamble(args.response.read_bytes())
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "waveform":
        raw = args.response.read_bytes()
        preamble_raw = args.preamble.read_bytes() if args.preamble else None
        result = parse_waveform(
            raw,
            preamble_raw=preamble_raw,
            include_samples=args.samples,
            window_start=args.window_start,
            window_stop=args.window_stop,
        )
        if args.csv_out and result["status"] not in FAILING_STATUSES:
            result["csv"] = waveform_to_csv(
                raw,
                args.csv_out,
                preamble_raw=preamble_raw,
                overwrite=args.overwrite,
            )
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "screenshot":
        raw = args.response.read_bytes()
        result = parse_screenshot(raw, out=args.out, overwrite=args.overwrite)
        _dump(result)
        return _status_exit_code(result["status"])

    if args.command == "block":
        raw = args.response.read_bytes()
        result = parse_block(raw)
        if args.payload_out and result["status"] not in FAILING_STATUSES:
            result["payload_out"] = write_payload(
                parse_ieee_block(raw).payload, args.payload_out, overwrite=args.overwrite
            )
        _dump(result)
        return _status_exit_code(result["status"])

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
