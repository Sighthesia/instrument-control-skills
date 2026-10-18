#!/usr/bin/env python3
"""Parse saved Keithley Model 2000 single-reading ASCII responses.

This module is transport-independent: it never connects to an instrument or
sends commands. Raw response bytes are retained as base64 and SHA-256 evidence
in the returned JSON-compatible artifact.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PARSER_NAME = "keithley2000-scalar"
PARSER_VERSION = "0.1.0"
SUPPORT_LEVEL = "documented"
MAX_RESPONSE_BYTES = 65_536


class ParserError(ValueError):
    """A parser failure with a conservative integrity classification."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Frame:
    """One line response and its byte-exact framing evidence."""

    content: bytes
    terminator: bytes
    trailing: bytes


ERROR_QUEUE_RE = re.compile(r"^\s*(?P<code>[+-]?\d+)\s*,\s*(?P<message>.*?)\s*$")
SCALAR_RE = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)(?P<unit>[A-Za-z]+)?$"
)
CHANNEL_RE = re.compile(r"^(?P<channel>\d+)(?P<kind>INTCHAN|EXTCHAN)$", re.IGNORECASE)
SUPPORTED_RESPONSE_UNITS = {"VDC", "VAC", "ADC", "AAC", "OHM", "OHM4W", "HZ", "C", "F", "K"}
OVERFLOW_SENTINEL = Decimal("9.9E37")


def _check(name: str, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _raw_evidence(raw: bytes) -> dict[str, str]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
    }


