# AGENTS.md

Maintenance-focused guidance for this repository: a collection of Agent Skills
(one `skills/<skill-name>/` directory each) for instrument control and data
analysis. No build system, no package manager. Each Skill's `SKILL.md` is its
authoritative contract. Prefer word-for-word reuses of this guidance over
rephrasing — the phrasing is part of the contract.

## Skill anatomy

```
skills/<skill-name>/
├── SKILL.md        # frontmatter `name` must equal the directory name; the contract
├── references/     # load lazily per goal, never read all up front
├── scripts/        # pure Python; bare intra-directory imports
└── assets/         # templates, fixtures, and expected results
```

## Writing a new Skill

Before authoring, read `skills/write-new-instrument-control/SKILL.md` and load
only the `references/` documents matching each stage. It is the normative source
for communication framing, data-integrity, and provenance conventions; do not
re-derive those rules from memory.

1. Model the directory on the parser templates, authoring references, and
   examples already shipped in this repository; do not invent a new layout.
2. Set the frontmatter `name` equal to the directory name; register the Skill in
   both `README.md` and `README.zh-CN.md` and keep the two in sync.
3. Keep instrument commands and state rules inside the Skill; preserve raw
   responses verbatim; never claim `hardware-verified` without a real response.
4. Separate framing, metadata, payload extraction, normalization, and validation;
   report `COMPLETE` / `INCOMPLETE` / `INVALID` / `UNVERIFIED` / `UNSUPPORTED`
   and never silently pad, truncate, interpolate, or guess missing calibration.
5. Label evidence conservatively: `documented` < `hardware-verified` =
   `firmware-scoped`. Labels describe evidence, not feature count.
6. Verification is performed on the real instrument and cites the model,
   firmware, and interface exercised. Supporting evidence such as screenshots
   may be recorded in the Skill, but is not mandatory.

## Command index completeness

- The authority for a command index is the manual's own command list or body
  headings, never a `grep` of syntax lines: forms that start with `[`
  (`[:SOURce[<n>]]`) and every `<n>`/`<X>` placeholder spelling are commands and
  must be listed.
- An index of only the commands a Skill sends is not an index: list every form
  the manual documents and say in the header which manual list the file covers.
- State coverage as a fraction of the manual's command forms; the denominator is
  the manual's form count, not the implemented subset. Report row count and form
  count separately so the two are not conflated.
- A row is `hardware-verified` only when a captured reply is cited; every other
  row is `documented`. A subsystem the Skill never sends is marked
  `not implemented` as a section, and manual-derived appendices stay separate
  from the curated tables so `documented` is never read as `hardware-verified`.
- Record manual defects instead of copying them: a wrong mnemonic in a heading
  or a space spliced into a keyword is noted against the corrected form, not
  reproduced as a command.
- Keep the working list used for the count under `artifacts/` (it is git-ignored)
  and commit only the index, never extracted or copied manual text. Re-do the
  count when the manual revision changes.

## Consistency checks (after every change)

```bash
# 1. Always: validate every changed Skill (schema, frontmatter, layout)
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>

# 2. Always: CLI discovery must list exactly the directories under skills/
npx skills@latest add . --list

# 3. Only when that Skill's scripts/ changed: run its offline unit tests
#    (they never open a socket; a documentation-only edit cannot break a parser)
python3 -m unittest discover -s skills/<skill-name>/scripts -p 'test_*.py'
```

- Documentation edits (references, SKILL.md, README, an index row) are checked by
  validation and discovery, not by the unit suite. Do not run 1000+ parser tests
  to publish a corrected page number; do run them the moment a line under
  `scripts/` moves.
- Device Skills carry `scripts/test_*.py`; the authoring guide has no `scripts/`,
  so run its bundled examples:
  `python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'`.
- The suite protects parsing, not prose. By construction it can catch a sentinel
  read as a number, a block truncated at an idle gap, a voltage formula that drops
  a term, and a retry that hides a desynchronised reply; it cannot catch a wrong
  page number, a mis-copied range, or a stale README figure. Those are review
  work, and injecting a mutation is the way to confirm which side of the line a
  given test sits on.
- A command count is a manual reading, not a script output: no extraction tool is
  shipped, because one heuristic cannot be right for a heading-per-command manual
  and a command-table manual. Count against the manual's own list, triage every
  residual by hand, and record the method and date with the number.
- A passing offline test run is not hardware evidence and must not upgrade an
  evidence label.- `README.md` and `README.zh-CN.md` must describe the same Skill set and rules
  in the same order; treat any divergence as a bug.
- Capability-table numbers (index rows, command forms) are audit results: when an
  audit changes them, update both READMEs in the same change and derive the
  numbers from the committed index rather than from memory.
- Evidence labels, integrity statuses, and safety rules must be worded the same
  way across Skills; copy phrasing from an existing Skill rather than rewriting.
- Never commit complete vendor manuals; keep them only in `ref/` (git-ignored),
  which documents — do not copy — their contents into Skill references.
- `ref/`, `dist/`, `artifacts/`, and `__pycache__/` are local-only (git-ignored);
  packaging is manual via `package_skill.py` (it validates first and excludes
  `__pycache__/`).

## Gotchas

- Scripts that talk to real hardware do so only when run directly; never run
  them from validation or packaging steps, and never merge a failed or retried
  read into a "complete" file.
- Design specs live in `.specs/` and `docs/superpowers/specs/` (date-prefixed
  markdown); check them before changing behavior that looks arbitrary.
