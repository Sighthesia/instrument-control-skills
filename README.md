# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Agent Skills that guide an AI agent to operate instruments and analyze the data
they return: connection and configuration, response framing and parsing, integrity
validation, provenance, and offline replay tests.

## Install

With the skills CLI (recommended):

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

Add a Skill as one directory under `skills/<skill-name>/` containing `SKILL.md`
and, when needed, `references/`, `scripts/`, and `assets/`. The directory name
must match the `name` in the frontmatter. Each Skill's `SKILL.md` is its
authoritative contract.

- Keep instrument commands and state rules inside the device Skill, preserve raw
  responses, and never claim a model or firmware is verified without a real response.
- Separate framing, metadata, payload extraction, normalization, and validation.
  Report `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, or `UNSUPPORTED`; never
  silently pad, truncate, interpolate, or guess missing calibration. Reuse the
  parser templates and authoring guide shipped in this repository.
- Offline tests must not connect to hardware, scan a network, or enumerate VISA
  resources. Include binary-safe fixtures, expected results, and negative cases.
- Label evidence conservatively: `documented`, `replay-tested`, `hardware-verified`,
  `firmware-scoped`. Labels describe evidence, not feature count.
- Do not commit complete vendor manuals. `dist/`, `artifacts/`, and `__pycache__/`
  are local and git-ignored: build packages by hand when needed, and keep both
  READMEs in sync before submitting.

### Commands

Tests are fully offline. Modules use bare intra-directory imports, so run them
with the working directory set to the directory containing the test modules:

```bash
cd skills/<skill-name>/scripts && python3 -m unittest discover -s . -p 'test_*.py'
python3 -m unittest discover -s skills/<skill-name>/assets/<component>/tests -p 'test_*.py'
```

Validate a Skill, then optionally build a local package (packaging validates
first and excludes `__pycache__/`), and confirm CLI discovery:

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py skills/<skill-name> dist   # dist/ is local only
npx skills@latest add . --list   # must list exactly the Skills under skills/
```

Scripts that talk to real hardware do so only when run directly; never wire them
into tests, and never merge a failed or retried read into a "complete" file.
