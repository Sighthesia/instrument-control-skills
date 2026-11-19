#!/usr/bin/env python3
"""Offline helpers for the GW Instek GPD-4303S DC power supply.

This module is transport-independent: it never opens a serial port and never
sends a command.  It frames saved responses, separates numeric value from unit,
decodes the ``STATUS?`` bit map, recognises the manual's error messages, and
classifies command strings against the manual's command table.

Manual citation: *GPD-X303S Series User Manual*, GW Instek part no.
82PD-433S0MC1, REMOTE CONTROL chapter, PDF pp. 43-52.

Safety: this Skill ships no state-changing command builder.  :func:`build_query`
can only produce the read-only queries the manual documents; every set/mode
command (``ISET<X>:<NR2>``, ``VSET<X>:<NR2>``, ``TRACK<NR1>``, ``OUT<Boolean>``,
``BEEP<Boolean>``, ``RCL``/``SAV``, ``BAUD``, ``LOCAL``/``REMOTE``) is only
*recognised* by :func:`classify_command`.  A probe such as ``OUT1`` can energise
the outputs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

PARSER_NAME = "gpd4303s-protocol"
PARSER_VERSION = "0.1.0"
SCHEMA_VERSION = "gpd4303s-protocol-v1"

# Manual p. 46: "The command length must be 15 characters or less."  The manual
# does not say whether the terminator counts; the limit is applied to the
# command body here and the reference keeps the ambiguity visible.
MAX_COMMAND_CHARS = 15

# Manual p. 46: "Each command must end with a terminal character (ASCII: 0x0A or
# 0x0D0A)."  The verified sessions used CR LF.
COMMAND_TERMINATOR = b"\r\n"

MAX_RESPONSE_BYTES = 65_536

# Manual p. 48: VSET<X>:<NR2> range 0-32.000 V, ISET<X>:<NR2> range 0-3.200 A.
VOLTAGE_SET_RANGE = (Decimal("0"), Decimal("32.000"))
CURRENT_SET_RANGE = (Decimal("0"), Decimal("3.200"))

# Manual pp. 48-49: "X 1: CH1, 2: CH2, (4303S: 3: CH3, 4: CH4)".  All four channels
# answered on the verified unit (firmware V2.08, 2026-11-19) and their raw response
# bytes are preserved in assets/fixtures/captures/, so every per-channel query form
# carries a channel-scoped hardware claim.
VERIFIED_CHANNELS = (1, 2, 3, 4)

# Manual p. 50: STATUS? bit map.  The manual defines the bit meanings but not
# the order in which the eight characters are transmitted.
STATUS_BIT_MEANINGS = (
    ("0", "CH1", "0=CC mode, 1=CV mode"),
    ("1", "CH2", "0=CC mode, 1=CV mode"),
    ("2, 3", "Tracking", "01=Independent, 11=Tracking series, 10=Tracking parallel"),
    ("4", "Beep", "0=Off, 1=On"),
    ("5", "Output", "0=Off, 1=On"),
    ("6, 7", "Baud", "00=115200bps, 01=57600bps, 10=9600bps"),
)

# Manual p. 56: program/read-back accuracy and meter resolution, recorded so a
# parsed value is never mistaken for a calibrated measurement.
PROGRAM_ACCURACY_VOLTAGE = "± (0.03% of reading + 10mV)"
PROGRAM_ACCURACY_CURRENT = "± (0.3% of reading + 10mA)"
METER_RESOLUTION_VOLTAGE = "1mV"
METER_RESOLUTION_CURRENT = "1mA"

# The two plausible transmission orders for the eight STATUS? characters.
BIT_ORDERS = ("lsb-first", "msb-first")
# Leftmost character is bit 0.  The manual does not state the order.  Four
# independent observations of the verified unit agree with this order: the 9600
# bps baud field, the captured output bit, the BEEP0 beep bit, and a 2026-11-19
# front-panel check (SER/INDEP LED on = series tracking).  It is still an
# inference for any other unit, not a documented fact; see
# references/response-and-evidence.md.
DEFAULT_BIT_ORDER = "lsb-first"

# Manual pp. 46-47: the six error messages the GPD-X303S may return.
DOCUMENTED_ERROR_MESSAGES = {
    "program mnemonic too long": {
        "code": "a",
        "manual_text": "Program mnemonic too long",
        "description": "The command length must be 15 characters or less.",
        "example": None,
        "pdf_page": 46,
    },
    "invalid character": {
        "code": "b",
        "manual_text": "Invalid character",
        "description": "Invalid characters, such as symbols, are entered.",
        "example": "VOUT#",
        "pdf_page": 46,
    },
    "missing parameter": {
        "code": "c",
        "manual_text": "Missing parameter",
        "description": "The parameter is missing from the command.",
        "example": "VSET: (should have a number)",
        "pdf_page": 46,
    },
    "data out of range": {
        "code": "d",
        "manual_text": "Data out of range",
        "description": "The entered value exceeds the specification.",
        "example": "VSET:33 (should be <= 32V)",
        "pdf_page": 46,
    },
    "command not allowed": {
        "code": "e",
        "manual_text": "Command not allowed",
        "description": "The entered command is not allowed in the circumstance.",
        "example": "trying to set CH2 output while in the tracking mode",
        "pdf_page": 47,
    },
    "undefined header": {
        "code": "f",
        "manual_text": "Undefined header",
        "description": "The entered command does not exist, or the syntax is wrong.",
        "example": None,
        "pdf_page": 47,
    },
}


class ProtocolError(ValueError):
    """A protocol failure with a conservative integrity classification."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Command table
