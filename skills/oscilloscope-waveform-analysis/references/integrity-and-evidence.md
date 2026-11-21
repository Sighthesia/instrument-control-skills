# Integrity, voltage claims, and the evidence report

Load this reference when a conclusion needs its scope stated before it can be
trusted: when someone asks whether a record is "complete", whether a voltage is
"right", whether the front end clipped, or what a `REFUSED` verdict and its
evidence package actually permit. Two artifacts are described here — the
`claims` block every analysis report carries, and the five-axis report built by
`scripts/waveform_evidence.py`.

## Three separate voltage claims

`integrity.status = COMPLETE` answers one question: do the stored bytes agree with
their own declared framing, counts and hashes? It says nothing about units,
calibration, or whether the number is a physical level. Those are three further
claims, and each artifact names the one it is making.

| Field | Question | Decided from | Never means |
|---|---|---|---|
| `bytes_complete` | Is the stored record structurally whole? | the loader's own checks; `COMPLETE` when no verification failure was recorded | that the record covers the screen, the acquisition memory, or the event of interest |
| `scale_usable` | Are the scale fields present, positive and not contradicted? | `calibration.status`, `effective_vdiv_v_per_div`, `effective_offset_v`, and that the units are volts | that the scale is correct: a wrong V/div source, an ampere scale read as volts, or a dropped panel offset all keep this claim green |
| `level_confirmed` | Does a reconstructed amplitude agree with the instrument's own reading? | `PASS` / `FAIL` / `UNKNOWN` from the tolerance comparison below | that the chain is calibrated, or that any other level, range, offset, channel or frame is confirmed |

`scale_reasons` names why `scale_usable` is not `VALID`: `calibration_status_not_valid`,
`vdiv_unknown`, `offset_unknown`, `units_<label>_not_volts`, a bundle's own
`bundle_declares_scale_unusable`, or `bundle_records_code_only_calibration`.

`level_reason` is a diagnostic beside `level_confirmed`, not the claim itself:
`instrument_measurement_absent`, `instrument_measurement_absent_for_<channel>`,
`code_scale_unknown`, `instrument_measurement_in_<unit>_not_volts`,
`no_reconstructed_amplitude`, `reconstructed_outside_tolerance`. Read
`level_confirmed` for the conclusion and `level_reason` for the trail; a `PASS`
carries whichever reason the loader recorded before an amplitude existed.

## The tolerance comparison

```text
tolerance = 2 * |code_scale_v| + 0.02 * |instrument_value|
level_confirmed = PASS   when |reconstructed_value - instrument_value| <= tolerance
                = FAIL   otherwise
                = UNKNOWN when no comparable measurement or no reconstruction exists
```

The first term covers two codes of quantisation, one at each end of a
peak-to-peak reading. The second covers the instrument's own measurement chain.
The comparison is only made when the recorded metric is `PKPK`, `top` or `base`
and its unit is a voltage; a metric recorded in amperes is a `FAIL`, not a
silent conversion, and any other metric name leaves the claim `UNKNOWN`.

This is a self-consistency check against the instrument's own reading. Both
numbers come from the same acquisition, so a `PASS` is sufficient to place
thresholds and to reproduce the instrument's readings, and it is not an
independent calibration. It must be labelled `OBSERVED_UNVERIFIED` for absolute
accuracy.

## `claims` — the closed vocabulary

Every `verdict` report carries `claims.can_claim`, `claims.cannot_claim` and
`claims.must_state`. A conclusion must quote `can_claim`, must not assert
anything in `cannot_claim`, and must reproduce every `must_state` entry
verbatim. Adding an entry is a contract change, not a wording tweak.

`can_claim` entries:

| Entry | Meaning |
|---|---|
| `levels` | the analyzed record's own level separation was resolved |
| `dense_window_local_frequency` | a median half period inside the densest windows is available; it is window-local |
| `intermittent_burst_structure` | the dense-window rate far exceeds the full-record mean rate, so the record is intermittent rather than steady |
| `no_clipping` | no sample sits on a rail **and** the observed range stays strictly inside the representable code limit |
| `candidate_excursions` | a refused scan still localized deviation candidates; they are not levels |

`cannot_claim` entries:

| Entry | Meaning |
|---|---|
| `absolute_voltage_accuracy` | emitted unless the scale is `VALID` **and** `level_confirmed` is `PASS` |
| `rail_bounds_unknown` | the record carries physical values but no ADC rails, so nothing can prove either way whether the front end clipped |
| `clipping_beyond_<n>_divisions_unobservable` | clipping is only observable up to the transport's own code limit; the boundary is stated |
| `period_stability_beyond_sample_grid` | half periods are integer sample counts; sub-sample jitter is not measurable |
| `stability_and_transition_analysis` | the gate alone does not perform regime segmentation |
| `single_continuous_frequency` | the half-period population is bimodal, so neither the median nor the mean describes the record |
| `multi_channel_causality` | one channel was analyzed |
| `screen_range_correspondence`, `trigger_time_alignment` | no accepted input carries a shared frame identifier or a trigger-locked timestamp |

