#!/usr/bin/env python3
"""Extract command forms and PDF physical pages from a programming manual.

The manual's own command headings and command list are the authority for which
commands exist.  A grep for lines that start with ``:`` is not an index: it
misses every optional-root family such as ``[:SOURce[<n>]]:VOLTage`` because
those headings start with ``[``.

Input is a PDF (converted with ``pdftotext -layout``) or an already extracted
plain-text file, including the paged text this script writes.  Output is:

* paged text with ``===== PDFPAGE <n> =====`` markers;
* a TSV with ``command``, ``pdf_page``, ``source`` and ``context`` columns.

``source`` is ``body`` or ``toc``.  ``context`` distinguishes an ordinary
heading from a parent heading that only wraps child commands.  A TOC entry has
no physical page because its printed page number is not the PDF page.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

PAGE_MARKER_RE = re.compile(r"^===== PDFPAGE (\d+) =====\s*$", re.MULTILINE)
TOC_DOT_RE = re.compile(r"\.{3,}")
LABEL_RE = re.compile(r"^(?:set|query)(?:\s+(?:set|query))?$", re.IGNORECASE)
COMMAND_LIST_RE = re.compile(r"^(?:command\s+list|命令列表)\b", re.IGNORECASE)

COLON_COMMAND_RE = re.compile(r"^(?:\[?:)[A-Za-z*][A-Za-z0-9_<>\[\]:*]*\??$")
COMMON_COMMAND_RE = re.compile(r"^\*[A-Za-z][A-Za-z0-9_<>\[\]:*]*\??$")
PATH_COMMAND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_<>\[\]:*]*\??$")
BARE_PART_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_<>\[\]*]*\??$")
TOC_COMMAND_RE = re.compile(
    r"(?<![A-Za-z0-9_<>\[\]])(?P<cmd>(?:\[?:|\*)[A-Za-z*][^\s.]*?)\s*\.{3,}"
)

TRAILING_PUNCTUATION = "。，、；：！？）】》”’,.;)）"
MAX_COMMAND_LENGTH = 160


@dataclass(frozen=True)
class Heading:
    token: str
    label: str


@dataclass(frozen=True)
class CommandRecord:
    command: str
    page: int | None
    source: str
    context: str


def strip_trailing_punctuation(token: str, *, keep_colon: bool) -> str:
    """Drop CJK and ASCII sentence punctuation; keep a query marker."""

    token = token.strip()
    while token:
        last = token[-1]
        if last == "?":
            break
        if last == ":" and keep_colon:
            break
        if last in TRAILING_PUNCTUATION:
            token = token[:-1]
            continue
        break
    return token


def is_command_like(token: str) -> bool:
    if not token or len(token) > MAX_COMMAND_LENGTH:
        return False
    if COLON_COMMAND_RE.match(token) or COMMON_COMMAND_RE.match(token):
        return True
    return bool(":" in token and PATH_COMMAND_RE.match(token))


def finalize_command(token: str) -> str:
    token = strip_trailing_punctuation(token, keep_colon=False)
    if token.endswith(":"):
        token = token[:-1]
    return token


def split_pages(text: str) -> list[tuple[int, str]]:
    """Return ``(physical_page, text)`` pairs from paged text or raw text."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    markers = list(PAGE_MARKER_RE.finditer(text))
    if markers:
        pages: list[tuple[int, str]] = []
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            pages.append((int(marker.group(1)), text[start:end]))
        return pages

    raw_pages = text.split("\f")
    if raw_pages and not raw_pages[-1].strip():
        raw_pages.pop()
    if not raw_pages:
        return []
    return [(index + 1, page) for index, page in enumerate(raw_pages)]


def render_paged_text(pages: Iterable[tuple[int, str]]) -> str:
    chunks: list[str] = []
    for page_number, content in pages:
        chunks.append(f"===== PDFPAGE {page_number} =====")
        chunks.append(content.strip("\n"))
        chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def parse_heading(
    line: str,
    *,
    require_column_zero: bool,
    table_mode: bool = False,
) -> Heading | None:
    if require_column_zero and line[:1].isspace():
        return None
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    token = strip_trailing_punctuation(parts[0], keep_colon=True)
    rest = parts[1].strip() if len(parts) > 1 else ""
    if rest and not LABEL_RE.fullmatch(rest):
        if not (table_mode and (token.startswith((":", "[:")) or token.startswith("*"))):
            return None

    if token.startswith((":", "[:")) or token.startswith("*"):
        if COLON_COMMAND_RE.match(token) or COMMON_COMMAND_RE.match(token):
            return Heading(token, rest.lower())
        return None
    if ":" in token and PATH_COMMAND_RE.match(token):
        # Some manuals lose the leading colon on a wrapped heading's first line.
        return Heading(token, rest.lower()) if rest else None
    if rest and BARE_PART_RE.match(token):
        # A wrapped heading can continue with a bare mnemonic line, for example
        # ``:SEARCH:...:DATa:`` followed by ``QUALifier   Query``.
        return Heading(token, rest.lower())
    return None