# ---------------------------------------------------------------------------

_NR2 = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"


@dataclass(frozen=True)
class CommandSpec:
    """One documented command form.

    ``kind`` is ``query`` (read-only), ``set`` (changes a setting or output), or
    ``mode`` (changes the remote/local interface state).
    """

    name: str
    pattern: re.Pattern[str]
    kind: str
    pdf_page: int
    description: str
    evidence: str
    value_range: tuple[Decimal, Decimal] | None = None

    @property
    def read_only(self) -> bool:
        return self.kind == "query"

    @property
    def state_changing(self) -> bool:
        return not self.read_only


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "ISET<X>:<NR2>",
        re.compile(rf"ISET(?P<x>[1-4]):(?P<value>{_NR2})", re.IGNORECASE),
        "set",
        48,
        "Sets the output current for the selected channel.",
        "documented",
        CURRENT_SET_RANGE,
    ),
    CommandSpec(
        "ISET<X>?",
        re.compile(r"ISET(?P<x>[1-4])\?", re.IGNORECASE),
        "query",
        48,
        "Returns the output current setting.",
        "hardware-verified",
    ),
    CommandSpec(
        "VSET<X>:<NR2>",
        re.compile(rf"VSET(?P<x>[1-4]):(?P<value>{_NR2})", re.IGNORECASE),
        "set",
        48,
        "Sets the output voltage for the selected channel.",
        "documented",
        VOLTAGE_SET_RANGE,
    ),
    CommandSpec(
        "VSET<X>?",
        re.compile(r"VSET(?P<x>[1-4])\?", re.IGNORECASE),
        "query",
        49,
        "Returns the output voltage setting.",
        "hardware-verified",
    ),
    CommandSpec(
        "IOUT<X>?",
        re.compile(r"IOUT(?P<x>[1-4])\?", re.IGNORECASE),
        "query",
        49,
        "Returns the actual output current.",
        "hardware-verified",
    ),
    CommandSpec(
        "VOUT<X>?",
        re.compile(r"VOUT(?P<x>[1-4])\?", re.IGNORECASE),
        "query",
        49,
        "Returns the actual output voltage.",
        "hardware-verified",
    ),
    CommandSpec(
        "TRACK<NR1>",
        re.compile(r"TRACK(?P<value>[0-2])", re.IGNORECASE),
        "set",
        49,
        "Selects the operation mode: 0 independent, 1 series, 2 parallel.",
        "documented",
    ),
    CommandSpec(
        "BEEP<Boolean>",
        re.compile(r"BEEP(?P<value>[01])", re.IGNORECASE),
        "set",
        50,
        "Turns the beep on (1) or off (0).",
        "documented",
    ),
    CommandSpec(
        "OUT<Boolean>",
        re.compile(r"OUT(?P<value>[01])", re.IGNORECASE),
        "set",
        50,
        "Turns the output on (1) or off (0).",
        "documented",
    ),
    CommandSpec(
        "STATUS?",
        re.compile(r"STATUS\?", re.IGNORECASE),
        "query",
        50,
        "Returns the 8-bit status register.",
        "hardware-verified",
    ),
    CommandSpec(
        "*IDN?",
        re.compile(r"\*IDN\?", re.IGNORECASE),
        "query",
        50,
        "Returns the instrument identification.",
        "hardware-verified",
    ),
    CommandSpec(
        "RCL<NR1>",
        re.compile(r"RCL(?P<value>[1-4])", re.IGNORECASE),
        "set",
        51,
        "Recalls a panel setting from memory 1-4.",
        "documented",
    ),
    CommandSpec(
        "SAV<NR1>",
        re.compile(r"SAV(?P<value>[1-4])", re.IGNORECASE),
        "set",
        51,
        "Stores the panel setting in memory 1-4.",
        "documented",
    ),
    CommandSpec(
        "BAUD<NR1>",
        re.compile(r"BAUD(?P<value>[0-2])", re.IGNORECASE),
        "set",
        51,
        "Sets the baud rate: 0 115200, 1 57600, 2 9600.",
        "documented",
    ),
    CommandSpec(
        "LOCAL",
        re.compile(r"LOCAL", re.IGNORECASE),
        "mode",
        51,
        "Exits remote mode and returns the instrument to local mode.",
        "documented",
    ),
    CommandSpec(
        "REMOTE",
        re.compile(r"REMOTE", re.IGNORECASE),
        "mode",
        48,
        "Exits local mode and sets the instrument to remote mode.",
        "documented",
    ),
    CommandSpec(
        "ERR?",
        re.compile(r"ERR\?", re.IGNORECASE),
        "query",
        52,
        "Returns the last error message.",
        "documented",
    ),
    CommandSpec(
        "HELP?",
        re.compile(r"HELP\?", re.IGNORECASE),
        "query",
        52,
        "Shows the command list; HELP? itself is not listed.",
        "hardware-verified",
    ),
)

