# Waveform Regime Analysis Design

- **Status**: Completed
- **Created**: 2026-10-28
- **Target Files**: `skills/siglent-sds800xhd-control/scripts/waveform_analysis.py`, `scripts/analyze_waveform.py`, `scripts/test_waveform_analysis.py`, `SKILL.md`, `references/screenshot-and-waveform.md`

## 1. Intent

Add a read-only analysis layer that quickly divides a full-resolution pulse/edge record into stable measurement regimes, especially regular waveform phase changes such as 100 Hz followed by 200 Hz. It must preserve per-cycle evidence and highlight anomalies so an agent does not overlook short irregularities or treat a whole-record statistic as the full explanation.

## 2. User Decisions (frozen)

- Default behavior autonomously selects supported per-cycle measurements that show reliable sustained stage-change evidence; users may explicitly override the selected features.
- A confirmed transition needs at least 5 complete cycles on each side by default; this minimum is configurable.
- A smooth drift/ramp is reported within one regime as trend evidence plus an unresolved drift annotation; it must not be forced into artificial step regimes in v1.
- `measures.selected` means features that actually support one or more accepted regime boundaries. Regime summaries still report all available measurements, including stable ones.

## 3. Goals and Constraints

- Derive cycles/regimes only from exhaustive original-resolution edge and pulse structure; never use M4 previews, stride, window counts, or whole-record aggregates as segmentation input.
- Preserve existing `structure` and `events` contracts. Add an independent Python API and `regimes` CLI command.
- Treat isolated abnormal cycles as anomalies, not regimes. A short candidate phase below support remains unresolved; never silently merge or assert it as stable.
- Code-domain measures remain available. Voltage-domain measures require `calibration.status == VALID`; explicitly report requested-but-unavailable measurements.
- No instrument control, hardware connection, new third-party dependencies, causal diagnosis, or missing-edge/sample inference.
- Use existing integrity statuses for primary artifact/overall completeness: `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, `UNSUPPORTED`. Local labels such as `transition_uncertain` and `drift_trend` are classifications, not replacements for integrity status.

## 4. Cycle Construction and Supported Measurements

Build a cycle from consecutive complete rising-edge/high-pulse starts. Use sample-grid values for deterministic, reproducible feature extraction and report `feature_basis = sample_grid`; do not substitute interpolated boundary widths. A cycle is complete only when its pulse and both bounding rising-edge starts are supported by complete in-record evidence. Incomplete first/last pulses do not produce complete cycles.

Initial supported measures where evidence permits:

- `period_s`, `frequency_hz` (reciprocal representations; auto mode must not count both as independent evidence)
- `high_width_s`, `low_width_s`, `duty_cycle`
- `peak_code`, `min_code`, `peak_to_peak_code`
- Calibrated voltage equivalents only with valid voltage calibration

Validate requested names and prerequisites. Explicitly report `selected`, `rejected`, and `unavailable` features with reason codes. Unknown names raise a structured `MEASURE_UNSUPPORTED` analysis error; requested measures must never be silently dropped.

## 5. Segmentation Semantics

- Use a deterministic robust change-point procedure over ordered per-cycle measurements (implementation may use rolling robust medians/MAD or an equivalent NumPy-only method).
- Each accepted step boundary must satisfy configured absolute/relative effect tolerance and have at least `min_cycles_per_side` complete cycles on both sides (default 5).
- Multi-feature acceptance is an explicit OR: at least one selected measurement can support a boundary. Report support and disagreement per feature; do not hide a composite score.
- A single isolated cycle outlier is an anomaly and cannot alone create a regime. Anomaly threshold default is robust modified-z `3.5`, configurable and recorded.
- Quantization must bound detectable changes. If one-sample feature resolution exceeds requested tolerance, mark that measure rejected/unresolved with `resolution_below_tolerance`; do not split regimes on sample quantization noise.
- A phase shorter than minimum support is an `unresolved` candidate, not silently swallowed as normal or asserted as stable.
- For a smooth drift, retain one regime, report trend slope and fit quality, and add `unresolved.kind = drift_trend`; no discrete transition is emitted.
- Detect transition uncertainty as the full contiguous interval of near-equivalent change-point evidence, expanded by configured `transition_margin_cycles`. Cycles in that interval are assigned `transition_uncertain`, excluded from stable regime cycle counts, and listed in coverage.
- A single regime with no transitions still reports summaries for all usable measures. `measures.selected` may be empty; measures remain present under the regime summary.

## 6. Proposed CLI Shape

```text
python3 scripts/analyze_waveform.py regimes \
  --capture /path/to/capture --channel C4 \
  --threshold-codes 20 35 \
  --measures auto \
  --min-cycles-per-side 5 \
  --relative-tolerance 0.08 \
  --absolute-tolerance 0 \
  --transition-margin-cycles 1 \
  --anomaly-z 3.5 \
  --max-edges 20000 --max-cycles 5000
