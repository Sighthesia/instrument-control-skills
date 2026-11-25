#!/usr/bin/env python3
"""Per-channel evidence snapshot for an SDS800X HD oscilloscope.

Answers "does this channel carry activity?" from read values, never from a
screenshot. One explicit TCP session, one raw reply per row. The first transport
or protocol failure stops every later query (there is no reconnect), and the
rows already read stay in the result as evidence.

The helper never writes the measurement source, enables a measurement item,
changes numeric format, arms/stops the acquisition, or drains the error queue.
The optional sample probe selects only ``WAV:SOUR/WIDT/BYT/INT/STAR/POIN``
transfer options on an already stopped frame; ``--strict-readonly`` disables
even those writes. ``***``, ``****``, an empty or non-scalar reply, an error
string, or a value that cannot be attributed to a requested channel is
`UNVERIFIED`, never 0 V.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import time
from pathlib import Path
from typing import Callable, Optional

from scope_protocol import (
    ScopeProtocolError,
    ScopeSession,
    decide_waveform_width,
    normalize_acquisition_state,
    parse_wavedesc,
    read_wav_segment,
    save_json,
)
import screenshot_capture


def capture_png_on_session(*args, **kwargs):
    """Call the screenshot reader through its module so either seam is patchable."""

    return screenshot_capture.capture_png_on_session(*args, **kwargs)


SCHEMA = "channel-snapshot/v1"
CHANNELS = ("C1", "C2", "C3", "C4")
DEFAULT_METRICS = ("PKPK", "MAX", "MIN")
DEFAULT_SLICE_POINTS = 4096
SOURCE_QUERY = ":MEASure:SIMPle:SOURce?"
# Signed transfer-width bounds, not calibrated full scale. A code exactly on a
# bound means the ADC may have clipped the waveform for at least one sample.
CODE_BOUNDS = {1: (-128, 127), 2: (-32768, 32767)}
TRANSFER_SELECTION_WRITE_PREFIXES = ("WAV:SOUR ", "WAV:INT ", "WAV:WIDT ", "WAV:BYT ", "WAV:STAR ", "WAV:POIN ")
VISUAL_NOT_CAPTURED_REASON = (
    "screenshot not requested; waveform shape, ringing, and full-screen overview were not inspected"
)
VISUAL_QUALITATIVE_REASON = (
    "a screenshot is qualitative visual context only: it can show shape, ringing, and full-screen "
    "overview, but it cannot prove per-channel presence or absence"
)
# Manual (programming guide printed p. 48) defines memory depth by 1/2/4-channel
# mode and the series is sold as 2- or 4-channel, so every documented model has
# at least two channels. Only the verified target's four-channel count is
# established here; a four-channel count for another model needs the caller's
# declaration. An unrecognized model is refused rather than assumed.
MIN_SERIES_CHANNELS = 2
VERIFIED_MODEL_CHANNELS = {"SDS824X HD": 4}
DOCUMENTED_MODELS = frozenset(
    {
        "SDS802X HD",
        "SDS804X HD",
        "SDS812X HD",
        "SDS814X HD",
        "SDS822X HD",
        "SDS824X HD",
    }
)

STATE_MEANING = {
    "READY": "armed and waiting for a trigger; a displayed trace is live, not a completed frame",
    "STOP": "the acquisition is stopped; this snapshot describes the current stopped state and proves no new frame",
    "ARM": "armed; no trigger has completed",
    "AUTO": "auto trigger; a frame is not proof of a trigger event",
    "TRIGD": "a trigger occurred; the acquisition is not necessarily stopped",
    "ROLL": "roll streaming display; a streaming trace can never satisfy a Ready -> Stop proof",
    "WAIT": "waiting",
    "RUN": "running",
}


class SnapshotAborted(RuntimeError):
    """Internal stop signal: a transport failure forbids every later query."""


class QueryLog:
    """Send only queries and stop the whole run at the first transport failure.

    ``scope`` is optional so existing callers that only need ``ask`` (for
    example ``capture_scope.py``) keep their constructor contract. When it is
    supplied, the probe can log transfer-selection writes and IEEE block reads
    through the same failure gate.
    """

    def __init__(self, transport: Callable[[str], str], *, scope: Optional[ScopeSession] = None):
        self.transport = transport
        self.scope = scope
        self.entries: list[dict] = []
        self.failure: Optional[dict] = None

    def _guard(self, command: str) -> None:
        if self.failure is not None:
            raise SnapshotAborted(command)

    def record_failure(self, command: str, exc: BaseException) -> dict:
        """Record one transport or protocol failure and forbid later commands."""

        if self.failure is not None:
            return self.failure
        self.failure = {
            "query": command,
            "error": f"{type(exc).__name__}: {exc}",
            "meaning": "transport or protocol failure; no later query was sent and no reconnect was attempted",
        }
        self.entries.append(
            {"query": command, "raw": None, "status": "TRANSPORT_FAILURE", "error": self.failure["error"]}
        )
        return self.failure

    def ask(self, command: str) -> str:
        self._guard(command)
        try:
            raw = self.transport(command)
        except (ScopeProtocolError, OSError) as exc:
            self.record_failure(command, exc)
            raise SnapshotAborted(command) from exc
        self.entries.append({"query": command, "raw": raw, "status": "REPLIED"})
        return raw

    def write(self, command: str) -> None:
        """Send one already-approved transfer-selection write and log it."""

        self._guard(command)
        if self.scope is None:
            raise ScopeProtocolError("this QueryLog has no scope for writes")
        if not command.strip().upper().startswith(TRANSFER_SELECTION_WRITE_PREFIXES):
            raise ScopeProtocolError(f"refusing a non-transfer write in the snapshot: {command}")
        try:
            self.scope.write(command, allow_after_stop=True)
        except (ScopeProtocolError, OSError) as exc:
            self.record_failure(command, exc)
            raise SnapshotAborted(command) from exc
        self.entries.append({"query": command, "raw": None, "status": "SENT_TRANSFER_SELECTION", "write": True})

    def read_block(self, command: str):
        """Read one IEEE block response and keep its size and digest as evidence."""

        self._guard(command)
        if self.scope is None:
            raise ScopeProtocolError("this QueryLog has no scope for block reads")
        try:
            block = self.scope.query_block(command, allow_after_stop=True)
        except (ScopeProtocolError, OSError) as exc:
            self.record_failure(command, exc)
            raise SnapshotAborted(command) from exc
        self.entries.append(
            {
                "query": command,
                "raw": None,
                "status": "REPLIED",
                "response_kind": "ieee4882",
                "payload_bytes": len(block.payload),
                "sha256": block.sha256,
            }
        )
        return block


# A measurement reply is a bare NR3 on the verified firmware. The strict pattern
# deliberately rejects `-113,"Undefined header;..."`: a permissive "last number
# in the line" parser would read the error code as a measurement. Non-finite
# values such as `1E999` are rejected as well.
_SCALAR_PATTERN = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(?P<unit>V|A)?$",
    re.IGNORECASE,
)
_SOURCE_PATTERN = re.compile(r"^(C[1-4]|Z[1-4]|F\d+|ZF\d+|M\d+|ZM\d+|D\d+|ZD\d+|REF[A-D])$")
_TRIGGER_SOURCE_PATTERN = re.compile(r"^(C[1-4]|D(?:[0-9]|1[0-5])|EX|EX5|LINE)$")
_TRIGGER_TYPES = frozenset(
    {
        "EDGE",
        "PULSE",
        "SLOPE",
        "INTERVAL",
        "PATTERN",
        "RUNT",
        "WINDOW",
        "DROPOUT",
        "VIDEO",
        "QUALIFIED",
        "NEDGE",
        "DELAY",
        "SHOLD",
        "IIC",
        "SPI",
        "UART",
        "LIN",
        "CAN",
        "FLEXRAY",
        "CANFD",
        "IIS",
        "M1553",
        "SENT",
        "A429",
    }
)


def _header_key(value: str) -> str:
    """Normalize a reply header: no whitespace, no leading colon, upper case."""

    return re.sub(r"\s+", "", str(value)).lstrip(":").rstrip("?").upper()


def _header_set(*headers: str) -> set[str]:
    return {_header_key(header) for header in headers if header}


def _split_echo(text: str, allowed_echoes) -> tuple[Optional[str], Optional[str]]:
    """Split ``header token`` only when ``header`` is an expected reply header.

    A two-token reply whose first token is not an expected header (``ERROR 0``,
    ``C2:VDIV ...`` on a C1 query) is not a value. A one-token reply is returned
    as the token for the caller's own value pattern to validate.
    """

    parts = str(text).strip().split(None, 1)
    if len(parts) == 1:
        return parts[0].strip("\"'"), None
    allowed = {_header_key(item) for item in allowed_echoes}
    if len(parts) == 2 and _header_key(parts[0]) in allowed:
        return parts[1].strip().strip("\"'"), parts[0]
    return None, None


def parse_scalar_reply(
    raw: str, *, allowed_echoes=()
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Return ``(value, unit_suffix, echo)`` for a strict finite NR3 scalar reply.

    ``None`` value means the reply is not a readable scalar: ``***``, empty,
    multi-value, error text, ``1E999`` (non-finite), or a header that was not
    expected for this query. A reply is either a bare value or
    ``<expected header> <value>``; the header must be in ``allowed_echoes``, so
    ``ERROR 0`` and another channel's header are rejected even when the tail is
    numeric.
    """

    text = str(raw).strip()
    if not text:
        return None, None, None
    # Try the whole reply as a bare value first, so a scalar with a space before
    # its unit ("3.3 V") is not mistaken for an echo header.
    match = _SCALAR_PATTERN.fullmatch(text)
    echo = None
    if match is None:
        token, echo = _split_echo(text, allowed_echoes)
        if token is None:
            return None, None, None
        match = _SCALAR_PATTERN.fullmatch(token)
    if match is None:
        return None, None, echo
    value = float(match.group("number"))
    if not math.isfinite(value):
        return None, None, echo
    unit = match.group("unit")
    return value, (unit.upper() if unit else None), echo


