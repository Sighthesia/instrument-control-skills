# Waveform Evidence Report

Load this reference when a capture must be described as an evidence package instead of a single verdict: when a `verdict` is `REFUSED` but a sparse event may exist, when someone asks whether a downloaded record is "complete", "the same frame", or "the same time as the screenshot", or when a conclusion needs its scope stated before it can be trusted.

Do not read a million waveform points to answer those questions. Run the report, read its five axes, read its limitations and conflicts, and inspect only the bounded windows it returns.

```bash
python3 scripts/waveform_evidence.py --capture /path/to/capture --channel C1 --out /outside/path/evidence.json
python3 scripts/waveform_evidence.py --capture /path/to/capture --channel C1 \
    --range-start 150000 --range-end 175000 \
    --max-sample-interval-s 2e-6 --sampling-requirement-source "task states 500 kSa/s minimum" \
    --candidate-windows 4 --candidate-window-points 1024 \
    --svg /outside/path/evidence.svg --out /outside/path/evidence.json
```

`--out` and `--svg` must be different paths outside the raw capture directory; the tool rejects that request before reading or writing anything, never overwrites an existing file (including a symlink or hardlink target), reserves each target exclusively before writing, and enforces `--max-json-bytes` as a hard bound on the report it produces. On a successful run the report is emitted and the exit code is `0`; a failed stage is explained in the same schema with exit code `2` (see *Failure stages* below). The tool never contacts an instrument and is offline-tested only; it has not been exercised against a physical scope.

## The five axes

Each axis carries `status`, `scope`, `reasons`, and `evidence`. The axes are deliberately independent: satisfying one never satisfies another.

| Axis | What `COMPLETE`/`SATISFIED` means | What it never means |
|---|---|---|
| `payload_integrity` | The downloaded descriptor record matches its own declared point count, byte width, segment ranges/sizes and SHA-256 values. Scope is `descriptor_record_download_only`. | Whole-screen or acquisition-memory coverage, same-frame identity, correct trigger time, or that the event of interest is inside the record. |
| `requested_range_coverage` | An explicitly requested half-open descriptor sample range `[start, end)` is fully present, with its own slice SHA-256. Default is `UNVERIFIED` when no range was requested. | Acquisition memory beyond the descriptor record, that the range contains the event, or any absolute time. An out-of-range request is `INCOMPLETE` for the target only; `payload_integrity` stays `COMPLETE`. |
| `frame_association` | Never. The status is always `UNVERIFIED`: no command in this Skill returns a shared frame identifier, and stop states, acquisition counters or matching hashes do not create one. | That the download, the display and any screenshot are the same acquisition. A valid PNG container never upgrades this, and a file-hash match only proves the file was not altered. |
| `time_correspondence` | Never. The status stays `UNVERIFIED`: descriptor-relative sample time is analyzable, absolute/trigger-locked time is not. | Wall-clock time, trigger instant alignment, or decoder bit-boundary alignment. |
| `analysis_capability` | `COMPLETE` only when the verdict is `OBSERVED` **and** no stated sampling requirement is contradicted. A `REFUSED` verdict always keeps this axis `UNVERIFIED`. An `OBSERVED` verdict on a record that misses an explicit `--max-sample-interval-s` requirement also drops the axis to `UNVERIFIED`; the verdict stays visible as sub-evidence but is not task capability. With no sampling specification at all the axis may stay `COMPLETE`, but `task_readiness` is `UNVERIFIED` and the report says `task_readiness_not_established`. The requirement itself is a subfield (`MISSING`, `SATISFIED`, `INSUFFICIENT`); a satisfied requirement never promotes the axis by itself. | Protocol decodability, decoder/option availability, sufficiency beyond the stated inequality, or any claim outside `verdict.claims.can_claim`. An insufficient requirement adds `sampling_requirement_insufficient_for_the_stated_task` to `blocked_task_claims` without altering the original verdict evidence. |

Rules that follow from the table:

