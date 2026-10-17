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

Offline / manual: the committed archives `dist/siglent-sds800xhd-control.skill` and
`dist/write-new-instrument-control.skill` are zips of their Skill folders. Unzip the
needed archive into an agent's skills directory (for OpenCode, e.g.
`~/.config/opencode/skills/`).

## Supported instruments

| Skill | Instruments | Transports | Evidence |
|---|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD series — SDS802X HD, SDS804X HD, SDS812X HD, SDS814X HD, SDS822X HD, SDS824X HD (2 or 4 channels; 70/100/200 MHz; 50 or 100 Mpts) | LAN (raw TCP), USB (USBTMC/VISA) | Hardware-verified on SDS824X HD, firmware `4.8.12.1.1.6.5` |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Any instrument being added by a new Skill; does not connect to hardware itself | — | Replay-tested with synthetic fixtures |

The Siglent Skill covers discovery and connection, signal measurement, screenshot
and waveform capture, protocol decode, anomaly/mask testing, counter/cursor/history
reads, and local read-only waveform analysis (NumPy). Channel-count-, bandwidth-,
and memory-depth-dependent behavior must be confirmed on the connected model before
being reported as verified.

`registry.yaml` is the machine-readable catalog of Skills, capabilities, and
evidence levels; each Skill's `SKILL.md` is its authoritative contract.

## Contributing

Add a Skill as one directory under `skills/<skill-name>/` containing `SKILL.md` and,
when needed, `references/`, `scripts/`, and `assets/`. The directory name must match
the `name` in the frontmatter, and the Skill must be registered in `registry.yaml`.

- Keep instrument commands and state rules inside the device Skill, preserve raw
  responses, and never claim a model or firmware is verified without a real response.
- Separate framing, metadata, payload extraction, normalization, and validation.
  Report `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, or `UNSUPPORTED`; never
  silently pad, truncate, interpolate, or guess missing calibration.
- Offline tests must not connect to hardware, scan a network, or enumerate VISA
  resources. Include binary-safe fixtures, expected results, and negative cases.
- Label evidence conservatively: `documented`, `replay-tested`, `hardware-verified`,
  `firmware-scoped`. Labels describe evidence, not feature count.
- Do not commit complete vendor manuals, `artifacts/`, or `__pycache__/`; before
  submitting, update `registry.yaml`, both READMEs, and the affected `.skill` archive.

### Commands

The Siglent control tests are fully offline and only import correctly with the
working directory set to `scripts/`, because the modules use bare intra-directory
imports:

```bash
cd skills/siglent-sds800xhd-control/scripts && python3 -m unittest discover -s . -p 'test_*.py'
```

Parser template tests and the five parser examples with the offline safety guard:

```bash
python3 -m unittest discover -s skills/write-new-instrument-control/assets/parser-template/tests -p 'test_*.py'
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
```

Validate a Skill, rebuild its archive (packaging validates first and excludes
`__pycache__/`), then confirm CLI discovery and archive integrity:

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py skills/<skill-name> dist
npx skills@latest add . --list   # must list exactly two Skills
unzip -t dist/<skill-name>.skill
```

`capture_scope.py` and `discover_scope.py` talk to real hardware (default
`192.168.10.2:5025`; port `5024` is a legacy shell, never query it). Never send `ARM`,
and never merge a failed or retried read into a "complete" file.
