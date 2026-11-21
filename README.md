# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

Agent Skills for SCPI instrument control, byte-preserving parsing, and honest
evidence labels.

## Skills

| Skill | Instrument type | Verified on hardware |
|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Oscilloscope | ✅ SDS824X HD |
| [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Bench DMM | ✅ Model 2000 |
| [`gwinstek-gdm8352-control`](skills/gwinstek-gdm8352-control/SKILL.md) | Bench DMM | ✅ GDM-8352 |
| [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | Function generator | — |
| [`gwinstek-gpd4303s-control`](skills/gwinstek-gpd4303s-control/SKILL.md) | DC power supply | ✅ GPD-4303S |
| [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | Oscilloscope | — |
| [`rigol-ds1000z-control`](skills/rigol-ds1000z-control/SKILL.md) | Oscilloscope | ✅ DS1074Z |
| [`oscilloscope-waveform-analysis`](skills/oscilloscope-waveform-analysis/SKILL.md) | Offline waveform analysis | — (offline; tested with DS1074Z / SDS824X HD fixtures) |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | Authoring guide | — |

## Capabilities

| Skill | Manual coverage | Auxiliary tooling |
|---|---|---|
| `siglent-sds800xhd-control` | Manual index: 873 rows, parameters transcribed | 7 scripts: `capture_scope` (`waveform-bundle/v1`), `scope_protocol`, `configure_scope`, `screenshot_capture`, `read_decode_list` … |
| `keithley-2000-control` | 11/11 panel functions; 287 index rows, parameters transcribed | `keithley2000_session`: dry run, raw capture, lock |
| `gwinstek-gdm8352-control` | Read-only subset; writes refused; 173 index rows | `gdm8352_session`: dry run, whitelist, sha256 fixtures |
| `gwinstek-afg2225-control` | Partial: ARB/IEEE block builders and parsers; 13 unit tables | `afg2225_protocol`: ARB/IEEE block codec, error queue |
| `gwinstek-gpd4303s-control` | Read-only subset; writes refused; 48 index rows | `gpd4303s_protocol`/`_session`: `STATUS?` decode, dry run |
| `gwinstek-gds1000b-control` | Partial: measurements and waveform download; 450 index rows | `gds1000b_protocol`/`_session`: IEEE block, `waveform-bundle/v1` export, offline check |
| `rigol-ds1000z-control` | Manual index: 500 rows, parameters transcribed | `ds1000z_protocol`/`_session`: IEEE block, `waveform-bundle/v1` export, BMP trim, cursor readout, lockstep TCP |
| `oscilloscope-waveform-analysis` | n/a: vendor-neutral offline analyzer (`numpy`) | `analyze_waveform`, `waveform_bundle`, `waveform_analysis`, `waveform_scan`, `waveform_evidence`: `waveform-bundle/v1` / CSV / NPZ, pulse structure, regimes, ringing, verdict gate, SVG |
| `write-new-instrument-control` | n/a: no device commands | parser templates, framing examples, integrity statuses |

Index row counts are `grep -c '^|'` over each Skill's committed
`references/command-reference.md`; re-derive them rather than trusting this table.

## Hints and known issues

- GPD-4303S: when in series tracking, CH1/CH2 may be wired as one supply
  instead of two independent channels.
- Oscilloscopes: behavior that depends on channel count, bandwidth, or memory
  depth must be reconfirmed on the connected model.
- Some Skills are `documented` only and have never been exercised on hardware.

## Verification

**Evidence belongs to a claim, not to a Skill.** ✅ in the table above means the
Skill holds a capture from that instrument — not that every command, parser and
unit in it was exercised there. Read the per-claim table in that Skill's
`SUPPORT.md` (where present) or `SKILL.md`; a claim is `hardware-verified` only
where the raw reply is cited. Skills without a `SUPPORT.md` say so in their
`SKILL.md`.

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
