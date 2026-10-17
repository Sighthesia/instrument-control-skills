# Spec Contract: Multi-Type Instrument Control Authoring Examples

- **Created**: 2026-10-17 23:10
- **Status**: Completed
- **Target Files/Modules**: `skills/write-new-instrument-control/`, `docs/superpowers/specs/2026-10-17-write-new-instrument-control-examples-design.md`, `README.md`, `README.zh-CN.md`, `dist/write-new-instrument-control.skill`

## 1. Core Objective

Expand `write-new-instrument-control` with runnable, vendor-neutral examples that teach instrument types, response formats, parser stages, integrity reports, provenance, and offline replay tests.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Examples must be standard-library-only and must not connect to hardware, VISA, sockets, serial ports, or networks.
- [x] **C-02**: Examples must not claim vendor/model behavior; metadata must label them as synthetic teaching formats.
- [x] **C-03**: Keep framing exceptions separate from validation statuses and use the `integrity-report-v1` report shape.
- [x] **C-04**: Preserve raw binary fixtures as files and test negative evidence paths.
- [x] **C-05**: Do not introduce a shared runtime adapter framework or modify the Siglent control Skill.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: Add a direct `instrument-types-and-examples.md` reference and link it from `SKILL.md`.
- [x] **AC-02**: Add five examples: oscilloscope IEEE block, multimeter scalar text, analyzer CSV sweep, segmented binary records, and status/event records.
- [x] **AC-03**: Each example contains `example.json`, a uniquely named parser module, `tests/test_*.py`, `expected-result.json`, and raw/negative fixtures.
- [x] **AC-04**: Each parser exposes visible framing, metadata, payload, normalization, and validation stages.
- [x] **AC-05**: Each validation report includes status, checks, reasons, evidence, provenance, and limitations; at least one case per relevant type remains `UNVERIFIED` rather than falsely complete.
- [x] **AC-06**: Example tests consume `expected-result.json` and cover valid plus truncation/malformed/count/sequence/semantic failure paths as applicable.
- [x] **AC-07**: Add a static offline guard that rejects forbidden hardware/transport imports or connection calls in example source files.
- [x] **AC-08**: Update English and Chinese READMEs and design references with the example test command and research provenance.
- [x] **AC-09**: Existing 44 Siglent tests and parser-template 6 tests remain passing; all five example groups pass; validator, package, archive, and CLI discovery checks pass.
- [x] **AC-10**: Commit only intended files with an English Conventional Commit message; existing untracked artifacts/caches remain uncommitted.

## 4. Edge Cases & Boundary Conditions

- IEEE block payload may contain `#`, NUL, CR, or LF.
- CSV may have missing columns, malformed rows, duplicate or non-monotonic axis points.
- Scalar text may contain overload/status markers or unknown units.
- Segments may have gaps, overlaps, duplicate sequence numbers, short payloads, or malformed headers.
- Event records may have timestamp disorder, sequence gaps, duplicates, or missing end markers.
- A complete structure may still have unverified calibration or acquisition completeness.

## 5. Execution & Verification Log

- [x] Design revised after builder check
- [x] Five examples and shared teaching references implemented
- [x] Offline fixtures and tests implemented
- [x] README and Skill navigation updated
- [x] Full validation, packaging, and discovery checks
- [x] Acceptance audit and commit