COMMAND_SPEC_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}

# Response kind and quantity implied by each query, used by parse_response().
QUERY_RESPONSE_KIND = {
    "*IDN?": "identity",
    "VSET<X>?": "numeric",
    "ISET<X>?": "numeric",
    "VOUT<X>?": "numeric",
    "IOUT<X>?": "numeric",
    "STATUS?": "status",
    "HELP?": "command-list",
    "ERR?": "error-message",
}

QUERY_QUANTITY = {
    "VSET<X>?": "voltage_setting",
    "ISET<X>?": "current_setting",
    "VOUT<X>?": "voltage_measurement",
    "IOUT<X>?": "current_measurement",
}

# Quantity -> the only unit the device emits for that quantity (observed format
# "24.000V" / "1.000A"; the manual documents no response format at all).
QUANTITY_UNITS = {
    "voltage_setting": "V",
    "current_setting": "A",
    "voltage_measurement": "V",
    "current_measurement": "A",
}


def _known_mnemonic_prefix(text: str) -> str | None:
    """Return the documented mnemonic a malformed string starts with, if any."""

    head = re.split(r"[:?\s]", text, maxsplit=1)[0].upper()
    for spec in COMMAND_SPECS:
        mnemonic = re.split(r"[<?*]", spec.name.lstrip("*"), maxsplit=1)[0]
        if not mnemonic:
            continue
        if head == mnemonic or (spec.name.startswith("*") and text.startswith("*")):
            return spec.name
    return None


def classify_command(text: str) -> dict[str, Any]:
    """Classify one command string against the manual's command table.

    Never produces command bytes; use :func:`build_query` for the read-only
    subset.  The result records the manual page, the evidence level, whether the
    command changes instrument state, and any syntax/range problem.
    """

    if not isinstance(text, str):
        raise ProtocolError("command must be a string", "INVALID")
    stripped = text.strip()
    problems: list[str] = []

    if not stripped:
        raise ProtocolError("command is empty", "INVALID")
    if len(stripped) > MAX_COMMAND_CHARS:
        problems.append("command_too_long")
    if re.search(r"[\r\n]", stripped):
        problems.append("command_contains_terminator")

    for spec in COMMAND_SPECS:
        match = spec.pattern.fullmatch(stripped)
        if not match:
            continue
        groups = match.groupdict()
        channel = int(groups["x"]) if groups.get("x") else None
        value = groups.get("value")
        if value is not None and spec.value_range is not None:
            number = Decimal(value)
            low, high = spec.value_range
            if number < low or number > high:
                problems.append("value_out_of_range")
        return {
            "text": stripped,
            "known": True,
            "name": spec.name,
            "kind": spec.kind,
            "read_only": spec.read_only,
            "state_changing": spec.state_changing,
            "channel": channel,
            "value": value,
            "length": len(stripped),
            "length_limit": MAX_COMMAND_CHARS,
            "length_ok": len(stripped) <= MAX_COMMAND_CHARS,
            "pdf_page": spec.pdf_page,
            "description": spec.description,
            "evidence": spec.evidence,
            "evidence_channels": list(VERIFIED_CHANNELS) if channel is not None else None,
            "evidence_note": None,
            "problems": problems,
        }

    prefix = _known_mnemonic_prefix(stripped)
    problems.append("not_a_documented_command")
    if prefix is not None:
        problems.append("malformed_documented_command")
    return {
        "text": stripped,
        "known": False,
        "name": None,
        "kind": None,
        "read_only": False,
        "state_changing": None,
        "channel": None,
        "value": None,
        "length": len(stripped),
        "length_limit": MAX_COMMAND_CHARS,
        "length_ok": len(stripped) <= MAX_COMMAND_CHARS,
        "pdf_page": None,
        "description": None,
        "evidence": None,
        "evidence_channels": None,
        "evidence_note": None,
        "probable_documented_header": prefix,
        "problems": problems,
    }


