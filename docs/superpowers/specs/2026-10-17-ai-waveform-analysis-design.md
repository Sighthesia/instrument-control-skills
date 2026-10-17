# AI Waveform Analysis Tools Design

## Intent

Add a read-only local analysis layer for SDS824X HD raw capture artifacts. Its purpose is to turn multi-million-point analog captures into small, evidence-linked responses that an AI agent can interpret and then selectively refine. Raw binary captures remain authoritative and are never replaced by a visualization or statistical summary.

## Goals

- Validate the manifest, descriptor, merged file length, transfer width, byte order, segment continuity, and SHA-256 before interpreting samples.
- Read the existing headerless BYTE and WORD `waveform.bin` files with bounded memory using NumPy memory mapping and chunked scans.
- Produce exact full-record count/min/max/mean/RMS/percentiles/clipping statistics and a bounded M4 first/last/min/max preview.
- Detect configured threshold crossings, pulse widths, runts, and missing/long intervals over the full-resolution record.
- Retrieve bounded sample windows around an absolute point range or detected event without exposing the whole trace.
- Emit versioned JSON with calibration provenance, coverage, limitations, algorithm parameters, absolute sample indices, hashes, and bounded event pagination.
- Integrate as standalone scripts in the existing skill and package with offline deterministic tests.

## Non-goals for This Release

- No SCPI calls and no changes to scope capture state, current capture script, or raw artifacts.
- No claim that summaries preserve every event. M4 is only a shape-preserving visualization reduction under its bucket semantics; event scans use original samples.
- No automatic causal diagnosis, universal logic threshold, or automatic threshold selection presented as ground truth.
- No voltage scaling from user-supplied V/div unless the value is explicitly declared probe-compensated; otherwise use the descriptor's VDIV and probe fields and label the source.
- No WORD effective-bit or voltage-scale claim by default. Preserve signed little-endian 16-bit codes. The current parser's `max_value=code_per_div*256` is a derived transport relation, not an independent calibration record; WORD voltage remains `OBSERVED_UNVERIFIED` unless a separate BYTE/WORD comparison or known-voltage calibration artifact is supplied and bound to the exact merged waveform SHA-256.
- No protocol decoders, jitter/ringing curve fits, power spectral density, PI transient analysis, MCP server, GUI, database, or generic ML feature extraction in the first implementation.
- Do not add `tsfresh`, `catch22`, `wavekit`, or a required SciPy dependency. NumPy is used for memory mapping, chunk operations, and deterministic numerical reduction; SciPy may be evaluated later for specific detectors.

## Inputs and Capture Compatibility

The analyzer accepts either a capture directory containing `manifest.json` or a manifest path, plus a channel. It selects that channel's successful `results[]` entry, resolves `merged_waveform`, and cross-checks it against `merged_waveform_bytes`, `merged_waveform_sha256`, `frame_report`, `segment_report`, and the WAVEDESC-derived `preamble`.

- BYTE: signed 8-bit samples (`int8`), one byte per point.
- WORD: signed little-endian 16-bit samples (`<i2`), two bytes per point; the descriptor must report `COMM_TYPE=1`, `COMM_ORDER=LSB`, and `SPARSING_FACTOR=1`.
- Point count and file byte length must agree exactly before analysis. Segment ranges must be contiguous and each segment file must match recorded size and hash when segment metadata is available.
- Sample time is computed from descriptor origin and interval. Each event stores the absolute point index and time in seconds, not only a rounded timestamp.

### Voltage Calibration

The parser exposes descriptor `vdiv`, `probe`, `offset`, `code_per_div`, and `max_value`; channel snapshots include queried VDIV/OFST strings. Scale provenance must be explicit.

- Default BYTE conversion uses the documented SDS interpretation: `vdiv_effective = descriptor.vdiv * descriptor.probe`, `offset_effective = descriptor.offset * descriptor.probe`, and `signed_byte * vdiv_effective / code_per_div - offset_effective`.
- WORD conversion is not emitted by default. The documented formula must be independently validated for this firmware because the descriptor's vertical code field has been observed in both BYTE and WORD transport contexts and the current parser derives `max_value=code_per_div*256`. A separate calibration artifact may explicitly provide a WORD divisor and source; otherwise return codes only with `calibration.status=OBSERVED_UNVERIFIED`.
- An optional `--vdiv` is an explicit physical, probe-compensated panel scale in V/div and must not be multiplied by `probe` again. An optional `--offset` is an explicit physical offset in volts. Include both override values and source labels in the JSON.
- The analyzer compares descriptor-derived scale with the captured panel snapshot. A mismatch does not invalidate raw capture integrity; it downgrades calibration to `UNKNOWN` and suppresses `_v` fields unless an explicit override resolves it. No channel scale such as C1/C2/C3/C4 = 2/2/10/5 V/div is silently assumed.

