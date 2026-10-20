from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import gds1000b_session as session_module  # noqa: E402
from gds1000b_session import (  # noqa: E402
    DEFAULT_SERIAL_PORT,
    Session,
    SessionError,
    cmd_capture,
    cmd_errors,
    cmd_hardcopy,
    cmd_measure,
    cmd_query,
    cmd_save_image,
    cmd_snapshot,
    cmd_waveform,
    main,
    save_raw,
    validate_image_path,
)

WAVEFORM = (FIXTURES / "waveform-valid.bin").read_bytes()


class FakeConnection:
    """A byte source for exercising exact reads without a socket."""

    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    def recv(self, count: int) -> bytes:
        chunk = bytes(self.data[:count])
        del self.data[:count]
        return chunk

    def close(self) -> None:
        pass


class FakeSession(Session):
    """A live-looking session whose responses are fixed, no transport."""

    def __init__(self, *, state: str, block: bytes = WAVEFORM, text: str = "") -> None:
        super().__init__(dry_run=False)
        self.state = state
        self.block = block
        self.text = text

    def query_text(self, command: str) -> str:
        self.sent.append(command.encode("ascii") + b"\n")
        return self.state

    def query_block(self, command: str) -> bytes:
        self.sent.append(command.encode("ascii") + b"\n")
        return self.block


class SessionConstructionTests(unittest.TestCase):
    def test_serial_defaults(self):
        session = Session()
        self.assertEqual(session.kind, "serial")
        self.assertEqual(session.port, DEFAULT_SERIAL_PORT)
        self.assertEqual(session.baud, 115200)
        self.assertIsNone(session._connection)

    def test_tcp_selection(self):
        session = Session(host="127.0.0.1", tcp_port=5025)
        self.assertEqual(session.kind, "tcp")
        self.assertEqual(session.tcp_port, 5025)

    def test_tcp_requires_port(self):
        with self.assertRaises(SessionError):
            Session(host="127.0.0.1")

    def test_tcp_port_range(self):
        with self.assertRaises(SessionError):
            Session(host="127.0.0.1", tcp_port=23)
        with self.assertRaises(SessionError):
            Session(host="127.0.0.1", tcp_port=65536)

    def test_serial_and_tcp_conflict(self):
        with self.assertRaises(SessionError):
            Session(port="/dev/ttyACM1", host="127.0.0.1", tcp_port=5025)

    def test_no_module_level_pyserial_import(self):
        tree = ast.parse((SCRIPTS / "gds1000b_session.py").read_text())
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                self.assertNotIn("serial", names)
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "serial")

    def test_pyserial_missing_is_reported_lazily(self):
        with mock.patch.dict(sys.modules, {"serial": None}):
            with self.assertRaises(SessionError):
                session_module._serial_module()


class DryRunTests(unittest.TestCase):
    def _session(self) -> Session:
        return Session(dry_run=True)

    def test_send_appends_exact_bytes(self):
        session = self._session()
        session.send(b"*IDN?")
        session.send(b":RUN\n")
        self.assertEqual(session.sent, [b"*IDN?\n", b":RUN\n"])
        self.assertIsNone(session._connection)

    def test_idn_dry_run(self):
        session = self._session()
        self.assertEqual(session_module.cmd_idn(session), 0)
        self.assertEqual(session.sent, [b"*IDN?\n"])

    def test_query_text_never_reads(self):
        session = self._session()
        self.assertEqual(session.query_text(":TRIGger:STATe?"), "")
        self.assertEqual(session.sent, [b":TRIGger:STATe?\n"])

    def test_capture_order(self):
        session = self._session()
        self.assertEqual(cmd_capture(session, 1, 1.0, 0.01), 0)
        self.assertEqual(
            session.sent,
            [
                b":TRIGger:MODe?\n",
                b":HEADer ON\n",
                b":SINGle\n",
                b":TRIGger:STATe?\n",
                b":ACQuire1:STATe?\n",
                b":STOP\n",
                b":ACQuire1:MEMory?\n",
            ],
        )

    def test_capture_channel_validation(self):
        session = self._session()
        for channel in (0, 5, True):
            with self.assertRaises(SessionError):
                cmd_capture(session, channel, 1.0, 0.01)  # type: ignore[arg-type]

    def test_waveform_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.bin"
            session = self._session()
            self.assertEqual(
                cmd_waveform(session, 2, out, overwrite=False, allow_unready=False), 0
            )
            self.assertEqual(session.sent, [b":ACQuire2:MEMory?\n"])
            self.assertFalse(out.exists())

    def test_errors_drain_single_dry_run(self):
        session = self._session()
        self.assertEqual(cmd_errors(session, drain=True), 0)
        self.assertEqual(session.sent, [b":SYSTem:ERRor?\n"])

    def test_measure_uses_documented_command(self):
        session = self._session()
        self.assertEqual(cmd_measure(session, "frequency"), 0)
        self.assertEqual(session.sent, [b":MEASure:FREQuency?\n"])

    def test_save_image_bytes_and_no_readback(self):
        session = self._session()
        self.assertEqual(cmd_save_image(session, "Disk:/pic1.PNG", "ON"), 0)
        self.assertEqual(
            session.sent,
            [
                b":SAVe:IMAGe:FILEFormat PNG\n",
                b":SAVe:IMAGe:INKSaver ON\n",
                b':SAVe:IMAGe "Disk:/pic1.PNG"\n',
            ],
        )

    def test_hardcopy_bytes(self):
        session = self._session()
        self.assertEqual(cmd_hardcopy(session, "USB:/pic2.BMP"), 0)
        self.assertEqual(
            session.sent,
            [
                b":HARDcopy:MODe SAVE\n",
                b":HARDcopy:ASSIGN IMAGe\n",
                b":HARDcopy:SAVEFORMat BMP\n",
                b":HARDcopy:START\n",
            ],
        )

    def test_snapshot_query_count(self):
        session = self._session()
        self.assertEqual(cmd_snapshot(session, 2), 0)
        self.assertEqual(len(session.sent), 12)
        self.assertEqual(session.sent[0], b"*IDN?\n")
        self.assertIn(b":CHANnel2:SCALe?\n", session.sent)

    def test_query_refuses_write_without_flag(self):
        session = self._session()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.assertEqual(cmd_query(session, ":RUN", False), 2)
        self.assertEqual(session.sent, [])
        self.assertIn("refusing", buffer.getvalue())

    def test_query_allows_write_with_flag(self):
        session = self._session()
        self.assertEqual(cmd_query(session, ":RUN", True), 0)
        self.assertEqual(session.sent, [b":RUN\n"])