```

`--measures auto` is the default. Explicit overrides may use a comma-separated supported list such as `--measures duty_cycle,high_width_s`. Auto-selection must report selected features, stable/rejected features, unavailable features, and the evidence/reason for each. Every effective control, detector version, and source SHA-256 is included in output.

## 7. Output Contract

- `regimes[]`: stable ID/index, half-open sample/time range, stable complete-cycle count, status, summaries for all usable measures (median/MAD/min/max/trend), source pulse/edge references, neighbor transition IDs.
- `transitions[]`: left/right regime IDs, boundary and uncertainty range, changed measures, robust before/after values, effect size/configured threshold, per-measure support/disagreement, confidence/status, source cycle IDs.
- `cycles[]` (bounded): per-cycle start/end sample/time, all calculated features, source pulse/edge IDs, anomaly flags, regime/transition assignment.
- `anomalies[]` (bounded): cycle and measure, observed value, regime/local reference, signed residual/score, source references, sample/time.
- `unresolved[]`: short candidate phases, drift trends, ambiguous boundaries, unsupported measures, incomplete boundary cycles, and reasons.
- `measures`: selected (boundary-supporting), evaluated (all usable), rejected, unavailable; every item has a reason/evidence reference.
- `coverage`: source hash, raw full-resolution flag, stride=1, point/edge/pulse/cycle counts, complete/incomplete/transition-uncertain cycles, budgets, output completeness and limitations.
- Edge budget overrun propagates `UNVERIFIED` and lower-bound completeness to the entire segmentation; a prefix must never be described as a complete partition.
- JSON output budget must truncate `cycles`, `anomalies`, `transitions`, `unresolved`, and `regimes` lists explicitly (`items_truncated`, `items_complete`, authoritative count/returned fields) rather than raising a generic error. Large lists are bounded in order cycles, anomalies, transitions, unresolved, then regimes, preserving compact regime summaries as long as possible. References from retained records remain resolvable; records whose referenced details were omitted carry sample/time and IDs inline.

## 8. Acceptance Criteria

- A synthetic 100 Hz then 200 Hz record produces two regimes with correct period/frequency summaries and a traceable transition.
- A single isolated period outlier remains an anomaly and does not split a stable regime.
- Auto mode detects a sustained duty/high-width change with stable period, identifies the supporting feature, and reports frequency as stable/rejected for segmentation while retaining it in regime summaries.
- Explicit single- and multi-measure overrides work; unknown names error; non-valid voltage calibration makes voltage features unavailable while code measures continue.
- A smooth monotonic ramp yields one regime, a trend summary, and unresolved drift evidence, not fabricated step regimes.
- Five cycles on each side is enforced by default and configurable. A shorter intermediate phase is unresolved. Tests include under-threshold, exact-threshold, and above-threshold cases.
- Transition uncertainty cycles are explicit and excluded from stable regime cycle counts; phase counts reconcile with coverage (stable + transition + unresolved + boundary cycles = observed cycles).
- Capture-boundary partial cycles remain incomplete and do not form measurements.
- Quantization-limited changes are unresolved/rejected, not fragmented into false stages.
- Edge and JSON budgets produce explicit unverified/truncated status; bounded output does not throw merely because new sections are large.
- Results are invariant to preview/stride settings and include source hash, selected measures/reasons, thresholds, algorithm parameters, sample/time ranges, and source pulse/edge references.
- Existing waveform-analysis tests, protocol tests, compilation, Skill validation, and CLI discovery all pass.

## 9. Implementation Partition and Verification

1. `waveform_analysis.py` (one owner): cycle extraction, feature registry/auto-selection, robust step/drift/anomaly detection, output schema, and `bound_json` support for regime sections.
2. `analyze_waveform.py` (separate owner after API signature freezes): CLI parameters and dispatch.
3. `test_waveform_analysis.py` (separate owner after behavior freezes): synthetic feature transitions, outliers, drift, min-cycle support, calibration, quantization, boundary, and limits.
4. `SKILL.md` + `references/screenshot-and-waveform.md` (separate doc owner after schema freezes): agent workflow and interpretation limits; do not update READMEs because they do not enumerate analyzer commands.
5. Parent integrates, audits all fields and boundary math, runs all tests/checks, and commits English conventional commit.

## 10. Approval

- [x] User approved this design, including auto feature choice, five-cycle support, and drift as trend + unresolved evidence.
- [x] Independent builder feasibility review completed; implementation risks incorporated above.
- [x] Core API and CLI implemented; synthetic tests/documentation added.
- [x] Offline tests, compilation, Skill validation, and CLI discovery pass.
- [x] Final API audit and commit.
