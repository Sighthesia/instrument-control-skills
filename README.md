# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Some agent skills for operating instruments and analyzing the data they return:
connecting and configuring instruments, parsing their responses, and
validating data integrity.

## Skills

| Instrument type | Skill | Instrument series | Capabilities | Evidence |
|---|---|---|---|---|
| Oscilloscope | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD series — SDS802X HD, SDS804X HD, SDS812X HD, SDS814X HD, SDS822X HD, SDS824X HD (2 or 4 channels; 70/100/200 MHz; 50 or 100 Mpts) | Discovery and connection, signal measurement, screenshot and waveform capture, protocol decode, anomaly/mask testing, counter/cursor/history reads, local waveform analysis (NumPy); LAN (raw TCP) and USB (USBTMC/VISA) | ✅Verified (SDS824X HD, firmware `4.8.12.1.1.6.5`; channel-count-, bandwidth-, and memory-depth-dependent behavior must be reconfirmed on the connected model) |
| Any instrument (authoring guide) | [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Extensible to any instrument: oscilloscopes, multimeters, power supplies, analyzers, and more | Authoring guide with parser templates and examples for new instrument Skills; does not connect to hardware | Authoring guide; no device commands to verify |

Install with the skills CLI:

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

If you have an instrument communication method you'd like to add, you're
welcome to include it here. To add a Skill for a new instrument, start with
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md),
the authoring guide shipped in this repository. It walks through the authoring
path: define the instrument boundary, collect cited evidence from the
programming manual, classify response formats, and split parsing into stages.

The guide itself does not connect to real hardware. A device Skill counts as
verified only when exercised on a real instrument; supporting evidence such as
screenshots and the firmware version may be recorded in the Skill or README
table, but is not mandatory.

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
