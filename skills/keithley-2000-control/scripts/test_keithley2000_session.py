from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
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

    def test_read_rejects_unsupported_settings_before_writing(self):
        cases = [
            (["--function", "FREQ", "--nplc", "1"], "NPLC"),
            (["--function", "CONT", "--digits", "6"], "DIGits"),
        ]
        for argv, message in cases:
            with self.subTest(argv=argv):
                session = Session(dry_run=True)
                args = session_module._build_parser().parse_args(
                    ["--dry-run", "read", *argv])
                with self.assertRaises(SessionError) as caught:
                    session_module.cmd_read(session, args)
                self.assertIn(message, str(caught.exception))
                self.assertEqual(session.sent, [])
                session.close()

    def test_walk_skips_rate_for_functions_without_nplc(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "walk", "--nplc", "1", "--digits", "6"])
        self.assertEqual(session_module.cmd_walk(session, args), 0)
        sent = b"".join(session.sent)
        self.assertNotIn(b":SENSe:FREQuency:NPLCycles", sent)
        self.assertNotIn(b":SENSe:CONTinuity:NPLCycles", sent)
        self.assertIn(b":SENSe:VOLTage:DC:NPLCycles 1\r", sent)
        session.close()

    def test_walk_requires_open_input_confirmation(self):
        session = Session(dry_run=False)
        args = session_module._build_parser().parse_args(["walk", "--json"])
        with self.assertRaises(SessionError):
            session_module.cmd_walk(session, args)
        session.close()


    def test_config_plan_sets_rate_digits_filter_and_rel(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "config", "--function", "VOLT:DC",
             "--nplc", "0.1", "--digits", "6",
             "--filter", "on", "--filter-type", "moving", "--filter-count", "5",
             "--rel", "on", "--rel-reference", "0.05"])
        self.assertEqual(session_module.cmd_config(session, args), 0)
        self.assertEqual(
            session.sent,
            [b':FUNCtion "VOLT:DC"\r',
             b':SENSe:VOLTage:DC:NPLCycles 0.1\r',
             b':SENSe:VOLTage:DC:DIGits 6\r',
             b':SENSe:VOLTage:DC:AVERage:TCONtrol moving\r',
             b':SENSe:VOLTage:DC:AVERage:COUNt 5\r',
             b':SENSe:VOLTage:DC:AVERage:STATe ON\r',
             b':SENSe:VOLTage:DC:REFerence 0.05\r',
             b':SENSe:VOLTage:DC:REFerence:STATe ON\r',
             b':FUNCtion?\r',
             b':SENSe:VOLTage:DC:NPLCycles?\r',
             b':SENSe:VOLTage:DC:DIGits?\r',
             b':SENSe:VOLTage:DC:AVERage:STATe?\r',
             b':SENSe:VOLTage:DC:AVERage:TCONtrol?\r',
             b':SENSe:VOLTage:DC:AVERage:COUNt?\r',
             b':SENSe:VOLTage:DC:REFerence?\r',
             b':SENSe:VOLTage:DC:REFerence:STATe?\r'],
        )
        session.close()

    def test_config_dry_run_needs_a_function(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(["--dry-run", "config"])
        with self.assertRaises(SessionError):
            session_module.cmd_config(session, args)
        self.assertEqual(session.sent, [])
        session.close()

    def test_config_rejects_unsupported_settings(self):
        cases = [
            (["--function", "FREQ", "--nplc", "1"], "NPLC"),
            (["--function", "CONT", "--filter", "on"], "filter"),
            (["--function", "CONT", "--rel", "on"], "REL"),
            (["--function", "VOLT:DC", "--digits", "8"], "DIGits"),
            (["--function", "VOLT:DC", "--filter-count", "0"], "filter count"),
        ]
        for argv, message in cases:
            with self.subTest(argv=argv):
                session = Session(dry_run=True)
                args = session_module._build_parser().parse_args(
                    ["--dry-run", "config", *argv])
                with self.assertRaises(SessionError) as caught:
                    session_module.cmd_config(session, args)
                self.assertIn(message, str(caught.exception))
                self.assertEqual(session.sent, [])
                session.close()

    def test_config_current_function_needs_confirmation(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "config", "--function", "CURR:DC"])
        with self.assertRaises(SessionError):
            session_module.cmd_config(session, args)
        self.assertEqual(session.sent, [])
        session.close()

    def test_config_current_function_with_confirmation_is_allowed(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "config", "--function", "CURR:DC",
             "--allow-current", "--nplc", "1"])
        self.assertEqual(session_module.cmd_config(session, args), 0)
        self.assertIn(b":SENSe:CURRent:DC:NPLCycles 1\r", session.sent)
        session.close()

    def test_constants_dry_run_queries_the_documented_set(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(["--dry-run", "constants"])
        self.assertEqual(session_module.cmd_constants(session, args), 0)
        self.assertEqual(
            session.sent,
            [(query + "\r").encode() for _, query in session_module.CONSTANT_QUERIES],
        )
        session.close()

    def test_constants_are_interpreted(self):
        raw = {
            "identity": b"KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  \r",
            "options": b"0,0\r",
            "scpi_version": b"1991.0\r",
            "line_frequency": b"50\r",
            "front_rear_switch": b"1\r",
            "power_on_setup": b"SAV0\r",
            "autozero": b"1\r",
            "calibration_count": b"6\r",
            "calibration_date": b"2008,06,20\r",
            "calibration_due": b"2009,06,20\r",
            "calibration_lock": b"0\r",
        }
        constants = session_module._interpret_constants(raw)
        self.assertEqual(constants["identity"]["serial"], "0944865")
        self.assertEqual(constants["identity"]["firmware_digital"], "A17")
        self.assertEqual(constants["options"], "0,0")
        self.assertEqual(constants["line_frequency_hz"], 50.0)
        self.assertEqual(constants["input_switch"], "front")
        self.assertTrue(constants["autozero"])
        self.assertEqual(constants["calibration"]["count"], 6)
        self.assertEqual(constants["calibration"]["lock"], "locked")
        self.assertTrue(constants["calibration"]["due_in_past"])
        self.assertEqual(constants["calibration"]["date"], "2008,06,20")

    def test_zero_flag_value_is_off(self):
        zero = session_module.parse_config(b"0\r")["configuration"]
        one = session_module.parse_config(b"1\r")["configuration"]
        self.assertFalse(session_module._flag({"configuration": zero}))
        self.assertTrue(session_module._flag({"configuration": one}))

    def test_calibration_due_comparison(self):
        self.assertTrue(session_module._calibration_due_in_past(
            "2009,06,20", date(2026, 10, 20)))
        self.assertFalse(session_module._calibration_due_in_past(
            "2030,01,01", date(2026, 10, 20)))
        self.assertIsNone(session_module._calibration_due_in_past("not-a-date"))

    def test_read_plan_records_rate_and_digits_readbacks(self):
        session = Session(dry_run=True)
        args = session_module._build_parser().parse_args(
            ["--dry-run", "read", "--function", "VOLT:DC",
             "--nplc", "0.5", "--digits", "5"])
        self.assertEqual(session_module.cmd_read(session, args), 0)
        self.assertEqual(session.sent[:3],
                         [b":CONFigure:VOLT:DC\r",
                          b":SENSe:VOLTage:DC:NPLCycles 0.5\r",
                          b":SENSe:VOLTage:DC:DIGits 5\r"])
        self.assertIn(b":SENSe:VOLTage:DC:NPLCycles?\r", session.sent)
        self.assertIn(b":SENSe:VOLTage:DC:DIGits?\r", session.sent)
        self.assertEqual(session.sent[-1], b":READ?\r")
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


    def test_abbreviated_calibration_write_is_refused(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError):
            session.write(":CAL:PROT:CODE 'KI002000'")
        self.assertEqual(session.sent, [])
        session.close()

    def test_calculate_is_not_mistaken_for_calibration(self):
        session = Session(dry_run=True)
        session.write(":CALCulate1:STATe ON")
        self.assertEqual(session.sent, [b":CALCulate1:STATe ON\r"])
        session.close()

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

    def test_unblock_sends_device_clear_and_restores_link(self):
        session = self._session(b'KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  \r')
        self.assertEqual(session.unblock(),
                         b'KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  \r')
        self.assertEqual(session._connection.written, b"\x03*IDN?\r")
        self.assertFalse(session._desynced)
        session.close()

    def test_unblock_clears_a_timed_out_session(self):
        session = self._session(b"")
        with self.assertRaises(SessionError):
            session.query(":FETCh?")
        self.assertTrue(session._desynced)
        session._connection.buffer.extend(b'KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  \r')
        self.assertTrue(session.unblock().startswith(b"KEITHLEY"))
        session.close()

    def test_unblock_dry_run_records_device_clear(self):
        session = Session(dry_run=True)
        self.assertEqual(session.unblock(), b"")
        self.assertEqual(session.sent, [b"\x03"])
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
