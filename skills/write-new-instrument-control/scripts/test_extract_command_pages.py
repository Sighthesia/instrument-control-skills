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

import extract_command_pages as ecp  # noqa: E402

MANUAL = ASSETS / "synthetic-manual.txt"


def parse_tsv(path: Path) -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    metadata: dict[str, str] = {}
    rows: list[tuple[str, str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            key, _, value = line[1:].partition(":")
            metadata[key.strip()] = value.strip()
            continue
        fields = line.split("\t")
        if fields[0].lower() == "command":
            continue
        rows.append(tuple(fields + [""] * (4 - len(fields)))[:4])  # type: ignore[arg-type]
    return metadata, rows


def run_extract(*extra: str) -> tuple[str, dict[str, str], list[tuple[str, str, str, str]]]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        out_text = root / "manual.txt"
        out_tsv = root / "commands.tsv"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ecp.main(
                [
                    str(MANUAL),
                    "--out-text",
                    str(out_text),
                    "--out-tsv",
                    str(out_tsv),
                    *extra,
                ]
            )
        if code != 0:
            raise AssertionError(f"extract failed ({code}): {stderr.getvalue()}")
        return (
            out_text.read_text(encoding="utf-8"),
            *parse_tsv(out_tsv),
        )


class ExtractCommandPagesTests(unittest.TestCase):
    def test_paged_text_has_physical_page_markers(self) -> None:
        text, metadata, rows = run_extract()
        self.assertEqual(metadata["pdf_pages"], "5")
        for page in range(1, 5):
            self.assertIn(f"===== PDFPAGE {page} =====", text)
        self.assertNotIn("PDFPAGE 0", text)
        self.assertEqual(len(rows), 8)

    def test_body_forms_keep_optional_root_query_and_min_page(self) -> None:
        _, metadata, rows = run_extract()
        by_command = {row[0]: row for row in rows}

        self.assertIn("[:SOURce[<n>]]:VOLTage[:DC]", by_command)
        self.assertEqual(by_command["[:SOURce[<n>]]:VOLTage[:DC]"][1], "3")
        self.assertIn(":MEASure:VPP?", by_command)
        self.assertEqual(by_command[":RUN"][1], "2")
        self.assertIn("*IDN?", by_command)
        self.assertIn(":STOP", by_command)
        self.assertNotIn(":STOP，", by_command)
        self.assertNotIn(":CHANnel1:SCALe", by_command)
        self.assertNotIn(":CHANnel<n>:SCALe", by_command)

    def test_wrapped_heading_is_joined_and_parent_is_marked(self) -> None:
        _, _, rows = run_extract()
        by_command = {row[0]: row for row in rows}
        self.assertIn(":WRAPped:PARent:CHILd", by_command)
        self.assertEqual(by_command[":WRAPped:PARent:CHILd"][3], "heading")
        self.assertEqual(by_command[":PARent:ONLY"][3], "wrapped-heading")
        self.assertNotIn(":CHILd", by_command)
        self.assertNotIn(":WRAPped:PARent", by_command)

    def test_min_page_filters_body_but_keeps_toc_spellings(self) -> None:
        _, _, rows = run_extract("--min-page", "3", "--include-toc")
        by_command = {row[0]: row for row in rows}
        self.assertEqual(by_command[":RUN"][1], "")
        self.assertEqual(by_command[":RUN"][2], "toc")
        self.assertIn(":MEASure:VPP?", by_command)
        self.assertIn(":TOConly:COMMand", by_command)
        self.assertEqual(by_command[":TOConly:COMMand"][1], "")
        self.assertEqual(by_command[":TOConly:COMMand"][2], "toc")

    def test_include_toc_collects_toc_only_spellings(self) -> None:
        _, _, default_rows = run_extract()
        self.assertNotIn(":TOConly:COMMand", {row[0] for row in default_rows})

        _, _, toc_rows = run_extract("--include-toc")
        by_command = {row[0]: row for row in toc_rows}
        self.assertIn(":TOConly:COMMand", by_command)
        self.assertEqual(by_command[":TOConly:COMMand"][1], "")
        self.assertEqual(by_command[":TOConly:COMMand"][2], "toc")
        self.assertIn(":GLUED:COMMand", by_command)
        self.assertNotIn(":GLUED:COMMand200", by_command)

    def test_first_page_limits_text_and_records(self) -> None:
        text, metadata, rows = run_extract("--first-page", "3")
        self.assertEqual(metadata["pdf_pages"], "5")
        self.assertTrue(text.startswith("===== PDFPAGE 3 ====="))
        self.assertNotIn("===== PDFPAGE 2 =====", text)
        self.assertNotIn(":RUN", {row[0] for row in rows})
        self.assertIn("[:SOURce[<n>]]:VOLTage[:DC]", {row[0] for row in rows})

    def test_extracted_text_can_be_re_extracted(self) -> None:
        text, _, first_rows = run_extract()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path = root / "paged.txt"
            text_path.write_text(text, encoding="utf-8")
            out_text = root / "again.txt"
            out_tsv = root / "again.tsv"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = ecp.main(
                    [
                        str(text_path),
                        "--out-text",
                        str(out_text),
                        "--out-tsv",
                        str(out_tsv),
                    ]
                )
            self.assertEqual(code, 0, stderr.getvalue())
            _, second_rows = parse_tsv(out_tsv)
        self.assertEqual(
            {row[0] for row in first_rows},
            {row[0] for row in second_rows},
        )

    def test_missing_manual_returns_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = ecp.main(
                    [
                        str(Path(directory) / "missing.pdf"),
                        "--out-text",
                        str(Path(directory) / "out.txt"),
                        "--out-tsv",
                        str(Path(directory) / "out.tsv"),
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("error:", stderr.getvalue())

    def test_indented_heading_needs_the_flag(self) -> None:
        _, _, rows = run_extract()
        without = {row[0] for row in rows}
        _, _, indented_rows = run_extract("--allow-indented")
        with_flag = {row[0] for row in indented_rows}
        self.assertNotIn(":INDented:ONLY", without)
        self.assertIn(":INDented:ONLY", with_flag)

    def test_table_mode_reads_a_row_with_its_parameter(self) -> None:
        _, _, rows = run_extract("--allow-indented", "--table-mode")
        by_command = {row[0]: row for row in rows}
        self.assertIn(":TABle:MODE", by_command)
        self.assertEqual(by_command[":TABle:MODE"][1], "5")

    def test_table_mode_off_drops_a_row_with_a_parameter(self) -> None:
        _, _, rows = run_extract("--allow-indented")
        self.assertNotIn(":TABle:MODE", {row[0] for row in rows})


if __name__ == "__main__":
    unittest.main()
