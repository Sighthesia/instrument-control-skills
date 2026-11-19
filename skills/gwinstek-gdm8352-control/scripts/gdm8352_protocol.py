#!/usr/bin/env python3
"""Offline protocol helpers for the GW Instek GDM-8352 digital multimeter.

This module is transport-independent: it never opens a serial port and never
sends a command.  It frames saved responses, preserves the IEEE 488.2 numeric
text verbatim (``+0.10466E-01`` is kept as text, not round-tripped through
``float``), exposes a :class:`~decimal.Decimal` value, resolves the unit from
the measurement command, separates the two ``READ?`` displays, decodes the
three beeper states, and recognises free-text system errors.

Manual citation: *GDM-8352 User Manual*, GW Instek part no. 82DM-83520E01.
Page numbers below are the printed page numbers; the PDF physical page is one
higher (printed p. 117 = PDF p. 116).  The command reference spans printed
pp. 107-139.

Safety: this Skill ships no state-changing command builder.  :func:`build_query`
can only produce the read-only queries in :data:`QUERY_SPECS`; every setter
(``CONF:VOLT:DC 1``, ``SYST:BEEP:STAT 0``, ``*RST``, ``*CLS``, calibration and
display commands) is rejected before a byte could reach a port.

The framing, staged normalization, and artifact shape follow this repository's
``skills/gwinstek-gpd4303s-control/scripts/gpd4303s_protocol.py`` (same
project, https://github.com/Sighthesia/instrument-control-skills); the command
table, units, and response parsers here are specific to the GDM-8352.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Sequence

PARSER_NAME = "gdm8352-protocol"
PARSER_VERSION = "0.1.0"
SCHEMA_VERSION = "gdm8352-protocol-v1"

# The captured USB CDC session ended every response with CR LF.
COMMAND_TERMINATOR = b"\r\n"

MAX_RESPONSE_BYTES = 65_536

# The five integrity states used by every artifact in this Skill.
COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"
INVALID = "INVALID"
UNVERIFIED = "UNVERIFIED"
UNSUPPORTED = "UNSUPPORTED"
INTEGRITY_STATUSES = (COMPLETE, INCOMPLETE, INVALID, UNVERIFIED, UNSUPPORTED)

# Manual p. 93 (RS232 settings).  The verified USB CDC interface ignores the
# host baud rate entirely, but the setting must still be one the instrument
# documents.
DOCUMENTED_BAUD_RATES = (9600, 19200, 38400, 57600, 115200)
DEFAULT_BAUD = 115200


class ProtocolError(ValueError):
    """A framing, parsing, or validation failure with an integrity status."""

    def __init__(self, message: str, status: str = INVALID) -> None:
        if status not in INTEGRITY_STATUSES:
            raise ValueError(f"unknown integrity status {status!r}")
        super().__init__(message)
        self.status = status


class CommandRefused(ValueError):
    """A command is not a documented, read-only GDM-8352 query."""


# ---------------------------------------------------------------------------
# Measurement functions and their units
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementFunction:
    """One first-display measurement query and the unit it reports.

    ``unit_status`` is ``DOCUMENTED`` when the manual's command example states
    the unit, and ``AMBIGUOUS`` when the unit is selectable or absent from the
    response.  ``format_status`` is ``UNVERIFIED`` when the command reference
    has no example response, so the token layout itself is not evidenced.
    """

    key: str
    query: str
    long_query: str
    quantity: str
    unit: str
    manual_page: int
    example_response: str | None
    unit_status: str = COMPLETE
    format_status: str = COMPLETE
    unit_candidates: tuple[str, ...] = ()
    note: str = ""


MEASUREMENT_FUNCTIONS: Dict[str, MeasurementFunction] = {
    "dc-voltage": MeasurementFunction(
        key="dc-voltage",
        query="MEAS:VOLT:DC?",
        long_query="MEASure:VOLTage:DC?",
        quantity="voltage",
        unit="V",
        manual_page=117,
        example_response="+0.10348E-01",
    ),
    "ac-voltage": MeasurementFunction(
        key="ac-voltage",
        query="MEAS:VOLT:AC?",
        long_query="MEASure:VOLTage:AC?",
        quantity="voltage",
        unit="V",
        manual_page=117,
        example_response="+0.09020E-01",
    ),
    "dcac-voltage": MeasurementFunction(
        key="dcac-voltage",
        query="MEAS:VOLT:DCAC?",
        long_query="MEASure:VOLTage:DCAC?",
        quantity="voltage",
        unit="V",
        manual_page=117,
        example_response="+0.10123E-01",
    ),
    "dc-current": MeasurementFunction(
        key="dc-current",
        query="MEAS:CURR:DC?",
        long_query="MEASure:CURRent:DC?",
        quantity="current",
        unit="A",
        manual_page=117,
        example_response="+0.00703E-02",
    ),
    "ac-current": MeasurementFunction(
        key="ac-current",
        query="MEAS:CURR:AC?",
        long_query="MEASure:CURRent:AC?",
        quantity="current",
        unit="A",
        manual_page=118,
        example_response="+0.00872E-02",
    ),
    "dcac-current": MeasurementFunction(
        key="dcac-current",
        query="MEAS:CURR:DCAC?",
        long_query="MEASure:CURRent:DCAC?",
        quantity="current",
        unit="A",
        manual_page=118,
        example_response="+0.01245E-02",
    ),
    "resistance-2w": MeasurementFunction(
        key="resistance-2w",
        query="MEAS:RES?",
        long_query="MEASure:RESistance?",
        quantity="resistance",
        unit="Ω",
        manual_page=118,
        example_response="+1.00156E+03",
    ),
    "resistance-4w": MeasurementFunction(
        key="resistance-4w",
        query="MEAS:FRES?",
        long_query="MEASure:FRESistance?",
        quantity="resistance",
        unit="Ω",
        manual_page=118,
        example_response="+1.11365E+03",
    ),
    "frequency": MeasurementFunction(
        key="frequency",
        query="MEAS:FREQ?",
        long_query="MEASure:FREQuency?",
        quantity="frequency",
        unit="Hz",
        manual_page=119,
        example_response="+1.00123E+03",
    ),
    "period": MeasurementFunction(
        key="period",
        query="MEAS:PER?",
        long_query="MEASure:PERiod?",
        quantity="period",
        unit="s",
        manual_page=119,
        example_response=None,
        format_status=UNVERIFIED,
        note="the command reference gives no example response for period",
    ),
    "continuity": MeasurementFunction(
        key="continuity",
        query="MEAS:CONT?",
        long_query="MEASure:CONTinuity?",
        quantity="continuity",
        unit="Ω",
        manual_page=119,
        example_response=None,
        format_status=UNVERIFIED,
        note=(
            "the command reference only says 'Returns the continuity'; it does not "
            "state whether the token is a resistance or a pass/fail code"
        ),
    ),
    "diode": MeasurementFunction(
        key="diode",
        query="MEAS:DIOD?",
        long_query="MEASure:DIODe?",
        quantity="diode_voltage",
        unit="V",
        manual_page=119,
        example_response=None,
        format_status=UNVERIFIED,
        note="the command reference gives no example response for the diode test",
    ),
    "capacitance": MeasurementFunction(
        key="capacitance",
        query="MEAS:CAP?",
        long_query="MEASure:CAPacitance?",
        quantity="capacitance",
        unit="F",
        manual_page=119,
        example_response=None,
        format_status=UNVERIFIED,
        note="the command reference gives no example response for capacitance",
    ),
    "temperature": MeasurementFunction(
        key="temperature",
        query="MEAS:TEMP:TCO?",
        long_query="MEASure:TEMPerature:TCOuple?",
        quantity="temperature",
        unit="°C",
        manual_page=120,
        example_response="+0.02667E+03",
        unit_status=UNVERIFIED,
        unit_candidates=("°C", "°F"),
        note=(
            "manual p. 52 selects °C or °F in the front-panel unit menu; the "
            "response carries no unit and the command reference example does not "
            "state which unit the unit was set to"
        ),
    ),
}


def measurement_function_for_query(query: str) -> MeasurementFunction | None:
    """Return the first-display measurement function for a canonical query."""

    for function in MEASUREMENT_FUNCTIONS.values():
        if function.query == query:
            return function
    return None


# ---------------------------------------------------------------------------
# Read-only query table and command construction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuerySpec:
    canonical: str
    kind: str
    function_key: str | None = None


QUERY_SPECS: Dict[str, QuerySpec] = {
    "*IDN?": QuerySpec("*IDN?", "identity"),
    "READ?": QuerySpec("READ?", "read"),
    "SYST:BEEP:STAT?": QuerySpec("SYST:BEEP:STAT?", "beep-state"),
    "SYST:ERR?": QuerySpec("SYST:ERR?", "system-error"),
    "CONF:FUNC?": QuerySpec("CONF:FUNC?", "function-setting"),
    "CONF:RANG?": QuerySpec("CONF:RANG?", "range-setting"),
    "CONF:AUTO?": QuerySpec("CONF:AUTO?", "auto-range"),
    "SENS:UNIT?": QuerySpec("SENS:UNIT?", "temperature-unit"),
}
for _function in MEASUREMENT_FUNCTIONS.values():
    QUERY_SPECS[_function.query] = QuerySpec(
        _function.query, "measurement", function_key=_function.key
    )

ALLOWED_QUERIES = frozenset(QUERY_SPECS)

# Long forms from the manual's command reference, plus the two accepted spellings
# of the temperature-unit query (manual p. 125: "SENSe:UNIT? and UNIT? are both
# valid forms").
_QUERY_ALIASES: Dict[str, str] = {query.upper(): query for query in QUERY_SPECS}
for _function in MEASUREMENT_FUNCTIONS.values():
    _QUERY_ALIASES[_function.long_query.upper()] = _function.query
_QUERY_ALIASES.update(
    {
        "SYSTEM:BEEPER:STATE?": "SYST:BEEP:STAT?",
        "SYSTEM:ERROR?": "SYST:ERR?",
        "CONFIGURE:FUNCTION?": "CONF:FUNC?",
        "CONFIGURE:RANGE?": "CONF:RANG?",
        "CONFIGURE:AUTO?": "CONF:AUTO?",
        "SENSE:UNIT?": "SENS:UNIT?",
        "UNIT?": "SENS:UNIT?",
    }
)

_TEMPERATURE_TYPES = frozenset({"J", "K", "T"})
_FORBIDDEN_TEXT = ("\r", "\n", "\x00", ";", "|", "&")
_MAX_QUERY_CHARS = 64


def resolve_query(text: str) -> tuple[QuerySpec, str | None]:
    """Validate a read-only query and return its canonical form and parameter.

    Only the documented temperature-type parameter is accepted.  Range
    arguments are deliberately refused: they would make one interaction both a
    configuration change and a measurement.
    """

    if not isinstance(text, str):
        raise CommandRefused("command must be a string")
    if any(token in text for token in _FORBIDDEN_TEXT):
        raise CommandRefused("command contains a control character or command separator")
    command = text.strip()
    if not command:
        raise CommandRefused("command is empty")
    if len(command) > _MAX_QUERY_CHARS:
        raise CommandRefused(f"command exceeds {_MAX_QUERY_CHARS} characters")

    parts = command.split()
    if len(parts) > 2:
        raise CommandRefused(f"refusing {command!r}: at most one parameter is accepted")
    head = parts[0].upper()
    parameter = parts[1].upper() if len(parts) == 2 else None

    canonical = _QUERY_ALIASES.get(head)
    if canonical is None:
        raise CommandRefused(
            f"refusing {text!r}: not a documented read-only GDM-8352 query"
        )
    if canonical == "MEAS:TEMP:TCO?":
        if parameter is not None and parameter not in _TEMPERATURE_TYPES:
            raise CommandRefused(
                f"refusing {text!r}: thermocouple type must be one of J, K, T"
            )
    elif parameter is not None:
        raise CommandRefused(
            f"refusing {text!r}: only MEAS:TEMP:TCO? accepts a parameter"
        )
    return QUERY_SPECS[canonical], parameter


def build_query(text: str) -> bytes:
    """Build the exact ASCII bytes for one allowed query, including CR LF."""

    spec, parameter = resolve_query(text)
    body = spec.canonical if parameter is None else f"{spec.canonical} {parameter}"
    return body.encode("ascii") + COMMAND_TERMINATOR


# ---------------------------------------------------------------------------
# Framing and common metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    content: bytes
    terminator: bytes
    trailing: bytes
    raw: bytes


def _raw_evidence(raw: bytes) -> dict[str, Any]:
    return {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_base64": base64.b64encode(raw).decode("ascii"),
        "raw_bytes": len(raw),
    }


def _check_response_size(raw: bytes) -> bytes:
    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("response must be bytes", INVALID)
    raw = bytes(raw)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProtocolError("response exceeds the protocol size limit", UNSUPPORTED)
    if not raw:
        raise ProtocolError("response is empty", INCOMPLETE)
    return raw


def read_frame(raw: bytes) -> Frame:
    """Read exactly one terminated line and reject any trailing bytes."""

    raw = _check_response_size(raw)
    positions = [position for delimiter in (b"\r", b"\n") if (position := raw.find(delimiter)) >= 0]
    if not positions:
        raise ProtocolError("response has no line terminator", INCOMPLETE)

    start = min(positions)
    first = raw[start : start + 1]
    following = raw[start + 1 : start + 2]
    if first == b"\r" and following == b"\n":
        terminator = b"\r\n"
    elif first == b"\n" and following == b"\r":
        terminator = b"\n\r"
    else:
        terminator = first

    trailing = raw[start + len(terminator) :]
    if trailing:
        raise ProtocolError("extra bytes follow the first response line", INVALID)
    return Frame(content=raw[:start], terminator=terminator, trailing=trailing, raw=raw)


def _text(frame: Frame) -> str:
    try:
        return frame.content.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("response contains non-ASCII bytes", INVALID) from exc


def parse_metadata(frame: Frame, *, response_type: str) -> dict[str, Any]:
    text = _text(frame)
    return {
        "response_type": response_type,
        "text": text,
        "terminator": frame.terminator,
        "raw": frame.raw,
        "raw_sha256": hashlib.sha256(frame.raw).hexdigest(),
        "raw_response_base64": base64.b64encode(frame.raw).decode("ascii"),
    }


def extract_payload(metadata: Mapping[str, Any]) -> dict[str, Any]:
    text = metadata["text"]
    return {
        "raw_text": text,
        "text": text,
        "fields": text.split(","),
        "stripped": text.strip(),
    }


def _artifact(
    kind: str,
    command: str,
    raw: bytes,
    *,
    status: str,
    checks: Sequence[Mapping[str, Any]],
    reasons: Sequence[str] = (),
    **fields: Any,
) -> dict[str, Any]:
    if status not in INTEGRITY_STATUSES:
        raise ValueError(f"unknown integrity status {status!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "command": command,
        **fields,
        "status": status,
        "integrity": {
            "status": status,
            "checks": list(checks),
            "reasons": list(reasons),
            **_raw_evidence(bytes(raw)),
            "parser": f"{PARSER_NAME}/{PARSER_VERSION}",
        },
    }


def artifact_decimal(artifact: Mapping[str, Any]) -> Decimal | None:
    """Return the exact Decimal carried by a scalar/range artifact.

    Artifacts keep ``value_decimal`` as a string so they remain JSON-safe; this
    helper is the explicit Decimal accessor for callers that need arithmetic.
    """

    value = artifact.get("value_decimal")
    if value is None:
        return None
    return Decimal(str(value))


def response_failure(command: str, status: str, reason: str) -> dict[str, Any]:
    """Build an empty-response artifact for a transport timeout."""

    try:
        resolved_kind = resolve_query(command)[0].kind
    except CommandRefused:
        resolved_kind = "unparsed-query"
    kind = {
        "measurement": "scalar-value",
        "read": "two-display-reading",
    }.get(resolved_kind, resolved_kind)
    return _artifact(
        kind,
        command,
        b"",
        status=status,
        checks=[{"name": "response_received", "status": "fail", "evidence": {"reason": reason}}],
        reasons=[reason],
        raw_text=None,
        value_decimal=None,
        unit=None,
    )


# ---------------------------------------------------------------------------
# Numeric normalization
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(
    r"^(?P<number>[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[Ee][+-]?\d+)?)"
    r"(?P<unit>[A-Za-z]+)?$"
)

_UNIT_ALIASES = {
    "V": "V",
    "VOLT": "V",
    "VOLTS": "V",
    "A": "A",
    "AMP": "A",
    "AMPS": "A",
    "OHM": "Ω",
    "OHMS": "Ω",
    "HZ": "Hz",
    "F": "F",
    "FARAD": "F",
    "S": "s",
    "SEC": "s",
    "C": "°C",
}


def parse_ieee4882_numeric(token: str) -> dict[str, Any]:
    """Parse one IEEE 488.2 numeric token without a float round trip."""

    if not isinstance(token, str) or token == "":
        raise ProtocolError("numeric token is empty", INCOMPLETE)
    match = _NUMERIC_RE.fullmatch(token)
    if match is None:
        raise ProtocolError(f"non-numeric response token {token!r}", INVALID)

    number_text = match.group("number")
    suffix = match.group("unit")
    if suffix is not None and suffix.upper() in {"E", "D"}:
        raise ProtocolError(f"malformed exponent in {token!r}", INVALID)
    try:
        value = Decimal(number_text)
    except InvalidOperation as exc:  # pragma: no cover - regex already constrains this
        raise ProtocolError(f"invalid decimal token {number_text!r}", INVALID) from exc
    if not value.is_finite():
        raise ProtocolError("non-finite numeric response", INVALID)

    mantissa, _, exponent_text = number_text.upper().partition("E")
    fraction = mantissa.partition(".")[2]
    return {
        "value": value,
        "value_decimal": str(value),
        "numeric_token": number_text,
        "raw_unit_suffix": suffix,
        "fraction_digits": len(fraction),
        "exponent": int(exponent_text) if exponent_text else 0,
    }


def _resolve_unit(
    payload: Mapping[str, Any], function: MeasurementFunction
) -> tuple[str, str, list[str]]:
    """Return (unit, unit_source, reasons) or raise on a conflicting suffix."""

    suffix = payload["raw_unit_suffix"]
    format_reasons = (
        [f"{function.key}_response_format_not_documented"]
        if function.format_status != COMPLETE
        else []
    )
    if suffix is not None:
        suffix_upper = suffix.upper()
        if function.key == "temperature":
            # The temperature unit is selectable (°C or °F); F here is
            # Fahrenheit, not Farad, so it needs a function-scoped mapping.
            resolved = {"C": "°C", "F": "°F"}.get(suffix_upper)
        else:
            resolved = _UNIT_ALIASES.get(suffix_upper)
        if resolved is None or (
            function.key != "temperature" and resolved != function.unit
        ):
            raise ProtocolError(
                f"response unit {suffix!r} conflicts with {function.key} ({function.unit})",
                INVALID,
            )
        return resolved, "response-suffix", format_reasons

    reasons = list(format_reasons)
    if function.unit_status != COMPLETE:
        reasons.insert(0, f"{function.key}_unit_not_conveyed_by_response")
    return function.unit, "measurement-command", reasons


# ---------------------------------------------------------------------------
# Stage parsers: identity, measurement, READ?, beeper, error, settings
# ---------------------------------------------------------------------------


def _frame_and_payload(raw: bytes, *, response_type: str) -> tuple[Frame, dict[str, Any], dict[str, Any]]:
    frame = read_frame(raw)
    if not frame.content:
        raise ProtocolError("response line is empty", INCOMPLETE)
    metadata = parse_metadata(frame, response_type=response_type)
    return frame, metadata, extract_payload(metadata)


def parse_identity(raw: bytes) -> dict[str, Any]:
    """Parse a saved ``*IDN?`` response into four comma-separated fields."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="identity")
    except ProtocolError as exc:
        return _failure("identity", "*IDN?", raw, exc.status, str(exc))

    fields = payload["fields"]
    if len(fields) < 4:
        return _failure(
            "identity",
            "*IDN?",
            raw,
            INCOMPLETE,
            f"identity has {len(fields)} field(s); the observed response has 4 "
            "(vendor, model, serial, firmware)",
        )
    if len(fields) > 4:
        return _failure(
            "identity",
            "*IDN?",
            raw,
            INVALID,
            f"identity has {len(fields)} fields; expected 4",
        )
    vendor_raw, model_raw, serial, firmware = fields
    if not vendor_raw or not model_raw:
        return _failure("identity", "*IDN?", raw, INCOMPLETE, "vendor or model is empty")
    if not serial:
        return _failure("identity", "*IDN?", raw, INCOMPLETE, "serial number is empty")
    if not firmware:
        return _failure("identity", "*IDN?", raw, INCOMPLETE, "firmware version is empty")

    vendor_key = re.sub(r"[^A-Z]", "", vendor_raw.upper())
    model_key = model_raw.upper().replace("-", "")
    if vendor_key != "GWINSTEK":
        return _failure(
            "identity", "*IDN?", raw, INVALID, f"unexpected vendor {vendor_raw!r}"
        )
    if model_key != "GDM8352":
        return _failure(
            "identity", "*IDN?", raw, INVALID, f"unexpected model {model_raw!r}"
        )
    if re.fullmatch(r"\d+\.\d+", firmware) is None:
        return _failure(
            "identity",
            "*IDN?",
            raw,
            INVALID,
            f"malformed firmware version {firmware!r}; observed form is '1.00'",
        )

    return _artifact(
        "identity",
        "*IDN?",
        raw,
        status=COMPLETE,
        checks=[
            {
                "name": "identity_fields",
                "status": "pass",
                "evidence": {"vendor": vendor_raw, "model": model_raw, "firmware": firmware},
            }
        ],
        raw_text=payload["raw_text"],
        vendor="GW Instek",
        model="GDM-8352",
        serial=serial,
        firmware=firmware,
        vendor_raw=vendor_raw,
        model_raw=model_raw,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
    )


