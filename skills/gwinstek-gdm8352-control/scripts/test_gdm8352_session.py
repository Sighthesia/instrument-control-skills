from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gdm8352_protocol import (  # noqa: E402
    COMPLETE,
    INCOMPLETE,
    MEASUREMENT_FUNCTIONS,
    UNVERIFIED,
)
from gdm8352_session import (  # noqa: E402
    DEFAULT_BAUD,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_S,
    FAILURE_STATUSES,
    MAX_ATTEMPTS,
    CommandRefused,
    ResponseTimeout,
    Session,
    cmd_idn,
    cmd_measure,
    cmd_raw,
    cmd_read,
    main,
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ReplayTransport:
    """A local stand-in for pyserial that answers from saved bytes."""

    def __init__(self, responses: dict[bytes, bytes]) -> None:
        self.responses = dict(responses)
        self.writes: list[bytes] = []
        self.events: list[tuple[str, bytes | None]] = []
        self.reset_calls = 0
        self.timeout = 1.0
        self.closed = False
        self._pending = bytearray()

    def reset_input_buffer(self) -> None:
        self.reset_calls += 1
        self.events.append(("reset", None))

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))
        self.events.append(("write", bytes(data)))
        self._pending += self.responses.get(bytes(data), b"")

    def read(self, size: int = 1) -> bytes:
        if not self._pending:
            return b""
        chunk = bytes(self._pending[:size])
        del self._pending[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


def offline_session(responses: dict[bytes, bytes], **kwargs) -> tuple[Session, ReplayTransport]:
    transport = ReplayTransport(responses)
    session = Session(transport=transport, **kwargs)
    return session, transport


class DryRunTests(unittest.TestCase):
    def test_dry_run_prints_exact_bytes_and_writes_nothing(self):
        session, transport = offline_session({}, dry_run=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_idn(session, Namespace())
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'*IDN?\\r\\n'", buffer.getvalue())
        self.assertEqual(transport.writes, [])
        self.assertEqual(transport.reset_calls, 0)

    def test_dry_run_does_not_import_pyserial(self):
        real_import = builtins.__import__

        def guarded(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "serial":
                raise AssertionError("--dry-run must not import pyserial")
            return real_import(name, globals, locals, fromlist, level)

        buffer = io.StringIO()
        with mock.patch("builtins.__import__", side_effect=guarded):
            with contextlib.redirect_stdout(buffer):
                code = main(["--dry-run", "--port", "/dev/does-not-exist", "idn"])
        self.assertEqual(code, 0)
        self.assertIn("b'*IDN?\\r\\n'", buffer.getvalue())

    def test_cli_dry_run_measure_dc_voltage(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--dry-run", "measure", "--function", "dc-voltage"])
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'MEAS:VOLT:DC?\\r\\n'", buffer.getvalue())

    def test_cli_dry_run_raw_beep(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--dry-run", "raw", "SYST:BEEP:STAT?"])
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'SYST:BEEP:STAT?\\r\\n'", buffer.getvalue())

    def test_cli_dry_run_temperature_parameter(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--dry-run", "raw", "MEAS:TEMP:TCO? J"])
        self.assertEqual(code, 0)
        self.assertIn("b'MEAS:TEMP:TCO? J\\r\\n'", buffer.getvalue())

    def test_exchange_dry_run_returns_no_artifact(self):
        session, transport = offline_session({}, dry_run=True)
        record = session.exchange("READ?")
        self.assertTrue(record["dry_run"])
        self.assertIsNone(record["artifact"])
        self.assertEqual(record["request_bytes"], b"READ?\r\n")
        self.assertEqual(transport.writes, [])


class ReplayTests(unittest.TestCase):
    def test_verified_idn(self):
        session, transport = offline_session({b"*IDN?\r\n": fixture("idn.txt")})
        record = session.exchange("*IDN?")
        self.assertEqual(transport.writes, [b"*IDN?\r\n"])
        self.assertEqual(record["attempts"], 1)
        self.assertEqual(record["response"], fixture("idn.txt"))
        self.assertEqual(record["artifact"]["status"], COMPLETE)
        self.assertEqual(record["artifact"]["serial"], "GEP848232")
        self.assertEqual(transport.reset_calls, 1)

    def test_verified_dc_voltage(self):
        session, transport = offline_session(
            {b"MEAS:VOLT:DC?\r\n": fixture("meas-volt-dc.txt")}
        )
        record = session.exchange("MEAS:VOLT:DC?")
        self.assertEqual(record["artifact"]["status"], COMPLETE)
        self.assertEqual(record["artifact"]["value_decimal"], "0.010466")
        self.assertEqual(record["artifact"]["unit"], "V")

    def test_verified_dc_current(self):
        session, _transport = offline_session(
            {b"MEAS:CURR:DC?\r\n": fixture("meas-curr-dc.txt")}
        )
        record = session.exchange("MEAS:CURR:DC?")
        self.assertEqual(record["artifact"]["status"], COMPLETE)
        self.assertEqual(record["artifact"]["quantity"], "current")

    def test_verified_read_is_unverified_with_two_displays(self):
        session, _transport = offline_session({b"READ?\r\n": fixture("read-two-display.txt")})
        record = session.exchange("READ?")
        self.assertEqual(record["artifact"]["status"], UNVERIFIED)
        self.assertEqual(record["artifact"]["first_display"]["raw_text"], "+0.00023E-02")
        self.assertEqual(record["artifact"]["second_display"]["raw_text"], "+0.00000E+00")
        self.assertEqual(record["artifact"]["second_display"]["unit_status"], UNVERIFIED)

    def test_verified_no_beep(self):
        session, _transport = offline_session(
            {b"SYST:BEEP:STAT?\r\n": fixture("syst-beep-stat-no-beep.txt")}
        )
        record = session.exchange("SYST:BEEP:STAT?")
        self.assertEqual(record["artifact"]["mode"], "no-beep")

    def test_verified_command_error(self):
        session, _transport = offline_session(
            {b"SYST:ERR?\r\n": fixture("syst-err-command-error.txt")}
        )
        record = session.exchange("SYST:ERR?")
        self.assertEqual(record["artifact"]["message"], "Command error")
        self.assertEqual(record["artifact"]["source"], "observed")

    def test_temperature_parameter_is_preserved_on_the_wire(self):
        session, transport = offline_session(
            {b"MEAS:TEMP:TCO? J\r\n": b"+0.02667E+03\r\n"}
        )
        record = session.exchange("MEAS:TEMP:TCO? J")
        self.assertEqual(transport.writes, [b"MEAS:TEMP:TCO? J\r\n"])
        self.assertEqual(record["artifact"]["function"], "temperature")

    def test_reset_input_buffer_precedes_every_write(self):
        session, transport = offline_session({b"*IDN?\r\n": fixture("idn.txt")})
        session.exchange("*IDN?")
        self.assertEqual(
            transport.events,
            [("reset", None), ("write", b"*IDN?\r\n")],
        )

    def test_response_without_terminator_is_incomplete(self):
        session, _transport = offline_session(
            {b"MEAS:VOLT:DC?\r\n": b"+0.10466E-01"}
        )
        record = session.exchange("MEAS:VOLT:DC?")
        self.assertEqual(record["artifact"]["status"], INCOMPLETE)


class TimeoutTests(unittest.TestCase):
    def test_timeout_retries_and_reports_incomplete(self):
        session, transport = offline_session({}, timeout=0.01)
        record = session.exchange("MEAS:VOLT:DC?")
        self.assertEqual(record["attempts"], MAX_ATTEMPTS)
        self.assertEqual(len(transport.writes), MAX_ATTEMPTS)
        self.assertEqual(transport.reset_calls, MAX_ATTEMPTS)
        self.assertIsNone(record["response"])
        self.assertEqual(record["artifact"]["status"], INCOMPLETE)
        self.assertEqual(record["artifact"]["integrity"]["raw_bytes"], 0)
        self.assertIn("no response within", record["error"])

    def test_timeout_failure_is_counted_as_failure(self):
        self.assertEqual(FAILURE_STATUSES, frozenset({"INVALID", "INCOMPLETE", "UNSUPPORTED"}))

    def test_response_timeout_is_raisable_directly(self):
        session, _transport = offline_session({})
        with self.assertRaises(ResponseTimeout):
            session._read_response()


class RefusalTests(unittest.TestCase):
    def test_state_changing_commands_never_reach_the_port(self):
        refused = [
            "*RST",
            "*CLS",
            "CONF:VOLT:DC 1",
            "SYST:BEEP:STAT 0",
            "SYST:BEEP",
            "CAL:VOLT",
            "OUT1",
            "DISP ON",
            "MEAS:VOLT:DC?;*RST",
            "CONF?",
        ]
        session, transport = offline_session({})
        for command in refused:
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    session.exchange(command)
        self.assertEqual(transport.writes, [])
        self.assertEqual(transport.reset_calls, 0)

    def test_cli_refuses_a_write_before_opening_the_port(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = main(["--port", "/dev/does-not-exist", "raw", "*RST"])
        self.assertEqual(code, 2)
        self.assertIn("refused", buffer.getvalue())

    def test_unknown_query_is_refused(self):
        session, _transport = offline_session({})
        for command in ("SYST:ERR", "CONF", "MEAS:VOLT?", "OUT1?", "HELP?"):
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    session.exchange(command)


class CliOutputTests(unittest.TestCase):
    def test_cmd_idn_emits_json(self):
        session, _transport = offline_session({b"*IDN?\r\n": fixture("idn.txt")})
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_idn(session, Namespace())
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue().split("\n", 1)[1])
        self.assertEqual(payload["kind"], "identity")
        self.assertEqual(payload["status"], COMPLETE)

    def test_cmd_measure_selects_the_function(self):
        session, transport = offline_session(
            {b"MEAS:VOLT:DC?\r\n": fixture("meas-volt-dc.txt")}
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_measure(session, Namespace(function="dc-voltage"))
        self.assertEqual(code, 0)
        self.assertEqual(transport.writes, [b"MEAS:VOLT:DC?\r\n"])
        self.assertIn('"value_decimal": "0.010466"', buffer.getvalue())

    def test_cmd_read_exits_zero_for_unverified_values(self):
        session, _transport = offline_session({b"READ?\r\n": fixture("read-two-display.txt")})
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_read(session, Namespace())
        self.assertEqual(code, 0)
        self.assertIn("UNVERIFIED", buffer.getvalue())

    def test_cmd_raw_beep(self):
        session, _transport = offline_session(
            {b"SYST:BEEP:STAT?\r\n": fixture("syst-beep-stat-no-beep.txt")}
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_raw(session, Namespace(command_text="SYST:BEEP:STAT?"))
        self.assertEqual(code, 0)
        self.assertIn('"mode": "no-beep"', buffer.getvalue())

    def test_cmd_raw_surfaces_incomplete_timeout_as_exit_one(self):
        session, _transport = offline_session({}, timeout=0.01)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_raw(session, Namespace(command_text="SYST:ERR?"))
        self.assertEqual(code, 1)
        self.assertIn("INCOMPLETE", buffer.getvalue())


class CaptureTests(unittest.TestCase):
    def test_capture_writes_raw_bytes_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            session, _transport = offline_session(
                {b"*IDN?\r\n": fixture("idn.txt")}, capture_dir=Path(directory)
            )
            session.exchange("*IDN?")
            raw_files = sorted(Path(directory).glob("*.raw"))
            self.assertEqual(len(raw_files), 1)
            self.assertEqual(raw_files[0].read_bytes(), fixture("idn.txt"))

            entries = [
                json.loads(line)
                for line in (Path(directory) / "captures.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["command"], "*IDN?")
            self.assertEqual(entries[0]["request_base64"], "KklETj8NCg==")
            self.assertEqual(
                entries[0]["response_sha256"],
                hashlib.sha256(fixture("idn.txt")).hexdigest(),
            )

    def test_no_capture_directory_means_no_files(self):
        session, _transport = offline_session({b"*IDN?\r\n": fixture("idn.txt")})
        session.exchange("*IDN?")
        self.assertIsNone(session.capture_dir)


class SessionStateTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(DEFAULT_PORT, "/dev/ttyACM0")
        self.assertEqual(DEFAULT_BAUD, 115200)
        self.assertEqual(DEFAULT_TIMEOUT_S, 2.0)
        self.assertEqual(MAX_ATTEMPTS, 2)
        session = Session(transport=ReplayTransport({}))
        self.assertEqual(session.port, "/dev/ttyACM0")

    def test_baud_must_be_documented(self):
        with self.assertRaises(ValueError):
            Session(baud=12345)

    def test_timeout_and_attempts_are_validated(self):
        with self.assertRaises(ValueError):
            Session(timeout=0)
        with self.assertRaises(ValueError):
            Session(attempts=0)

    def test_close_is_idempotent(self):
        transport = ReplayTransport({})
        session = Session(transport=transport)
        session.close()
        session.close()
        self.assertTrue(transport.closed)

    def test_every_measurement_function_has_a_cli_choice(self):
        self.assertIn("dc-voltage", MEASUREMENT_FUNCTIONS)
        self.assertIn("temperature", MEASUREMENT_FUNCTIONS)


if __name__ == "__main__":
    unittest.main()