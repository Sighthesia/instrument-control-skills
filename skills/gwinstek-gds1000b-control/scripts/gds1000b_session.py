#!/usr/bin/env python3
"""Optional live transport for the GW Instek GDS-1000B series.

The module imports pyserial lazily. ``--dry-run`` records the exact bytes that
would be sent and never opens a serial port or socket. No command in this
helper resets, saves, recalls, overwrites files, or changes calibration state
without an explicit subcommand.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gds1000b_protocol import (  # noqa: E402
    ProtocolError,
    parse_error_queue,
    parse_identity,
    parse_measurement,
    parse_waveform,
)

DEFAULT_SERIAL_PORT = "/dev/ttyACM0"
DEFAULT_BAUD = 115200
MAX_RESPONSE_BYTES = 20_100_000

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
    "crms": "CRMS",
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

_IMAGE_RE = re.compile(r"^(Disk|USB):/([^/\\]{1,8})\.(PNG|BMP)$", re.IGNORECASE)


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
    if len(data) < 2 or data[:1] != b"#" or not data[1:2].isdigit():
        return None
    digits = int(data[1:2])
    if digits == 0 or len(data) < 2 + digits:
        return None
    length_text = data[2 : 2 + digits]
    if not length_text.isdigit():
        return None
    return 2 + digits + int(length_text)


def _with_optional_terminator(data: bytes, end: int) -> int:
    """Include one optional LF/CR/CRLF terminator after a binary block."""

    if data[end : end + 2] == b"\r\n" or data[end : end + 2] == b"\n\r":
        return end + 2
    if bytes(data[end : end + 1]) in {b"\r", b"\n"}:
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


def validate_image_path(path: str) -> tuple[str, str]:
    """Validate a documented Disk:/USB: image path and return (path, format)."""

    match = _IMAGE_RE.fullmatch(path)
    if not match:
        raise SessionError(
            'image path must be "Disk:/name.PNG" or "USB:/name.BMP" with a filename of at most 8 characters'
        )
    return path, match.group(3).upper()


class Session:
    """One serial or TCP session with byte-exact reads and dry-run support."""

    def __init__(
        self,
        *,
        port: str | None = None,
        baud: int = DEFAULT_BAUD,
        host: str | None = None,
        tcp_port: int | None = None,
        timeout: float = 10.0,
        dry_run: bool = False,
    ) -> None:
        if port is not None and host is not None:
            raise SessionError("choose either a serial port or a TCP host, not both")
        if host is not None and tcp_port is None:
            raise SessionError("TCP mode requires --host and --port")
        if tcp_port is not None and not 1024 <= tcp_port <= 65535:
            raise SessionError("TCP port must be in 1024..65535")
        self.kind = "tcp" if host is not None else "serial"
        self.port = port if port is not None else DEFAULT_SERIAL_PORT
        self.baud = baud
        self.host = host
        self.tcp_port = tcp_port
        self.timeout = timeout
        self.dry_run = dry_run
        self.sent: list[bytes] = []
        self._connection = None
        self._buffer = bytearray()

    def _open(self) -> None:
        if self._connection is not None or self.dry_run:
            return
        if self.kind == "tcp":
            assert self.host is not None and self.tcp_port is not None
            self._connection = socket.create_connection((self.host, self.tcp_port), self.timeout)
            self._connection.settimeout(self.timeout)
        else:
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
        connection = self._connection
        try:
            if hasattr(connection, "recv"):
                data = connection.recv(size)
            else:
                data = connection.read(size)
        except socket.timeout as exc:
            raise SessionError("read timed out") from exc
        if not data:
            raise SessionError("instrument closed the connection or timed out")
        return data

    def send(self, data: bytes) -> None:
        payload = data if data.endswith(b"\n") else data + b"\n"
        self.sent.append(payload)
        if self.dry_run:
            print(f"DRY-RUN SEND: {payload!r}")
            return
        self._open()
        assert self._connection is not None
        if hasattr(self._connection, "sendall"):
            self._connection.sendall(payload)
        else:
            self._connection.write(payload)

    def query_text(self, command: str) -> str:
        self.send(command.encode("ascii"))
        if self.dry_run:
            return ""
        return self._read_line().decode("utf-8").strip()

    def query_block(self, command: str) -> bytes:
        self.send(command.encode("ascii"))
        if self.dry_run:
            return b""
        return self.read_block_response()

    def _read_line(self) -> bytes:
        while True:
            cr = self._buffer.find(b"\r")
            lf = self._buffer.find(b"\n")
            positions = [position for position in (cr, lf) if position >= 0]
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
            self._buffer.extend(self._recv())

    def read_block_response(self) -> bytes:
        """Read an ASCII header + IEEE block, or a headerless block, exactly."""

        while True:
            if self._buffer.startswith(b"#"):
                total = _block_total(self._buffer)
                if total is not None and len(self._buffer) >= total:
                    end = _with_optional_terminator(self._buffer, total)
                    if len(self._buffer) < end:
                        self._buffer.extend(self._recv())
                        continue
                    data = bytes(self._buffer[:end])
                    del self._buffer[:end]
                    return data
            marker = self._buffer.find(b"Waveform Data;")
            if marker >= 0:
                hash_index = self._buffer.find(b"#", marker + len(b"Waveform Data;"))
                if hash_index >= 0:
                    total = _block_total(self._buffer[hash_index:])
                    if total is not None and len(self._buffer) >= hash_index + total:
                        end = _with_optional_terminator(self._buffer, hash_index + total)
                        if len(self._buffer) < end:
                            self._buffer.extend(self._recv())
                            continue
                        data = bytes(self._buffer[:end])
                        del self._buffer[:end]
                        return data
            if marker < 0 and not self._buffer.startswith(b"#") and (
                b"\n" in self._buffer or b"\r" in self._buffer
            ):
                return self._read_line()
            if len(self._buffer) > MAX_RESPONSE_BYTES:
                raise SessionError("response exceeds the size limit")
            self._buffer.extend(self._recv())

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:  # pragma: no cover
                pass
            self._connection = None


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _validate_channel(channel: int) -> None:
    if isinstance(channel, bool) or channel not in {1, 2, 3, 4}:
        raise SessionError("channel must be 1, 2, 3, or 4")


def cmd_idn(session: Session) -> int:
    raw = session.query_text("*IDN?")
    if session.dry_run:
        return 0
    result = parse_identity(raw.encode("utf-8"))
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_errors(session: Session, *, drain: bool = False) -> int:
    limit = 20 if drain else 1
    for _ in range(limit):
        raw = session.query_text(":SYSTem:ERRor?")
        if session.dry_run:
            return 0
        result = parse_error_queue(raw.encode("utf-8"), response_type="error-queue")
        _print_json(result)
        if result.get("code") == 0:
            return 0
    return 0


def cmd_snapshot(session: Session, channel: int) -> int:
    _validate_channel(channel)
    queries = [
        "*IDN?",
        ":TRIGger:STATe?",
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:MODe?",
        ":ACQuire:MODe?",
        ":ACQuire:RECOrdlength?",
        ":HEADer?",
        f":CHANnel{channel}:DISPlay?",
        f":CHANnel{channel}:SCALe?",
        f":CHANnel{channel}:POSition?",
        f":CHANnel{channel}:COUPling?",
    ]
    for query in queries:
        response = session.query_text(query)
        if not session.dry_run:
            print(f"{query} -> {response!r}")
    return 0


def cmd_run(session: Session) -> int:
    session.send(b":RUN")
    return 0


def cmd_stop(session: Session) -> int:
    session.send(b":STOP")
    return 0


def cmd_single(session: Session) -> int:
    session.send(b":SINGle")
    return 0


def cmd_force(session: Session) -> int:
    session.send(b":FORCe")
    return 0


def cmd_measure(session: Session, quantity: str, channel: int | None = None) -> int:
    key = quantity.lower().strip()
    if key not in MEASURE_ITEMS:
        raise SessionError(f"unsupported measurement quantity {quantity!r}")
    if channel is not None:
        _validate_channel(channel)
        session.send(f":MEASure:SOURce1 CH{channel}".encode("ascii"))
    raw = session.query_text(f":MEASure:{MEASURE_ITEMS[key]}?")
    if session.dry_run:
        return 0
    result = parse_measurement(raw.encode("utf-8"), quantity=key)
    _print_json(result)
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_query(session: Session, command: str, allow_write: bool = False) -> int:
    text = command.strip()
    is_query = text.endswith("?")
    if not is_query and not allow_write:
        print("refusing non-query command without --allow-write", file=sys.stderr)
        return 2
    if is_query:
        response = session.query_text(text)
        if not session.dry_run:
            print(f"RESPONSE: {response!r}")
    else:
        session.send(text.encode("ascii"))
    return 0


def cmd_capture(session: Session, channel: int, timeout: float, poll: float) -> int:
    _validate_channel(channel)
    session.send(b":HEADer ON")
    session.send(b":SINGle")
    if session.dry_run:
        session.query_text(":TRIGger:STATe?")
        session.query_text(f":ACQuire{channel}:STATe?")
        session.send(b":STOP")
        session.query_block(f":ACQuire{channel}:MEMory?")
        return 0

    deadline = time.monotonic() + timeout
    last_state = ""
    while time.monotonic() < deadline:
        last_state = session.query_text(":TRIGger:STATe?").strip()
        state = last_state.lstrip("*").upper()
        if state == "SAVE":
            break
        if state not in {"ARMED", "READY", "TRIGGER", "AUTO"}:
            raise SessionError(f"unexpected trigger state: {last_state!r}")
        time.sleep(max(poll, 0.01))
    else:
        raise SessionError(f"capture timed out; last trigger state {last_state!r}")

    state = session.query_text(f":ACQuire{channel}:STATe?").strip()
    if state != "1":
        raise SessionError(f"channel {channel} raw data is not ready: {state!r}")
    session.send(b":STOP")
    raw = session.query_block(f":ACQuire{channel}:MEMory?")
    result = parse_waveform(raw)
    result["trigger_state"] = last_state
    _print_json(result)
    return 0 if result["status"] not in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 1


def cmd_waveform(
    session: Session,
    channel: int,
    path: Path,
    *,
    overwrite: bool = False,
    allow_unready: bool = False,
) -> int:
    _validate_channel(channel)
    if not session.dry_run and not allow_unready:
        state = session.query_text(f":ACQuire{channel}:STATe?").strip()
        if state != "1":
            raise SessionError(f"channel {channel} raw data is not ready: {state!r}")
    raw = session.query_block(f":ACQuire{channel}:MEMory?")
    if session.dry_run:
        return 0
    save_raw(Path(path), raw, overwrite=overwrite)
    result = parse_waveform(raw)
    result["raw_path"] = str(path)
    _print_json(result)
    return 0 if result["status"] not in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 1


def cmd_save_image(session: Session, path: str, inksaver: str = "ON") -> int:
    _, fmt = validate_image_path(path)
    session.send(f":SAVe:IMAGe:FILEFormat {fmt}".encode("ascii"))
    session.send(f":SAVe:IMAGe:INKSaver {inksaver}".encode("ascii"))
    session.send(f':SAVe:IMAGe "{path}"'.encode("ascii"))
    print("image save requested; retrieve the file from Disk:/ or USB:/; SCPI does not return image bytes")
    return 0


def cmd_hardcopy(session: Session, path: str) -> int:
    _, fmt = validate_image_path(path)
    session.send(b":HARDcopy:MODe SAVE")
    session.send(b":HARDcopy:ASSIGN IMAGe")
    session.send(f":HARDcopy:SAVEFORMat {fmt}".encode("ascii"))
    session.send(b":HARDcopy:START")
    print("hardcopy requested; retrieve the saved file from the instrument storage")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=None, help="USB CDC device path")
    parser.add_argument("--host", help="Ethernet socket-server host")
    parser.add_argument("--port", type=int, help="Ethernet socket-server port")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--poll", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("idn")
    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--channel", type=int, default=1)
    p_errors = sub.add_parser("errors")
    p_errors.add_argument("--drain", action="store_true")
    sub.add_parser("run")
    sub.add_parser("stop")
    sub.add_parser("single")
    sub.add_parser("force")

    p_measure = sub.add_parser("measure")
    p_measure.add_argument("--quantity", required=True)
    p_measure.add_argument("--channel", type=int)

    p_wave = sub.add_parser("waveform")
    p_wave.add_argument("--channel", type=int, default=1)
    p_wave.add_argument("--out", required=True)
    p_wave.add_argument("--overwrite", action="store_true")
    p_wave.add_argument("--allow-unready", action="store_true")

    p_capture = sub.add_parser("capture")
    p_capture.add_argument("--channel", type=int, default=1)

    p_image = sub.add_parser("save-image")
    p_image.add_argument("--path", required=True)

    p_hard = sub.add_parser("hardcopy")
    p_hard.add_argument("--path", required=True)

    p_query = sub.add_parser("query")
    p_query.add_argument("command_text")
    p_query.add_argument("--allow-write", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        session = Session(
            port=args.serial,
            baud=args.baud,
            host=args.host,
            tcp_port=args.port,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.subcommand == "idn":
            return cmd_idn(session)
        if args.subcommand == "snapshot":
            return cmd_snapshot(session, args.channel)
        if args.subcommand == "errors":
            return cmd_errors(session, drain=args.drain)
        if args.subcommand == "run":
            return cmd_run(session)
        if args.subcommand == "stop":
            return cmd_stop(session)
        if args.subcommand == "single":
            return cmd_single(session)
        if args.subcommand == "force":
            return cmd_force(session)
        if args.subcommand == "measure":
            return cmd_measure(session, args.quantity, args.channel)
        if args.subcommand == "waveform":
            return cmd_waveform(
                session,
                args.channel,
                Path(args.out),
                overwrite=args.overwrite,
                allow_unready=args.allow_unready,
            )
        if args.subcommand == "capture":
            return cmd_capture(session, args.channel, args.timeout, args.poll)
        if args.subcommand == "save-image":
            return cmd_save_image(session, args.path)
        if args.subcommand == "hardcopy":
            return cmd_hardcopy(session, args.path)
        if args.subcommand == "query":
            return cmd_query(session, args.command_text, args.allow_write)
    except (SessionError, ProtocolError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
