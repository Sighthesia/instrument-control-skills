# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Some agent skills for operating instruments and analyzing the data they return:
connecting and configuring instruments, parsing their responses, and
validating data integrity.

## Skills

| Skill | Instrument | Interface |
|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD series | `LAN (TCP 5025)`, `USB-TMC` |
| [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Keithley Model 2000 | `RS-232` |
| [`gwinstek-gdm8352-control`](skills/gwinstek-gdm8352-control/SKILL.md) | GW Instek GDM-8352 | `USB CDC-ACM` |
| [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | GW Instek AFG-2225 | `USB CDC` |
| [`gwinstek-gpd4303s-control`](skills/gwinstek-gpd4303s-control/SKILL.md) | GW Instek GPD-4303S | `FTDI serial` |
| [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | GW Instek GDS-1000B series | `USB CDC`, `LAN` (4-channel models) |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Any instrument (authoring guide) | — |

## Coverage

- **`siglent-sds800xhd-control`** — measurement, screenshot, waveform capture,
  protocol decode, mask testing, offline analysis.
- **`keithley-2000-control`** — DC/AC voltage and current, resistance, frequency,
  temperature, diode and continuity measurements with response validation.
- **`gwinstek-gdm8352-control`** — read-only identity and DC/AC measurement
  queries with two-display framing and a query-only whitelist.
- **`gwinstek-afg2225-control`** — standard and arbitrary waveform generation,
  modulation, sweep, burst, counter, and validated ARB upload.
- **`gwinstek-gpd4303s-control`** — read-only supply monitoring: identity,
  `STATUS?` decode, set-point and output readback, no command that energises a
  load.
- **`gwinstek-gds1000b-control`** — acquisition, trigger, waveform download and
  validation, measurements, save and screenshot.
- **`write-new-instrument-control`** — authoring guide with parser templates and
  examples for new instrument Skills; it does not connect to hardware.

## Verified on hardware

| Skill | Model | Firmware | Interface | Bench date |
|---|---|---|---|---|
| `siglent-sds800xhd-control` | SDS824X HD | `4.8.12.1.1.6.5` | LAN TCP 5025 | not recorded |
| `keithley-2000-control` | Model 2000 | `A17` / `A02` | RS-232 9600 8N1 | 2026-10-20 |
| `gwinstek-gdm8352-control` | GDM-8352 | `1.00` | USB CDC-ACM `2184:003b` | 2026-11-19 |
| `gwinstek-gpd4303s-control` | GPD-4303S | `V2.08` | FTDI serial 9600 8N1 | 2026-11-19 |

## Bench notes

- SDS824X HD: channel-count-, bandwidth-, and memory-depth-dependent behavior
  must be reconfirmed on the connected model.
- Keithley Model 2000: verified only for DC voltage and DC current over
  RS-232, unit `0944865`; every other function remains `documented`.
- GDM-8352: seven read-only queries verified on unit `GEP848232`, re-tested the
  same day; every setter and all other measurement functions remain
  `documented`.
- GPD-4303S: CH1-CH4 read-only queries verified on unit `EP924162`, re-tested
  the same day; every output, set-point, tracking, and memory command remains
  `documented`. The unit was in series tracking (`SER/INDEP` LED on, matching
  the `STATUS?` decode), so CH1/CH2 formed one 0-60 V supply, not two
  independent channels.
- AFG-2225 and GDS-1000B are `documented` only; neither has been verified on
  hardware.
- Do not extend `hardware-verified` beyond the recorded model, firmware,
  interface, and functions.

## Evidence labels

`documented` < `hardware-verified` = `firmware-scoped`: a label describes
evidence for a named model, firmware, and interface, never feature count.

**A device Skill counts as verified only when exercised on a real instrument.**
Each Skill's `SKILL.md` / `SUPPORT.md` is the authoritative record.

## Install

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

If you have an instrument communication method you'd like to add, you're
welcome to include it here. To add a Skill for a new instrument, start with
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md),
the authoring guide shipped in this repository: define the instrument boundary,
collect cited evidence from the programming manual, classify response formats,
and split parsing into stages.

The guide itself does not connect to real hardware. Reference basis for the
authoring rules and analysis routines: [`docs/references.md`](docs/references.md).

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
