# `analyze_waveform.py` — subcommands, options, outputs

Load this reference when choosing a subcommand, picking its options, or reading
its report. Every subcommand takes one capture, prints one JSON document (or
writes it with `--out`), and returns exit code `0`, or `2` with an error
envelope. Nothing here reconnects to an instrument, writes to a capture
directory, or reads a vendor manual.

```text
python3 scripts/analyze_waveform.py <subcommand> --capture <path> [subcommand options] [common options]
```

## Common options

| Option | Meaning |
|---|---|
| `--capture <path>` | required. A `waveform-bundle/v1` JSON, a legacy Siglent `manifest.json` or capture directory, a `.csv`, or a `.npz`. The format is auto-detected |
| `--channel <ch>` | channel to analyze (`C1`-`C4`, `CH1`-`CH4` or a bundle's own label). Required only when the source records more than one |
| `--sample-interval-s <s>` / `--sample-rate-hz <hz>` | the time base a CSV or NPZ file does not record; mutually exclusive, and refused when a recorded interval disagrees |
| `--units <volts\|code>` | units of a CSV or NPZ value column, overriding the file's own label |
| `--calibration <path>` | legacy Siglent only: an explicit calibration JSON, including the independent WORD scale bound to the merged record SHA-256 |
| `--vdiv <v>` / `--offset <v>` | legacy Siglent only: explicit probe-compensated physical overrides |
| `--revalidate-screen-range` | legacy Siglent only: re-derive a recorded screen-count comparison offline while keeping the original status and reasons |
| `--max-json-bytes <n>` | hard bound on the emitted JSON, default `262144`, maximum `4194304` |
| `--out <path>` | write the JSON outside the capture directory instead of stdout |

`--calibration`, `--vdiv` and `--offset` are rejected with
`CALIBRATION_INCONSISTENT` for a bundle, CSV or NPZ file: those formats
self-describe their scale, and silently ignoring a physical correction would let
the caller believe it was applied.

## Subcommand summary

| Subcommand | Question it answers | Thresholds | Fails closed on |
|---|---|---|---|
| `inspect` | What is this capture, and what scale does it claim? | not used | loader refusal only |
| `summarize` | Whole-record statistics and a coarse visual overview | not used | never: it scans the full record at chunk granularity |
| `verdict` | Can any level or timing claim be made at all? | derived, or explicit | derived thresholds that sit inside the noise band |
| `events` | Where do threshold crossings, runt pulses and long intervals occur? | required | the event scan budget |
| `structure` | What are the raw edges, high pulses, pulse clusters and the pulse-structure class? | required | the edge budget |
| `regimes` | Which per-cycle measurements are stable, when do they change, which cycles are anomalies? | required | the edge and cycle budgets |
| `window` | What are the raw samples around one index or time range? | not used | the window size limit |
| `ringing` | Is there edge overshoot, residual ringing, a ring frequency and a decay time in one window? | not used | window size and boundary conditions |

## inspect

The integrity and calibration entry point. It reports `integrity`, the
screen-range and time-correspondence blocks, the three-way calibration block,
`record_counts` (descriptor, downloaded, screen and record points, each stated
separately), `sampling`, and the `limitations` list. `inspect` is the integrity
entry, not analysis evidence: a `COMPLETE` payload here proves framing and counts
only.

## summarize

`--chunk-points` (default `1000000`), `--preview-buckets` (default `256`,
maximum `2000`).

Returns exact integer-code min/max/mean/RMS and nearest-rank percentiles — the
`_v` family when `calibration.status` is `VALID`, otherwise the `_code` family
plus `underlying_code_statistics` (min/max/mean/RMS only, no percentiles). The
two families are mutually exclusive. `preview` is an M4 sample labelled
`visualization_only_lossy` with `semantics: visualization_only_lossy` and
`value_domain` naming volts or code; it exists for display and must never stand
in for event detection or an absence claim. `summarize` accepts no time range, so
a whole-record percentile describes the whole record only.

## verdict

The first conclusion subcommand, and the only one that places its own
thresholds. `--threshold-codes LOW HIGH` or `--threshold-volts LOW HIGH` are
optional and mutually exclusive; when omitted the gate derives a pair from the
record's own level peaks and refuses if the split is not observable. Other
options: `--window-s` (default `0.05`), `--near-threshold-limit` (default
`0.02`), `--minimum-sigmas` (default `3.0`), `--chunk-points`.

Report blocks: `status` (`OBSERVED` or `REFUSED`), `domain`, `levels`,
`structure`, `sampling_risk`, `timing`, `windows`, `provenance`, and `claims`.

- `levels.low_v` / `levels.high_v` are the **level** voltages and come from the
  level peaks, not from the thresholds; `levels.threshold_v` publishes the
  threshold pair separately.
- `levels.threshold_evidence.placement` holds the sigma-clearance test.
  `near_threshold_fraction` is diagnostic only and never participates in the
  decision.
- `timing.dense_window_local_frequency_hz` is the median half period inside the
  densest windows. It is a window-local headline, never a record-wide frequency:
  a whole-frame statistic describes a record that spent most of its length
  elsewhere, and must not be used as a stage description.
- `timing.distribution_note` says whether the half-period population is bimodal;
  when it is, neither the median nor the mean describes the record.
- `refusal.code` and `refusal.candidate_excursions` are present only on a
  `REFUSED` verdict. The candidates are localized deviations, not levels.

`claims` is a closed vocabulary and is the whole point of the gate:
`can_claim` lists what this record supports, `cannot_claim` lists what it does
not, and `must_state` holds complete limitation sentences that a conclusion must
reproduce verbatim. `absolute_voltage_accuracy` leaves `cannot_claim` only when
the scale is `VALID` **and** `level_confirmed` is `PASS`.

## events

Requires `--threshold-codes LOW HIGH` or `--threshold-volts LOW HIGH`. Optional:
`--min-pulse-s`, `--expected-period-s`, `--period-tolerance` (default `0.1`),
`--chunk-points`, `--max-events-scanned` (default `10000`, maximum `20000`),
`--limit` (default `100`, maximum `100`), `--cursor`, `--start-time` /
`--end-time` (aliases of `--start-time-s` / `--end-time-s`).

Returns bounded pages of `rising` and `falling` threshold crossings (with a
linear-interpolated crossing time), `runt_pulse` events and `long_interval`
events, each with its own evidence window. `next_cursor` is a stateless cursor
bound to the record SHA-256; pass it back to continue. `events.total_is_lower_bound`
is `true` when the scan budget stopped the walk. A page is not a full-record
review: `page_truncated` and `scan_truncated` say which limit applied.

## structure

Requires a threshold pair. Optional: `--cluster-gap-s` (default is three times
the observed median pulse period, or eight sample intervals when no period
evidence exists), `--max-edges` (default `20000`, maximum `200000`),
`--chunk-points`, `--start-time` / `--end-time`.

This is the raw-edge fact layer. It scans every original sample
(`evidence.raw_scan = true`, `evidence.stride_used = 1`) and returns:

- `edges.items`: id, direction, sample, time, `before_code` / `after_code`, the
  same-direction interval, and time uncertainty.
- `pulses`: rising/falling pairs with start and end sample and time, width, code
  levels, thresholds, boundary flags and `status`. A pulse cut by the scan or
  capture boundary is reported as incomplete, never padded or dropped.
- `pulse_clusters`: pulses grouped by a low-level gap. Grouping is by gap only,
  so one physical pulse cut by an intermediate level stays a single cluster —
  the cluster count is a correct computation, not a description of sub-structure.
- `classification`: one of `continuous_carrier`, `short_burst`,
  `low_duty_pulse_train`, `pulse_train`, `single_pulse`, `no_crossing_observed`,
  `insufficient_evidence`, each with `basis`, `metrics` and `evidence` (edge and
  pulse ids, sample range) so the label can be re-derived from raw samples.

Paired or equal-width pulses are the signature of one pulse cut by an
intermediate level. Re-scan at that level and report the levels separately
instead of the split count.

## regimes

Requires a threshold pair. Optional: `--measures` (default `auto`, or a
comma-separated list such as `period_s,duty_cycle,high_width_s`),
`--min-cycles-per-side` (default `5`), `--relative-tolerance` (default `0.08`),
`--absolute-tolerance` (default `0.0`), `--transition-margin-cycles` (default
`1`), `--anomaly-z` (default `3.5`), `--max-edges`, `--max-cycles` (default
`5000`, maximum `200000`), `--cluster-gap-s`, `--chunk-points`, `--start-time` /
`--end-time`.

Builds on the same raw structure and groups complete cycles into stable regimes,
transitions, unresolved phases and isolated anomalies. Read these before relying
on it:

- `data_integrity_status` describes the record; `segmentation_status` and
  `overall_status` describe the interpretation. An intact capture with uncertain
  interpretation is not a corrupt waveform.
- `coverage.count_reconciliation` states the rule
  `stable + transition_uncertain + unresolved_phase + unassigned = analyzed_complete_cycles`
  and whether it reconciles.
- `coverage.segmentation_scope` is `prefix_only` when either budget was hit.
- A window holding only one complete cycle legitimately returns `UNSUPPORTED`;
  take stage evidence from a window with enough complete cycles and say which
  one.
- Smooth monotonic drift is reported as trend evidence inside a regime, not
  forced into step changes.

## window

`--start <index> --count <n>`, or `--start-time <s> --end-time <s>` (half-open);
never both. `--max-window-points` defaults to and is capped at `2000`.

Returns the raw `codes` for the window, plus `volts` when the calibration is
`VALID` (otherwise `value_domain: code` and a limitation). Use it to inspect
samples around an event id or an anomaly, never as a replacement for a
full-record scan.

## ringing

Same window arguments as `window`. Analyzes one bounded window: it locates the
dominant edge, then reports step amplitude, overshoot, undershoot, residual
crossings, an estimated ring frequency and an exponential decay constant when
enough peaks exist. It never returns the local array, so call `window` when the
raw samples themselves are needed.

Flags that must travel with any quoted result: `insufficient_pre_edge_context`,
`ringing_tail_may_be_truncated_by_analysis_window`,
`analysis_window_touches_capture_boundary`, and the standing limitations
`heuristic_local_edge_and_ringdown_estimate` and
`sampling_and_probe_bandwidth_limit_physical_ringing_claims`. A local estimate is
not proof that the physical event ended.

## Time, budgets and truncation

- Every time argument is half-open `[start, end)` relative to
  `sampling.origin_s`, not wall-clock time, and not absolute trigger time.
- A time range and a sample-index range are never combined.
- `--chunk-points` bounds memory, not coverage: the scan still walks the whole
  requested range.
- `structure`, `regimes` and `events` each carry an explicit budget. An exceeded
  budget produces an `UNVERIFIED` lower bound, never a truncated table presented
  as complete.
- `--max-json-bytes` bounding keeps each section's authoritative `count` and
  updates `returned` to the emitted length, reporting `items_truncated` /
  `items_complete`; the emitted list is a prefix. `classification` and
  `pulse_clusters.count` are computed before bounding and stay authoritative.
- A large record with dense transitions may not fit any single full-record call
  under the JSON budget. Cover it with contiguous sub-range windows, state their
  boundaries, and reconcile them rather than presenting one window as the record.

## Output conventions and errors

Every successful report carries `schema_version`, `tool`, `capture`,
`integrity`, `sampling`, `limitations`, `source_manifest_sha256`, `screen_range`,
`time_correspondence` and `screen_range_revalidation`. `source_manifest_sha256`
identifies the exact document that was read, so a later re-read can be proved
identical.

A refused command prints an error envelope and exits `2`:

```json
{
  "schema_version": "1.0",
  "tool": "structure",
  "capture": {"channel": "CH1"},
  "error": {"code": "CALIBRATION_INCONSISTENT", "message": "...", "reasons": ["..."]}
}
```

`--out` is refused when it resolves inside the capture directory. No output file
is overwritten. Read `error.code` before retrying: a loader code means the
capture is unusable as stored, while a `LIMIT_INVALID` code means the request
was malformed.
