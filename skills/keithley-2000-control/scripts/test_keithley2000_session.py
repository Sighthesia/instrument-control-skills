from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
CAPTURES = ROOT / "assets" / "captures"
sys.path.insert(0, str(SCRIPTS))

import keithley2000_session as session_module  # noqa: E402
from keithley2000_session import Session, SessionError  # noqa: E402


class FakeConnection:
    """Byte-oriented stand-in for a serial port."""

    def __init__(self, blob: bytes = b"") -> None:
        self.buffer = bytearray(blob)
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    def flush(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        chunk = bytes(self.buffer[:size])
        del self.buffer[:size]
        return chunk

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class ImportPolicyTests(unittest.TestCase):
    def test_no_module_level_pyserial_import(self):
        tree = ast.parse((SCRIPTS / "keithley2000_session.py").read_text())
        for node in tree.body:
            if isinstance(node, ast.Import):
                self.assertNotIn("serial", [alias.name for alias in node.names])
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "serial")

    def test_pyserial_missing_is_reported_lazily(self):
        with mock.patch.dict(sys.modules, {"serial": None}):
            with self.assertRaises(SessionError):
                session_module._serial_module()


class DryRunTests(unittest.TestCase):
    def test_send_records_exact_cr_terminated_bytes(self):
        session = Session(dry_run=True)
        session.write("*IDN?")
        session.write(":FUNCtion?")
        self.assertEqual(session.sent, [b"*IDN?\r", b":FUNCtion?\r"])
        self.assertIsNone(session._connection)
        session.close()

    def test_query_never_reads_in_dry_run(self):
        session = Session(dry_run=True)
        self.assertEqual(session.query(":FUNCtion?"), b"")
        self.assertEqual(session.sent, [b":FUNCtion?\r"])
        session.close()

    def test_read_is_blocked_for_current_without_confirmation(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "CURR:DC"])
        with self.assertRaises(SessionError):
            session_module.cmd_read(session, args)
        session.close()

    def test_dry_run_read_plans_configure_then_reads(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "VOLT:DC", "--count", "2",
             "--json", "--elements", "READ,CHAN,UNIT"])
        self.assertEqual(session_module.cmd_read(session, args), 0)
        self.assertEqual(
            session.sent,
            [b":CONFigure:VOLT:DC\r",
             b":FORMat:ELEments READ,CHAN,UNIT\r",
             b":FUNCtion?\r",
             b":SENSe:VOLTage:DC:RANGe?\r",
             b":SENSe:VOLTage:DC:RANGe:AUTO?\r",
             b":READ?\r",
             b":READ?\r"],
        )
        session.close()

    def test_frequency_plan_uses_threshold_range_not_range(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "FREQ"])
        self.assertEqual(session_module.cmd_read(session, args), 0)
        self.assertEqual(
            session.sent,
            [b":CONFigure:FREQ\r",
             b":FUNCtion?\r",
             b":SENSe:FREQuency:THReshold:VOLTage:RANGe?\r",
             b":READ?\r"],
        )
        self.assertNotIn(b":SENSe:FREQuency:RANGe?\r", session.sent)
        session.close()

    def test_temperature_plan_uses_unit_subsystem(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "TEMP"])
        self.assertEqual(session_module.cmd_read(session, args), 0)
        self.assertIn(b":SENSe:TEMPerature:TCouple:TYPE?\r", session.sent)
        self.assertIn(b":UNIT:TEMPerature?\r", session.sent)
        self.assertNotIn(b":SENSe:TEMPerature:UNIT?\r", session.sent)
        session.close()

    def test_no_configure_only_reads_current_setup(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "VOLT:DC", "--no-configure"])
        self.assertEqual(session_module.cmd_read(session, args), 0)
        self.assertEqual(
            session.sent,
            [b":FUNCtion?\r",
             b":SENSe:VOLTage:DC:RANGe?\r",
             b":SENSe:VOLTage:DC:RANGe:AUTO?\r",
             b":READ?\r"],
        )
        session.close()

    def test_range_is_rejected_for_functions_without_one(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "TEMP", "--range", "1"])
        with self.assertRaises(SessionError):
            session_module.cmd_read(session, args)
        self.assertEqual(session.sent, [])
        session.close()

    def test_temperature_unit_mapping(self):
        def readback(value: str) -> dict:
            return {"readbacks": {":UNIT:TEMPerature?": {
                "configuration": {"value": value}}}}

        self.assertEqual(session_module._temperature_unit(readback("C")), "C")
        self.assertEqual(session_module._temperature_unit(readback("FAR")), "F")
        self.assertEqual(session_module._temperature_unit(readback("K")), "K")
        self.assertIsNone(session_module._temperature_unit(readback("?")))
        self.assertIsNone(session_module._temperature_unit({}))

    def test_walk_requires_open_input_confirmation(self):
        session = Session(dry_run=False)
        args = session_module._build_parser().parse_args(["walk", "--json"])
        with self.assertRaises(SessionError):
            session_module.cmd_walk(session, args)
        session.close()


