# Spec Contract: Waveform Evidence Review

- **Created**: 2026-11-11
- **Status**: Completed (research and approved implementation; offline verification complete, hardware verification pending)
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
- [x] Research phase made no instrument commands or implementation changes; subsequent approved implementation is recorded below.

## Approved Direction
Use an orchestrated evidence package: acquisition context and optional screenshot, exact descriptor-range download, independent integrity checks, full-sample candidate scan, task-specific analysis, and AI review of structured results and selected original-resolution windows. Require explicit scope on every completeness claim.

Report payload integrity, requested-range coverage, frame association, timing correspondence, analysis capability separately. Screenshot capture should be attempted when safe, but screenshot failure must not invalidate independently verified data. Unknown range or association remains UNVERIFIED rather than becoming INCOMPLETE.

Provide an audited sparse-event escalation path after automatic threshold refusal. Candidate localization is not pulse counting; local threshold validation and sampling sufficiency must pass before further claims. Local success cannot establish record-wide absence or stability.

Regression acceptance should cover valid screen/descriptor count differences; short, overlapping, missing, and reordered segments; width and byte-order errors; frame/configuration changes; screenshot unavailability; sparse events; undersampling; capture-boundary pulses; and truncated analysis output. Each case must test both permitted and prohibited claims.

## Sources
- Siglent SDS800X HD Programming Guide EN11G: https://siglentna.com/wp-content/uploads/dlm_uploads/2024/09/SDS800XHD_Series_ProgrammingGuide_EN11G.pdf — memory management, maximum depth, acquisition type.
- Siglent SDS Programming Guide EN11F: https://siglentna.com/wp-content/uploads/dlm_uploads/2024/03/ProgrammingGuide_EN11F.pdf — ACQuire:POINts describes current on-screen waveform points.
- Tektronix XYZs of Oscilloscopes: https://download.tek.com/document/XYZs-of-Oscilloscopes_Primer_03W-8605-8.pdf — sampling, reconstruction, aliasing, record length; general principles, not Siglent command semantics.
- PyVISA Reading and Writing Values: https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html — binary framing, data type, endianness, advertised length, and termination.

## Implementation Checklist

Implementation started after this research contract; every item below is tracked here.

- [x] **Screenshot evidence** — bounded headerless PNG reader (`scripts/screenshot_capture.py`) with container/decode separation, opt-in `capture_scope.py --screenshot` on the same socket after payloads, offline tests. Committed in `b21c7bb`.
- [x] **Five-axis evidence report** — `scripts/waveform_evidence.py` reporting `payload_integrity` (descriptor scope only), `requested_range_coverage` (explicit half-open descriptor sample range, default `UNVERIFIED`), `frame_association` (always `UNVERIFIED`), `time_correspondence` (always `UNVERIFIED`), and `analysis_capability` (existing verdict/claims/calibration plus an explicit sampling requirement; a refused verdict or a contradicted sampling requirement keeps the axis `UNVERIFIED`, and a missing requirement marks the result not task-ready). Axis statuses are restricted to `COMPLETE`/`INCOMPLETE`/`INVALID`/`UNVERIFIED`/`UNSUPPORTED`; failures are attributed to an `input`, `load`, `analysis`, or `output` stage so an input, analysis or output problem never becomes a load failure and never downgrades an already-validated payload. A `CAPTURE_NOT_COMPLETE` load stays `UNVERIFIED` because it also covers permission, connection and unknown manifest errors. Output is written only to reserved non-existing paths (never through symlinks or hardlinks), `--out` and `--svg` must differ and stay outside the capture, and the JSON budget is a hard bound. Offline tests cover all of it.
- [x] **Sparse candidate review entry** — after a `REFUSED` verdict, preserve the refusal and expose the existing candidate excursions with bounded original-resolution windows, per-window SHA-256 and sample-index binding, explicit selection policy, and an optional stdlib raw-code SVG whose markers are the raw samples and whose connecting line is labelled as a display aid only. Windows and their `observations` are trimmed together to a hard JSON budget, and the SVG is rendered after trimming from the surviving windows.
- [x] **Review documentation** — `references/waveform-evidence.md` describes the five axes, the failure stages, prohibited claims, conflicts, output safety and the bounded review protocol; the `verdict` gate in `SKILL.md` routes a refusal to the candidate review instead of hand-rolled thresholds.
- [ ] **Instrument validation** — the evidence package has not been exercised on a physical SDS824X HD; all evidence statuses remain offline/documented until it is. **Not started.**
