---
name: oscilloscope-waveform-analysis
description: Analyze stored oscilloscope waveform captures offline. Reads waveform-bundle/v1 JSON bundles, generic CSV and NPZ time series, and legacy Siglent capture directories, then emits bounded JSON for integrity, statistics, a verdict gate, threshold events, pulse structure, regime segmentation, local sample windows, ringing screening, and a five-axis evidence report with an optional SVG. Use for Siglent SDS800X HD, Rigol DS1000Z, and GW Instek GDS-1000B captures when the question is what the stored samples prove rather than how to command the instrument. Sends zero SCPI commands and requires numpy.
---

# Oscilloscope Waveform Analysis

Use this Skill when a capture already exists on disk and the question is what
those samples prove. It is offline only: it opens no socket, sends zero SCPI
commands, and imports no module from a device-control Skill. Its one runtime
dependency is `numpy` (2.0 or newer); the device-control Skills stay
standard-library-only and hand over a file rather than calling into this one.

Every accepted input is normalized by `scripts/waveform_bundle.py:load_capture`
into one `capture` mapping, so all eight analyzer subcommands and the evidence
builder read the same vertical formula and the same time axis:

```text
voltage(sample) = (sample - zero_code) * code_scale_v + effective_offset_v
time(index)     = time_origin_s + index * sample_interval_s
```

| Input | How it is recognized | `--channel` |
|---|---|---|
| `waveform-bundle/v1` JSON | any `.json` whose `schema` is `waveform-bundle/v1`; the primary, vendor-neutral contract | optional — needed only when the recorded channel differs from the one asked for |
| Generic `.csv` | one value column, or `time_s,value`; a recognized time column supplies a uniform sample interval | optional label only |
| Generic `.npz` | a `samples` array plus optional scalar metadata (`sample_interval_s`, `sample_rate_hz`, `time_origin_s`, `units`, `code_scale_v`, `zero_code`, `offset_v`) | optional label only |
| Legacy Siglent capture | a `manifest.json` or a capture directory containing one; read-only adapter, no import of `scope_protocol.py` | required when the manifest records more than one channel |

A capture that records no sample interval is refused unless
`--sample-interval-s` or `--sample-rate-hz` supplies it; a recorded interval that
disagrees with the flag is refused rather than overridden. `--vdiv`,
`--offset` and `--calibration` are legacy Siglent overrides and are rejected for
a self-describing bundle, CSV or NPZ file.

## Non-negotiable analysis rules

- **Run the verdict gate first, as one command.** `verdict` is the first
  conclusion subcommand, before any other analysis subcommand. A conclusion
  must quote `claims.can_claim`, must not assert anything in
  `claims.cannot_claim`, and must reproduce every `claims.must_state` entry
  verbatim. A `REFUSED` verdict is a complete answer: never work around it with
  hand-rolled arithmetic, a new threshold pair, or a narrower sampling claim.
  When a refusal hides a possible sparse event, escalate with
  `scripts/waveform_evidence.py`, which preserves the refusal and exposes the
  candidates it already localized.
- **A threshold is not placed by reaching it.** A threshold pair sitting inside
  the noise band returns a healthy-looking `OBSERVED` result whose silent
  prefix, first-edge time and pulse count are all wrong, and no output field
  flags it. Derive levels from `summarize` percentiles (`percentiles_v` when the
  calibration is `VALID`, `percentiles_code` otherwise) or from the `before_code`
  / `after_code` of a deliberately low `structure` pass, and state the evidence
  for every threshold pair used.
- **Analyze original-resolution samples.** The M4 preview from `summarize` and
  any strided view are `visualization_only_lossy`. Never derive an absence,
  no-drive, or duration conclusion from an aggregate, a window count, a mean, a
  preview, or a decimated view; use `structure`, or `events` plus `window`.
- **A local minimum or maximum is not a crossing.** Activity requires recorded
  threshold crossings under the stated thresholds. Features narrower than one
  sample interval between the two thresholds can be missed, so "no crossing
  observed" is not "no drive"; state the detection capability next to any
  negative claim.