`must_state` entries are complete limitation sentences:

| Entry | Statement to reproduce |
|---|---|
| `existing_stopped_no_ready_to_stop` | the frame was read from an already-stopped scope; no `Ready -> Stop` transition was observed |
| `frame_provenance_unrecorded` | the capture records no transition claim either way |
| `scale_observed_unverified_no_calibration_available` | no verified scale exists, so no absolute voltage is available |
| `detection_resolution_<n>ns` | the sample interval bounds every timing claim |
| `frequency_basis_is_window_local_not_record_wide` | the headline frequency is a dense-window median, not a record-wide value |
| `single_channel_analysis_only` | no cross-channel relationship was analyzed |
| `screen_range_and_trigger_time_alignment_unverified` | descriptor-relative time only; screen, trigger and wall-clock alignment are unproven |
| `screen_range_revalidated_original_frame_incomplete` | a recorded screen-range failure was re-derived offline; the original frame status is unchanged |

## Clipping rails

Rail detection is decoupled from any vendor's nominal grid:

1. `vertical.adc_min_code` and `vertical.adc_max_code` (vendor-neutral, primary).
2. `vertical.full_scale_code` (optional nominal display rail, recorded only).
3. For a legacy Siglent manifest without ADC bounds, the descriptor's own
   code-per-division fields; a WORD frame is never scaled by the BYTE value.

`structure.rail_bounds` states which source applied, and `clipping_check` says
whether it was evaluable at all. `representable_code_limit` is the highest
transportable code and `clip_limit_div` the same limit in divisions, so
`clipping_detectable_up_to_div` names the boundary beyond which clipping is
invisible.

Rules:

- `no_clipping` requires `rail_samples == 0` **and** the observed min/max strictly
  inside the representable limit. A clean rail count alone is not proof, because
  a clipped excursion that runs past the transport's range is indistinguishable
  from one that stops at it.
- A record whose samples are already physical values (a float capture) with no
  ADC rails produces `cannot_claim: rail_bounds_unknown`. Saying "it did not
  clip" would be a guess and saying "it did" would be an invention.
- Unsigned (`u1`, `[0, 255]`) and signed (`i1` `[-128, 127]`, `<i2`
  `[-32768, 32767]`) records are handled from their own dtype and declared
  bounds; a width-only guess misplaces every unsigned rail.

## The evidence report (`waveform_evidence.py`)

The report answers five independent questions instead of one verdict. Each axis
carries `status`, `scope`, `reasons` and `evidence`, and satisfying one axis
never satisfies another.

| Axis | `COMPLETE` means | Never means |
|---|---|---|
| `payload_integrity` | the stored descriptor record matches its own point count, byte width, segment ranges/sizes and SHA-256 values; scope `descriptor_record_download_only` | whole-screen or acquisition-memory coverage, same-frame identity, trigger time, or that the event is inside the record |
| `requested_range_coverage` | an explicitly requested half-open descriptor range `[start, end)` is fully present, with its own slice SHA-256 | acquisition memory beyond the descriptor record, that the range contains the event, or any absolute time. Default is `UNVERIFIED` when no range was requested; an out-of-range request is `INCOMPLETE` for the target while `payload_integrity` stays `COMPLETE` |
| `frame_association` | never — always `UNVERIFIED` | that the payload, the display and any screenshot are the same acquisition; equal hashes and a recorded stop state do not create a frame identifier |
| `time_correspondence` | never — always `UNVERIFIED` | wall-clock time, trigger-instant alignment, or decoder bit boundaries |
| `analysis_capability` | the verdict is `OBSERVED` **and** no stated sampling requirement is contradicted; the verdict's own `claims` are exposed as sub-evidence | protocol decodability, option availability, sufficiency beyond the stated inequality, or any claim outside `can_claim` |

A `REFUSED` verdict always keeps `analysis_capability` at `UNVERIFIED`, and an
`OBSERVED` verdict on a record that misses an explicit `--max-sample-interval-s`
requirement also drops the axis. With no sampling requirement stated, the axis
may stay `COMPLETE` but `task_readiness` is `UNVERIFIED` and the report says
`task_readiness_not_established`. The requirement subfield is `MISSING`,
`SATISFIED` or `INSUFFICIENT`; a satisfied requirement proves one inequality and
never promotes the axis by itself.

Axis statuses are restricted to `COMPLETE`, `INCOMPLETE`, `INVALID`,
`UNVERIFIED`, `UNSUPPORTED`. `UNKNOWN` is not an axis status.

