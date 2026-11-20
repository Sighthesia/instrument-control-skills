# Command Index and Coverage

A command index is a coverage claim. A coverage claim needs an authoritative
source, a method, and a date; a row count alone proves nothing.

## Authoritative source

Take command forms from the manual's own command table, contents page, or
per-command headings. Do not extract them by searching for lines that look like
syntax: a pattern anchored on `:` misses every optional-root family, because
those syntax lines begin with `[` (`[:SOURce[<n>]]:...`, `[:SENSe[1]]:...`,
`[:TRACe[<n>]]:...`).

Measured in this repository when indexes were audited against their manuals:

| Skill | Documented forms | Rows before the audit |
|---|---:|---:|
| `gwinstek-gds1000b-control` | 343 | 121 |
| `siglent-sds800xhd-control` | 780 headings | 215 |
| `keithley-2000-control` | 161 in scope | 124 |

Every one of those files said in its header that it did not enumerate the rest of
the manual. The gap was not hidden; it was declared and then read as complete.

## What counts as a form

- The set form and the query form are separate forms; list both when the manual
  documents both.
- Keep every optional bracket level as printed (`[:SENSe[1]]:VOLTage[:DC]`), and
  state which spelling the Skill sends.
- Cover `<n>`, `<x>`, `<m>`, and numeric instance indices. A family that exists
  only under an optional root is a top-level entry, not a variant of its
  sibling.
- A short mnemonic (`STAT`) and its long form (`STATe`) are one command, but a
  row must carry the exact spelling the Skill sends.
- A parent heading that only wraps child commands is not a command. Say so in a
  note rather than adding it as a third form.

## Comparing against the index

There is no shipped comparison script: a matcher tuned to one manual's layout is
wrong for the next, and a number nobody can reproduce is worse than no number.
Compare by hand, with these rules, and keep the working list:

1. Normalize both sides the same way: ignore case, drop a trailing `?`, drop `[`
   and `]`, treat `<n>`/`<x>`/`<m>` and a numeric instance index as the same
   placeholder, and match a short mnemonic to its long form as a prefix.
2. Walk the manual's list in order and mark each entry: covered, or a residual.
3. Triage every residual individually: a renamed placeholder, a short form of a
   listed row, a compound example line, or a wrapping parent heading is not a gap.
   Keep only what the manual documents and the index lacks.
4. Never widen the matching to reduce the residual. Fuzzy matching is not a
   substitute: one audit found 12 distinct commands hidden behind similarly named
   siblings until each was checked by hand.
5. Record the count, the method, the manual revision, and the date in the index
   header, and re-do it when the manual revision changes.

## Status per row, sections apart

Use one status per row:

- `documented`: the manual documents the form; this Skill has not sent it.
- `hardware-verified`: a real reply exists, with model, firmware, interface, and
  date.
- `not implemented`: deliberately not sent; cite the page and the reason.

Keep curated rows and the documented-only appendix in separate sections with
separate headers, so a reader can tell "the manual has it" from "this Skill
exercised it" without reading every row. Counts in the header must match the rows
below it.

Commands that answer on the instrument but appear nowhere in the manual are a
third class: put them in a `measured-only` section, label them `UNVERIFIED`
against the manual, and never call them documented.

## Header contract

- Do not write "complete" unless the normalized comparison was run and is
  recorded with its date.
- A partial index must say what it covers and that any other command has to be
  checked in the manual before use.
- A complete index states the manual form count, the comparison method and date,
  and that `documented` rows are not hardware-verified.
- Cite PDF physical pages and say that is what the numbers are; printed chapter
  labels drift from the file.
- Route readers to the task references first. An index is a fallback for
  cross-checks, not a starting point.

## Record manual defects, do not copy them

- The sendable column carries the correct spelling; a note quotes the printed
  text with its page and the correction.
- Observed in this repository: a page heading printed `:DVD:MODe` while its body
  documented `:DVM:MODe`, and one offset command was printed with a stray space
  inside the path.
- A repair that the manual does not state is an inference. Label it inferred and
  verify it on hardware before the row can become `hardware-verified`.
- Preserve duplicated or mislabelled names as printed and add a note (`12C` vs
  `I2C` is a manual defect, not a second command).
- Do not silently fix a defect in a script only. The record of the defect is part
  of the evidence.

## Checks before publishing an index

1. The form list comes from the manual's own list, contents, or headings, and the
   extraction kept page markers.
2. The normalized comparison was executed; residual is zero or itemized.
3. Every row has a form, a page, and a status.
4. Every `hardware-verified` row cites the instrument record.
5. The header states scope, method, date, and counts.
6. Manual defects have their own list, and every corrected spelling is cited.

Items 1-4 and 6 are machine-checkable only while the extraction file is kept;
without it they need manual confirmation. Item 5 always needs manual
confirmation. If the index cannot answer "which commands does the manual
document, and which of them has this Skill verified?", it is incomplete no matter
how many rows it has.