def parse_measurement(raw: bytes, spec: QuerySpec) -> dict[str, Any]:
    """Parse a saved first-display measurement response."""

    raw = bytes(raw)
    function = MEASUREMENT_FUNCTIONS.get(spec.function_key or "")
    kind = "scalar-value"
    if function is None:
        return _failure(
            kind,
            spec.canonical,
            raw,
            UNSUPPORTED,
            f"no measurement function is registered for {spec.canonical}",
        )
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="numeric")
    except ProtocolError as exc:
        return _failure(
            kind, spec.canonical, raw, exc.status, str(exc), function=function.key,
            quantity=function.quantity, unit=function.unit,
        )

    try:
        numeric = parse_ieee4882_numeric(payload["text"])
        unit, unit_source, reasons = _resolve_unit(numeric, function)
    except ProtocolError as exc:
        return _failure(
            kind, spec.canonical, raw, exc.status, str(exc), function=function.key,
            quantity=function.quantity, unit=function.unit,
            numeric_token=None, value_decimal=None, unit_source=None,
        )

    status = UNVERIFIED if reasons else COMPLETE
    checks = [
        {"name": "frame_terminator", "status": "pass", "evidence": {"terminator": metadata["terminator"].hex()}},
        {
            "name": "numeric_parse",
            "status": "pass",
            "evidence": {
                "raw_token": numeric["numeric_token"],
                "decimal": numeric["value_decimal"],
                "fraction_digits": numeric["fraction_digits"],
            },
        },
        {
            "name": "unit_resolution",
            "status": "warn" if reasons else "pass",
            "evidence": {"unit": unit, "source": unit_source, "quantity": function.quantity},
        },
    ]
    return _artifact(
        kind,
        spec.canonical,
        raw,
        status=status,
        checks=checks,
        reasons=reasons,
        function=function.key,
        quantity=function.quantity,
        display="first",
        raw_text=payload["raw_text"],
        numeric_token=numeric["numeric_token"],
        value_decimal=numeric["value_decimal"],
        value_type="Decimal",
        fraction_digits=numeric["fraction_digits"],
        exponent=numeric["exponent"],
        unit=unit,
        unit_source=unit_source,
        unit_candidates=list(function.unit_candidates),
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
        manual_page=function.manual_page,
        note=function.note,
    )


