from __future__ import annotations

import ast
import contextlib
import io
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from ds1000z_protocol import encode_ieee_block, parse_measurement  # noqa: E402
from ds1000z_session import (  # noqa: E402
    DEFAULT_PORT,
    Session,
    SessionError,
    _encode_command,
    cmd_capture,
    cmd_errors,
    cmd_identity,
    cmd_measurement,
    cmd_preamble,
    cmd_query,
    cmd_screenshot,
    cmd_waveform,
    forbidden_reason,
    main,
    save_raw,
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeConnection:
    """A scripted byte source; raises socket.timeout when the script ends."""

    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)
        self.sent: list[bytes] = []
        self.closed = False

    def recv(self, size: int) -> bytes:
        if not self.chunks:
            raise socket.timeout()
        return self.chunks.pop(0)

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def close(self) -> None:
        self.closed = True


def connected_session(*chunks: bytes, **kwargs) -> Session:
    """A Session with a scripted transport; no socket is ever created."""

    session = Session(host="127.0.0.1", port=DEFAULT_PORT, idle_timeout=0.01, timeout=0.05,
                      block_timeout=0.05, write_delay=0, **kwargs)
    session._connection = FakeConnection(*chunks)
    return session


class GapConnection(FakeConnection):
    """Delivers each chunk after an idle gap, like a throttled block transfer."""

    def __init__(self, *chunks: bytes) -> None:
        super().__init__(*chunks)
        self.calls = 0

    def recv(self, size: int) -> bytes:
        self.calls += 1
        if self.calls % 2 == 0 and self.chunks:
            raise socket.timeout()
        return super().recv(size)


class FakeSession(Session):
    """A live-looking session whose responses come from a dictionary."""

    def __init__(self, responses: dict[str, bytes], *, allow_writes: bool = True) -> None:
        super().__init__(dry_run=False, allow_writes=allow_writes, write_delay=0)
        self.responses = responses
        self.commands: list[str] = []

    def send(self, command) -> None:
        payload = _encode_command(command)
        self.sent.append(payload)
        self.commands.append(payload.decode("ascii").strip())

    def query_text(self, command: str) -> bytes:
        self.send(command)
        return self.responses.get(command.strip(), b"")

    def query_block(self, command: str) -> bytes:
        self.send(command)
        return self.responses.get(command.strip(), b"")


def healthy_responses() -> dict[str, bytes]:
    return {
        "*IDN?": fixture("identity.txt"),
        ":SYSTem:ERRor?": fixture("error-queue-none.txt"),
        ":MEASure:VPP?": b"3.040000e+00\n",
        ":MEASure:VMAX?": b"3.000000e+00\n",
        ":MEASure:VMIN?": b"-4.000000e-02\n",
        ":MEASure:VAVG?": b"1.493662e+00\n",
        ":MEASure:VRMS?": b"2.082721e+00\n",
        ":MEASure:FREQuency?": b"9.999999e+02\n",
        ":MEASure:PERiod?": b"1.000000e-03\n",
        ":MEASure:PDUTy?": b"5.039999e-01\n",
        ":WAVeform:POINts?": b"1200\n",
        ":WAVeform:PREamble?": fixture("preamble-norm.txt"),
        ":WAVeform:DATA?": fixture("waveform-norm-block.bin"),
        ":WAVeform:MODE?": b"NORM\n",
        ":WAVeform:SOURce?": b"CHAN1\n",
        ":TRIGger:STATus?": b"TD\n",
        ":CHANnel1:SCALe?": b"5.000000e-01\n",
    }


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class SessionConstructionTests(unittest.TestCase):
    def test_defaults(self):
        session = Session()
        self.assertEqual(session.port, DEFAULT_PORT)
        self.assertEqual(DEFAULT_PORT, 5555)
        self.assertFalse(session.dry_run)
        self.assertFalse(session.allow_writes)
        self.assertIsNone(session._connection)

    def test_port_range(self):
        with self.assertRaises(SessionError):
            Session(host="127.0.0.1", port=0)
        with self.assertRaises(SessionError):
            Session(host="127.0.0.1", port=65536)

    def test_negative_delay(self):
        with self.assertRaises(SessionError):
            Session(write_delay=-1)

    def test_zero_timeout(self):
        with self.assertRaises(SessionError):
            Session(timeout=0)

    def test_missing_host_without_dry_run(self):
        session = Session()
        with self.assertRaises(SessionError):
            session.query_text("*IDN?")


