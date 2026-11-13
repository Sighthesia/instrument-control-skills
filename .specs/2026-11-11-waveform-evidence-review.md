# Spec Contract: Waveform Evidence Review

- **Created**: 2026-11-11
- **Status**: Completed (research only; implementation not approved)
- **Target Files/Modules**: siglent-sds800xhd-control capture, validation, analysis, and screenshot workflow

## 1. Core Objective
Evaluate how deterministic validation and AI review can prevent false claims of waveform completeness, incompleteness, and signal absence.

## 2. Hard Constraints & Negative Rules (Non-negotiables)
- [x] **C-01**: Research without instrument access or changes to Skill behavior.
- [x] **C-02**: Separate verified current behavior, external documentation, and proposed improvements.

## 3. Atomized Acceptance Criteria (Checklist)
- [x] **AC-01**: Inspect existing integrity and interpretation gates, including screen-count semantics.
- [x] **AC-02**: Verify relevant vendor and binary-transfer documentation online.
- [x] **AC-03**: Compare screenshot-first, script-only, and combined evidence workflows.
- [x] **AC-04**: Define evidence scopes, failure handling, and regression acceptance criteria.

## 4. Edge Cases & Boundary Conditions
- A complete descriptor record need not cover the whole acquisition memory or the requested event.
- Equal lengths and matching hashes do not prove same-frame identity or correct instrument transfer semantics.
- A screenshot can contain persistence, a zoomed view, processed traces, or a different frame.
- Sparse events can be suppressed by a whole-record level histogram; refusal is not absence.
- Complete downloaded samples can still be insufficient for pulse timing or protocol decoding.
- An unavailable screenshot restricts visual correspondence claims, not independent payload validation.

## 5. Execution & Verification Log
- [x] Read-only child review plus parent codegraph verification of validate_frame and build_verdict.
- [x] Inspected Skill evidence gates and screenshot-reader limitation.
- [x] Exa searches verified vendor acquisition semantics, aliasing limitations, and PyVISA binary framing.
- [x] Memorix CLI search returned no matching records; no repeated search.
- [x] No instrument commands or implementation changes made.

## Proposed Direction (not implemented)
Use an orchestrated evidence package: acquisition context and optional screenshot, exact descriptor-range download, independent integrity checks, full-sample candidate scan, task-specific analysis, and AI review of structured results and selected original-resolution windows. Require explicit scope on every completeness claim.

Report payload integrity, requested-range coverage, frame association, timing correspondence, analysis capability separately. Screenshot capture should be attempted when safe, but screenshot failure must not invalidate independently verified data. Unknown range or association remains UNVERIFIED rather than becoming INCOMPLETE.

Provide an audited sparse-event escalation path after automatic threshold refusal. Candidate localization is not pulse counting; local threshold validation and sampling sufficiency must pass before further claims. Local success cannot establish record-wide absence or stability.

Regression acceptance should cover valid screen/descriptor count differences; short, overlapping, missing, and reordered segments; width and byte-order errors; frame/configuration changes; screenshot unavailability; sparse events; undersampling; capture-boundary pulses; and truncated analysis output. Each case must test both permitted and prohibited claims.

## Sources
- Siglent SDS800X HD Programming Guide EN11G: https://siglentna.com/wp-content/uploads/dlm_uploads/2024/09/SDS800XHD_Series_ProgrammingGuide_EN11G.pdf — memory management, maximum depth, acquisition type.
- Siglent SDS Programming Guide EN11F: https://siglentna.com/wp-content/uploads/dlm_uploads/2024/03/ProgrammingGuide_EN11F.pdf — ACQuire:POINts describes current on-screen waveform points.
- Tektronix XYZs of Oscilloscopes: https://download.tek.com/document/XYZs-of-Oscilloscopes_Primer_03W-8605-8.pdf — sampling, reconstruction, aliasing, record length; general principles, not Siglent command semantics.
- PyVISA Reading and Writing Values: https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html — binary framing, data type, endianness, advertised length, and termination.
