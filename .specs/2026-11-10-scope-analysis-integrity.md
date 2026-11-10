# Spec Contract: Scope Analysis Integrity Gate

- **Created**: 2026-11-10
- **Status**: Completed
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/SKILL.md`; `.specs/2026-11-10-scope-analysis-integrity.md`. No script changed.

## 1. Core Objective

Make the pre-analysis gate of the SDS800X HD Skill state, in one bounded section,
what must be recorded before a waveform conclusion: the instrument's own readings
or their unavailability, the channel-map declaration checked against wiring, the
manifest/`inspect` completeness proof, the time basis, pulse-boundary semantics,
threshold placement, and drive/reception evidence. The gate must not allow a
missing instrument statistic to block an offline conclusion the samples support,
and must not allow an unverified statistic comparison to be reported as agreement.

A capture manifest can carry a `channel_mapping` field. The manifest records a
declaration only, and the caller must cross-check it against wiring and user evidence. `inspect` does not
currently emit the mapping, which does not block the workflow check; the caller
compares the manifest declaration directly.

`inspect` already reports the integrity entry this gate needs: the validated
full-record point count, `integrity.status`, `integrity.segments_verified`, and
the descriptor-derived `sampling.interval_s`, `sampling.rate_hz`, and
`sampling.origin_s`. No analyzer or script change is required, and no test is
added for unchanged code.

## 2. Hard Constraints

- [x] **C-01**: A missing instrument readout (unsafe or undocumented query, or no readout exists) is recorded as `unavailable` with the unknown metadata; it must not block evidence-based offline analysis, and it blocks only statistical-consistency claims and inferences beyond the offline evidence.
- [x] **C-02**: An instrument statistic and an analyzer statistic are compared only on the same capture, channel, measurement window, gating, threshold, and count definition; any unknown or differing condition keeps the comparison `UNVERIFIED`.
- [x] **C-03**: A manifest `channel_mapping`, when present, is a declaration and must be cross-checked against wiring, probe, and the user's channel description before samples are attributed; no manifest or tool output substitutes for that check.
- [x] **C-04**: Analysis reads the complete record through the manifest and `inspect` (`COMPLETE`, declared full-record points, segment count); globbing `*.bin` and treating one segment payload as the record are forbidden.
- [x] **C-05**: Analysis time comes from `sampling.origin_s` / `sampling.interval_s` and CLI time windows, not filenames, segment offsets, or a guessed rate.
- [x] **C-06**: A rising edge is not a complete positive pulse; boundary pulses are reported separately and differing quantities are never called agreement.
- [x] **C-07**: Hysteresis thresholds sit outside the noise band; a local minimum or maximum is not crossing evidence.
- [x] **C-08**: A received-frame claim needs frame decode plus protocol context; an active-drive claim needs independent electrical evidence; a decode does not prove drive, and a level reading does not prove reception.
- [x] **C-09**: Keep the repair procedural, preserve scripts and raw captures, and perform verification offline.

## 3. Acceptance Criteria

- [x] **AC-01**: `SKILL.md` contains one "Pre-analysis evidence gate" section as the single authority for measurement provenance, channel identity, record completeness, analysis time, pulse-boundary semantics, threshold placement, and drive/reception claims, reusing the existing threshold and verdict/structure rules by reference.
- [x] **AC-02**: The gate ordering requires `inspect` before the `verdict` conclusion, and no text still calls `verdict` the first analyzer action.
- [x] **AC-03**: The readout rule permits an offline conclusion on captured samples when the instrument readout is unavailable and marks only the statistical comparison `UNVERIFIED`; a readout is not a prerequisite.
- [x] **AC-04**: The statistics rule names all six shared conditions (capture, channel, window, gating, threshold, count definition) and requires `UNVERIFIED` when any is unknown or different.
- [x] **AC-05**: The MISO rule separates protocol reception (frame decode plus protocol context) from active drive (independent electrical evidence) and states that decode does not prove drive.
- [x] **AC-06**: The channel-map rule accepts a manifest `channel_mapping` as a declaration, requires wiring/user cross-check, and does not depend on `inspect` emitting the mapping.
- [x] **AC-07**: This specification follows the anchor template (Hard Constraints, Acceptance Criteria, Verification Log), records audited acceptance, and distinguishes offline verification from hardware verification.
- [x] **AC-08**: Offline validation passes after the wording changes: `quick_validate.py` reports the Skill valid, and discovery still lists the unchanged Skill set.

## 4. Verification Log

- [x] `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/siglent-sds800xhd-control` → `Skill is valid!` (rerun after the final wording edit).
- [x] `npx skills@latest add . --list` → `Found 5 skills`; `siglent-sds800xhd-control` present with unchanged description (run in this task before the wording-only edits).
- [x] Read-only inspection of `scripts/analyze_waveform.py` confirmed `inspect` already emits `capture.points`, `integrity.status`, `integrity.segments_verified`, and `sampling.interval_s`; no code change needed.
- [x] Main-agent acceptance audit: reviewed the complete Skill diff, checked `inspect` fields and time-window/pulse-boundary implementation, and verified C-01 through C-09 and AC-01 through AC-08 against the final text.
- [x] `python3 -m pytest -q skills/siglent-sds800xhd-control/scripts/test_waveform_analysis.py skills/siglent-sds800xhd-control/scripts/test_verdict_gate.py` → `79 passed`.
- [x] Read-only `inspect` on an existing local capture confirmed `COMPLETE`, full-record points, all declared segments verified, descriptor time origin/interval, and explicit unverified voltage-calibration status. No instrument connection was opened.
- [x] `git diff --check` → passed.

## 5. Limits

The repair enforces the agent workflow through the Skill contract; it adds no
mechanical CLI gate. Existing instrument-statistics automation and electrical
or protocol validation were not exercised on hardware. Unavailable or
incomparable statistics remain `UNVERIFIED`.