def parse_read(raw: bytes) -> dict[str, Any]:
    """Parse a saved ``READ?`` response into first/second display values.

    Manual p. 131: ``READ?`` "Returns 1st and 2nd display value" and its
    examples interleave the two displays.  The response carries neither the
    function nor the unit of either display, and the second display's function
    is not documented by this command, so both unit fields stay UNVERIFIED.
    """

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="read")
    except ProtocolError as exc:
        return _failure("two-display-reading", "READ?", raw, exc.status, str(exc))

    fields = payload["fields"]
    if any(field == "" for field in fields):
        return _failure(
            "two-display-reading", "READ?", raw, INCOMPLETE, "READ? has an empty field"
        )
    if len(fields) < 2:
        return _failure(
            "two-display-reading",
            "READ?",
            raw,
            INCOMPLETE,
            f"READ? has {len(fields)} field(s); the two-display response needs at least 2",
        )
    if len(fields) % 2:
        return _failure(
            "two-display-reading",
            "READ?",
            raw,
            INCOMPLETE,
            f"READ? has an odd field count ({len(fields)}); a second-display value is missing",
        )
    if len(fields) > 64:
        return _failure(
            "two-display-reading", "READ?", raw, UNSUPPORTED, "READ? has more than 64 fields"
        )

    samples: list[dict[str, Any]] = []
    for index in range(0, len(fields), 2):
        pair = {}
        for label, field in (("first", fields[index]), ("second", fields[index + 1])):
            try:
                numeric = parse_ieee4882_numeric(field)
            except ProtocolError as exc:
                return _failure(
                    "two-display-reading", "READ?", raw, exc.status,
                    f"display {1 if label == 'first' else 2} in sample "
                    f"{index // 2 + 1}: {exc}",
                    samples=samples, first_display=None, second_display=None,
                )
            pair[label] = {
                "display": 1 if label == "first" else 2,
                "sample": index // 2 + 1,
                "raw_text": field,
                "numeric_token": numeric["numeric_token"],
                "value_decimal": numeric["value_decimal"],
                "value_type": "Decimal",
                "semantics": "display value; READ? conveys no measurement function",
                "semantics_status": UNVERIFIED,
                "function": None,
                "function_status": UNVERIFIED,
                "unit": None,
                "unit_status": UNVERIFIED,
            }
        pair["second"]["role"] = "second display value (manual p. 131)"
        pair["second"]["role_status"] = COMPLETE
        pair["second"]["note"] = (
            "READ? does not state the second display's function or unit; the "
            "manual only says '2nd display value'"
        )
        samples.append(pair)

    reasons = [
        "read_display_functions_not_conveyed",
        "second_display_unit_not_conveyed",
    ]
    if len(samples) > 1:
        reasons.append("sample_count_not_queried")
    return _artifact(
        "two-display-reading",
        "READ?",
        raw,
        status=UNVERIFIED,
        checks=[
            {"name": "frame_terminator", "status": "pass", "evidence": {"terminator": metadata["terminator"].hex()}},
            {
                "name": "read_field_pairs",
                "status": "warn",
                "evidence": {"fields": len(fields), "samples": len(samples)},
            },
        ],
        reasons=reasons,
        raw_text=payload["raw_text"],
        samples=samples,
        sample_count=len(samples),
        first_display=samples[0]["first"] if len(samples) == 1 else None,
        second_display=samples[0]["second"] if len(samples) == 1 else None,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
        manual_page=131,
    )


