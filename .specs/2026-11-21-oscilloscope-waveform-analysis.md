# Oscilloscope Waveform Analysis — Design Specification (`waveform-bundle/v1`)

Date: 2026-11-21
Status: Frozen for implementation
Decision: Full split (remove duplicated analysis scripts from `siglent-sds800xhd-control` once `oscilloscope-waveform-analysis` passes full parity and regression checks).

## 1. Goal and Boundary

Extract the vendor-independent offline waveform analysis engine (~8,200 lines across
`waveform_analysis.py`, `waveform_scan.py`, `waveform_evidence.py`, and
`analyze_waveform.py`) out of `siglent-sds800xhd-control` into a standalone Agent
Skill: `skills/oscilloscope-waveform-analysis/`.

- **Device control Skills** (`siglent-sds800xhd-control`, `rigol-ds1000z-control`,
  `gwinstek-gds1000b-control`, future oscilloscopes):
  - Own SCPI sessions, triggering, framing, raw response preservation, and
    device-specific calibration formulas.
  - Remain zero-`numpy` (Python stdlib + existing serial/VISA dependencies only).
  - Export a `waveform-bundle/v1` JSON + raw/sample binary file on disk.
- **Universal analysis Skill** (`oscilloscope-waveform-analysis`):
  - Owns all offline signal analysis (summary, M4 preview, event search, pulse
    structure, regime segmentation, ringing analysis, hysteresis scan, verdict
    gate, evidence packaging, SVG preview, three-way voltage/level cross-check).
  - Explicitly declares `numpy` as a runtime dependency.
  - Sends zero SCPI commands and imports zero modules from any device Skill.
  - Accepts:
    1. `waveform-bundle/v1` JSON files (primary contract for all oscilloscopes),
    2. generic CSV/NPZ time-series files (with explicit metadata/units flags),
    3. legacy Siglent `manifest.json` captures (backward-compatible read-only
       adapter, zero dependency on `scope_protocol.py`).

## 2. Standard Interchange Contract: `waveform-bundle/v1`

A bundle consists of one UTF-8 JSON file (`<name>.bundle.json` or `bundle.json`)
referencing a binary sample file (relative to the bundle JSON directory when
possible).

```json
{
  "schema": "waveform-bundle/v1",
  "source": {
    "vendor": "siglent | rigol | gwinstek | generic",
    "model": "DS1074Z",
    "idn": "RIGOL TECHNOLOGIES,DS1074Z,...",
    "channel": "CH1",
    "captured_at": "2026-11-20T00:00:00Z"
  },
  "data": {
    "file": "waveform-norm-ch1.bin",
    "sha256": "<64-hex-sha256-of-file-or-slice>",
    "file_sha256": "<64-hex-sha256-of-entire-referenced-file>",
    "dtype": "<i2 | i1 | u1 | <f4 | <f8 | >i2",
    "points": 1200,
    "byte_offset": 0,
    "byte_length": 1200,
    "width_bytes": 1
  },
  "time_axis": {
    "sample_interval_s": 2.0e-7,
    "time_origin_s": -1.2e-4,
    "timebase_s": 1.0e-4,
    "horizontal_offset_s": 0.0,
    "reference": "trigger | descriptor | unverified",
    "origin_formula": "optional human-readable formula"
  },
  "vertical": {
    "units": "V | code",
    "scale_usable": true,
    "zero_code": 127.0,
    "code_scale_v": 0.02,
    "offset_v": 0.0,
    "vdiv_v_per_div": 0.5,
    "adc_min_code": 0,
    "adc_max_code": 255,
    "full_scale_code": null,
    "calibration_status": "VERIFIED | UNVERIFIED | CODE_ONLY",
    "calibration_source": "rigol_preamble | gds1000b_header | siglent_descriptor | explicit_cli | external_file | none",
    "scale_reasons": []
  },
  "integrity": {
    "status": "COMPLETE | INCOMPLETE | INVALID | UNVERIFIED | UNSUPPORTED",
    "bytes_complete": true,
    "checks": ["..."],
    "status_meaning": "payload framing/count integrity only"
  },
  "provenance": {
    "raw_file": "waveform-norm-ch1.raw",
    "raw_sha256": "<hex>",
    "new_transition_proven": null,
    "screen_range": null,
    "screenshot": null
  },
  "instrument_measurements": null
}
```

### 2.1 Vertical Reconstruction Formula

For integer/code dtypes (`i1`, `u1`, `<i2`, `>i2`, `<u2`, etc.):
```
voltage(sample) = (sample - zero_code) * code_scale_v + offset_v
```
- When `vertical.units == "V"` and `vertical.scale_usable == true`:
  `code_scale_v` MUST be finite and `> 0`; `zero_code` defaults to `0.0`;
  `offset_v` defaults to `0.0`.
- When `vertical.units == "code"` or `vertical.scale_usable == false`:
  analysis stays in code domain; `cannot_claim` includes `absolute_voltage_accuracy`.
- For floating-point dtypes (`<f4`, `<f8`):
  when `code_scale_v` is `1.0`, `zero_code` is `0.0`, `offset_v` is `0.0`, samples
  are already in physical units (`V`).