class CommandEncodingTests(unittest.TestCase):
    def test_appends_lf(self):
        self.assertEqual(_encode_command("*IDN?"), b"*IDN?\n")
        self.assertEqual(_encode_command("*IDN?\n"), b"*IDN?\n")
        self.assertEqual(_encode_command("*IDN?\r\n"), b"*IDN?\n")
        self.assertEqual(_encode_command(b"*IDN?"), b"*IDN?\n")

    def test_one_command_per_write(self):
        with self.assertRaises(SessionError) as ctx:
            _encode_command("*IDN?\n:STOP\n")
        self.assertIn("one command per write", str(ctx.exception))

    def test_two_commands_without_second_terminator(self):
        with self.assertRaises(SessionError):
            _encode_command(":STOP\n:RUN")

    def test_empty(self):
        with self.assertRaises(SessionError):
            _encode_command("  \n")

    def test_non_ascii(self):
        with self.assertRaises(SessionError):
            _encode_command(":SAVE \"é\"")

    def test_send_records_one_payload(self):
        session = Session(dry_run=True)
        with contextlib.redirect_stdout(io.StringIO()):
            session.send("*IDN?")
            session.send(":STOP")
        self.assertEqual(session.sent, [b"*IDN?\n", b":STOP\n"])


class ForbiddenCommandTests(unittest.TestCase):
    def test_destructive_commands_are_refused(self):
        for command in (
            "*RST",
            "*SAV",
            "*SAV 1",
            "*RCL",
            ":SAVE:WAVeform",
            ":RECAll:WAVeform 1",
            ":LAN:DHCP 1",
            ":LAN:IPADdress 10.0.0.2",
            ":SYSTem:KEY:LOCK 1",
        ):
            self.assertIsNotNone(forbidden_reason(command), command)

    def test_case_and_colon_variants(self):
        self.assertIsNotNone(forbidden_reason("*rst"))
        self.assertIsNotNone(forbidden_reason("  :save:wav  "))
        self.assertIsNotNone(forbidden_reason(":reca:wav 1"))
        self.assertIsNotNone(forbidden_reason(":lan:mac?"))

    def test_safe_commands(self):
        for command in ("*IDN?", ":RUN", ":STOP", ":WAVeform:MODE RAW", ":DISPlay:DATA?"):
            self.assertIsNone(forbidden_reason(command), command)

    def test_send_refuses_even_with_allow_writes(self):
        session = Session(dry_run=True, allow_writes=True)
        for command in ("*RST", ":SAVE:x", ":LAN:DHCP 1", ":SYSTem:KEY:LOCK 1"):
            with self.assertRaises(SessionError):
                session.send(command)
        self.assertEqual(session.sent, [])

    def test_query_refuses_without_writes_flag(self):
        session = Session(dry_run=True, allow_writes=True)
        for command in ("*RST", ":LAN:DHCP 1"):
            with self.assertRaises(SessionError):
                cmd_query(session, command)
        self.assertEqual(session.sent, [])


