# Spec Contract: Exhaustive Edge and Pulse-Cluster Analysis

- **Created**: 2026-10-28
- **Status**: In Progress
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/scripts/waveform_analysis.py`, `scripts/analyze_waveform.py`, `scripts/test_waveform_analysis.py`, `SKILL.md`, `references/screenshot-and-waveform.md`

## 1. Core Objective

Add a reproducible fact layer that scans original-resolution samples to produce a traceable edge table, paired high-level pulses, pulse clusters, and explicitly bounded classifications. Prevent previews and aggregates from being promoted into absolute absence, drive, or duration claims.

## 2. Hard Constraints

- [x] **C-01**: Edge and pulse reconstruction uses every original sample and has no stride/downsample input.
- [x] **C-02**: Unpaired capture-boundary pulses remain `INCOMPLETE`; no missing edge or pulse width is inferred.
- [x] **C-03**: Edge-budget or JSON-output truncation is explicit and cannot appear complete.
- [x] **C-04**: Existing event pagination and capture evidence behavior remains compatible; tests are offline and do not contact hardware.

## 3. Acceptance Criteria

- [x] **AC-01**: A `structure` CLI command and Python API emit edges, high pulses, pulse clusters, classification basis, and coverage evidence.
- [x] **AC-02**: Every edge and pulse traces to sample indexes and times; edge entries preserve crossing direction, before/after codes, same-direction interval, and time uncertainty.
- [x] **AC-03**: The output distinguishes sustained carrier, short burst, low-duty pulse train, and insufficient evidence without using aggregate window counts as the primary evidence.
- [x] **AC-04**: A 6-sample pulse missed by stride 25 and 20 sparse narrow pulses are still found by the raw scan.
- [x] **AC-05**: Boundary pulses are marked incomplete, low-duty pulses are not labeled absent, and a no-crossing result is scoped to detection capability.
- [x] **AC-06**: Exceeding edge budget returns `UNVERIFIED` lower-bound counts; bounded JSON flags each shortened evidence list.
- [x] **AC-07**: Documentation makes raw-sample structure the fact layer and limits M4/stride to visualization.
- [x] **AC-08**: All offline tests, compilation, Skill validation, and CLI discovery pass.
- [ ] **AC-09**: Changes are committed using an English conventional commit.

## 4. Verification Log

- [x] Implementation reviewed
- [x] Offline tests and compilation
- [x] Skill validation and discovery
- [ ] Acceptance audit and commit