BEEP_STATES = {
    "no beep": {"mode": "no-beep", "numeric_code": 0, "label": "No Beep"},
    "beep on pass": {"mode": "beep-on-pass", "numeric_code": 1, "label": "Beep on Pass"},
    "beep on fail": {"mode": "beep-on-fail", "numeric_code": 2, "label": "Beep on Fail"},
}


def parse_beep_state(raw: bytes) -> dict[str, Any]:
    """Parse ``SYST:BEEP:STAT?`` (manual p. 134)."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="beep-state")
    except ProtocolError as exc:
        return _failure("beep-state", "SYST:BEEP:STAT?", raw, exc.status, str(exc))

    normalized = " ".join(payload["stripped"].split()).casefold()
    state = BEEP_STATES.get(normalized)
    if state is None:
        return _failure(
            "beep-state",
            "SYST:BEEP:STAT?",
            raw,
            UNSUPPORTED,
            f"beeper response {payload['stripped']!r} is not one of the three documented "
            "texts: No Beep, Beep on Pass, Beep on Fail",
            raw_text=payload["raw_text"],
            mode=None,
            numeric_code=None,
        )
    return _artifact(
        "beep-state",
        "SYST:BEEP:STAT?",
        raw,
        status=COMPLETE,
        checks=[{"name": "beep_state_match", "status": "pass", "evidence": {"normalized": normalized}}],
        raw_text=payload["raw_text"],
        mode=state["mode"],
        numeric_code=state["numeric_code"],
        label=state["label"],
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
        manual_page=134,
    )


# Manual p. 134 documents only "Returns the current system error, if any."  The
# manual never enumerates the response strings, and the verified unit returned
# the free text "Command error", not a "<code>,<message>" queue entry.  The
# IEEE 488.2 strings below are recognised externally, not claimed as manual text.
KNOWN_ERROR_TEXTS = {
    "command error": {"category": "command", "source": "observed"},
    "execution error": {"category": "execution", "source": "ieee-488.2"},
    "device-specific error": {"category": "device", "source": "ieee-488.2"},
    "query error": {"category": "query", "source": "ieee-488.2"},
    "undefined header": {"category": "command", "source": "ieee-488.2"},
}


def parse_system_error(raw: bytes) -> dict[str, Any]:
    """Recognise the GDM-8352's free-text ``SYST:ERR?`` response."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="system-error")
    except ProtocolError as exc:
        return _failure("system-error", "SYST:ERR?", raw, exc.status, str(exc))

    text = payload["stripped"]
    normalized = " ".join(text.split()).casefold()
    note = (
        "manual p. 134 documents only 'Returns the current system error, if any'; "
        "it does not enumerate the text or define a numbered queue"
    )
    if re.fullmatch(r"\+?0(?:\.0+)?", normalized):
        return _artifact(
            "system-error",
            "SYST:ERR?",
            raw,
            status=UNVERIFIED,
            checks=[{"name": "error_text_match", "status": "warn", "evidence": {"text": text}}],
            reasons=["no_error_encoding_not_observed"],
            raw_text=payload["raw_text"],
            message=text,
            normalized=normalized,
            category="none",
            error_present=None,
            source="unverified-convention",
            manual_enumeration=False,
            note=note,
        )

    known = KNOWN_ERROR_TEXTS.get(normalized)
    if known is None:
        return _failure(
            "system-error",
            "SYST:ERR?",
            raw,
            UNSUPPORTED,
            f"system error text {text!r} is not a recognised free-text error",
            raw_text=payload["raw_text"],
            message=text,
            category=None,
            error_present=None,
        )

    return _artifact(
        "system-error",
        "SYST:ERR?",
        raw,
        status=COMPLETE,
        checks=[
            {
                "name": "error_text_match",
                "status": "pass",
                "evidence": {"normalized": normalized, "source": known["source"]},
            }
        ],
        raw_text=payload["raw_text"],
        message=text,
        normalized=normalized,
        category=known["category"],
        error_present=True,
        source=known["source"],
        manual_enumeration=False,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
        note=note,
    )