class WriteGatingTests(unittest.TestCase):
    def test_write_requires_flag(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError) as ctx:
            session.write(":STOP")
        self.assertIn("--allow-writes", str(ctx.exception))
        self.assertEqual(session.sent, [])

    def test_write_allowed(self):
        session = Session(dry_run=True, allow_writes=True)
        with contextlib.redirect_stdout(io.StringIO()):
            session.write(":STOP")
        self.assertEqual(session.sent, [b":STOP\n"])

    def test_write_rejects_queries(self):
        session = Session(dry_run=True, allow_writes=True)
        with self.assertRaises(SessionError):
            session.write(":WAVeform:MODE?")

    def test_query_command_needs_flag(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError):
            cmd_query(session, ":RUN")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cmd_query(session, "*IDN?"), 0)

    def test_query_write_with_flag(self):
        session = Session(dry_run=True, allow_writes=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cmd_query(session, ":RUN"), 0)
        self.assertEqual(session.sent, [b":RUN\n"])

    def test_measurement_source_is_a_write(self):
        session = Session(dry_run=True)
        with self.assertRaises(SessionError):
            cmd_measurement(session, "vpp", channel=1)
        session = Session(dry_run=True, allow_writes=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cmd_measurement(session, "vpp", channel=2), 0)
        self.assertEqual(session.sent, [b":MEASure:SOURce CHANnel2\n", b":MEASure:VPP?\n"])


class DryRunTests(unittest.TestCase):
    def test_no_socket_is_opened(self):
        def forbidden(*args, **kwargs):  # pragma: no cover - only on failure
            raise AssertionError("socket.create_connection must not be called in --dry-run")

        original = socket.create_connection
        socket.create_connection = forbidden
        try:
            code, out, _ = run_cli(["--dry-run", "--host", "10.99.0.194", "identity"])
        finally:
            socket.create_connection = original
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'*IDN?\\n'", out)

    def test_waveform_raw_dry_run_prints_state_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "wave.bin"
            code, out, _ = run_cli([
                "--dry-run", "--allow-writes", "waveform", "--out", str(out_path),
                "--mode", "RAW", "--start", "1", "--stop", "4000",
            ])
            self.assertEqual(code, 0)
            self.assertIn("b':STOP\\n'", out)
            self.assertIn("b':WAVeform:MODE RAW\\n'", out)
            self.assertIn("b':WAVeform:STARt 1\\n'", out)
            self.assertIn("b':WAVeform:STOP 4000\\n'", out)
            self.assertIn("DRY-RUN NOTE", out)
            self.assertFalse(out_path.exists())

    def test_capture_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "cap"
            code, out, _ = run_cli(["--dry-run", "capture", "--out-prefix", str(prefix)])
            self.assertEqual(code, 0)
            self.assertIn(":MEASure:VPP?", out.replace("\\n", ""))
            self.assertEqual(list(Path(tmp).iterdir()), [])


