# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Some agent skills for operating instruments and analyzing the data they return:
connecting and configuring instruments, parsing their responses, and
validating data integrity.

## Skills

| Instrument type | Skill | Instrument series | Capabilities | Evidence |
|---|---|---|---|---|
| Oscilloscope | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD series — SDS802X HD, SDS804X HD, SDS812X HD, SDS814X HD, SDS822X HD, SDS824X HD (2 or 4 channels; 70/100/200 MHz; 50 or 100 Mpts) | Discovery and connection, signal measurement, screenshot and waveform capture, protocol decode, anomaly/mask testing, counter/cursor/history reads, local waveform analysis (NumPy); LAN (raw TCP) and USB (USBTMC/VISA) | ✅Verified (SDS824X HD, firmware `4.8.12.1.1.6.5`; channel-count-, bandwidth-, and memory-depth-dependent behavior must be reconfirmed on the connected model) |
| Bench multimeter | [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Keithley Model 2000 (6½-digit multimeter) | Documented SCPI workflows for DC/AC voltage and current, 2-/4-wire resistance, frequency/period, thermocouple temperature, diode and continuity; readout selection, response validation, and conditional trigger/buffer/limit/scanner reference | `documented` from manual 2000-900-01 Rev. J / August 2010; no hardware verification claimed |
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

### Reference basis

New device Skills follow the authoring guide's references on response framing
(line text, CSV, IEEE 488.2 blocks, length-prefixed and segmented binary),
metadata/payload separation, integrity statuses and report shape, scalar,
waveform and axis checks, provenance, and offline replay testing.

The guide and the waveform analyzer also draw on published standards and
established open-source instrument projects; none is a runtime dependency:

- **IEEE 488.2** block framing for definite-length waveform transfers.
- **IEEE Std 181 / IEC 60469** for transition, pulse, and aberration terms such as
  rise time, pulse width, overshoot, and ringing.
- **PyVISA, PyVISA-sim, PyMeasure, QCoDeS** for transfer options, replay testing,
  and transport/semantic separation.
- **M4** (VLDB 2014) for the lossy preview, **NumPy `memmap`** for chunked reads,
  **SciPy `find_peaks`/`welch`** as future detector references.
- **Vendor programming manuals** for every command, field, and unit claim.

Threshold crossings, pulse and runt widths, and ringing screening are heuristics
and are not claimed to comply with any standard. Full index, links, and caveats:
[`docs/references.md`](docs/references.md).

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