def _failure(
    raw: bytes,
    status: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "keithley2000-scalar-v1",
        "kind": "unknown",
        "context": context or {},
        "integrity": {
            "status": status,
            "checks": [_check("response_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_raw_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def read_frame(raw: bytes) -> Frame:
    """Read exactly one CR, LF, CRLF, or LFCR-terminated ASCII response line."""

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ParserError("response exceeds the scalar parser size limit", "UNSUPPORTED")
    if raw.startswith(b"#"):
        raise ParserError("IEEE-488.2 block data is not supported by the scalar parser", "UNSUPPORTED")
    if not raw:
        raise ParserError("response is empty", "INCOMPLETE")

    positions = [position for delimiter in (b"\r", b"\n") if (position := raw.find(delimiter)) >= 0]
    if not positions:
        raise ParserError("response has no line terminator", "INCOMPLETE")

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
    return Frame(content=raw[:start], terminator=terminator, trailing=raw[end:])


def _is_error_queue_message(message: str) -> bool:
    """Distinguish error text from the documented ``0INTCHAN`` field."""

    stripped = message.strip()
    if not stripped:
        return False
    if CHANNEL_RE.fullmatch(stripped):
        return False
    unquoted = stripped.strip("\"'").strip()
    if unquoted.casefold() in {"no error", "queue overflow"}:
        return True
    if SCALAR_RE.fullmatch(unquoted):
        return False
    if re.match(r"^[+-]?(?:\d|\.\d)", unquoted):
        return False
    return any(character.isalpha() for character in unquoted)


def _is_documented_scalar_channel_pair(line: str) -> bool:
    """Avoid mistaking a signed reading plus channel token for an error code."""

    parts = line.split(",")
    return (
        len(parts) == 2
        and SCALAR_RE.fullmatch(parts[0].strip()) is not None
        and CHANNEL_RE.fullmatch(parts[1].strip()) is not None
    )


def parse_metadata(frame: Frame, response_type: str = "auto") -> dict[str, Any]:
    """Classify a line and parse documented scalar or error-queue metadata."""

    if response_type not in {"auto", "measurement", "error-queue"}:
        raise ParserError("response_type must be auto, measurement, or error-queue", "INVALID")
    if frame.trailing:
        raise ParserError("extra bytes follow the first response line", "INVALID")
    if not frame.content:
        raise ParserError("response line is empty", "INCOMPLETE")

    try:
        line = frame.content.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ParserError("response contains non-ASCII bytes", "INVALID") from exc
    if not line:
        raise ParserError("response line contains no data", "INCOMPLETE")

    if line.upper() in {"OVLD", "OVERFLOW"}:
        if response_type == "error-queue":
            raise ParserError("error-queue response is not a code/message record", "INVALID")
        return {
            "kind": "scalar-measurement",
            "raw_line": line,
            "reading_status": "OVERFLOW",
            "numeric_token": None,
            "value": None,
            "response_unit": None,
            "channel": None,
            "channel_kind": None,
        }

    error_match = ERROR_QUEUE_RE.fullmatch(line)
    if error_match and response_type == "error-queue":
        return {
            "kind": "status-record",
            "record_type": "error-queue",
            "raw_line": line,
            "code": int(error_match.group("code")),
            "message": error_match.group("message").strip(),
        }

    if (
        error_match
        and response_type == "auto"
        and not _is_documented_scalar_channel_pair(line)
        and _is_error_queue_message(error_match.group("message"))
    ):
        return {
            "kind": "status-record",
            "record_type": "error-queue",
            "raw_line": line,
            "code": int(error_match.group("code")),
            "message": error_match.group("message").strip(),
        }

    if response_type == "error-queue":
        raise ParserError("error-queue response must contain an integer code and message", "INVALID")

    parts = line.split(",")
    if len(parts) > 2:
        raise ParserError("multiple values or ambiguous CSV fields are unsupported", "UNSUPPORTED")

    reading_match = SCALAR_RE.fullmatch(parts[0].strip())
    if not reading_match:
        if re.search(r"\b(?:NAN|INF(?:INITY)?)\b", parts[0], re.IGNORECASE):
            raise ParserError("non-finite numeric responses are invalid", "INVALID")
        if len(parts) == 1:
            raise ParserError("response is not a supported scalar ASCII reading", "INVALID")
        raise ParserError("comma-separated response is not a supported reading/channel pair", "UNSUPPORTED")

    numeric_token = reading_match.group("number")
    response_unit = reading_match.group("unit")
    if response_unit and response_unit.upper() not in SUPPORTED_RESPONSE_UNITS:
        raise ParserError(f"unrecognized response unit {response_unit!r}", "UNSUPPORTED")

    channel: int | None = None
    channel_kind: str | None = None
    if len(parts) == 2:
        channel_match = CHANNEL_RE.fullmatch(parts[1].strip())
        if not channel_match:
            raise ParserError("second field is not a documented channel token", "UNSUPPORTED")
        channel = int(channel_match.group("channel"))
        channel_kind = channel_match.group("kind").upper()

    try:
        decimal_value = Decimal(numeric_token)
    except InvalidOperation as exc:
        raise ParserError("reading token is not numeric", "INVALID") from exc
    if not decimal_value.is_finite():
        raise ParserError("non-finite numeric responses are invalid", "INVALID")
    if response_unit is None and abs(decimal_value) == OVERFLOW_SENTINEL:
        reading_status = "OVERFLOW"
        value: float | None = None
    else:
        try:
            value = float(decimal_value)
        except (OverflowError, ValueError) as exc:
            raise ParserError("numeric reading is outside the supported finite range", "INVALID") from exc
        if not math.isfinite(value):
            raise ParserError("numeric reading is outside the supported finite range", "INVALID")
        if decimal_value != 0 and value == 0.0:
            raise ParserError("numeric reading underflows floating-point range", "INVALID")
        reading_status = "VALID"

    return {
        "kind": "scalar-measurement",
        "raw_line": line,
        "reading_status": reading_status,
        "numeric_token": numeric_token,
        "value": value,
        "response_unit": response_unit,
        "channel": channel,
        "channel_kind": channel_kind,
    }


def extract_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract one scalar value or status without transforming raw evidence."""

    if metadata.get("kind") == "status-record":
        return {
            "record_type": metadata["record_type"],
            "code": metadata["code"],
            "message": metadata["message"],
        }
    return {
        "numeric_token": metadata.get("numeric_token"),
        "value": metadata.get("value"),
        "reading_status": metadata["reading_status"],
        "response_unit": metadata.get("response_unit"),
        "channel": metadata.get("channel"),
        "channel_kind": metadata.get("channel_kind"),
    }


def _unit_dimension(unit: str | None) -> str | None:
    if not unit:
        return None
    normalized = (
        unit.strip()
        .upper()
        .replace("°", "")
        .replace("Ω", "OHM")
        .replace("Μ", "U")
        .replace("μ", "U")
        .replace("µ", "U")
        .replace(" ", "")
    )
    aliases = {
        "VDC": "voltage",
        "VAC": "voltage",
        "V": "voltage",
        "VOLT": "voltage",
        "VOLTS": "voltage",
        "ADC": "current",
        "AAC": "current",
        "A": "current",
        "AMP": "current",
        "AMPS": "current",
        "OHM": "resistance",
        "OHMS": "resistance",
        "OHM4W": "resistance",
        "HZ": "frequency",
        "KHZ": "frequency",
        "MHZ": "frequency",
        "GHZ": "frequency",
        "S": "time",
        "SEC": "time",
        "SECS": "time",
        "SECOND": "time",
        "SECONDS": "time",
        "MS": "time",
        "MSEC": "time",
        "MSECS": "time",
        "US": "time",
        "USEC": "time",
        "USECS": "time",
        "NS": "time",
        "NSEC": "time",
        "C": "temperature",
        "DEGC": "temperature",
        "CELSIUS": "temperature",
        "F": "temperature",
        "DEGF": "temperature",
        "FAHRENHEIT": "temperature",
        "K": "temperature",
        "KELVIN": "temperature",
    }
    if normalized in aliases:
        return aliases[normalized]
    if re.fullmatch(r"[PNUMK]?V", normalized):
        return "voltage"
    if re.fullmatch(r"[PNUMK]?A", normalized):
        return "current"
    if re.fullmatch(r"[PNUMK]?OHM", normalized):
        return "resistance"
    return None


def _function_dimension(function: Any) -> str | None:
    if not isinstance(function, str):
        return None
    normalized = function.strip().strip("'\" ").upper().replace(" ", "")
    normalized = re.sub(r"^:?(?:SENSE(?:\[1\])?:)?", "", normalized)
    if normalized.startswith("VOLT"):
        return "voltage"
    if normalized.startswith("CURR"):
        return "current"
    if normalized.startswith("FRES") or normalized.startswith("RES") or normalized.startswith("CONT"):
        return "resistance"
    if normalized.startswith("FREQ"):
        return "frequency"
    if normalized.startswith("PER"):
        return "time"
    if normalized.startswith("TEMP"):
        return "temperature"
    if normalized.startswith("DIO"):
        return "voltage"
    return None


def normalize(
    metadata: dict[str, Any], payload: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a JSON-compatible measurement/status artifact."""

    context = dict(context or {})
    if metadata.get("kind") == "status-record":
        return {
            "schema_version": "keithley2000-scalar-v1",
            "kind": "status-record",
            "record": payload,
            "context": context,
        }

    response_unit = payload.get("response_unit")
    context_unit = context.get("unit")
    function_dimension = _function_dimension(context.get("function"))
    if response_unit and context_unit:
        response_dimension = _unit_dimension(str(response_unit))
        context_dimension = _unit_dimension(str(context_unit))
        if response_dimension and context_dimension and response_dimension != context_dimension:
            raise ParserError("response unit conflicts with supplied unit context", "INVALID")

    for candidate_unit, candidate_source in (
        (response_unit, "response"),
        (context_unit, "context"),
    ):
        unit_dimension = _unit_dimension(str(candidate_unit)) if candidate_unit else None
        if (
            function_dimension
            and unit_dimension
            and function_dimension != unit_dimension
        ):
            raise ParserError(
                f"{candidate_source} unit conflicts with supplied measurement function",
                "INVALID",
            )

    unit = response_unit or context_unit
    unit_source = "response" if response_unit else "context" if context_unit else None
    return {
        "schema_version": "keithley2000-scalar-v1",
        "kind": "scalar-measurement",
        "measurement": {
            "value": payload.get("value"),
            "numeric_token": payload.get("numeric_token"),
            "unit": unit,
            "raw_response_unit": response_unit,
            "unit_source": unit_source,
            "function": context.get("function"),
            "reading_status": payload["reading_status"],
            "channel": payload.get("channel"),
            "channel_kind": payload.get("channel_kind"),
        },
        "context": context,
    }


def validate(
    artifact: dict[str, Any],
    *,
    raw: bytes,
    frame: Frame,
) -> dict[str, Any]:
    """Validate only claims supported by the response and caller context."""

    evidence = _raw_evidence(raw)
    checks: list[dict[str, Any]] = [_check("line_terminator", "pass", {"terminator_hex": frame.terminator.hex()})]
    reasons: list[str] = []
    context = artifact.get("context", {})

    if frame.trailing:
        checks.append(_check("single_response_frame", "fail", {"trailing_hex": frame.trailing.hex()}))
        reasons.append("extra_bytes_after_response")
        status = "INVALID"
    elif artifact["kind"] == "status-record":
        record = artifact["record"]
        code = record["code"]
        checks.append(_check("error_queue_record", "pass", {"code": code}))
        if code == 0:
            status = "COMPLETE"
        elif code == 350:
            status = "INCOMPLETE"
            reasons.append("instrument_error_queue_overflow")
        else:
            status = "UNVERIFIED"
            reasons.append("instrument_reported_error_or_status")
    else:
        measurement = artifact["measurement"]
        if measurement["reading_status"] == "OVERFLOW":
            checks.append(_check("reading_status", "fail", {"status": "OVERFLOW"}))
            reasons.append("instrument_reported_overflow")
            status = "UNVERIFIED"
        else:
            checks.append(_check("numeric_reading", "pass", {"token": measurement["numeric_token"]}))
            missing: list[str] = []
            if not measurement.get("unit"):
                missing.append("unit_missing")
            if not measurement.get("function"):
                missing.append("function_context_missing")
            if missing:
                checks.append(_check("measurement_context", "fail", {"missing": missing}))
                reasons.extend(missing)
                status = "INCOMPLETE"
            elif context.get("acquisition_complete") is not True:
                checks.append(_check("acquisition_completeness", "not_checked", {"required_assertion": True}))
                reasons.append("acquisition_completeness_not_asserted")
                status = "UNVERIFIED"
            else:
                checks.append(_check("measurement_context", "pass", {"function": measurement["function"], "unit": measurement["unit"]}))
                checks.append(_check("acquisition_completeness", "pass", {"asserted_by_caller": True}))
                status = "COMPLETE"

    return {
        "status": status,
        "checks": checks,
        "reasons": reasons,
        **evidence,
        "support_level": SUPPORT_LEVEL,
        "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
    }


def parse_response(
    raw: bytes,
    *,
    context: dict[str, Any] | None = None,
    response_type: str = "auto",
) -> dict[str, Any]:
    """Parse one saved line response and return data plus integrity evidence."""

    try:
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type=response_type)
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload, context)
        artifact["integrity"] = validate(artifact, raw=raw, frame=frame)
        return artifact
    except ParserError as exc:
        return _failure(raw, exc.status, str(exc), context)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path, help="path to a saved raw response")
    parser.add_argument("--function", help="function from a separately captured :FUNCtion? query")
    parser.add_argument("--unit", help="unit supplied by the response or configuration record")
    parser.add_argument("--query", help="query command that produced this response")
    parser.add_argument(
        "--response-type",
        choices=("auto", "measurement", "error-queue"),
        default="auto",
        help="classify the saved line as a scalar, error-queue record, or automatically",
    )
    parser.add_argument(
        "--acquisition-complete",
        action="store_true",
        help="assert that the caller has independent evidence of a complete acquisition",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        raw = args.response.read_bytes()
    except OSError as exc:
        print(f"cannot read response: {exc}", file=sys.stderr)
        return 2

    context: dict[str, Any] = {}
    for key in ("function", "unit", "query"):
        value = getattr(args, key)
        if value is not None:
            context[key] = value
    if args.acquisition_complete:
        context["acquisition_complete"] = True

    artifact = parse_response(raw, context=context, response_type=args.response_type)
    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