class TransportTests(unittest.TestCase):
    def test_identity_query_reads_one_line(self):
        session = connected_session(fixture("identity.txt"))
        raw = session.query_text("*IDN?")
        self.assertEqual(raw, fixture("identity.txt"))
        self.assertEqual(session.sent, [b"*IDN?\n"])
        self.assertEqual(session._connection.sent, [b"*IDN?\n"])

    def test_one_command_per_send(self):
        session = connected_session(b"TD\n", b"STOP\n")
        session.query_text(":TRIGger:STATus?")
        session.query_text(":TRIGger:STATus?")
        self.assertEqual(session.sent, [b":TRIGger:STATus?\n", b":TRIGger:STATus?\n"])

    def test_command_error_ends_at_idle_timeout(self):
        # Measured: an undefined header answers 13 bytes with no terminator.
        session = connected_session(b"command error")
        raw = session.query_text(":MEASure:RISetime?")
        self.assertEqual(raw, b"command error")
        result = parse_measurement(raw, quantity="rtime")
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIsNone(result["value"])
        self.assertTrue(result["command_error"])

    def test_command_error_measurement_command(self):
        responses = healthy_responses()
        responses[":MEASure:VPP?"] = fixture("command-error.bin")
        session = FakeSession(responses)
        code, out, _ = run_cli_with_session(session, ["measurement", "--quantity", "vpp"])
        self.assertEqual(code, 1)
        result = json.loads(out)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIsNone(result["value"])

    def test_split_chunks_are_joined(self):
        session = connected_session(b"RIGOL TECH", b"NOLOGIES,DS1074Z,", b"DS1ZA171004155,00.04.02.SP4\n")
        self.assertEqual(session.query_text("*IDN?"), fixture("identity.txt"))

    def test_block_read_is_byte_exact(self):
        block = fixture("waveform-norm-block.bin")
        session = connected_session(block[:400], block[400:])
        self.assertEqual(session.query_block(":WAVeform:DATA?"), block)

    def test_block_read_keeps_payload_and_quirk_tail(self):
        raw = fixture("screenshot-compact.bin")
        self.assertTrue(raw.endswith(b";0\n"))
        session = connected_session(raw[:50], raw[50:])
        self.assertEqual(session.query_block(":DISPlay:DATA?"), raw)

    def test_partial_block_is_returned_after_idle(self):
        raw = fixture("waveform-norm-block.bin")
        session = connected_session(raw[:600])
        self.assertEqual(session.query_block(":WAVeform:DATA?"), raw[:600])

    def test_block_read_survives_idle_gaps(self):
        # Measured: a 1152054-byte screenshot stalled after 51200 bytes, so an
        # idle gap must not end a definite-length block read.
        raw = fixture("screenshot-compact.bin")
        session = Session(host="127.0.0.1", port=DEFAULT_PORT, idle_timeout=0.01,
                          timeout=0.05, block_timeout=5.0, write_delay=0)
        session._connection = GapConnection(raw[:20], raw[20:40], raw[40:])
        self.assertEqual(session.query_block(":DISPlay:DATA?"), raw)

    def test_line_read_still_ends_on_idle(self):
        session = connected_session(b"command error")
        self.assertEqual(session.query_text(":MEASure:VPP?"), b"command error")

    def test_drain_stops_at_no_error(self):
        session = connected_session(
            fixture("error-queue-undefined.txt"),
            fixture("error-queue-none.txt"),
        )
        records = session.drain_errors()
        self.assertEqual([record["code"] for record in records], [-113, 0])
        self.assertEqual(session.sent, [b":SYSTem:ERRor?\n", b":SYSTem:ERRor?\n"])

    def test_drain_reports_command_error(self):
        session = connected_session(b"command error")
        with self.assertRaises(SessionError):
            session.drain_errors()

    def test_close(self):
        session = connected_session(b"TD\n")
        connection = session._connection
        session.close()
        self.assertTrue(connection.closed)
        self.assertIsNone(session._connection)


def run_cli_with_session(session: Session, argv: list[str]) -> tuple[int, str, str]:
    """Run a single subcommand against an injected session."""

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if argv[0] == "measurement":
            code = cmd_measurement(session, argv[argv.index("--quantity") + 1])
        else:  # pragma: no cover - other subcommands are exercised directly
            raise AssertionError(f"unexpected subcommand {argv[0]}")
    return code, out.getvalue(), err.getvalue()


class ReadOnlyCommandTests(unittest.TestCase):
    def test_identity(self):
        session = FakeSession(healthy_responses())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cmd_identity(session), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["model"], "DS1074Z")
        self.assertEqual(session.commands, ["*IDN?"])

    def test_errors_single(self):
        session = FakeSession(healthy_responses())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cmd_errors(session), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "COMPLETE")

    def test_preamble(self):
        session = FakeSession(healthy_responses())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cmd_preamble(session), 0)
        self.assertEqual(json.loads(out.getvalue())["zero_code"], 51)

    def test_measurement_no_result_exit(self):
        responses = healthy_responses()
        responses[":MEASure:VPP?"] = fixture("measurement-no-result.txt")
        session = FakeSession(responses)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cmd_measurement(session, "vpp"), 1)
        self.assertIsNone(json.loads(out.getvalue())["value"])


