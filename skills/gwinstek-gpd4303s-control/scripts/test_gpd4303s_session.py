from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpd4303s_session import (  # noqa: E402
    ALLOWED_COMMAND_NAMES,
    CommandRefused,
    Session,
    cmd_idn,
    cmd_read,
    cmd_settings,
    main,
)

CRLF = b"\r\n"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ReplayTransport:
    """A local stand-in for pyserial that answers from saved bytes."""

    def __init__(self, responses: dict[bytes, bytes]) -> None:
        self.responses = dict(responses)
        self.writes: list[bytes] = []
        self.timeout = 1.0
        self.closed = False
        self._pending = bytearray()

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))
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
    def test_dry_run_prints_exact_bytes_and_opens_nothing(self):
        transport = ReplayTransport({})
        session = Session(dry_run=True, transport=transport)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_idn(session, Namespace())
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN SEND: b'*IDN?\\r\\n'", buffer.getvalue())
        self.assertEqual(transport.writes, [])

    def test_cli_dry_run_needs_no_port(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--dry-run", "--port", "/dev/does-not-exist", "status"])
        self.assertEqual(code, 0)
        self.assertIn("b'STATUS?\\r\\n'", buffer.getvalue())


class AllowlistTests(unittest.TestCase):
    def test_every_allowed_name_is_a_query(self):
        self.assertEqual(
            ALLOWED_COMMAND_NAMES,
            frozenset({"*IDN?", "STATUS?", "HELP?", "VSET<X>?", "ISET<X>?", "VOUT<X>?", "IOUT<X>?"}),
        )

    def test_state_changing_commands_are_refused_before_the_port(self):
        refused = [
            "OUT1",
            "OUT0",
            "VSET1:24.000",
            "ISET1:1.000",
            "TRACK1",
            "SAV1",
            "RCL1",
            "LOCAL",
            "REMOTE",
            "BEEP0",
            "BEEP1",
            "BAUD2",
        ]
        session, transport = offline_session({})
        for command in refused:
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    session.exchange(command)
        self.assertEqual(transport.writes, [])

    def test_documented_but_unexercised_query_is_refused(self):
        session, transport = offline_session({})
        with self.assertRaises(CommandRefused):
            session.exchange("ERR?")
        self.assertEqual(transport.writes, [])

    def test_unknown_command_is_refused(self):
        session, transport = offline_session({})
        for command in ("SYST:ERR?", "*OPT?", "OUT1?", "TRACK?", "MEAS:VOLT?"):
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    session.exchange(command)
        self.assertEqual(transport.writes, [])


class ReplayTests(unittest.TestCase):
    def test_identity_replay(self):
        session, transport = offline_session({b"*IDN?\r\n": fixture("idn.txt")})
        record = session.exchange("*IDN?")
        self.assertEqual(transport.writes, [b"*IDN?\r\n"])
        self.assertEqual(record["response"], fixture("idn.txt"))
        self.assertEqual(record["artifact"]["integrity"]["status"], "COMPLETE")
        self.assertEqual(record["artifact"]["firmware"], "V2.08")

    def test_status_replay_decodes_the_capture(self):
        session, _ = offline_session({b"STATUS?\r\n": fixture("status-output-off.txt")})
        artifact = session.exchange("STATUS?")["artifact"]
        self.assertEqual(artifact["decoded"]["output"], "off")
        self.assertEqual(artifact["decoded"]["baud_bps"], 9600)

    def test_lowercase_query_is_sent_verbatim(self):
        session, transport = offline_session({b"vout3?\r\n": fixture("vout3-off.txt")})
        record = session.exchange("vout3?")
        self.assertEqual(transport.writes, [b"vout3?\r\n"])
        self.assertEqual(record["artifact"]["channel"], 3)

    def test_multi_line_help_is_read_to_the_last_line(self):
        session, _ = offline_session({b"HELP?\r\n": fixture("help-list.txt")})
        artifact = session.exchange("HELP?")["artifact"]
        self.assertEqual(artifact["line_count"], 18)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")

    def test_silent_instrument_raises(self):
        session, _ = offline_session({})
        with self.assertRaises(RuntimeError):
            session.exchange("*IDN?")

    def test_undocumented_baud_is_rejected(self):
        with self.assertRaises(ValueError):
            Session(baud=12345)


class CaptureTests(unittest.TestCase):
    def test_capture_writes_raw_bytes_and_an_index(self):
        with tempfile.TemporaryDirectory() as directory:
            session, _ = offline_session(
                {b"*IDN?\r\n": fixture("idn.txt")}, capture_dir=Path(directory)
            )
            session.exchange("*IDN?")
            raw_files = [path for path in Path(directory).glob("*.raw")]
            self.assertEqual(len(raw_files), 1)
            self.assertEqual(raw_files[0].read_bytes(), fixture("idn.txt"))
            entry = json.loads((Path(directory) / "captures.jsonl").read_text().strip())
            self.assertEqual(entry["command"], "*IDN?")
            self.assertEqual(entry["raw_path"], raw_files[0].name)


class SnapshotTests(unittest.TestCase):
    def _read_responses(self, status: bytes, voltage: bytes, current: bytes) -> dict:
        return {
            b"STATUS?\r\n": status,
            b"VOUT1?\r\n": voltage,
            b"IOUT1?\r\n": current,
            b"VOUT2?\r\n": fixture("vout2-off.txt"),
            b"IOUT2?\r\n": fixture("iout2-off.txt"),
        }

    def test_read_snapshot_reports_no_output_measured(self):
        session, _ = offline_session(self._read_responses(
            fixture("status-output-off.txt"), fixture("vout1-off.txt"), fixture("iout1-off.txt")
        ))
        args = Namespace(channels=[1, 2], bit_order="lsb-first")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_read(session, args)
        self.assertEqual(code, 0)
        # The JSON follows the echoed exchanges; isolate it by its opening brace.
        text = buffer.getvalue()
        snapshot = json.loads(text[text.index("{\n") :])
        self.assertEqual(snapshot["output_state"], "no_output_measured")
        self.assertEqual(snapshot["integrity"]["status"], "UNVERIFIED")
        self.assertEqual(len(snapshot["readings"]), 4)

    def test_read_snapshot_warns_when_status_says_output_on(self):
        session, _ = offline_session(self._read_responses(
            fixture("status-output-on.txt"), fixture("vout1-on.txt"), fixture("iout1-on.txt")
        ))
        args = Namespace(channels=[1, 2], bit_order="lsb-first")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cmd_read(session, args)
        self.assertIn("output bit as ON", err.getvalue())
        text = out.getvalue()
        snapshot = json.loads(text[text.index("{\n"):])
        self.assertEqual(snapshot["output_state"], "voltage_present")
        self.assertEqual(snapshot["readings"][0]["value"], 23.994)

    def test_settings_snapshot_is_complete(self):
        session, _ = offline_session({
            b"VSET1?\r\n": fixture("vset1.txt"),
            b"ISET1?\r\n": fixture("iset1.txt"),
            b"VSET2?\r\n": fixture("vset2.txt"),
            b"ISET2?\r\n": fixture("iset2.txt"),
        })
        args = Namespace(channels=[1, 2])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cmd_settings(session, args)
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        snapshot = json.loads(text[text.index("{\n"):])
        self.assertEqual(snapshot["integrity"]["status"], "COMPLETE")
        self.assertEqual([item["value"] for item in snapshot["setpoints"]], [24.0, 1.0, 24.0, 1.0])


if __name__ == "__main__":
    unittest.main()
