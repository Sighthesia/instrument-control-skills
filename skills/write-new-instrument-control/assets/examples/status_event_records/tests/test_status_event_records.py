import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from _example_support import assert_expected, load_json  # noqa: E402
from parser_status_event_records import ParserError, parse  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class StatusEventRecordTests(unittest.TestCase):
    def test_valid_event_sequence(self):
        assert_expected(parse((FIXTURES / "valid.jsonl").read_bytes()), load_json(ROOT / "expected-result.json"))

    def test_sequence_gap_is_invalid(self):
        self.assertEqual(parse((FIXTURES / "sequence-gap.jsonl").read_bytes())["integrity"]["status"], "INVALID")

    def test_missing_end_marker_is_incomplete(self):
        result = parse((FIXTURES / "missing-end.jsonl").read_bytes())
        self.assertIn("end_marker_missing", result["integrity"]["reasons"])

    def test_bad_timestamp_is_invalid(self):
        self.assertEqual(parse((FIXTURES / "bad-timestamp.jsonl").read_bytes())["integrity"]["status"], "INVALID")

    def test_malformed_json_raises(self):
        with self.assertRaisesRegex(ParserError, "valid JSON"):
            parse((FIXTURES / "malformed.jsonl").read_bytes())


if __name__ == "__main__":
    unittest.main()
