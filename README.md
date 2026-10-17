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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the Skill layout, control/parser rules,
evidence levels, manual and copyright policy, offline test requirements, and the
pre-submit verification checklist.
