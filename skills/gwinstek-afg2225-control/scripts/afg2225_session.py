#!/usr/bin/env python3
"""Optional live transport helper for the GW Instek AFG-2225.

The module imports ``serial`` lazily.  ``--dry-run`` prints the exact bytes
that would be sent and never touches hardware or pyserial.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from afg2225_protocol import (  # noqa: E402
    build_arb_artifact,
    load_arb_csv,
    parse_error_queue,
    parse_identity,
    validate_arb_samples,
)

LOAD_SETTINGS = {"50": ("DEF", "50 ohm"), "highz": ("INF", "high impedance")}


def _set_load(session: "Session", channel: int, load: str) -> None:
    """Set the reference termination before amplitude/offset are applied."""

    short, label = LOAD_SETTINGS[load]
    session.send(f"OUTP{channel}:LOAD {short}".encode("ascii"), read_response=False)
    print(f"termination=OUTP{channel}:LOAD {short} ({label})")


def _serial_module():
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required for live transport; install it or use --dry-run"
        ) from exc
    return serial


class Session:
    def __init__(self, port: str, baud: int, timeout: float, dry_run: bool) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.dry_run = dry_run
        self._serial = None

    def _open(self):
        if self.dry_run:
            return None
        if self._serial is None:
            serial = _serial_module()
            self._serial = serial.Serial(
                self.port,
                self.baud,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
        return self._serial

    def send(self, data: bytes, read_response: bool = False) -> bytes:
        payload = data if data.endswith(b"\n") else data + b"\n"
        if self.dry_run:
            print(f"DRY-RUN SEND: {payload!r}")
            return b""
        port = self._open()
        port.write(payload)
        if not read_response:
            return b""
        response = port.readline()
        if not response:
            raise RuntimeError("query timed out with no response")
        if not response.endswith(b"\n") and not response.endswith(b"\r"):
            raise RuntimeError("query response is incomplete (no terminator)")
        return response

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # pragma: no cover
                pass
            self._serial = None


def _print_bytes(label: str, data: bytes) -> None:
    print(f"{label}: {data!r}")


def cmd_idn(session: Session, args) -> int:
    response = session.send(b"*IDN?", read_response=True)
    if session.dry_run:
        return 0
    print(f"RESPONSE: {response!r}")
    result = parse_identity(response)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETE" else 1


def cmd_query(session: Session, args) -> int:
    command = args.command_text.strip()
    is_query = command.endswith("?")
    if not is_query and not args.allow_write:
        print("refusing non-query command without --allow-write", file=sys.stderr)
        return 2
    response = session.send(command.encode("ascii"), read_response=is_query)
    if session.dry_run or not is_query:
        return 0
    print(f"RESPONSE: {response!r}")
    return 0


def cmd_errors(session: Session, args) -> int:
    limit = 20 if args.drain else 1
    for _ in range(limit):
        response = session.send(b"SYST:ERR?", read_response=True)
        if session.dry_run:
            return 0
        print(f"RESPONSE: {response!r}")
        result = parse_error_queue(response, response_type="error-queue")
        if result.get("code") == 0:
            return 0
    return 0


def cmd_apply(session: Session, args) -> int:
    if args.load is None:
        print("--load 50|highz is required for apply", file=sys.stderr)
        return 2
    channel = args.channel
    shape = args.shape
    freq = args.frequency if args.frequency is not None else "1kHz"
    amp = args.amplitude if args.amplitude is not None else 1.0
    off = args.offset if args.offset is not None else 0.0
    if not amp > 0:
        print("--amplitude must be positive", file=sys.stderr)
        return 2
    name_map = {
        "sine": "SIN",
        "square": "SQU",
        "ramp": "RAMP",
        "pulse": "PULS",
        "noise": "NOIS",
        "user": "USER",
    }
    short = name_map[shape]
    _set_load(session, channel, args.load)
    amp_token = f"{amp}VPP"
    offset_token = f"{off}V"
    if shape == "noise":
        # Noise has no frequency, but the manual requires a frequency or DEF
        # placeholder before the nested amplitude and offset.
        freq_token = freq if args.frequency is not None else "DEF"
        command = f"SOUR{channel}:APPL:NOIS {freq_token},{amp_token},{offset_token}"
    else:
        command = f"SOUR{channel}:APPL:{short} {freq},{amp_token},{offset_token}"
    session.send(command.encode("ascii"), read_response=False)
    print(f"APPLy command turns output ON; amplitude={amp} Vpp offset={off} V")
    return 0


def cmd_output(session: Session, args) -> int:
    channel = args.channel
    state = "ON" if args.state == "on" else "OFF"
    session.send(f"OUTP{channel} {state}".encode("ascii"), read_response=False)
    return 0


def cmd_arb(session: Session, args) -> int:
    if args.load is None:
        print("--load 50|highz is required for arb", file=sys.stderr)
        return 2
    values = load_arb_csv(args.csv)
    validation = validate_arb_samples(values)
    if validation["status"] != "COMPLETE":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 1
    if args.data_format == "binary" and args.byte_order is None:
        print("binary arb requires --byte-order little|big", file=sys.stderr)
        return 2
    artifact = build_arb_artifact(
        values,
        start=args.start,
        data_format=args.data_format,
        byte_order=args.byte_order,
        source=args.csv,
    )
    import base64

    command = base64.b64decode(artifact["command_bytes_base64"])
    _set_load(session, args.channel, args.load)
    session.send(command, read_response=False)
    session.send(f"SOUR{args.channel}:FUNC USER".encode("ascii"), read_response=False)
    if args.frequency is not None:
        session.send(f"SOUR{args.channel}:FREQ {args.frequency}".encode("ascii"), read_response=False)
    else:
        print("frequency not set; set SOUR<n>:FREQ so rate = frequency x points")
    print(f"points={len(values)} format={args.data_format} byte_order={artifact['byte_order']}")
    print("output remains OFF; use the output subcommand when the load is ready")
    return 0 if artifact["integrity"]["status"] not in {"INVALID", "INCOMPLETE", "UNSUPPORTED"} else 1


def cmd_off(session: Session, args) -> int:
    channel = args.channel
    session.send(f"OUTP{channel} OFF".encode("ascii"), read_response=False)
    return 0


def cmd_snapshot(session: Session, args) -> int:
    channel = args.channel
    queries = [
        "*IDN?",
        f"SOUR{channel}:FUNC?",
        f"SOUR{channel}:FREQ?",
        f"SOUR{channel}:AMPL?",
        f"SOUR{channel}:DCO?",
        f"OUTP{channel}?",
        f"OUTP{channel}:LOAD?",
    ]
    for q in queries:
        response = session.send(q.encode("ascii"), read_response=True)
        if session.dry_run:
            continue
        print(f"{q} -> {response!r}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("idn")

    p_query = sub.add_parser("query")
    p_query.add_argument("command_text")
    p_query.add_argument("--allow-write", action="store_true")

    p_errors = sub.add_parser("errors")
    p_errors.add_argument("--drain", action="store_true", help="read until 0 No error (max 20)")

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("shape", choices=["sine", "square", "ramp", "pulse", "noise", "user"])
    p_apply.add_argument("--channel", type=int, default=1)
    p_apply.add_argument("--frequency")
    p_apply.add_argument("--amplitude", type=float)
    p_apply.add_argument("--offset", type=float)
    p_apply.add_argument("--load", choices=["50", "highz"])

    p_output = sub.add_parser("output")
    p_output.add_argument("state", choices=["on", "off"])
    p_output.add_argument("--channel", type=int, default=1)

    p_arb = sub.add_parser("arb")
    p_arb.add_argument("--csv", required=True)
    p_arb.add_argument("--format", choices=["ascii", "binary"], default="ascii", dest="data_format")
    p_arb.add_argument("--byte-order", choices=["little", "big"], default=None)
    p_arb.add_argument("--start", type=int, default=0)
    p_arb.add_argument("--channel", type=int, default=1)
    p_arb.add_argument("--frequency", help="repetition frequency; rate = frequency x points")
    p_arb.add_argument("--load", choices=["50", "highz"])

    sub.add_parser("off").add_argument("--channel", type=int, default=1, dest="channel")

    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--channel", type=int, default=1)

    args = parser.parse_args(argv)
    channel = getattr(args, "channel", None)
    if channel is not None and channel not in {1, 2}:
        print("channel must be 1 or 2", file=sys.stderr)
        return 2
    session = Session(args.port, args.baud, args.timeout, args.dry_run)
    try:
        if args.subcommand == "idn":
            return cmd_idn(session, args)
        if args.subcommand == "query":
            return cmd_query(session, args)
        if args.subcommand == "errors":
            return cmd_errors(session, args)
        if args.subcommand == "apply":
            return cmd_apply(session, args)
        if args.subcommand == "output":
            return cmd_output(session, args)
        if args.subcommand == "arb":
            return cmd_arb(session, args)
        if args.subcommand == "off":
            return cmd_off(session, args)
        if args.subcommand == "snapshot":
            return cmd_snapshot(session, args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
