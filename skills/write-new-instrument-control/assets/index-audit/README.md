# Synthetic index-audit fixtures

All files here are synthetic. They contain no vendor manual text and are not a
command reference for any instrument.

There are deliberately two manual fixtures, because the two tools need different
shapes and one must never be mistaken for output of the other:

- `synthetic-manual.txt` — input for `extract_command_pages.py`. It holds the
  shapes the extractor must handle: an optional-root family, a CJK full stop and
  comma glued to a heading, an example line that must not be captured, an
  indented heading, a table row carrying its own parameter, a heading split over
  two lines, and a parent heading that only wraps children.
  Regenerate a TSV from it with the tool; do not hand-edit it.
- `synthetic-diff-manual.tsv` — hand-maintained input for
  `diff_command_index.py`. It is **not** derived from `synthetic-manual.txt`; it
  exists so every gap class (`placeholder-variant`, `short-form`, `example-line`,
  `wrapped-heading`, `true-gap`) appears exactly once against
  `synthetic-index.md`.
- `synthetic-index.md` — the index those two fixtures are compared against.
