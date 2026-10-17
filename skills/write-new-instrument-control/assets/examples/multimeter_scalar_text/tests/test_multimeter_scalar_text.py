import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from _example_support import assert_expected, load_json  # noqa: E402
from parser_multimeter_scalar_text import ParserError, parse  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class MultimeterScalarTextTests(unittest.TestCase):
    def test_valid_reading(self):
        assert_expected(parse((FIXTURES / "valid.txt").read_bytes()), load_json(ROOT / "expected-result.json"))

    def test_overload_is_unverified(self):
        self.assertEqual(parse((FIXTURES / "overload.txt").read_bytes())["integrity"]["status"], "UNVERIFIED")

    def test_instrument_reported_unsupported_is_unsupported(self):
        self.assertEqual(parse((FIXTURES / "unsupported.txt").read_bytes())["integrity"]["status"], "UNSUPPORTED")

    def test_missing_unit_is_incomplete(self):
        self.assertEqual(parse((FIXTURES / "missing-unit.txt").read_bytes())["integrity"]["status"], "INCOMPLETE")

    def test_bad_number_raises(self):
        with self.assertRaisesRegex(ParserError, "not numeric"):
            parse((FIXTURES / "bad-number.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
