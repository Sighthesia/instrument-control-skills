#!/usr/bin/env python3
"""Opt-in live transport for the RIGOL DS1000Z series over raw TCP (port 5555).

The module is the only place in this Skill that imports ``socket``. It is
read-only by default: every command that changes instrument state needs
``--allow-writes``, and ``*RST``, ``*SAV``, ``*RCL``, ``:SAVE``, ``:RECAll``,
``:LAN:*`` and the panel lock are refused even then. ``--dry-run`` prints the
exact bytes that would be written and never opens a socket.

Wire rules from the bench instrument (DS1074Z, firmware 00.04.02.SP4):

* One command per write. A single write carrying two commands is answered for
  the first command only; the rest are dropped without an error.
* Every command ends with LF. Writes return nothing, so allow ~0.3-0.4 s before
  the next command on the same socket.
* Reads end at an idle timeout, not at LF: an undefined command header answers
  the literal ``command error`` (13 bytes, no terminator).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds1000z_protocol import (  # noqa: E402
    COMMAND_ERROR,
    CURSOR_COMMANDS,
    CURSOR_FAMILY_QUERIES,
    CURSOR_MODE_FAMILIES,
    MAX_INLINE_RAW_BYTES,
    MEASUREMENT_COMMANDS,
    ProtocolError,
    export_waveform_bundle,
    is_command_error,
    parse_cursor_readout,
    parse_error_queue,
    parse_identity,
    parse_ieee_block,
    parse_measurement,
    parse_preamble,
    parse_screenshot,
    parse_waveform,
)

DEFAULT_PORT = 5555
DEFAULT_TIMEOUT = 10.0
DEFAULT_IDLE_TIMEOUT = 0.3
DEFAULT_BLOCK_TIMEOUT = 60.0
# Measured: writes (:STOP, :WAVeform:MODE, ...) return nothing; 0.3-0.4 s is
# enough for the instrument to be ready for the next command.
DEFAULT_WRITE_DELAY = 0.35
# Measured: :CURSor:MODE is a silent write that also lengthens the response
# delay, so 0.4 s is not enough. A query sent after only 0.4 s can come back
# empty and the late reply is then read as the answer to the next command.
CURSOR_MODE_SETTLE_DELAY = 1.0
# Write spellings for the cursor modes; the read-back is the short form (TRAC).
CURSOR_MODE_WRITE_FORMS = {
    "OFF": "OFF",
    "MAN": "MANual",
    "MANUAL": "MANual",
    "TRAC": "TRACk",
    "TRACK": "TRACk",
    "AUTO": "AUTO",
    "XY": "XY",
}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Documented trigger states that mean "the acquisition is running". Any other
# observed value (:STOP, :SINGle completed) must be restored with :STOP.
RUNNING_TRIGGER_STATES = {"TD", "WAIT", "RUN", "AUTO", "T'D"}

# Always refused, even with --allow-writes: destructive, network, or panel lock.
# Both the long and the short form of the panel lock are listed because the
# instrument accepts either spelling.
FORBIDDEN_COMMANDS = (
    "*RST",
    "*SAV",
    "*RCL",
    ":SAVE",
    ":RECA",
    ":LAN:",
    ":SYSTEM:KEY:LOCK",
    ":SYST:KEY:LOCK",
)

CAPTURE_QUANTITIES = ("vpp", "vmax", "vmin", "vavg", "vrms", "frequency", "period", "pduty")

STATUS_PRECEDENCE = ("INVALID", "INCOMPLETE", "UNSUPPORTED", "UNVERIFIED", "COMPLETE")


class SessionError(RuntimeError):
    """A transport, state, or file-safety failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _header(command: str) -> str:
    return " ".join(command.strip().upper().split())


def forbidden_reason(command: str) -> str | None:
    """Return the refused prefix when a command is always unsafe."""

    header = _header(command)
    for prefix in FORBIDDEN_COMMANDS:
        if header.startswith(prefix):
            return prefix
        if prefix.startswith(":") and header.startswith(prefix[1:]):
            return prefix
    return None


def _encode_command(command: str | bytes) -> bytes:
    """Encode exactly one LF-terminated command."""

    if isinstance(command, str):
        try:
            data = command.encode("ascii")
        except UnicodeEncodeError as exc:
            raise SessionError("commands must be ASCII") from exc
    elif isinstance(command, (bytes, bytearray)):
        data = bytes(command)
    else:
        raise SessionError("command must be str or bytes")
    if data.endswith(b"\r\n"):
        data = data[:-2]
    elif data.endswith((b"\n", b"\r")):
        data = data[:-1]
    if b"\n" in data or b"\r" in data:
        raise SessionError(
            "one command per write: the instrument answers only the first command of a multi-command write"
        )
    if not data.strip():
        raise SessionError("command is empty")
    return data + b"\n"


def _block_total(data: bytes) -> int | None:
    """Total block bytes (# + digits + declared payload) or None if incomplete."""

    if len(data) < 2 or data[:1] != b"#" or not data[1:2].isdigit():
        return None
    digits = int(data[1:2])
    if digits == 0 or len(data) < 2 + digits:
        return None
    length_text = data[2 : 2 + digits]
    if not length_text.isdigit():
        return None
    return 2 + digits + int(length_text)


