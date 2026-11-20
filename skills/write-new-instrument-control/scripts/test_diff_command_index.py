from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ASSETS = SCRIPTS.parent / "assets" / "index-audit"
sys.path.insert(0, str(SCRIPTS))

import diff_command_index as dci  # noqa: E402

INDEX = ASSETS / "synthetic-index.md"
MANUAL_TSV = ASSETS / "synthetic-diff-manual.tsv"


def run_main(*args: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = dci.main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


class NormalizationTests(unittest.TestCase):
    def test_placeholders_numeric_indices_and_query_markers(self) -> None:
        self.assertEqual(
            dci.normalize_command(":CHANnel1:SCALe?"),
            dci.normalize_command(":CHANnel<n>:SCALe"),
        )
        self.assertEqual(
            dci.normalize_command(":MEMory2:IMPort"),
            dci.normalize_command(":MEMory<m>:IMPort"),
        )
        self.assertTrue(dci.commands_match(":CHANnel1:SCALe?", ":CHANnel<n>:SCALe"))
        self.assertTrue(dci.commands_match(":STAT?", ":STATe?"))
        self.assertTrue(dci.commands_match(":TIM:SCAL?", ":TIMebase:SCALe?"))

    def test_optional_root_and_cjk_punctuation(self) -> None:
        self.assertEqual(
            dci.normalize_command("[:SOURce[<n>]]:VOLTage[:DC]"),
            "source<n>:voltage:dc",
        )
        self.assertEqual(
            dci.normalize_command(":MEASure:VPP?。"),
            dci.normalize_command(":MEASure:VPP"),
        )

    def test_placeholder_variant_is_not_a_plain_match(self) -> None:
        self.assertFalse(
            dci.commands_match(":FUNCtion<x>:FFT", ":FUNCtion:FFT")
        )
        self.assertEqual(
            dci.loose_components(":FUNCtion<x>:FFT"),
            dci.loose_components(":FUNCtion:FFT"),
        )


class CoverageTests(unittest.TestCase):
    def test_fixture_classifies_every_residual_kind(self) -> None:
        manual = dci.parse_manual_tsv(MANUAL_TSV)
        index = dci.parse_index_markdown(INDEX)
        result = dci.analyze_coverage(manual, index)

        self.assertEqual(len(manual.forms), 11)
        self.assertEqual(len(result.covered), 6)
        self.assertEqual(len(result.gaps), 5)
        counts = result.classification_counts
        self.assertEqual(counts["placeholder-variant"], 1)
        self.assertEqual(counts["short-form"], 1)
        self.assertEqual(counts["example-line"], 1)
        self.assertEqual(counts["wrapped-heading"], 1)
        self.assertEqual(counts["true-gap"], 1)
        self.assertEqual(result.true_gaps[0][0].command, ":REAL:GAP")

    def test_true_gap_is_not_hidden_by_an_index_parent_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual_path = root / "manual.tsv"
            manual_path.write_text(
                "command\tpdf_page\tsource\tcontext\n"
                ":FUNCtion<x>:FFT:SEARch:RESult\t10\tbody\theading\n",
                encoding="utf-8",
            )
            index_path = root / "index.md"
            index_path.write_text(
                "| Command | Type |\n|---|---|\n"
                "| `:FUNCtion1:FFT:SEARch` | family |\n",
                encoding="utf-8",
            )
            result = dci.analyze_coverage(
                dci.parse_manual_tsv(manual_path),
                dci.parse_index_markdown(index_path),
            )
        self.assertEqual(result.gaps[0][1], "true-gap")

    def test_blank_line_inside_table_does_not_drop_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "index.md"
            index_path.write_text(
                "| Command | Type |\n|---|---|\n"
                "| `:ACQuire:MDEPth?` | query |\n\n"
                "| `:TIMebase:SCALe` | set |\n",
                encoding="utf-8",
            )
            index = dci.parse_index_markdown(index_path)
        normalized = {dci.normalize_command(form.command) for form in index.forms}
        self.assertIn("acquire:mdepth", normalized)
        self.assertIn("timebase:scale", normalized)

    def test_bare_index_mnemonic_matches_colon_form(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual_path = root / "manual.tsv"
            manual_path.write_text(
                "command\tpdf_page\tsource\tcontext\n"
                ":AUToset\t10\tbody\theading\n",
                encoding="utf-8",
            )
            index_path = root / "index.md"
            index_path.write_text(
                "| Command | Type |\n|---|---|\n| `AUToset` | event |\n",
                encoding="utf-8",
            )
            result = dci.analyze_coverage(
                dci.parse_manual_tsv(manual_path),
                dci.parse_index_markdown(index_path),
            )
        self.assertEqual(len(result.covered), 1)
        self.assertEqual(result.gaps, ())

    def test_exit_codes_and_report(self) -> None:
        code, output, _ = run_main(
            "--manual", str(MANUAL_TSV), "--index", str(INDEX)
        )
        self.assertEqual(code, 0)
        self.assertIn("True gaps: 1", output)

        code, _, _ = run_main(
            "--manual",
            str(MANUAL_TSV),
            "--index",
            str(INDEX),
            "--fail-on-missing",
        )
        self.assertEqual(code, 1)

        code, _, stderr = run_main(
            "--manual", str(MANUAL_TSV), "--index", str(INDEX.with_name("missing.md"))
        )
        self.assertEqual(code, 2)
        self.assertIn("error:", stderr)

    def test_markdown_report_has_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            code, _, _ = run_main(
                "--manual",
                str(MANUAL_TSV),
                "--index",
                str(INDEX),
                "--report",
                str(report),
            )
            self.assertEqual(code, 0)
            text = report.read_text(encoding="utf-8")
        self.assertIn("# Command index coverage audit", text)
        self.assertIn("Date:", text)
        self.assertIn("synthetic-manual.txt", text)
        self.assertIn("Manual pages: 4", text)
        self.assertIn("Gaps by subsystem", text)
        self.assertIn("Classification counts", text)
        self.assertIn("True gaps", text)
        self.assertIn(":REAL:GAP", text)


class DriftTests(unittest.TestCase):
    def test_drift_extracts_fstring_prefix_and_literals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code_path = Path(directory) / "code.py"
            code_path.write_text(
                'IDENTITY = "*IDN?"\n'
                "def read(channel):\n"
                '    return f":CHANnel{channel}:SCALe?"\n'
                "def run(session):\n"
                '    session.write(":RUN")\n'
                '    session.query_text(":MEASure:VPP?")\n',
                encoding="utf-8",
            )
            code, output, _ = run_main(
                "--drift",
                "--index",
                str(INDEX),
                "--code",
                str(code_path),
            )
        self.assertEqual(code, 0)
        self.assertIn("Code sends but index does not list: 0", output)
        self.assertIn(":WAVEform:DATA?", output)

    def test_drift_reports_unindexed_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code_path = Path(directory) / "code.py"
            code_path.write_text(
                'session.write(":NOT:INDEXED")\n', encoding="utf-8"
            )
            code, output, _ = run_main(
                "--drift",
                "--index",
                str(INDEX),
                "--code",
                str(code_path),
            )
        self.assertEqual(code, 1)
        self.assertIn(":NOT:INDEXED", output)
        self.assertIn("Code sends but index does not list: 1", output)

    def test_drift_skips_test_files_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_ignored.py").write_text(
                'session.write(":NOT:INDEXED")\n', encoding="utf-8"
            )
            code, output, _ = run_main(
                "--drift",
                "--index",
                str(INDEX),
                "--code",
                str(root),
            )
            self.assertEqual(code, 0)
            self.assertIn("Code command literals: 0", output)

            code, output, _ = run_main(
                "--drift",
                "--index",
                str(INDEX),
                "--code",
                str(root),
                "--include-tests",
            )
            self.assertEqual(code, 1)
            self.assertIn(":NOT:INDEXED", output)

    def test_drift_skips_guard_prefix_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code_path = Path(directory) / "code.py"
            code_path.write_text(
                'FORBIDDEN_PREFIXES = {":SAVE", ":LAN:"}\n'
                'session.write(":RUN")\n',
                encoding="utf-8",
            )
            code, output, _ = run_main(
                "--drift",
                "--index",
                str(INDEX),
                "--code",
                str(code_path),
            )
        self.assertEqual(code, 0)
        self.assertIn("Code command literals: 1", output)


if __name__ == "__main__":
    unittest.main()
