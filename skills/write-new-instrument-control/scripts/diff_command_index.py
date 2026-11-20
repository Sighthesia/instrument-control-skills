#!/usr/bin/env python3
"""Compare a manual command extraction with a Skill command index.

Two modes:

``--manual TSV --index PATH``
    Coverage audit.  Every command form extracted from the manual is normalized
    and matched against the index.  Residuals are classified only by rules that
    can be decided from the form itself: placeholder variant, short form,
    example line, wrapped heading, or a true gap.  A true gap is never hidden to
    make a number smaller.

``--drift --index PATH --code PATH...``
    Drift audit.  Literal SCPI command strings in the code are compared with the
    index.  Commands the code sends but the index does not list are reported as
    drift.  Index rows marked ``hardware-verified`` that the code never sends
    are reported as hints, not errors.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import functools
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

PAGE_HEADER = "command\tpdf_page\tsource\tcontext"
INDEX_COMMAND_HEADERS = {"command", "syntax", "query"}
INDEX_PLACEHOLDER_NAMES = {
    "n",
    "x",
    "m",
    "r",
    "d",
    "p",
    "i",
    "s",
    "t",
    "k",
    "a",
    "b",
    "c",
}
TRAILING_PUNCTUATION = "。，、；：！？）】》”’,.;)）"
CLASSIFICATIONS = (
    "placeholder-variant",
    "short-form",
    "example-line",
    "wrapped-heading",
    "true-gap",
)
CLASSIFICATION_LABELS = {
    "placeholder-variant": "placeholder variant",
    "short-form": "short form",
    "example-line": "example line",
    "wrapped-heading": "wrapped heading",
    "true-gap": "true gap",
}


@dataclass(frozen=True)
class ManualForm:
    command: str
    page: int | None
    source: str
    context: str


@dataclass(frozen=True)
class ManualData:
    forms: tuple[ManualForm, ...]
    manual_path: str
    pdf_pages: int | None


@dataclass(frozen=True)
class IndexForm:
    command: str
    verified: bool
    row: int


@dataclass(frozen=True)
class IndexData:
    forms: tuple[IndexForm, ...]
    path: str


@dataclass(frozen=True)
class CodeCommand:
    command: str
    path: str
    line: int


@dataclass(frozen=True)
class CoverageResult:
    manual: ManualData
    index: IndexData
    covered: tuple[tuple[ManualForm, IndexForm], ...]
    gaps: tuple[tuple[ManualForm, str, IndexForm | None], ...]

    @property
    def true_gaps(self) -> tuple[tuple[ManualForm, str, IndexForm | None], ...]:
        return tuple(item for item in self.gaps if item[1] == "true-gap")

    @property
    def classification_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in CLASSIFICATIONS}
        for _, classification, _ in self.gaps:
            counts[classification] += 1
        return counts


@dataclass(frozen=True)
class DriftResult:
    index: IndexData
    code_paths: tuple[str, ...]
    code_commands: tuple[CodeCommand, ...]
    unindexed: tuple[tuple[CodeCommand, IndexForm | None], ...]
    verified_not_sent: tuple[IndexForm, ...]


def strip_command_token(raw: str) -> str:
    """Return the command token, dropping parameters and sentence punctuation."""

    token = raw.strip().strip("`").strip()
    if not token:
        return ""
    token = token.split(None, 1)[0]
    while token:
        last = token[-1]
        if last == "?":
            break
        if last in TRAILING_PUNCTUATION:
            token = token[:-1]
            continue
        break
    return token


def is_command_like(token: str) -> bool:
    if not token or len(token) > 160:
        return False
    if token.startswith("*"):
        return bool(re.match(r"^\*[A-Za-z][A-Za-z0-9_<>\[\]:*]*\??$", token))
    if token.startswith((":", "[:")):
        return bool(re.match(r"^(?:\[?:)[A-Za-z*][A-Za-z0-9_<>\[\]:*]*\??$", token))
    return bool(":" in token and re.match(r"^[A-Za-z][A-Za-z0-9_<>\[\]:*]*\??$", token))


def is_index_command_like(token: str) -> bool:
    """Accept a table-cell command, including a bare mnemonic such as ``TDIV``."""

    if is_command_like(token):
        return True
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_<>\[\]:*]*\??$", token))


@functools.lru_cache(maxsize=None)
def normalize_command(raw: str) -> str:
    """Normalize a SCPI form for set comparison.

    Lowercase, drop a trailing query marker, drop optional brackets, turn every
    ``<...>`` placeholder into ``<n>``, and turn a numeric instance index at the
    end of a component into ``<n>`` (``CHAN1`` -> ``CHAN<n>``).  Numeric and
    placeholder spellings therefore share one canonical form.
    """

    token = strip_command_token(raw)
    if not token:
        return ""
    if token.endswith("?"):
        token = token[:-1]
    token = token.replace("[", "").replace("]", "")
    token = re.sub(r"<[^<>]+>", "<n>", token)
    token = token.lower()
    components = []
    for component in token.split(":"):
        component = re.sub(r"\d+$", "<n>", component)
        components.append(component)
    return ":".join(components).lstrip(":")


@functools.lru_cache(maxsize=None)
def command_components(raw: str) -> tuple[str, ...]:
    normalized = normalize_command(raw)
    return tuple(normalized.split(":")) if normalized else ()


def component_matches(left: str, right: str) -> bool:
    left_match = re.match(r"^([a-z*]+)(.*)$", left)
    right_match = re.match(r"^([a-z*]+)(.*)$", right)
    if not left_match or not right_match:
        return left == right
    left_mnemonic, left_suffix = left_match.groups()
    right_mnemonic, right_suffix = right_match.groups()
    if left_suffix != right_suffix:
        return False
    return left_mnemonic.startswith(right_mnemonic) or right_mnemonic.startswith(left_mnemonic)


def commands_match(left: str, right: str) -> bool:
    left_components = command_components(left)
    right_components = command_components(right)
    if len(left_components) != len(right_components):
        return False
    return all(
        component_matches(a, b) for a, b in zip(left_components, right_components)
    )


def commands_prefix_match(short: str, long: str) -> bool:
    short_components = command_components(short)
    long_components = command_components(long)
    if not short_components or len(short_components) > len(long_components):
        return False
    return all(
        component_matches(a, b)
        for a, b in zip(short_components, long_components[: len(short_components)])
    )


def _loose_component_equal(left: str, right: str) -> bool:
    def without_instance_letter(component: str) -> str:
        if len(component) > 2 and component[-1] in "abcd":
            return component[:-1]
        return component

    left = without_instance_letter(left)
    right = without_instance_letter(right)
    if left == right:
        return True
    left_match = re.match(r"^([a-z*]+)(.*)$", left)
    right_match = re.match(r"^([a-z*]+)(.*)$", right)
    if not left_match or not right_match:
        return False
    left_mnemonic, left_suffix = left_match.groups()
    right_mnemonic, right_suffix = right_match.groups()
    if left_suffix != right_suffix:
        return False
    return left_mnemonic.startswith(right_mnemonic) or right_mnemonic.startswith(left_mnemonic)


def loose_components(raw: str) -> tuple[str, ...]:
    """Components with index markers removed, for placeholder-variant checks."""

    normalized = normalize_command(raw).replace("<n>", "")
    return tuple(normalized.split(":")) if normalized else ()


def placeholder_variant(manual: ManualForm, index_forms: Sequence[IndexForm]) -> IndexForm | None:
    manual_components = loose_components(manual.command)
    if not manual_components:
        return None
    for index_form in index_forms:
        index_components = loose_components(index_form.command)
        if len(index_components) != len(manual_components):
            continue
        if all(
            _loose_component_equal(a, b)
            for a, b in zip(manual_components, index_components)
        ):
            return index_form
    return None


def has_non_index_placeholder(command: str) -> bool:
    for name in re.findall(r"<([^<>]+)>", command):
        if name not in INDEX_PLACEHOLDER_NAMES and name.lower() not in INDEX_PLACEHOLDER_NAMES:
            return True
    return ";" in command


def wrapped_heading_child(
    manual: ManualForm, index_forms: Sequence[IndexForm]
) -> IndexForm | None:
    manual_components = command_components(manual.command)
    if not manual_components:
        return None
    children = [
        index_form
        for index_form in index_forms
        if len(command_components(index_form.command)) > len(manual_components)
        and commands_prefix_match(manual.command, index_form.command)
    ]
    if manual.context == "wrapped-heading":
        return children[0] if children else None
    return children[0] if len(children) >= 2 else None


def short_form_source(manual: ManualForm, index_forms: Sequence[IndexForm]) -> IndexForm | None:
    for index_form in index_forms:
        index_components = command_components(index_form.command)
        manual_components = command_components(manual.command)
        if len(index_components) < len(manual_components) and commands_prefix_match(
            index_form.command, manual.command
        ):
            return index_form
    return None


def nearest_form(manual: ManualForm, index_forms: Sequence[IndexForm]) -> IndexForm | None:
    target = normalize_command(manual.command)
    if not target:
        return None
    best: IndexForm | None = None
    best_ratio = 0.0
    for index_form in index_forms:
        candidate = normalize_command(index_form.command)
        if not candidate:
            continue
        ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = index_form
    return best if best_ratio >= 0.55 else None


def classify_gap(
    manual: ManualForm, index_forms: Sequence[IndexForm]
) -> tuple[str, IndexForm | None]:
    if has_non_index_placeholder(manual.command):
        return "example-line", nearest_form(manual, index_forms)

    variant = placeholder_variant(manual, index_forms)
    if variant is not None:
        return "placeholder-variant", variant

    if manual.context == "wrapped-heading":
        child = wrapped_heading_child(manual, index_forms)
        if child is not None:
            return "wrapped-heading", child

    if not manual.context:
        child = wrapped_heading_child(manual, index_forms)
        if child is not None and len(
            [
                index_form
                for index_form in index_forms
                if len(command_components(index_form.command))
                > len(command_components(manual.command))
                and commands_prefix_match(manual.command, index_form.command)
            ]
        ) >= 2:
            return "wrapped-heading", child

    short = short_form_source(manual, index_forms)
    if short is not None and manual.context in {"", "toc"}:
        return "short-form", short

    return "true-gap", nearest_form(manual, index_forms)


def subsystem_label(command: str) -> str:
    normalized = normalize_command(command)
    if not normalized:
        return "(unknown)"
    root = normalized.split(":", 1)[0].split("<", 1)[0]
    return root or "(unknown)"


def parse_manual_tsv(path: Path) -> ManualData:
    manual_path = str(path)
    pdf_pages: int | None = None
    records: dict[str, ManualForm] = {}
    header_seen = False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            if line.startswith("# manual:"):
                manual_path = line.split(":", 1)[1].strip()
            elif line.startswith("# pdf_pages:"):
                try:
                    pdf_pages = int(line.split(":", 1)[1].strip())
                except ValueError as exc:
                    raise ValueError(
                        f"{path}:{line_number}: malformed pdf_pages metadata"
                    ) from exc
            continue
        fields = line.split("\t")
        if not header_seen and fields[0].strip().lower() == "command":
            header_seen = True
            continue
        if len(fields) < 2:
            raise ValueError(f"{path}:{line_number}: expected command and page columns")
        command = fields[0].strip()
        if not command or any(character.isspace() for character in command):
            raise ValueError(f"{path}:{line_number}: malformed command {command!r}")
        try:
            page = int(fields[1]) if fields[1].strip() else None
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: malformed page {fields[1]!r}") from exc
        source = fields[2].strip() if len(fields) > 2 and fields[2].strip() else "body"
        if source not in {"body", "toc"}:
            raise ValueError(f"{path}:{line_number}: unknown source {source!r}")
        context = fields[3].strip() if len(fields) > 3 else ""
        key = command.casefold()
        existing = records.get(key)
        if existing is None:
            records[key] = ManualForm(command, page, source, context)
            continue
        if existing.page is None and page is not None:
            records[key] = ManualForm(command, page, source, context)
        elif existing.page is not None and page is not None and page < existing.page:
            records[key] = ManualForm(command, page, source, context)
        elif existing.source == "toc" and source == "body":
            records[key] = ManualForm(command, page, source, context)

    if not records:
        raise ValueError(f"{path}: no command forms found")
    if pdf_pages is None:
        pages = [form.page for form in records.values() if form.page is not None]
        pdf_pages = max(pages) if pages else None
    ordered = sorted(
        records.values(),
        key=lambda form: (
            form.page is None,
            form.page if form.page is not None else 0,
            form.command.casefold(),
        ),
    )
    return ManualData(tuple(ordered), manual_path, pdf_pages)


def _split_table_row(line: str) -> list[str]:
    escaped = line.replace("\\|", "\x00")
    return [cell.replace("\x00", "|").strip() for cell in escaped.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _extract_code_spans(cell: str) -> list[str]:
    spans = re.findall(r"`([^`]+)`", cell)
    if spans:
        return spans
    candidate = cell.strip()
    return [candidate] if is_command_like(strip_command_token(candidate)) else []


def parse_index_markdown(path: Path) -> IndexData:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    forms: dict[str, list[IndexForm]] = {}
    command_columns: list[int] = []
    in_table = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            # A blank line inside a table does not end the table: some indexes
            # insert one for readability and continue with the same columns.
            index += 1
            continue
        if not line.strip().startswith("|"):
            command_columns = []
            in_table = False
            index += 1
            continue
        if index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            header = _split_table_row(line)
            command_columns = [
                column
                for column, cell in enumerate(header)
                if cell.strip().strip("`").lower() in INDEX_COMMAND_HEADERS
            ]
            in_table = bool(command_columns)
            index += 2
            continue
        if _is_table_separator(line):
            index += 1
            continue
        if in_table and command_columns:
            cells = _split_table_row(line)
            verified = "hardware-verified" in line.lower()
            for command_column in command_columns:
                if command_column >= len(cells):
                    continue
                for span in _extract_code_spans(cells[command_column]):
                    command = strip_command_token(span)
                    if not is_index_command_like(command):
                        continue
                    key = normalize_command(command)
                    if not key:
                        continue
                    forms.setdefault(key, []).append(
                        IndexForm(command, verified, index + 1)
                    )
        index += 1

    if not forms:
        raise ValueError(f"{path}: no command table rows found")
    result = []
    for entries in forms.values():
        first = entries[0]
        result.append(
            IndexForm(first.command, any(entry.verified for entry in entries), first.row)
        )
    result.sort(key=lambda form: form.command.casefold())
    return IndexData(tuple(result), str(path))


def analyze_coverage(manual: ManualData, index: IndexData) -> CoverageResult:
    by_component_count: dict[int, list[IndexForm]] = {}
    for index_form in index.forms:
        by_component_count.setdefault(
            len(command_components(index_form.command)), []
        ).append(index_form)

    covered: list[tuple[ManualForm, IndexForm]] = []
    gaps: list[tuple[ManualForm, str, IndexForm | None]] = []
    for manual_form in manual.forms:
        count = len(command_components(manual_form.command))
        candidates = by_component_count.get(count, [])
        match = next(
            (
                index_form
                for index_form in candidates
                if commands_match(manual_form.command, index_form.command)
            ),
            None,
        )
        if match is not None:
            covered.append((manual_form, match))
            continue
        classification, nearest = classify_gap(manual_form, index.forms)
        gaps.append((manual_form, classification, nearest))
    return CoverageResult(manual, index, tuple(covered), tuple(gaps))


def _looks_like_command_literal(value: str) -> bool:
    token = strip_command_token(value)
    return bool(token) and is_command_like(token)


def _literal_from_node(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Constant) and isinstance(node.value, bytes):
        return node.value.decode("ascii", "replace")
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("<n>")
            else:
                return None
        return "".join(parts)
    return None


def _is_guard_assignment(node: ast.AST) -> bool:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    for target in targets:
        if isinstance(target, ast.Name) and re.search(
            r"forbidden|prefix|blocked|guard", target.id, re.IGNORECASE
        ):
            return True
    return False


def extract_code_commands(paths: Sequence[Path], *, include_tests: bool = False) -> list[CodeCommand]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                candidate
                for candidate in sorted(path.rglob("*.py"))
                if "__pycache__" not in candidate.parts
                and (include_tests or not candidate.name.startswith("test_"))
            )
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(path)

    commands: list[CodeCommand] = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            print(f"warning: skipped {path}: {exc}", file=sys.stderr)
            continue

        def visit(node: ast.AST, *, guarded: bool = False) -> None:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and _is_guard_assignment(node):
                guarded = True
            value = _literal_from_node(node)
            if value is not None and not guarded:
                command = strip_command_token(value)
                if (
                    _looks_like_command_literal(command)
                    and not command.endswith(":")
                ):
                    commands.append(
                        CodeCommand(command, str(path), getattr(node, "lineno", 0))
                    )
                return
            for child in ast.iter_child_nodes(node):
                visit(child, guarded=guarded)

        visit(tree)
    return commands


def analyze_drift(
    index: IndexData, code_paths: Sequence[Path], *, include_tests: bool = False
) -> DriftResult:
    code_commands = extract_code_commands(code_paths, include_tests=include_tests)
    by_component_count: dict[int, list[IndexForm]] = {}
    for index_form in index.forms:
        by_component_count.setdefault(
            len(command_components(index_form.command)), []
        ).append(index_form)

    unindexed: list[tuple[CodeCommand, IndexForm | None]] = []
    for code_command in code_commands:
        count = len(command_components(code_command.command))
        exact = next(
            (
                index_form
                for index_form in by_component_count.get(count, [])
                if commands_match(code_command.command, index_form.command)
            ),
            None,
        )
        if exact is not None:
            continue
        prefix = next(
            (
                index_form
                for index_form in index.forms
                if commands_prefix_match(code_command.command, index_form.command)
            ),
            None,
        )
        if prefix is not None:
            continue
        unindexed.append(
            (
                code_command,
                nearest_form(
                    ManualForm(code_command.command, None, "body", ""), index.forms
                ),
            )
        )

    verified_not_sent: list[IndexForm] = []
    for index_form in index.forms:
        if not index_form.verified:
            continue
        sent = any(
            commands_match(code_command.command, index_form.command)
            or commands_prefix_match(index_form.command, code_command.command)
            for code_command in code_commands
        )
        if not sent:
            verified_not_sent.append(index_form)

    return DriftResult(
        index,
        tuple(str(path) for path in code_paths),
        tuple(code_commands),
        tuple(unindexed),
        tuple(verified_not_sent),
    )


def _md_code(value: str) -> str:
    return "`" + value.replace("|", "\\|") + "`"


def _coverage_by_subsystem(result: CoverageResult) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for manual_form, index_form in result.covered:
        label = subsystem_label(manual_form.command)
        group = groups.setdefault(
            label,
            {
                "label": label,
                "manual": 0,
                "covered": 0,
                "gaps": 0,
                "true": 0,
                **{name: 0 for name in CLASSIFICATIONS},
            },
        )
        group["manual"] = int(group["manual"]) + 1
        group["covered"] = int(group["covered"]) + 1
    for manual_form, classification, _ in result.gaps:
        label = subsystem_label(manual_form.command)
        group = groups.setdefault(
            label,
            {
                "label": label,
                "manual": 0,
                "covered": 0,
                "gaps": 0,
                "true": 0,
                **{name: 0 for name in CLASSIFICATIONS},
            },
        )
        group["manual"] = int(group["manual"]) + 1
        group["gaps"] = int(group["gaps"]) + 1
        group[classification] = int(group[classification]) + 1
        if classification == "true-gap":
            group["true"] = int(group["true"]) + 1
    return sorted(
        groups.values(),
        key=lambda group: (-int(group["gaps"]), str(group["label"]).lower()),
    )


def render_coverage_markdown(result: CoverageResult) -> str:
    counts = result.classification_counts
    manual = result.manual
    index = result.index
    lines = [
        "# Command index coverage audit",
        "",
        f"- Date: {date.today().isoformat()}",
        f"- Manual: `{manual.manual_path}`",
        f"- Manual pages: {manual.pdf_pages if manual.pdf_pages is not None else 'unknown'}",
        f"- Index: `{index.path}`",
        f"- Manual forms: {len(manual.forms)}",
        f"- Index forms: {len(index.forms)}",
        f"- Covered: {len(result.covered)}",
        f"- Gaps: {len(result.gaps)}",
        f"- True gaps: {len(result.true_gaps)}",
        "",
        "## Gaps by subsystem",
        "",
        "| Subsystem | Manual forms | Covered | Gaps | True gaps | "
        + " | ".join(CLASSIFICATION_LABELS[name] for name in CLASSIFICATIONS)
        + " |",
        "|---|---:|---:|---:|---:|"
        + "---:|" * len(CLASSIFICATIONS),
    ]
    for group in _coverage_by_subsystem(result):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(group["label"]),
                    str(group["manual"]),
                    str(group["covered"]),
                    str(group["gaps"]),
                    str(group["true"]),
                    *[str(group[name]) for name in CLASSIFICATIONS],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Classification counts",
            "",
            "| Classification | Count |",
            "|---|---:|",
        ]
    )
    for name in CLASSIFICATIONS:
        lines.append(f"| {CLASSIFICATION_LABELS[name]} | {counts[name]} |")
    lines.extend(
        [
            "",
            "## Gaps",
            "",
            "| Manual form | PDF page | Source | Context | Classification | Nearest index form |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for manual_form, classification, nearest in result.gaps:
        page = "" if manual_form.page is None else str(manual_form.page)
        nearest_text = _md_code(nearest.command) if nearest is not None else ""
        lines.append(
            f"| {_md_code(manual_form.command)} | {page} | {manual_form.source} | "
            f"{manual_form.context or '—'} | {classification} | {nearest_text} |"
        )
    true_gaps = result.true_gaps
    lines.extend(["", "## True gaps (manual review required)", ""])
    if not true_gaps:
        lines.append("None.")
    else:
        for manual_form, _, nearest in true_gaps:
            page = "" if manual_form.page is None else f" (PDF p. {manual_form.page})"
            nearest_text = (
                f"; nearest index form: {_md_code(nearest.command)}"
                if nearest is not None
                else ""
            )
            lines.append(f"- {_md_code(manual_form.command)}{page}{nearest_text}")
    return "\n".join(lines) + "\n"


def print_coverage(result: CoverageResult, *, verbose: bool) -> None:
    counts = result.classification_counts
    print(f"Manual: {result.manual.manual_path}")
    print(
        "Manual pages: "
        f"{result.manual.pdf_pages if result.manual.pdf_pages is not None else 'unknown'}"
    )
    print(f"Index: {result.index.path}")
    print(f"Manual forms: {len(result.manual.forms)}")
    print(f"Index forms: {len(result.index.forms)}")
    print(f"Covered: {len(result.covered)}")
    print(f"Gaps: {len(result.gaps)}")
    print(f"True gaps: {len(result.true_gaps)}")
    print()

    if result.gaps:
        print("Gaps:")
        for manual_form, classification, nearest in result.gaps:
            page = "toc" if manual_form.page is None else f"p.{manual_form.page}"
            suffix = ""
            if verbose:
                suffix = f"  source={manual_form.source} context={manual_form.context or '-'}"
                if nearest is not None:
                    suffix += f" nearest={nearest.command}"
            print(f"  {manual_form.command}  {page}  [{classification}]{suffix}")
        print()

    print("Gaps by subsystem:")
    for group in _coverage_by_subsystem(result):
        details = ", ".join(
            f"{CLASSIFICATION_LABELS[name]}={group[name]}"
            for name in CLASSIFICATIONS
            if int(group[name])
        )
        print(
            f"  {group['label']:<20} gaps={group['gaps']:<4} "
            f"true={group['true']:<3} {details}"
        )
    print()

    print("Classification counts:")
    for name in CLASSIFICATIONS:
        print(f"  {CLASSIFICATION_LABELS[name]:<20} {counts[name]}")
    print()

    print("True gaps (manual review required):")
    if not result.true_gaps:
        print("  none")
    else:
        for manual_form, _, nearest in result.true_gaps:
            page = "toc" if manual_form.page is None else f"p.{manual_form.page}"
            nearest_text = f" nearest={nearest.command}" if nearest is not None else ""
            print(f"  {manual_form.command}  {page}{nearest_text}")
    print()
    print(
        f"Summary: manual forms={len(result.manual.forms)} "
        f"covered={len(result.covered)} gaps={len(result.gaps)} "
        f"true gaps={len(result.true_gaps)}"
    )


def print_drift(result: DriftResult) -> None:
    print("Drift check")
    print(f"Index: {result.index.path}")
    print("Code: " + ", ".join(result.code_paths))
    print(f"Code command literals: {len(result.code_commands)}")
    print(f"Code sends but index does not list: {len(result.unindexed)}")
    for code_command, nearest in result.unindexed:
        nearest_text = f" nearest={nearest.command}" if nearest is not None else ""
        print(f"  {code_command.command}  {code_command.path}:{code_command.line}{nearest_text}")
    print()
    print(
        "Index hardware-verified but code does not send "
        f"(hint only): {len(result.verified_not_sent)}"
    )
    for index_form in result.verified_not_sent:
        print(f"  {index_form.command}")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a command index against a manual extraction or against the "
            "literal commands in code."
        )
    )
    parser.add_argument("--manual", type=Path, help="TSV written by extract_command_pages.py")
    parser.add_argument("--index", type=Path, required=True, help="command-reference.md path")
    parser.add_argument("--verbose", action="store_true", help="include source, context, nearest form")
    parser.add_argument("--report", type=Path, help="write a Markdown report")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="exit 1 when the coverage audit finds a true gap",
    )
    parser.add_argument(
        "--drift",
        action="store_true",
        help="compare literal code commands with the index instead of manual coverage",
    )
    parser.add_argument(
        "--code",
        type=Path,
        nargs="+",
        default=[],
        help="code file or directory (repeatable; used with --drift)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="include test_*.py files in the drift scan (default: skip them)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.drift:
        if not args.code:
            print("error: --drift requires --code", file=sys.stderr)
            return 2
        try:
            index = parse_index_markdown(args.index)
            result = analyze_drift(
                index, args.code, include_tests=args.include_tests
            )
        except (OSError, ValueError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print_drift(result)
        return 1 if result.unindexed else 0

    if args.manual is None:
        print("error: coverage mode requires --manual", file=sys.stderr)
        return 2
    try:
        manual = parse_manual_tsv(args.manual)
        index = parse_index_markdown(args.index)
        result = analyze_coverage(manual, index)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_coverage(result, verbose=args.verbose)
    if args.report is not None:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(render_coverage_markdown(result), encoding="utf-8")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Markdown report: {args.report}")

    if args.fail_on_missing and result.true_gaps:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