class Session:
    """One raw TCP session with byte-exact reads and dry-run support."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        block_timeout: float = DEFAULT_BLOCK_TIMEOUT,
        write_delay: float = DEFAULT_WRITE_DELAY,
        cursor_settle_delay: float = CURSOR_MODE_SETTLE_DELAY,
        dry_run: bool = False,
        allow_writes: bool = False,
        empty_retries: int = 1,
    ) -> None:
        if isinstance(port, bool) or not 1 <= int(port) <= 65535:
            raise SessionError("TCP port must be in 1..65535")
        if timeout <= 0 or idle_timeout <= 0 or block_timeout <= 0:
            raise SessionError("timeouts must be positive")
        if write_delay < 0:
            raise SessionError("write delay must not be negative")
        if cursor_settle_delay < 0:
            raise SessionError("cursor settle delay must not be negative")
        if empty_retries < 0:
            raise SessionError("empty retry budget must not be negative")
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.block_timeout = block_timeout
        self.write_delay = write_delay
        self.cursor_settle_delay = cursor_settle_delay
        self.dry_run = dry_run
        self.allow_writes = allow_writes
        self.empty_retries = empty_retries
        self.empty_reply_retries = 0
        self.sent: list[bytes] = []
        self._connection = None

    # -- transport ---------------------------------------------------------

    def _open(self) -> None:
        if self._connection is not None or self.dry_run:
            return
        if not self.host:
            raise SessionError("--host is required unless --dry-run is used")
        try:
            self._connection = socket.create_connection((self.host, self.port), self.timeout)
        except OSError as exc:
            raise SessionError(f"cannot connect to {self.host}:{self.port}: {exc}") from exc
        self._connection.settimeout(self.idle_timeout)

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except OSError:  # pragma: no cover - close errors are not actionable
                pass
            self._connection = None

    def send(self, command: str | bytes) -> None:
        """Write exactly one LF-terminated command (no read)."""

        payload = _encode_command(command)
        refused = forbidden_reason(payload.decode("ascii"))
        if refused is not None:
            raise SessionError(f"refusing {refused}: this command is never sent by this Skill")
        self.sent.append(payload)
        if self.dry_run:
            print(f"DRY-RUN SEND: {payload!r}")
            return
        self._open()
        assert self._connection is not None
        try:
            self._connection.sendall(payload)
        except OSError as exc:
            raise SessionError(f"write failed: {exc}") from exc
        if not payload.rstrip().endswith(b"?"):
            time.sleep(self.write_delay)

    def write(self, command: str | bytes) -> None:
        """Send a state-changing command; requires --allow-writes."""

        if _encode_command(command).rstrip().endswith(b"?"):
            raise SessionError("write() takes a state-changing command, not a query")
        if not self.allow_writes:
            raise SessionError(f"refusing write {command!r} without --allow-writes")
        self.send(command)

    def _read(
        self, *, complete, overall_timeout: float, idle_ends_read: bool = True
    ) -> bytes:
        self._open()
        if self.dry_run or self._connection is None:
            return b""
        buffer = bytearray()
        deadline = time.monotonic() + overall_timeout
        while time.monotonic() < deadline:
            try:
                chunk = self._connection.recv(65536)
            except socket.timeout:
                # A definite-length block keeps arriving in bursts with gaps
                # longer than the text idle timeout (the bench unit paused after
                # about 50 KiB), so only an overall deadline ends a block read.
                # A line reply has no length, so its idle timeout is the frame
                # terminator.
                if idle_ends_read:
                    break
                continue
            except OSError as exc:
                raise SessionError(f"read failed: {exc}") from exc
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > MAX_RESPONSE_BYTES:
                raise SessionError("response exceeds the size limit")
            if complete(bytes(buffer)):
                break
        return bytes(buffer)

    def query_text(self, command: str) -> bytes:
        """Send one query and read until LF or the idle timeout.

        ``command error`` has no terminator, so the idle timeout is the only
        terminator for that reply; the bytes are returned unmodified.

        Measured: the instrument occasionally drops a query and answers with 0
        bytes (seen on `:TRIGger:STATus?` right after `:RUN` and on
        `:CHANnel1:SCALe?`). Queries are idempotent, so an empty reply is
        re-sent up to ``empty_retries`` times before it is reported. Writes are
        never retried.
        """

        for attempt in range(self.empty_retries + 1):
            self.send(command)
            raw = self._read(
                complete=lambda data: data.endswith(b"\n"), overall_timeout=self.timeout
            )
            if raw or self.dry_run:
                return raw
            if attempt < self.empty_retries:
                self.empty_reply_retries += 1
                if self.write_delay:
                    time.sleep(self.write_delay)
        return b""

    def discard_pending(self, *, budget: float = 0.05) -> int:
        """Drop bytes that arrived without a query waiting for them.

        Measured: :CURSor:MODE is a silent write whose reply can arrive late;
        a reader that sends the next query too early then reads that late reply
        as the answer to the new command. The cursor path settles, then clears
        the socket, then queries. Returns the number of bytes discarded.
        """

        if self.dry_run or self._connection is None:
            return 0
        self._connection.settimeout(budget)
        dropped = 0
        try:
            while True:
                try:
                    chunk = self._connection.recv(65536)
                except socket.timeout:
                    break
                except OSError as exc:
                    raise SessionError(f"read failed: {exc}") from exc
                if not chunk:
                    break
                dropped += len(chunk)
        finally:
            self._connection.settimeout(self.idle_timeout)
        return dropped

    def query_block(self, command: str) -> bytes:
        """Send one query and read a complete IEEE 488.2 block byte-exactly."""

        self.send(command)

        def complete(data: bytes) -> bool:
            total = _block_total(data)
            return total is not None and len(data) >= total and data.endswith(b"\n")

        return self._read(
            complete=complete,
            overall_timeout=self.block_timeout,
            idle_ends_read=False,
        )

    # -- instrument helpers ------------------------------------------------

    def status(self, command: str) -> str:
        return self.query_text(command).strip().decode("ascii", "replace")

    def drain_errors(self, *, limit: int = 16, emit=None) -> list[dict]:
        """Read the error queue until it reports ``0,"No error"``."""

        records: list[dict] = []
        for _ in range(limit):
            raw = self.query_text(":SYSTem:ERRor?")
            if self.dry_run:
                return records
            if is_command_error(raw):
                raise SessionError(f"error-queue query answered {COMMAND_ERROR!r}")
            record = parse_error_queue(raw)
            records.append(record)
            if emit is not None:
                emit(record)
            if record.get("code") == 0:
                return records
        records.append(
            {
                "status": "INCOMPLETE",
                "integrity": {"reasons": ["error_queue_not_empty_after_limit"]},
            }
        )
        return records


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def _bundle_stem(path: Path) -> str:
    """``<stem>.bundle.json`` and ``<stem>.json`` name the same bundle as ``<stem>``."""

    name = path.name
    for suffix in (".bundle.json", ".json"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def save_raw(path: Path, raw: bytes, *, overwrite: bool = False) -> dict:
    """Write raw bytes atomically and refuse to overwrite by default."""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise SessionError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return {
        "path": str(destination),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _raw_record(raw: bytes) -> dict:
    """Small raw-response record: hash always, inline bytes when small."""

    record: dict = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if len(raw) <= MAX_INLINE_RAW_BYTES:
        record["repr"] = repr(raw)
        record["base64"] = base64.b64encode(raw).decode("ascii")
    else:
        record["repr"] = None
        record["base64"] = None
    return record


def _check(name: str, status: str, evidence: dict | None = None) -> dict:
    return {"name": name, "status": status, "evidence": evidence or {}}


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _require_channel(channel: int) -> int:
    if isinstance(channel, bool) or channel not in {1, 2, 3, 4}:
        raise SessionError("channel must be 1, 2, 3, or 4")
    return channel


# ---------------------------------------------------------------------------
# Read-only subcommands
# ---------------------------------------------------------------------------


def cmd_identity(session: Session) -> int:
    raw = session.query_text("*IDN?")
    if session.dry_run:
        return 0
    result = parse_identity(raw)
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_errors(session: Session, *, drain: bool = False) -> int:
    if not drain:
        raw = session.query_text(":SYSTem:ERRor?")
        if session.dry_run:
            return 0
        result = parse_error_queue(raw)
        _print_json(result)
        return 0 if result["status"] in {"COMPLETE", "UNVERIFIED"} else 1

    records = session.drain_errors(emit=_print_json)
    if session.dry_run:
        return 0
    return 0 if records and records[-1].get("code") == 0 else 1


def cmd_measurement(session: Session, quantity: str, channel: int | None = None) -> int:
    key = quantity.lower().strip()
    if key not in MEASUREMENT_COMMANDS:
        raise SessionError(f"unsupported measurement quantity {quantity!r}")
    if channel is not None:
        _require_channel(channel)
        session.write(f":MEASure:SOURce CHANnel{channel}")
    raw = session.query_text(MEASUREMENT_COMMANDS[key])
    if session.dry_run:
        return 0
    result = parse_measurement(raw, quantity=key)
    result["transport"] = {"command": MEASUREMENT_COMMANDS[key], "raw_sha256": hashlib.sha256(raw).hexdigest()}
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_preamble(session: Session) -> int:
    raw = session.query_text(":WAVeform:PREamble?")
    if session.dry_run:
        return 0
    result = parse_preamble(raw)
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def _cursor_family(mode: str) -> str | None:
    return CURSOR_MODE_FAMILIES.get(mode.strip().upper())


def cmd_cursor(
    session: Session,
    *,
    mode: str | None = None,
    out_raw: Path | None = None,
    overwrite: bool = False,
) -> int:
    """Read every cursor field of the active cursor family and report it.

    Read-only by default: one ``:CURSor:MODE?`` query decides which family is
    collected. ``--mode`` switches the family first, which needs
    ``--allow-writes``, and the previous mode is always written back. ``XY`` is
    refused because the bench firmware answers ``-200,"Execution error"`` and
    stays in its previous mode. Writes are silent, so the switch settles and
    then clears late bytes before the next query.
    """

    target: str | None = None
    if mode is not None:
        key = mode.strip().upper()
        if key not in CURSOR_MODE_WRITE_FORMS:
            raise SessionError(f"unknown cursor mode {mode!r}; use MAN, TRACk, or AUTO")
        if key == "XY":
            raise SessionError(
                "refusing :CURSor:MODE XY: the bench unit answers -200,\"Execution error\" and stays "
                "in its previous mode; XY cursors need :TIMebase:MODE XY and stay "
                "model/firmware-dependent"
            )
        if not session.allow_writes:
            raise SessionError(f"switching the cursor mode to {mode!r} needs --allow-writes")
        target = CURSOR_MODE_WRITE_FORMS[key]

    prior_raw = session.query_text(CURSOR_COMMANDS["mode"])
    prior_mode = prior_raw.decode("ascii", "replace").strip()

    if session.dry_run:
        if target is not None:
            session.write(f":CURSor:MODE {target}")
            families = [_cursor_family(target) or "manual"]
            print(
                "DRY-RUN NOTE: the cursor mode write is silent and lengthens the response "
                f"delay; the read waits {session.cursor_settle_delay:g} s and discards late bytes"
            )
        else:
            families = ["manual", "track", "auto", "xy"]
            print(
                "DRY-RUN NOTE: the family is whichever :CURSor:MODE? names, so the bytes "
                "below are the union of the four families; one family is sent live"
            )
        for family in families:
            for quantity in CURSOR_FAMILY_QUERIES[family]:
                session.send(CURSOR_COMMANDS[quantity])
        if target is not None:
            print(f"DRY-RUN NOTE: after the read :CURSor:MODE {prior_mode or '<read-back>'} is written back")
        return 0

    readings: dict[str, bytes] = {"mode": prior_raw}
    observed_mode = prior_mode
    switched = False
    restored_mode: str | None = None
    try:
        if target is not None:
            session.write(f":CURSor:MODE {target}")
            switched = True
            if session.cursor_settle_delay:
                time.sleep(session.cursor_settle_delay)
            session.discard_pending()
            observed_mode = session.status(CURSOR_COMMANDS["mode"])
        family = _cursor_family(observed_mode)
        if family is not None:
            for quantity in CURSOR_FAMILY_QUERIES[family]:
                readings[quantity] = session.query_text(CURSOR_COMMANDS[quantity])
    finally:
        if switched:
            _restore_cursor_mode(session, {"cursor_mode": prior_mode})
            restored_mode = session.status(CURSOR_COMMANDS["mode"])

    result = parse_cursor_readout(observed_mode, readings)
    result["transport"] = {
        "host": session.host,
        "port": session.port,
        "raw_tcp": True,
        "captured_at": _utc_now(),
        "commands": [payload.decode("ascii", "replace").strip() for payload in session.sent],
        "empty_reply_retries": session.empty_reply_retries,
    }
    if switched:
        result["mode_restore"] = {
            "requested": target,
            "prior_mode": prior_mode,
            "observed_mode": observed_mode,
            "restored_mode": restored_mode,
            "status": "pass" if _cursor_family(restored_mode or "") == _cursor_family(prior_mode) else "fail",
        }
    if out_raw is not None:
        saved = {
            quantity: save_raw(Path(out_raw) / f"{quantity}.raw", raw, overwrite=overwrite)
            for quantity, raw in readings.items()
        }
        result["saved"] = saved
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def _restore_cursor_mode(session: Session, prior: dict) -> None:
    """Write the previous cursor mode back; the write is silent, so settle first."""

    mode = (prior.get("cursor_mode") or "").strip()
    if session.dry_run or not mode:
        return
    session.write(f":CURSor:MODE {CURSOR_MODE_WRITE_FORMS.get(mode.upper(), mode)}")
    if session.cursor_settle_delay:
        time.sleep(session.cursor_settle_delay)
    session.discard_pending()


def cmd_waveform(
    session: Session,
    *,
    out: Path,
    channel: int | None = None,
    mode: str | None = None,
    start: int | None = None,
    stop: int | None = None,
    overwrite: bool = False,
    bundle_out: Path | None = None,
) -> int:
    """Read one waveform block and save the bytes that the instruments sent.

    ``bundle_out`` additionally writes a ``waveform-bundle/v1`` document for the
    vendor-neutral analysis Skill; it is written only for a COMPLETE parse and
    its payload goes next to it as ``<name>.bin``.
    """

    if (start is None) != (stop is None):
        raise SessionError("--start and --stop must be given together")
    if start is not None and (start < 1 or stop < start):
        raise SessionError("waveform window must satisfy 1 <= start <= stop")
    if channel is not None:
        _require_channel(channel)

    prior = _acquire_context(session)
    state_changed = channel is not None or mode is not None or start is not None or stop is not None
    try:
        if channel is not None:
            session.write(f":WAVeform:SOURce CHANnel{channel}")
        if mode is not None or start is not None or stop is not None:
            _prepare_waveform_read(session, mode=mode, start=start, stop=stop, prior=prior)
        points_raw = session.query_text(":WAVeform:POINts?")
        preamble_raw = session.query_text(":WAVeform:PREamble?")
        data_raw = session.query_block(":WAVeform:DATA?")
        # A bundle names the model that produced its samples, so read the
        # identity only when one is asked for; a waveform read never needed it.
        identity_raw = session.query_text("*IDN?") if bundle_out is not None else None
    finally:
        if state_changed:
            _restore_acquire_context(session, prior)
    if session.dry_run:
        return 0

    saved = save_raw(Path(out), data_raw, overwrite=overwrite)
    result = parse_waveform(
        data_raw,
        preamble_raw=preamble_raw,
        window_start=start,
        window_stop=stop,
    )
    result["saved"] = saved
    result["transport"] = {
        "host": session.host,
        "port": session.port,
        "channel": channel,
        "requested_mode": mode,
        "window": [start, stop],
        "points_response": points_raw.decode("ascii", "replace").strip(),
        "preamble_sha256": hashlib.sha256(preamble_raw).hexdigest(),
        "data_sha256": saved["sha256"],
        "captured_at": _utc_now(),
    }
    if bundle_out is not None:
        if result["status"] == "COMPLETE":
            destination = Path(bundle_out)
            idn_text = (
                None if identity_raw is None else identity_raw.decode("ascii", "replace").strip()
            )
            result["bundle"] = export_waveform_bundle(
                data_raw,
                preamble_raw=preamble_raw,
                out_dir=destination.parent,
                name=_bundle_stem(destination),
                channel=channel,
                idn=idn_text,
                captured_at=result["transport"]["captured_at"],
                raw_file=Path(out),
                overwrite=overwrite,
            )
        else:
            result["bundle"] = {
                "written": False,
                "status": result["status"],
                "reasons": result["integrity"]["reasons"],
            }
    _print_json(result)
    return 0 if result["status"] not in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 1


def cmd_screenshot(session: Session, *, out: Path, overwrite: bool = False,
                   arguments: str | None = None) -> int:
    """Read :DISPlay:DATA?, write the declared BMP to ``out`` and the raw bytes beside it."""

    command = ":DISPlay:DATA?" if not arguments else f":DISPlay:DATA? {arguments}"
    raw = session.query_block(command)
    if session.dry_run:
        return 0
    result = parse_screenshot(raw)
    if result["status"] in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}:
        _print_json(result)
        return 1
    # The declared length is the image; the measured trailing ";0\n" stays in
    # the raw file as evidence and is never appended to the .bmp.
    result["saved_bmp"] = save_raw(Path(out), parse_ieee_block(raw).payload, overwrite=overwrite)
    result["saved_raw"] = save_raw(Path(str(out) + ".raw"), raw, overwrite=overwrite)
    result["transport"] = {
        "command": command,
        "captured_at": _utc_now(),
        "raw_sha256": result["saved_raw"]["sha256"],
    }
    _print_json(result)
    return 0


def cmd_query(session: Session, command: str) -> int:
    """Send one verbatim command; writes require --allow-writes."""

    text = command.strip()
    if not text:
        raise SessionError("command is empty")
    refused = forbidden_reason(text)
    if refused is not None:
        raise SessionError(f"refusing {refused}: this command is never sent by this Skill")
    is_query = text.endswith("?")
    if is_query:
        raw = session.query_text(text)
        if session.dry_run:
            return 0
        record = _raw_record(raw)
        record["command"] = text
        if is_command_error(raw):
            record["command_error"] = True
        _print_json(record)
        return 0 if not is_command_error(raw) else 1
    session.write(text)
    return 0


# ---------------------------------------------------------------------------
# Acquisition state handling
# ---------------------------------------------------------------------------


def _acquire_context(session: Session) -> dict:
    """Record the state that a waveform read may need to restore."""

    if session.dry_run:
        return {}
    return {
        "trigger_status": session.status(":TRIGger:STATus?"),
        "waveform_mode": session.status(":WAVeform:MODE?"),
        "waveform_source": session.status(":WAVeform:SOURce?"),
        # The window is a global setting: leaving STOP behind after a RAW read
        # makes a later NORM read report more points than the screen record.
        "waveform_start": session.status(":WAVeform:STARt?"),
        "waveform_stop": session.status(":WAVeform:STOP?"),
    }


def _prepare_waveform_read(
    session: Session,
    *,
    mode: str | None,
    start: int | None,
    stop: int | None,
    prior: dict,
) -> None:
    """RAW/MAX reads require a stopped acquisition (measured)."""

    # Measured: :WAVeform:STOP is rejected with -220 while the scope runs, and
    # :ACQuire:MDEPth only accepts a new depth while it runs.
    session.write(":STOP")
    if mode is not None:
        session.write(f":WAVeform:MODE {mode}")
    if start is not None and stop is not None:
        session.write(f":WAVeform:STARt {int(start)}")
        session.write(f":WAVeform:STOP {int(stop)}")


def _restore_acquire_context(session: Session, prior: dict) -> None:
    """Restore the waveform source/mode and the run/stop state after a read."""

    if session.dry_run:
        print(
            "DRY-RUN NOTE: after the read, :WAVeform:SOURce/:WAVeform:MODE and "
            ":RUN or :STOP are written back with the values read before the change"
        )
        return
    source = prior.get("waveform_source")
    if source:
        session.write(f":WAVeform:SOURce {source}")
    mode = prior.get("waveform_mode")
    if mode:
        session.write(f":WAVeform:MODE {mode}")
    start = prior.get("waveform_start")
    stop = prior.get("waveform_stop")
    if start and stop:
        session.write(f":WAVeform:STARt {int(float(start))}")
        session.write(f":WAVeform:STOP {int(float(stop))}")
    status = (prior.get("trigger_status") or "").upper()
    if status:
        session.write(":RUN" if status in RUNNING_TRIGGER_STATES else ":STOP")


# ---------------------------------------------------------------------------
# Composite capture
# ---------------------------------------------------------------------------


def _report_status(checks: list[dict]) -> str:
    failed = [check for check in checks if check["status"] == "fail"]
    for status in STATUS_PRECEDENCE[:-1]:
        if any(check["evidence"].get("status") == status for check in failed):
            return status
    return "COMPLETE" if not failed else "UNVERIFIED"


def cmd_capture(
    session: Session,
    *,
    prefix: Path,
    channel: int = 1,
    mode: str | None = None,
    with_screenshot: bool = False,
    overwrite: bool = False,
) -> int:
    """Capture identity, measurements, preamble and one waveform into a report."""

    _require_channel(channel)
    targets = {
        "waveform": Path(f"{prefix}.waveform.bin"),
        "preamble": Path(f"{prefix}.preamble.txt"),
        "report": Path(f"{prefix}.report.json"),
    }
    if with_screenshot:
        targets["screenshot_raw"] = Path(f"{prefix}.screenshot.raw")
        targets["screenshot_bmp"] = Path(f"{prefix}.screenshot.bmp")
    if not overwrite and not session.dry_run:
        for path in targets.values():
            if path.exists():
                raise SessionError(f"refusing to overwrite {path}")

    captured_at = _utc_now()
    prior = _acquire_context(session)
    identity_raw = session.query_text("*IDN?")
    error_raw = session.query_text(":SYSTem:ERRor?")
    measurement_raw: dict[str, bytes] = {}
    for quantity in CAPTURE_QUANTITIES:
        measurement_raw[quantity] = session.query_text(MEASUREMENT_COMMANDS[quantity])
    try:
        if mode is not None:
            # Measured: RAW/MAX read the internal memory only while stopped.
            _prepare_waveform_read(session, mode=mode, start=None, stop=None, prior=prior)
        points_raw = session.query_text(":WAVeform:POINts?")
        preamble_raw = session.query_text(":WAVeform:PREamble?")
        data_raw = session.query_block(":WAVeform:DATA?")
    finally:
        if mode is not None:
            _restore_acquire_context(session, prior)
    if session.dry_run:
        return 0

    identity = parse_identity(identity_raw)
    error_queue = parse_error_queue(error_raw)
    preamble = parse_preamble(preamble_raw)
    waveform = parse_waveform(data_raw, preamble_raw=preamble_raw)
    measurements = {
        quantity: parse_measurement(raw, quantity=quantity)
        for quantity, raw in measurement_raw.items()
    }

    checks: list[dict] = []
    checks.append(
        _check(
            "identity",
            "pass" if identity["status"] == "COMPLETE" else "fail",
            {"status": identity["status"], "model": identity.get("model"), "firmware": identity.get("firmware")},
        )
    )
    checks.append(
        _check(
            "error_queue_empty",
            "pass" if error_queue["status"] == "COMPLETE" else "fail",
            {"status": error_queue["status"], "code": error_queue.get("code"), "message": error_queue.get("message")},
        )
    )

    for quantity, result in measurements.items():
        if result["status"] == "COMPLETE":
            checks.append(
                _check(
                    f"measurement_{quantity}",
                    "pass",
                    {"value": result["value"], "unit": result["unit"], "token": result["numeric_token"]},
                )
            )
        elif result.get("sentinel") == "9.9E37":
            checks.append(
                _check(
                    f"measurement_{quantity}",
                    "fail",
                    {"status": "INCOMPLETE", "reason": "no_measurement_result_sentinel", "token": "9.9E37"},
                )
            )
        else:
            checks.append(
                _check(
                    f"measurement_{quantity}",
                    "fail",
                    {
                        "status": result["status"],
                        "reason": result["integrity"]["reasons"],
                        "command_error": result.get("command_error", False),
                    },
                )
            )

    checks.append(
        _check(
            "waveform",
            "pass" if waveform["status"] == "COMPLETE" else "fail",
            {"status": waveform["status"], "reasons": waveform["integrity"]["reasons"]},
        )
    )
    block_check = next(
        (check for check in waveform["integrity"]["checks"] if check["name"] == "ieee_block_length"),
        None,
    )
    checks.append(
        _check(
            "block_length",
            "pass" if block_check is not None else "not_checked",
            dict(block_check["evidence"]) if block_check else {"status": waveform["status"]},
        )
    )
    declared_points = next(
        (check for check in waveform["integrity"]["checks"] if check["name"] == "declared_points"),
        None,
    )
    checks.append(
        _check(
            "preamble_points_match_payload",
            "pass" if declared_points is not None else "not_checked",
            dict(declared_points["evidence"]) if declared_points else {"reason": "preamble_missing"},
        )
    )
    points_text = points_raw.decode("ascii", "replace").strip()
    checks.append(
        _check(
            "points_response_match_preamble",
            "pass" if points_text.isdigit() and waveform.get("preamble")
            and int(points_text) == waveform["preamble"]["points"] else "fail",
            {
                "status": "INVALID",
                "points_response": points_text,
                "preamble_points": (waveform.get("preamble") or {}).get("points"),
            },
        )
    )

    # Measured: NORM yincrement is the channel scale / 25 (0.5 V/div -> 0.02).
    # RAW uses a different factor (0.0209375 at the same scale), so only the
    # NORM relation is checked.
    scale_raw = session.query_text(f":CHANnel{channel}:SCALe?")
    scale_text = scale_raw.decode("ascii", "replace").strip()
    try:
        channel_scale = float(scale_text)
    except ValueError:
        channel_scale = None
    if waveform.get("preamble") and waveform["preamble"]["mode"] == 0 and channel_scale:
        expected = channel_scale / 25.0
        observed = waveform["preamble"]["yincrement"]
        matches = abs(observed - expected) <= expected * 1e-6
        checks.append(
            _check(
                "preamble_yincrement_matches_channel_scale",
                "pass" if matches else "fail",
                {
                    "status": "INVALID",
                    "yincrement": observed,
                    "channel_scale": channel_scale,
                    "expected_yincrement": expected,
                },
            )
        )
    else:
        checks.append(
            _check(
                "preamble_yincrement_matches_channel_scale",
                "not_checked",
                {"channel_scale": channel_scale, "mode": (waveform.get("preamble") or {}).get("mode_name")},
            )
        )

    measured_vpp = measurements.get("vpp", {}).get("value")
    codes = waveform.get("codes")
    if measured_vpp is not None and codes is not None:
        yincrement = waveform["preamble"]["yincrement"]
        difference = abs(codes["vpp_volts"] - measured_vpp)
        tolerance = max(2 * yincrement, 0.05 * measured_vpp)
        checks.append(
            _check(
                "waveform_vpp_matches_measurement",
                "pass" if difference <= tolerance else "fail",
                {
                    "status": "UNVERIFIED",
                    "waveform_vpp_volts": codes["vpp_volts"],
                    "measured_vpp_volts": measured_vpp,
                    "difference_volts": difference,
                    "tolerance_volts": tolerance,
                },
            )
        )
    else:
        checks.append(_check("waveform_vpp_matches_measurement", "not_checked", {}))

    screenshot = None
    if with_screenshot:
        shot_raw = session.query_block(":DISPlay:DATA?")
        screenshot = parse_screenshot(shot_raw)
        checks.append(
            _check(
                "screenshot",
                "pass" if screenshot["status"] == "COMPLETE" else "fail",
                {
                    "status": screenshot["status"],
                    "declared_bytes": screenshot.get("declared_bytes"),
                    "trailing_hex": screenshot.get("trailing_hex"),
                },
            )
        )

    status = _report_status(checks)
    saved = {
        "waveform": save_raw(targets["waveform"], data_raw, overwrite=overwrite),
        "preamble": save_raw(targets["preamble"], preamble_raw, overwrite=overwrite),
    }
    if with_screenshot and screenshot is not None:
        saved["screenshot_raw"] = save_raw(targets["screenshot_raw"], shot_raw, overwrite=overwrite)
        saved["screenshot_bmp"] = save_raw(
            targets["screenshot_bmp"], parse_ieee_block(shot_raw).payload, overwrite=overwrite
        )

    report = {
        "schema_version": "ds1000z-capture-v1",
        "captured_at": captured_at,
        "status": status,
        "instrument": {
            "identity": identity.get("identity"),
            "identity_status": identity["status"],
            "raw": _raw_record(identity_raw),
        },
        "transport": {"host": session.host, "port": session.port, "raw_tcp": True, "dry_run": session.dry_run},
        "request": {
            "channel": channel,
            "mode": mode,
            "with_screenshot": with_screenshot,
            "commands": [payload.decode("ascii", "replace").strip() for payload in session.sent],
        },
        "acquisition": {
            "trigger_status": prior.get("trigger_status"),
            "waveform_mode_before": prior.get("waveform_mode"),
            "points_response": points_text,
            "channel_scale": scale_text,
        },
        "checks": checks,
        "measurements": {
            quantity: {
                "status": result["status"],
                "value": result["value"],
                "unit": result["unit"],
                "numeric_token": result["numeric_token"],
                "reasons": result["integrity"]["reasons"],
                "raw": _raw_record(measurement_raw[quantity]),
            }
            for quantity, result in measurements.items()
        },
        "error_queue": {
            "status": error_queue["status"],
            "code": error_queue.get("code"),
            "message": error_queue.get("message"),
            "raw": _raw_record(error_raw),
        },
        "preamble": {key: preamble.get(key) for key in
                     ("status", "format", "mode", "points", "count", "xincrement", "xorigin",
                      "yincrement", "yorigin", "yreference", "zero_code", "raw_fields")},
        "waveform": {
            "status": waveform["status"],
            "points": waveform.get("points"),
            "declared_block_bytes": waveform.get("declared_block_bytes"),
            "codes": waveform.get("codes"),
            "reasons": waveform["integrity"]["reasons"],
            "payload_sha256": waveform.get("payload_sha256"),
        },
        "screenshot": None if screenshot is None else {
            "status": screenshot["status"],
            "declared_bytes": screenshot.get("declared_bytes"),
            "payload_bytes": screenshot.get("payload_bytes"),
            "trailing_hex": screenshot.get("trailing_hex"),
            "trimmed_bmp_sha256": screenshot.get("trimmed_bmp_sha256"),
            "reasons": screenshot["integrity"]["reasons"],
        },
        "saved": saved,
        "limitations": [
            "one command per write; a dropped command is invisible without an error-queue read",
            "waveform voltages are uncalibrated; code-domain claims only",
            "RAW/MAX reads require a stopped acquisition and restore the previous run state",
        ],
    }
    report_saved = save_raw(
        targets["report"],
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n",
        overwrite=overwrite,
    )
    _print_json({**report, "report_file": report_saved})
    return 0 if status in {"COMPLETE", "UNVERIFIED"} else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", help="instrument IPv4/hostname (raw TCP)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="overall text-query timeout")
    parser.add_argument("--idle-timeout", type=float, default=DEFAULT_IDLE_TIMEOUT,
                        help="per-recv idle timeout; also ends a terminator-less 'command error'")
    parser.add_argument("--block-timeout", type=float, default=DEFAULT_BLOCK_TIMEOUT)
    parser.add_argument("--write-delay", type=float, default=DEFAULT_WRITE_DELAY)
    parser.add_argument("--dry-run", action="store_true", help="print the bytes instead of connecting")
    parser.add_argument("--allow-writes", action="store_true",
                        help="permit state-changing commands (never *RST/*SAV/*RCL/:SAVE/:RECAll/:LAN:*)")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("identity", help="query *IDN? and parse it")

    p_errors = sub.add_parser("errors", help="read the error queue")
    p_errors.add_argument("--drain", action="store_true", help="read until 0,\"No error\"")

    p_measure = sub.add_parser("measurement", help="query one measurement")
    p_measure.add_argument("--quantity", required=True)
    p_measure.add_argument("--channel", type=int, help="set :MEASure:SOURce first (requires --allow-writes)")

    sub.add_parser("preamble", help="query :WAVeform:PREamble?")

    p_wave = sub.add_parser("waveform", help="read and save one :WAVeform:DATA? block")
    p_wave.add_argument("--out", required=True, type=Path)
    p_wave.add_argument("--channel", type=int)
    p_wave.add_argument("--mode", choices=("NORM", "MAX", "RAW"))
    p_wave.add_argument("--start", type=int)
    p_wave.add_argument("--stop", type=int)
    p_wave.add_argument("--overwrite", action="store_true")
    p_wave.add_argument(
        "--bundle-out",
        type=Path,
        help=(
            "also write a waveform-bundle/v1 document for the analysis Skill: "
            "<name>.bundle.json plus <name>.bin beside it, where <name> drops a "
            "trailing .bundle.json / .json"
        ),
    )

    p_shot = sub.add_parser("screenshot", help="read :DISPlay:DATA? and save the BMP")
    p_shot.add_argument("--out", required=True, type=Path, help="raw response path; the image goes to <out>.bmp")
    p_shot.add_argument("--arguments", help="documented argument set, e.g. ON,OFF")
    p_shot.add_argument("--overwrite", action="store_true")

    p_capture = sub.add_parser("capture", help="identity, measurements, preamble, waveform and a report")
    p_capture.add_argument("--out-prefix", required=True, type=Path)
    p_capture.add_argument("--channel", type=int, default=1)
    p_capture.add_argument("--mode", choices=("NORM", "MAX", "RAW"))
    p_capture.add_argument("--with-screenshot", action="store_true")
    p_capture.add_argument("--overwrite", action="store_true")

    p_query = sub.add_parser("query", help="send one verbatim command")
    p_query.add_argument("command_text")

    p_cursor = sub.add_parser("cursor", help="read every :CURSor field of the active cursor family")
    p_cursor.add_argument("--mode", help="switch to MAN, TRACk, or AUTO first (needs --allow-writes); XY is refused")
    p_cursor.add_argument("--out-raw", type=Path, help="save every raw reply as <dir>/<quantity>.raw")
    p_cursor.add_argument("--overwrite", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        session = Session(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            idle_timeout=args.idle_timeout,
            block_timeout=args.block_timeout,
            write_delay=args.write_delay,
            dry_run=args.dry_run,
            allow_writes=args.allow_writes,
        )
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.subcommand == "identity":
            return cmd_identity(session)
        if args.subcommand == "errors":
            return cmd_errors(session, drain=args.drain)
        if args.subcommand == "measurement":
            return cmd_measurement(session, args.quantity, args.channel)
        if args.subcommand == "preamble":
            return cmd_preamble(session)
        if args.subcommand == "waveform":
            return cmd_waveform(
                session,
                out=Path(args.out),
                channel=args.channel,
                mode=args.mode,
                start=args.start,
                stop=args.stop,
                overwrite=args.overwrite,
                bundle_out=args.bundle_out,
            )
        if args.subcommand == "screenshot":
            return cmd_screenshot(
                session, out=Path(args.out), overwrite=args.overwrite, arguments=args.arguments
            )
        if args.subcommand == "capture":
            return cmd_capture(
                session,
                prefix=Path(args.out_prefix),
                channel=args.channel,
                mode=args.mode,
                with_screenshot=args.with_screenshot,
                overwrite=args.overwrite,
            )
        if args.subcommand == "query":
            return cmd_query(session, args.command_text)
        if args.subcommand == "cursor":
            return cmd_cursor(
                session, mode=args.mode, out_raw=args.out_raw, overwrite=args.overwrite
            )
    except (SessionError, ProtocolError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