### Failure stages

Every report names the stage that produced it. Only the axes the stage could
actually evaluate are reported as evaluated.

| Stage | Cause | `payload_integrity` | Everything else |
|---|---|---|---|
| `input` | malformed arguments, `--max-json-bytes` outside `1..4194304`, `--out`/`--svg` inside the capture directory or equal to each other | `UNVERIFIED` — nothing was loaded | `UNVERIFIED` with the stage reason |
| `load` | the loader refused the stored data | mapped from the reason: `INVALID` for `LENGTH_MISMATCH`/`HASH_MISMATCH`/`DESCRIPTOR_MISMATCH`, `UNVERIFIED` for `MANIFEST_MISSING`/`CAPTURE_NOT_COMPLETE`/`CHANNEL_MISSING`/`AMBIGUOUS_CAPTURE`/`CALIBRATION_INCONSISTENT`, `UNSUPPORTED` for `WIDTH_UNSUPPORTED`/`NUMPY_UNAVAILABLE`/`DEPENDENCY_MISSING` | `UNVERIFIED` |
| `analysis` | the verdict raised after the payload was already validated | stays `COMPLETE` | `analysis_capability` becomes `UNVERIFIED` with `analysis_failed:<code>`; the report is still delivered with exit `2` |
| `output` | a target could not be reserved or written, or the report cannot fit the budget | stays `COMPLETE` | the report is emitted with `operation_error.stage = output`; nothing is created or overwritten |

`limitations` always contains `<stage>_failed:<code>` and
`a_refused_run_is_not_evidence_of_absence`. A refused load is not `INCOMPLETE`
payload and not an empty record; do not work around it by globbing `*.bin`.

### Delivery contract

- `--out` and `--svg` must be different paths outside the capture directory. The
  request is rejected before anything is read or written.
- No existing file is overwritten: each target is reserved exclusively before
  any bytes are written, and a failed reservation removes what it created.
- Without `--out` the JSON goes to stdout. `--svg` still has to be a file.
- Exit code is `0` only when `stage` is `complete`; every other outcome exits
  `2` with the same schema plus `error` and `operation_error` where applicable.
- Every axis `status`, the report `stage`, and the `truncated` flag are the
  fields to read first; the per-axis `reasons` explain them.

### Sparse candidate review after a refusal

When the verdict refuses because the level split is unresolved, the report
reuses the candidate excursions the refusal already localized; it never adds
thresholds or re-runs a heuristic. `sparse_candidates` then reports
`status = CANDIDATES_ONLY`, the full-record original-resolution scan scope,
record SHA-256, detection resolution, `candidate_count`, `candidates_returned`,
`candidates_truncated`, the parent verdict (unchanged, still `REFUSED`), and a
bounded `selection` with `policy = first_n_candidates_in_record_order`.
`all_candidates_reviewed` is `false`, and `windows_truncated` says whether the
JSON budget trimmed the selection. Those windows are observations of raw
samples: not levels, edges, pulses, protocol activity, absence or stability, and
never a review of every candidate.

## The SVG contract

`--svg` writes a bounded, dependency-free SVG of the selected candidate windows.

- The x axis is the sample index of the record; the y axis is the raw ADC code
  for an integer record and the captured sample value for a floating-point one.
  The document states which.
- Circles are the stored samples at original resolution. The connecting polyline
  is a display aid only: nothing about the signal between the markers is
  claimed.
- Each row is annotated with the candidate index, the half-open sample range, the
  observed value range and the first twelve hex characters of that window's
  SHA-256, so the window can be found again in the record.
- The document carries the record SHA-256, the channel, and the generator name.

The JSON reports `svg.written`, `bytes`, `sha256`, `axes`,
`markers = one_circle_per_raw_sample`,
`polyline = display_aid_only_connects_the_markers`, `windows_plotted`,
`points_plotted`, and `does_not_establish`
(`voltage_or_protocol_behaviour`, `any_sample_between_the_plotted_indices`,
`a_hardware_screenshot_or_display_state`). When no window was selected it
reports `written: false` with `no_candidate_window_was_selected`.

An SVG is a plotting aid, not evidence of the frame, the voltage, or the
instrument's display.

## What is never upgraded

- `payload_integrity` is always quoted with its scope words. "The record is
  complete" is true only of the stored descriptor record.
- `frame_association` and `time_correspondence` never leave `UNVERIFIED`, no
  matter how many hashes match, whether a stop state was recorded, or whether a
  screenshot file exists.
- A satisfied sampling requirement proves one inequality, not that a bus is
  decodable, a decoder present, or the capture adequate for the task.
- An offline test run never upgrades a voltage or a hardware claim; only a
  recorded instrument reading and a `PASS` inside the stated tolerance support a
  level, and each such claim names the model, firmware, interface and date.