def parse_token_reply(raw: str, *, allowed, allowed_echoes=()) -> Optional[str]:
    """Return one allowed token from a bare reply or an expected header + token."""

    text = str(raw).strip()
    if not text:
        return None
    token, _ = _split_echo(text, allowed_echoes)
    if token is None:
        return None
    token = token.upper()
    return token if token in allowed else None


# Horizontal context is a number with an engineering unit, not a measurement
# voltage. The unit set is closed per quantity so ``***``, an error string, or a
# mismatched unit cannot be read as a timebase, sample rate, or point count.
_QUANTITY_PATTERN = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(?P<unit>[A-Za-z/]*)$"
)
TIME_UNITS = frozenset({"", "s", "ms", "us", "ns", "ps"})
RATE_UNITS = frozenset({"", "sa/s", "sa", "ksa/s", "msa/s", "gsa/s", "ksa", "msa", "gsa"})
POINT_UNITS = frozenset({"", "pt", "pts", "kpt", "kpts", "mpt", "mpts", "point", "points", "sample", "samples"})
_UNIT_SCALES = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
    "ps": 1e-12,
    "sa/s": 1.0,
    "sa": 1.0,
    "ksa/s": 1e3,
    "ksa": 1e3,
    "msa/s": 1e6,
    "msa": 1e6,
    "gsa/s": 1e9,
    "gsa": 1e9,
    "kpt": 1e3,
    "kpts": 1e3,
    "mpt": 1e6,
    "mpts": 1e6,
}


TIME_SCALE_ECHOES = _header_set("TIM:SCAL?", "TIM:SCAL", ":TIMebase:SCALe", "TDIV")
SAMPLE_RATE_ECHOES = _header_set("ACQ:SRAT?", "ACQ:SRAT", ":ACQuire:SRATe", "SARA")
RECORD_POINTS_ECHOES = _header_set("ACQ:POIN?", "ACQ:POIN", ":ACQuire:POINts")