class GuardTests(unittest.TestCase):
    def test_reset_is_refused_by_default(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError):
            session.write("*RST")
        session.close()

    def test_continuous_initiation_needs_explicit_permission(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError):
            session.write(":INITiate:CONTinuous ON")
        allowed = Session(dry_run=True, allow_state_change=True)
        allowed.write(":INITiate:CONTinuous ON")
        self.assertEqual(allowed.sent, [b":INITiate:CONTinuous ON\r"])
        session.close()
        allowed.close()

    def test_invalid_baud_and_timeout(self):
        with self.assertRaises(SessionError):
            Session(baud=300)
        with self.assertRaises(SessionError):
            Session(timeout=0)


class FramingTests(unittest.TestCase):
    def _session(self, blob: bytes) -> Session:
        session = Session(dry_run=False)
        session._connection = FakeConnection(blob)
        return session

    def test_query_reads_one_cr_framed_response(self):
        session = self._session(b"+2.52731000E+01\r+2.52732000E+01\r")
        first = session.query(":READ?")
        second = session.query(":READ?")
        self.assertEqual(first, b"+2.52731000E+01\r")
        self.assertEqual(second, b"+2.52732000E+01\r")
        self.assertEqual(session._connection.written, b":READ?\r:READ?\r")
        session.close()

    def test_lf_terminated_response_is_accepted(self):
        session = self._session(b'0,"No error"\n')
        self.assertEqual(session.query(":SYSTem:ERRor?"), b'0,"No error"\n')
        session.close()

    def test_timeout_marks_session_desynchronised(self):
        session = self._session(b"")
        with self.assertRaises(SessionError):
            session.query(":READ?")
        with self.assertRaises(SessionError):
            session.query(":READ?")
        session.close()

    def test_drain_errors_reads_until_empty_record(self):
        session = self._session(b'-213,"Init ignored"\r0,"No error"\r')
        queue = session.drain_errors()
        self.assertEqual([record["code"] for record in queue["records"]], [-213, 0])
        self.assertTrue(queue["drained"])
        self.assertEqual(session._connection.written,
                         b":SYSTem:ERRor?\r:SYSTem:ERRor?\r")
        session.close()

    def test_exchange_log_hashes_are_recorded(self):
        session = self._session(b'0,"No error"\r')
        session.query(":SYSTem:ERRor?")
        received = [entry for entry in session.exchange if entry["direction"] == "rx"]
        self.assertEqual(len(received), 1)
        self.assertEqual(len(received[0]["sha256"]), 64)
        session.close()

    def test_save_log_writes_session_record(self):
        session = self._session(b'0,"No error"\r')
        session.query(":SYSTem:ERRor?")
        with tempfile.TemporaryDirectory() as tmp:
            path = session.save_log(Path(tmp) / "session.json")
            payload = json.loads(path.read_text())
        self.assertEqual(payload["tx_terminator"], "CR (0x0D)")
        self.assertEqual(payload["sent"], [":SYSTem:ERRor?".encode().hex() + "0d"])
        session.close()


class CliTests(unittest.TestCase):
    def _main(self, argv: list[str]) -> int:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = session_module.main(argv)
        return code

    def test_dry_run_identify(self):
        self.assertEqual(self._main(["--dry-run", "identify"]), 0)

    def test_current_read_without_confirmation_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code = self._main(["--dry-run", "read", "--function", "CURR:DC"])
        self.assertEqual(code, 2)

    def test_walk_without_confirmation_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code = self._main(["walk"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
