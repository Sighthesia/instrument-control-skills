#!/usr/bin/env python3
"""Offline helpers for the GW Instek AFG-2225 arbitrary function generator.

This module is transport-independent: it never opens a serial port or sends a
command.  It preserves raw response bytes, separates framing/metadata/payload/
normalization/validation, and reports conservative integrity statuses.

Manual citation: AFG-2225 Series User Manual, GW Instek part no.
82RF-22250M01, REMOTE INTERFACE chapter, PDF pp. 180-265.  Vendor USB CDC
identity (0x2184:0x001c) is external/Linux-kernel evidence, not manual text.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import struct
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


PARSER_NAME = "afg2225-protocol"
PARSER_VERSION = "0.1.0"
SUPPORT_LEVEL = "documented"
MAX_ARB_POINTS = 4096
DAC_MIN = -511
DAC_MAX = 511
MAX_RESPONSE_BYTES = 65_536
MAX_IEEE_PAYLOAD_BYTES = 65_536

# Manual identity contract.  These are documented facts, not hardware evidence.
EXPECTED_VENDOR = "GW INSTEK"
EXPECTED_MODEL = "AFG-2225"

# Suffix -> (canonical unit, multiplier to the canonical unit).  The manual
# returns NR3 values without suffixes for most queries; suffixes are accepted
# only when they can be normalized without guessing.  Amplitude units are kept
# distinct because Vpp, Vrms, and dBm are not interchangeable without context.
UNIT_DEFINITIONS: dict[str, tuple[str, Decimal]] = {
    "hz": ("Hz", Decimal(1)),
    "khz": ("Hz", Decimal(1000)),
    "mhz": ("Hz", Decimal(1_000_000)),
    "ghz": ("Hz", Decimal(1_000_000_000)),
    "v": ("V", Decimal(1)),
    "mv": ("V", Decimal("0.001")),
    "vpp": ("Vpp", Decimal(1)),
    "vrms": ("Vrms", Decimal(1)),
    "dbm": ("dBm", Decimal(1)),
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
    "ppm": ("ppm", Decimal(1)),
}

# Quantity -> implied unit when a response is unitless.  An empty string means
# the quantity is intentionally unitless (for example a cycle count).
QUANTITY_UNITS = {
    "frequency": "Hz",
    "amplitude": "Vpp",
    "offset": "V",
    "phase": "deg",
    "duty": "%",
    "symmetry": "%",
    "width": "s",
    "period": "s",
    "deviation": "Hz",
    "depth": "%",
    "rate": "Hz",
    "time": "s",
    "count": "",
}

# A response suffix must belong to the quantity's accepted unit family.  The
# amplitude family is special because the manual allows Vpp, Vrms, and dBm.
QUANTITY_ALLOWED_UNITS = {
    "frequency": {"Hz"},
    "amplitude": {"Vpp", "Vrms", "dBm"},
    "offset": {"V"},
    "phase": {"deg"},
    "duty": {"%"},
    "symmetry": {"%"},
    "width": {"s"},
    "period": {"s"},
    "deviation": {"Hz"},
    "depth": {"%"},
    "rate": {"Hz"},
    "time": {"s"},
    "count": {None},
}


def _normalize_unit(unit: str) -> tuple[str, Decimal] | None:
    """Return the canonical unit and scale for a documented suffix."""

    key = unit.strip().lower()
    if key in {"µs", "μs", "us"}:
        key = "us"
    return UNIT_DEFINITIONS.get(key)


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
    """A decoded IEEE 488.2 definite-length binary block."""

    prefix: bytes
    header: bytes
    declared_length: int
    payload: bytes
    trailing: bytes = b""
    raw: bytes = b""

    @property
    def length_digits(self) -> int:
        # Number of ASCII digits used for the declared length.
        if len(self.header) < 2:
            return 0
        try:
            return int(self.header[1:2])
        except ValueError:
            return 0

    @property
    def length(self) -> int:
        return self.declared_length


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def _raw_evidence(raw: bytes) -> dict[str, str]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
    }


def read_frame(raw: bytes) -> Frame:
    """Read exactly one LF/CR/CRLF/LFCR-terminated line.

    Trailing bytes after the first complete terminator are rejected so that a
    second, unread response can never be silently merged into the first.
    """

    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("response must be bytes", "INVALID")
    raw = bytes(raw)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProtocolError("response exceeds the protocol size limit", "UNSUPPORTED")
    if not raw:
        raise ProtocolError("response is empty", "INCOMPLETE")

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
    return Frame(content=raw[:start], terminator=terminator, trailing=trailing)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains non-ASCII bytes", "INVALID") from exc


# ---------------------------------------------------------------------------
# Response stages: metadata -> payload -> normalization -> validation
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(?P<unit>[A-Za-z%°Ωµμμ]+)?$"
)
_ERROR_QUEUE_RE = re.compile(r"^\s*(?P<code>[+-]?\d+)(?:\s*,\s*|\s+)(?P<message>.+?)\s*$")


def _is_no_error_text(line: str) -> bool:
    return re.fullmatch(r'"?no error"?', line, re.IGNORECASE) is not None


def _is_known_error_queue_sentinel(code: int, message: str) -> bool:
    normalized = message.strip().strip("\"'").strip().casefold()
    return (code == 0 and normalized == "no error") or (
        abs(code) == 350 and normalized == "queue overflow"
    )


def parse_metadata(frame: Frame, *, response_type: str = "auto") -> dict[str, Any]:
    """Decode one ASCII response line and classify its raw tokens.

    This stage performs framing-to-text conversion and token classification
    only.  It does not normalize units, validate semantic ranges, or attach
    provenance; those are separate stages.
    """

    if response_type not in {"auto", "identity", "numeric", "error-queue"}:
        raise ProtocolError("response_type must be auto, identity, numeric, or error-queue", "INVALID")

    line = _text(frame)
    if not line:
        raise ProtocolError("response line is empty", "INCOMPLETE")

    if response_type == "auto":
        if _is_no_error_text(line) or _ERROR_QUEUE_RE.fullmatch(line):
            response_type = "error-queue"
            mode = "auto"
        else:
            raise ProtocolError(
                "automatic classification is limited to documented error-queue sentinels",
                "UNSUPPORTED",
            )
    else:
        mode = "explicit"

    if response_type == "identity":
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3 or len(parts) > 4:
            raise ProtocolError(
                "identity response does not have the expected comma-separated fields",
                "INVALID",
            )
        return {
            "response_type": "identity",
            "line": line,
            "fields": parts,
            "mode": mode,
        }

    if response_type == "numeric":
        match = _NUMERIC_RE.fullmatch(line)
        if not match:
            if re.search(r"\b(?:NAN|INF(?:INITY)?)\b", line, re.IGNORECASE):
                raise ProtocolError("non-finite numeric response", "INVALID")
            raise ProtocolError("response is not a supported numeric value", "INVALID")
        return {
            "response_type": "numeric",
            "line": line,
            "numeric_token": match.group("number"),
            "raw_unit": match.group("unit"),
            "mode": mode,
        }

    if _is_no_error_text(line):
        code = 0
        message = "No error"
    else:
        match = _ERROR_QUEUE_RE.fullmatch(line)
        if not match:
            raise ProtocolError(
                "error-queue response must contain an integer code and message",
                "INVALID",
            )
        code = int(match.group("code"))
        message = match.group("message").strip().strip("\"'").strip()
    return {
        "response_type": "error-queue",
        "line": line,
        "code": code,
        "message": message,
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
            "serial_field": fields[2] if len(fields) > 2 else "",
            "firmware": fields[3] if len(fields) > 3 else "",
        }
    if response_type == "numeric":
        return {
            "numeric_token": metadata["numeric_token"],
            "raw_unit": metadata["raw_unit"],
        }
    if response_type == "error-queue":
        return {"code": metadata["code"], "message": metadata["message"]}
    raise ProtocolError("metadata has no supported response_type", "UNSUPPORTED")


def normalize(
    metadata: dict[str, Any],
    payload: dict[str, Any],
    *,
    quantity: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Normalize extracted fields without changing the source bytes.

    The returned artifact contains ``status``, ``checks``, and ``reasons``;
    :func:`validate` moves the checks/reasons into the final integrity block.
    Semantic failures are raised as :class:`ProtocolError` so the high-level
    parser can return a conservative failure artifact with the raw bytes.
    """

    response_type = metadata.get("response_type")

    if response_type == "identity":
        vendor = payload["vendor"]
        model = payload["model"]
        serial_field = payload["serial_field"]
        firmware = payload["firmware"]

        if vendor.upper().replace("  ", " ") != EXPECTED_VENDOR:
            raise ProtocolError(f"unexpected vendor {vendor!r}", "INVALID")
        if model.upper() != EXPECTED_MODEL:
            raise ProtocolError(f"unexpected model {model!r}", "INVALID")

        if serial_field == "":
            raise ProtocolError("serial number is missing", "INCOMPLETE")
        if serial_field.upper().startswith("SN:"):
            serial = serial_field[3:].strip()
        else:
            raise ProtocolError("serial field is missing the SN: prefix", "INVALID")
        if not serial:
            raise ProtocolError("serial number is missing", "INCOMPLETE")
        if firmware == "":
            raise ProtocolError("firmware version is missing", "INCOMPLETE")
        if not re.fullmatch(r"V\d+\.\d+", firmware, re.IGNORECASE):
            raise ProtocolError(f"malformed firmware version {firmware!r}", "INVALID")

        identity = {
            "vendor": vendor.upper().replace("  ", " "),
            "model": model.upper(),
            "serial": serial,
            "firmware": firmware,
        }
        return {
            "schema_version": "afg2225-protocol-v1",
            "kind": "identity",
            "vendor": identity["vendor"],
            "model": identity["model"],
            "serial": identity["serial"],
            "firmware": identity["firmware"],
            "identity": identity,
            "status": "COMPLETE",
            "checks": [
                {
                    "name": "identity_parse",
                    "status": "pass",
                    "evidence": {"model": identity["model"]},
                }
            ],
            "reasons": [],
        }

    if response_type == "numeric":
        if not isinstance(quantity, str) or not quantity.strip():
            raise ProtocolError("quantity is required for numeric normalization", "INVALID")

        token = payload["numeric_token"]
        suffix = payload["raw_unit"]

        try:
            value = Decimal(token)
        except InvalidOperation as exc:
            raise ProtocolError("numeric token is not valid", "INVALID") from exc
        if not value.is_finite():
            raise ProtocolError("non-finite numeric response", "INVALID")

        expected: tuple[str | None, Decimal] | None
        explicit_unit = unit is not None
        if explicit_unit:
            if not isinstance(unit, str):
                raise ProtocolError("unit must be a string", "INVALID")
            expected = _normalize_unit(unit)
            if expected is None:
                raise ProtocolError(f"unsupported supplied unit {unit!r}", "INVALID")
        else:
            default_unit = QUANTITY_UNITS.get(quantity.lower().strip())
            if default_unit == "":
                expected = (None, Decimal(1))
            elif default_unit is None:
                expected = None
            else:
                expected = _normalize_unit(default_unit)

        if suffix:
            observed = _normalize_unit(suffix)
            if observed is None:
                raise ProtocolError(f"unrecognized response unit {suffix!r}", "INVALID")
        else:
            observed = expected

        if observed is None:
            status = "INCOMPLETE"
            reason = "unit could not be resolved from response or quantity"
            canonical_unit = None
            multiplier = Decimal(1)
            checks = [
                {
                    "name": "unit_resolution",
                    "status": "fail",
                    "evidence": {"reason": reason},
                }
            ]
        else:
            canonical_unit, multiplier = observed
            allowed = QUANTITY_ALLOWED_UNITS.get(quantity.lower().strip())
            if allowed is not None and canonical_unit not in allowed:
                raise ProtocolError(
                    "response unit does not belong to the declared quantity",
                    "INVALID",
                )
            if (
                expected is not None
                and expected[0] != canonical_unit
                and (explicit_unit or allowed is None)
            ):
                raise ProtocolError("response unit conflicts with supplied unit", "INVALID")
            status = "COMPLETE"
            reason = ""
            checks = [
                {
                    "name": "numeric_parse",
                    "status": "pass",
                    "evidence": {"token": token, "unit": canonical_unit},
                }
            ]

        try:
            normalized_value = value * multiplier
            raw_float = float(value)
            float_value = float(normalized_value)
        except (OverflowError, ValueError) as exc:
            raise ProtocolError(
                "numeric value is outside the supported finite range",
                "INVALID",
            ) from exc
        if not math.isfinite(float_value) or not math.isfinite(raw_float):
            raise ProtocolError(
                "numeric value is outside the supported finite range",
                "INVALID",
            )

        return {
            "schema_version": "afg2225-protocol-v1",
            "kind": "numeric",
            "quantity": quantity,
            "value": float_value,
            "raw_value": raw_float,
            "numeric_token": token,
            "unit": canonical_unit,
            "raw_unit": suffix,
            "status": status,
            "checks": checks,
            "reasons": [reason] if reason else [],
        }

    if response_type == "error-queue":
        code = payload["code"]
        message = payload["message"]
        mode = metadata.get("mode", "explicit")

        if mode == "auto" and not _is_known_error_queue_sentinel(code, message):
            return {
                "schema_version": "afg2225-protocol-v1",
                "kind": "unknown",
                "code": code,
                "message": message,
                "record_type": None,
                "status": "UNSUPPORTED",
                "checks": [
                    {
                        "name": "error_queue_classification",
                        "status": "fail",
                        "evidence": {"reason": "explicit_error_queue_mode_required"},
                    }
                ],
                "reasons": ["explicit_error_queue_mode_required"],
            }

        normalized = message.casefold()
        if code == 0 and normalized == "no error":
            status = "COMPLETE"
            reasons: list[str] = []
        elif abs(code) == 350 and normalized == "queue overflow":
            status = "INCOMPLETE"
            reasons = ["instrument_error_queue_overflow"]
        else:
            status = "UNVERIFIED"
            reasons = ["instrument_reported_error_or_status"]

        return {
            "schema_version": "afg2225-protocol-v1",
            "kind": "status-record",
            "record_type": "error-queue",
            "code": code,
            "message": message,
            "status": status,
            "checks": [
                {
                    "name": "error_queue_record",
                    "status": "pass",
                    "evidence": {"code": code},
                }
            ],
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
        "schema_version": "afg2225-protocol-v1",
        "kind": "identity",
        "vendor": None,
        "model": None,
        "serial": None,
        "firmware": None,
        "identity": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [
                {
                    "name": "identity_parse",
                    "status": "fail",
                    "evidence": {"reason": reason},
                }
            ],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def _numeric_failure(raw, status, reason, quantity, unit) -> dict[str, Any]:
    return {
        "schema_version": "afg2225-protocol-v1",
        "kind": "numeric",
        "quantity": quantity,
        "value": None,
        "numeric_token": None,
        "unit": unit,
        "raw_unit": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [
                {
                    "name": "numeric_parse",
                    "status": "fail",
                    "evidence": {"reason": reason},
                }
            ],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def _error_queue_failure(raw, status, reason) -> dict[str, Any]:
    return {
        "schema_version": "afg2225-protocol-v1",
        "kind": "unknown",
        "code": None,
        "message": None,
        "record_type": None,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [
                {
                    "name": "error_queue_parse",
                    "status": "fail",
                    "evidence": {"reason": reason},
                }
            ],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def parse_identity(raw: bytes) -> dict[str, Any]:
    """Validate and parse a ``*IDN?`` response through the documented stages."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload)
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _identity_failure(raw, exc.status, str(exc))


def parse_numeric(raw: bytes, *, quantity: str, unit: str | None = None) -> dict[str, Any]:
    """Parse a numeric response through metadata, payload, normalization, and validation."""

    raw = bytes(raw)
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="numeric")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload, quantity=quantity, unit=unit)
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _numeric_failure(raw, exc.status, str(exc), quantity, unit)


def parse_error_queue(raw: bytes, *, response_type: str = "auto") -> dict[str, Any]:
    """Parse a ``SYSTem:ERRor?`` response through the documented stages."""

    raw = bytes(raw)
    if response_type not in {"auto", "error-queue"}:
        return _error_queue_failure(raw, "INVALID", "response_type must be auto or error-queue")
    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type=response_type)
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload)
        return validate(artifact, raw)
    except ProtocolError as exc:
        return _error_queue_failure(raw, exc.status, str(exc))


# ---------------------------------------------------------------------------
# ARB helpers
# ---------------------------------------------------------------------------


def load_arb_csv(path_or_text: Any) -> list[int]:
    """Load the Skill-defined ARB CSV format into a list of integers."""

    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8-sig")
    elif isinstance(path_or_text, str):
        candidate = Path(path_or_text)
        is_path_candidate = "\n" not in path_or_text and "\r" not in path_or_text
        try:
            is_file = is_path_candidate and candidate.is_file()
        except OSError:
            is_file = False
        text = candidate.read_text(encoding="utf-8-sig") if is_file else path_or_text
    else:
        text = str(path_or_text)

    values: list[int] = []
    for raw_line in text.splitlines():
        # Strip comments.
        if "#" in raw_line:
            raw_line = raw_line.split("#", 1)[0]
        line = raw_line.strip()
        if not line:
            continue
        for token in re.split(r"[,\s]+", line):
            if not token:
                continue
            if not re.fullmatch(r"[+-]?\d+", token):
                raise ProtocolError(f"invalid ARB CSV integer token {token!r}", "INVALID")
            values.append(int(token))
    if not values:
        raise ProtocolError("ARB CSV contains no data", "INCOMPLETE")
    return values


def scale_normalized(values: Any, full_scale: int = 511) -> list[int]:
    """Scale normalized values in [-1, 1] to integer DAC codes.

    Rounding is half-away-from-zero.  No clamping is performed.
    """

    if not isinstance(values, (list, tuple)):
        raise ProtocolError("values must be a list or tuple", "INVALID")
    if not isinstance(full_scale, int) or full_scale <= 0:
        raise ProtocolError("full_scale must be a positive integer", "INVALID")

    result: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ProtocolError("normalized values must be finite numbers", "INVALID")
        if not math.isfinite(item):
            raise ProtocolError("normalized values must be finite", "INVALID")
        if item < -1.0 or item > 1.0:
            raise ProtocolError("normalized value is outside [-1, 1]", "INVALID")
        scaled = (Decimal(str(item)) * Decimal(full_scale)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        code = int(scaled)
        if code < DAC_MIN or code > DAC_MAX:
            raise ProtocolError("scaled DAC code is outside +/-511", "INVALID")
        result.append(code)
    return result


def validate_arb_samples(values: Any) -> dict[str, Any]:
    """Validate ARB DAC samples."""

    reasons: list[str] = []
    status = "COMPLETE"
    count = 0
    minimum = None
    maximum = None

    if not isinstance(values, (list, tuple)):
        status = "INVALID"
        reasons.append("samples must be a list or tuple")
        return _arb_validation_result(status, count, minimum, maximum, reasons)

    count = len(values)
    if count == 0:
        status = "INVALID"
        reasons.append("arb waveform must contain at least one point")
    if count > MAX_ARB_POINTS:
        status = "INVALID"
        reasons.append(f"arb waveform exceeds {MAX_ARB_POINTS} points")

    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int):
            status = "INVALID"
            reasons.append(f"sample {index} is not an integer")
            continue
        if value < DAC_MIN or value > DAC_MAX:
            status = "INVALID"
            reasons.append(f"sample {index} is outside +/-511")

    if status == "COMPLETE":
        minimum = min(values) if values else None
        maximum = max(values) if values else None

    return _arb_validation_result(status, count, minimum, maximum, reasons)


def _arb_validation_result(status, count, minimum, maximum, reasons):
    return {
        "schema_version": "afg2225-protocol-v1",
        "kind": "arb-validation",
        "count": count,
        "min": minimum,
        "max": maximum,
        "status": status,
        "integrity": {
            "status": status,
            "checks": [{"name": "arb_samples", "status": "pass" if status == "COMPLETE" else "fail", "evidence": {"count": count}}],
            "reasons": reasons,
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def encode_ieee_block(payload: bytes) -> bytes:
    """Encode a definite-length IEEE 488.2 binary block."""

    if not isinstance(payload, (bytes, bytearray)):
        raise ProtocolError("IEEE block payload must be bytes", "INVALID")
    payload = bytes(payload)
    if not payload:
        raise ProtocolError("IEEE block payload must not be empty", "INVALID")
    if len(payload) > MAX_IEEE_PAYLOAD_BYTES:
        raise ProtocolError("IEEE block payload is too large", "UNSUPPORTED")

    length_text = str(len(payload))
    header = ("#" + str(len(length_text)) + length_text).encode("ascii")
    return header + payload


def decode_ieee_block(raw: bytes) -> IEEEBlock:
    """Decode a definite-length IEEE 488.2 binary block, preserving trailing bytes."""

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
    header_end = 2 + digit_count

    if len(raw) < header_end + declared_length:
        raise ProtocolError("IEEE block payload is truncated", "INCOMPLETE")

    payload = raw[header_end : header_end + declared_length]
    trailing = raw[header_end + declared_length :]
    header = raw[:header_end]
    return IEEEBlock(prefix=b"", header=header, declared_length=declared_length, payload=payload, trailing=trailing, raw=raw)


def _validate_arb_placement(start: Any, point_count: int) -> None:
    """Validate the start address and the start + length range."""

    if isinstance(start, bool) or not isinstance(start, int):
        raise ProtocolError("start address must be an integer", "INVALID")
    if start < 0 or start > 4095:
        raise ProtocolError("start address must be in 0..4095", "INVALID")
    if point_count < 1 or point_count > MAX_ARB_POINTS:
        raise ProtocolError("arb waveform must contain 1..4096 points", "INVALID")
    if start + point_count > MAX_ARB_POINTS:
        raise ProtocolError("start address plus point count exceeds 4096", "INVALID")


def build_data_dac_ascii(start: int, values: Any) -> bytes:
    """Build an ASCII ``DATA:DAC VOLATILE`` command."""

    validation = validate_arb_samples(values)
    if validation["status"] != "COMPLETE":
        raise ProtocolError("ARB samples are invalid", validation["status"])
    _validate_arb_placement(start, len(values))

    body = "DATA:DAC VOLATILE,{}".format(start)
    if values:
        body += "," + ",".join(str(int(v)) for v in values)
    return body.encode("ascii")


def build_data_dac_binary(start: int, values: Any, *, byte_order: str) -> bytes:
    """Build a binary ``DATA:DAC VOLATILE`` command with an explicit byte order."""

    validation = validate_arb_samples(values)
    if validation["status"] != "COMPLETE":
        raise ProtocolError("ARB samples are invalid", validation["status"])
    _validate_arb_placement(start, len(values))

    if byte_order not in {"little", "big"}:
        raise ProtocolError("byte_order must be 'little' or 'big'", "INVALID")

    endian = "<" if byte_order == "little" else ">"
    payload = struct.pack(endian + "h" * len(values), *values) if values else b""
    # struct format h is signed 16-bit; values already validated to +/-511.
    block = encode_ieee_block(payload)
    command = "DATA:DAC VOLATILE,{}".format(start).encode("ascii") + b"," + block
    return command


def build_arb_artifact(
    values: Any,
    *,
    start: int = 0,
    data_format: str = "ascii",
    byte_order: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a provenance-bearing ARB artifact description."""

    validation = validate_arb_samples(values)
    if validation["status"] != "COMPLETE":
        raise ProtocolError("ARB samples are invalid", validation["status"])

    if data_format not in {"ascii", "binary"}:
        raise ProtocolError("data_format must be ascii or binary", "INVALID")
    if data_format == "binary" and byte_order not in {"little", "big"}:
        raise ProtocolError("binary ARB requires an explicit byte_order", "INVALID")

    if data_format == "ascii":
        command = build_data_dac_ascii(start, values)
        resolved_byte_order = "not-applicable"
        status = "COMPLETE"
        reasons: list[str] = []
    else:
        command = build_data_dac_binary(start, values, byte_order=byte_order)
        resolved_byte_order = byte_order
        # Byte order is an unverified operator choice; binary uploads are UNVERIFIED.
        status = "UNVERIFIED"
        reasons = ["binary_byte_order_unverified"]

    command_b64 = base64.b64encode(command).decode("ascii")
    artifact = {
        "schema_version": "afg2225-protocol-v1",
        "kind": "waveform",
        "artifact": "arbitrary-dac-command",
        "points": len(values),
        "min": min(values),
        "max": max(values),
        "format": data_format,
        "byte_order": resolved_byte_order,
        "start": start,
        "command_bytes_base64": command_b64,
        "command_sha256": hashlib.sha256(command).hexdigest(),
        "integrity": {
            "status": status,
            "checks": [{"name": "arb_command", "status": "pass" if status in {"COMPLETE", "UNVERIFIED"} else "fail", "evidence": {"format": data_format}}],
            "reasons": reasons,
            **_raw_evidence(command),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
        "provenance": {
            "manual": "AFG-2225 Series User Manual, GW Instek part no. 82RF-22250M01",
            "pages": "pp. 260-265",
            "source": source,
            "support_level": SUPPORT_LEVEL,
        },
    }
    return artifact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _status_exit_code(status: str) -> int:
    if status in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser("identity", help="parse a saved *IDN? response")
    p_id.add_argument("response", type=Path, help="path to saved raw response bytes")

    p_num = sub.add_parser("numeric", help="parse a saved numeric response")
    p_num.add_argument("response", type=Path, help="path to saved raw response bytes")
    p_num.add_argument("--quantity", required=True, help="quantity whose unit is implied when unitless")
    p_num.add_argument("--unit", help="documented unit supplied by context")

    p_err = sub.add_parser("error-queue", help="parse a saved SYSTem:ERRor? response")
    p_err.add_argument("response", type=Path, help="path to saved raw response bytes")
    p_err.add_argument("--response-type", choices=("auto", "error-queue"), default="auto")

    p_arb = sub.add_parser("arb", help="build and validate an ARB command")
    p_arb.add_argument("--csv", required=True, help="path to ARB CSV file")
    p_arb.add_argument("--format", choices=("ascii", "binary"), default="ascii", dest="data_format")
    p_arb.add_argument("--byte-order", choices=("little", "big"), default=None)
    p_arb.add_argument("--start", type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "identity":
        raw = Path(args.response).read_bytes()
        result = parse_identity(raw)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "numeric":
        raw = Path(args.response).read_bytes()
        result = parse_numeric(raw, quantity=args.quantity, unit=args.unit)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "error-queue":
        raw = Path(args.response).read_bytes()
        result = parse_error_queue(raw, response_type=args.response_type)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(result["status"])

    if args.command == "arb":
        values = load_arb_csv(args.csv)
        validation = validate_arb_samples(values)
        if validation["status"] != "COMPLETE":
            json.dump(validation, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
            sys.stdout.write("\n")
            return 1
        artifact = build_arb_artifact(
            values,
            start=args.start,
            data_format=args.data_format,
            byte_order=args.byte_order,
            source=str(args.csv),
        )
        json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
        return _status_exit_code(artifact["integrity"]["status"])

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