def build_query(command: str) -> bytes:
    """Return ``command`` plus the session terminator.

    Only documented read-only queries are accepted.  A set/mode command is
    rejected here so that no code path in this Skill can turn the outputs on.
    """

    spec = classify_command(command)
    if not spec["known"]:
        raise ProtocolError(f"{command!r} is not a documented GPD command", "UNSUPPORTED")
    if not spec["read_only"]:
        raise ProtocolError(
            f"{command!r} ({spec['name']}) changes instrument state and is not built here",
            "UNSUPPORTED",
        )
    if not spec["length_ok"]:
        raise ProtocolError("command exceeds the documented 15-character limit", "INVALID")
    return spec["text"].encode("ascii") + COMMAND_TERMINATOR


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """One line response and its byte-exact framing evidence."""

    content: bytes
    terminator: bytes
    trailing: bytes = b""


@dataclass(frozen=True)
class MultiLineFrame:
    """A multi-line response (``HELP?``) with its per-line separators."""

    lines: tuple[bytes, ...]
    terminator: bytes
    raw: bytes = b""


_SEPARATOR_RE = re.compile(rb"\r\n|\n\r|\r|\n")


def _raw_evidence(raw: bytes) -> dict[str, str]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
    }


def _check_response_size(raw: bytes) -> bytes:
    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("response must be bytes", "INVALID")
    raw = bytes(raw)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProtocolError("response exceeds the protocol size limit", "UNSUPPORTED")
    if not raw:
        raise ProtocolError("response is empty", "INCOMPLETE")
    return raw


def read_frame(raw: bytes) -> Frame:
    """Read exactly one terminated line and reject any trailing bytes.

    A multi-line body (``HELP?``) is not a single-line frame; use
    :func:`read_multiline_frame` for it.
    """

    raw = _check_response_size(raw)
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

    trailing = raw[start + len(terminator) :]
    if trailing:
        raise ProtocolError("extra bytes follow the first response line", "INVALID")
    return Frame(content=raw[:start], terminator=terminator, trailing=trailing)


def read_multiline_frame(raw: bytes) -> MultiLineFrame:
    """Split a CR/LF-terminated multi-line response and preserve the raw bytes."""

    raw = _check_response_size(raw)
    if raw[-1:] not in (b"\r", b"\n"):
        raise ProtocolError("response has no line terminator", "INCOMPLETE")

    separators = _SEPARATOR_RE.findall(raw)
    lines = _SEPARATOR_RE.split(raw)
    if lines and lines[-1] == b"":
        lines.pop()
    if not lines:
        raise ProtocolError("response has no content lines", "INCOMPLETE")
    return MultiLineFrame(lines=tuple(lines), terminator=separators[-1], raw=raw)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains non-ASCII bytes", "INVALID") from exc


# ---------------------------------------------------------------------------
# Response stages: metadata -> payload -> normalization -> validation
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:\s*(?P<unit>[A-Za-z]+))?$")
_STATUS_RE = re.compile(r"^[01]{8}$")