class BlockReadTests(unittest.TestCase):
    def _session_with(self, data: bytes) -> Session:
        session = Session(host="127.0.0.1", tcp_port=5025)
        session._connection = FakeConnection(data)
        return session

    def test_reads_exact_binary_payload_with_lf_bytes(self):
        payload = b"\x0a\x0d\x00\x01\x0a\x0d\xff\xff"
        raw = b"Format,2.0E;Memory Length,4;Waveform Data;#40008" + payload
        session = self._session_with(raw)
        self.assertEqual(session.read_block_response(), raw)

    def test_headerless_block(self):
        raw = b"#40002\x00\x01"
        session = self._session_with(raw)
        self.assertEqual(session.read_block_response(), raw)

    def test_whitespace_after_marker(self):
        raw = b"Memory Length,1;Waveform Data;\r\n#40002\x00\x01"
        session = self._session_with(raw)
        self.assertEqual(session.read_block_response(), raw)

    def test_missing_length_digit(self):
        session = self._session_with(b"Waveform Data;X")
        with self.assertRaises(SessionError):
            session.read_block_response()


class FileSafetyTests(unittest.TestCase):
    def test_save_raw_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            out.write_bytes(b"operator data")
            with self.assertRaises(SessionError):
                save_raw(out, WAVEFORM)
            self.assertEqual(out.read_bytes(), b"operator data")

    def test_save_raw_writes_and_allows_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            self.assertEqual(save_raw(out, b"one"), out)
            self.assertEqual(out.read_bytes(), b"one")
            save_raw(out, b"two", overwrite=True)
            self.assertEqual(out.read_bytes(), b"two")
            self.assertFalse(out.with_name(out.name + ".tmp").exists())

    def test_validate_image_path_accepts_documented_forms(self):
        self.assertEqual(validate_image_path("Disk:/pic1.PNG"), ("Disk:/pic1.PNG", "PNG"))
        self.assertEqual(validate_image_path("USB:/pic2.bmp"), ("USB:/pic2.bmp", "BMP"))

    def test_validate_image_path_rejects_long_name(self):
        with self.assertRaises(SessionError):
            validate_image_path("Disk:/123456789.PNG")

    def test_validate_image_path_rejects_bad_prefix(self):
        with self.assertRaises(SessionError):
            validate_image_path("/tmp/pic1.PNG")

    def test_validate_image_path_rejects_bad_extension(self):
        with self.assertRaises(SessionError):
            validate_image_path("Disk:/pic1.JPG")

    def test_validate_image_path_requires_extension(self):
        with self.assertRaises(SessionError):
            validate_image_path("Disk:/pic1")

    def test_waveform_refuses_unready_state(self):
        session = FakeSession(state="*ARMED")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            with self.assertRaises(SessionError):
                cmd_waveform(session, 1, out, overwrite=False, allow_unready=False)
            self.assertFalse(out.exists())

    def test_waveform_saves_when_ready(self):
        session = FakeSession(state="1")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            self.assertEqual(cmd_waveform(session, 1, out, overwrite=False, allow_unready=False), 0)
            self.assertEqual(out.read_bytes(), WAVEFORM)
            self.assertEqual(
                session.sent,
                [b":ACQuire1:STATe?\n", b":ACQuire1:MEMory?\n"],
            )

    def test_waveform_refuses_existing_output(self):
        session = FakeSession(state="1")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            out.write_bytes(b"operator data")
            with self.assertRaises(SessionError):
                cmd_waveform(session, 1, out, overwrite=False, allow_unready=False)
            self.assertEqual(out.read_bytes(), b"operator data")


class CliTests(unittest.TestCase):
    def _run(self, argv):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_idn_dry_run(self):
        code, out, _ = self._run(["--dry-run", "idn"])
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'*IDN?\\n'", out)

    def test_tcp_requires_port_at_cli(self):
        code, _, err = self._run(["--host", "127.0.0.1", "idn"])
        self.assertEqual(code, 2)
        self.assertIn("requires --host and --port", err)

    def test_capture_dry_run(self):
        code, out, _ = self._run(["--dry-run", "capture", "--channel", "3"])
        self.assertEqual(code, 0)
        self.assertIn(b":ACQuire3:STATe?".decode(), out.replace("\\n", ""))

    def test_waveform_dry_run_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "raw.bin"
            code, _, _ = self._run(["--dry-run", "waveform", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertFalse(out.exists())

    def test_save_image_rejects_long_name(self):
        code, _, err = self._run(["--dry-run", "save-image", "--path", "Disk:/123456789.PNG"])
        self.assertEqual(code, 2)
        self.assertIn("8 characters", err)


if __name__ == "__main__":
    unittest.main()