def can_join_heading_parts(first: str, second: str) -> bool:
    if second.startswith(":"):
        return True
    if first.endswith(":"):
        return True
    return not first.startswith(":")


def join_heading_parts(first: str, second: str) -> str:
    if first.endswith(":") and not second.startswith(":"):
        return first + second
    if second.startswith(":"):
        return first + second
    return first + ":" + second


# A real command heading is always followed by a syntax line ("Syntax",
# "命令格式", "Command Format", ...). A parent heading that only wraps children is
# not: it is followed by prose, or by a list of the child commands.
DOC_LABEL_RE = re.compile(
    r"^(?:syntax|command\s+format|format|description|parameter|return|example)\b"
    r"|^(?:命令格式|描述|参数|参数说明|返回|返回格式|示例)",
    re.IGNORECASE,
)


def heading_context(lines: Sequence[str], index: int) -> str:
    """Classify a body heading as a sendable command or a wrapping parent.

    ``index`` is the last line consumed by the heading itself, so a continuation
    line is not read as a sibling. ``wrapped-heading`` when the next few lines
    announce a command list, or when no syntax line appears before a colon path
    does -- a parent heading in a
    Chinese manual is often followed by one line of prose and then the child
    headings, and treating it as a command invents a command the manual never
    documents.
    """

    lookahead = [line.strip() for line in lines[index + 1 : index + 9] if line.strip()]
    for line in lookahead:
        if DOC_LABEL_RE.match(line):
            return "heading"
        if COMMAND_LIST_RE.match(line):
            return "wrapped-heading"
        if COLON_COMMAND_RE.match(line) or BARE_PART_RE.match(line):
            # A sibling command heading or the child list arrives first: this
            # heading only wraps children.
            return "wrapped-heading"
    return "heading"


def parse_toc_entry(line: str, *, toc_page: bool) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if TOC_DOT_RE.search(stripped):
        match = TOC_COMMAND_RE.search(stripped)
        if not match:
            return None
        command = finalize_command(match.group("cmd"))
        return command if is_command_like(command) else None

    if not toc_page or line[:1].isspace():
        return None
    token = strip_trailing_punctuation(stripped.split(None, 1)[0], keep_colon=False)
    if not is_command_like(token):
        return None
    # A long command can consume the whole TOC line and glue the printed page
    # number to the last mnemonic.  Two or more trailing digits are treated as
    # that page number; a line without a dot leader or a glued page is not a
    # TOC entry.
    glued = re.match(r"^(.*?)(\d{2,4})$", token)
    if glued and is_command_like(glued.group(1)):
        return finalize_command(glued.group(1))
    return None


def _merge_record(records: dict[str, CommandRecord], record: CommandRecord) -> None:
    key = record.command.casefold()
    existing = records.get(key)
    if existing is None:
        records[key] = record
        return
    if existing.page is None and record.page is not None:
        records[key] = record
        return
    if existing.page is not None and record.page is None:
        return
    if record.page is not None and existing.page is not None and record.page < existing.page:
        records[key] = record
        return
    if existing.source == "toc" and record.source == "body":
        records[key] = record


def extract_records(
    pages: Iterable[tuple[int, str]],
    *,
    include_toc: bool,
    min_page: int,
    allow_indented: bool = False,
    table_mode: bool = False,
) -> list[CommandRecord]:
    records: dict[str, CommandRecord] = {}

    for page_number, content in pages:
        lines = content.splitlines()
        toc_page = sum(1 for line in lines if TOC_DOT_RE.search(line)) >= 3
        index = 0
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            toc_command = parse_toc_entry(line, toc_page=toc_page)
            if toc_command is not None:
                if include_toc:
                    _merge_record(
                        records,
                        CommandRecord(toc_command, None, "toc", "toc"),
                    )
                index += 1
                continue

            if toc_page:
                index += 1
                continue

            heading = parse_heading(
                line,
                require_column_zero=not allow_indented,
                table_mode=table_mode,
            )
            if heading is None:
                index += 1
                continue

            token = heading.token
            context_index = index
            if heading.label and index + 1 < len(lines):
                continuation = parse_heading(lines[index + 1], require_column_zero=False)
                if (
                    continuation is not None
                    and continuation.label
                    and can_join_heading_parts(token, continuation.token)
                ):
                    token = join_heading_parts(token, continuation.token)
                    index += 1

            command = finalize_command(token)
            if is_command_like(command):
                if page_number >= min_page:
                    _merge_record(
                        records,
                        CommandRecord(
                            command,
                            page_number,
                            "body",
                            heading_context(lines, index),
                        ),
                    )
            index += 1

    return sorted(
        records.values(),
        key=lambda record: (
            record.page is None,
            record.page if record.page is not None else 0,
            record.command.casefold(),
        ),
    )


