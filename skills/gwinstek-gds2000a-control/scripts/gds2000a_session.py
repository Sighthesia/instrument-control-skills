#!/usr/bin/env python3
"""Optional live transport for the GW Instek GDS-2000A series.

The module imports pyserial lazily. ``--dry-run`` prints the exact bytes that
would be sent and never opens a serial port. No command here resets, saves,
recalls, overwrites instrument files, or changes calibration state without an
explicit subcommand.

Default transport: USB CDC-ACM on /dev/ttyACM1, 115200 8N1, LF terminator.
The GDS-2104A used for verification was at that port; a different host may
enumerate it elsewhere, so always pass ``--port`` when it is not /dev/ttyACM1.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gds2000a_protocol import (  # noqa: E402
    ProtocolError,
    parse_error_queue,
    parse_identity,
    parse_ieee_block,
    parse_measurement,
    parse_waveform,
)

DEFAULT_SERIAL_PORT = "/dev/ttyACM1"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 2.0
DEFAULT_BLOCK_DEADLINE = 60.0
MAX_RESPONSE_BYTES = 20_100_000
ERROR_QUEUE_LIMIT = 32
STOPPED_STATES = {"SAVE", "STOP", "STOPPED"}
RUNNING_STATES = {"ARMED", "AUTO", "TRIGGER"}
SINGLE_READY_STATES = {"READY"}

MEASURE_ITEMS = {
    "frequency": "FREQuency",
    "freq": "FREQuency",
    "period": "PERiod",
    "rise": "RISe",
    "fall": "FALL",
    "width": "PWIDth",
    "nwidth": "NWIDth",
    "pwidth": "PWIDth",
    "duty": "PDUTy",
    "pduty": "PDUTy",
    "amplitude": "AMPlitude",
    "mean": "MEAN",
    "cmean": "CMEan",
    "high": "HIGH",
    "low": "LOW",
    "max": "MAX",
    "min": "MIN",
    "pk2pk": "PK2PK",
    "vpp": "PK2PK",
    "rms": "RMS",
    "area": "AREa",
    "carea": "CARea",
    "fovshoot": "FOVShoot",
    "fpreshoot": "FPReshoot",
    "rovshoot": "ROVShoot",
    "rpreshoot": "RPReshoot",
    "phase": "PHAse",
    "frrdelay": "FRRDelay",
    "frfdelay": "FRFDelay",
    "ffrdelay": "FFRDelay",
    "fffdelay": "FFFDelay",
    "lrrdelay": "LRRDelay",
    "lrfdelay": "LRFDelay",
    "lfrdelay": "LFRDelay",
    "lffdelay": "LFFDelay",
    "ppulse": "PPULSE",
    "npulse": "NPULSE",
    "pedge": "PEDGE",
    "nedge": "NEDGE",
}


class SessionError(RuntimeError):
    """A transport, state, or file-safety failure."""


def _serial_module():
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SessionError(
            "pyserial is required for USB CDC transport; install it or use --dry-run"
        ) from exc
    return serial


def _block_total(data: bytes) -> int | None:
    """Return the absolute end offset of a definite-length block in ``data``."""

    start = 0
    if not data.startswith(b"#"):
        marker = data.find(b"Waveform Data;")
        if marker < 0:
            return None
        start = data.find(b"#", marker + len(b"Waveform Data;"))
        if start < 0:
            return None
    if len(data) < start + 2 or data[start : start + 1] != b"#":
        return None
    if not data[start + 1 : start + 2].isdigit():
        return None
    digits = int(data[start + 1 : start + 2])
    if digits == 0 or len(data) < start + 2 + digits:
        return None
    length_text = data[start + 2 : start + 2 + digits]
    if not length_text.isdigit():
        return None
    total = start + 2 + digits + int(length_text)
    if total > MAX_RESPONSE_BYTES:
        raise SessionError("response exceeds the size limit")
    return total


def _with_optional_terminator(data: bytes, end: int) -> int:
    if data[end : end + 2] in {b"\r\n", b"\n\r"}:
        return end + 2
    if data[end : end + 1] in {b"\r", b"\n"}:
        return end + 1
    return end


def save_raw(path: Path, raw: bytes, *, overwrite: bool = False) -> Path:
    """Write raw bytes atomically and refuse to overwrite by default."""

    destination = Path(path)
    if destination.exists() and not overwrite:
        raise SessionError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return destination


class Session:
    """One serial session with byte-exact reads and dry-run support."""

    def __init__(
        self,
        *,
        port: str = DEFAULT_SERIAL_PORT,
        baud: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT,
        block_deadline: float = DEFAULT_BLOCK_DEADLINE,
        dry_run: bool = False,
        connection=None,
    ) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.block_deadline = block_deadline
        self.dry_run = dry_run
        self.sent: list[bytes] = []
        self.last_read_end: str | None = None
        self._connection = connection
        self._buffer = bytearray()

    def _open(self) -> None:
        if self._connection is not None or self.dry_run:
            return
        serial = _serial_module()
        self._connection = serial.Serial(
            self.port,
            self.baud,
            timeout=self.timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )

    def _recv(self, size: int = 4096) -> bytes:
        self._open()
        if self._connection is None:
            return b""
        try:
            data = self._connection.read(size)
        except (TimeoutError, OSError) as exc:
            raise SessionError("read timed out") from exc
        if not data:
            raise SessionError("instrument closed the connection or timed out")
        return data

    def send(self, data: bytes) -> None:
        """Send exactly one command; reject a second embedded terminator."""

        if not isinstance(data, (bytes, bytearray)):
            raise SessionError("command must be bytes")
        body = bytes(data).rstrip(b"\r\n")
        if not body:
            raise SessionError("command must not be empty")
        if b"\r" in body or b"\n" in body:
            raise SessionError("one command per write; embedded terminator rejected")
        payload = body + b"\n"
        self.sent.append(payload)
        if self.dry_run:
            print(f"DRY-RUN SEND: {payload!r}")
            return
        self._open()
        assert self._connection is not None
        self._connection.write(payload)
        if hasattr(self._connection, "flush"):
            self._connection.flush()

    def _read_line(self) -> bytes:
        while True:
            positions = [index for delimiter in (b"\r", b"\n") if (index := self._buffer.find(delimiter)) >= 0]
            if positions:
                start = min(positions)
                first = self._buffer[start : start + 1]
                second = self._buffer[start + 1 : start + 2]
                length = 2 if (first == b"\r" and second == b"\n") or (
                    first == b"\n" and second == b"\r"
                ) else 1
                data = bytes(self._buffer[: start + length])
                del self._buffer[: start + length]
                return data
            if len(self._buffer) > MAX_RESPONSE_BYTES:
                raise SessionError("response exceeds the size limit")
            self._buffer.extend(self._recv())

    def query_text(self, command: str) -> bytes:
        """Send one query and return one raw line, terminator included."""

        self.send(command.encode("ascii"))
        if self.dry_run:
            return b""
        raw = self._read_line()
        self.last_read_end = "line_terminator"
        return raw

    def query_block(self, command: str) -> bytes:
        """Send one query and read a header + definite-length block exactly.

        The read ends at the declared length (plus an already-buffered line
        terminator) or at ``block_deadline``. It never ends on an idle gap.
        """

        self.send(command.encode("ascii"))
        if self.dry_run:
            return b""
        start = time.monotonic()
        self.last_read_end = None
        while True:
            total = _block_total(bytes(self._buffer))
            if total is not None and len(self._buffer) >= total:
                end = _with_optional_terminator(bytes(self._buffer), total)
                if len(self._buffer) <= end:
                    # Try to consume the one documented terminator without
                    # waiting for a second idle gap.  If the next read is the
                    # next reply instead, it stays buffered.
                    try:
                        self._buffer.extend(self._recv())
                    except SessionError:
                        pass
                    end = _with_optional_terminator(bytes(self._buffer), total)
                if len(self._buffer) < end:
                    end = total
                data = bytes(self._buffer[:end])
                del self._buffer[:end]
                self.last_read_end = "declared_length" if end > total else "declared_length_no_terminator"
                return data
            if time.monotonic() - start > self.block_deadline:
                data = bytes(self._buffer)
                self._buffer.clear()
                self.last_read_end = "deadline"
                return data
            # A short line is an error reply, not a partial waveform.  Header
            # prefixes (`Format,`, `Waveform Data;`) are not complete lines
            # until the block marker appears.
            if b"\n" in self._buffer or b"\r" in self._buffer:
                probe = bytes(self._buffer)
                if b"Format," not in probe and b"Waveform Data;" not in probe and not probe.startswith(b"#"):
                    data = self._read_line()
                    self.last_read_end = "line_terminator"
                    return data
            try:
                self._buffer.extend(self._recv())
            except SessionError:
                data = bytes(self._buffer)
                self._buffer.clear()
                self.last_read_end = "deadline"
                return data

    def drain_errors(self) -> list[bytes]:
        """Read `:SYSTem:ERRor?` until +0 or the bounded limit."""

        responses: list[bytes] = []
        for _ in range(ERROR_QUEUE_LIMIT):
            raw = self.query_text(":SYSTem:ERRor?")
            if self.dry_run:
                return [b""]
            responses.append(raw)
            record = parse_error_queue(raw)
            if record.get("code") == 0:
                break
        return responses

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:  # pragma: no cover - hardware close best effort
                pass
            self._connection = None


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _validate_channel(channel: int) -> None:
    if isinstance(channel, bool) or channel not in {1, 2, 3, 4}:
        raise SessionError("channel must be 1, 2, 3, or 4")


def _state(session: Session) -> str:
    raw = session.query_text(":TRIGger:STATe?")
    return raw.decode("ascii", errors="replace").strip()


def _restore_run(session: Session) -> dict[str, str]:
    """Return the instrument to continuous acquisition after a forced STOP."""

    session.send(b":RUN")
    time.sleep(0.2)
    state = _state(session)
    detail = {"after_run": state}
    if state.upper() in SINGLE_READY_STATES | STOPPED_STATES:
        # The GDS-2104A V1.18 did not leave READY/SAVE on :RUN alone; a STOP
        # followed by RUN restored continuous AUTO/ARMED in the verified run.
        session.send(b":STOP")
        time.sleep(0.1)
        session.send(b":RUN")
        time.sleep(0.2)
        detail["after_stop_run"] = _state(session)
    return detail


def cmd_idn(session: Session, *, provenance: str) -> int:
    raw = session.query_text("*IDN?")
    if session.dry_run:
        return 0
    result = parse_identity(raw, provenance=provenance)
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_errors(session: Session, *, drain: bool, provenance: str) -> int:
    responses = session.drain_errors() if drain else [session.query_text(":SYSTem:ERRor?")]
    if session.dry_run:
        return 0
    records = [parse_error_queue(raw, provenance=provenance) for raw in responses]
    _print_json({"records": records, "complete": any(r.get("code") == 0 for r in records)})
    return 0 if any(r.get("code") == 0 for r in records) else 1


def cmd_state(session: Session) -> int:
    commands = [
        ":TRIGger:STATe?",
        ":TRIGger:MODe?",
        ":TRIGger:TYPe?",
        ":TRIGger:SOURce?",
        ":TRIGger:LEVel?",
        ":TIMebase:SCALe?",
        ":TIMebase:MODe?",
        ":ACQuire:MODe?",
        ":ACQuire:RECOrdlength?",
        ":HEADer?",
        ":CHANnel1:DISPlay?",
        ":CHANnel1:SCALe?",
        ":CHANnel1:COUPling?",
        ":MEASure:SOURce1?",
        ":MEASure:SOURce2?",
    ]
    snapshot: dict[str, str] = {}
    for command in commands:
        raw = session.query_text(command)
        if session.dry_run:
            continue
        snapshot[command] = raw.decode("ascii", errors="replace").strip()
    if not session.dry_run:
        _print_json({"snapshot": snapshot})
    return 0


def cmd_measure(
    session: Session,
    *,
    item: str,
    channel: int,
    slot: int,
    provenance: str,
) -> int:
    _validate_channel(channel)
    if slot not in {1, 2}:
        raise SessionError("measurement source slot must be 1 or 2")
    if item.lower() not in MEASURE_ITEMS:
        raise SessionError(f"unsupported measurement item {item!r}")
    command = f":MEASure:{MEASURE_ITEMS[item.lower()]}?"

    if session.dry_run:
        session.query_text(f":MEASure:SOURce{slot}?")
        session.send(f":MEASure:SOURce{slot} CH{channel}".encode("ascii"))
        session.query_text(command)
        session.send(f":MEASure:SOURce{slot} CH{channel}".encode("ascii"))
        return 0

    original_raw = session.query_text(f":MEASure:SOURce{slot}?")
    original = original_raw.decode("ascii", errors="replace").strip()
    changed = original.upper() != f"CH{channel}"
    if changed:
        session.send(f":MEASure:SOURce{slot} CH{channel}".encode("ascii"))
        time.sleep(0.2)
    try:
        raw = session.query_text(command)
        result = parse_measurement(raw, quantity=item, provenance=provenance)
    finally:
        if changed:
            session.send(f":MEASure:SOURce{slot} {original}".encode("ascii"))
            time.sleep(0.2)
    errors = session.drain_errors()
    _print_json(
        {
            "measurement": result,
            "source_slot": slot,
            "original_source": original,
            "source_restored": not changed or session.query_text(f":MEASure:SOURce{slot}?").decode().strip() == original,
            "error_queue": [parse_error_queue(raw).get("message") for raw in errors],
        }
    )
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_waveform(
    session: Session,
    *,
    channel: int,
    out: Path | None,
    csv_out: Path | None,
    overwrite: bool,
    provenance: str,
) -> int:
    _validate_channel(channel)
    command = f":ACQuire{channel}:MEMory?"

    if session.dry_run:
        session.query_text(":TRIGger:STATe?")
        session.send(b":STOP")
        session.query_block(command)
        session.send(b":RUN")
        return 0

    initial_state = _state(session)
    stopped_by_us = initial_state.upper() not in STOPPED_STATES
    restore: dict[str, str] | None = None
    if stopped_by_us:
        session.send(b":STOP")
        time.sleep(0.3)
    try:
        raw = session.query_block(command)
    finally:
        if stopped_by_us:
            restore = _restore_run(session)
    artifact = parse_waveform(raw, provenance=provenance)
    errors = session.drain_errors()
    artifact["transport"] = {
        "port": session.port,
        "baud": session.baud,
        "initial_trigger_state": initial_state,
        "stopped_by_skill": stopped_by_us,
        "restore": restore,
        "read_end": session.last_read_end,
        "error_queue": [parse_error_queue(raw).get("message") for raw in errors],
    }
    if out is not None:
        artifact["raw_path"] = str(save_raw(out, raw, overwrite=overwrite))
    if csv_out is not None:
        from gds2000a_protocol import waveform_to_csv

        try:
            artifact["csv"] = waveform_to_csv(raw, csv_out, overwrite=overwrite)
        except (ProtocolError, FileExistsError) as exc:
            artifact["csv_error"] = str(exc)
    _print_json(artifact)
    return 0 if artifact["status"] in {"COMPLETE", "UNVERIFIED"} else 1


def cmd_screenshot(session: Session, *, out: Path | None, overwrite: bool) -> int:
    raw = session.query_block(":DISPlay:OUTPut?")
    if session.dry_run:
        return 0
    result = {
        "kind": "screen-image",
        "transport": {"read_end": session.last_read_end},
        "raw_bytes": len(raw),
    }
    try:
        block = parse_ieee_block(raw, allow_terminator=True)
        result.update(
            {
                "block_declared_bytes": block.declared_length,
                "block_payload_bytes": len(block.payload),
                "block_trailing_hex": block.trailing.hex(),
                "status": "UNVERIFIED",
                "reason": "image decoding is not implemented; raw RLE bytes only",
            }
        )
    except ProtocolError as exc:
        result.update({"status": exc.status, "reason": str(exc)})
    if out is not None:
        result["raw_path"] = str(save_raw(out, raw, overwrite=overwrite))
    _print_json(result)
    return 0 if result["status"] == "UNVERIFIED" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_SERIAL_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--block-deadline", type=float, default=DEFAULT_BLOCK_DEADLINE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provenance", default="hardware-verified", choices=["documented", "hardware-verified"])
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("idn", help="parse one *IDN? response")
    errors = subparsers.add_parser("errors", help="read or drain :SYSTem:ERRor?")
    errors.add_argument("--drain", action="store_true")
    subparsers.add_parser("state", help="read-only state snapshot")

    measure = subparsers.add_parser("measure", help="set one measurement source, query an item, restore")
    measure.add_argument("--item", default="pk2pk")
    measure.add_argument("--channel", type=int, default=1)
    measure.add_argument("--slot", type=int, default=1)

    waveform = subparsers.add_parser("waveform", help="STOP, download :ACQuire<n>:MEMory?, restore RUN")
    waveform.add_argument("--channel", type=int, default=1)
    waveform.add_argument("--out", type=Path)
    waveform.add_argument("--csv-out", type=Path)
    waveform.add_argument("--overwrite", action="store_true")

    screenshot = subparsers.add_parser("screenshot", help="download :DISPlay:OUTPut? raw RLE bytes")
    screenshot.add_argument("--out", type=Path)
    screenshot.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)
    session = Session(
        port=args.port,
        baud=args.baud,
        timeout=args.timeout,
        block_deadline=args.block_deadline,
        dry_run=args.dry_run,
    )
    try:
        if args.command == "idn":
            return cmd_idn(session, provenance=args.provenance)
        if args.command == "errors":
            return cmd_errors(session, drain=args.drain, provenance=args.provenance)
        if args.command == "state":
            return cmd_state(session)
        if args.command == "measure":
            return cmd_measure(
                session,
                item=args.item,
                channel=args.channel,
                slot=args.slot,
                provenance=args.provenance,
            )
        if args.command == "waveform":
            return cmd_waveform(
                session,
                channel=args.channel,
                out=args.out,
                csv_out=args.csv_out,
                overwrite=args.overwrite,
                provenance=args.provenance,
            )
        if args.command == "screenshot":
            return cmd_screenshot(session, out=args.out, overwrite=args.overwrite)
        raise SessionError(f"unknown command {args.command}")
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