def parse_quantity_reply(
    raw: str, *, allowed_echoes=(), units=frozenset()
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Return ``(value, unit, echo)`` for one strict engineering-unit scalar.

    Unlike :func:`parse_scalar_reply`, this parser is for horizontal context
    (seconds, samples/s, points). The unit must be in the closed set for that
    quantity, so a voltage suffix on ``ACQ:POIN?`` or an unreadable placeholder
    never becomes a number.
    """

    text = str(raw).strip()
    if not text:
        return None, None, None
    match = _QUANTITY_PATTERN.fullmatch(text)
    echo = None
    if match is None:
        token, echo = _split_echo(text, allowed_echoes)
        if token is None:
            return None, None, None
        match = _QUANTITY_PATTERN.fullmatch(token)
    if match is None:
        return None, None, echo
    unit = match.group("unit").lower()
    if unit not in units:
        return None, None, echo
    value = float(match.group("number"))
    if not math.isfinite(value):
        return None, None, echo
    return value * _UNIT_SCALES.get(unit, 1.0), (unit or None), echo


SOURCE_ECHOES = _header_set(
    SOURCE_QUERY.rstrip("?"),
    ":MEAS:SIMP:SOUR",
    ":MEAS:SIMPle:SOUR",
)


def parse_pattern_reply(raw: str, *, pattern, allowed_echoes=()) -> Optional[str]:
    """Return one token matching ``pattern`` from a bare/expected-header reply."""

    text = str(raw).strip()
    if not text:
        return None
    token, _ = _split_echo(text, allowed_echoes)
    if token is None:
        return None
    candidate = token.upper()
    return candidate if pattern.fullmatch(candidate) else None


def parse_measurement_source(raw: str) -> Optional[str]:
    """Return the documented simple-measurement source token, or ``None``.

    Accepts a bare source (``C1``) or a source after the expected source-query
    header. ``ERROR C1`` is rejected because ``ERROR`` is not that header.
    """

    return parse_pattern_reply(raw, pattern=_SOURCE_PATTERN, allowed_echoes=SOURCE_ECHOES)


def parse_switch(raw: str, channel: str) -> Optional[str]:
    number = channel[1:]
    return parse_token_reply(
        raw,
        allowed={"ON", "OFF"},
        allowed_echoes=_header_set(f":CHANnel{number}:SWITch", f"CHAN{number}:SWIT"),
    )


def parse_coupling(raw: str, channel: str) -> Optional[str]:
    number = channel[1:]
    return parse_token_reply(
        raw,
        allowed={"AC", "DC", "GND"},
        allowed_echoes=_header_set(f":CHANnel{number}:COUPling", f"CHAN{number}:COUP"),
    )


def parse_unit(raw: str, channel: str) -> Optional[str]:
    number = channel[1:]
    return parse_token_reply(
        raw,
        allowed={"V", "A"},
        allowed_echoes=_header_set(f":CHANnel{number}:UNIT", f"CHAN{number}:UNIT"),
    )


TRIGGER_MODE_ECHOES = _header_set("TRMD", ":TRIGger:MODE", "TRIG:MODE")
TRIGGER_TYPE_ECHOES = _header_set(":TRIGger:TYPE", "TRIG:TYPE")
TRIGGER_SOURCE_ECHOES = _header_set(":TRIGger:EDGE:SOURce", "TRIG:EDGE:SOUR")
TRIGGER_SLOPE_ECHOES = _header_set(":TRIGger:EDGE:SLOPe", "TRIG:EDGE:SLOP")
TRIGGER_LEVEL_ECHOES = _header_set(":TRIGger:EDGE:LEVel", "TRIG:EDGE:LEV")


def parse_trigger_mode(raw: str) -> Optional[str]:
    return parse_token_reply(
        raw,
        allowed={"SINGLE", "NORMAL", "AUTO", "FTRIG"},
        allowed_echoes=TRIGGER_MODE_ECHOES,
    )


def parse_trigger_type(raw: str) -> Optional[str]:
    return parse_token_reply(raw, allowed=_TRIGGER_TYPES, allowed_echoes=TRIGGER_TYPE_ECHOES)


def parse_trigger_source(raw: str) -> Optional[str]:
    return parse_pattern_reply(
        raw,
        pattern=_TRIGGER_SOURCE_PATTERN,
        allowed_echoes=TRIGGER_SOURCE_ECHOES,
    )


def parse_trigger_slope(raw: str) -> Optional[str]:
    return parse_token_reply(
        raw,
        allowed={"RISING", "FALLING", "ALTERNATE"},
        allowed_echoes=TRIGGER_SLOPE_ECHOES,
    )


def _not_attempted(query: str, *, status: str = "NOT_ATTEMPTED", reason: str = "") -> dict:
    entry = {
        "query": query,
        "raw": None,
        "value": None,
        "unit": None,
        "status": status,
        "reason": reason or "not sent: an earlier transport failure stopped this read-only session",
    }
    return entry


def _read_scalar(
    log: QueryLog,
    query: str,
    *,
    quantity: str,
    channel_unit: Optional[str],
    echo_headers=(),
) -> dict:
    """Read one scale/offset value with a unit bound only from evidence.

    ``quantity`` is ``"scale"`` or ``"level"``. A reply suffix wins over the
    channel unit; a conflict is recorded instead of silently choosing one, and an
    unreadable channel unit leaves the unit `UNVERIFIED` rather than assuming V.
    An echo is accepted only for this query's own header or a documented short
    alias in ``echo_headers``.
    """

    raw = log.ask(query)
    value, reply_unit, echo = parse_scalar_reply(
        raw, allowed_echoes=_header_set(query, *echo_headers)
    )
    unit = None
    unit_status = "UNVERIFIED"
    if reply_unit and channel_unit and reply_unit != channel_unit:
        unit_status = "CONFLICT"
    elif reply_unit or channel_unit:
        base = reply_unit or channel_unit
        unit = f"{base}/div" if quantity == "scale" else base
        unit_status = "BOUND"
    entry = {
        "query": query,
        "raw": raw,
        "value": value,
        "unit": unit,
        "unit_status": unit_status,
        "channel_unit": channel_unit,
        "reply_unit": reply_unit,
        "status": "OBSERVED" if value is not None else "UNVERIFIED",
    }
    if echo:
        entry["echo"] = echo
    if value is None:
        entry["reason"] = "reply is not a readable NR3 scalar"
    elif unit_status == "CONFLICT":
        entry["reason"] = f"reply suffix {reply_unit} conflicts with :CHANnel<n>:UNIT? {channel_unit}"
    return entry


def _read_switch(log: QueryLog, query: str, channel: str) -> dict:
    raw = log.ask(query)
    state = parse_switch(raw, channel)
    entry = {"query": query, "raw": raw, "state": state, "status": "OBSERVED" if state else "UNVERIFIED"}
    if state is None:
        entry["reason"] = "reply is not a bare ON/OFF or this channel's switch header followed by ON/OFF"
    return entry


def _read_coupling(log: QueryLog, query: str, channel: str) -> dict:
    raw = log.ask(query)
    state = parse_coupling(raw, channel)
    entry = {"query": query, "raw": raw, "state": state, "status": "OBSERVED" if state else "UNVERIFIED"}
    if state is None:
        entry["reason"] = "reply is not a bare AC/DC/GND or this channel's coupling header followed by one"
    return entry


def _read_channel_row(log: QueryLog, channel: str, row: dict) -> None:
    number = channel[1:]
    row["switch"] = _read_switch(log, f":CHANnel{number}:SWITch?", channel)
    raw_unit = log.ask(f":CHANnel{number}:UNIT?")
    channel_unit = parse_unit(raw_unit, channel)
    row["unit"] = {
        "query": f":CHANnel{number}:UNIT?",
        "raw": raw_unit,
        "unit": channel_unit,
        "status": "OBSERVED" if channel_unit else "UNVERIFIED",
    }
    if channel_unit is None:
        row["unit"]["reason"] = "reply is not a bare V/A or this channel's unit header followed by V/A"
    row["vdiv"] = _read_scalar(
        log,
        f"C{number}:VDIV?",
        quantity="scale",
        channel_unit=channel_unit,
        echo_headers=(f":CHANnel{number}:SCALe", f"CHAN{number}:SCAL"),
    )
    row["offset"] = _read_scalar(
        log,
        f"C{number}:OFST?",
        quantity="level",
        channel_unit=channel_unit,
        echo_headers=(f":CHANnel{number}:OFFSet", f"CHAN{number}:OFFS"),
    )
    row["coupling"] = _read_coupling(log, f":CHANnel{number}:COUPling?", channel)


def _finalize_channel_row(row: dict, channel: str) -> None:
    number = channel[1:]
    for key, query in (
        ("switch", f":CHANnel{number}:SWITch?"),
        ("unit", f":CHANnel{number}:UNIT?"),
        ("vdiv", f"C{number}:VDIV?"),
        ("offset", f"C{number}:OFST?"),
        ("coupling", f":CHANnel{number}:COUPling?"),
    ):
        if key not in row:
            row[key] = _not_attempted(query)
    row.setdefault("status", "UNVERIFIED")


def _measurement_metric_entry(query: str, metric: str, raw: str) -> dict:
    # A metric value is a bare NR3 per the manual: no header echo is accepted.
    value, reply_unit, echo = parse_scalar_reply(raw)
    entry = {
        "query": query,
        "raw": raw,
        "metric": metric,
        "value": value,
        "unit": None,
        "reply_unit": reply_unit,
        "unit_status": "UNVERIFIED",
        "status": "OBSERVED" if value is not None else "UNVERIFIED",
    }
    if echo:
        entry["echo"] = echo
    if value is None:
        entry["reason"] = "reply is not a readable finite NR3 scalar (***, empty, non-scalar, overflow, or error text); no value is recorded"
    elif metric == "PKPK" and value < 0:
        entry["value"] = None
        entry["status"] = "UNVERIFIED"
        entry["reason"] = "PKPK is a peak-to-peak magnitude; a negative reply contradicts its definition and is not recorded as a level"
    elif value == 0:
        if metric == "PKPK":
            entry["zero_semantics"] = (
                "PKPK 0 means no variation was measured in the current measurement window; "
                "it is not an absolute 0 V level and not evidence that the channel is undriven. "
                "A negative conclusion from stored samples must still state the original offline "
                "window and the detection capability (observation_status, detection_resolution_s, "
                "minimum_detectable_pulse_s)."
            )
        else:
            entry["zero_semantics"] = (
                "a measured level of 0 is one finding, not a diagnosis; channel state, coupling, "
                "scale/clipping, probe-ground reference, and an undriven pin all remain possible"
            )
    return entry


def _bind_units(block: dict) -> None:
    """Bind V/A only from evidence: a reply suffix or this channel's UNIT? readback."""

    unit_entry = block.get("unit") or {}
    channel_unit = unit_entry.get("unit")
    for entry in block["metrics"].values():
        if entry.get("status") != "OBSERVED":
            continue
        reply_unit = entry.get("reply_unit")
        if reply_unit and channel_unit and reply_unit != channel_unit:
            entry["status"] = "UNVERIFIED"
            entry["value"] = None
            entry["reason"] = (
                f"measurement reply suffix {reply_unit} conflicts with :CHANnel<n>:UNIT? {channel_unit}; "
                "the unit cannot be bound"
            )
            entry["unit_status"] = "CONFLICT"
            continue
        unit = reply_unit or channel_unit
        if unit:
            entry["unit"] = unit
            entry["unit_status"] = "BOUND"
            entry["unit_basis"] = "measurement_reply_suffix" if reply_unit else unit_entry.get("query")
        else:
            entry["unit"] = None
            entry["unit_status"] = "UNVERIFIED"
            entry["unit_reason"] = "no reply suffix and no readable :CHANnel<n>:UNIT? for the measurement source"


def _sanitize_block(block: dict) -> None:
    """Remove numeric values that are not backed by a matched V/A observation.

    The raw reply stays for audit. A value may be consumed as a level only when
    the before/after source readback named one channel and the unit was bound to
    V or A from a reply suffix or that channel's UNIT? readback. Ampere values
    stay (the offline analyzer rejects them as volts); an unknown unit never
    leaves a consumable number.
    """

    matched = block.get("source") in CHANNELS and block.get("source_stable") is True
    for entry in block["metrics"].values():
        if entry.get("status") != "OBSERVED":
            entry["value"] = None
            continue
        unit_ok = entry.get("unit_status") == "BOUND" and entry.get("unit") in ("V", "A")
        if matched and unit_ok:
            continue
        entry["value"] = None
        entry["unit"] = None
        entry["unit_status"] = "UNVERIFIED"
        entry["status"] = "UNVERIFIED"
        entry["reason"] = (
            "measurement source is not an attributed channel; only the raw reply is retained"
            if not matched
            else "measurement unit is not established as V or A; only the raw reply is retained"
        )
    block["value_export"] = (
        "only metrics with a proven V/A unit on the matched source keep a numeric value; "
        "all other metric observations are raw-only"
    )


def read_measurement_block(log: QueryLog, metrics=DEFAULT_METRICS, channel_units=None) -> dict:
    """Read the one simple-measurement panel with a source check on both sides.

    The panel has exactly one source. ``:MEASure:SIMPle:SOURce?`` is documented
    (programming guide PDF p. 210) and is read before and after the metric
    queries; numeric values are kept only when both readbacks name the same
    channel. No write, no item enable, and no format change is sent.
    """

    block: dict = {
        "source_query": SOURCE_QUERY,
        "source_before": None,
        "source_after": None,
        "source": None,
        "source_stable": None,
        "metrics": {},
        "unit": None,
        "transport_failure": None,
        "queried_at": None,
    }
    try:
        raw_before = log.ask(SOURCE_QUERY)
        parsed_before = parse_measurement_source(raw_before)
        source_before = {
            "query": SOURCE_QUERY,
            "raw": raw_before,
            "source": parsed_before,
            "status": "OBSERVED" if parsed_before else "UNVERIFIED",
        }
        if source_before["source"] is None:
            source_before["reason"] = "reply does not name a documented measurement source"
        block["source_before"] = source_before
        if source_before["source"] is None:
            for metric in metrics:
                block["metrics"][metric] = _not_attempted(
                    f":MEASure:SIMPle:VALue? {metric}",
                    reason="not sent: the simple-measurement source could not be established, so no value can be attributed",
                )
            _sanitize_block(block)
            block["queried_at"] = _utc_now()
            return block

        for metric in metrics:
            query = f":MEASure:SIMPle:VALue? {metric}"
            raw = log.ask(query)
            block["metrics"][metric] = _measurement_metric_entry(query, metric, raw)

        raw_after = log.ask(SOURCE_QUERY)
        parsed_after = parse_measurement_source(raw_after)
        source_after = {
            "query": SOURCE_QUERY,
            "raw": raw_after,
            "source": parsed_after,
            "status": "OBSERVED" if parsed_after else "UNVERIFIED",
        }
        if source_after["source"] is None:
            source_after["reason"] = "reply does not name a documented measurement source"
        block["source_after"] = source_after
        stable = source_after["source"] is not None and source_after["source"] == source_before["source"]
        block["source_stable"] = stable
        block["source"] = source_before["source"] if stable else None

        if stable and source_before["source"] in CHANNELS:
            known_unit = (channel_units or {}).get(source_before["source"])
            if isinstance(known_unit, dict) and known_unit.get("raw") is not None:
                block["unit"] = known_unit
            else:
                number = source_before["source"][1:]
                raw_unit = log.ask(f":CHANnel{number}:UNIT?")
                parsed_unit = parse_unit(raw_unit, source_before["source"])
                block["unit"] = {
                    "query": f":CHANnel{number}:UNIT?",
                    "raw": raw_unit,
                    "unit": parsed_unit,
                    "status": "OBSERVED" if parsed_unit else "UNVERIFIED",
                }
                if block["unit"]["unit"] is None:
                    block["unit"]["reason"] = "reply is not a bare V/A or the measurement source's unit header followed by V/A"
        _bind_units(block)
        _sanitize_block(block)
        block["queried_at"] = _utc_now()
        return block
    except SnapshotAborted:
        block["transport_failure"] = log.failure
        block["queried_at"] = block["queried_at"] or _utc_now()
        for metric in metrics:
            query = f":MEASure:SIMPle:VALue? {metric}"
            block["metrics"].setdefault(metric, _not_attempted(query))
        if block.get("source_before") is None:
            block["source_before"] = _not_attempted(SOURCE_QUERY)
        if block.get("source_after") is None:
            block["source_after"] = _not_attempted(SOURCE_QUERY)
        _sanitize_block(block)
        return block


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def attribute_measurements(block: dict, channels) -> dict:
    """Build the per-channel manifest block; only the proven source gets values."""

    source = block.get("source")
    stable = block.get("source_stable")
    failure = block.get("transport_failure")
    queried_at = block.get("queried_at")
    result: dict = {}
    for channel in channels:
        matched = source == channel and stable is True
        entry: dict = {
            "source": source,
            "source_query": SOURCE_QUERY,
            "source_raw_before": (block.get("source_before") or {}).get("raw"),
            "source_raw_after": (block.get("source_after") or {}).get("raw"),
            "source_stable": stable,
            "queried_at": queried_at,
        }
        if matched:
            entry["source_attribution"] = "verified-simple-source-readback"
            statuses = {metric_entry.get("status") for metric_entry in block["metrics"].values()}
            query_status = "INCOMPLETE" if failure or "NOT_ATTEMPTED" in statuses else "COMPLETE"
            usable_metrics: list[str] = []
            for metric, metric_entry in block["metrics"].items():
                usable = (
                    metric_entry.get("status") == "OBSERVED"
                    and metric_entry.get("value") is not None
                    and metric_entry.get("unit") in ("V", "A")
                    and metric_entry.get("unit_status") == "BOUND"
                )
                if usable:
                    usable_metrics.append(metric)
                item = {
                    "metric": metric,
                    "value": metric_entry.get("value") if usable else None,
                    "unit": metric_entry.get("unit") if usable else None,
                    "unit_status": metric_entry.get("unit_status") if usable else "UNVERIFIED",
                    "raw": metric_entry.get("raw"),
                    "source_query": metric_entry.get("query"),
                    "source": source,
                    "status": (
                        "OBSERVED"
                        if usable
                        else ("NOT_ATTEMPTED" if metric_entry.get("status") == "NOT_ATTEMPTED" else "UNVERIFIED")
                    ),
                }
                for extra in ("reason", "zero_semantics", "unit_reason"):
                    if metric_entry.get(extra):
                        item[extra] = metric_entry[extra]
                if not usable and metric_entry.get("status") == "OBSERVED":
                    item["reason"] = "unit is not established as V or A; the raw reply is retained for audit"
                entry[metric.lower()] = item
            entry["query_status"] = query_status
            entry["usable_metrics"] = usable_metrics
            entry["status"] = (
                "OBSERVED"
                if usable_metrics
                else ("INCOMPLETE" if query_status == "INCOMPLETE" else "UNVERIFIED")
            )
            result[channel] = entry
            continue

        if source is None:
            entry["source_attribution"] = "unknown"
            reason = (
                "the simple-measurement source could not be established from "
                f"{SOURCE_QUERY}; no value can be attributed to {channel}"
            )
        else:
            entry["source_attribution"] = "other-source"
            reason = (
                f"the simple-measurement source is {source}, not {channel}; "
                f"no value from {SOURCE_QUERY} may be recorded for {channel}"
            )
        if failure:
            reason = f"measurement readback stopped by a transport failure before this channel could be attributed; {reason}"
        statuses = {metric_entry.get("status") for metric_entry in block["metrics"].values()}
        entry["query_status"] = "INCOMPLETE" if failure or "NOT_ATTEMPTED" in statuses else "COMPLETE"
        entry["usable_metrics"] = []
        entry["status"] = "UNVERIFIED"
        entry["reason"] = reason
        for metric, metric_entry in block["metrics"].items():
            metric_status = metric_entry.get("status")
            item = {
                "metric": metric,
                "value": None,
                "unit": None,
                "unit_status": "UNVERIFIED",
                "raw": metric_entry.get("raw"),
                "source_query": metric_entry.get("query"),
                "source": source,
                "status": "NOT_ATTEMPTED" if metric_status == "NOT_ATTEMPTED" else "UNVERIFIED",
                "reason": metric_entry.get("reason") if metric_status == "NOT_ATTEMPTED" else reason,
            }
            entry[metric.lower()] = item
        result[channel] = entry
    return result


class _ProbeSession:
    """Route every WAV transfer command through QueryLog's failure gate."""

    def __init__(self, log: QueryLog):
        self.log = log

    def write(self, command: str, *, allow_after_stop: bool = False, explicit_release: bool = False) -> None:
        self.log.write(command)

    def query_ascii(self, command: str, *, allow_after_stop: bool = False) -> str:
        return self.log.ask(command)

    def query_block(self, command: str, *, allow_after_stop: bool = False):
        return self.log.read_block(command)


def _sample_probe_entry(
    channel: str, *, status: str, reason: Optional[str] = None, activity_hint: str = "UNVERIFIED"
) -> dict:
    entry = {
        "channel": channel,
        "status": status,
        "activity_hint": activity_hint,
        "coverage_mode": None,
        "sampled_points": 0,
        "total_points": None,
        "coverage_ratio": None,
        "slices": [],
        "bytes_per_point": None,
        "code_bounds": None,
        "code_min": None,
        "code_max": None,
        "code_span": None,
        "clipped": None,
        "transfer_selection_writes": [],
    }
    if reason:
        entry["reason"] = reason
    return entry


def decode_transfer_codes(payload: bytes, bytes_per_point: int) -> list[int]:
    """Decode signed little-endian transfer codes without numpy."""

    if bytes_per_point not in CODE_BOUNDS:
        raise ScopeProtocolError(f"unsupported waveform transfer width: {bytes_per_point} bytes")
    if len(payload) % bytes_per_point:
        raise ScopeProtocolError(
            f"payload {len(payload)} bytes is not divisible by {bytes_per_point} B/point"
        )
    fmt = "<b" if bytes_per_point == 1 else "<h"
    return [value for (value,) in struct.iter_unpack(fmt, payload)]


def plan_sample_slices(total_points: int, slice_points: int, max_points: int) -> tuple[str, list[dict]]:
    """Choose a full chunked read or three non-overlapping sample slices."""

    if total_points <= 0:
        raise ScopeProtocolError("record point count must be positive")
    budget = min(slice_points, max_points)
    if budget <= 0:
        raise ScopeProtocolError("slice and transfer budgets must be positive")
    if total_points <= slice_points * 3:
        ranges: list[dict] = []
        start = 0
        while start < total_points:
            count = min(budget, total_points - start)
            ranges.append({"start": start, "points": count})
            start += count
        return "FULL_RECORD", ranges
    return "PARTIAL_SLICES", [
        {"start": 0, "points": budget},
        {"start": (total_points - budget) // 2, "points": budget},
        {"start": total_points - budget, "points": budget},
    ]


def _apply_probe_coverage(
    entry: dict,
    slices: list[dict],
    *,
    total_points: Optional[int],
    coverage_mode: Optional[str],
    bytes_per_point: Optional[int],
) -> None:
    entry["slices"] = slices
    entry["coverage_mode"] = coverage_mode
    entry["bytes_per_point"] = bytes_per_point
    entry["total_points"] = total_points
    sampled = sum(item["points"] for item in slices)
    entry["sampled_points"] = sampled
    entry["coverage_ratio"] = round(sampled / total_points, 6) if total_points else None
    if bytes_per_point in CODE_BOUNDS:
        low, high = CODE_BOUNDS[bytes_per_point]
        entry["code_bounds"] = {"low": low, "high": high, "source": "signed transfer width"}
    if slices:
        code_min = min(item["code_min"] for item in slices)
        code_max = max(item["code_max"] for item in slices)
        entry["code_min"] = code_min
        entry["code_max"] = code_max
        entry["code_span"] = code_max - code_min
        if bytes_per_point in CODE_BOUNDS:
            low, high = CODE_BOUNDS[bytes_per_point]
            entry["clipped"] = code_min <= low or code_max >= high


def _activity_hint(entry: dict) -> str:
    if entry.get("clipped") is True:
        return "CLIPPED"
    span = entry.get("code_span")
    if span is None:
        return "UNVERIFIED"
    if span > 0:
        return "ACTIVE_CODES"
    if entry.get("coverage_mode") == "FULL_RECORD":
        return "FLAT_IN_FULL_RECORD"
    if entry.get("coverage_mode") == "PARTIAL_SLICES":
        return "FLAT_IN_SAMPLED_SLICES_ONLY"
    return "UNVERIFIED"


def _coverage_warning(entry: dict) -> Optional[str]:
    hint = entry.get("activity_hint")
    if hint == "FLAT_IN_SAMPLED_SLICES_ONLY":
        return (
            "flat only inside the three sampled slices; a pulse outside the head/middle/tail "
            "slices would be missed, so this is not evidence that the channel is undriven"
        )
    if hint == "FLAT_IN_FULL_RECORD":
        return (
            "flat across the full read record; this is a finding that still needs apparent-zero "
            "triage, not a diagnosis"
        )
    if hint == "CLIPPED":
        return "codes touched the signed transfer boundary; amplitude and shape may be clipped"
    return None


def _set_probe_hint(entry: dict) -> None:
    entry["activity_hint"] = _activity_hint(entry)
    warning = _coverage_warning(entry)
    if warning is None:
        entry.pop("coverage_warning", None)
    else:
        entry["coverage_warning"] = warning


def _probe_integer(log: QueryLog, query: str) -> int:
    raw = log.ask(query)
    value, _unit, _echo = parse_quantity_reply(
        raw, allowed_echoes=_header_set(query, query.rstrip("?")), units=POINT_UNITS
    )
    if value is None or not value.is_integer() or value <= 0:
        raise ScopeProtocolError(f"{query} did not return a positive whole number: {raw!r}")
    return int(value)


def probe_channel_samples(
    scope,
    log: QueryLog,
    channel: str,
    *,
    slice_points: int,
    record_points_entry: Optional[dict],
) -> dict:
    """Read bounded samples for one stopped, enabled channel.

    Only ``WAV:`` transfer-selection writes are sent. Acquisition state, trigger,
    vertical scale/offset, timebase, and the measurement source are never
    written. Every transfer command goes through ``QueryLog`` so the first
    failure stops the rest of the snapshot.
    """

    entry = _sample_probe_entry(channel, status="UNVERIFIED")
    original_mode = scope.capture_mode
    proxy = _ProbeSession(log)
    entry_start = len(log.entries)
    slices: list[dict] = []
    coverage_mode: Optional[str] = None
    total_points: Optional[int] = None
    bytes_per_point: Optional[int] = None
    step = f"WAV:SOUR {channel}"

    def write(command: str) -> None:
        log.write(command)

    try:
        scope.capture_mode = "configured_capture"
        write(f"WAV:SOUR {channel}")
        step = "WAV:INT 1"
        write("WAV:INT 1")
        step = "WAV:INT?"
        if _probe_integer(log, "WAV:INT?") != 1:
            raise ScopeProtocolError("scope did not accept WAV:INT 1")
        step = "WAV:STAR 0"
        write("WAV:STAR 0")
        step = "WAV:PRE?"
        initial_preamble = parse_wavedesc(log.read_block("WAV:PRE?").payload)
        selection = decide_waveform_width(initial_preamble, "auto")
        bytes_per_point = int(selection["bytes_per_point"])
        step = f"WAV:WIDT {selection['width_command']}"
        write(step)
        if bytes_per_point == 2:
            step = "WAV:BYT LSB"
            write(step)
            step = "WAV:BYT?"
            if log.ask("WAV:BYT?").strip().upper() != "LSB":
                raise ScopeProtocolError("scope did not accept WAV:BYT LSB")
        step = "WAV:PRE?"
        preamble = parse_wavedesc(log.read_block("WAV:PRE?").payload)
        if preamble["data_width_bytes"] != bytes_per_point:
            raise ScopeProtocolError(
                f"requested {bytes_per_point} B/point, WAVEDESC reports {preamble['data_width_bytes']} B/point"
            )
        if bytes_per_point == 2 and preamble["byte_order"] != "LSB":
            raise ScopeProtocolError("requested LSB WORD transfer, WAVEDESC reports MSB")
        step = "WAV:MAXP?"
        max_points = _probe_integer(log, "WAV:MAXP?")
        entry["wav_pre_points"] = int(preamble["wave_array_count"])
        pre_points = entry["wav_pre_points"]
        if pre_points <= 0:
            raise ScopeProtocolError(f"WAV:PRE? reports {pre_points} points")
        total_points = pre_points
        authority = "WAV:PRE? wave_array_count"
        record_total = (
            record_points_entry.get("value")
            if isinstance(record_points_entry, dict) and record_points_entry.get("status") == "OBSERVED"
            else None
        )
        if record_total is not None and int(record_total) < total_points:
            total_points = int(record_total)
            authority = "ACQ:POIN? (valid and smaller than WAV:PRE?)"
        elif record_total is None:
            authority = "WAV:PRE? wave_array_count (ACQ:POIN? is UNVERIFIED)"
        else:
            authority = "WAV:PRE? wave_array_count (not larger than ACQ:POIN?)"
        entry["total_points_authority"] = authority
        coverage_mode, ranges = plan_sample_slices(total_points, slice_points, max_points)
        for item in ranges:
            start, count = item["start"], item["points"]
            step = f"WAV:DATA? start={start} points={count}"
            block = read_wav_segment(proxy, start, count, preamble)
            codes = decode_transfer_codes(block.payload, bytes_per_point)
            slice_entry = {
                "start": start,
                "end_exclusive": start + len(codes),
                "points": len(codes),
                "code_min": min(codes),
                "code_max": max(codes),
                "code_span": max(codes) - min(codes),
                "sha256": block.sha256,
            }
            slices.append(slice_entry)
        _apply_probe_coverage(
            entry,
            slices,
            total_points=total_points,
            coverage_mode=coverage_mode,
            bytes_per_point=bytes_per_point,
        )
        entry["status"] = "OBSERVED"
        _set_probe_hint(entry)
    except SnapshotAborted:
        entry["status"] = "INCOMPLETE"
        entry["activity_hint"] = "UNVERIFIED"
        entry["reason"] = (
            "sample probe stopped by a transport or protocol failure; completed slices are retained and "
            "no later device query was sent"
        )
    except (ScopeProtocolError, OSError) as exc:
        if log.failure is None:
            log.record_failure(step, exc)
        entry["status"] = "INCOMPLETE"
        entry["activity_hint"] = "UNVERIFIED"
        entry["reason"] = f"sample probe stopped at {step!r}: {type(exc).__name__}: {exc}"
    finally:
        scope.capture_mode = original_mode
        entry["transfer_selection_writes"] = [
            item["query"] for item in log.entries[entry_start:] if item.get("write")
        ]
        _apply_probe_coverage(
            entry,
            slices,
            total_points=total_points,
            coverage_mode=coverage_mode,
            bytes_per_point=bytes_per_point,
        )
        if entry["status"] == "OBSERVED":
            _set_probe_hint(entry)
    return entry


def run_sample_probes(
    scope,
    log: QueryLog,
    snapshot: dict,
    *,
    strict_readonly: bool,
    slice_points: int,
) -> None:
    """Attach one sample-probe entry per supported requested channel."""

    acquisition = snapshot.get("acquisition") or {}
    state = acquisition.get("state")
    horizontal = snapshot.get("horizontal") or {}
    record_points_entry = horizontal.get("record_points")
    for channel in snapshot.get("requested_channels", []):
        row = snapshot["channels"].get(channel)
        if row is None or row.get("status") == "UNSUPPORTED":
            continue
        if log.failure is not None:
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="NOT_ATTEMPTED",
                reason="not attempted: an earlier transport or protocol failure stopped this session",
            )
            continue
        if state is None:
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="UNVERIFIED",
                reason="acquisition state could not be established from SAST?; no sample probe was attempted",
            )
            continue
        if state != "STOP":
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="LIVE_NOT_STOPPED",
                reason=(
                    f"SAST? reports {state}; the scope was not stopped and no sample probe was attempted. "
                    "Capture a single-shot frame before concluding anything about this channel"
                ),
            )
            continue
        switch = (row.get("switch") or {}).get("state")
        if strict_readonly:
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="SKIPPED_STRICT_READONLY",
                reason=(
                    "strict read-only mode disables every WAV transfer-selection write, so no sample "
                    "probe ran; the command log contains queries only"
                ),
            )
            continue
        if switch == "OFF":
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="CHANNEL_OFF",
                reason="channel switch is OFF; no sample probe was attempted",
            )
            continue
        if switch != "ON":
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="UNVERIFIED",
                reason="channel switch state could not be read; no sample probe was attempted",
            )
            continue
        row["sample_probe"] = probe_channel_samples(
            scope,
            log,
            channel,
            slice_points=slice_points,
            record_points_entry=record_points_entry,
        )
        if log.failure is not None:
            # The failing channel is recorded; every later channel is marked
            # NOT_ATTEMPTED below and the screenshot is skipped as well.
            continue
    for channel in snapshot.get("requested_channels", []):
        row = snapshot["channels"].get(channel)
        if row is None or row.get("status") == "UNSUPPORTED":
            continue
        if "sample_probe" not in row:
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="NOT_ATTEMPTED",
                reason="not attempted: an earlier transport or protocol failure stopped this session",
            )