### 2.2 Clipping Bounds (Decoupled from Siglent `_codes_per_div`)

`waveform_scan.py` computes clipping/rail limits from:
1. `vertical.adc_min_code` and `vertical.adc_max_code` (primary, vendor-neutral),
2. `vertical.full_scale_code` (optional nominal display rail, e.g. `5 * codes_per_div`),
3. fallback to legacy Siglent `preamble` fields ONLY when loading a legacy
   Siglent `manifest.json` without `adc_min_code`/`adc_max_code`.

Unsigned integer captures (e.g. Rigol 8-bit `u1`, `[0, 255]`) MUST be handled
correctly alongside signed integer captures (`i1` `[-128, 127]`, `<i2` `[-32768, 32767]`).

### 2.3 Integrity Fail-Closed Rules

- `data.sha256` (slice SHA-256) and `data.file_sha256` (if present) are verified
  against actual bytes on disk. Any mismatch raises `AnalysisError`.
- `data.byte_length` MUST equal `data.points * itemsize(data.dtype)`.
- `data.byte_offset + data.byte_length <= actual_file_size`.
- `integrity.status != "COMPLETE"` refuses analysis (unless an explicit legacy
  opt-in flag is active for legacy Siglent manifests).
- `time_axis.sample_interval_s` MUST be finite and `> 0`.

### 2.4 Optional `instrument_measurements` Shape

Compatible with Siglent's contract (`artifacts/fix-plan/contract.md`):
```json
{
  "metric": "PKPK",
  "value": 3.04167,
  "unit": "V",
  "source_query": "C1:PAVA? PKPK"
}
```
When present and `scale_usable` is `True`, `attach_three_way_status` evaluates:
`tolerance = 2.0 * abs(code_scale_v) + 0.02 * abs(instrument_value)`
and sets `level_confirmed` to `PASS` / `FAIL` / `UNKNOWN`.
When absent, `level_confirmed` is `UNKNOWN` (`no_instrument_measurement`), and
`cannot_claim` includes `absolute_voltage_accuracy`.

### 2.5 Vendor Adapter Mappings

| Vendor | Source | `dtype` | `zero_code` | `code_scale_v` | `offset_v` | `adc_min_code` / `adc_max_code` |
|---|---|---|---|---|---|---|
| **Rigol DS1000Z** | `parse_waveform()` (`WAV:PRE?` + `WAV:DATA?`) | `u1` | `yorigin + yreference` | `yincrement` | `0.0` | `0` / `255` |
| **GW Instek GDS-1000B** | `parse_waveform()` (`:ACQ<X>:MEM?` header + big-endian int16) | `>i2` | `0.0` | `vdiv / 25.0` (per `gds1000b_protocol.sample_value`) | `0.0` (position noted in metadata; match `sample_value`) | `-32768` / `32767` |
| **Siglent SDS800X HD** | `capture_scope.py` (modern BYTE/WORD or legacy DAT2) | `i1` or `<i2` | `0.0` | `effective_vdiv / codes_per_div` (when verified) | `-effective_offset_v` (or `0.0` when unverified) | `-128`/`127` or `-32768`/`32767` |
| **Generic CSV / NPZ** | 1- or 2-column CSV or `.npz` | `<f8` | `0.0` | `1.0` | `0.0` | `null` / `null` |

*Note on GDS-1000B voltage formula*: verify the exact formula in
`gds1000b_protocol.py:sample_value()` during WP-6 and match it verbatim so
`waveform_bundle` voltages equal `gds1000b_protocol.sample_value()` to floating-point precision.

## 3. Canonical Internal `capture` Dict Shape

All analysis functions (`summarize_capture`, `m4_preview`, `find_events`,
`analyze_pulse_structure`, `get_window`, `analyze_ringing`,
`analyze_waveform_regimes`, `build_verdict`, `collect_evidence`, `build_evidence`)
consume one normalized `capture` dict produced by `waveform_bundle.load_capture()`:

Required keys (preserving compatibility with existing analysis code & tests):
- `manifest_path`, `manifest_dir`, `manifest`, `manifest_sha256` (for bundle-v1, `manifest` holds the bundle dict and `manifest_path` holds the bundle JSON path)
- `source_format`: `"waveform-bundle/v1"` | `"siglent-manifest"` | `"csv"` | `"npz"`
- `channel`, `path`, `samples` (numpy ndarray), `points`, `bytes`, `width`, `dtype`, `raw_sha256`
- `sample_interval_s`, `sample_rate_hz`, `time_origin_s`
- `preamble` (dict; may be minimal `{horizontal_offset, timebase_s}` for non-Siglent bundles)
- `calibration` (dict with `units`, `status`, `source`, `code_scale_v`, `zero_code`, `effective_offset_v`, `effective_vdiv_v_per_div`, `lsb`, `bytes_complete`, `scale_usable`, `scale_reasons`, `level_confirmed`, `level_reason`, `instrument_metric`, `instrument_value`, `instrument_unit`, `reconstructed_value`, `tolerance`, `adc_min_code`, `adc_max_code`, `full_scale_code`)
- `integrity` (`status`, `checks`, `status_meaning`)
- `screen_range` (dict or `None`)
- `time_correspondence` (dict)
- `screen_range_revalidation` (dict; `{"applied": False}` for non-Siglent)
- `provenance` (`new_transition_proven`, `screenshot`, `raw_file`, `raw_sha256`)