def parse_metadata(frame: Frame, *, response_type: str = "explicit") -> dict[str, Any]:
    """Decode one ASCII response line and classify its raw tokens.

    This stage performs framing-to-text conversion and token classification
    only.  It does not resolve units, decode the status bits, or attach
    provenance.
    """

    if response_type not in {"explicit", "identity", "numeric", "status", "error-message"}:
        raise ProtocolError("unsupported response_type", "INVALID")

    line = _text(frame)
    if not line.strip():
        raise ProtocolError("response line is empty", "INCOMPLETE")

    if response_type == "identity":
        parts = [part.strip() for part in line.split(",")]
        if len(parts) not in (3, 4):
            raise ProtocolError(
                "identity response does not have the documented three or four comma-separated fields",
                "INVALID",
            )
        return {"response_type": "identity", "line": line, "fields": parts}

    if response_type == "numeric":
        match = _NUMERIC_RE.fullmatch(line.strip())
        if not match:
            raise ProtocolError("response is not a supported numeric value", "INVALID")
        return {
            "response_type": "numeric",
            "line": line,
            "numeric_token": match.group("number"),
            "raw_unit": match.group("unit"),
        }

    if response_type == "status":
        token = line.strip()
        if not _STATUS_RE.fullmatch(token):
            raise ProtocolError("status response is not eight binary digits", "INVALID")
        return {"response_type": "status", "line": line, "raw_text": token}

    # Explicit error-message mode is also the default: every other response
    # shape is reported as an instrument message rather than guessed at.
    return {"response_type": "error-message", "line": line, "message": line.strip()}


def extract_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    """Expose raw fields without unit conversion or semantic classification."""

    response_type = metadata.get("response_type")
    if response_type == "identity":
        fields = metadata["fields"]
        return {
            "vendor": fields[0],
            "model": fields[1],
            "serial_field": fields[2],
            "firmware": fields[3] if len(fields) > 3 else "",
        }
    if response_type == "numeric":
        return {
            "numeric_token": metadata["numeric_token"],
            "raw_unit": metadata["raw_unit"],
        }
    if response_type == "status":
        return {"raw_text": metadata["raw_text"]}
    if response_type == "error-message":
        return {"message": metadata["message"]}
    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED")


def decode_status_bits(bits: Sequence[int], *, bit_order: str = DEFAULT_BIT_ORDER) -> dict[str, Any]:
    """Decode the eight ``STATUS?`` bits using the manual's bit map (p. 50).

    ``bits`` is the wire order of the eight characters.  ``bit_order`` says
    whether the leftmost character is bit 0 (``lsb-first``) or bit 7
    (``msb-first``); the manual does not state which.  Multi-bit fields are read
    low index first, matching the manual's ``01``/``11``/``10`` and ``00``/``01``
    /``10`` encodings.
    """

    if bit_order not in BIT_ORDERS:
        raise ProtocolError("bit_order must be lsb-first or msb-first", "INVALID")
    values = [int(bit) for bit in bits]
    if len(values) != 8 or any(value not in (0, 1) for value in values):
        raise ProtocolError("status must be eight binary digits", "INVALID")

    bit = values if bit_order == "lsb-first" else list(reversed(values))
    tracking_code = f"{bit[2]}{bit[3]}"
    baud_code = f"{bit[6]}{bit[7]}"
    return {
        "wire_order": values,
        "bit_order": bit_order,
        "ch1_regulation": "CV" if bit[0] else "CC",
        "ch2_regulation": "CV" if bit[1] else "CC",
        "tracking_code": tracking_code,
        "tracking": {"01": "independent", "11": "series", "10": "parallel"}.get(
            tracking_code, "undefined"
        ),
        "beep": "on" if bit[4] else "off",
        "output": "on" if bit[5] else "off",
        "baud_code": baud_code,
        "baud_bps": {"00": 115200, "01": 57600, "10": 9600}.get(baud_code),
    }


