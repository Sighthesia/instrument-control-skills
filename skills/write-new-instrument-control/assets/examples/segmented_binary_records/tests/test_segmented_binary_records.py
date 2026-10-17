import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from _example_support import assert_expected, load_json  # noqa: E402
from parser_segmented_binary_records import ParserError, parse  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class SegmentedBinaryRecordTests(unittest.TestCase):
    def test_valid_segments(self):
        assert_expected(parse((FIXTURES / "valid.txt").read_bytes()), load_json(ROOT / "expected-result.json"))

    def test_gap_is_invalid(self):
        result = parse((FIXTURES / "gap.txt").read_bytes())
        self.assertIn("segment_gap_overlap_or_short_payload", result["integrity"]["reasons"])

    def test_overlap_is_invalid(self):
        result = parse((FIXTURES / "overlap.txt").read_bytes())
        self.assertIn("segment_gap_overlap_or_short_payload", result["integrity"]["reasons"])

    def test_duplicate_sequence_is_invalid(self):
        result = parse((FIXTURES / "duplicate-sequence.txt").read_bytes())
        self.assertIn("duplicate_sequence", result["integrity"]["reasons"])

    def test_short_payload_is_invalid(self):
        self.assertEqual(parse((FIXTURES / "short-payload.txt").read_bytes())["integrity"]["status"], "INVALID")

    def test_malformed_header_raises(self):
        with self.assertRaisesRegex(ParserError, "malformed"):
            parse((FIXTURES / "malformed.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
