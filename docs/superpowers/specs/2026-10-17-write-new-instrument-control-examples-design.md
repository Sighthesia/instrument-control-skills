# Design: Multi-Type Examples for `write-new-instrument-control`

- **Status**: Reviewed; implementation approved
- **Scope**: Expand the authoring Skill with instrument-type guidance, response-format examples, normative parser structure, integrity checks, and offline replay tests.

## Intent

`write-new-instrument-control` currently contains one executable length-prefixed
scalar example and broad written guidance. A contributor adding a new oscilloscope,
multimeter, analyzer, or other instrument still has to infer how the same authoring
rules apply to different instrument data shapes and wire formats.

This change makes the Skill teach by contrast. It will provide small, dependency-
free, runnable examples that show how an author adapts the same parser stages to
different instrument types and response formats while preserving a common evidence
and integrity contract.

## Research Basis

The design reuses established patterns, without copying implementation code:

- [PyVISA: Reading and Writing values](https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html)
  distinguishes ASCII and binary transfers and requires explicit datatype,
  endianness, header, termination, and sometimes expected point-count decisions.
- [PyVISA-sim: Building simulated instruments](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html)
  models query/response dialogues, end-of-message rules, and raw bytes for offline
  instrument simulation.
- [QCoDeS community drivers](https://github.com/QCoDeS/Qcodes_contrib_drivers)
  separates driver code, examples, and tests, and treats hardware support as the
  responsibility of the individual contributor.
- [PyMeasure adapters](https://pymeasure.readthedocs.io/en/latest/api/adapters.html)
  and [advanced communication protocols](https://pymeasure.readthedocs.io/en/latest/dev/adding_instruments/advanced_communication.html)
  separate instrument semantics from transport details and provide protocol-test
  patterns for command/response behavior.

These sources support the repository's existing choice to keep device-specific
control rules local and to use replay fixtures instead of requiring hardware in CI.

## Goals

1. Make instrument type and data shape explicit before parser code is written.
2. Show five representative parser patterns:
   - oscilloscope waveform + IEEE 488.2 definite-length binary block;
   - multimeter scalar reading + line-oriented/CSV-like text;
   - analyzer or sweep data + CSV with an independent axis;
   - segmented/custom binary data + sequence and range validation;
   - logger/status event records + sequence and end-marker validation.
3. Give every example a normative stage boundary:
   `read_frame -> parse_metadata -> extract_payload -> normalize -> validate`.
4. Keep each example self-contained, runnable with Python standard library only,
   and testable without a real instrument.
5. Demonstrate that structural completeness, semantic validity, calibration, and
   support level are separate claims.
6. Keep examples small enough to copy into a new instrument Skill without creating
   a framework or plugin dependency.

## Non-goals

- Implement Keithley 2000 or any other real device control Skill.
- Claim that synthetic examples are vendor-specific behavior.
- Build a universal instrument adapter base class or a runtime registry.
- Replace the existing Siglent control code or waveform analysis code.
- Add PyVISA, PyVISA-sim, NumPy, or other runtime dependencies to the authoring Skill.
- Treat a parser example as hardware verification.

## Conceptual Model

Use two orthogonal axes when choosing an example:

### Instrument/data type

| Type | Typical normalized artifact | Primary risks |
|---|---|---|
| Oscilloscope | ordered waveform samples | byte width, byte order, point count, segments, scale/calibration |
| Multimeter | scalar measurement records | function/unit, status/overload, reading count, configuration context |
| Analyzer/sweeper | axis + value arrays | axis monotonicity, bin count, units, missing/duplicate points |
| Logger/status source | ordered events or records | sequence gaps, timestamps, continuation/end markers |

### Response format

| Format | Framing evidence | Example focus |
|---|---|---|
| IEEE 488.2 definite-length block | `#`, length-of-length, exact payload | preserve binary bytes and validate declared length |
| Line/CSV text | terminator, columns, token count | explicit encoding, units, status, row/reading count |
| Segmented/custom binary | segment id/start/count, checksum or end marker | gaps, overlaps, duplicates, short payloads |

An instrument Skill selects the combination that matches its actual manual and
response evidence. The examples are format-focused teaching aids, not a list of
supported vendors.

## Proposed Resource Layout

```text
skills/write-new-instrument-control/
├── SKILL.md
├── references/
│   ├── authoring-workflow.md
│   ├── instrument-types-and-examples.md
│   ├── instrument-types-and-examples.md
│   ├── response-framing.md
│   ├── metadata-payload-validation.md
│   ├── status-and-reports.md
│   ├── waveform-checks.md
│   ├── scalar-checks.md
│   ├── axes-and-sequences.md
│   ├── evidence-and-provenance.md
│   └── replay-testing.md
└── assets/
    ├── integrity-report.json
    ├── parser-template/
    └── examples/
        ├── oscilloscope-ieee-block/
        ├── multimeter-scalar-text/
        ├── analyzer-csv-sweep/
        ├── segmented-binary-records/
        └── status-event-records/
```

Each example contains:

```text
example.json             # type, format, purpose, evidence level
parser_<example>.py      # pure parser stages; no hardware I/O
tests/test_<example>.py  # unittest replay tests
expected-result.json     # normalized output and integrity expectations
fixtures/                # binary-safe raw responses and negative cases
```

Use `example.json` so metadata can be validated with the Python standard library.
Keep fixture bytes in files, not only as escaped strings in tests. Every example's
test module must import a uniquely named parser module; never use four sibling
modules all named `parser.py` under one unittest discovery run.

## Example Contracts

### Oscilloscope / IEEE block

- Find `#`, read the length-of-length digit, read exact length digits, then exact
  payload bytes.
- Preserve prefix, header, payload, trailing bytes, and raw SHA-256.
- Parse a tiny metadata preamble containing point count, bytes per point, interval,
  and unit; do not use a vendor-specific `WAVEDESC` field layout.
- Validate `point_count * bytes_per_point == payload length`.
- Mark physical-unit calibration `UNVERIFIED` when only raw codes are available.
- Test a valid block, truncated block, invalid length field, wrong payload width,
  and trailing bytes.

### Multimeter / scalar text

- Parse a response containing value, unit, function, and status fields.
- Validate finite numeric value, supported unit syntax, expected function, and
  status/overload markers.
- Demonstrate that one valid value without acquisition count or status evidence can
  be `UNVERIFIED` for sequence completeness.
- Test normal reading, overload, malformed number, missing unit, and extra tokens.

### Analyzer / CSV sweep

- Parse headers and rows without assuming a specific vendor.
- Validate required columns, numeric values, equal axis/value counts, units, and
  monotonic independent axis.
- Treat duplicate or missing axis points as explicit integrity failures.
- Test normal sweep, missing column, malformed row, non-monotonic axis, and duplicate
  point.

### Segmented/custom binary

- Parse a deterministic segment header containing sequence, start, count, and bytes
  per element.
- Validate each segment payload before merging.
- Validate global range continuity, uniqueness, ordering, and expected total count.
- Test valid two-segment merge, gap, overlap, duplicate sequence, short payload,
  and malformed header.

### Logger/status source / event records

- Parse line-oriented records containing sequence, timestamp, event kind, and an
  explicit end marker.
- Validate sequence continuity, timestamp ordering, required fields, and end-marker
  presence.
- Test a complete sequence, sequence gap, duplicate sequence, malformed timestamp,
  and missing end marker.

## Normative Parser Contract

Every example must keep these stages visible and independently testable:

```python
frame = read_frame(raw)
metadata = parse_metadata(frame)
payload = extract_payload(frame)
artifact = normalize(metadata, payload)
report = validate(artifact, raw=raw)
```

No example may open a socket, enumerate VISA resources, or issue commands. A future
device Skill may place control code beside the parser, but its parser tests must be
able to consume saved bytes independently. A standard-library guard test scans all
example source files for forbidden transport imports and hardware calls.

### Failure convention

- `read_frame()` raises `ParserError` for impossible or truncated framing, because
  there is no safe artifact to normalize.
- `parse_metadata()`, `extract_payload()`, and `normalize()` may raise
  `ParserError` for malformed fields that make the artifact structurally unusable.
- `validate()` always returns the `integrity-report-v1` shape, including `status`,
  `checks`, `reasons`, `evidence`, `provenance`, and `limitations`.
- Use `INVALID` for contradictory framing/metadata, `INCOMPLETE` for missing bytes,
  records, segments, or end markers, `UNVERIFIED` for missing semantic/calibration
  evidence, and `UNSUPPORTED` for an intentionally unimplemented kind/version.

## Evidence and Status Contract

Use `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, and `UNSUPPORTED` as the
primary status vocabulary. Individual checks use `pass`, `fail`, and `not_checked`.

Examples must show at least one case where parsing succeeds but the result is not
fully trusted. For example:

```text
structure: COMPLETE
calibration: UNVERIFIED
analysis_allowed: code-domain-only
```

Every example must state its evidence level as `documented` or `replay-tested`; no
synthetic example is `hardware-verified`.

Every example test must load and compare `expected-result.json` for its normalized
fields and primary integrity status. Tests must not keep the expected result only
as inline Python literals.

## Verification Plan

Run all example tests through this standard-library discovery command, then run:

```bash
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/write-new-instrument-control
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py skills/write-new-instrument-control dist
unzip -t dist/write-new-instrument-control.skill
npx skills@latest add . --list
```

Existing Siglent tests must remain at 44 passing. The parser template's existing six
tests must remain passing. The five example groups must pass, including the static
offline guard. The final discovery result must remain exactly two Skills.

## Risks and Decisions

- **Risk: examples become a second framework.** Keep functions plain, files local,
  and copy boundaries explicit; do not introduce shared runtime imports.
- **Risk: synthetic wire formats are mistaken for vendor formats.** Name examples by
  type and format, not by vendor/model, and state this in each metadata file.
- **Risk: examples become too shallow.** Require negative fixtures for truncation,
  malformed framing, count mismatch, and semantic uncertainty.
- **Decision: no external dependencies.** PyVISA and PyVISA-sim remain cited
  references and optional patterns, while the bundled examples run offline with
  Python stdlib only.
- **Decision: package all examples.** They are teaching assets and are included in
  `dist/write-new-instrument-control.skill`; they are not separate installable
  Skills.
- **Decision: retain `integrity-and-provenance.md`.** It remains the compact support
  vocabulary reference; `evidence-and-provenance.md` covers the fuller artifact
  evidence chain. The new examples use both where appropriate.
- **Research correction:** PyVISA-sim informs query/response and EOM modeling, not
  the parser test runtime. PyMeasure supports transport/semantic separation and
  custom framing patterns; protocol-test claims are limited to the repository's
  own replay tests rather than attributed to the adapter API documentation.