def normalize(
    metadata: dict[str, Any],
    payload: dict[str, Any],
    *,
    quantity: str | None = None,
    channel: int | None = None,
    bit_order: str = DEFAULT_BIT_ORDER,
) -> dict[str, Any]:
    """Normalize extracted fields without changing the source bytes."""

    response_type = metadata.get("response_type")

    if response_type == "identity":
        vendor = payload["vendor"].strip()
        model = payload["model"].strip()
        serial_field = payload["serial_field"].strip()
        firmware = payload["firmware"].strip()

        if vendor.upper() != "GW INSTEK":
            raise ProtocolError(f"unexpected vendor {vendor!r}", "INVALID")
        if model.upper() != "GPD-4303S":
            raise ProtocolError(f"unexpected model {model!r}", "INVALID")
        if not serial_field.upper().startswith("SN:"):
            raise ProtocolError("serial field is missing the SN: prefix", "INVALID")
        serial = serial_field[3:].strip()
        if not serial:
            raise ProtocolError("serial number is missing", "INCOMPLETE")
        if not firmware:
            raise ProtocolError("firmware version is missing", "INCOMPLETE")
        if not re.fullmatch(r"V\d+\.\d+", firmware, re.IGNORECASE):
            raise ProtocolError(f"malformed firmware version {firmware!r}", "INVALID")

        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "identity",
            "vendor": "GW INSTEK",
            "model": "GPD-4303S",
            "serial": serial,
            "firmware": firmware,
            "identity": {
                "vendor": "GW INSTEK",
                "model": "GPD-4303S",
                "serial": serial,
                "firmware": firmware,
            },
            "status": "COMPLETE",
            "checks": [
                {
                    "name": "identity_parse",
                    "status": "pass",
                    "evidence": {"model": model.upper(), "firmware": firmware},
                }
            ],
            "reasons": [],
        }

    if response_type == "numeric":
        if quantity not in QUANTITY_UNITS:
            raise ProtocolError(f"unsupported quantity {quantity!r}", "INVALID")

        token = payload["numeric_token"]
        suffix = payload["raw_unit"]
        expected_unit = QUANTITY_UNITS[quantity]

        try:
            value = Decimal(token)
        except InvalidOperation as exc:
            raise ProtocolError("numeric token is not valid", "INVALID") from exc
        if not value.is_finite():
            raise ProtocolError("non-finite numeric response", "INVALID")

        reasons: list[str] = []
        checks: list[dict[str, Any]] = []
        if suffix is None:
            status = "INCOMPLETE"
            reasons.append("response_unit_missing")
            checks.append(
                {
                    "name": "unit_resolution",
                    "status": "fail",
                    "evidence": {"reason": "the device always sends V or A; a unitless token cannot be attributed"},
                }
            )
            raw_unit = None
            unit = None
        else:
            raw_unit = suffix
            unit = suffix.upper() if len(suffix) == 1 else suffix
            if unit != expected_unit:
                raise ProtocolError(
                    f"response unit {suffix!r} conflicts with quantity {quantity!r} ({expected_unit})",
                    "INVALID",
                )
            status = "COMPLETE"
            checks.append(
                {
                    "name": "unit_resolution",
                    "status": "pass",
                    "evidence": {"unit": unit, "quantity": quantity},
                }
            )

        digits = len(token.partition(".")[2]) if "." in token else 0
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "scalar-value",
            "quantity": quantity,
            "channel": channel,
            "value": float(value),
            "unit": unit,
            "raw_token": token,
            "raw_unit": raw_unit,
            "resolution_digits": digits,
            "status": status,
            "checks": checks,
            "reasons": reasons,
        }

    if response_type == "status":
        decoded = decode_status_bits(payload["raw_text"], bit_order=bit_order)
        other = "msb-first" if bit_order == "lsb-first" else "lsb-first"
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "status-record",
            "record_type": "status-register",
            "command": "STATUS?",
            "raw_text": payload["raw_text"],
            "wire_order": decoded["wire_order"],
            "bit_order": bit_order,
            "decoded": {key: decoded[key] for key in (
                "ch1_regulation",
                "ch2_regulation",
                "tracking_code",
                "tracking",
                "beep",
                "output",
                "baud_code",
                "baud_bps",
            )},
            "decoded_alternate_order": {
                key: decode_status_bits(payload["raw_text"], bit_order=other)[key]
                for key in (
                    "ch1_regulation",
                    "ch2_regulation",
                    "tracking_code",
                    "tracking",
                    "beep",
                    "output",
                    "baud_code",
                    "baud_bps",
                )
            },
            "status": "UNVERIFIED",
            "checks": [
                {
                    "name": "status_width",
                    "status": "pass",
                    "evidence": {"characters": 8},
                },
                {
                    "name": "status_alphabet",
                    "status": "pass",
                    "evidence": {"values": sorted(set(payload["raw_text"]))},
                },
                {
                    "name": "status_bit_meanings",
                    "status": "pass",
                    "evidence": {"manual": "GPD-X303S Series User Manual p. 50"},
                },
                {
                    "name": "status_bit_order",
                    # The default order is corroborated by four independent
                    # observations, one of them a front-panel check on 2026-11-19
                    # (SER/INDEP LED on = series tracking).  The manual still does
                    # not state the order, so that evidence is scoped to the
                    # verified unit; the artifact stays UNVERIFIED.
                    "status": "pass" if bit_order == DEFAULT_BIT_ORDER else "not_checked",
                    "evidence": {
                        "used": bit_order,
                        "manual_defines_order": False,
                        "reason": "the manual defines the bits but not their transmission order",
                        "corroborated_by": [
                            "baud_9600_matches_link",
                            "output_off_matches_vout_zero",
                            "beep_off_matches_beep0",
                            "panel_ser_indep_led_on_matches_series_decode",
                        ] if bit_order == DEFAULT_BIT_ORDER else [],
                    },
                },
            ],
            "reasons": [
                "status_bit_order_not_documented_but_panel_corroborated"
                if bit_order == DEFAULT_BIT_ORDER
                else "status_bit_order_not_documented"
            ],
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
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
    }
    return artifact