# Manual p. 111: CONF:FUNC? return tokens for the first display.
FUNCTION_TOKENS = {
    "VOLT": ("voltage", "dc-voltage"),
    "VOLT:AC": ("voltage", "ac-voltage"),
    "VOLT:DCAC": ("voltage", "dcac-voltage"),
    "CURR": ("current", "dc-current"),
    "CURR:AC": ("current", "ac-current"),
    "CURR:DCAC": ("current", "dcac-current"),
    "RES": ("resistance", "resistance-2w"),
    "FRES": ("resistance", "resistance-4w"),
    "FREQ": ("frequency", "frequency"),
    "PER": ("period", "period"),
    "TEMP": ("temperature", "temperature"),
    "DIOD": ("diode_voltage", "diode"),
    "CONT": ("continuity", "continuity"),
    "CAP": ("capacitance", "capacitance"),
}


def parse_function_setting(raw: bytes) -> dict[str, Any]:
    """Parse ``CONF:FUNC?`` (manual p. 111)."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="function-setting")
    except ProtocolError as exc:
        return _failure("function-setting", "CONF:FUNC?", raw, exc.status, str(exc))

    token = payload["stripped"].upper()
    known = FUNCTION_TOKENS.get(token)
    if known is None:
        return _failure(
            "function-setting",
            "CONF:FUNC?",
            raw,
            UNSUPPORTED,
            f"function token {payload['stripped']!r} is not in the manual's return list",
            raw_text=payload["raw_text"],
            function_token=None,
            quantity=None,
        )
    quantity, function_key = known
    return _artifact(
        "function-setting",
        "CONF:FUNC?",
        raw,
        status=COMPLETE,
        checks=[{"name": "function_token_match", "status": "pass", "evidence": {"token": token}}],
        raw_text=payload["raw_text"],
        function_token=token,
        quantity=quantity,
        function=function_key,
        display="first",
        manual_page=111,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
    )


def parse_auto_range(raw: bytes) -> dict[str, Any]:
    """Parse ``CONF:AUTO?`` (manual pp. 111-112)."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="auto-range")
    except ProtocolError as exc:
        return _failure("auto-range", "CONF:AUTO?", raw, exc.status, str(exc))

    token = payload["stripped"]
    if token not in {"0", "1"}:
        return _failure(
            "auto-range",
            "CONF:AUTO?",
            raw,
            INVALID,
            f"auto-range token {token!r} is not 0 or 1",
            raw_text=payload["raw_text"],
            auto_range=None,
        )
    return _artifact(
        "auto-range",
        "CONF:AUTO?",
        raw,
        status=COMPLETE,
        checks=[{"name": "auto_range_token", "status": "pass", "evidence": {"token": token}}],
        raw_text=payload["raw_text"],
        auto_range=token == "1",
        manual_range=token == "0",
        manual_page=112,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
    )


