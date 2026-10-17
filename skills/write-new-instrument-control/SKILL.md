---
name: write-new-instrument-control
description: Guide the creation of a new instrument-control Skill from programming manuals, raw ASCII or binary responses, metadata, and replay fixtures. Use when adding support for a new oscilloscope, multimeter, power supply, analyzer, or other instrument, especially when hardware is unavailable and communication, parsing, data integrity, provenance, and offline tests must be explicit.
---

# Write New Instrument Control

## Purpose

Use this Skill when creating a new, self-contained instrument-control Skill. It
guides the complete authoring path:

```text
programming manual and evidence
  -> control workflow and raw response capture
  -> device-specific framing and parser
  -> normalized artifact and integrity report
  -> replay tests and support-level declaration
```

This Skill guides the authoring of device Skills; it does not connect to real
instruments, configure hardware, or impose a shared adapter inheritance framework.
Keep commands and state rules inside the new device Skill.

## Authoring Workflow

1. **Define the instrument boundary**: record vendor, model family, interfaces,
   firmware assumptions, data kinds, supported operations, and safety-sensitive
   state changes. Keep the control workflow explicit and device-specific.
2. **Collect evidence**: obtain the official programming manual and cite its URL,
   revision, page or section. Preserve raw responses as bytes. Keep inferred fields
   separate from manual-documented fields and hardware observations.
3. **Classify response formats**: identify line-oriented text, CSV, IEEE 488.2
   binary, length-prefixed binary, packetized data, segmented records, or a custom
   format. Record the command or acquisition operation that produced each fixture.
4. **Separate parser stages**: implement framing, metadata parsing, payload
   extraction, normalization, and validation as distinct functions. Do not let a
   convenient text conversion hide binary boundaries or invalid bytes.
5. **Define the artifact**: choose a data kind such as `waveform`,
   `scalar-measurement`, `spectrum`, or `status-record`. Record identity, source,
   raw artifact path, hashes, units, encoding, calibration status, and support level.
6. **Validate evidence**: compare declared and observed lengths, element widths,
   segment ranges, checksums, timestamps, units, configuration, and source status
   where available. Return `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, or
   `UNSUPPORTED`; never silently pad, truncate, interpolate, or infer.
7. **Add replay tests**: test valid, truncated, malformed, length-mismatch,
   unsupported, missing-unit, and missing-calibration cases offline. Assert both
   parsed values and integrity status. Use binary fixtures for binary protocols.
8. **Declare support**: label manual-only, replay-tested, hardware-verified, and
   firmware/interface-scoped claims separately. Include known limitations and the
   exact evidence used.

Read the matching reference before implementing a stage:

| Task | Reference |
|---|---|
| Choose Skill stages and deliverables | [Authoring workflow](references/authoring-workflow.md) |
| Handle response boundaries and binary framing | [Response framing](references/response-framing.md) |
| Separate metadata, payload, normalization, and validation | [Metadata and validation](references/metadata-payload-validation.md) |
| Decide integrity status and report failures | [Status and reports](references/status-and-reports.md) |
| Check waveforms and segmented samples | [Waveform checks](references/waveform-checks.md) |
| Check scalar readings and measurement context | [Scalar checks](references/scalar-checks.md) |
| Check spectra, axes, event logs, and sequences | [Axes and sequence checks](references/axes-and-sequences.md) |
| Record evidence, provenance, and calibration | [Evidence and provenance](references/evidence-and-provenance.md) |
| Build offline fixtures and replay tests | [Replay testing](references/replay-testing.md) |

## Required Skill Shape

Start from `assets/parser-template/` and adapt only protocol-specific parts:

```text
<vendor>-<model>-control/
|-- SKILL.md
|-- scripts/
|   |-- control and parser helpers
|   `-- offline tests
|-- references/
|   `-- programming manual notes
|-- assets/
|   |-- replay fixtures
|   `-- integrity-report.json
|-- manifest.json
`-- SUPPORT.md
```

The parser template is intentionally a small example protocol. Replace its
framing and field names; do not claim that the example wire format is a vendor
standard.

## Integrity Method

Treat data integrity as a set of claims, not one boolean:

```text
structure: COMPLETE
calibration: UNVERIFIED
analysis_allowed: code-domain-only
```

Use these primary statuses:

- `COMPLETE`: all applicable structural checks pass and required evidence exists
  for the stated claim.
- `INCOMPLETE`: required bytes, samples, segments, records, or end markers are
  missing.
- `INVALID`: framing, metadata, checksum, ordering, or type constraints contradict
  the observed artifact.
- `UNVERIFIED`: parsing succeeded, but evidence cannot prove completeness, units,
  calibration, or acquisition state.
- `UNSUPPORTED`: the new Skill deliberately does not implement the format or claim.

Individual checks use `pass`, `fail`, or `not_checked`. Compare declared and
observed lengths, multiply element count by bytes per element, verify segment
continuity, check hashes/checksums, validate axes and status flags, and preserve
extra trailing bytes. Do not infer missing samples, timestamps, units, or
calibration. Bind external calibration to the exact raw or merged artifact hash.

Use `assets/integrity-report.json` as a starting point. Keep raw bytes, request,
identity, interface, timestamp, parser version, manual citation, hashes, and known
limitations beside the normalized artifact.

## Non-negotiable Rules

- Preserve raw bytes before decoding.
- Do not call a result complete because a parser returned a number.
- Keep framing errors distinct from semantic or calibration uncertainty.
- Keep device-specific commands and field offsets out of reusable analysis code.
- Do not include copyrighted vendor manuals; cite the official source and page or
  section instead.
- Do not connect to real hardware from offline parser tests.
- Distinguish “no anomaly found” from “analysis could not be trusted because the
  input was incomplete or unverified.”

## Support Levels

Use the most conservative applicable label:

| Level | Meaning |
|---|---|
| `documented` | Implementation follows a cited official manual; no replay or hardware evidence is claimed. |
| `replay-tested` | Preserved responses, expected results, and negative cases pass offline. |
| `hardware-verified` | The parser or control workflow was exercised against a real instrument response. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and test date. |

These labels describe evidence, not feature breadth. A broad implementation can
remain `documented` or `replay-tested`.