class WaveformCommandTests(unittest.TestCase):
    def test_reads_and_saves_exact_block(self):
        session = FakeSession(healthy_responses())
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "wave.bin"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(cmd_waveform(session, out=out_path), 0)
            result = json.loads(buffer.getvalue())
            self.assertEqual(out_path.read_bytes(), fixture("waveform-norm-block.bin"))
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["saved"]["sha256"], result["transport"]["data_sha256"])
            self.assertEqual(session.commands[0], ":TRIGger:STATus?")
            self.assertNotIn(":STOP", session.commands)

    def test_raw_mode_stops_then_restores_run(self):
        responses = healthy_responses()
        responses[":WAVeform:DATA?"] = fixture("waveform-raw-block.bin")
        responses[":WAVeform:PREamble?"] = fixture("preamble-raw.txt")
        responses[":WAVeform:POINts?"] = b"4000\n"
        session = FakeSession(responses)
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    cmd_waveform(
                        session,
                        out=Path(tmp) / "raw.bin",
                        channel=1,
                        mode="RAW",
                        start=1,
                        stop=4000,
                    ),
                    0,
                )
        self.assertLess(session.commands.index(":STOP"), session.commands.index(":WAVeform:MODE RAW"))
        self.assertLess(session.commands.index(":WAVeform:MODE RAW"), session.commands.index(":WAVeform:DATA?"))
        self.assertEqual(session.commands[-1], ":RUN")
        self.assertIn(":WAVeform:MODE NORM", session.commands)

    def test_raw_mode_restores_window(self):
        responses = healthy_responses()
        responses[":WAVeform:DATA?"] = fixture("waveform-raw-block.bin")
        responses[":WAVeform:PREamble?"] = fixture("preamble-raw.txt")
        responses[":WAVeform:POINts?"] = b"4000\n"
        responses[":WAVeform:STARt?"] = b"1\n"
        responses[":WAVeform:STOP?"] = b"1200\n"
        session = FakeSession(responses)
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_waveform(session, out=Path(tmp) / "raw.bin", mode="RAW", start=1, stop=4000)
        # The window is global: leaving STOP=4000 behind would make a later NORM
        # read report 4000 points for a 1200-point screen record.
        self.assertIn(":WAVeform:STOP 1200", session.commands)
        self.assertLess(session.commands.index(":WAVeform:MODE NORM"),
                        session.commands.index(":WAVeform:STOP 1200"))
        self.assertEqual(session.commands[-1], ":RUN")

    def test_raw_mode_restores_stopped_state(self):
        responses = healthy_responses()
        responses[":TRIGger:STATus?"] = b"STOP\n"
        session = FakeSession(responses)
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_waveform(session, out=Path(tmp) / "raw.bin", mode="RAW")
        self.assertEqual(session.commands[-1], ":STOP")

    def test_window_requires_both_bounds(self):
        session = FakeSession(healthy_responses())
        with self.assertRaises(SessionError):
            cmd_waveform(session, out=Path("/tmp/none.bin"), start=1)

    def test_refuses_existing_output(self):
        session = FakeSession(healthy_responses())
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "wave.bin"
            out_path.write_bytes(b"operator data")
            with self.assertRaises(SessionError):
                cmd_waveform(session, out=out_path)
            self.assertEqual(out_path.read_bytes(), b"operator data")


class ScreenshotCommandTests(unittest.TestCase):
    def test_writes_trimmed_bmp_and_raw(self):
        responses = healthy_responses()
        responses[":DISPlay:DATA?"] = fixture("screenshot-compact.bin")
        session = FakeSession(responses)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "shot.bmp"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(cmd_screenshot(session, out=out_path), 0)
            result = json.loads(buffer.getvalue())
            self.assertEqual(out_path.read_bytes()[:2], b"BM")
            self.assertEqual(len(out_path.read_bytes()), 102)
            self.assertEqual(Path(str(out_path) + ".raw").read_bytes(), fixture("screenshot-compact.bin"))
            self.assertEqual(result["saved_bmp"]["sha256"], result["trimmed_bmp_sha256"])

    def test_truncated_screenshot_is_not_written(self):
        responses = healthy_responses()
        responses[":DISPlay:DATA?"] = fixture("screenshot-color-head.bin")
        session = FakeSession(responses)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "shot.bmp"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(cmd_screenshot(session, out=out_path), 1)
            self.assertFalse(out_path.exists())
            self.assertEqual(json.loads(buffer.getvalue())["status"], "INCOMPLETE")


