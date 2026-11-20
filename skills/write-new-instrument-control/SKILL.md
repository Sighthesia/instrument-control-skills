---
name: write-new-instrument-control
description: Guide the creation of a new instrument-control Skill from programming manuals, raw ASCII or binary responses, and metadata. Use when adding support for a new oscilloscope, multimeter, power supply, analyzer, or other instrument, especially when hardware is unavailable and communication, parsing, data integrity, and provenance must be explicit, or when auditing command coverage and transport behavior.
---

# Write New Instrument Control

## Purpose

Use this Skill when creating a new, self-contained instrument-control Skill. It
guides the complete authoring path:

```text
programming manual and evidence
  -> command index and transport contract
  -> control workflow and raw response capture
  -> device-specific framing and parser
  -> normalized output
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
   separate from manual-documented fields and hardware observations. Enumerate the
   manual's commands from its own list or headings, not from a search for syntax
   lines, and keep documented-only rows separate from verified rows.
3. **Classify response formats**: identify line-oriented text, CSV, IEEE 488.2
   binary, length-prefixed binary, packetized data, segmented records, or a custom
   format. Record the command or acquisition operation that produced each fixture.
4. **Separate parser stages**: implement framing, metadata parsing, payload
   extraction, normalization, and validation as distinct functions. Do not let a
   convenient text conversion hide binary boundaries or invalid bytes.
5. **Define the artifact**: choose a data kind such as `waveform`,
   `scalar-measurement`, `spectrum`, or `status-record`. Record identity, source,
   units, and support level.
6. **Validate evidence**: compare declared and observed lengths, element widths,
   segment ranges, checksums, timestamps, units, configuration, and source status
   where available. Return `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, or
   `UNSUPPORTED`; never silently pad, truncate, interpolate, or infer.
7. **Confirm the transport contract**: establish one command per write, the
   response terminator, idle and total read budgets, empty-reply retry, and
   definite-length block completion on the real interface. Record each rule as
   verified or unconfirmed.
8. **Verify on hardware when available**: exercise the workflow on the real
   instrument and record model, firmware, and interface, optionally with
   screenshots.
9. **Declare support**: label manual-only (`documented`), hardware-verified, and
   firmware/interface-scoped claims separately. Include known limitations and the
   exact evidence used.

Read the matching reference before implementing a stage:

| Task | Reference |
|---|---|
| Choose Skill stages and deliverables | [Authoring workflow](references/authoring-workflow.md) |
| Enumerate the manual's commands and separate documented from verified rows | [Command index](references/command-index.md) |
| Select an instrument type and matching example | [Instrument types and examples](references/instrument-types-and-examples.md) |
| Handle response boundaries and binary framing | [Response framing](references/response-framing.md) |
| Confirm terminators, retries, and block completion before trusting a read | [Transport rules](references/transport-rules.md) |
| Separate metadata, payload, normalization, and validation | [Metadata and validation](references/metadata-payload-validation.md) |
| Decide integrity status and report failures | [Status and reports](references/status-and-reports.md) |
| Check waveforms and segmented samples | [Waveform checks](references/waveform-checks.md) |
| Check scalar readings and measurement context | [Scalar checks](references/scalar-checks.md) |
| Check spectra, axes, event logs, and sequences | [Axes and sequence checks](references/axes-and-sequences.md) |
| Record evidence, provenance, calibration, and one label per claim | [Evidence and provenance](references/evidence-and-provenance.md) |
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
|   |-- workflow, transport, and measurement notes
|   `-- command-reference.md   # coverage claim with a status per row
|-- assets/          # optional: fixtures and expected results
|-- manifest.json
`-- SUPPORT.md
```

The parser template is intentionally a small example protocol. Replace its
framing and field names; do not claim that the example wire format is a vendor
standard. Its synthetic protocol has no sentinel value; when adapting it, add the
instrument's enumerated non-values before the first numeric conversion.

## Coverage Audit Tooling

`scripts/` ships two standard-library tools so a coverage claim can be re-run
instead of re-implemented. Neither touches an instrument.

```bash
# manual -> paged text + a command/page TSV (authority from body headings and TOC)
python3 scripts/extract_command_pages.py ref/<manual>.pdf \
    --out-text /tmp/manual.txt --out-tsv /tmp/manual.tsv