- Always report `payload_integrity` with its scope words. "The record is complete" is only true about the descriptor download.
- Never restate `frame_association` or `time_correspondence` as verified because a hash matched, a `SAST?` reply said `Stop`, an acquisition counter was unchanged, or a screenshot file exists.
- A satisfied sampling requirement proves one inequality. It does not declare a bus decodable, a decoder present, or a capture adequate for a protocol task. A completed verdict without a stated requirement is likewise not task-ready.
- Every axis `status` is one of `COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, `UNSUPPORTED`. `UNKNOWN` is not an axis status.

## Failure stages

Every report names the stage that produced it (`stage`, also inside `error.stage`). A failure is attributed to exactly one stage, and only the axes that the stage could actually evaluate are reported as evaluated:

| Stage | Cause | `payload_integrity` | Everything else |
|---|---|---|---|
| `input` | malformed caller arguments (range, candidate limits, sampling requirement, `--max-json-bytes`, `--out`/`--svg` paths) | `UNVERIFIED` — nothing was loaded, so no payload claim exists | `UNVERIFIED` with the stage reason; no axis is `COMPLETE` or `INVALID` |
| `load` | `load_capture` refused the stored data | mapped from the real reason: `INVALID` for `LENGTH_MISMATCH`/`HASH_MISMATCH`/`DESCRIPTOR_MISMATCH`, `UNVERIFIED` for `MANIFEST_MISSING`/`CAPTURE_NOT_COMPLETE`/`CHANNEL_MISSING`/`AMBIGUOUS_CAPTURE`/`CALIBRATION_INCONSISTENT`, `UNSUPPORTED` for `WIDTH_UNSUPPORTED`/`NUMPY_UNAVAILABLE` | `UNVERIFIED` |
| `analysis` | `build_verdict` raised; the payload already loaded and validated | stays `COMPLETE` | `analysis_capability` becomes `UNVERIFIED` with `analysis_failed:<code>`; the report is still delivered, exit code `2` |
| `output` | the JSON/SVG path could not be reserved or written, or the report cannot fit the hard budget | stays `COMPLETE` and the whole report is preserved | the report is emitted with `operation_error` (`stage = output`); no file is created or overwritten. If even the minimal report cannot fit, a short message goes to stderr and no JSON is produced |

`CAPTURE_NOT_COMPLETE` stays `UNVERIFIED` on purpose: `load_capture` uses it for any recorded `manifest.error` — which may be a permission, connection or unknown failure — and for a capture with no unique complete result, so the code alone never proves that samples are missing. `INCOMPLETE` is reserved for axes that can confirm a missing target, such as an out-of-range range request; a refused load is not evidence of incomplete data.

`limitations` always contains `<stage>_failed:<code>` and `a_refused_run_is_not_evidence_of_absence`. Do not relabel a refused load as `INCOMPLETE` payload or as an empty record, do not call an input or output problem a load failure, and do not parse `*.bin` files by glob to work around it.

## Sparse candidate review after a refusal

When `build_verdict` refuses because the level split is unresolved, it may already have localised candidate excursions with a full-resolution scan away from the record-median reference band. The evidence report reuses that result; it does not re-run heuristics or invent thresholds.

`sparse_candidates` then reports:

- `status = CANDIDATES_ONLY`, the scan scope (`full_record_original_resolution`), record points, record SHA-256, detection resolution, `candidate_count`, `candidates_returned`, `candidates_truncated`, and the scanner's own limitations (for example `candidates_capped_to_200_of_7262`).
- `parent_verdict`: `status = REFUSED` plus the refusal code and the original `can_claim`/`cannot_claim` lists. The parent refusal is never overwritten.
- `selection`: `policy = first_n_candidates_in_record_order`, bounded `max_windows` and `window_points`, `windows_selected`, and `all_candidates_reviewed = false`. The same `false` appears at the top of the block. The report never claims that the returned windows cover every candidate or the whole record.
- `windows`: bounded original-resolution windows. Each has `candidate_index`, candidate and window sample bounds, `covers_candidate`, descriptor time range, `record_sha256`, `codes_sha256` over the exact returned integer codes, the `codes` themselves, and `raw_code_domain_only` limitations.
- `observations`: one entry per returned window, in the same order and with the same `candidate_index`. Each entry has the window's min/max raw codes and the explicit statement that the observation is not a level, edge, pulse, protocol, or record-wide claim.
- `windows_truncated`: true when fewer windows were selected than candidates returned, or when the JSON budget forced trailing windows to be dropped.

If the report is too large for `--max-json-bytes`, trailing windows are dropped **together with their matching `observations` entries**, and `selection.windows_selected`, `truncated`, `windows_truncated` and the `svg` binding are updated in the same step. Counts and parent claims are preserved. If even the report without windows cannot fit, the run fails at the `output` stage: a short stderr message, exit code `2`, and no partial JSON.

### Optional raw-code SVG

`--svg <path>` writes a stdlib-only SVG with one panel per selected window: x is the sample index, y is the raw ADC code. Each raw sample is drawn as its own marker circle; the polyline only connects those markers as a display aid, so it is **not** evidence about samples between markers and the file does not claim interpolation-free rendering. The SVG is generated from the windows that survive the JSON budget, then the file is written, and the report binds it with `svg.sha256`, `svg.bytes`, `markers`, `points_plotted`, and `windows_plotted`. A raw-code plot is not voltage, not a decoded protocol, and not a display capture.

## How to review the report (AI protocol)

1. Read all five axes; a missing axis or an unreported scope is itself a finding. Do not summarise the report as a single pass/fail.
2. Quote each `status` together with its `scope`.
3. Read `limitations` and `conflicts` before interpreting anything. A `conflicts` entry means the evidence contradicts itself somewhere (for example a screenshot record that claims `container_valid` while its file is missing or its SHA-256 changed, or a recorded stop state that is not `STOP`).
4. For a refusal, read `parent_verdict.cannot_claim`, keep every entry, and inspect the returned windows or the SVG. State the selection policy and that the review is bounded.
5. Never convert a candidate window into a level, pulse width, protocol byte, absence proof, or stability claim. Local evidence is observation only; record-wide conclusions still need a passed full-resolution structure/regimes analysis on the same record, and an unresolved level split blocks them regardless of what a window shows.
6. Do not describe `payload_integrity = COMPLETE` as "the waveform is complete", and do not describe a candidate window as "the event was reviewed".

### Prohibited claims

- Same-frame identity between the download and the display or a screenshot.
- Absolute, trigger-locked, or wall-clock time from descriptor coordinates.
- Whole-record absence or stability from candidate localisation or from a bounded window subset.
- Protocol decodability from a satisfied sampling interval.
- An image claim from a PNG container check (`image_decode_status` is always `UNVERIFIED`).
- "All candidates reviewed" or "the record was fully scanned" when `all_candidates_reviewed` is `false` or `candidates_truncated` is `true`.

## Report shape (abridged)

```text
{
  "schema_version": "1.1", "tool": "evidence", "stage": "complete",
  "capture": { "channel", "raw_sha256", "points", "bytes", "sample_interval_s", "source_manifest_sha256", ... },
  "axes": { "payload_integrity", "requested_range_coverage", "frame_association", "time_correspondence", "analysis_capability" },
  "sparse_candidates": { "status", "candidate_count", "selection", "windows", "observations", "parent_verdict", ... } | null,
  "screenshot": { "present", "status", "container", "file_check", "frame_association", "conflicts" },
  "conflicts": [ { "code", "detail" } ],
  "limitations": [ ... ],
  "truncated": false,
  "svg": { "written", "sha256", "bytes", "windows_plotted", "points_plotted" }
}
```

## Evidence labels

- Axis statuses describe this report's own deterministic checks on the stored artifacts; they are not hardware-verified device behaviour.
- The report is `documented` + offline-tested. It makes no claim that the firmware behaves the same way on a different model or firmware build.
- Screenshot file checks only compare the recorded byte count and SHA-256; both must be present and well formed before a `MATCH` is possible. A missing count or hash is `UNVERIFIED`; a malformed one is `INVALID` and appears as a conflict. These outcomes are screenshot-only and never change `payload_integrity`, and they never establish that the PNG is decodable, viewable, correctly framed, or from the same acquisition.