class CaptureTests(unittest.TestCase):
    def _capture(self, responses: dict[str, bytes], tmp: str, **kwargs) -> tuple[int, dict, Path]:
        session = FakeSession(responses)
        prefix = Path(tmp) / "cap"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_capture(session, prefix=prefix, **kwargs)
        return code, json.loads(buffer.getvalue()), prefix

    def test_healthy_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, report, prefix = self._capture(healthy_responses(), tmp)
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "COMPLETE")
            self.assertTrue(report["captured_at"].endswith("Z"))
            checks = {check["name"]: check for check in report["checks"]}
            self.assertEqual(checks["identity"]["status"], "pass")
            self.assertEqual(checks["error_queue_empty"]["status"], "pass")
            self.assertEqual(checks["block_length"]["status"], "pass")
            self.assertEqual(checks["preamble_points_match_payload"]["status"], "pass")
            self.assertEqual(checks["points_response_match_preamble"]["status"], "pass")
            self.assertEqual(checks["preamble_yincrement_matches_channel_scale"]["status"], "pass")
            self.assertEqual(checks["waveform_vpp_matches_measurement"]["status"], "pass")
            self.assertEqual(Path(f"{prefix}.waveform.bin").read_bytes(), fixture("waveform-norm-block.bin"))
            self.assertEqual(Path(f"{prefix}.preamble.txt").read_bytes(), fixture("preamble-norm.txt"))
            saved_report = json.loads(Path(f"{prefix}.report.json").read_text())
            self.assertEqual(saved_report["status"], "COMPLETE")
            for entry in saved_report["saved"].values():
                data = Path(entry["path"]).read_bytes()
                self.assertEqual(entry["bytes"], len(data))
                self.assertEqual(entry["sha256"], session_sha256(data))

    def test_no_result_sentinel_marks_incomplete(self):
        responses = healthy_responses()
        responses[":MEASure:VPP?"] = fixture("measurement-no-result.txt")
        with tempfile.TemporaryDirectory() as tmp:
            code, report, _ = self._capture(responses, tmp)
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "INCOMPLETE")
            checks = {check["name"]: check for check in report["checks"]}
            self.assertEqual(checks["measurement_vpp"]["status"], "fail")
            self.assertEqual(checks["measurement_vpp"]["evidence"]["reason"], "no_measurement_result_sentinel")
            self.assertEqual(checks["waveform_vpp_matches_measurement"]["status"], "not_checked")
            self.assertIsNone(report["measurements"]["vpp"]["value"])

    def test_preamble_payload_mismatch_marks_invalid(self):
        responses = healthy_responses()
        block = fixture("waveform-norm-block.bin")
        responses[":WAVeform:DATA?"] = encode_ieee_block(block[11:1011]) + b"\n"
        responses[":WAVeform:POINts?"] = b"1000\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, report, _ = self._capture(responses, tmp)
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "INVALID")
            checks = {check["name"]: check for check in report["checks"]}
            self.assertEqual(checks["waveform"]["status"], "fail")
            self.assertIn("declared_points_do_not_match_payload", report["waveform"]["reasons"])

    def test_preamble_scale_mismatch_marks_invalid(self):
        responses = healthy_responses()
        responses[":CHANnel1:SCALe?"] = b"1.000000e+00\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, report, _ = self._capture(responses, tmp)
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "INVALID")
            checks = {check["name"]: check for check in report["checks"]}
            self.assertEqual(checks["preamble_yincrement_matches_channel_scale"]["status"], "fail")

    def test_error_queue_not_clean_is_unverified(self):
        responses = healthy_responses()
        responses[":SYSTem:ERRor?"] = fixture("error-queue-undefined.txt")
        with tempfile.TemporaryDirectory() as tmp:
            code, report, _ = self._capture(responses, tmp)
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "UNVERIFIED")
            self.assertEqual(report["error_queue"]["code"], -113)

    def test_refuses_existing_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "cap"
            Path(f"{prefix}.waveform.bin").write_bytes(b"operator data")
            session = FakeSession(healthy_responses())
            with self.assertRaises(SessionError):
                cmd_capture(session, prefix=prefix)
            self.assertEqual(Path(f"{prefix}.waveform.bin").read_bytes(), b"operator data")

    def test_overwrite_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "cap"
            Path(f"{prefix}.waveform.bin").write_bytes(b"operator data")
            session = FakeSession(healthy_responses())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_capture(session, prefix=prefix, overwrite=True), 0)
            self.assertEqual(Path(f"{prefix}.waveform.bin").read_bytes(), fixture("waveform-norm-block.bin"))

    def test_with_screenshot(self):
        responses = healthy_responses()
        responses[":DISPlay:DATA?"] = fixture("screenshot-compact.bin")
        with tempfile.TemporaryDirectory() as tmp:
            code, report, prefix = self._capture(responses, tmp, with_screenshot=True)
            self.assertEqual(code, 0)
            self.assertEqual(Path(f"{prefix}.screenshot.bmp").read_bytes()[:2], b"BM")
            self.assertEqual(
                Path(f"{prefix}.screenshot.raw").read_bytes(), fixture("screenshot-compact.bin")
            )
            self.assertEqual(report["screenshot"]["status"], "COMPLETE")

    def test_capture_is_read_only_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession(healthy_responses(), allow_writes=False)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_capture(session, prefix=Path(tmp) / "cap"), 0)
            self.assertTrue(all(command.endswith("?") for command in session.commands))