## Architecture

### Files

- `scripts/waveform_analysis.py`: manifest and calibration model, integrity checks, memory-mapped reader, chunked exact statistics, M4 aggregation, event algorithms, and window extraction as importable functions.
- `scripts/analyze_waveform.py`: CLI with `inspect`, `summarize`, `events`, and `window` commands; JSON to stdout or an explicitly named output file.
- `scripts/test_waveform_analysis.py`: synthetic BYTE/WORD fixtures and deterministic tests for integrity, units, bounds, and chunk boundaries.
- `SKILL.md`: add the local analysis workflow and explain that full raw files remain local.
- `dist/siglent-sds824xhd-control.skill`: rebuild after validation.

### Bounded Processing

- Use `numpy.memmap(mode="r")` over the merged raw file; never call `.tolist()` or serialize a full array. NumPy is a runtime dependency with a documented lower bound of 2.0; missing NumPy returns `NUMPY_UNAVAILABLE`.
- Process fixed-size blocks (default 1,000,000 points) for streaming summaries and transition scans. Report block size and scanned range.
- Accumulate `sum` and `sum_squared` as integer arithmetic over the finite integer code domain; derive mean/RMS only after the scan. For exact percentiles, use a fixed-size histogram over the finite ADC code domain (256 BYTE codes, 65,536 WORD codes), nearest-rank/no interpolation, and report that the discrete-code percentile is exact.
- M4 divides the requested full-record range into at most `preview_buckets` temporal buckets and returns original point indices for first, last, minimum, and maximum in chronological order, deduplicated within each bucket. Include bucket span and explicitly label the output `visualization_only_lossy`.
- Event detectors operate on the raw samples/derived calibrated values. A block boundary carries enough prior samples/state to detect transitions and pulses crossing the boundary; absolute point indices deduplicate the event.
- Default output bounds are independent: at most 2,000 M4 buckets (up to 8,000 selected samples), 100 event rows per page, 2,000 samples per window, and 256 KiB compact serialized JSON (without indentation). The CLI must reject or clamp invalid limits and report truncation. A final serialized-size check may truncate event rows first, then preview rows, while retaining summary/integrity fields and setting `truncated=true`.

### First-Release Detectors

- Threshold edge scanner: rising/falling crossings at caller-specified low/high threshold with interpolated crossing time; report threshold and hysteresis.
- Pulse/run-length scanner: pair crossings, compute high/low widths, classify runt only when caller supplies a minimum valid pulse width and optional minimum amplitude; do not infer a logic family automatically.
- Missing/long interval scanner: estimate expected period from an explicit parameter or robust median of accepted adjacent same-polarity edges; use caller tolerance. If too few periods exist, return `insufficient_evidence`, not a guessed clock.
- Edge quality features may include 10-90% rise/fall time and slew only when a stable edge and configurable baseline/high levels are available. Keep these as computed measurements and do not claim SI compliance without probe/bandwidth/sampling metadata.

## CLI Contract

Examples:

```text
python3 scripts/analyze_waveform.py inspect --capture /data/capture --channel C4
python3 scripts/analyze_waveform.py summarize --capture /data/capture --channel C4 --preview-buckets 1000
python3 scripts/analyze_waveform.py events --capture /data/capture --channel C4 --threshold-volts 1.0 2.0 --min-pulse-s 1e-6 --limit 100
python3 scripts/analyze_waveform.py window --capture /data/capture --channel C4 --start 123456 --count 512
```

`events` uses a stateless cursor containing the last absolute start sample, event type, and event ID. Each request rescans the capture from the beginning and skips events through that cursor; this is deterministic but has full-scan cost per page. The detector has a `max_events_scanned` budget and reports `transition_density_exceeds_budget` when it stops early. Each response includes `total`, `returned`, `next_cursor`, `scan_truncated`, `page_truncated`, and `total_is_lower_bound`. Event pages are deterministic when sorted by absolute start sample, event type, and event ID. With fewer than three observed rising-edge intervals and no explicit period, the detector status is `insufficient_evidence`. `window` always caps returned samples and supports raw ADC codes plus calibrated volts only when calibration is independently valid.

## JSON Output

All commands return a compact envelope:

