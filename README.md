# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Agent Skills for SCPI instrument control, byte-preserving parsing, and honest
evidence labels.

## Skills

| Skill | Instrument type | Verified on hardware |
|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Oscilloscope | ✅ SDS824X HD, date not recorded |
| [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Bench DMM | ✅ Model 2000, 2026-10-20 |
| [`gwinstek-gdm8352-control`](skills/gwinstek-gdm8352-control/SKILL.md) | Bench DMM | ✅ GDM-8352, 2026-11-19 |
| [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | Function generator | — |
| [`gwinstek-gpd4303s-control`](skills/gwinstek-gpd4303s-control/SKILL.md) | DC power supply | ✅ GPD-4303S, 2026-11-19 |
| [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | Oscilloscope | — |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Authoring guide | — |

## Capabilities

| Skill | Manual coverage | Auxiliary tooling |
|---|---|---|
| `siglent-sds800xhd-control` | Partial: 7 task areas; fallback index only | 11 scripts: `waveform_analysis`, `waveform_scan`, `capture_scope` … |
| `keithley-2000-control` | Partial: 11/11 panel functions; no block/buffer parsing | `keithley2000_session`: dry run, raw capture, lock |
| `gwinstek-gdm8352-control` | Read-only subset: 22 of 122 indexed queries; writes refused | `gdm8352_session`: dry run, whitelist, sha256 fixtures |
| `gwinstek-afg2225-control` | Partial: 9 builder/parser functions; 13 unit tables | `afg2225_protocol`: ARB/IEEE block codec, error queue |
| `gwinstek-gpd4303s-control` | Read-only subset: 8 of 18 command forms; writes refused | `gpd4303s_protocol`/`_session`: `STATUS?` decode, dry run |
| `gwinstek-gds1000b-control` | Partial: 41 measurement commands; waveform download | `gds1000b_protocol`: IEEE block, offline waveform check |
| `write-new-instrument-control` | n/a: no device commands | parser templates, framing examples, integrity statuses |

## Bench notes

- GPD-4303S: the verified bench was in series tracking (`SER/INDEP` LED on,
  matching the `STATUS?` decode), so CH1/CH2 formed one 0-60 V supply, not two
  independent channels.
- SDS824X HD: channel-count-, bandwidth-, and memory-depth-dependent behavior
  must be reconfirmed on the connected model.
- Keithley Model 2000: only DC voltage and DC current were exercised, over
  RS-232; every other function remains `documented`.
- GDM-8352 and GPD-4303S: `hardware-verified` covers read-only queries, plus one
  silent GDM-8352 `SYST:BEEP:STAT 0` confirmed by the follow-up query (the Skill
  still refuses the setter); all other writes, function/range switching,
  tracking, and memory commands remain `documented`.
- AFG-2225 and GDS-1000B: `documented` only, never exercised on hardware.
- Do not extend `hardware-verified` beyond the recorded model, firmware,
  interface, and functions.

## Evidence labels

`documented` < `hardware-verified` = `firmware-scoped`: labels describe evidence,
not feature count.

**A device Skill counts as verified only when exercised on a real instrument.**

Each Skill's `SKILL.md` / `SUPPORT.md` is the authoritative record.

## Install

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

Offline / manual: copy or symlink any Skill directory under `skills/` into an
agent's skills directory (for OpenCode, e.g. `~/.config/opencode/skills/`).

## Contributing

To add a Skill for a new instrument, start with the
[authoring guide][authoring-guide]. The guide itself does not connect to real
hardware; its basis is [`docs/references.md`](docs/references.md).

Keep `README.md` and `README.zh-CN.md` in sync when submitting.

[authoring-guide]: skills/write-new-instrument-control/SKILL.md