# TSV vs an index: gaps, subsystem table, and a classification per gap
python3 scripts/diff_command_index.py --manual /tmp/manual.tsv \
    --index skills/<skill>/references/command-reference.md --report /tmp/audit.md

# index vs the commands the code actually sends
python3 scripts/diff_command_index.py --drift \
    --index skills/<skill>/references/command-reference.md --code skills/<skill>/scripts
```

Run with the default flags first. `--allow-indented` and `--table-mode` exist for
manuals that print commands inside a table cell rather than as a heading followed
by a syntax line; in that mode the extractor also picks up parameter-table rows
and prose, so every residual must be triaged by hand. Set `--min-page` to the
first page of the command chapter to bound it.

The gap classification (`placeholder-variant`, `short-form`, `example-line`,
`wrapped-heading`, `true-gap`) is a triage aid, not a verdict: only `true-gap` is
a defect, and a `wrapped-heading` result means the manual's parent heading wraps
children and is not a sendable command. Never widen the matcher to lower the
number. `--drift` reports commands the code sends but the index does not list, and
(hint only) rows labelled `hardware-verified` that the code never sends.

The tools cannot tell you that a command which answers on the instrument is
missing from the manual; that class belongs in a `measured-only` section, labelled
`UNVERIFIED` against the manual.

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

Before any numeric conversion, match each numeric field against the enumerated
non-value table. A sentinel or unset value is `INCOMPLETE` with a `null` field and
a reason, never `0` and never a finite reading.

Record how each read ended: terminator, declared length, idle timeout, or overall
deadline. A read that ended on a timeout is `INCOMPLETE` evidence, not a short
valid response.

Use `assets/integrity-report.json` as a starting point. Keep raw bytes, request,
identity, interface, timestamp, parser version, manual citation, hashes, and known
limitations beside the normalized artifact.

Runnable teaching examples live under `assets/examples/`. They are synthetic,
vendor-neutral, standard-library-only, and included in the packaged Skill. Run all
of them with:

```bash
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
```

The examples deliberately cover different instrument/data types and wire formats;
copy their stage boundaries and tests, not their synthetic field names.

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
- Do not claim a command index is complete without a normalized difference against
  the manual's own command list; keep documented-only rows separate from
  hardware-verified rows.
- Enumerate the instrument's non-values before parsing numbers; a sentinel or
  unset value is `INCOMPLETE`, never a measurement.
- Send one command per write and read before the next write; end a definite-length
  block at its declared length or an overall deadline, never at an idle gap.
- Never retry a write; retry an empty reply only for an idempotent query and keep
  both attempts.
- Record manual defects; do not copy them into sendable commands.

## Pre-submission Checks

A new Skill is not finished until its own offline tests pass. Run from the
repository root:

```bash
python3 -m unittest discover -s skills/<skill-name>/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>
npx skills@latest add . --list
```

The tests are offline. Nothing in the verification path opens a socket, enumerates
VISA resources, or fetches a URL, so a passing run does not re-verify hardware
behavior. If the Skill has a session or transport module, its fake-transport tests
are part of the suite; see [Replay testing](references/replay-testing.md).

## Support Levels

Use the most conservative applicable label:

| Level | Meaning |
|---|---|
| `documented` | Implementation follows a cited official manual; no hardware evidence is claimed. |
| `hardware-verified` | The parser or control workflow was exercised against a real instrument response. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and test date. |

These labels describe evidence, not feature breadth. A broad implementation can
remain `documented`.

The label belongs to one claim, not to the Skill: an index can be `documented` row
by row while its identity query is `hardware-verified`. Apply the per-claim test in
[Evidence and provenance](references/evidence-and-provenance.md#label-one-claim-at-a-time).