def build_triage(row: dict, measurement: dict) -> Optional[dict]:
    """List the causes of a measured zero; never conclude "no signal".

    Triage is produced only from a usable zero-amplitude PKPK reading. An
    unreadable amplitude is missing evidence, not an apparent zero, and does not
    trigger this list.
    """

    if measurement.get("source_attribution") != "verified-simple-source-readback":
        return None
    pkpk = measurement.get("pkpk") or {}
    if pkpk.get("status") != "OBSERVED" or pkpk.get("value") != 0:
        return None
    observed = [
        item.get("value")
        for key, item in measurement.items()
        if isinstance(item, dict) and key in ("pkpk", "max", "min", "top", "base") and item.get("value") is not None
    ]
    if any(value not in (None, 0) for value in observed):
        # Contradictory extrema mean the zero amplitude is not a clean finding;
        # do not build a diagnosis on it.
        return None

    switch = row.get("switch") or {}
    coupling = row.get("coupling") or {}
    causes = [
        {
            "cause": "channel disabled",
            "status": "CONFIRMED" if switch.get("state") == "OFF" else ("EXCLUDED" if switch.get("state") == "ON" else "UNVERIFIED"),
            "evidence": switch,
            "meaning": "SWITch OFF disables the channel; SWITch ON only enables it and does not by itself prove a signal",
        },
        {
            "cause": "GND coupling disconnects the input",
            "status": "CONFIRMED" if coupling.get("state") == "GND" else ("EXCLUDED" if coupling.get("state") else "UNVERIFIED"),
            "evidence": coupling,
        },
        {
            "cause": "wrong vertical scale or clipping",
            "status": "UNVERIFIED",
            "evidence": {"vdiv": row.get("vdiv"), "offset": row.get("offset")},
            "requires": "compare the channel range with the expected signal amplitude; VDIV/OFST reads alone cannot exclude clipping",
        },
        {
            "cause": "probe ground on a different board reference",
            "status": "UNVERIFIED",
            "requires": "independent electrical check that the probe ground is on the same board's GND; multi-MCU boards have separate references",
        },
        {
            "cause": "genuinely undriven pin",
            "status": "UNVERIFIED",
            "requires": "every earlier cause excluded by its own evidence, plus independent electrical evidence (for example a second known-good probe or a known driver state); PKPK=0 alone cannot assert it",
        },
    ]
    return {
        "question": "measured zero amplitude",
        "causes": causes,
        "conclusion": "UNVERIFIED",
        "detection_limit": (
            "PKPK=0 is bounded by the instrument's current measurement window. A negative "
            "conclusion from stored samples must still state the original offline window and "
            "observation_status=NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY, detection_resolution_s, "
            "and minimum_detectable_pulse_s."
        ),
        "rule": "a true 0 V reading is a finding, not a diagnosis; this snapshot never returns a 'no signal' verdict",
    }


