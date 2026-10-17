# Spec Contract: Measurement Data Integrity Skill

- **Created**: 2026-10-17 21:30
- **Status**: Completed
- **Target Files/Modules**: `skills/measurement-data-integrity/`, `registry.yaml`, `README.md`, `README.zh-CN.md`, `dist/measurement-data-integrity.skill`

## 1. Core Objective

Create a vendor-neutral AgentSkill that guides agents and contributors in deciding whether instrument-derived data is complete, invalid, incomplete, or unverified, based on explicit evidence rather than parser success alone.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Keep the Skill independent of any vendor, model, command tree, transport, or instrument family.
- [x] **C-02**: Do not connect to instruments, configure hardware, or provide device-control code.
- [x] **C-03**: Keep data integrity distinct from semantic parsing, calibration, and domain analysis.
- [x] **C-04**: Never infer `COMPLETE` from a successful numeric parse when completeness evidence is absent.
- [x] **C-05**: Preserve the distinction between `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, and `UNSUPPORTED`.
- [x] **C-06**: Do not include vendor manuals or require external runtime dependencies.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: A discoverable `measurement-data-integrity/SKILL.md` exists with trigger-oriented frontmatter and a concise workflow.
- [x] **AC-02**: The Skill defines evidence-first checks for declared length, observed length, element width, segments, checksums, timestamps, units, calibration, and source status.
- [x] **AC-03**: References cover status semantics, evidence/provenance, type-specific checks, and failure reporting.
- [x] **AC-04**: A reusable integrity-report template records status, checks, reasons, evidence, provenance, and limitations.
- [x] **AC-05**: The Skill explicitly addresses waveforms, scalar measurements, spectra, and status/event records without assuming one data shape.
- [x] **AC-06**: README files list the Skill and preserve the single established `npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill` command.
- [x] **AC-07**: `registry.yaml` records the Skill as vendor-neutral and analysis/integrity oriented.
- [x] **AC-08**: `quick_validate.py`, package creation, archive integrity, and CLI discovery pass; existing tests remain unaffected.
- [x] **AC-09**: Changes are committed with an English Conventional Commit message; existing untracked artifacts remain uncommitted.

## 4. Edge Cases & Boundary Conditions

- A payload can be syntactically parseable but shorter than the declared record.
- A format can contain no declared length, sequence, checksum, or status evidence; the result must remain `UNVERIFIED`.
- Extra trailing bytes must be reported, not silently discarded.
- Validity of units or calibration may be unknown even when byte completeness passes.
- Scalar records, waveform samples, and event logs require different evidence checks.
- An integrity report should remain useful when only a subset of checks is applicable.

## 5. Execution & Verification Log

- [x] Initial scaffolding
- [x] Skill and references implementation
- [x] Report template implementation
- [x] Registry and README updates
- [x] Automated validation and package verification
- [x] Acceptance audit and commit
