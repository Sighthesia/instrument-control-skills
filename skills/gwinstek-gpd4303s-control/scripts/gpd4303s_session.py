#!/usr/bin/env python3
"""Read-only live transport helper for the GW Instek GPD-4303S.

``pyserial`` is imported lazily, and ``--dry-run`` prints the exact bytes that
would be sent without opening a port.

Safety boundary: this helper sends only the read-only queries that were
exercised on real hardware (``*IDN?``, ``VSET<X>?``, ``ISET<X>?``,
``VOUT<X>?``, ``IOUT<X>?``, ``STATUS?``, ``HELP?``).  Every set/mode command is
refused before any byte reaches the port.  ``OUT1`` energises the outputs and
``OUT1?`` does not exist, so a probing write cannot be undone by the same
command; see ``SKILL.md``.

Manual: *GPD-X303S Series User Manual*, GW Instek part no. 82PD-433S0MC1,
REMOTE CONTROL chapter, PDF pp. 43-52.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpd4303s_protocol import (  # noqa: E402
    BIT_ORDERS,
    DEFAULT_BIT_ORDER,
    SCHEMA_VERSION,
    build_query,
    classify_command,
    parse_response,
)

# Manual p. 43: baud rate 9600/57600/115200, parity none, 8 data bits, 1 stop
# bit, no flow control.  The verified unit only answered at 9600.
DOCUMENTED_BAUD_RATES = (9600, 57600, 115200)
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT_S = 3.0

# The interaction set this Skill is allowed to send.  ERR? is a documented
# read-only query (manual p. 52) but lies outside the exercised set, so it is
# not sent by this helper.
ALLOWED_COMMAND_NAMES = frozenset(
    {
        "*IDN?",
        "STATUS?",
        "HELP?",
        "VSET<X>?",
        "ISET<X>?",
        "VOUT<X>?",
        "IOUT<X>?",
    }
)


class CommandRefused(RuntimeError):
    """A command was refused locally; nothing was written to the port."""


def _slug(command: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in command).strip("_")


class Session:
    """One transport session; every query is paired with exactly one response."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT_S,
        dry_run: bool = False,
        transport: Any | None = None,
        capture_dir: Path | None = None,
    ) -> None:
        if baud not in DOCUMENTED_BAUD_RATES:
            raise ValueError(
                f"baud must be one of {DOCUMENTED_BAUD_RATES}; the manual documents no other rate"
            )
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.dry_run = dry_run
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self._transport = transport
        self._serial = None
        self._exchange_index = 0
        # One capture directory may receive several runs; keep their file names
        # distinct so an earlier run is never overwritten by index collision.
        self._run_id = datetime.now().strftime("%Y%m%dT%H%M%S")

    # -- transport ---------------------------------------------------------

    def _open(self):
        if self._transport is not None:
            return self._transport
        if self._serial is None:
            try:
                import serial  # type: ignore
            except ImportError as exc:  # pragma: no cover - depends on the host
                raise RuntimeError(
                    "pyserial is required for live transport; install it or use --dry-run"
                ) from exc
            self._serial = serial.Serial(
                self.port,
                self.baud,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
        return self._serial

    def _set_lookahead_timeout(self, seconds: float) -> None:
        try:
            self._open().timeout = seconds
        except AttributeError:  # pragma: no cover - a transport without timeouts
            pass

    def _read_response(self) -> bytes:
        """Read one response, stopping on LF or on a bare CR.

        HELP? answers with several CR-separated lines that end in CR LF, so the
        reader must not stop at the first CR.
        """

        port = self._open()
        buffer = bytearray()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            chunk = port.read(1)
            if not chunk:
                break
            buffer += chunk
            if chunk == b"\n":
                break
            if chunk == b"\r":
                # A bare CR may already terminate the response; wait briefly for
                # a following LF without stalling a CR-only instrument.
                self._set_lookahead_timeout(0.1)
                following = port.read(1)
                self._set_lookahead_timeout(self.timeout)
                if not following:
                    break
                buffer += following
                if following == b"\n":
                    break
        if not buffer:
            raise RuntimeError(f"{self.port}: no response within {self.timeout:g}s")
        return bytes(buffer)

    def close(self) -> None:
        target = self._transport if self._transport is not None else self._serial
        if target is None:
            return
        try:
            target.close()
        except Exception:  # pragma: no cover - close must never mask a result
            pass
        self._transport = None
        self._serial = None

    # -- exchanges ---------------------------------------------------------

    def exchange(self, command: str, *, bit_order: str = DEFAULT_BIT_ORDER) -> dict[str, Any]:
        """Send one allowed query and parse its response."""

        spec = classify_command(command)
        if not spec["known"]:
            raise CommandRefused(
                f"refusing {command!r}: not a documented GPD-4303S command"
            )
        if not spec["read_only"]:
            raise CommandRefused(
                f"refusing {command!r}: {spec['name']} changes instrument state "
                "(output, setpoint, tracking, memory, baud, or remote/local mode)"
            )
        if spec["name"] not in ALLOWED_COMMAND_NAMES:
            raise CommandRefused(
                f"refusing {command!r}: {spec['name']} is documented but was not "
                "exercised on hardware, so this helper does not send it"
            )

        request = build_query(spec["text"])
        record: dict[str, Any] = {
            "command": spec["text"],
            "request_bytes": request,
            "response": None,
            "artifact": None,
        }
        if self.dry_run:
            record["dry_run"] = True
            return record

        port = self._open()
        port.write(request)
        response = self._read_response()
        record["response"] = response
        record["artifact"] = parse_response(response, spec["text"], bit_order=bit_order)
        self._capture(spec["text"], request, response)
        return record

    def _capture(self, command: str, request: bytes, response: bytes) -> None:
        if self.capture_dir is None:
            return
        self._exchange_index += 1
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        raw_path = (
            self.capture_dir
            / f"{self._run_id}-{self._exchange_index:03d}-{_slug(command)}.raw"
        )
        raw_path.write_bytes(response)
        entry = {
            "index": self._exchange_index,
            "run_id": self._run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "port": self.port,
            "baud": self.baud,
            "command": command,
            "request_base64": base64.b64encode(request).decode("ascii"),
            "response_base64": base64.b64encode(response).decode("ascii"),
            "response_sha256": hashlib.sha256(response).hexdigest(),
            "raw_path": str(raw_path.name),
        }
        with (self.capture_dir / "captures.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _print_exchange(record: dict[str, Any]) -> None:
    command = record["command"]
    if record.get("dry_run"):
        print(f"DRY-RUN SEND: {record['request_bytes']!r}")
        return
    print(f"{command} -> {record['response']!r}")


def _emit(artifact: dict[str, Any]) -> None:
    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")


def _parse_channels(text: str) -> list[int]:
    channels = [int(part) for part in text.split(",") if part.strip()]
    if not channels or any(channel not in (1, 2, 3, 4) for channel in channels):
        raise argparse.ArgumentTypeError(
            "channels must be a comma-separated subset of 1,2,3,4 (4303S: CH1, CH2, CH3, CH4)"
        )
    return channels


def _status_failure(artifacts: list[dict[str, Any]]) -> bool:
    return any(
        artifact.get("integrity", {}).get("status") in {"INVALID", "INCOMPLETE", "UNSUPPORTED"}
        for artifact in artifacts
    )


def cmd_idn(session: Session, args) -> int:
    record = session.exchange("*IDN?")
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _status_failure([record["artifact"]]) else 0


def cmd_status(session: Session, args) -> int:
    record = session.exchange("STATUS?", bit_order=args.bit_order)
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _status_failure([record["artifact"]]) else 0


def cmd_settings(session: Session, args) -> int:
    records = []
    for channel in args.channels:
        for template in ("VSET{x}?", "ISET{x}?"):
            record = session.exchange(template.format(x=channel))
            records.append(record)
            _print_exchange(record)
    if session.dry_run:
        return 0

    artifacts = [record["artifact"] for record in records if record["artifact"]]
    failed = _status_failure(artifacts)
    if failed:
        status = "INVALID"
    elif len(artifacts) != len(records):
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": "settings-snapshot",
        "port": session.port,
        "baud": session.baud,
        "setpoints": artifacts,
        "integrity": {
            "status": status,
            "checks": [
                {
                    "name": "settings_readback",
                    "status": "pass" if len(artifacts) == len(records) else "fail",
                    "evidence": {"queries": len(records), "parsed": len(artifacts)},
                }
            ],
            "reasons": [] if len(artifacts) == len(records) else ["setpoint_readback_incomplete"],
            "parser": "gpd4303s-session/0.1.0",
        },
        "limitations": [
            "Setpoints are programmed values, not measured outputs; query VOUT<x>? and STATUS? "
            "before concluding anything about the terminals.",
        ],
    }
    _emit(snapshot)
    return 1 if failed else 0


def cmd_read(session: Session, args) -> int:
    records = []
    status_record = session.exchange("STATUS?", bit_order=args.bit_order)
    records.append(status_record)
    _print_exchange(status_record)

    for channel in args.channels:
        for template in ("VOUT{x}?", "IOUT{x}?"):
            record = session.exchange(template.format(x=channel))
            records.append(record)
            _print_exchange(record)

    if session.dry_run:
        return 0

    artifacts = [record["artifact"] for record in records if record["artifact"]]
    readings = [artifact for artifact in artifacts if artifact.get("kind") == "scalar-value"]
    status_artifact = next(
        (artifact for artifact in artifacts if artifact.get("kind") == "status-record"), None
    )

    voltages = [
        reading["value"]
        for reading in readings
        if reading["quantity"] == "voltage_measurement" and reading["value"] is not None
    ]
    if len(voltages) != len(args.channels):
        output_state = "unknown"
    elif all(value == 0 for value in voltages):
        output_state = "no_output_measured"
    else:
        output_state = "voltage_present"

    if status_artifact is not None and status_artifact["decoded"]["output"] == "on":
        print(
            "WARNING: STATUS? reports the output bit as ON; the terminals may be live.",
            file=sys.stderr,
        )

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": "session-snapshot",
        "port": session.port,
        "baud": session.baud,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status_register": status_artifact,
        "readings": readings,
        "output_state": output_state,
        "integrity": {
            "status": "INVALID"
            if _status_failure(artifacts)
            else "UNVERIFIED",
            "checks": [
                {
                    "name": "reading_count",
                    "status": "pass" if len(readings) == 2 * len(args.channels) else "fail",
                    "evidence": {
                        "channels": args.channels,
                        "readings": len(readings),
                        "expected": 2 * len(args.channels),
                    },
                },
                {
                    "name": "status_context_present",
                    "status": "pass" if status_artifact is not None else "fail",
                    "evidence": {"command": "STATUS?"},
                },
            ],
            "reasons": ["v_and_i_are_sequential_reads_not_simultaneous"],
            "parser": "gpd4303s-session/0.1.0",
        },
        "limitations": [
            "VOUT<x>? and IOUT<x>? are separate queries: a voltage and its current are not "
            "simultaneous samples.",
            "A 0.000 V read-back is a meter reading with the manual's read-back accuracy "
            "(± (0.03% of reading + 10 mV), p. 56); it does not prove the terminals are "
            "de-energised.",
            "Readings are uncalibrated read-back values, not a calibration certificate.",
        ],
    }
    _emit(snapshot)
    return 1 if _status_failure(artifacts) else 0