def parse_idn(raw: str) -> dict:
    fields = [field.strip() for field in str(raw).strip().split(",")]
    while len(fields) < 4:
        fields.append("")
    return {
        "idn_raw": str(raw).strip(),
        "vendor": fields[0] or None,
        "model": fields[1] or None,
        "serial": fields[2] or None,
        "firmware": fields[3] or None,
    }


def resolve_channel_count(model: Optional[str], declared: Optional[int] = None) -> tuple[Optional[int], str]:
    if declared is not None:
        return declared, "user-supplied"
    key = re.sub(r"\s+", " ", (model or "").strip().upper())
    if key in VERIFIED_MODEL_CHANNELS:
        return VERIFIED_MODEL_CHANNELS[key], "verified-target"
    if key in DOCUMENTED_MODELS:
        return MIN_SERIES_CHANNELS, "series-minimum"
    return None, "unknown"


def _read_horizontal(log: QueryLog, snapshot: dict) -> None:
    """Read timebase, sample rate, and record length as horizontal context.

    ``ACQ:POIN?`` is also the record-length authority for the sample probe: a
    ``WAV:PRE?`` transfer window may reflect ``WFSU`` instead of the acquired
    record, so the probe uses the smaller valid value.
    """

    horizontal = snapshot["horizontal"] = {}
    specs = (
        ("timebase", "TIM:SCAL?", TIME_SCALE_ECHOES, TIME_UNITS, "timebase must be a positive finite number of seconds"),
        ("sample_rate", "ACQ:SRAT?", SAMPLE_RATE_ECHOES, RATE_UNITS, "sample rate must be a positive finite number of samples per second"),
        ("record_points", "ACQ:POIN?", RECORD_POINTS_ECHOES, POINT_UNITS, "record length must be a positive whole number of points"),
    )
    for key, query, echoes, units, requirement in specs:
        raw = log.ask(query)
        value, unit, echo = parse_quantity_reply(raw, allowed_echoes=echoes, units=units)
        entry = {
            "query": query,
            "raw": raw,
            "value": value,
            "unit": unit,
            "status": "OBSERVED" if value is not None else "UNVERIFIED",
        }
        if echo:
            entry["echo"] = echo
        if value is not None and key == "record_points" and (not value.is_integer() or value <= 0):
            entry["value"] = None
            entry["status"] = "UNVERIFIED"
            entry["reason"] = requirement
        elif value is not None and value <= 0:
            entry["value"] = None
            entry["status"] = "UNVERIFIED"
            entry["reason"] = requirement
        elif value is None:
            entry["reason"] = (
                "reply is not a readable engineering-unit scalar for this query; "
                "no value is recorded"
            )
        horizontal[key] = entry
    snapshot["acquisition"]["horizontal"] = horizontal


