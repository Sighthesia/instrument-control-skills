#!/usr/bin/env python3
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parser import ParserError, parse, read_frame  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ParserTemplateTests(unittest.TestCase):
    def test_valid_response_is_complete_and_preserves_hash(self):
        raw = fixture("valid-response.bin")
        result = parse(raw)
        self.assertEqual(result["values"], [1.234, 1.235])
        self.assertEqual(result["integrity"]["status"], "COMPLETE")
        self.assertEqual(result["integrity"]["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_truncated_response_fails_closed(self):
        with self.assertRaisesRegex(ParserError, "truncated payload"):
            read_frame(fixture("truncated-response.bin"))

    def test_malformed_header_is_rejected(self):
        with self.assertRaisesRegex(ParserError, "invalid length field"):
            read_frame(fixture("malformed-header.bin"))

    def test_declared_count_mismatch_is_incomplete(self):
        raw = fixture("length-mismatch.bin")
        result = parse(raw)
        self.assertEqual(result["integrity"]["status"], "INCOMPLETE")
        self.assertIn("declared_count_does_not_match_values", result["integrity"]["reasons"])

    def test_missing_unit_is_incomplete(self):
        payload = b"META kind=scalar count=1\nDATA 1.234\n"
        raw = b"#" + f"{len(payload):04d}".encode("ascii") + payload
        result = parse(raw)
        self.assertEqual(result["integrity"]["status"], "INCOMPLETE")
        self.assertIn("unit_missing", result["integrity"]["reasons"])

    def test_trailing_bytes_are_unverified(self):
        result = parse(fixture("valid-response.bin") + b"\r\n")
        self.assertEqual(result["integrity"]["status"], "UNVERIFIED")
        self.assertIn("trailing_bytes_present", result["integrity"]["reasons"])


if __name__ == "__main__":
    unittest.main()