# ---------------------------------------------------------------------------
# High-level parsers
# ---------------------------------------------------------------------------


def _failure(kind: str, raw: bytes, status: str, reason: str, **fields: Any) -> dict[str, Any]:
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        **fields,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [{"name": f"{kind}_parse", "status": "fail", "evidence": {"reason": reason}}],
            "reasons": [reason],
            **_raw_evidence(bytes(raw)),
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }
    return artifact


def parse_identity(raw: bytes) -> dict[str, Any]:
    """Parse a saved ``*IDN?`` response."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        payload = extract_payload(metadata)
        return validate(normalize(metadata, payload), raw)
    except ProtocolError as exc:
        return _failure(
            "identity",
            raw,
            exc.status,
            str(exc),
            vendor=None,
            model=None,
            serial=None,
            firmware=None,
            identity=None,
        )


def parse_reading(
    raw: bytes, *, quantity: str, channel: int | None = None
) -> dict[str, Any]:
    """Parse a saved ``VSET``/``ISET``/``VOUT``/``IOUT`` response."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="numeric")
        payload = extract_payload(metadata)
        return validate(
            normalize(metadata, payload, quantity=quantity, channel=channel),
            raw,
        )
    except ProtocolError as exc:
        return _failure(
            "scalar-value",
            raw,
            exc.status,
            str(exc),
            quantity=quantity,
            channel=channel,
            value=None,
            unit=QUANTITY_UNITS.get(quantity),
            raw_token=None,
            raw_unit=None,
            resolution_digits=None,
        )


def parse_status(raw: bytes, *, bit_order: str = DEFAULT_BIT_ORDER) -> dict[str, Any]:
    """Parse a saved ``STATUS?`` response and decode the manual's bit map."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="status")
        payload = extract_payload(metadata)
        return validate(normalize(metadata, payload, bit_order=bit_order), raw)
    except ProtocolError as exc:
        return _failure(
            "status-record",
            raw,
            exc.status,
            str(exc),
            record_type="status-register",
            command="STATUS?",
            raw_text=None,
            decoded=None,
        )


def parse_error_message(raw: bytes) -> dict[str, Any]:
    """Parse a saved instrument error message (manual pp. 46-47)."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="error-message")
        payload = extract_payload(metadata)
    except ProtocolError as exc:
        return _failure(
            "error-message",
            raw,
            exc.status,
            str(exc),
            message=None,
            code=None,
            documented=False,
        )

    message = payload["message"]
    key = message.strip().rstrip(".").strip().casefold()
    documented = DOCUMENTED_ERROR_MESSAGES.get(key)
    if documented is None:
        return _failure(
            "error-message",
            raw,
            "UNSUPPORTED",
            "message is not one of the six documented error messages",
            message=message,
            code=None,
            documented=False,
        )
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": "error-message",
        "message": message,
        "normalized": key,
        "code": documented["code"],
        "documented_text": documented["manual_text"],
        "description": documented["description"],
        "example": documented["example"],
        "pdf_page": documented["pdf_page"],
        "written_as_documented": message.strip() == documented["manual_text"],
        "status": "COMPLETE",
        "checks": [
            {
                "name": "error_message_match",
                "status": "pass",
                "evidence": {"code": documented["code"], "normalized": key},
            }
        ],
        "reasons": [],
    }
    return validate(artifact, raw)


