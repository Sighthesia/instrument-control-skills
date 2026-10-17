# AGENTS.md

Maintenance-focused guidance for this repository: a collection of Agent Skills
(one `skills/<skill-name>/` directory each) for instrument control and offline
data analysis. No build system, no package manager; tests are plain `unittest`.
Each Skill's `SKILL.md` is its authoritative contract. Prefer word-for-word
reuses of this guidance over rephrasing — the phrasing is part of the contract.

## Skill anatomy

```
skills/<skill-name>/
├── SKILL.md        # frontmatter `name` must equal the directory name; the contract
├── references/     # load lazily per goal, never read all up front
├── scripts/        # pure Python; bare intra-directory imports
└── assets/         # templates, fixtures, expected results, and their tests
```

## Writing a new Skill

1. Model the directory on the parser templates, authoring references, and
   examples already shipped in this repository; do not invent a new layout.
2. Set the frontmatter `name` equal to the directory name; register the Skill in
   both `README.md` and `README.zh-CN.md` and keep the two in sync.
3. Keep instrument commands and state rules inside the Skill; preserve raw
   responses verbatim; never claim `hardware-verified` without a real response.
4. Separate framing, metadata, payload extraction, normalization, and validation;
   report `COMPLETE` / `INCOMPLETE` / `INVALID` / `UNVERIFIED` / `UNSUPPORTED`
   and never silently pad, truncate, interpolate, or guess missing calibration.
5. Label evidence conservatively: `documented` < `replay-tested` <
   `hardware-verified` = `firmware-scoped`. Labels describe evidence, not
   feature count.
6. Offline tests must not connect to hardware, scan a network, or enumerate VISA
   resources; include binary-safe fixtures, expected results, and negative cases.

## Consistency checks (after every change)

Run all of the following before committing; the last two catch drift that
inspection alone misses:

```bash
# 1. Validate every changed Skill (schema, frontmatter, layout)
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>

# 2. Run each Skill's offline tests; cwd matters because of bare imports
cd skills/<skill-name>/scripts && python3 -m unittest discover -s . -p 'test_*.py'
python3 -m unittest discover -s skills/<skill-name>/assets/<component>/tests -p 'test_*.py'

# 3. CLI discovery must list exactly the directories under skills/
npx skills@latest add . --list
```

- `README.md` and `README.zh-CN.md` must describe the same Skill set and rules
  in the same order; treat any divergence as a bug.
- Evidence labels, integrity statuses, and safety rules must be worded the same
  way across Skills; copy phrasing from an existing Skill rather than rewriting.
- Never commit complete vendor manuals; keep them only in `docs/ref/`,
  which documents — do not copy — their contents into Skill references.
- `dist/`, `artifacts/`, and `__pycache__/` are local-only (git-ignored);
  packaging is manual via `package_skill.py` (it validates first and excludes
  `__pycache__/`).

## Gotchas

- Scripts that talk to real hardware do so only when run directly; never import
  or invoke them from tests, and never merge a failed or retried read into a
  "complete" file.
- Design specs live in `.specs/` and `docs/superpowers/specs/` (date-prefixed
  markdown); check them before changing behavior that looks arbitrary.