def load_manual_text(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8", errors="replace")

    executable = shutil.which("pdftotext")
    if executable is None:
        raise RuntimeError(
            "pdftotext not found; install poppler-utils or pass an extracted text file"
        )
    completed = subprocess.run(
        [executable, "-layout", "-enc", "UTF-8", str(path), "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"pdftotext failed for {path}: {detail or completed.returncode}")
    return completed.stdout.decode("utf-8", "replace")


def write_text_output(path: Path, pages: Iterable[tuple[int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_paged_text(pages), encoding="utf-8")


def write_tsv_output(
    path: Path,
    records: Sequence[CommandRecord],
    *,
    manual: Path,
    pdf_pages: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# manual: {manual.resolve()}",
        f"# pdf_pages: {pdf_pages}",
        "command\tpdf_page\tsource\tcontext",
    ]
    for record in records:
        page = "" if record.page is None else str(record.page)
        lines.append(f"{record.command}\t{page}\t{record.source}\t{record.context}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract command headings and TOC entries with PDF physical pages "
            "from a programming manual."
        )
    )
    parser.add_argument("manual", type=Path, help="PDF or already extracted plain-text manual")
    parser.add_argument("--out-text", type=Path, required=True, help="paged text output path")
    parser.add_argument("--out-tsv", type=Path, required=True, help="command/page TSV output path")
    parser.add_argument(
        "--first-page",
        type=int,
        default=1,
        help="first PDF page to include in the paged text and body scan (default: 1)",
    )
    parser.add_argument(
        "--min-page",
        type=int,
        default=None,
        help=(
            "minimum PDF page for body command records (default: --first-page); "
            "TOC entries have no page and are unaffected"
        ),
    )
    parser.add_argument(
        "--allow-indented",
        action="store_true",
        help=(
            "accept command headings that are indented (manuals that print commands "
            "inside a table cell); without it only column-zero headings are read"
        ),
    )
    parser.add_argument(
        "--table-mode",
        action="store_true",
        help=(
            "read command tables, where a row carries the command path and its "
            "parameter text on the same line instead of a separate syntax line"
        ),
    )
    parser.add_argument(
        "--include-toc",
        action="store_true",
        help="also collect command spellings from TOC/command-list lines (page left empty)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.first_page < 1:
        print("error: --first-page must be >= 1", file=sys.stderr)
        return 2
    if args.min_page is not None and args.min_page < 1:
        print("error: --min-page must be >= 1", file=sys.stderr)
        return 2

    try:
        text = load_manual_text(args.manual)
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    all_pages = split_pages(text)
    if not all_pages:
        print(f"error: no pages found in {args.manual}", file=sys.stderr)
        return 2
    pdf_pages = max(page_number for page_number, _ in all_pages)
    selected_pages = [
        (page_number, content)
        for page_number, content in all_pages
        if page_number >= args.first_page
    ]
    if not selected_pages:
        print(
            f"error: --first-page {args.first_page} is past the last page ({pdf_pages})",
            file=sys.stderr,
        )
        return 2

    min_page = args.min_page if args.min_page is not None else args.first_page
    records = extract_records(
        selected_pages,
        allow_indented=args.allow_indented,
        table_mode=args.table_mode,
        include_toc=args.include_toc,
        min_page=min_page,
    )

    try:
        write_text_output(args.out_text, selected_pages)
        write_tsv_output(
            args.out_tsv,
            records,
            manual=args.manual,
            pdf_pages=pdf_pages,
        )
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    body_count = sum(1 for record in records if record.source == "body")
    toc_count = len(records) - body_count
    print(
        f"extracted {len(records)} command forms "
        f"({body_count} body, {toc_count} toc) from {len(selected_pages)} of "
        f"{pdf_pages} pages"
    )
    print(f"paged text: {args.out_text}")
    print(f"command TSV: {args.out_tsv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
