# Spec Contract: Time-Ranged Waveform and Ringing Analysis

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `waveform_analysis.py`, `analyze_waveform.py`, waveform-analysis tests, `SKILL.md`, analysis references, packaged skill

## 1. Core Objective
Allow an AI agent to inspect long motor captures without flooding context: select events by time range, retrieve high-resolution samples by time range, and obtain bounded screening metrics for switching-edge overshoot and ringing.

## 2. Hard Constraints & Negative Rules (Non-negotiables)
- [x] **C-01**: Preserve complete-capture validation and raw waveform SHA-256 evidence before every analysis operation.
- [x] **C-02**: Keep all JSON bounded by the existing default 256 KiB limit and local point/event limits.
- [x] **C-03**: Keep M4 previews explicitly lossy; never use a preview as evidence that narrow ringing was absent.
- [x] **C-04**: Keep voltage output conditional on existing BYTE calibration or exact WORD calibration evidence.
- [x] **C-05**: Mark ringing estimates as heuristic and expose capture/window boundary truncation instead of presenting them as definitive physical measurements.
- [x] **C-06**: Preserve existing sample-index APIs and existing event cursor behavior.

## 3. Atomized Acceptance Criteria (Checklist)
- [x] **AC-01**: `window` accepts a finite `[start_time_s, end_time_s)` range and returns the resolved sample range plus time metadata.
- [x] **AC-02**: `events` accepts an optional finite time range, scans only that range, reports resolved sample/time coverage, and keeps bounded pagination.
- [x] **AC-03**: Add a `ringing` operation with bounded local-window input by samples or time, returning edge location, baseline/final level, overshoot/undershoot, period/frequency when supported, decay estimate when supported, and explicit evidence limitations.
- [x] **AC-04**: Reject invalid, mixed, out-of-record, too-small, and over-budget ranges with fixed structured error envelopes through the CLI.
- [x] **AC-05**: Add deterministic tests for time conversion, time-limited event scans, ringing estimates, insufficient evidence, and boundary flags.
- [x] **AC-06**: Update `SKILL.md` and a task-specific reference with the staged workflow: inspect, summarize, time-range events, ringing, then raw window.
- [x] **AC-07**: Run protocol/analysis tests, validate the skill, rebuild the distributable package, and commit the task-scoped changes.

## 4. Edge Cases & Boundary Conditions
- Time ranges are half-open and use the capture's relative display-time origin, not wall-clock time.
- Time endpoints are converted conservatively to sample indices; a request must contain at least one complete sample.
- An event scan beginning mid-record must initialize threshold state from the preceding sample when available.
- A ringing window touching the capture boundary, placing the edge at its boundary, or retaining above-noise tail at the window end must report the relevant limitation.
- Fewer than three alternating residual zero crossings or significant extrema must produce `insufficient_evidence`, not fabricated frequency/decay values.
- WORD captures remain code-domain unless exact independent calibration is present.

## 5. Execution & Verification Log
- [x] Inspect existing bounded analyzer, event paging, window extraction, and calibration contracts.
- [x] Implement time-range selection and ringing metrics.
- [x] Add CLI commands/options, tests, and documentation.
- [x] Validate, package, and commit.
