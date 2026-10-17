# Spec Contract: AI Waveform Analysis Tools

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `siglent-sds800xhd-control/scripts/`, tests, skill documentation, package output

## 1. Core Objective
Design and implement a first local analysis layer that converts large oscilloscope captures into compact, evidence-linked JSON for an AI agent without treating lossy summaries as replacements for raw waveform data.

## 2. Hard Constraints & Negative Rules
- [x] **C-01**: Preserve the captured raw payload and its metadata/checksum as the authoritative evidence.
- [x] **C-02**: Do not send multi-million-sample arrays to the model by default.
- [x] **C-03**: Do not claim that downsampling, summary statistics, or a visual envelope preserve all diagnostic information.
- [x] **C-04**: Keep instrument measurements, computed measurements, and diagnostic hypotheses distinct and traceable.
- [x] **C-05**: Do not infer voltage units from V/div alone; use per-channel descriptor/configuration scale, probe factor, offset, data width, and byte order.
- [x] **C-06**: Keep analysis read-only with respect to the scope and raw capture artifacts; do not change capture behavior.
- [x] **C-07**: Process large files in bounded chunks or via memory mapping; bound every list returned to AI.

## 3. Atomized Acceptance Criteria
- [x] **AC-01**: Base the architecture on mature methods for large-series visualization reduction, local signal processing, memory-mapped access, and structured agent-tool results.
- [x] **AC-02**: Implement capture integrity/calibration inspection, bounded chunked summary, M4 preview, edge/runt/missing-pulse events, and on-demand waveform windows.
- [x] **AC-03**: Keep visualization reduction separate from full-resolution event scans and document the lossy limits of each output.
- [x] **AC-04**: Emit bounded JSON with evidence provenance, assumptions, uncertainty, and event pagination.
- [x] **AC-05**: Support the existing BYTE/WORD SDS capture artifact schema, LSB WORD, descriptor conversion, and panel V/div values 2/2/10/5 V/div when supplied or verified.
- [x] **AC-06**: Keep this first implementation focused on analog oscilloscope captures; do not add simulation waveform, protocol-decoder, or generic ML feature-engine dependencies.
- [x] **AC-07**: Add deterministic tests for scaling, M4 preservation, chunk-boundary event handling, pagination/output bounds, and invalid/incomplete captures.
- [x] **AC-08**: Validate the skill and package; preserve unrelated working-tree changes.

## 4. Edge Cases & Boundary Conditions
- Segment boundary events must be detected with overlapping context and deduplicated by absolute sample index.
- WORD samples require confirmed LSB byte order and the device's calibrated vertical scaling; the 16-bit container does not imply 16 effective ADC bits.
- Narrow pulses, multiple same-polarity events inside a summary bucket, clipping, flat/NaN data, low SNR, and insufficient observed periods must lower confidence or produce an explicit unknown result.
- Cross-channel temporal association is not causation; channel alignment/skew and common time origin must be verified.

## 5. Execution & Verification Log
- [x] Reviewed the existing capture/parser/validator interfaces and current skill guidance.
- [x] Researched M4, NumPy memmap, SciPy signal analysis, MCP structured outputs, wavekit-mcp, WAL, and catch22.
- [x] Delivered architecture and implementation priorities in the prior response.
- [x] Write design document and complete independent subagent design review before implementation.
- [x] Implement scripts, tests, skill usage, and package update.
- [x] Run tests, skill validation, and package checks; commit task-scoped changes.