## 4. CLI Contract (`analyze_waveform.py` & `waveform_evidence.py`)

`analyze_waveform.py` supports:
- `--capture <path>` (auto-detects: `waveform-bundle/v1` JSON, Siglent `manifest.json` or capture directory, `.csv`, `.npz`)
- `--channel <ch>` (required for multi-channel Siglent manifests; optional for single-channel bundles/CSV/NPZ)
- All 8 existing subcommands preserved with identical JSON schemas:
  `inspect`, `summarize`, `verdict`, `events`, `structure`, `regimes`, `window`, `ringing`
- Existing CLI flags preserved (`--vdiv`, `--offset`, `--calibration-file`,
  `--revalidate-screen-range`, `--sample-rate-hz` / `--sample-interval-s` for CSV).

`waveform_evidence.py` supports `--capture <path>` (same auto-detection) and all
existing options (`--out-dir`, `--channel`, `--summary`, etc.).

## 5. Module Layout and Work Packages

### New Skill: `skills/oscilloscope-waveform-analysis/`
- `scripts/waveform_bundle.py` (WP-1): schema validator, bundle-v1 loader, CSV/NPZ loader, self-contained Siglent manifest compatibility loader (inlining SCPI number parsing and minimal frame validation needed for `--revalidate-screen-range` without importing `scope_protocol`), `attach_three_way_status`, `AnalysisError`.
- `scripts/waveform_analysis.py` (WP-2): re-exports loader/calibration symbols from `waveform_bundle` for API compatibility; hosts all pure signal-processing functions (`summarize_capture`, `m4_preview`, `find_events`, `analyze_pulse_structure`, `get_window`, `analyze_ringing`, `analyze_waveform_regimes`, `bound_json`, `error_envelope`), using `(samples - zero_code) * code_scale_v + offset_v`.
- `scripts/waveform_scan.py` (WP-3): histogram, thresholds, hysteresis scan, candidate excursions, clipping bounds via `adc_min_code`/`adc_max_code` (supporting unsigned `u1` and signed `i1`/`i2`), `build_verdict` + `cannot_claim`.
- `scripts/waveform_evidence.py` + `scripts/analyze_waveform.py` (WP-4): evidence builder, SVG preview, unified CLI.
- `SKILL.md`, `SUPPORT.md`, `manifest.json`, `references/{bundle-schema,analysis-methods,integrity-and-evidence}.md` (WP-8).

### Device Skills Updated
- `skills/rigol-ds1000z-control/` (WP-5): `export_waveform_bundle()` in `ds1000z_protocol.py` + `--bundle-out` in `ds1000z_session.py` + unit tests + end-to-end check on committed DS1074Z fixtures.
- `skills/gwinstek-gds1000b-control/` (WP-6): `export_waveform_bundle()` in `gds1000b_protocol.py` + `--bundle-out` in `gds1000b_session.py` + unit tests + end-to-end check on committed GDS-1000B fixtures.
- `skills/siglent-sds800xhd-control/` (WP-7 & WP-9):
  - WP-7: `capture_scope.py` writes `<channel>.bundle.json` (`waveform-bundle/v1`) alongside `manifest.json` on successful capture; fix `test_scope_protocol.py` line 586 (remove cross-import of `waveform_analysis`).
  - WP-9: remove duplicated `waveform_analysis.py`, `waveform_scan.py`, `waveform_evidence.py`, `analyze_waveform.py`, `test_waveform_analysis.py`, `test_verdict_gate.py`, `test_waveform_evidence.py`; update `siglent-sds800xhd-control/{SKILL.md,SUPPORT.md,manifest.json,references/*.md}`, `README.md`, `README.zh-CN.md`.

## 6. Acceptance Gate

1. `quick_validate.py` passes on all 9 Skills.
2. `npx skills@latest add . --list` lists all 9 Skills matching `ls skills/`.
3. All offline unit test suites pass:
   - `oscilloscope-waveform-analysis` (migrated 143+ tests + new bundle/CSV/Rigol/GDS tests),
   - `siglent-sds800xhd-control` (protocol/capture/configure/discover/decode/screenshot tests, zero dependency on deleted analysis scripts),
   - `rigol-ds1000z-control` (249+ tests including bundle export),
   - `gwinstek-gds1000b-control` (149+ tests including bundle export),
   - all other 4 device Skills + `write-new-instrument-control/assets/examples`.
4. End-to-end smoke: real DS1074Z fixture -> Rigol bundle -> `analyze_waveform.py summarize` & `verdict`; GDS-1000B fixture -> GDS bundle -> `analyze_waveform.py summarize` & `verdict`; Siglent synthetic capture -> Siglent bundle -> `analyze_waveform.py summarize` & `verdict`.
5. `README.md` and `README.zh-CN.md` stay strictly parallel and verified.
