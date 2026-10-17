---
name: measurement-data-integrity
description: Evaluate whether data obtained from scientific instruments is complete, structurally valid, semantically trustworthy, or unverified. Use when reviewing waveform, scalar measurement, spectrum, CSV, binary, segmented, timestamped, or event data; designing artifact checks; writing integrity reports; or deciding whether an analysis result is supported by the available evidence.
---

# Measurement Data Integrity

## Purpose

Apply an evidence-first method to instrument-derived data before analysis or
reporting. This Skill is vendor-neutral and data-type oriented. It does not
connect to instruments, issue commands, parse a vendor command tree, or replace a
device-specific decoder.

Treat the pipeline as:

```text
raw response -> device-specific framing/decoder -> normalized artifact
             -> integrity report -> domain analysis
```

Do not allow a successful parser call or a plausible numeric value to stand in for
proof that the artifact is complete or calibrated.

## Integrity Workflow

1. **Identify the claim**: decide whether the claim concerns byte completeness,
   sample completeness, record sequence, units, calibration, timestamps, or domain
   semantics. Do not use one boolean for all claims.
2. **Collect evidence**: preserve the raw artifact and record declared sizes,
   observed sizes, element widths, segment ranges, checksums, sequence numbers,
   status flags, units, calibration sources, and acquisition metadata where present.
3. **Select applicable checks**: use the matching reference for waveform, scalar,
   spectrum, or event data. Mark checks as `pass`, `fail`, or `not_checked`; do not
   mark unavailable evidence as passing.
4. **Classify conservatively**: return `COMPLETE`, `INCOMPLETE`, `INVALID`,
   `UNVERIFIED`, or `UNSUPPORTED`, with reasons and evidence. A complete payload
   can still have `UNVERIFIED` units or calibration.
5. **Preserve limitations**: keep raw bytes, hashes, decoder identity, manual
   citations, and unresolved warnings beside the report. Do not silently repair,
   pad, interpolate, truncate, or discard unexplained bytes.
6. **Gate analysis**: permit analysis only at the level supported by the report.
   For example, code-domain statistics may be valid while voltage-domain results
   remain unverified.

## Check Selection

| Need | Read |
|---|---|
| Status vocabulary and report shape | [Status and reports](references/status-and-reports.md) |
| Provenance and evidence quality | [Evidence and provenance](references/evidence-and-provenance.md) |
| Waveform or segmented samples | [Waveform checks](references/waveform-checks.md) |
| Scalar measurements and repeated readings | [Scalar checks](references/scalar-checks.md) |
| Spectra, axes, event logs, and timestamps | [Axes and sequence checks](references/axes-and-sequences.md) |

Use `assets/integrity-report.json` as a starting point for a report. Adapt the
`checks` and `evidence` fields to the data type while retaining the top-level
status, reasons, provenance, and limitations.

## Status Rules

- `COMPLETE`: all applicable structural checks pass and no required evidence is
  missing for the stated claim.
- `INCOMPLETE`: required bytes, samples, segments, records, or end markers are
  missing.
- `INVALID`: framing, metadata, checksum, ordering, or type constraints
  contradict the observed artifact.
- `UNVERIFIED`: parsing succeeded, but available evidence cannot prove an
  important property such as completeness, units, calibration, or acquisition
  state.
- `UNSUPPORTED`: the checker deliberately does not implement the format or claim.

Report separate statuses when needed. For example:

```text
structure: COMPLETE
calibration: UNVERIFIED
analysis_allowed: code-domain-only
```

Do not downgrade a valid structural result merely because a different semantic
claim is unavailable; state both facts explicitly.

## Non-negotiable Rules

- Compare declared and observed lengths whenever the source declares a length.
- Multiply declared element count by declared bytes per element before accepting a
  binary payload as complete.
- Check segment continuity and uniqueness before merging files.
- Treat extra trailing bytes, duplicate records, gaps, and ambiguous boundaries as
  evidence that needs classification, not as harmless noise.
- Keep units, scale, offset, probe factor, resolution, and calibration evidence
  separate from transport completeness.
- Never infer missing samples, timestamps, units, or calibration from a convenient
  assumption.
- Preserve a hash of the raw or merged artifact and bind external calibration to
  the exact artifact hash.
- Distinguish “no anomaly found” from “analysis could not be trusted because the
  input was incomplete or unverified.”
