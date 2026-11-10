# Spec Contract: Scope Analysis Integrity Gate

- **Created**: 2026-11-10
- **Status**: Completed — revised after independent review and main-agent acceptance
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/SKILL.md`; `skills/siglent-sds800xhd-control/scripts/capture_scope.py`; `skills/siglent-sds800xhd-control/scripts/test_scope_protocol.py`; `skills/siglent-sds800xhd-control/references/signal-discovery-and-measurement.md`; `skills/siglent-sds800xhd-control/references/command-reference.md`; `.specs/2026-11-10-scope-analysis-integrity.md`.

## 1. Core Objective

Make the pre-analysis gate of the SDS800X HD Skill state, in one bounded section,
what must be recorded before a waveform conclusion: the instrument's own readings
or their unavailability, the channel-map declaration checked against wiring, the
manifest/`inspect` completeness proof, the time basis, pulse-boundary semantics,
threshold placement, and drive/reception evidence. The gate must not allow a
missing instrument statistic to block an offline conclusion the samples support,
and must not allow an unverified statistic comparison to be reported as agreement.

`capture_scope.py` previously wrote a fixed `channel_mapping`
(`C1=ENABLE`, `C2=nFAULT`, `C3=HOC`, `C4=P4.1/CMP`) into every manifest, so the
field looked like per-capture wiring evidence while carrying none. The capture CLI
now records a mapping only when the caller states one with
`--channel-mapping C1=ENABLE,C4=MISO`, and always records its provenance as
`channel_mapping_source` (`user-supplied` or `unknown`). The scope exposes no
channel-name readback this Skill queries, so no script output can confirm wiring;
the gate treats any mapping as a declaration to be cross-checked, and the exact
legacy constant as an unverified template from older manifests.

`inspect` reports the integrity entry this gate needs: the validated full-record
point count, `integrity.status`, `integrity.segments_verified`, and the
descriptor-derived `sampling.interval_s`, `sampling.rate_hz`, and
`sampling.origin_s`. It does not report the scope-side record length, which stays
in `results[].frame_report.scope_record.points`; `inspect` skips that comparison
when the field is absent, so the gate names the field and the fallback statement.

## 2. Hard Constraints

- [x] **C-01**: A missing instrument readout (unsafe or undocumented query, or no readout exists) is recorded as `unavailable` with the unknown metadata; it must not block evidence-based offline analysis, and it blocks only statistical-consistency claims and inferences beyond the offline evidence.
- [x] **C-02**: An instrument statistic and an analyzer statistic are compared only on the same capture, channel, measurement window, gating, threshold, and count definition. Each condition is classified as matched, `unknown`, `not_exposed`, or `not_applicable`; `not_exposed` records only that the interfaces and documents this Skill records expose no control for the condition, never that the instrument has none, so the behaviour behind it stays `UNVERIFIED`; `not_applicable` describes the quantity. Neither classification supplies a known value or relaxes a differing threshold, window, or count definition into agreement. Any `unknown` or differing condition keeps the comparison `UNVERIFIED`.
- [x] **C-03**: A manifest `channel_mapping` is a declaration with a recorded source and must be cross-checked against wiring, probe, and the user's channel description before samples are attributed. The fixed constant written by earlier `capture_scope.py` versions is an unverified template, not a per-capture declaration, and no manifest or tool output substitutes for the cross-check.
- [x] **C-04**: Analysis reads the complete record through the manifest and `inspect` (`COMPLETE`, declared full-record points, segment count) and requires `results[].frame_report.status = COMPLETE` as well: a `COMPLETE` `segment_report` proves only segment continuity and hashes, while an `INCOMPLETE` frame means the scope record, the WAVEDESC record, and the download disagree. When `frame_report.scope_record.points` is absent, the analysis states that the scope-side record length was not independently verified. Globbing `*.bin` and treating one segment payload as the record are forbidden.
- [x] **C-05**: Analysis time comes from `sampling.origin_s` / `sampling.interval_s` and CLI time windows, not filenames, segment offsets, or a guessed rate.
- [x] **C-06**: A rising edge is not a complete positive pulse; `pulses.count`, `pulses.complete_count`, `pulses.incomplete_count`, and `pulses.status` are reported together, and `PPULSES`/`NPULSES` is compared only after confirming what the instrument counts.
- [x] **C-07**: Hysteresis thresholds sit outside the noise band; a local minimum or maximum is not crossing evidence.
- [x] **C-08**: A received-frame claim needs frame decode plus protocol context; an active-drive claim needs independent electrical evidence; a decode does not prove drive, and a level reading does not prove reception.
- [x] **C-09**: Preserve raw captures and the existing instrument safety boundaries. Validate the repair offline; separately authorized hardware observations retain their original evidence and integrity status.

## 3. Acceptance Criteria

- [x] **AC-01**: `SKILL.md` contains one "Pre-analysis evidence gate" section as the single authority for measurement provenance, channel identity, record completeness, analysis time, pulse-boundary semantics, threshold placement, and drive/reception claims, reusing the existing threshold and verdict/structure rules by reference.
- [x] **AC-02**: The gate ordering requires `inspect` before the `verdict` conclusion, and no text still calls `verdict` the first analyzer action.
- [x] **AC-03**: The readout rule permits an offline conclusion on captured samples when the instrument readout is unavailable and marks only the statistical comparison `UNVERIFIED`; a readout is not a prerequisite. It requires the readout's source channel, threshold source/type/levels, and display timebase state to be recorded (`:MEASure:SIMPle:SOURce?`, `:MEASure:THReshold:SOURce?`, `:MEASure:THReshold:TYPE?`, `:MEASure:THReshold:PERCent?`/`:MEASure:THReshold:ABSolute?`) rather than assumed, and states that a differing measurement and queried threshold source means the measurement channel's thresholds were not read, leaving the comparison `UNVERIFIED` without re-writing the threshold source.
- [x] **AC-04**: The statistics rule names all six shared conditions (capture, channel, window, gating, threshold, count definition) and defines the `unknown` / `not_exposed` / `not_applicable` classification, limiting `not_exposed` to what the recorded interfaces and documents expose, requiring `UNVERIFIED` for any `unknown` or differing condition, and leaving the unobserved measurement behaviour behind a `not_exposed` condition `UNVERIFIED`.
- [x] **AC-05**: The MISO rule separates protocol reception (frame decode plus protocol context) from active drive (independent electrical evidence) and states that decode does not prove drive.
- [x] **AC-06**: The channel-map rule treats a manifest `channel_mapping` as a sourced declaration, names the legacy fixed constant as an unverified template, requires wiring/user cross-check, and does not depend on `inspect` emitting the mapping. `capture_scope.py` no longer writes a default mapping: `--channel-mapping` records the caller's declaration with `channel_mapping_source: user-supplied`, and an omitted flag records `null`/`unknown`.
- [x] **AC-07**: An unresolved signal name blocks only functional or protocol attribution; physical-channel analysis (`C2`) and same-channel statistics proceed with the signal name `UNVERIFIED`, and the `UNVERIFIED` stop applies only to a missing or non-`COMPLETE` `inspect` integrity record.
- [x] **AC-08**: The gate records the display timebase state (`TIMebase:SCALe`, `TIMebase:DELay`, `TIMebase:REFerence:POSition`) as display configuration and records the range a readout evaluates as separate evidence; an unestablished evaluation range stays `unknown` and is never inferred from, or defaulted equal to, the display window. The display state is not proof of measurement gating: the only gating control the Skill records is `:FUNCtion<x>:INTegrate:GATE` (math integrate), so basic-measurement gating is `not_exposed` only in the sense that the recorded interfaces and documents expose none, and the measurement's own gating behaviour stays `UNVERIFIED`. Acceptance verifies that the contract preserves these unknowns; it does not claim a hardware-verified evaluation range or gating rule.
- [x] **AC-09**: The completeness rule names `results[].frame_report.scope_record.points` as the declared full record, requires `frame_report.status = COMPLETE` in addition to `segment_report` completeness, and requires a statement that the scope length was not independently verified when the field is absent.
- [x] **AC-10**: The pulse rule names `pulses.complete_count`, `pulses.incomplete_count`, `pulses.count`, and `pulses.status`, and requires confirming the instrument's `PPULSES`/`NPULSES` definition before any comparison.
- [x] **AC-11**: This specification follows the anchor template (Hard Constraints, Acceptance Criteria, Verification Log), records audited acceptance, and distinguishes offline verification from hardware verification.
- [x] **AC-12**: `python3 -m pytest -q` over `test_scope_protocol.py`, `test_waveform_analysis.py`, and `test_verdict_gate.py` passes (`137 passed, 5 subtests passed`), and `quick_validate.py` reports `Skill is valid!`. The main agent also re-ran `npx skills@latest add . --list` and confirmed the unchanged five-directory Skill set.

## 4. Verification Log

- [x] `python3 -m pytest -q skills/siglent-sds800xhd-control/scripts/test_scope_protocol.py` → `58 passed, 5 subtests passed`; four new tests cover the mapping default (`null`/`unknown`), an explicit `--channel-mapping` declaration, rejection of malformed entries, and the CLI flag.
- [x] `python3 -m pytest -q skills/siglent-sds800xhd-control/scripts/test_scope_protocol.py skills/siglent-sds800xhd-control/scripts/test_waveform_analysis.py skills/siglent-sds800xhd-control/scripts/test_verdict_gate.py` → `137 passed, 5 subtests passed` (final pass, all three suites together).
- [x] `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/siglent-sds800xhd-control` → `Skill is valid!` (re-run after the review wording fixes).
- [x] `npx skills@latest add . --list` → `Found 5 skills`, re-run by the main agent after the changes; the discovered set matches the directories under `skills/`.
- [x] Read-only inspection of `scripts/analyze_waveform.py` confirmed `inspect` emits `capture.points`, `integrity.status`, `integrity.segments_verified`, and `sampling.interval_s`. In `scripts/waveform_analysis.py`, `_select_result` requires `frame_report.status = COMPLETE` and `segment_report.status = COMPLETE` before any capture is used, `load_capture` compares `frame_report.scope_record.points` (plus the WAVEDESC, downloaded and segment point counts) against the WAVEDESC count and skips only fields that are `None`, and `integrity.status = COMPLETE` is reported only on the path after those checks have run.
- [x] Read-only inspection of `scripts/waveform_analysis.py` confirmed `pulses.count`, `complete_count`, `incomplete_count`, and `status` (`COMPLETE` / `COMPLETE_WITH_INCOMPLETE_BOUNDARY_PULSES`).
- [x] Manual evidence checked locally against `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` (git-ignored, read-only, no instrument session): TOC places `:MEASure:SIMPle:SOURce` at printed p. 182 and `:MEASure:THReshold:SOURce`/`TYPE`/`ABSolute`/`PERCent` at printed pp. 183-185; the `:MEASure:THReshold:SOURce` page documents setting or querying the threshold source with `{C<n>|Z<n>|F<x>|ZF<x>|M<m>|ZM<m>|REF<r>}` and zoom validity, and does not describe how a threshold source relates to an active measurement's thresholding. The Skill therefore records the two sources separately and makes no causal claim about a measurement's thresholds.
- [x] Main-agent acceptance: reviewed the six-file diff, checked the mapping CLI and its regression coverage, and re-ran the three focused suites (`137 passed, 5 subtests passed`), Skill validation, discovery, and `git diff --check`. Corrected pulse-count comparison so neither `count` nor `complete_count` is assumed equivalent to the instrument's undocumented boundary rule.
- [x] `git diff --check` → passed.

## 5. Limits

The repair enforces the agent workflow through the Skill contract; it adds no
mechanical CLI gate and the analyzer does not read `channel_mapping`. Channel
identity remains a caller statement: the scope has no name readback in this Skill,
so `user-supplied` records provenance, not verification. The threshold-context
section records what the documented pages state (the queries and their accepted
source values) and claims nothing about which thresholds an active measurement
uses; that interaction is unrecorded, so a differing measurement and threshold
source stays `UNVERIFIED`. The evaluation window of a basic measurement and its
gating remain unestablished here; AC-08 verifies the explicit handling of those
unknowns. Hardware readouts were collected separately, but their equivalence to
offline statistics was not established. Unavailable or incomparable statistics
remain `UNVERIFIED`.
