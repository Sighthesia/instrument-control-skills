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

Each Skill is one directory under `skills/<skill-name>/`. The directory name
must match the `name` in the frontmatter. Each Skill's `SKILL.md` is the
authoritative contract for that Skill.

- Offline tests must not connect to hardware, scan a network, or enumerate VISA
  resources.
- Scripts that talk to real hardware connect only when run directly; do not
  import or invoke them from tests.
- Do not commit complete vendor manuals.

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
