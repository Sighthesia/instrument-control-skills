# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Agent Skills for operating instruments and analyzing the data they return:
connecting and configuring instruments, parsing their responses, and
validating data integrity.

## Skills

| Instrument type | Skill | Instrument series | Capabilities | Evidence |
|---|---|---|---|---|
| Oscilloscope | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD series — SDS802X HD, SDS804X HD, SDS812X HD, SDS814X HD, SDS822X HD, SDS824X HD (2 or 4 channels; 70/100/200 MHz; 50 or 100 Mpts) | Discovery and connection, signal measurement, screenshot and waveform capture, protocol decode, anomaly/mask testing, counter/cursor/history reads, local waveform analysis (NumPy); LAN (raw TCP) and USB (USBTMC/VISA) | Hardware-verified on SDS824X HD, firmware `4.8.12.1.1.6.5`; channel-count-, bandwidth-, and memory-depth-dependent behavior must be reconfirmed on the connected model |
| Any instrument (authoring guide) | [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Extensible to any instrument: oscilloscopes, multimeters, power supplies, analyzers, and more | Authoring guide with parser templates and examples for new instrument Skills; does not connect to hardware | Replay-tested with synthetic fixtures |

Install with the skills CLI:

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

To add a Skill for a new instrument, start with
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md),
the authoring guide shipped in this repository. It walks through the authoring
path: define the instrument boundary, collect cited evidence from the
programming manual, classify response formats, and split parsing into stages.

The guide itself does not connect to real hardware; it is replay-tested against
synthetic fixtures. Hardware verification of a new device Skill must be done on
the real instrument separately.

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
