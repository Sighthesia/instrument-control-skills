#!/usr/bin/env python3
"""Parse Model 2000 responses that are not a single scalar reading.

Transport-independent: this module never opens a serial port or sends a
command. It complements ``keithley2000_scalar.py`` by covering the three
responses a real session also needs:

* ``*IDN?`` identity (vendor, model, serial, digital/display firmware);
* configuration readbacks such as ``"VOLT:DC"``, ``1010.000000``, ``1``, or
  ``READ,,``;
* a whole ``:SYSTem:ERRor?`` drain, one code/message record per line.

It also derives the convenience facts the scalar parser deliberately refuses
to guess: the default unit and sense path for a function token, and an
assessment that ties a reading to the error queue (``-213,"Init ignored"``
means the number came from continuous acquisition, and a zero
frequency/period on an open input is no-signal, not a measurement).

Every artifact keeps its raw bytes, SHA-256, and a conservative status.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keithley2000_scalar import ERROR_QUEUE_RE, Frame, ParserError, read_frame  # noqa: E402

PARSER_NAME = "keithley2000-protocol"
PARSER_VERSION = "0.1.0"
SUPPORT_LEVEL = "documented"
MAX_RESPONSE_BYTES = 65_536

# Identity captured during the 2026-10-20 hardware verification. Matching values
# only mean "same instrument as the recorded capture", not "calibrated".
VERIFIED_IDENTITY = {"serial": "0944865", "firmware": "A17  /A02"}

LINE_BREAK_RE = re.compile(rb"\r\n|\n\r|\r|\n")
QUOTED_RE = re.compile(r'^"(?P<text>[^"]*)"$')
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")

# Function token -> (sense path, default unit). Units are the documented
# response units; temperature needs an explicit unit because it depends on
# :SENSe:TEMPerature:UNIT.
FUNCTIONS: dict[str, tuple[str, str | None]] = {
    "VOLT:DC": ("VOLTage:DC", "VDC"),
    "VOLT:AC": ("VOLTage:AC", "VAC"),
    "CURR:DC": ("CURRent:DC", "ADC"),
    "CURR:AC": ("CURRent:AC", "AAC"),
    "RES": ("RESistance", "OHM"),
    "FRES": ("FRESistance", "OHM4W"),
    "FREQ": ("FREQuency", "HZ"),
    "PER": ("PERiod", "S"),
    "CONT": ("CONTinuity", "OHM"),
    "DIOD": ("DIODe", "VDC"),
    "TEMP": ("TEMPerature", None),
}

FUNCTION_ALIASES = {
    "VOLTAGE:DC": "VOLT:DC",
    "VOLTAGE": "VOLT:DC",
    "VOLT": "VOLT:DC",
    "VOLTAGE:AC": "VOLT:AC",
    "CURRENT:DC": "CURR:DC",
    "CURRENT": "CURR:DC",
    "CURR": "CURR:DC",
    "CURRENT:AC": "CURR:AC",
    "RESISTANCE": "RES",
    "FRESISTANCE": "FRES",
    "FREQUENCY": "FREQ",
    "PERIOD": "PER",
    "CONTINUITY": "CONT",
    "DIODE": "DIOD",
    "TEMPERATURE": "TEMP",
}


class ProtocolError(ValueError):
    """A non-reading response that cannot be parsed as claimed."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


def _evidence(raw: bytes) -> dict[str, str]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
    }


