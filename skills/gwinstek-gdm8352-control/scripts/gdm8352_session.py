#!/usr/bin/env python3
"""Read-only live transport helper for the GW Instek GDM-8352.

``pyserial`` is imported lazily and only when a real port is opened;
``--dry-run`` prints the exact bytes that would be sent and never imports it.

Safety boundary: this helper sends only the read-only queries registered in
``gdm8352_protocol.QUERY_SPECS``.  Every setter or mode command (``CONF:*``
without ``?``, ``SYST:BEEP:STAT 0``, ``*RST``, ``*CLS``, calibration, display
and local/remote commands) is refused before a byte reaches the port.

Transport facts from the verified unit (2026-11-19, firmware 1.00): USB
CDC-ACM VID:PID ``2184:003b``, responses terminated by CR LF, and the CDC baud
rate is ignored by the instrument.  The default port is ``/dev/ttyACM0``.

The lazy-import/dry-run transport shape follows this repository's
``skills/gwinstek-gpd4303s-control/scripts/gpd4303s_session.py`` (same project,
https://github.com/Sighthesia/instrument-control-skills).
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
from gdm8352_protocol import (  # noqa: E402
    DEFAULT_BAUD,
    DOCUMENTED_BAUD_RATES,
    INCOMPLETE,
    INVALID,
    MEASUREMENT_FUNCTIONS,
    UNSUPPORTED,
    CommandRefused,
    build_query,
    parse_response,
    resolve_query,
    response_failure,
)

DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_TIMEOUT_S = 2.0
# A read-only query is safe to repeat once after a timeout.  The input buffer is
# drained before each attempt so a late reply is never paired with the next
# command.
MAX_ATTEMPTS = 2
FAILURE_STATUSES = frozenset({INVALID, INCOMPLETE, UNSUPPORTED})


class ResponseTimeout(RuntimeError):
    """No bytes arrived within the configured timeout."""


def _slug(command: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in command).strip("_")


class Session:
    """One transport session; every query is paired with exactly one response."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT_S,
        dry_run: bool = False,
        transport: Any | None = None,
        capture_dir: Path | None = None,
        attempts: int = MAX_ATTEMPTS,
    ) -> None:
        if baud not in DOCUMENTED_BAUD_RATES:
            raise ValueError(
                f"baud must be one of {DOCUMENTED_BAUD_RATES}; the manual documents no other rate"
            )
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self.port = port
        self.baud = baud
        self.timeout = float(timeout)
        self.dry_run = dry_run
        self.attempts = attempts
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self._transport = transport
        self._serial = None
        self._exchange_index = 0
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
                    "pyserial is required for live transport; install it with "
                    "'python3 -m pip install pyserial', or use --dry-run"
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

    def _drain(self) -> None:
        """Discard stale input so a late reply cannot masquerade as this one."""

        reset = getattr(self._open(), "reset_input_buffer", None)
        if reset is None:
            return
        try:
            reset()
        except Exception:  # pragma: no cover - a transport without a real FIFO
            pass

    def _set_timeout(self, seconds: float) -> None:
        try:
            self._open().timeout = seconds
        except AttributeError:  # pragma: no cover - a transport without timeouts
            pass

    def _read_response(self) -> bytes:
        """Read one CR LF-terminated response, tolerating a bare CR or LF."""

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
                # Wait briefly for the LF of CR LF without stalling a CR-only
                # instrument.
                self._set_timeout(0.1)
                try:
                    following = port.read(1)
                finally:
                    self._set_timeout(self.timeout)
                if not following:
                    break
                buffer += following
                if following == b"\n":
                    break
        if not buffer:
            raise ResponseTimeout(f"{self.port}: no response within {self.timeout:g}s")
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

    def exchange(self, command: str) -> dict[str, Any]:
        """Send one allowed query and parse its response."""

        spec, _parameter = resolve_query(command)
        request = build_query(command)
        record: dict[str, Any] = {
            "command": spec.canonical,
            "request_bytes": request,
            "response": None,
            "artifact": None,
            "attempts": 0,
        }
        if self.dry_run:
            record["dry_run"] = True
            return record

        port = self._open()
        last_timeout: ResponseTimeout | None = None
        for attempt in range(1, self.attempts + 1):
            record["attempts"] = attempt
            self._drain()
            port.write(request)
            try:
                response = self._read_response()
            except ResponseTimeout as exc:
                last_timeout = exc
                continue
            record["response"] = response
            record["artifact"] = parse_response(response, spec.canonical)
            self._capture(spec.canonical, request, response)
            return record

        reason = (
            f"no response within {self.timeout:g}s after {record['attempts']} attempt(s)"
        )
        record["error"] = str(last_timeout) if last_timeout else reason
        record["artifact"] = response_failure(spec.canonical, INCOMPLETE, reason)
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
    if record.get("dry_run"):
        print(f"DRY-RUN SEND: {record['request_bytes']!r}")
        return
    print(f"{record['command']} -> {record['response']!r}")


def _emit(artifact: dict[str, Any]) -> None:
    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")


def _failure(artifact: dict[str, Any] | None) -> bool:
    if artifact is None:
        return False
    return artifact.get("integrity", {}).get("status") in FAILURE_STATUSES


def cmd_idn(session: Session, args: argparse.Namespace) -> int:
    record = session.exchange("*IDN?")
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _failure(record["artifact"]) else 0


def cmd_measure(session: Session, args: argparse.Namespace) -> int:
    function = MEASUREMENT_FUNCTIONS[args.function]
    record = session.exchange(function.query)
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _failure(record["artifact"]) else 0


def cmd_read(session: Session, args: argparse.Namespace) -> int:
    record = session.exchange("READ?")
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _failure(record["artifact"]) else 0


def cmd_raw(session: Session, args: argparse.Namespace) -> int:
    record = session.exchange(args.command_text)
    _print_exchange(record)
    if record["artifact"] is None:
        return 0
    _emit(record["artifact"])
    return 1 if _failure(record["artifact"]) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_BAUD, choices=DOCUMENTED_BAUD_RATES,
        help="USB CDC ignores this; it matters only for the RS232 interface",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the exact request bytes without importing pyserial or opening a port",
    )
    parser.add_argument(
        "--capture-dir", type=Path, default=None,
        help="write raw response bytes and a captures.jsonl index",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("idn", help="send *IDN? and parse the identity")

    p_measure = sub.add_parser("measure", help="take one first-display measurement")
    p_measure.add_argument(
        "--function", required=True, choices=sorted(MEASUREMENT_FUNCTIONS),
        help="measurement function key",
    )

    sub.add_parser("read", help="send READ? and separate the two display values")

    p_raw = sub.add_parser("raw", help="send one allowed read-only query")
    p_raw.add_argument("command_text", help="for example 'SYST:BEEP:STAT?'")

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
        if args.subcommand == "measure":
            return cmd_measure(session, args)
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