def session_sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


class FileSafetyTests(unittest.TestCase):
    def test_save_raw_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            out.write_bytes(b"operator data")
            with self.assertRaises(SessionError):
                save_raw(out, b"new")
            self.assertEqual(out.read_bytes(), b"operator data")

    def test_save_raw_writes_and_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            self.assertEqual(save_raw(out, b"one")["sha256"], session_sha256(b"one"))
            save_raw(out, b"two", overwrite=True)
            self.assertEqual(out.read_bytes(), b"two")
            self.assertFalse(out.with_name(out.name + ".tmp").exists())


class IsolationTests(unittest.TestCase):
    def test_socket_is_imported_here(self):
        tree = ast.parse((SCRIPTS / "ds1000z_session.py").read_text())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("socket", imported)

    def test_protocol_module_has_no_socket(self):
        tree = ast.parse((SCRIPTS / "ds1000z_protocol.py").read_text())
        names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("socket", names)
        self.assertNotIn("socket", modules)


class CliTests(unittest.TestCase):
    def test_identity_dry_run(self):
        code, out, _ = run_cli(["--dry-run", "identity"])
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'*IDN?\\n'", out)

    def test_measurement_quantity_validation_in_dry_run(self):
        code, _, err = run_cli(["--dry-run", "measurement", "--quantity", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("unsupported measurement quantity", err)

    def test_forbidden_query_at_cli(self):
        code, _, err = run_cli(["--dry-run", "--allow-writes", "query", "*RST"])
        self.assertEqual(code, 2)
        self.assertIn("refusing", err)

    def test_bad_port_at_cli(self):
        code, _, err = run_cli(["--port", "0", "--dry-run", "identity"])
        self.assertEqual(code, 2)
        self.assertIn("port", err.lower())

    def test_capture_requires_prefix(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                main(["--dry-run", "capture"])


if __name__ == "__main__":
    unittest.main()
