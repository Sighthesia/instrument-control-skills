---
name: instrument-parser-authoring
description: Guide the authoring of vendor-neutral instrument data parsers from programming manuals, raw ASCII or binary responses, metadata, and replay fixtures. Use when creating or reviewing a parser for waveform, scalar measurement, spectrum, status, CSV, IEEE 488.2, or custom binary data, especially when hardware is unavailable and evidence quality, completeness, provenance, and offline tests must be explicit.
---

# Instrument Parser Authoring

## Purpose

Use this skill to create a parser package that converts instrument-specific raw
responses into a normalized artifact without pretending that undocumented or
untested behavior is verified. The parser may be based on a programming manual,
replay fixtures, or hardware captures. It must preserve raw evidence and expose
what is known, inferred, incomplete, invalid, unsupported, or unverified.

This skill authors parsers; it does not connect to instruments, configure them,
or replace a domain-specific control skill.

## Authoring Workflow

1. **Classify the input**: identify whether the response is line-oriented text,
   CSV, IEEE 488.2 binary, length-prefixed binary, packetized data, or a custom
   format. Record the command or acquisition operation that produced it.
2. **Collect evidence**: obtain the official manual and cite its URL, revision,
   page or section. Preserve raw responses as bytes. Keep inferred fields
   separate from manual-documented fields.
3. **Separate parser stages**: implement framing, metadata parsing, payload
   extraction, normalization, and validation as distinct functions. Do not let a
   convenient text conversion hide binary boundaries or invalid bytes.
4. **Define the artifact**: choose a data kind such as `waveform`,
   `scalar-measurement`, `spectrum`, or `status-record`. Record identity, source,
   raw artifact path, hashes, units, encoding, and support level.
5. **Validate evidence**: compare declared and observed lengths, element widths,
   segment ranges, checksums, timestamps, units, and configuration where the
   source provides them. Return `COMPLETE`, `INCOMPLETE`, `INVALID`,
   `UNVERIFIED`, or `UNSUPPORTED`; never silently pad, truncate, or infer.
6. **Add replay tests**: test valid, truncated, malformed, length-mismatch, and
   unsupported responses offline. Assert both parsed values and the integrity
   status. Use binary fixtures for binary protocols.
7. **Declare support**: label manual-only, replay-tested, hardware-verified, and
   firmware/interface-scoped claims separately. Include known limitations and
   the exact evidence used.

Read the matching reference before implementing a stage:

| Task | Reference |
|---|---|
| Choose parser stages and deliverables | [Authoring workflow](references/authoring-workflow.md) |
| Handle response boundaries and binary framing | [Response framing](references/response-framing.md) |
| Separate metadata, payload, normalization, and validation | [Metadata and validation](references/metadata-payload-validation.md) |
| Record evidence and support levels | [Integrity and provenance](references/integrity-and-provenance.md) |
| Build offline fixtures and replay tests | [Replay testing](references/replay-testing.md) |

## Required Deliverable Shape

Start from `assets/parser-template/` and adapt only the protocol-specific parts:

```text
<vendor>-<model>-parser/
|-- parser.py
|-- tests/
|   |-- test_parser.py
|   `-- fixtures/
|-- manifest.json
|-- expected-result.json
|-- references/
|   `-- programming-manual.md
`-- SUPPORT.md
```

The template is intentionally a small example protocol. Replace its framing and
field names; do not claim that the example wire format is a vendor standard.

## Non-negotiable Rules

- Preserve raw bytes before decoding, and retain the exact request, identity,
  interface, timestamp, and SHA-256 where available.
- Do not call a result complete because a parser returned a number.
- Keep framing errors distinct from semantic or calibration uncertainty.
- Keep device-specific commands and field offsets out of reusable analysis code.
- Treat missing length, checksum, sequence, status, or calibration evidence as
  `UNVERIFIED`, unless the protocol proves completeness another way.
- Do not include copyrighted vendor manuals in the skill; cite the official source
  and record the relevant revision and page/section.
- Do not connect to real hardware from offline parser tests.

## Support Levels

Use the most conservative applicable label:

| Level | Meaning |
|---|---|
| `documented` | Implementation follows cited manual behavior; no replay or hardware evidence is claimed. |
| `replay-tested` | Raw fixtures, expected results, and negative cases pass offline. |
| `hardware-verified` | The parser was exercised against a real instrument response. |
| `firmware-scoped` | Hardware evidence records the exact firmware, interface, model, and test date. |

These labels describe evidence, not feature breadth. A parser can support many
documented commands while remaining unverified on hardware.
