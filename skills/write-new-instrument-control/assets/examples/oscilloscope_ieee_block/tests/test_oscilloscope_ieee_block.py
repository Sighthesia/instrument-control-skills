import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from _example_support import assert_expected, load_json  # noqa: E402
from parser_oscilloscope_ieee_block import ParserError, parse, read_frame  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class OscilloscopeIEEEBlockTests(unittest.TestCase):
    def test_valid_block_matches_expected_result(self):
        assert_expected(parse((FIXTURES / "valid.bin").read_bytes()), load_json(ROOT / "expected-result.json"))

    def test_truncated_block_raises_framing_error(self):
        with self.assertRaisesRegex(ParserError, "truncated IEEE payload"):
            read_frame((FIXTURES / "truncated.bin").read_bytes())

    def test_invalid_length_digit_raises(self):
        with self.assertRaisesRegex(ParserError, "invalid IEEE length"):
            read_frame((FIXTURES / "invalid-header.bin").read_bytes())

    def test_wrong_point_count_is_incomplete(self):
        self.assertEqual(parse((FIXTURES / "short-payload.bin").read_bytes())["integrity"]["status"], "INCOMPLETE")

    def test_trailing_bytes_are_preserved(self):
        result = parse((FIXTURES / "trailing.bin").read_bytes())
        self.assertEqual(result["integrity"]["status"], "UNVERIFIED")
        self.assertEqual(result["integrity"]["evidence"]["payload_bytes"], 4)


if __name__ == "__main__":
    unittest.main()