```json
{
  "schema_version": "1.0",
  "tool": "summarize",
  "capture": {"id": "...", "channel": "C4", "raw_sha256": "...", "points": 25000000, "bytes": 50000000},
  "integrity": {"status": "COMPLETE", "checks": []},
  "sampling": {"interval_s": 2e-7, "rate_hz": 5000000},
  "calibration": {"status": "OBSERVED_UNVERIFIED", "units": "code", "vdiv_v_per_div": null, "source": "WORD scale requires independent calibration", "word_scale_codes_per_div": null},
  "summary": {"count": 25000000, "min_code": 0, "max_code": 0, "mean_code": 0.0, "rms_code": 0.0, "percentiles_code": {"p01": 0, "p50": 0, "p99": 0}},
  "preview": {"kind": "M4", "semantics": "visualization_only_lossy", "value_domain": "code", "bucket_count": 2, "points": [{"sample": 0, "code": 0}, {"sample": 24999999, "code": 0}]},
  "coverage": {"scanned_start": 0, "scanned_end_exclusive": 25000000, "full_record_scanned": true, "limitations": []},
  "events": {"total": 0, "returned": 0, "items": [], "next_cursor": null, "scan_truncated": false, "page_truncated": false}
}
```

Event records additionally include detector ID/version, parameters, absolute `[start_sample, end_sample)` range, time range, measured values and units, confidence/evidence quality, capture hash, and a recommended raw-window range. Hypotheses belong in a separate optional `interpretation` field and must never be mixed with measurements.

## Failure Behavior

- Missing manifest/channel/result, descriptor/manifest disagreement, internally inconsistent calibration, wrong file size/hash, or malformed segments return a machine-readable error and nonzero process exit. A channel result is selectable only when exactly one entry has `frame_report.status==COMPLETE`, `segment_report.status==COMPLETE`, and an existing merged waveform; missing/ambiguous entries have fixed error codes.
- A structurally complete capture without independently verified voltage calibration returns exit 0 with `calibration.status=UNKNOWN` or `OBSERVED_UNVERIFIED`; it may emit code-domain fields but no `_v` fields. A malformed descriptor required for interpreting the raw format returns `DESCRIPTOR_MISMATCH`; a scale disagreement is a calibration limitation, not a raw capture corruption.
- NaN/non-finite derived values are serialized as JSON `null` with a limitation entry; never emit non-standard NaN/Infinity JSON.
- Empty files, zero sample interval, non-divisible WORD byte length, out-of-range windows, and excessive event/window limits fail with clear errors.

### Error Envelope

Errors use this bounded shape and a nonzero exit code:

```json
{"schema_version":"1.0","tool":"summarize","capture":{"channel":"C4"},"error":{"code":"HASH_MISMATCH","message":"...","reasons":["..."]}}
```

Fixed codes include `MANIFEST_MISSING`, `CHANNEL_MISSING`, `CAPTURE_NOT_COMPLETE`, `AMBIGUOUS_CAPTURE`, `PATH_UNRESOLVED`, `DESCRIPTOR_MISMATCH`, `WIDTH_UNSUPPORTED`, `HASH_MISMATCH`, `LENGTH_MISMATCH`, `CALIBRATION_INCONSISTENT`, `WINDOW_OUT_OF_RANGE`, `LIMIT_INVALID`, and `NUMPY_UNAVAILABLE`.

The external WORD calibration file is intentionally small and capture-bound:

```json
{"channels":{"C4":{"word_scale_verified":true,"capture_sha256":"<merged SHA-256>","word_codes_per_div":7680,"vdiv_v_per_div":5.0,"offset_v":0.0,"evidence":"known DC reference and BYTE/WORD comparison"}}}
```

## Verification

- BYTE and WORD synthetic fixtures verify signed decode, LSB, descriptor metadata, explicit panel overrides, and that unverified WORD scale emits codes without voltage fields or double probe multiplication.
- M4 tests verify bucket bounds, extrema inclusion, chronological order, and original absolute indices.
- Event tests include rising/falling edges, runt widths, normal/missing pulse intervals, events straddling processing chunks, deterministic stateless cursors, scan budgets, and deduplication.
- Integrity tests cover hash mismatch, length mismatch, wrong `COMM_TYPE`, wrong byte order, invalid calibration and incomplete frame rejection.
- Bound tests verify preview/event/window/JSON limits and cursor ordering; sum/squared-sum use integer accumulation and percentile uses nearest rank.
- Run the full offline test suite, skill validator, package builder, and `git diff --check`.

## Reuse and References

- M4 reduction pattern: Jugel et al., *M4: A Visualization-Oriented Time Series Data Aggregation*, VLDB 2014, https://www.vldb.org/pvldb/vol7/p797-jugel.pdf. The M4 concept informs preview only; this project implements its small bucket reducer locally for raw index preservation.
- NumPy memory-mapped access: https://numpy.org/doc/stable/reference/generated/numpy.memmap.html.
- SciPy peak detection/PSD references for future specific detectors: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html and https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html. SciPy is not required for this release.
- MCP structured tool output contract: https://modelcontextprotocol.io/specification/2025-11-25/server/tools. The first release emits schema-shaped CLI JSON; exposing MCP endpoints is outside the current deliverable.
- Waveform-tool pattern: https://github.com/cxzzzz/wavekit-mcp, reviewed as an interaction model, not reused as code or an analog-scope parser.
