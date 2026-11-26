#!/usr/bin/env python3
"""Offline tests for the GDS-2000A optional live transport.

The fake connection replays byte chunks.  No test imports pyserial, opens a
serial port, or touches the real instrument.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gds2000a_protocol as protocol
import gds2000a_session as session_module
from gds2000a_session import Session, SessionError, cmd_measure, cmd_waveform, save_raw

ASSETS = Path(__file__).resolve().parent.parent / "assets"
HARDWARE = ASSETS / "fixtures" / "hardware"
WAVEFORM = (HARDWARE / "acquire1-memory.bin").read_bytes()


class FakeConnection:
    """A deterministic chunk stream; an empty queue behaves like a read timeout."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.writes: list[bytes] = []
        self.closed = False

    def read(self, size: int = 4096) -> bytes:
        if not self.chunks:
            raise TimeoutError("fake read timeout")
        return self.chunks.pop(0)

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def make_session(chunks: list[bytes]) -> tuple[Session, FakeConnection]:
    connection = FakeConnection(chunks)
    return Session(connection=connection, timeout=0.01, block_deadline=1.0), connection


class TransportTests(unittest.TestCase):
    def test_send_rejects_a_second_terminator(self) -> None:
        session, connection = make_session([])
        session.send(b":RUN")
        self.assertEqual([b":RUN\n"], connection.writes)
        with self.assertRaises(SessionError):
            session.send(b":RUN\n:STOP\n")
        self.assertEqual([b":RUN\n"], connection.writes)

    def test_dry_run_sends_nothing(self) -> None:
        session = Session(dry_run=True)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(b"", session.query_text("*IDN?"))
        self.assertIn("DRY-RUN SEND: b'*IDN?\\n'", output.getvalue())
        self.assertEqual([b"*IDN?\n"], session.sent)
        self.assertIsNone(session._connection)

    def test_line_read_preserves_terminator(self) -> None:
        session, connection = make_session([b"GW,GDS-2104A,GEN182193,V1.18\n"])
        raw = session.query_text("*IDN?")
        self.assertEqual(b"GW,GDS-2104A,GEN182193,V1.18\n", raw)
        self.assertEqual("line_terminator", session.last_read_end)
        self.assertEqual([b"*IDN?\n"], connection.writes)

    def test_block_read_ends_at_declared_length(self) -> None:
        header = (
            b"Format,2.0A;Memory Length,4;Source,CH1;Vertical Units,V;"
            b"Vertical Scale,1.000e+00;Sampling Period,1.000e-06;Waveform Data;\n#40008"
        )
        session, connection = make_session(
            [header, b"\x00\x00\x01\x00", b"\xff\xff\x02\x00", b"\n"]
        )
        raw = session.query_block(":ACQuire1:MEMory?")
        artifact = protocol.parse_waveform(raw)
        self.assertEqual("COMPLETE", artifact["status"])
        self.assertEqual(4, artifact["points"])
        self.assertEqual("declared_length", session.last_read_end)

    def test_block_read_returns_partial_bytes_on_timeout(self) -> None:
        session, connection = make_session([b"#40008\x00\x00"])
        raw = session.query_block(":ACQuire1:MEMory?")
        self.assertEqual(b"#40008\x00\x00", raw)
        self.assertEqual("deadline", session.last_read_end)
        self.assertEqual("INCOMPLETE", protocol.parse_waveform(raw)["status"])

    def test_error_drain_stops_at_no_error(self) -> None:
        session, connection = make_session(
            [b'-113, "Undefined header"\n', b'+0, "No error."\n']
        )
        responses = session.drain_errors()
        self.assertEqual(2, len(responses))
        self.assertEqual(b'+0, "No error."\n', responses[-1])
        self.assertEqual([b":SYSTem:ERRor?\n", b":SYSTem:ERRor?\n"], connection.writes)


class SafetyTests(unittest.TestCase):
    def test_save_raw_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.bin"
            first = save_raw(path, b"one")
            self.assertEqual(b"one", first.read_bytes())
            with self.assertRaises(SessionError):
                save_raw(path, b"two")
            save_raw(path, b"two", overwrite=True)
            self.assertEqual(b"two", path.read_bytes())

    def test_measure_restores_the_original_source(self) -> None:
        session, connection = make_session(
            [
                b"CH2\n",  # original source
                b"8.000E-02\n",  # :MEASure:PK2PK?
                b'+0, "No error."\n',  # drain
                b"CH2\n",  # final source check
            ]
        )
        with mock.patch.object(session_module.time, "sleep"), redirect_stdout(io.StringIO()):
            code = cmd_measure(
                session,
                item="pk2pk",
                channel=1,
                slot=1,
                provenance="hardware-verified",
            )
        self.assertEqual(0, code)
        self.assertEqual(
            [b":MEASure:SOURce1?\n", b":MEASure:SOURce1 CH1\n", b":MEASure:PK2PK?\n",
             b":MEASure:SOURce1 CH2\n", b":SYSTem:ERRor?\n", b":MEASure:SOURce1?\n"],
            connection.writes,
        )

    def test_waveform_stops_before_download_and_restores_run(self) -> None:
        session, connection = make_session(
            [
                b"ARMED\n",  # initial trigger state
                WAVEFORM,  # :ACQuire1:MEMory?
                b"AUTO\n",  # state after :RUN
                b'+0, "No error."\n',  # drain
            ]
        )
        with mock.patch.object(session_module.time, "sleep"), redirect_stdout(io.StringIO()):
            code = cmd_waveform(
                session,
                channel=1,
                out=None,
                csv_out=None,
                overwrite=False,
                provenance="hardware-verified",
            )
        self.assertEqual(0, code)
        writes = connection.writes
        self.assertEqual(b":TRIGger:STATe?\n", writes[0])
        self.assertEqual(b":STOP\n", writes[1])
        self.assertEqual(b":ACQuire1:MEMory?\n", writes[2])
        self.assertIn(b":RUN\n", writes)
        self.assertLess(writes.index(b":STOP\n"), writes.index(b":ACQuire1:MEMory?\n"))

    def test_waveform_leaves_an_already_stopped_instrument_stopped(self) -> None:
        session, connection = make_session(
            [
                b"SAVE\n",  # initial trigger state
                WAVEFORM,  # :ACQuire1:MEMory?
                b'+0, "No error."\n',  # drain
            ]
        )
        with mock.patch.object(session_module.time, "sleep"), redirect_stdout(io.StringIO()):
            code = cmd_waveform(
                session,
                channel=1,
                out=None,
                csv_out=None,
                overwrite=False,
                provenance="hardware-verified",
            )
        self.assertEqual(0, code)
        self.assertNotIn(b":STOP\n", connection.writes)
        self.assertNotIn(b":RUN\n", connection.writes)


if __name__ == "__main__":
    unittest.main()