def _read_acquisition(log: QueryLog, snapshot: dict) -> None:
    acquisition = snapshot["acquisition"] = {}
    raw = log.ask("SAST?")
    try:
        state = normalize_acquisition_state(raw)
        reason = None
    except ScopeProtocolError as exc:
        state = None
        reason = f"unrecognized acquisition-state reply: {exc}"
    acquisition.update(
        {
            "query": "SAST?",
            "raw": raw,
            "state": state,
            "meaning": STATE_MEANING.get(state, "UNRECOGNIZED"),
            "status": "OBSERVED" if state else "UNVERIFIED",
        }
    )
    if reason:
        acquisition["reason"] = reason

    _read_horizontal(log, snapshot)

    trigger = snapshot["trigger"] = {}
    raw_mode = log.ask("TRMD?")
    mode = parse_trigger_mode(raw_mode)
    trigger["mode"] = {
        "query": "TRMD?",
        "raw": raw_mode,
        "mode": mode,
        "status": "OBSERVED" if mode else "UNVERIFIED",
    }
    if mode is None:
        trigger["mode"]["reason"] = (
            "reply is not a bare documented trigger mode or the TRMD/:TRIGger:MODE header followed by one"
        )

    raw_type = log.ask(":TRIGger:TYPE?")
    type_token = parse_trigger_type(raw_type)
    trigger["type"] = {
        "query": ":TRIGger:TYPE?",
        "raw": raw_type,
        "type": type_token,
        "status": "OBSERVED" if type_token else "UNVERIFIED",
    }
    if type_token is None:
        trigger["type"]["reason"] = (
            "reply is not a bare documented trigger type or the :TRIGger:TYPE header followed by one"
        )

    edge_queries = (
        ("source", ":TRIGger:EDGE:SOURce?"),
        ("slope", ":TRIGger:EDGE:SLOPe?"),
        ("level", ":TRIGger:EDGE:LEVel?"),
    )
    if type_token == "EDGE":
        raw_source = log.ask(":TRIGger:EDGE:SOURce?")
        source = parse_trigger_source(raw_source)
        trigger["source"] = {
            "query": ":TRIGger:EDGE:SOURce?",
            "raw": raw_source,
            "source": source,
            "status": "OBSERVED" if source else "UNVERIFIED",
        }
        if source is None:
            trigger["source"]["reason"] = "reply is not a documented edge-trigger source"

        raw_slope = log.ask(":TRIGger:EDGE:SLOPe?")
        slope = parse_trigger_slope(raw_slope)
        trigger["slope"] = {
            "query": ":TRIGger:EDGE:SLOPe?",
            "raw": raw_slope,
            "slope": slope,
            "status": "OBSERVED" if slope else "UNVERIFIED",
        }
        if slope is None:
            trigger["slope"]["reason"] = "reply is not RISing, FALLing, or ALTernate"

        raw_level = log.ask(":TRIGger:EDGE:LEVel?")
        level, level_unit, echo = parse_scalar_reply(
            raw_level, allowed_echoes=TRIGGER_LEVEL_ECHOES
        )
        trigger["level"] = {
            "query": ":TRIGger:EDGE:LEVel?",
            "raw": raw_level,
            "value": level,
            "unit": level_unit,
            "status": "OBSERVED" if level is not None else "UNVERIFIED",
        }
        if echo:
            trigger["level"]["echo"] = echo
        if level is None:
            trigger["level"]["reason"] = "reply is not a finite bare NR3 or the edge-level header followed by one"
    elif type_token is not None:
        reason = f"trigger type is {type_token}; EDGE source/slope/level do not apply"
        for key, query in edge_queries:
            trigger[key] = {
                "query": query,
                "raw": None,
                "value": None,
                "status": "NOT_APPLICABLE",
                "reason": reason,
            }
    else:
        reason = "trigger type is unreadable; EDGE applicability is not established, so no EDGE field was queried"
        for key, query in edge_queries:
            trigger[key] = {
                "query": query,
                "raw": None,
                "value": None,
                "status": "UNVERIFIED",
                "reason": reason,
            }


def _channel_limit_reason(model: Optional[str], count: int, count_source: str, channel: str) -> str:
    return (
        f"model {model!r} is established as {count}-channel by {count_source}; "
        f"{channel} is not addressed and was not queried"
    )


def _visual_context_not_captured() -> dict:
    return {
        "status": "NOT_CAPTURED",
        "qualitative_only": True,
        "reason": VISUAL_NOT_CAPTURED_REASON,
    }


def _capture_visual_context(scope, log: QueryLog, screenshot_path) -> dict:
    """Capture the optional PNG last, or record why it was not attempted."""

    if screenshot_path is None:
        return _visual_context_not_captured()
    raw_path = Path(screenshot_path)
    metadata_path = raw_path.with_suffix(raw_path.suffix + ".json")
    if log.failure is not None:
        return {
            "status": "NOT_ATTEMPTED",
            "qualitative_only": True,
            "raw_path": str(raw_path),
            "metadata_path": str(metadata_path),
            "reason": (
                "not attempted: an earlier transport or protocol failure stopped this session; "
                "no screenshot query was sent"
            ),
        }
    try:
        record = capture_png_on_session(scope, raw_path, metadata_path)
    except Exception as exc:  # artifact or transport problems must not erase channel evidence
        return {
            "status": "INCOMPLETE",
            "qualitative_only": True,
            "raw_path": str(raw_path),
            "metadata_path": str(metadata_path),
            "error": f"{type(exc).__name__}: {exc}",
            "reason": VISUAL_QUALITATIVE_REASON,
        }
    return {
        "status": record.get("status"),
        "qualitative_only": True,
        "reason": VISUAL_QUALITATIVE_REASON,
        "raw_path": record.get("raw_path"),
        "metadata_path": record.get("metadata_path"),
        "sha256": record.get("sha256"),
        "raw_bytes": record.get("raw_bytes"),
        "container_valid": record.get("container_valid"),
        "image_decode_status": record.get("image_decode_status"),
        "frame_association": record.get("frame_association"),
    }


def _snapshot_command(host: Optional[str], channels, extra: str = "") -> str:
    host_text = host or "<host>"
    channel_text = " ".join(channels) if channels else "C1"
    command = f"python3 scripts/channel_snapshot.py --host {host_text} --channels {channel_text}"
    return f"{command} {extra}".strip()


