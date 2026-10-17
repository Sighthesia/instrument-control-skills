# Spec Contract: Left-Aligned Trigger Capture Strategy

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `capture_scope.py`, `scope_protocol.py`, tests, `SKILL.md`, signal reference, packaged skill

## 1. Core Objective
Add an explicit single-shot capture option that places a trigger at a configurable left-screen margin, maximizing post-trigger storage while preserving the existing SDS824X HD safety and state-transition rules.

## 2. Hard Constraints & Negative Rules
- [x] **C-01**: Never send `ARM`; a new capture still uses only `TRMD SINGLE` and verifies `Ready -> Stop`.
- [x] **C-02**: Apply timebase/delay/reference/memory-depth writes only before `TRMD SINGLE`; never change a stopped frame.
- [x] **C-03**: Do not change default capture behavior unless the caller explicitly enables the strategy or supplies a related option.
- [x] **C-04**: Do not enable the strategy with `--existing-stopped`; return a clear argument error.
- [x] **C-05**: Preserve raw capture metadata and report requested/read-back timebase, delay, reference position, memory depth, and computed pre/post window.
- [x] **C-06**: Treat `TIM:REF:POS` as an optional explicit setting; the mathematical delay strategy must work without it.

## 3. Atomized Acceptance Criteria
- [x] **AC-01**: Query `TIM:SCAL?` before calculating delay and set `TIM:DEL = (5 - margin_div) * timebase` for `0 < margin_div <= 5`.
- [x] **AC-02**: Read back `TIM:SCAL?` and `TIM:DEL?`; reject materially different values and report the resulting `pre_trigger_s`, `post_trigger_s`, and `total_window_s`.
- [x] **AC-03**: Support automatic SDS800X HD memory depth selection: 100M for one channel, 50M for two, and 25M for three/four; support explicit `100M|50M|25M` override.
- [x] **AC-04**: Optionally set/read back `TIM:REF:POS` using the documented integer percentage range 0..100; do not assume it is required for delay correctness.
- [x] **AC-05**: Apply strategy only before `TRMD SINGLE`, reject stopped-frame use, and preserve the no-`ARM` command log invariant.
- [x] **AC-06**: Add offline tests for delay math, margin validation, memory-depth selection, readback mismatch, optional reference position, and CLI argument guards.
- [x] **AC-07**: Update progressive references and package output with a documented example and limitation that this strategy is for trigger-following events, not pre-trigger analysis.

## 4. Edge Cases & Boundary Conditions
- `margin_div <= 0` or `margin_div > 5` must fail before connecting; a positive delay is required by the strategy.
- A non-finite or non-positive timebase, malformed readback, or unsupported memory-depth readback must fail closed.
- Three active channels use the four-channel 25M depth class unless the caller explicitly overrides it.
- Memory depth is a storage limit, not a guarantee that the selected timebase/sample rate will produce that many points; the post-capture WAVEDESC remains authoritative.
- Reference-position changes may affect later horizontal scaling behavior; record them as a configuration change and never apply them during `--existing-stopped` reads.

## 5. Execution & Verification Log
- [x] Confirmed the manual formula and command support for `TIM:SCAL?`, `TIM:DEL`, `TIM:REF:POS`, and `ACQ:MDEP`.
- [x] Implement strategy and metadata.
- [x] Add offline tests and run existing protocol/analysis tests.
- [x] Validate skill, rebuild package, and commit task-scoped changes.
