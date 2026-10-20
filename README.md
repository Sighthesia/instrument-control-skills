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

### What the authoring conventions cover

Read these before writing a new device Skill; they are normative for the new
Skill's communication and data handling:

| Area | Reference | Rules |
|---|---|---|
| Authoring stages | `authoring-workflow.md` | Instrument boundary, evidence table, the `read_frame → parse_metadata → extract_payload → normalize → validate` split, test-before-hardware, conservative publication |
| Instrument types | `instrument-types-and-examples.md` | Choosing an example by data claim and response format; the five teaching formats and their main checks |
| Response framing | `response-framing.md` | Line-oriented text, CSV, IEEE 488.2 definite-length blocks, length-prefixed binary, segmented/packetized records; failure mapping and allocation limits |
| Metadata and payload | `metadata-payload-validation.md` | Metadata versus payload, applicable length/segment/checksum/axis checks, normalization limited to evidenced semantics |
| Integrity status | `status-and-reports.md` | `COMPLETE`/`INCOMPLETE`/`INVALID`/`UNVERIFIED`/`UNSUPPORTED`; per-check `pass`/`fail`/`not_checked`; report shape and analysis gates |
| Data-specific checks | `waveform-checks.md`, `scalar-checks.md`, `axes-and-sequences.md` | Point/byte counts, segment coverage, axes and units, reading count and instrument status, ordering and duplicate records |
| Evidence and provenance | `evidence-and-provenance.md` | Model, firmware, interface, command, raw response, SHA-256, parser version, manual citation, calibration binding |
| Offline testing | `replay-testing.md` | Valid and negative fixtures, expected results, no sockets or VISA in tests |

### Research and standards basis

The guide is written from published specifications and established open-source
instrument libraries; no implementation code is copied and none of these projects
becomes a runtime dependency.

- **IEEE 488.2** binary block framing (`#<length-of-length><length><payload>`) is
  the reference for oscilloscope waveform transfers and other definite-length
  responses.
- **Vendor programming manuals** (for example SCPI manuals) are the only accepted
  source for command, field, and unit claims; they are cited by revision and page
  and never copied into the repository.
- **PyVISA** ([reading and writing values](https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html))
  documents the decisions a transfer must make explicit: datatype, endianness,
  header, termination, and expected point count.
- **PyVISA-sim** ([simulated instruments](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html))
  informs query/response dialogues, end-of-message rules, and raw-byte replay
  testing.
- **PyMeasure** ([adapters](https://pymeasure.readthedocs.io/en/latest/api/adapters.html),
  [advanced communication](https://pymeasure.readthedocs.io/en/latest/dev/adding_instruments/advanced_communication.html))
  supports keeping transport below instrument semantics and framing/checksums
  above the byte layer.
- **QCoDeS community drivers** ([Qcodes_contrib_drivers](https://github.com/QCoDeS/Qcodes_contrib_drivers))
  model the separation of driver, examples, and tests, with support responsibility
  on the contributor.

Keep `README.md` and `README.zh-CN.md` in sync when submitting.