def parse_range_setting(raw: bytes) -> dict[str, Any]:
    """Parse ``CONF:RANG?``; the unit depends on the current function."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="range-setting")
    except ProtocolError as exc:
        return _failure("range-setting", "CONF:RANG?", raw, exc.status, str(exc))

    try:
        numeric = parse_ieee4882_numeric(payload["stripped"])
    except ProtocolError as exc:
        return _failure(
            "range-setting", "CONF:RANG?", raw, exc.status, str(exc),
            raw_text=payload["raw_text"], value_decimal=None,
        )
    if numeric["raw_unit_suffix"] is not None:
        return _failure(
            "range-setting",
            "CONF:RANG?",
            raw,
            INVALID,
            "CONF:RANG? returns a bare range number; a unit suffix cannot be attributed",
            raw_text=payload["raw_text"],
            value_decimal=None,
        )
    return _artifact(
        "range-setting",
        "CONF:RANG?",
        raw,
        status=UNVERIFIED,
        checks=[
            {"name": "numeric_parse", "status": "pass", "evidence": {"raw_token": payload["stripped"]}}
        ],
        reasons=["range_unit_depends_on_current_function"],
        raw_text=payload["raw_text"],
        value_decimal=numeric["value_decimal"],
        value_type="Decimal",
        unit=None,
        unit_status=UNVERIFIED,
        manual_page=111,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
    )


def parse_temperature_unit(raw: bytes) -> dict[str, Any]:
    """Parse ``SENS:UNIT?``; the manual does not exemplify its return text."""

    raw = bytes(raw)
    try:
        frame, metadata, payload = _frame_and_payload(raw, response_type="temperature-unit")
    except ProtocolError as exc:
        return _failure("temperature-unit", "SENS:UNIT?", raw, exc.status, str(exc))

    token = payload["stripped"].upper()
    if token not in {"C", "F"}:
        return _failure(
            "temperature-unit",
            "SENS:UNIT?",
            raw,
            UNSUPPORTED,
            f"temperature unit {payload['stripped']!r} is not C or F",
            raw_text=payload["raw_text"],
            unit=None,
        )
    return _artifact(
        "temperature-unit",
        "SENS:UNIT?",
        raw,
        status=UNVERIFIED,
        checks=[{"name": "temperature_unit_token", "status": "warn", "evidence": {"token": token}}],
        reasons=["temperature_unit_return_format_not_exemplified"],
        raw_text=payload["raw_text"],
        unit="°C" if token == "C" else "°F",
        unit_token=token,
        manual_page=125,
        terminator=metadata["terminator"].decode("ascii", errors="backslashreplace"),
    )


_FAILURE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "identity": {"raw_text": None, "vendor": None, "model": None, "serial": None, "firmware": None},
    "scalar-value": {
        "raw_text": None,
        "function": None,
        "quantity": None,
        "unit": None,
        "numeric_token": None,
        "value_decimal": None,
        "unit_source": None,
    },
    "two-display-reading": {
        "raw_text": None,
        "samples": [],
        "first_display": None,
        "second_display": None,
    },
    "beep-state": {"raw_text": None, "mode": None, "numeric_code": None},
    "system-error": {
        "raw_text": None,
        "message": None,
        "category": None,
        "error_present": None,
    },
    "function-setting": {"raw_text": None, "function_token": None, "quantity": None},
    "auto-range": {"raw_text": None, "auto_range": None, "manual_range": None},
    "range-setting": {"raw_text": None, "value_decimal": None, "unit": None},
    "temperature-unit": {"raw_text": None, "unit": None},
    "unparsed-query": {"raw_text": None},
}


def _failure(
    kind: str,
    command: str,
    raw: bytes,
    status: str,
    reason: str,
    **fields: Any,
) -> dict[str, Any]:
    merged = {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in _FAILURE_DEFAULTS.get(kind, {"raw_text": None}).items()
    }
    merged.update(fields)
    return _artifact(
        kind,
        command,
        raw,
        status=status,
        checks=[{"name": f"{kind}_parse", "status": "fail", "evidence": {"reason": reason}}],
        reasons=[reason],
        **merged,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def parse_response(raw: bytes, command: str) -> dict[str, Any]:
    """Parse one saved response according to the query that produced it."""

    if not isinstance(raw, (bytes, bytearray)):
        return _failure(
            "unparsed-query", command, b"", INVALID, "response must be bytes"
        )
    try:
        spec, _parameter = resolve_query(command)
    except CommandRefused as exc:
        return _failure("unparsed-query", command, bytes(raw), UNSUPPORTED, str(exc))

    if spec.kind == "identity":
        return parse_identity(raw)
    if spec.kind == "measurement":
        return parse_measurement(raw, spec)
    if spec.kind == "read":
        return parse_read(raw)
    if spec.kind == "beep-state":
        return parse_beep_state(raw)
    if spec.kind == "system-error":
        return parse_system_error(raw)
    if spec.kind == "function-setting":
        return parse_function_setting(raw)
    if spec.kind == "auto-range":
        return parse_auto_range(raw)
    if spec.kind == "range-setting":
        return parse_range_setting(raw)
    if spec.kind == "temperature-unit":
        return parse_temperature_unit(raw)
    return _failure(
        "unparsed-query", spec.canonical, bytes(raw), UNSUPPORTED,
        f"no parser is implemented for {spec.canonical}",
    )