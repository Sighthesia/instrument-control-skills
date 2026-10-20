from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import afg2225_session  # noqa: E402


class SessionDryRunTests(unittest.TestCase):
    def test_idn_dry_run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = afg2225_session.main(["--dry-run", "idn"])
        self.assertEqual(code, 0)
        self.assertIn(b"*IDN?".decode(), buf.getvalue())  # loose
        self.assertIn("*IDN?", buf.getvalue())

    def test_arb_binary_refused_without_byte_order(self):
        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = afg2225_session.main([
                "--dry-run", "arb", "--csv", str(FIXTURES / "arb-valid.csv"),
                "--format", "binary", "--load", "50",
            ])
        self.assertNotEqual(code, 0)
        self.assertIn("byte-order", err.getvalue())

    def test_arb_dry_run_prints_bytes(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = afg2225_session.main([
                "--dry-run", "arb", "--csv", str(FIXTURES / "arb-valid.csv"),
                "--format", "ascii", "--load", "50",
            ])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("DATA:DAC VOLATILE", output)
        self.assertIn("SOUR1:FUNC USER", output)

    def test_apply_requires_load(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = afg2225_session.main(["--dry-run", "apply", "sine"])
        self.assertNotEqual(code, 0)

    def test_apply_sets_load_then_applies(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = afg2225_session.main([
                "--dry-run", "apply", "sine", "--load", "50",
                "--frequency", "1000", "--amplitude", "2", "--offset", "0.5",
            ])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("OUTP1:LOAD DEF", output)
        self.assertIn("SOUR1:APPL:SIN 1000,2.0VPP,0.5V", output)

    def test_invalid_channel_rejected(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = afg2225_session.main(["--dry-run", "output", "on", "--channel", "3"])
        self.assertEqual(code, 2)

    def test_query_write_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = afg2225_session.main(["--dry-run", "query", "OUTP1 ON"])
        self.assertNotEqual(code, 0)

    def test_query_write_allowed_does_not_read(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = afg2225_session.main(["--dry-run", "query", "OUTP1 ON", "--allow-write"])
        self.assertEqual(code, 0)
        self.assertNotIn("RESPONSE:", buf.getvalue())

    def test_query_read_allowed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = afg2225_session.main(["--dry-run", "query", "SOUR1:FREQ?"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
