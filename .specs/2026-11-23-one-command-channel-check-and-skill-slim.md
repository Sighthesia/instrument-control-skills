# Spec Contract: One-Command Channel Check, Bidirectional Blind-Spot Guard, and SKILL.md Slimming

- **Created**: 2026-11-23
- **Status**: Completed and accepted offline (2026-11-23). `channel_snapshot.py` sample-probe/source-readback and `screenshot_capture.py` remain `documented` + offline-tested pending a physical SDS824X HD run.
- **Target Files/Modules**:
  - `skills/siglent-sds800xhd-control/scripts/channel_snapshot.py`
  - `skills/siglent-sds800xhd-control/scripts/screenshot_capture.py`
  - `skills/siglent-sds800xhd-control/scripts/test_channel_snapshot.py`
  - `skills/siglent-sds800xhd-control/scripts/test_screenshot_capture.py`
  - `skills/siglent-sds800xhd-control/SKILL.md`
  - `skills/siglent-sds800xhd-control/references/signal-discovery-and-measurement.md`
  - `skills/siglent-sds800xhd-control/references/screenshot-and-waveform.md`
  - `skills/siglent-sds800xhd-control/references/programming-guide.md`

## 1. Core Objective

Close both halves of the oscilloscope misdiagnosis failure mode in one default
entry point (`scripts/channel_snapshot.py`) and slim `SKILL.md` into an
executable skeleton:

1. **Screenshot-only blind spot**: AI guesses "no signal" from a PNG or the
   single-source measurement panel.
2. **Local-number blind spot**: AI skips visual context or reads a tiny local
   slice of a long record and declares "flat" or "healthy" without checking
   coverage or full-screen shape.
3. **Single-pass confirmation bias**: AI concludes a hardware/grounding fault
   after one observation instead of running a second confirmation capture.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Never alter acquisition state (`RUN`/`STOP`/`TRMD`/`ARM`),
      trigger settings, vertical/horizontal settings, or `:MEASure:SIMPle:SOURce`
      in `channel_snapshot.py`.
- [x] **C-02**: Sample probing uses `WAV:SOUR/INT/STAR/POIN/PRE?/DATA?` only
      when `SAST? == Stop` and `SWITch == ON`, and is disabled completely by
      `--strict-readonly` (0-write query-only mode). Never silently stop a
      `Ready`/`Run`/`Roll` scope.
- [x] **C-03**: Every sample probe must report explicit record coverage
      (`sampled_points`, `total_points`, `coverage_ratio`, `coverage_mode`:
      `FULL_RECORD` vs `PARTIAL_SLICES`). `PARTIAL_SLICES` with flat codes must
      never be labelled "no signal" or "flat across record".
- [x] **C-04**: Optional screenshot (`--screenshot <png>` or `--out-dir <dir>`)
      always runs **last** on the same session, only if no earlier transport
      failure occurred, and is always tagged `QUALITATIVE_ONLY`. When omitted,
      the snapshot explicitly records `visual_context.status = "NOT_CAPTURED"`.
- [x] **C-05**: Keep `SKILL.md` concise (target `<= 120` lines) without losing
      any authoritative contract: move detailed history, formulas, and long
      script descriptions into `references/`.
- [x] **C-06**: Preserve existing `capture_scope.py` and
      `oscilloscope-waveform-analysis` compatibility and existing `screenshot_capture.py`
      JSON contract fields.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: `channel_snapshot.py` reads horizontal context (`TIM:SCAL?`,
      `ACQ:SRAT?`, `ACQ:POIN?`) alongside acquisition/trigger/per-channel state
      and `:MEASure:SIMPle` source-verified readings.
- [x] **AC-02**: When `SAST? == Stop` and `--strict-readonly` is not set,
      `channel_snapshot.py` probes each requested channel with `SWITch == ON`
      using `WAV:PRE?` + bounded raw slices (full read when `total_points <= budget`,
      otherwise 3 slices: head / middle / tail), computes `code_min`, `code_max`,
      `code_span`, clipping against signed width bounds (`-128..127` BYTE or
      `-32768..32767` WORD), and `activity_hint` (`ACTIVE_CODES`,
      `FLAT_IN_FULL_RECORD`, `FLAT_IN_SAMPLED_SLICES_ONLY`, `CLIPPED`,
      `UNVERIFIED`).
- [x] **AC-03**: When `SAST? != Stop` (e.g. `Ready`/`Run`/`Roll`), sample probe
      is skipped without stopping the scope, reported as `LIVE_NOT_STOPPED`, and
      `next_actions` instructs a single-shot capture before concluding.
- [x] **AC-04**: `channel_snapshot.py` supports `--strict-readonly` (no `WAV:*`
      writes, identical 0-write guarantee), `--slice-points`, `--screenshot <png>`,
      and `--out-dir <dir>` (writes `snapshot.json` and `screen.png`). When
      screenshot is not requested, `visual_context.status == "NOT_CAPTURED"`.
- [x] **AC-05**: `channel_snapshot.py` emits actionable `next_actions` covering:
      `PARTIAL_SLICES` flat warning, `NOT_CAPTURED` visual-context reminder,
      `CLIPPED` V/div adjustment, `LIVE_NOT_STOPPED` trigger-capture prompt,
      and `PKPK == 0` / `FLAT_IN_FULL_RECORD` apparent-zero triage.
- [x] **AC-06**: `screenshot_capture.py` CLI summary / JSON includes explicit
      qualitative-only warning and points to `channel_snapshot.py` for
      per-channel evidence without breaking existing JSON keys.
- [x] **AC-07**: `SKILL.md` is slimmed to `<= 120` lines and puts up front:
      (a) `channel_snapshot.py --out-dir` as the default one-command check,
      (b) bidirectional blind-spot prohibition (neither PNG-only nor
      partial-slice/number-only), (c) Second-Capture Rule before hardware/fault
      claims, and (d) 3-line Evidence Gate before reporting faults. Displaced
      details live in `references/` with working links.
- [x] **AC-08**: Offline tests cover: full-record vs 3-slice `PARTIAL_SLICES`
      coverage, clipping detection, `LIVE_NOT_STOPPED` (no stop sent),
      `--strict-readonly` (query-only command log), `--out-dir` / `--screenshot`
      last-step ordering + skipped on transport failure, `visual_context:
      NOT_CAPTURED`, `next_actions` generation, and `screenshot_capture.py`
      qualitative-only reminder. All Siglent tests, `oscilloscope-waveform-analysis`
      tests, `quick_validate.py`, and `npx skills@latest add . --list` pass.

## 4. Execution & Verification Log

- [x] Spec written
- [x] Implementation (`channel_snapshot.py`, `screenshot_capture.py`, tests: +20 offline tests)
- [x] `SKILL.md` slimming (311 -> 96 lines) + `references/` consolidation
- [x] Acceptance audit + full validation (209 Siglent + 241 analysis tests, `quick_validate.py`, `npx skills@latest add . --list` = 9/9, `git diff --check`)