- **Read the truncation flags before reusing a list.** `structure` fails closed
  on volume: an exceeded `--max-edges` budget yields
  `classification.status = UNVERIFIED`, `edges.count_is_lower_bound = true` and
  `full_record_scanned = false`, never a short table presented as complete.
  `--max-json-bytes` bounding is a separate limit: the section keeps its
  authoritative `count`, updates `returned`, and flags `items_truncated = true`
  with `items_complete = false`, so the emitted `items` list is a prefix.
- **Time is relative and half-open.** Every time argument is
  `[start, end)` against `sampling.origin_s`, not wall-clock time. Never combine
  time arguments with sample-index arguments.
- **Write outputs outside the capture directory.** `--out` and `--svg` are
  refused when they resolve inside it, and no target is ever overwritten.
- **Never pad, truncate, clamp, interpolate, or guess.** A refused command is
  reported in the error envelope with exit code `2`; it is not repaired by
  arithmetic on the descriptor.

## Integrity statuses

- `COMPLETE`: every applicable **structural and count** check passes for the stated claim (framing, required fields, point/row counts, terminator); it never means the data is correct, covers what the caller wanted, or is within calibration.
- `INCOMPLETE`: a required byte, terminator, field, point, segment, or status element is missing.
- `INVALID`: framing, counts, or type constraints contradict the observed bytes.
- `UNVERIFIED`: parsing found no contradiction, but the available evidence cannot prove completeness, units, calibration, or acquisition state.
- `UNSUPPORTED`: this Skill does not implement that response shape or feature.

A structural status never stands in for a different claim: **bytes complete**,
**scale usable**, **same frame**, and **the number is a physical level** are four
separate conclusions. Where an artifact reports one of them, it names it.

Never silently pad, truncate, clamp, interpolate, or guess. A sample array keeps
its record SHA-256 and its declared point and byte counts; a bounded list keeps
its authoritative `count` beside whatever prefix was returned.

## The three voltage claims

`integrity.status = COMPLETE` describes the stored payload arithmetic only. Three
separate fields decide whether a number is a physical level:

- `bytes_complete` — structural and count integrity of the stored record.
- `scale_usable` — the scale fields needed for a conversion are present and not
  contradicted by the record. `calibration.status = VALID` describes this one
  claim, never an absolute level.
- `level_confirmed` — the reconstructed amplitude agrees with the instrument's
  own recorded reading inside `2 * |code_scale_v| + 0.02 * |instrument_value|`.

Only `level_confirmed: PASS` removes `absolute_voltage_accuracy` from
`claims.cannot_claim`, and it does so for that record, channel and metric. With
no instrument measurement the claim is `UNKNOWN`, never a silent pass. A derived
value that only reproduces the instrument's own reading is
`OBSERVED_UNVERIFIED`, never calibrated.

## Quick start

```text
# Integrity and calibration entry point — run this first
python3 scripts/analyze_waveform.py inspect --capture /path/to/waveform.bundle.json

# Verdict gate before any other conclusion
python3 scripts/analyze_waveform.py verdict --capture /path/to/waveform.bundle.json

# Statistics plus an M4 visualization preview (never analysis evidence)
python3 scripts/analyze_waveform.py summarize --capture /path/to/waveform.bundle.json --preview-buckets 256

# Threshold events, paged with a stateless cursor
python3 scripts/analyze_waveform.py events --capture /path/to/waveform.bundle.json --threshold-codes 20 35 --limit 100
python3 scripts/analyze_waveform.py events --capture /path/to/waveform.bundle.json --threshold-codes 20 35 --start-time 2.01795 --end-time 2.01805 --limit 20

# Raw full-resolution edge, pulse and pulse-cluster facts
python3 scripts/analyze_waveform.py structure --capture /path/to/waveform.bundle.json --threshold-codes 20 35
python3 scripts/analyze_waveform.py structure --capture /path/to/waveform.bundle.json --threshold-volts 0.8 2.0 --cluster-gap-s 0.002 --max-edges 20000

# Stable measurement regimes, transitions and isolated anomalous cycles
python3 scripts/analyze_waveform.py regimes --capture /path/to/waveform.bundle.json --threshold-codes 20 35 --measures auto --min-cycles-per-side 5

# Bounded raw windows, by sample index or by half-open display time
python3 scripts/analyze_waveform.py window --capture /path/to/waveform.bundle.json --start 123456 --count 512
python3 scripts/analyze_waveform.py window --capture /path/to/waveform.bundle.json --start-time 2.01795 --end-time 2.01805

# Local overshoot, undershoot, residual crossings, ring frequency and decay
python3 scripts/analyze_waveform.py ringing --capture /path/to/waveform.bundle.json --start-time 2.01795 --end-time 2.01805

# Five-axis evidence package, optionally with a bounded raw-sample SVG
python3 scripts/waveform_evidence.py --capture /path/to/waveform.bundle.json --out /outside/path/evidence.json
python3 scripts/waveform_evidence.py --capture /path/to/waveform.bundle.json \
    --range-start 150000 --range-end 175000 \
    --max-sample-interval-s 2e-6 --sampling-requirement-source "task states 500 kSa/s minimum" \
    --candidate-windows 4 --candidate-window-points 1024 \
    --svg /outside/path/evidence.svg --out /outside/path/evidence.json
```