def parse_command_list(raw: bytes) -> dict[str, Any]:
    """Parse a saved ``HELP?`` response, preserving every line."""

    raw = bytes(raw)
    try:
        frame = read_multiline_frame(raw)
        try:
            lines = [line.decode("ascii") for line in frame.lines]
        except UnicodeDecodeError as exc:
            raise ProtocolError("response contains non-ASCII bytes", "INVALID") from exc
    except ProtocolError as exc:
        return _failure(
            "command-list", raw, exc.status, str(exc), lines=None, advertised_commands=None
        )

    return validate(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "command-list",
            "command": "HELP?",
            "lines": lines,
            "line_count": len(lines),
            "advertised_commands": extract_advertised_commands(lines),
            "status": "COMPLETE",
            "checks": [
                {
                    "name": "command_list_framing",
                    "status": "pass",
                    "evidence": {"lines": len(lines), "terminator": frame.terminator.decode("ascii")},
                },
                {
                    "name": "command_list_lines_non_empty",
                    "status": "pass" if all(line.strip() for line in lines) else "fail",
                    "evidence": {"empty_lines": sum(1 for line in lines if not line.strip())},
                },
            ],
            "reasons": [],
        },
        raw,
    )


def extract_advertised_commands(lines: Iterable[str]) -> list[str]:
    """Return the leading mnemonic of each non-indented ``HELP?`` line."""

    advertised: list[str] = []
    for line in lines:
        if not line or line[0].isspace():
            continue
        match = re.match(r"^(?P<token>\*?[A-Za-z]+(?:<[^>]*>)?\??)", line)
        if match:
            advertised.append(match.group("token"))
    return advertised


def parse_response(
    raw: bytes, command: str, *, bit_order: str = DEFAULT_BIT_ORDER
) -> dict[str, Any]:
    """Dispatch a saved response using the command that produced it."""

    spec = classify_command(command)
    if not spec["known"]:
        raise ProtocolError(f"{command!r} is not a documented GPD command", "UNSUPPORTED")
    if not spec["read_only"]:
        raise ProtocolError(f"{command!r} is not a query", "UNSUPPORTED")

    kind = QUERY_RESPONSE_KIND.get(spec["name"])
    if kind == "identity":
        artifact = parse_identity(raw)
    elif kind == "numeric":
        artifact = parse_reading(
            raw,
            quantity=QUERY_QUANTITY[spec["name"]],
            channel=spec["channel"],
        )
    elif kind == "status":
        artifact = parse_status(raw, bit_order=bit_order)
    elif kind == "command-list":
        artifact = parse_command_list(raw)
    elif kind == "error-message":
        artifact = parse_error_message(raw)
    else:
        raise ProtocolError(f"{command!r} has no implemented response parser", "UNSUPPORTED")

    artifact["command"] = spec["text"]
    artifact.setdefault("evidence", {})
    artifact["evidence"].update(
        {
            "command": spec["text"],
            "command_evidence": spec["evidence"],
            "pdf_page": spec["pdf_page"],
        }
    )
    return artifact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(artifact: dict[str, Any]) -> int:
    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    status = artifact.get("integrity", {}).get("status")
    return 1 if status in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_id = sub.add_parser("identity", help="parse a saved *IDN? response")
    p_id.add_argument("response", type=Path)

    p_reading = sub.add_parser("reading", help="parse a saved VSET/ISET/VOUT/IOUT response")
    p_reading.add_argument("response", type=Path)
    p_reading.add_argument(
        "--query", required=True, help="the query that produced the response, e.g. VOUT1?"
    )
    p_reading.add_argument("--bit-order", choices=BIT_ORDERS, default=DEFAULT_BIT_ORDER)

    p_status = sub.add_parser("status", help="parse a saved STATUS? response")
    p_status.add_argument("response", type=Path)
    p_status.add_argument("--bit-order", choices=BIT_ORDERS, default=DEFAULT_BIT_ORDER)

    p_error = sub.add_parser("error", help="parse a saved instrument error message")
    p_error.add_argument("response", type=Path)

    p_help = sub.add_parser("help", help="parse a saved HELP? command list")
    p_help.add_argument("response", type=Path)

    p_classify = sub.add_parser("classify", help="classify a command string without sending it")
    p_classify.add_argument("command_text")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.subcommand == "classify":
        result = classify_command(args.command_text)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if result["known"] and not result["problems"] else 1

    raw = Path(args.response).read_bytes()
    if args.subcommand == "identity":
        return _emit(parse_identity(raw))
    if args.subcommand == "reading":
        return _emit(parse_response(raw, args.query, bit_order=args.bit_order))
    if args.subcommand == "status":
        return _emit(parse_status(raw, bit_order=args.bit_order))
    if args.subcommand == "error":
        return _emit(parse_error_message(raw))
    if args.subcommand == "help":
        return _emit(parse_command_list(raw))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