def _check(name: str, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _envelope(kind: str, status: str, reason: str, raw: bytes) -> dict[str, Any]:
    return {
        "schema_version": "keithley2000-protocol-v1",
        "kind": kind,
        "integrity": {
            "status": status,
            "checks": [_check("response_parse", "fail", {"reason": reason})],
            "reasons": [reason],
            **_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def _single_line(raw: bytes) -> Frame:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProtocolError("response exceeds the protocol parser size limit", "UNSUPPORTED")
    frame = read_frame(raw)
    if frame.trailing:
        raise ProtocolError("extra bytes follow the first response line", "INVALID")
    return frame


def normalize_function(function: str | None) -> str | None:
    """Map a function token or command to the documented short form."""

    if not function:
        return None
    token = function.strip().strip("'\"").upper().replace(" ", "")
    token = re.sub(r"^:?(?:SENSE(?:\[1\])?:)?", "", token)
    if token in FUNCTIONS:
        return token
    if token in FUNCTION_ALIASES:
        return FUNCTION_ALIASES[token]
    for suffix in (":DC", ":AC"):
        if token.endswith(suffix) and token[:-3] in FUNCTION_ALIASES:
            return FUNCTION_ALIASES[token[:-3]] + suffix
    return None


def sense_path(function: str | None) -> str | None:
    """Return the ``:SENSe:`` path for a function token, or ``None``."""

    token = normalize_function(function)
    return FUNCTIONS[token][0] if token else None


def default_unit(function: str | None) -> str | None:
    """Return the documented response unit implied by the function token."""

    token = normalize_function(function)
    return FUNCTIONS[token][1] if token else None


def parse_identity(raw: bytes) -> dict[str, Any]:
    """Parse ``*IDN?`` into vendor/model/serial/firmware fields."""

    try:
        frame = _single_line(raw)
        text = frame.content.decode("ascii").strip()
    except (ProtocolError, ParserError) as exc:
        return _envelope("identity", getattr(exc, "status", "INVALID"), str(exc), raw)

    if not text:
        return _envelope("identity", "INCOMPLETE", "identity response is empty", raw)

    fields = [field.strip() for field in text.split(",")]
    reasons: list[str] = []
    checks = [_check("line_terminator", "pass", {"terminator_hex": frame.terminator.hex()})]

    if len(fields) < 4:
        checks.append(_check("identity_fields", "fail", {"count": len(fields)}))
        reasons.append("identity_field_count")
        status = "INCOMPLETE"
        vendor, model, serial, firmware_raw = (fields + [""] * 4)[:4]
    else:
        vendor, model, serial = fields[0], fields[1], fields[2]
        firmware_raw = ",".join(fields[3:])
        checks.append(_check("identity_fields", "pass", {"count": len(fields)}))
        missing = [name for name, value in (("vendor", vendor), ("model", model),
                                            ("serial", serial), ("firmware", firmware_raw)) if not value]
        if missing:
            checks.append(_check("identity_values", "fail", {"missing": missing}))
            reasons.extend(f"identity_missing_{name}" for name in missing)
            status = "INCOMPLETE"
        else:
            status = "COMPLETE"

    digital, _, display = firmware_raw.partition("/")
    artifact = {
        "schema_version": "keithley2000-protocol-v1",
        "kind": "identity",
        "identity": {
            "vendor": vendor,
            "model": model,
            "serial": serial,
            "firmware_raw": firmware_raw,
            "firmware_digital": digital.strip() or None,
            "firmware_display": display.strip() or None,
            "raw_line": text,
        },
        "verified_scope": {
            "recorded_serial": VERIFIED_IDENTITY["serial"],
            "recorded_firmware": VERIFIED_IDENTITY["firmware"],
            "matches_recorded_capture": (
                serial == VERIFIED_IDENTITY["serial"]
                and firmware_raw == VERIFIED_IDENTITY["firmware"]
            ),
        },
        "integrity": {
            "status": status,
            "checks": checks,
            "reasons": reasons,
            **_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }
    return artifact


def parse_config(raw: bytes, query: str | None = None) -> dict[str, Any]:
    """Parse one configuration readback without assuming its type."""

    try:
        frame = _single_line(raw)
        text = frame.content.decode("ascii").strip()
    except (ProtocolError, ParserError) as exc:
        return _envelope("configuration", getattr(exc, "status", "INVALID"), str(exc), raw)
    except UnicodeDecodeError:
        return _envelope("configuration", "INVALID", "response contains non-ASCII bytes", raw)

    if not text:
        return _envelope("configuration", "INCOMPLETE", "configuration response is empty", raw)

    quoted = QUOTED_RE.fullmatch(text)
    number = NUMBER_RE.fullmatch(text)
    value: Any = None
    kind = "token"
    checks = [_check("line_terminator", "pass", {"terminator_hex": frame.terminator.hex()})]

    if quoted:
        kind = "string"
        value = quoted.group("text")
        checks.append(_check("value_type", "pass", {"type": "quoted-string"}))
    elif number:
        kind = "number"
        value = float(text)
        checks.append(_check("value_type", "pass", {"type": "number"}))
    elif text in {"READ", "READ,", "READ,,"} or text.startswith("READ,"):
        kind = "elements"
        value = [element.strip() for element in text.split(",")]
        checks.append(_check("value_type", "pass", {"type": "format-elements"}))
    else:
        checks.append(_check("value_type", "pass", {"type": "token"}))

    artifact = {
        "schema_version": "keithley2000-protocol-v1",
        "kind": "configuration",
        "configuration": {
            "query": query,
            "raw_line": text,
            "value_type": kind,
            "value": value if value is not None else text,
            "flag": (text in {"0", "1"}) if text in {"0", "1"} else None,
            "function": normalize_function(value) if kind == "string" else None,
        },
        "integrity": {
            "status": "COMPLETE",
            "checks": checks,
            "reasons": [],
            **_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }
    return artifact


def split_lines(raw: bytes) -> list[tuple[bytes, bytes]]:
    """Split a multi-line response into ``(content, terminator)`` pairs."""

    lines: list[tuple[bytes, bytes]] = []
    position = 0
    while position < len(raw):
        match = LINE_BREAK_RE.search(raw, position)
        if match is None:
            lines.append((raw[position:], b""))
            break
        lines.append((raw[position:match.start()], raw[match.start():match.end()]))
        position = match.end()
    return lines


def parse_error_queue(raw: bytes) -> dict[str, Any]:
    """Parse a whole ``:SYSTem:ERRor?`` drain, preserving order and bytes."""

    if not raw:
        return _envelope("error-queue", "INCOMPLETE", "error-queue response is empty", raw)
    if len(raw) > MAX_RESPONSE_BYTES:
        return _envelope("error-queue", "UNSUPPORTED", "response exceeds size limit", raw)

    records: list[dict[str, Any]] = []
    reasons: list[str] = []
    checks: list[dict[str, Any]] = [_check("line_count", "pass",
                                           {"count": len([line for line in split_lines(raw) if line[0]])})]

    for content, terminator in split_lines(raw):
        if not content:
            continue
        try:
            text = content.decode("ascii").strip()
        except UnicodeDecodeError:
            reasons.append("non_ascii_error_line")
            continue
        match = ERROR_QUEUE_RE.fullmatch(text)
        if match is None:
            reasons.append("unparsed_error_line")
            records.append({"code": None, "message": text, "raw_line": text,
                            "line_sha256": hashlib.sha256(content + terminator).hexdigest()})
            continue
        if not terminator:
            reasons.append("unterminated_error_line")
        records.append({
            "code": int(match.group("code")),
            "message": match.group("message").strip(),
            "raw_line": text,
            "line_sha256": hashlib.sha256(content + terminator).hexdigest(),
        })

    if not records:
        return _envelope("error-queue", "INCOMPLETE", "error-queue response has no records", raw)

    codes = [record["code"] for record in records]
    normalized_messages = [
        str(record["message"]).strip().strip("\"'").strip().casefold() for record in records
    ]
    queue_overflow = any(
        code is not None and abs(code) == 350 and message == "queue overflow"
        for code, message in zip(codes, normalized_messages)
    )
    ends_empty = codes[-1] == 0 and normalized_messages[-1] == "no error"

    if "unparsed_error_line" in reasons or "non_ascii_error_line" in reasons:
        status = "INVALID"
    elif queue_overflow or not ends_empty or "unterminated_error_line" in reasons:
        status = "INCOMPLETE"
        if not ends_empty and not queue_overflow:
            reasons.append("error_queue_not_drained")
        if queue_overflow:
            reasons.append("instrument_error_queue_overflow")
    else:
        status = "COMPLETE"

    errors = [
        record for record, message in zip(records, normalized_messages)
        if record["code"] not in (0, None) and message != "queue overflow"
    ]
    if errors:
        checks.append(_check("error_entries", "fail", {"count": len(errors)}))
    else:
        checks.append(_check("error_entries", "pass", {"count": 0}))
    checks.append(_check("drained", "pass" if ends_empty else "fail",
                         {"last_code": codes[-1]}))

    return {
        "schema_version": "keithley2000-protocol-v1",
        "kind": "error-queue",
        "records": records,
        "errors": errors,
        "drained": ends_empty,
        "queue_overflow": queue_overflow,
        "integrity": {
            "status": status,
            "checks": checks,
            "reasons": reasons,
            **_evidence(raw),
            "support_level": SUPPORT_LEVEL,
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def assess_reading(
    reading: dict[str, Any],
    queue: dict[str, Any] | None = None,
    function: str | None = None,
) -> dict[str, Any]:
    """Tie a parsed reading to the error queue and function semantics."""

    token = normalize_function(function or (
        reading.get("measurement", {}).get("function") if reading.get("kind") == "scalar-measurement" else None
    ))
    flags: set[str] = set()
    notes: list[str] = []
    measurement = reading.get("measurement") or {}
    status = measurement.get("reading_status")
    value = measurement.get("value")

    if status == "OVERFLOW":
        flags.add("overflow")
        notes.append("instrument reported the overflow sentinel; not a finite value")
    elif status == "VALID" and value == 0 and token in {"FREQ", "PER"}:
        flags.add("no_signal_suspected")
        notes.append("0 Hz/period is returned for no signal; confirm the input amplitude")

    queue_errors = queue.get("errors", []) if queue else []
    for record in queue_errors:
        message = str(record.get("message", "")).strip().strip("\"'").casefold()
        if record.get("code") == -213:
            flags.add("init_ignored")
            notes.append(
                "-213 means :INITiate was ignored; the reading came from continuous "
                "acquisition, not from a newly triggered one"
            )
        elif record.get("code") is not None:
            flags.add("queue_error")
            notes.append(f"error queue holds {record['code']}: {message}")

    if "init_ignored" in flags:
        freshness = "not_newly_triggered"
    elif reading.get("integrity", {}).get("status") == "COMPLETE":
        freshness = "one_shot_complete"
    else:
        freshness = "unknown"

    return {
        "function": token,
        "flags": sorted(flags),
        "freshness": freshness,
        "queue_errors": queue_errors,
        "notes": notes,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("identity", "config", "queue"))
    parser.add_argument("response", type=Path, help="path to saved raw response bytes")
    parser.add_argument("--query", help="query command that produced a configuration response")
    parser.add_argument("--function", help="function used to assess a reading")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        raw = args.response.read_bytes()
    except OSError as exc:
        print(f"cannot read response: {exc}", file=sys.stderr)
        return 2

    if args.kind == "identity":
        artifact = parse_identity(raw)
    elif args.kind == "config":
        artifact = parse_config(raw, query=args.query)
    else:
        artifact = parse_error_queue(raw)
    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