A legacy Siglent capture adds `--channel`; a CSV or NPZ file adds the time base
it does not record:

```text
python3 scripts/analyze_waveform.py inspect --capture /path/to/siglent-capture --channel C4
python3 scripts/analyze_waveform.py inspect --capture run.csv --sample-interval-s 2e-6 --units volts
python3 scripts/analyze_waveform.py summarize --capture run.npz
```

An NPZ archive may carry its own `sample_interval_s`/`sample_rate_hz` scalar; when
it carries neither, add `--sample-interval-s` or `--sample-rate-hz`, and expect a
recorded value that disagrees with the flag to be refused rather than replaced.

## Progressive reference

Load only the reference matching the current goal. Do not read all three up
front.

| Goal or observation | Read this reference |
|---|---|
| Write a bundle, verify one by hand, map a vendor's conversion into `zero_code` / `code_scale_v` / `offset_v`, or interpret a loader refusal | [Bundle schema](references/bundle-schema.md) |
| Choose a subcommand, pick its options, or interpret its report and limits | [Analysis methods](references/analysis-methods.md) |
| Decide what a capture can and cannot prove, read the three voltage claims, interpret clipping bounds, or read the evidence report and SVG contract | [Integrity and evidence](references/integrity-and-evidence.md) |
| Check which claims have actually been exercised, and against which model, firmware and interface | [SUPPORT.md](SUPPORT.md) |

## Bundled Resources

- `scripts/waveform_bundle.py`: `waveform-bundle/v1` validator and loader, CSV and NPZ loaders, the standalone legacy Siglent manifest adapter, `attach_three_way_status`, `samples_to_volts` / `volts_to_codes`, and `AnalysisError`. It inlines the SCPI scalar parse and the frame report the legacy `--revalidate-screen-range` path needs, so the analysis Skill stays free of any device-Skill import.
- `scripts/waveform_analysis.py`: the pure signal-processing layer — exact full-record statistics, M4 preview, threshold events, raw-edge pulse structure, raw windows, ringing screening, regime segmentation, JSON bounding and the error envelope.
- `scripts/waveform_scan.py`: full-record histograms, threshold placement diagnostics, hysteresis scanning, candidate excursions, clipping bounds from `adc_min_code` / `adc_max_code`, and `build_verdict` with its `claims` block.
- `scripts/analyze_waveform.py`: the bounded JSON CLI over the eight subcommands above.
- `scripts/waveform_evidence.py`: the five-axis evidence report and the optional raw-sample SVG.
- `scripts/test_waveform_bundle.py`, `test_waveform_analysis.py`, `test_verdict_gate.py`, `test_waveform_evidence.py`: offline tests. They read fixtures and synthesized captures only and never open a socket.

## Verification commands

```text
python3 -m unittest discover -s skills/oscilloscope-waveform-analysis/scripts -p 'test_*.py'
python3 scripts/analyze_waveform.py inspect --capture /path/to/waveform.bundle.json
```

A passing offline run is not hardware evidence: it cannot show that a stored
scale belongs to the physical signal. Only a recorded instrument reading and a
`level_confirmed` result inside the stated tolerance support a voltage claim, and
each such claim names the model, firmware, interface and date it came from.
