# Parser Support Record

- Parser status: `offline-tested`
- Hardware verification: `partial` — see the per-claim table below, not a Skill-level claim
- Verified instruments cited below: `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4` (raw TCP `5555`, 2026-11-20); `Siglent Technologies,SDS824X HD,SDS08A0Q909185,4.8.12.1.1.6.5` (SCPI raw TCP `5025`, 2026-11-21); `GW Instek GDS-1000B` documented only, no instrument exercised
- Runtime dependency: `numpy` 2.0 or newer. The device-control Skills remain standard-library-only and hand over a file; no script in this Skill opens a socket or sends a SCPI command.
- Inputs: `waveform-bundle/v1` JSON, generic CSV, generic NPZ, and a legacy Siglent `manifest.json` or capture directory (read-only adapter)

## Per-claim evidence

| Claim | Label | Evidence |
|---|---|---|
| `waveform-bundle/v1` loader: required sections, byte-range arithmetic, slice and file SHA-256, `COMPLETE`-only admission, vertical block to internal calibration | `offline-tested` | `scripts/test_waveform_bundle.py`. Every mismatch raises `AnalysisError` with a named code (`BUNDLE_INVALID`, `HASH_MISMATCH`, `CAPTURE_NOT_COMPLETE`, `TIME_AXIS_INVALID`, `DTYPE_UNSUPPORTED`); no socket is opened |
| CSV loader: one value column or `time_s,value`, header time-column detection, uniform-grid check, interval-flag disagreement refused | `offline-tested` | `scripts/test_waveform_bundle.py`; a recorded interval that contradicts `--sample-interval-s` is refused, not overridden |
| NPZ loader: `samples` array plus optional scalar metadata, integer samples refused without an explicit scale | `offline-tested` | `scripts/test_waveform_bundle.py` |
| Legacy Siglent manifest / capture-directory adapter | `offline-tested` | `scripts/test_waveform_bundle.py`; the suite asserts that no module of `scope_protocol`, `capture_scope`, `ds1000z_protocol` or `gds1000b_protocol` is imported |
| Signal-processing engine: exact statistics, M4 preview, threshold events, raw-edge pulse structure, raw windows, ringing screening, regime segmentation | `offline-tested` | `scripts/test_waveform_analysis.py` |
| Verdict gate: derived thresholds, refusal codes, candidate excursions, `claims` vocabulary | `offline-tested` | `scripts/test_verdict_gate.py` |
| Evidence builder and SVG: five independent axes, refusal preservation, budget trimming, reserved-path delivery | `offline-tested` | `scripts/test_waveform_evidence.py` |
| Whole offline suite | `offline-tested` | 241 unit tests across the four suites, no socket opened, no network access |
| Rigol DS1074Z committed fixtures → bundle → `summarize` / `verdict` | `hardware-verified` for framing, scale, summary and verdict | `skills/rigol-ds1000z-control/assets/fixtures/waveform-norm-ch1.bin` and `waveform-raw-ch1.bin` are real `:WAVeform:PREamble?` + `:WAVeform:DATA?` responses captured from `DS1ZA171004155` (`00.04.02.SP4`) over raw TCP `5555` on 2026-11-20. Exported as `waveform-bundle/v1` and read back here, the NORM frame reconstructs `-0.04 V` … `3.00 V` (`vpp 3.04 V`) and the RAW frame `0.0 V` … `0.08375 V`, exactly the committed `expected-waveform-norm.json` / `expected-waveform-raw.json` values. NORM yields an `OBSERVED` verdict, RAW a `REFUSED` one (`thresholds_not_separated`); a refusal is a complete answer. `level_confirmed` stays `UNKNOWN` (`instrument_measurement_absent`) because no instrument reading accompanies the fixtures |
| GW Instek GDS-1000B committed fixture → bundle → `summarize` | `documented` and `offline-tested` | `skills/gwinstek-gds1000b-control/assets/fixtures/waveform-valid.bin` is a documented header-plus-`>i2` payload fixture, not an instrument capture. It loads and summarizes as `OBSERVED_UNVERIFIED` with `scale_usable: UNKNOWN`, `level_confirmed: UNKNOWN`; the voltage scale stays `OBSERVED_UNVERIFIED` per the GDS-1000B Skill contract, and a 4-point fixture supports no structure or regime claim |
| Siglent SDS824X HD captures: three-way level cross-check | `hardware-verified` on one level, one V/div, zero offset | On `4.8.12.1.1.6.5` over SCPI raw TCP `5025`, the byte-domain conversion path this Skill carries reconstructed `PKPK 3.0417 V` against the instrument's own `3.04167 V`: absolute difference `0.00003` within tolerance `0.0611`, `level_confirmed: PASS`, and a fabricated `5.0 V` reconstruction on the same frame gave `FAIL`. A fresh `waveform-bundle/v1` round-trip from `capture_scope.py` was not re-run on hardware; that path is `offline-tested` only. A non-zero panel offset and a second voltage range remain `UNVERIFIED` |

## Known limitations

- **Absolute voltage accuracy is never established by this Skill.** A
  `level_confirmed: PASS` covers one metric, on one stored frame, at one V/div
  and offset setting. It is a self-consistency check against the instrument's own
  reading, not a calibration against a traceable reference, and it never
  transfers to another range, offset, channel or frame.
- **`level_confirmed` needs a comparable instrument measurement.** With no
  recorded measurement the claim is `UNKNOWN`. The consumed metric vocabulary is
  `PKPK`, `top` and `base`; a measurement recorded under any other metric name is
  preserved in the bundle but leaves the level claim `UNKNOWN`.
- **A width-2 (WORD, or left-aligned 16-bit) capture stays in the code domain**
  until an external calibration file binds the scale to that record's SHA-256.
  A 16-bit transport container is never treated as a 16-bit voltage-calibrated
  ADC result.
- **Clipping bounds are the representable code range.** No-clipping is claimed
  only when no sample sits on a rail *and* the observed range stays strictly
  inside `adc_min_code` / `adc_max_code`; otherwise the result names the
  division boundary beyond which clipping was unobservable. A floating-point
  record with no declared ADC rails cannot establish either outcome and reports
  `cannot_claim: rail_bounds_unknown`.
- **Structural completeness is scoped to the stored record.** Whole-screen
  coverage, acquisition-memory extent, same-frame identity and trigger or
  wall-clock alignment stay `UNVERIFIED`: no accepted input carries a frame
  identifier, and a matching hash only proves the file was not altered.
- **Units, probe attenuation and signal names are not inferable.** A capture that
  records no probe ratio or channel description leaves them unknown; a physical
  channel conclusion stands, an attribution to a named signal does not.
- **Every list output is bounded.** `--max-edges`, `--max-cycles`,
  `--max-events-scanned` and `--max-json-bytes` produce explicit lower bounds or
  prefixes with the authoritative `count` beside them; no output silently
  truncates into a complete-looking table.
- **Local heuristics are bounded observations.** `ringing` and candidate-window
  review describe one window at original resolution; they never prove that a
  physical event ended, that no other candidate exists, or that the returned
  subset is a full review.
- **Nothing here repairs a capture.** A truncation, wrong width, missing segment
  or `INCOMPLETE` status is refused at load time; it is fixed at capture time by
  the device-control Skill, never patched here.

Do not upgrade a row of this record without a captured reply: model, firmware,
interface, date, and the raw bytes. A passing offline test run is not hardware
evidence.