def build_next_actions(snapshot: dict, *, host: Optional[str] = None) -> list[dict]:
    """Return ordered, de-duplicated, executable follow-up suggestions."""

    actions: list[dict] = []
    seen: set[str] = set()
    rows = snapshot.get("channels") or {}
    channels = list(snapshot.get("requested_channels") or [])

    def add(action: str, message: str, command: Optional[str] = None) -> None:
        if action in seen:
            return
        seen.add(action)
        item = {"action": action, "message": message}
        if command:
            item["command"] = command
        actions.append(item)

    def probes_with(status: str) -> list[str]:
        return [
            channel
            for channel, row in rows.items()
            if (row.get("sample_probe") or {}).get("status") == status
        ]

    def probes_with_hint(hint: str) -> list[str]:
        return [
            channel
            for channel, row in rows.items()
            if (row.get("sample_probe") or {}).get("activity_hint") == hint
        ]

    live = probes_with("LIVE_NOT_STOPPED")
    if live:
        add(
            "CAPTURE_SINGLE_SHOT_FRAME",
            f"{', '.join(live)}: sample probe status LIVE_NOT_STOPPED (SAST? was not Stop), so "
            "no sample probe ran. Capture a single-shot frame and rerun this snapshot before "
            "concluding anything about these channels.",
            _snapshot_command(host, live, "--out-dir <dir>"),
        )

    clipped = probes_with_hint("CLIPPED")
    if clipped:
        add(
            "ADJUST_VDIV_AND_RECAPTURE",
            f"{', '.join(clipped)}: sample probe activity_hint CLIPPED; transfer codes touched "
            "the signed full-scale boundary, so the waveform may be clipped. Increase V/div until "
            "the trace fits, capture a new frame, and rerun this snapshot.",
            _snapshot_command(host, clipped, "--out-dir <dir>"),
        )

    partial_flat = probes_with_hint("FLAT_IN_SAMPLED_SLICES_ONLY")
    if partial_flat:
        add(
            "DO_NOT_CONCLUDE_NO_SIGNAL",
            f"{', '.join(partial_flat)}: sample probe activity_hint FLAT_IN_SAMPLED_SLICES_ONLY "
            "(coverage_mode PARTIAL_SLICES). A pulse may lie outside those three slices, so do not "
            "treat this as an absence-of-signal finding. Add --screenshot for full-screen shape, "
            "read the full record with scripts/capture_scope.py --existing-stopped, or change the "
            "timebase and recapture.",
            f"python3 scripts/capture_scope.py --host {host or '<host>'} --out <capture-dir> "
            f"--existing-stopped --channels {' '.join(partial_flat)}",
        )

    flat_full = probes_with_hint("FLAT_IN_FULL_RECORD")
    pkpk_zero = [
        channel
        for channel, row in rows.items()
        if ((row.get("measurement") or {}).get("pkpk") or {}).get("status") == "OBSERVED"
        and ((row.get("measurement") or {}).get("pkpk") or {}).get("value") == 0
    ]
    if flat_full or pkpk_zero:
        affected = sorted(set(flat_full) | set(pkpk_zero))
        add(
            "RUN_APPARENT_ZERO_TRIAGE",
            f"{', '.join(affected)}: activity_hint FLAT_IN_FULL_RECORD or PKPK == 0 is a finding, "
            "not a diagnosis. Run the apparent-zero triage (channel switch, coupling, V/div range, "
            "probe ground on the same board) and take a second independent observation; never call "
            "the channel undriven from one snapshot.",
            _snapshot_command(host, affected, "--out-dir <dir>"),
        )

    visual = snapshot.get("visual_context") or {}
    if visual.get("status") == "NOT_CAPTURED" and rows and snapshot.get("transport_failure") is None:
        add(
            "CAPTURE_SCREENSHOT_FOR_VISUAL_CONTEXT",
            "The snapshot has numeric readings only; waveform shape, ringing, and the full-screen "
            "overview were not inspected. Rerun with --screenshot <png> or --out-dir <dir> and "
            "treat the image as qualitative context only.",
            _snapshot_command(host, channels, "--out-dir <dir>"),
        )

    channel_off = probes_with("CHANNEL_OFF")
    if channel_off:
        add(
            "ENABLE_CHANNEL_AND_RECAPTURE",
            f"{', '.join(channel_off)}: sample probe status CHANNEL_OFF; the channel switch is OFF. "
            "Enable it and capture a new frame if a signal is expected there.",
            _snapshot_command(host, channel_off, "--out-dir <dir>"),
        )

    strict = probes_with("SKIPPED_STRICT_READONLY")
    if strict:
        add(
            "RERUN_WITHOUT_STRICT_READONLY",
            f"{', '.join(strict)}: sample probe status SKIPPED_STRICT_READONLY; --strict-readonly "
            "disabled the sample probe to guarantee a 0-write session. Rerun without it on a "
            "stopped frame to read bounded samples.",
            _snapshot_command(host, strict, "--out-dir <dir>"),
        )

    return actions


def _attach_visual_and_actions(
    snapshot: dict,
    scope,
    log: QueryLog,
    *,
    screenshot_path,
    host: Optional[str],
    strict_readonly: bool,
) -> None:
    snapshot["visual_context"] = _capture_visual_context(scope, log, screenshot_path)
    snapshot["next_actions"] = build_next_actions(snapshot, host=host)
    snapshot["strict_readonly"] = strict_readonly
    snapshot["read_only"] = not any(entry.get("write") for entry in log.entries)
    snapshot["writes"] = [entry["query"] for entry in log.entries if entry.get("write")]


def build_snapshot(
    scope,
    channels,
    *,
    declared_channel_count: Optional[int] = None,
    metrics=DEFAULT_METRICS,
    strict_readonly: bool = False,
    slice_points: int = DEFAULT_SLICE_POINTS,
    screenshot_path=None,
    host: Optional[str] = None,
) -> dict:
    """Read one context snapshot, one row per requested channel, and bounded samples."""

    if isinstance(slice_points, bool) or not isinstance(slice_points, int) or slice_points <= 0:
        raise ValueError("slice_points must be a positive integer")
    requested = [str(channel).upper() for channel in channels]
    log = QueryLog(lambda command: scope.query_ascii(command, allow_after_stop=True), scope=scope)
    snapshot: dict = {
        "schema": SCHEMA,
        "generated_at": _utc_now(),
        "read_only": True,
        "requested_channels": requested,
        "instrument": None,
        "acquisition": None,
        "horizontal": None,
        "trigger": None,
        "channels": {},
        "queries": log.entries,
        "transport_failure": None,
        "limits": {
            "no_signal_verdict": "NOT_SUPPORTED_BY_THIS_SNAPSHOT",
            "screenshot": (
                "optional qualitative image; it may only describe shape, ringing, and full-screen "
                "context, never per-channel presence or absence"
            ),
            "sample_probe": (
                "WAV samples are read only on a stopped frame with the channel switch ON; coverage_mode "
                "states whether the whole record or three non-overlapping slices were read. A flat "
                "PARTIAL_SLICES result is not evidence that the channel is undriven."
            ),
            "same_frame": "channel rows are sequential reads; values in one snapshot are not proven to come from one frame",
            "measurement_source": "one :MEASure:SIMPle source at a time; only the channel whose before/after source readback matches receives numeric values",
            "status_semantics": (
                "status describes the snapshot command flow: COMPLETE means every planned query returned a "
                "reply (including ***/error text), not that every channel has usable evidence. "
                "evidence_status describes whether at least one channel received a usable V/A measurement; "
                "an all-*** snapshot is COMPLETE/UNVERIFIED, never zero."
            ),
        },
    }
    try:
        idn_raw = log.ask("*IDN?")
    except SnapshotAborted:
        snapshot["instrument"] = {"idn_raw": None, "model": None, "channel_count": None, "channel_count_source": "unknown"}
        for channel in requested:
            snapshot["channels"][channel] = {
                "channel": channel,
                "requested": True,
                "status": "NOT_ATTEMPTED",
                "reason": "not read: *IDN? hit a transport failure",
            }
        snapshot["transport_failure"] = log.failure
        snapshot["status"] = "INCOMPLETE"
        snapshot["evidence_status"] = "INCOMPLETE"
        _attach_visual_and_actions(
            snapshot,
            scope,
            log,
            screenshot_path=screenshot_path,
            host=host,
            strict_readonly=strict_readonly,
        )
        return snapshot

    instrument = parse_idn(idn_raw)
    count, count_source = resolve_channel_count(instrument["model"], declared_channel_count)
    instrument["channel_count"] = count
    instrument["channel_count_source"] = count_source
    snapshot["instrument"] = instrument
    if count is None:
        for channel in requested:
            snapshot["channels"][channel] = {
                "channel": channel,
                "requested": True,
                "status": "UNSUPPORTED",
                "reason": (
                    "the model's channel count is not established by this Skill's evidence; "
                    "no channel was queried. Pass --model-channels 2 or 4 only when the instrument's "
                    "channel count is independently confirmed"
                ),
            }
        snapshot["status"] = "UNSUPPORTED"
        snapshot["evidence_status"] = "UNSUPPORTED"
        _attach_visual_and_actions(
            snapshot,
            scope,
            log,
            screenshot_path=screenshot_path,
            host=host,
            strict_readonly=strict_readonly,
        )
        return snapshot

    try:
        _read_acquisition(log, snapshot)
        for channel in requested:
            row: dict = {"channel": channel, "requested": True}
            snapshot["channels"][channel] = row
            if int(channel[1]) > count:
                row["status"] = "UNSUPPORTED"
                row["reason"] = _channel_limit_reason(instrument["model"], count, count_source, channel)
                continue
            _read_channel_row(log, channel, row)
            row["status"] = "OBSERVED"
        channel_units = {
            channel: snapshot["channels"][channel].get("unit")
            for channel in requested
            if snapshot["channels"][channel].get("status") != "UNSUPPORTED"
        }
        block = read_measurement_block(log, metrics, channel_units)
        snapshot["measurement"] = block
        attributed = attribute_measurements(block, requested)
        for channel in requested:
            row = snapshot["channels"][channel]
            if row.get("status") == "UNSUPPORTED":
                continue
            row["measurement"] = attributed[channel]
            row["triage"] = build_triage(row, row["measurement"])
        run_sample_probes(
            scope,
            log,
            snapshot,
            strict_readonly=strict_readonly,
            slice_points=slice_points,
        )
    except SnapshotAborted:
        pass

    snapshot["transport_failure"] = log.failure
    for channel in requested:
        row = snapshot["channels"].get(channel)
        if row is None:
            snapshot["channels"][channel] = {
                "channel": channel,
                "requested": True,
                "status": "NOT_ATTEMPTED",
                "reason": "not read: an earlier transport failure stopped this read-only session",
            }
            continue
        if row.get("status") == "UNSUPPORTED":
            continue
        _finalize_channel_row(row, channel)
        if "measurement" not in row:
            row["measurement"] = {
                "status": "INCOMPLETE",
                "query_status": "INCOMPLETE",
                "evidence_status": "UNVERIFIED",
                "reason": "not read: an earlier transport failure stopped this read-only session",
            }
        if "sample_probe" not in row:
            row["sample_probe"] = _sample_probe_entry(
                channel,
                status="NOT_ATTEMPTED",
                reason="not attempted: an earlier transport or protocol failure stopped this session",
            )
    unsupported = any(row.get("status") == "UNSUPPORTED" for row in snapshot["channels"].values())
    if log.failure is not None or unsupported:
        snapshot["status"] = "INCOMPLETE"
    else:
        snapshot["status"] = "COMPLETE"
    measurements = [
        row.get("measurement") for row in snapshot["channels"].values() if isinstance(row.get("measurement"), dict)
    ]
    if any(measurement.get("status") == "OBSERVED" for measurement in measurements):
        snapshot["evidence_status"] = "OBSERVED"
    elif log.failure is not None or unsupported:
        snapshot["evidence_status"] = "INCOMPLETE"
    else:
        snapshot["evidence_status"] = "UNVERIFIED"
    _attach_visual_and_actions(
        snapshot,
        scope,
        log,
        screenshot_path=screenshot_path,
        host=host,
        strict_readonly=strict_readonly,
    )
    return snapshot


