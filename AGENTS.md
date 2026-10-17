# AGENTS.md

Agent Skills repository (no package manager, no build system): markdown Skills plus pure-Python offline parsers/tests. Each Skill's `SKILL.md` is its authoritative contract. See `README.md` (bilingual with `README.zh-CN.md`) for the full contributing guide — this file only lists what is easy to get wrong.

## Repo layout

- `skills/<skill-name>/` — one Skill per directory; directory name must equal the frontmatter `name`.
  - `siglent-sds800xhd-control/` — Siglent SDS800X HD oscilloscope control (hardware-verified on SDS824X HD); `references/` are loaded lazily per goal, do not read them all, and do not paste unrelated commands into the active workflow.
  - `write-new-instrument-control/` — authoring guide + parser templates/examples; use as template source for new Skills.
- `docs/ref/` — vendor manuals (do not commit complete manuals elsewhere).
- `.specs/`, `docs/superpowers/specs/` — design specs.

## Tests (all offline — never touch hardware)

Siglent tests only import with cwd = `scripts/` (bare intra-directory imports):

```bash
cd skills/siglent-sds800xhd-control/scripts && python3 -m unittest discover -s . -p 'test_*.py'
python3 -m unittest discover -s skills/write-new-instrument-control/assets/parser-template/tests -p 'test_*.py'
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
```

## Hardware safety (siglent Skill)

- `capture_scope.py` and `discover_scope.py` connect to real hardware (default `192.168.10.2:5025`). Offline tests must not connect, scan networks, or enumerate VISA resources.
- SCPI TCP port is `5025`; port `5024` is a legacy shell — never query it, and never parse its banner as a query result.
- Never send `ARM` (use `TRMD SINGLE`); never merge a failed/retried read into a "complete" capture; a valid capture needs the observed `Ready -> Stop` transition. Full rules in the Skill.

## Conventions

- New Skills: add the directory under `skills/`, then add it to the table in both READMEs (update both `README.md` and `README.zh-CN.md`).
- Report integrity status `COMPLETE` / `INCOMPLETE` / `INVALID` / `UNVERIFIED` / `UNSUPPORTED`; never silently pad, truncate, interpolate, or guess missing calibration.
- Evidence labels are conservative: `documented` < `replay-tested` < `hardware-verified` = `firmware-scoped`; never claim a model/firmware is verified without a real response.
- `dist/` and `artifacts/` are local-only (git-ignored); packaging is manual:
  `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>`.
- Check CLI discovery after changes: `npx skills@latest add . --list` must list exactly two Skills.
