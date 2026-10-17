# Spec Contract: AI Waveform Analysis Tools

- **Created**: 2026-10-17
- **Status**: Analysis only
- **Target Files/Modules**: Existing SDS824X HD capture artifacts and scripts; no implementation requested in this task

## 1. Core Objective
Define a local analysis layer that converts large oscilloscope captures into compact, evidence-linked JSON for an AI agent without treating lossy summaries as replacements for raw waveform data.

## 2. Hard Constraints & Negative Rules
- [x] **C-01**: Preserve the captured raw payload and its metadata/checksum as the authoritative evidence.
- [x] **C-02**: Do not send multi-million-sample arrays to the model by default.
- [x] **C-03**: Do not claim that downsampling, summary statistics, or a visual envelope preserve all diagnostic information.
- [x] **C-04**: Keep instrument measurements, computed measurements, and diagnostic hypotheses distinct and traceable.
- [x] **C-05**: Do not infer voltage units from V/div alone; use per-channel descriptor/configuration scale, probe factor, offset, data width, and byte order.
- [x] **C-06**: No code or capture behavior changes are part of this analysis request.

## 3. Atomized Acceptance Criteria
- [x] **AC-01**: Research and cite mature methods for large-series visualization reduction, local signal processing, memory-mapped access, and structured agent-tool results.
- [x] **AC-02**: Define a layered workflow from integrity/calibration checks through compact summaries, task-specific detectors, and on-demand raw-window retrieval.
- [x] **AC-03**: Explain what information each summary preserves and what it can hide; include event-specific extraction separate from envelope downsampling.
- [x] **AC-04**: Specify bounded JSON fields, output limits, evidence provenance, uncertainty, and pagination/resource-link behavior.
- [x] **AC-05**: Map recommendations to the current BYTE/WORD SDS capture format and the four per-channel V/div settings supplied by the user.
- [x] **AC-06**: Separate analog-scope waveform analysis from VCD/FST/FSDB digital-simulation tools and generic feature libraries.

## 4. Edge Cases & Boundary Conditions
- Segment boundary events must be detected with overlapping context and deduplicated by absolute sample index.
- WORD samples require confirmed LSB byte order and the device's calibrated vertical scaling; the 16-bit container does not imply 16 effective ADC bits.
- Narrow pulses, multiple same-polarity events inside a summary bucket, clipping, flat/NaN data, low SNR, and insufficient observed periods must lower confidence or produce an explicit unknown result.
- Cross-channel temporal association is not causation; channel alignment/skew and common time origin must be verified.

## 5. Execution & Verification Log
- [x] Reviewed the existing capture/parser/validator interfaces and current skill guidance.
- [x] Researched M4, NumPy memmap, SciPy signal analysis, MCP structured outputs, wavekit-mcp, WAL, and catch22.
- [x] Delivered architecture and implementation priorities in the response; no source files or capture behavior changed.
