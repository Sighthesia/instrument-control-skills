# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Agent Skills for operating instruments and analyzing the data they return:
connecting and configuring instruments, parsing their responses, and
validating data integrity.

## Install

With the skills CLI (recommended):

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

To add a Skill for a new instrument, start with
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md),
the authoring guide shipped in this repository. It walks through the whole
authoring path: define the instrument boundary, collect cited evidence from the
programming manual, classify response formats, split parsing into stages,
produce data artifacts with integrity reports, and write offline replay tests.

The guide itself does not connect to real hardware; it is replay-tested against
synthetic fixtures. Hardware verification of a new device Skill must be done on
the real instrument separately.

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