def _format_entry(label: str, entry: dict) -> str:
    parts = [f"{label}: {entry.get('status')}"]
    for key in ("state", "value", "unit", "reply_unit"):
        if key in entry and entry[key] is not None:
            parts.append(f"{key}={entry[key]!r}" if key == "value" else f"{key}={entry[key]}")
    if "raw" in entry:
        parts.append(f"raw={entry.get('raw')!r}")
    if entry.get("query"):
        parts.append(f"query={entry['query']!r}")
    if entry.get("reason"):
        parts.append(f"reason={entry['reason']!r}")
    if entry.get("zero_semantics"):
        parts.append(f"zero={entry['zero_semantics']!r}")
    return "  " + " ".join(parts)


def format_table(snapshot: dict) -> str:
    lines: list[str] = []
    instrument = snapshot.get("instrument") or {}
    lines.append(
        f"instrument: model={instrument.get('model')!r} firmware={instrument.get('firmware')!r} "
        f"channel_count={instrument.get('channel_count')} ({instrument.get('channel_count_source')})"
    )
    acquisition = snapshot.get("acquisition") or {}
    if acquisition:
        lines.append(
            f"acquisition: SAST? raw={acquisition.get('raw')!r} state={acquisition.get('state')} — {acquisition.get('meaning')}"
        )
    horizontal = snapshot.get("horizontal") or {}
    if horizontal:
        fields = []
        for key in ("timebase", "sample_rate", "record_points"):
            entry = horizontal.get(key)
            if entry:
                fields.append(f"{key}={entry.get('raw')!r} [{entry.get('status')}]")
        lines.append("horizontal: " + "  ".join(fields))
    trigger = snapshot.get("trigger") or {}
    if trigger:
        fields = []
        for key in ("mode", "type", "source", "slope", "level"):
            entry = trigger.get(key)
            if entry:
                fields.append(f"{key}={entry.get('raw')!r} [{entry.get('status')}]")
        lines.append("trigger: " + "  ".join(fields))
    lines.append(
        f"write policy: read_only={snapshot.get('read_only')} strict_readonly={snapshot.get('strict_readonly')} "
        f"writes={len(snapshot.get('writes') or [])} (only WAV transfer-selection writes when not strict)"
    )
    for channel, row in (snapshot.get("channels") or {}).items():
        measurement = row.get("measurement") or {}
        lines.append(
            f"{channel}: channel_reads={row.get('status')} evidence={measurement.get('status')} "
            f"query_flow={measurement.get('query_status')}"
        )
        if row.get("reason"):
            lines.append(f"  reason: {row['reason']!r}")
        for key in ("switch", "unit", "vdiv", "offset", "coupling"):
            if key in row:
                lines.append(_format_entry(key, row[key]))
        source = measurement.get("source")
        lines.append(
            f"  measurement: source={source!r} source_stable={measurement.get('source_stable')} "
            f"attribution={measurement.get('source_attribution')} "
            f"status={measurement.get('status')} query_status={measurement.get('query_status')}"
        )
        for metric, entry in measurement.items():
            if isinstance(entry, dict) and metric in ("pkpk", "max", "min", "top", "base"):
                lines.append(_format_entry(metric.upper(), entry))
        if measurement.get("reason"):
            lines.append(f"  measurement reason: {measurement['reason']!r}")
        triage = row.get("triage")
        if triage:
            lines.append(f"  triage: conclusion={triage.get('conclusion')}")
            for cause in triage.get("causes", []):
                lines.append(f"    - {cause.get('cause')}: {cause.get('status')}")
            if triage.get("next_step"):
                lines.append(f"    next: {triage['next_step']}")
        probe = row.get("sample_probe")
        if probe:
            lines.append(
                f"  sample_probe: status={probe.get('status')} activity_hint={probe.get('activity_hint')} "
                f"coverage_mode={probe.get('coverage_mode')} sampled_points={probe.get('sampled_points')}/"
                f"total_points={probe.get('total_points')} coverage_ratio={probe.get('coverage_ratio')} "
                f"clipped={probe.get('clipped')} codes=[{probe.get('code_min')},{probe.get('code_max')}]"
            )
            if probe.get("total_points_authority"):
                lines.append(f"    total_points_authority: {probe['total_points_authority']}")
            for slice_entry in probe.get("slices") or []:
                if slice_entry.get("points"):
                    lines.append(
                        f"    slice [{slice_entry.get('start')},{slice_entry.get('end_exclusive')}) "
                        f"points={slice_entry.get('points')} codes=[{slice_entry.get('code_min')},"
                        f"{slice_entry.get('code_max')}]"
                    )
            if probe.get("reason"):
                lines.append(f"    reason: {probe['reason']!r}")
    failure = snapshot.get("transport_failure")
    if failure:
        lines.append(f"transport failure: query={failure.get('query')!r} error={failure.get('error')!r}")
        lines.append("  no later query was sent; no reconnect was attempted")
    visual = snapshot.get("visual_context") or {}
    if visual:
        lines.append(
            f"visual_context: status={visual.get('status')} qualitative_only={visual.get('qualitative_only')} "
            f"reason={visual.get('reason')!r}"
        )
        if visual.get("raw_path"):
            lines.append(f"  raw_path: {visual.get('raw_path')!r}")
        if visual.get("status") in ("INCOMPLETE", "INVALID") and visual.get("error"):
            lines.append(f"  error: {visual['error']!r}")
    actions = snapshot.get("next_actions") or []
    if actions:
        lines.append("next_actions:")
        for index, action in enumerate(actions, 1):
            lines.append(f"  {index}. {action.get('action')}: {action.get('message')}")
            if action.get("command"):
                lines.append(f"     command: {action['command']}")
    lines.append(
        f"snapshot status: {snapshot.get('status')} (query flow); evidence: {snapshot.get('evidence_status')}"
    )
    return "\n".join(lines)


def _emit(snapshot: dict, args) -> None:
    if args.out is not None:
        save_json(args.out, snapshot)
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(format_table(snapshot))


def _positive_finite_timeout(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number of seconds")
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return number


def _scpi_port(value: str) -> int:
    port = int(value)
    if port == 5024:
        raise argparse.ArgumentTypeError(
            "port 5024 is the legacy shell channel, not a SCPI query channel; use 5025"
        )
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be in 1..65535")
    return port


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="explicit instrument host or IP (no default target)")
    parser.add_argument("--port", type=_scpi_port, default=5025)
    parser.add_argument("--timeout", type=_positive_finite_timeout, default=10.0)
    parser.add_argument("--channels", nargs="+", choices=CHANNELS, required=True, help="explicit channel list, e.g. --channels C1 C2")
    parser.add_argument("--model-channels", type=int, choices=(2, 4), default=None, help="caller-confirmed model channel count; overrides the conservative model inference")
    parser.add_argument("--out", type=Path, default=None, help="write the machine-readable JSON snapshot to this path")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="write <dir>/snapshot.json and <dir>/screen.png; cannot be combined with --out or --screenshot",
    )
    parser.add_argument(
        "--strict-readonly",
        action="store_true",
        help="send queries only: disable the WAV transfer-selection writes used by the sample probe",
    )
    parser.add_argument(
        "--slice-points",
        type=_positive_int,
        default=DEFAULT_SLICE_POINTS,
        help=f"points per sample slice (default {DEFAULT_SLICE_POINTS}); capped by WAV:MAXP? and by the record length",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=None,
        help="capture one PNG on the same session after every query and sample probe",
    )
    parser.add_argument("--json", action="store_true", help="print the JSON snapshot instead of the per-channel table")
    args = parser.parse_args(argv)
    if args.out_dir is not None:
        if args.out is not None or args.screenshot is not None:
            parser.error("--out-dir cannot be combined with --out or --screenshot; it sets both paths")
        args.out = args.out_dir / "snapshot.json"
        args.screenshot = args.out_dir / "screen.png"
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    session = {"host": args.host, "port": args.port, "timeout_s": args.timeout}
    scope = ScopeSession(args.host, args.port, args.timeout)
    try:
        try:
            scope.connect()
        except OSError as exc:
            visual_context = (
                {
                    "status": "NOT_ATTEMPTED",
                    "qualitative_only": True,
                    "raw_path": str(args.screenshot),
                    "metadata_path": str(args.screenshot.with_suffix(args.screenshot.suffix + ".json")),
                    "reason": "not attempted: the TCP connection failed before any query or screenshot",
                }
                if args.screenshot is not None
                else _visual_context_not_captured()
            )
            snapshot = {
                "schema": SCHEMA,
                "generated_at": _utc_now(),
                "read_only": True,
                "strict_readonly": args.strict_readonly,
                "writes": [],
                "status": "INCOMPLETE",
                "evidence_status": "INCOMPLETE",
                "error": f"{type(exc).__name__}: {exc}",
                "transport_failure": {"query": None, "error": f"{type(exc).__name__}: {exc}"},
                "requested_channels": [channel.upper() for channel in args.channels],
                "channels": {},
                "visual_context": visual_context,
                "next_actions": [],
                "session": session,
            }
            _emit(snapshot, args)
            return 2
        snapshot = build_snapshot(
            scope,
            args.channels,
            declared_channel_count=args.model_channels,
            strict_readonly=args.strict_readonly,
            slice_points=args.slice_points,
            screenshot_path=args.screenshot,
            host=args.host,
        )
        snapshot["session"] = session
        _emit(snapshot, args)
        return 0 if snapshot["status"] == "COMPLETE" else 2
    finally:
        scope.close()


if __name__ == "__main__":
    raise SystemExit(main())
