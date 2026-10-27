# Spec Contract: Waveform Parsing Lessons and Protocol Guardrails

- **Created**: 2026-10-27 21:56
- **Status**: In Progress
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/scripts/scope_protocol.py`, `skills/siglent-sds800xhd-control/scripts/capture_scope.py`, related offline tests, waveform references and Skill guidance

## 1. Core Objective

Convert the six empirically confirmed waveform-analysis lessons and three Skill script defects into executable protocol guardrails and explicit documentation. The implementation must fail closed when the instrument silently truncates, returns decorated state values, uses an unsafe sampling/coordinate mode, or produces calibration evidence that does not match the captured channel.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Preserve raw binary payloads and metadata before analysis; never silently pad, truncate, interpolate, or treat a request/readback as proof of returned sample count.
- [x] **C-02**: Keep the existing single-session, no-`ARM`, `Ready -> Stop`, immutable/configured capture boundaries intact.
- [x] **C-03**: Keep offline tests hardware-free and do not add runtime dependencies beyond the repository's existing constraints.
- [x] **C-04**: Use ASCII for new/edited source and documentation text unless existing Chinese text requires otherwise; commit message must be English conventional-commit style.
- [x] **C-05**: Do not revert unrelated worktree changes under `.agents/` or `ref/`.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: Modern segment reads validate actual payload point count as `len(payload) / bytes_per_point` against the requested count and reject silent device truncation even when `WAV:POIN?` echoes the request.
- [x] **AC-02**: Segment metadata and merge/validation paths retain the actual returned point count and cannot advance ranges based only on requested count.
- [x] **AC-03**: `WAV:INTerval` remains explicitly set and verified as `1`; documentation warns against relying on instrument-side interval extraction and recommends local `[::stride]` extraction.
- [x] **AC-04**: State handling normalizes decorated `SAST?` responses such as `SAST Stop` while preserving raw response evidence, and `--existing-stopped` works with that response.
- [x] **AC-05**: Offline tests cover silent truncation with an echoed requested point count and decorated `Ready`/`Stop` state responses, including the CLI existing-stopped path where applicable.
- [x] **AC-06**: Documentation records the observed 250,000-point transfer ceiling/behavior, explicitly states that `WAV:POIN?` may be an echoed request and is not sufficient evidence, and requires `len(block.payload)`/actual width checks.
- [x] **AC-07**: Documentation and analysis guidance state that narrow-pulse signal presence requires full-record scanning or extrema/event detection, not one-point, mean, or sparse sampling; previews are visualization-only.
- [x] **AC-08**: Documentation and analysis guidance require channel calibration self-checks against a known logic-level channel before voltage interpretation, and retain code-domain/unverified status on mismatch.
- [x] **AC-09**: Documentation and diagnostic guidance warn that a probe/observer at the same frequency as the measured signal can alias into a false “signal changed” conclusion; require an unrelated observation rate or discriminating comparator output.
- [x] **AC-10**: Documentation and diagnostic guidance require hypotheses to explain all observations, including periodic retry windows, and forbid declaring a frozen counter from a single observation.
- [x] **AC-11**: Existing tests and repository consistency checks pass, including both waveform protocol/analysis test suites, Skill validation, and CLI Skill discovery; no hardware is contacted.
- [ ] **AC-12**: The completed changes are committed in one or more English conventional commits grouped by function.

## 4. Edge Cases & Boundary Conditions

- A device can echo `WAV:POIN?=1000000` while returning only 250000 points; the payload length is authoritative for the received segment and the caller must fail rather than silently renumber later segments.
- WORD payloads require two bytes per point; BYTE payloads require one byte per point.
- State responses may include command prefixes, whitespace, case differences, or other decoration; normalization must not erase the raw response recorded for evidence.
- A stopped frame can be valid for `--existing-stopped` without claiming a new `Ready -> Stop` transition, but it still must pass stopped-state validation.
- Any documentation of a 250000 limit must be scoped as observed firmware behavior, not a universal claim for every SDS800X HD model/firmware.

## 5. Execution & Verification Log

- [x] Initial repository and protocol inspection
- [x] Sub-agent broad audit and implementation
- [x] Parent-agent code review and targeted test additions/fixes
- [x] Full offline tests and repository consistency checks
- [ ] Acceptance checklist audited and commit created (blocked by repository safety policy)
