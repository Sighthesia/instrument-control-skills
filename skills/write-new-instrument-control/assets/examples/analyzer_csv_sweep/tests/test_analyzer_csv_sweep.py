import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from _example_support import assert_expected, load_json  # noqa: E402
from parser_analyzer_csv_sweep import ParserError, parse  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class AnalyzerCSVSweepTests(unittest.TestCase):
    def test_valid_sweep(self):
        assert_expected(parse((FIXTURES / "valid.csv").read_bytes()), load_json(ROOT / "expected-result.json"))

    def test_missing_column_raises(self):
        with self.assertRaisesRegex(ParserError, "requires"):
            parse((FIXTURES / "missing-column.csv").read_bytes())

    def test_malformed_numeric_row_raises(self):
        with self.assertRaisesRegex(ParserError, "malformed numeric"):
            parse((FIXTURES / "malformed-row.csv").read_bytes())

    def test_non_monotonic_axis_is_invalid(self):
        self.assertEqual(parse((FIXTURES / "non-monotonic.csv").read_bytes())["integrity"]["status"], "INVALID")

    def test_duplicate_axis_is_invalid(self):
        result = parse((FIXTURES / "duplicate-point.csv").read_bytes())
        self.assertIn("duplicate_frequency_point", result["integrity"]["reasons"])


if __name__ == "__main__":
    unittest.main()