def cmd_raw(session: Session, args) -> int:
    record = session.exchange(args.command_text, bit_order=args.bit_order)
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _status_failure([record["artifact"]]) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_BAUD, choices=DOCUMENTED_BAUD_RATES
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--capture-dir", type=Path, default=None, help="write raw response bytes and an index"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("idn", help="send *IDN? and parse the identity")

    p_status = sub.add_parser("status", help="send STATUS? and decode the bit map")
    p_status.add_argument("--bit-order", choices=BIT_ORDERS, default=DEFAULT_BIT_ORDER)

    p_settings = sub.add_parser("settings", help="read VSET/ISET setpoints")
    p_settings.add_argument("--channels", type=_parse_channels, default=[1, 2])

    p_read = sub.add_parser("read", help="read STATUS? and VOUT/IOUT readings")
    p_read.add_argument("--channels", type=_parse_channels, default=[1, 2])
    p_read.add_argument("--bit-order", choices=BIT_ORDERS, default=DEFAULT_BIT_ORDER)

    p_raw = sub.add_parser("raw", help="send one allowed read-only query")
    p_raw.add_argument("command_text")
    p_raw.add_argument("--bit-order", choices=BIT_ORDERS, default=DEFAULT_BIT_ORDER)

    args = parser.parse_args(argv)
    session = Session(
        port=args.port,
        baud=args.baud,
        timeout=args.timeout,
        dry_run=args.dry_run,
        capture_dir=args.capture_dir,
    )
    try:
        if args.subcommand == "idn":
            return cmd_idn(session, args)
        if args.subcommand == "status":
            return cmd_status(session, args)
        if args.subcommand == "settings":
            return cmd_settings(session, args)
        if args.subcommand == "read":
            return cmd_read(session, args)
        if args.subcommand == "raw":
            return cmd_raw(session, args)
    except CommandRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
