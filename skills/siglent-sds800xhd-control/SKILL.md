---
name: siglent-sds800xhd-control
description: Control and capture waveforms from a Siglent SDS800X HD series oscilloscope (verified on SDS824X HD) over one explicit raw SCPI TCP session. Use for single-shot captures, waveform downloads, signal measurements, screenshots, protocol decode, anomaly search, and progressive task-specific SCPI command discovery.
---

# Siglent SDS800X HD Control

Use this skill whenever an AI needs to operate an SDS800X HD series oscilloscope, capture a stopped frame, download waveform data, decode it, or diagnose a mismatch between screen record length and downloaded files. The series shares one platform and command set; every behavior here was verified on an SDS824X HD. Capabilities that depend on channel count, bandwidth, or memory depth (2 vs 4 channels, 50 vs 100 Mpts) must be confirmed against the connected model.

## Non-negotiable Safety Rules

- Never send `ARM`. `TRMD SINGLE` is the only accepted single-shot start operation on firmware `4.8.12.1.1.6.5`. `TRMD` is a firmware-verified short form; the manual's documented spelling is `:TRIGger:MODE SINGle`, which is the same operation (manual printed pp. 243-244). The manual contains no `ARM` command at all, and the target firmware rejected it; both facts stay, but attribute them correctly.
- A valid capture requires the observed state transition `Ready -> Stop`. A `Stop` observed without a prior `Ready` is not proof of a new capture.
- Roll mode (`:ACQuire:MODE ROLL`) never reports `Ready`; it is a streaming display, not a capture path. Leave it with `:ACQuire:MODE YT` before arming, and never treat `Roll` as `Ready` or as a `Stop` precursor.
- After `Stop`, do not send `STOP`, `ARM`, `RUN`, `TRMD`, trigger/timebase/channel configuration, `WFSU`, or a TCP reconnect while reading the frame.
- In an immutable legacy read, issue every channel's `WF? DAT2` first. Only after all payloads are saved may the caller explicitly issue `WF? DESC`.
- Keep `immutable_capture` and `configured_capture` explicit. Never silently send `WFSU`, restore `TRMD`, or clean up the instrument.
- Never use `max_points` as evidence of instrument record length. It is only a local CSV/downsampling setting.
- Preserve raw payloads and metadata before producing CSV. A short payload is `INCOMPLETE` or `INVALID`, never complete.

## Progressive Query Reference

Load only the reference matching the current debugging goal. Do not read every command reference up front, and do not expose unrelated configuration commands in the active workflow.

| Goal or observation | Read this reference |
|---|---|
| Automatically discover a scope, verify USB/LAN identity, configure the basic connection, choose a storage transfer path, or lock/release the front panel | [Connection and storage guidance](references/connection-and-storage.md) |
| Identify the scope, find a signal, auto-range, inspect trigger/acquisition state, or evaluate voltage/timing/jitter | [Signal discovery and measurement](references/signal-discovery-and-measurement.md) |
| Inspect waveform shape visually, fetch a screenshot, or download samples for external analysis | [Screenshot and waveform data](references/screenshot-and-waveform.md) |
| Diagnose UART/I2C/SPI/CAN/LIN or another supported serial bus | [Protocol decode](references/protocol-decode.md) |
| Find runt pulses, glitches, timing violations, mask failures, or replay a captured fault | [Anomaly search and mask testing](references/anomaly-search-and-mask-testing.md) |
| Measure long-term frequency/period statistics, inspect cursor deltas, or inspect history timestamps | [Counter, cursor, and history](references/counter-cursor-and-history.md) |
| Cross-check a command across subsystems, or answer a command question no task reference covers | [Command reference (fallback)](references/command-reference.md) |

The fallback command index is not a starting point: use it only after the matching task reference and the bundled scripts fail to answer the command question. It indexes only the commands this Skill already records; anything missing from it must be verified against the programming guide and labelled `documented` before use, and the safety rules above always take precedence.

Every setting has both a read and a write form. Reads are the default and are safe at any time; writes change the acquisition context, so they belong before `TRMD SINGLE` and never during a stopped-frame read. The most often missed writes are `:ACQuire:MMANagement`/`:ACQuire:SRATe` (sample rate only applies in `FSRate` mode), `:TRIGger:TYPE` (runt/pulse/serial triggering), `:SEARch` and `:MTESt` enable, `:MEASure:SIMPle:ITEM`, and `:FORMat:DATA` (default precision is only 3 significant digits).

Start with the matching reference's read-only snapshot. Use a setup/enable command only when that workflow requires it and the caller authorized changing scope state. Each reference distinguishes target-hardware-tested behavior from manual-documented behavior and notes feature prerequisites.

## Raw TCP Session

1. Connect once to SCPI TCP port `5025`; do not use legacy shell port `5024`.
2. Send `*IDN?` and save the returned identity before issuing model-specific commands.
3. Use `scripts/scope_protocol.py` for byte-preserving raw TCP queries and IEEE 488.2 blocks; use `scripts/capture_scope.py` for complete segmented waveform downloads. `:PRINt?` screenshots are the exception — raw PNG stream, no block header (see Binary Response Rules).
4. Apply channel or acquisition configuration only when explicitly requested, and do it before starting a new single acquisition.
5. Start a single acquisition with `TRMD SINGLE`; never send `ARM`. Poll `SAST?` until `Ready`, stimulate the DUT, then poll until `Stop`. Do not automatically retry.
6. Keep the same socket session for the complete capture. Do not trigger and then reconnect to read the frame.
7. Treat an export as unverified unless raw payload length and descriptor point count agree. A CSV or downsampled view alone does not prove a complete capture.

## Hardware Profile

- Supported series: `SDS800X HD` — SDS802X HD, SDS804X HD, SDS812X HD, SDS814X HD, SDS822X HD, SDS824X HD (2- or 4-channel, 70/100/200 MHz, 50 or 100 Mpts).
- Verified target: `Siglent SDS824X HD`, IP `192.168.10.2`, SCPI TCP `5025`, firmware `4.8.12.1.1.6.5`.
- Port `5024` is a legacy shell-like channel. It may begin with `Welcome to the SCPI instrument 'Siglent SDS824X HD'` and `>>`; never parse either as a query result.
- Channel mapping: `C1=ENABLE`, `C2=nFAULT`, `C3=HOC`, `C4=P4.1/CMP`.
- Typical setup: C1/C2/C4 `VDIV 2`, C3 `VDIV 5`, all `OFST 0`, probe `10`; edge trigger on C1 rising at `2.5 V`; `TRMD SINGLE`; `500 ms/div`; `5.00 MSa/s`; `25.0 Mpts`; about `-2 s` trigger delay.
- Expected record: `25,000,000` points, `200 ns` per point, `5 s`.
- Sample rate is only directly settable in `:ACQuire:MMANagement FSRate` mode; the typical setup above observed `5.00 MSa/s` in the default management mode, which derives it from the timebase.
- Front-panel lock is the explicit `:SYSTem:REMote ON|OFF` state (manual printed p. 264), not a side effect of opening a TCP session.

## Approved Workflows

### New Capture

1. Connect once and identify the scope.
2. Snapshot configuration before changing anything.
3. If requested, configure channels and trigger before starting acquisition.
4. Issue `TRMD SINGLE`; never issue `ARM`.
5. Poll `SAST?` until `Ready`; stimulate the DUT; poll until `Stop`.
6. Freeze the command set. Do not restore `TRMD AUTO` automatically.
7. For a full-length transfer, use the modern segmented path with the bundled script. Treat it as `configured_capture` because the scope receives transfer-selection writes after `Stop`; the path is verified for complete transfer integrity, but it is not called immutable:
   - `WAV:SOURce Cn`
   - `WAV:WIDTh WORD` when the preamble reports more than 8 nominal bits; use `--wav-width byte` only for an explicitly labeled lossy historical comparison
   - `WAV:BYTeorder LSB` for WORD transfers, followed by `WAV:BYT?` readback
   - `WAV:INTerval 1`, then verify `WAV:INT?` is `1`
   - `WAV:STARt <start>`
   - `WAV:POINt <count>`
   - `WAV:DATA?`
8. Save one raw binary file and one metadata file per segment. For BYTE expect `count` payload bytes; for WORD expect `count * 2` payload bytes. Check each returned payload length and checksum. On the verified firmware, requests above 250,000 points were observed to return 250,000 points while `WAV:POIN?` echoed the request; this is not a universal limit, and the payload length is authoritative.
9. Build the full report only after all segments have contiguous ranges from `0` through `array_count - 1`.

For a trigger-following burst, configure the optional horizontal strategy before step 4:

```text
python3 scripts/capture_scope.py \
  --out /path/to/capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --prepare --trigger \
  --left-aligned-trigger --trigger-margin-div 1 \
  --memory-depth auto --reference-position 10 \
  --wav-width auto
```

This queries `TIM:SCAL?`, sets `TIM:DEL = (5 - margin_div) * timebase`, and verifies the timebase, delay, memory-depth, and optional `TIM:REF:POS` readbacks before `TRMD SINGLE`. With `margin_div=1`, the trigger has one division of pre-trigger context and nine divisions of post-trigger window. The strategy is opt-in and is not valid with `--existing-stopped`; use a larger margin when pre-trigger history is important.

Example for the current stopped C4 frame:

```text
python3 scripts/capture_scope.py \
  --host 192.168.10.2 --port 5025 \
  --out /path/to/c4-capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --existing-stopped --segment-points 5000000 \
  --probe-points 10000,1000000 \
  --wav-width auto
```

The command writes `C4/segment-*.bin`, response/prefix files, per-segment JSON, `C4/waveform.bin`, and `manifest.json`. It creates `waveform.bin` only after the complete range validates.

### Existing Immutable Stopped Frame

Use this only when the caller explicitly says the current stopped frame is the target.

1. Do not send `STOP`, `TRMD`, `RUN`, `ARM`, `WFSU`, or configuration writes.
2. Read `C1:WF? DAT2`, `C2:WF? DAT2`, `C3:WF? DAT2`, and `C4:WF? DAT2` as requested; save every raw response.
3. After all DAT2 reads finish, optionally issue `C<n>:WF? DESC` as a separate explicit diagnostic step.
4. Compare `array_count`/`data_length` from the descriptor with actual payload bytes. For 8-bit DAT2, bytes equal points.

### Configured Repetitive Capture

This is not immutable. It may use `WFSU SP,1,NP,0,FP,0` before the new `TRMD SINGLE` capture and may select a fresh waveform memory view. Label artifacts `configured_capture`, record every WFSU command, and do not use the result to make claims about the original stopped frame. Never send WFSU after `Stop` in a stopped-frame read.

## Binary Response Rules

Use `scripts/scope_protocol.py` for all byte parsing of **waveform** responses. `:PRINt?` is the documented exception and needs its own bounded reader; see below.

- Search until `#` is found; arbitrary ASCII, NUL bytes, prompts, and status bytes may precede it.
- Read one ASCII digit `N`, then exactly `N` ASCII decimal length bytes, then exactly that many payload bytes.
- Validate the payload length. Keep `prefix`, the complete block header, payload, and SHA-256.
- A payload may contain `#`, NUL, CR, or LF; never split it on lines.
- A timeout, missing marker, non-decimal length, or short payload fails closed.
- **`:PRINt?` carries no IEEE 488.2 block header** on firmware `4.8.12.1.1.6.5`: it answers with a raw PNG stream closed by a single `LF`, so the rules above do not apply and `query_block()` legitimately fails with `invalid IEEE length-of-length`. Read bounded bytes until the `IEND` chunk plus that trailing `LF`, keep the SHA-256, and never `readline()` a screenshot. No bundled script implements this reader yet; it has to be written at the call site. See [Screenshot and waveform data](references/screenshot-and-waveform.md).

## Local AI Waveform Analysis

Use the bundled read-only analyzer after a capture has produced a complete `manifest.json`. It never reconnects to or writes the oscilloscope and it never replaces the raw `waveform.bin` evidence:

### Mandatory analysis gate

Evidence labels in this section are `firmware-scoped`: SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP `5025`.

Before making any conclusion about periodic-signal presence/absence, drive, frequency stability/change, duty/pulse timing, or a long record's phases, the agent must:

0. **Prove the thresholds are placed on the signal's own levels, not on its noise.** The analyzer only reports whether a threshold was *reached*, never whether it was *reached in the right place*: a threshold sitting inside the noise band returns a perfectly healthy `OBSERVED` / `low_duty_pulse_train` result whose silent prefix, first-edge time and pulse count are all wrong, with no field flagging it. Derive the levels first from `summarize.summary.percentiles_v` (calibrated) or `percentiles_code` (code domain — the two are mutually exclusive: a `VALID` calibration emits only the `_v` family plus `underlying_code_statistics`, which carries min/max but no percentiles). Place `high` under the code where p95 and p99 coincide and `low` above p50; for a bipolar or multi-level record take the boundary codes from a deliberately low `structure` pass and read `edges.items[].before_code` / `after_code`. `summarize` accepts no time range, so a whole-record percentile describes the whole record only — reproduce any single-region claim with a sub-range `structure` pass. `firmware-scoped` failure: on a 5 s record whose first 0.45 s sat at a 0.02–0.4 V noise floor, thresholds of 0.13/0.39 V moved the first edge from 0.0962 s to -0.4141 s (silent prefix 0.086 s instead of 0.596 s), added 67 spurious crossings, and still reported `status = OBSERVED`. State the evidence for each threshold pair you use.
1. Run `structure` on the **full record** at original resolution with explicit hysteresis thresholds. Inspect `coverage.full_record_scanned`, `edges.items_complete`, `pulses.items_complete`, and `evidence.observation_status`. If any is incomplete, truncated, `UNVERIFIED`, or limited to a time subrange, state the limitation and do not make a record-wide claim.
2. If the structure contains at least two complete cycles or the task asks whether a periodic regime changed, run `regimes` on the **same full record, channel, thresholds, and calibration context**. Inspect `data_integrity_status`, `segmentation_status`, `overall_status`, `coverage.count_reconciliation.reconciles`, regime/transition/cycle counts, unresolved phases, anomalies, and each returned item's completeness flags before drawing conclusions.
3. Reconcile each claim with the returned per-cycle values and edge/pulse references. Report every regime and every unresolved candidate phase, including brief phases; do not summarize away a detected stage or anomaly. Use `window` only to inspect samples around referenced transitions/anomalies, never as a replacement for full-record structure.
4. **Re-scan at a second threshold pair whenever the pulse table shows paired or equal-width pulses** — that is the signature of one real pulse being cut into several segments by an intermediate level. `pulse_clusters` cannot reveal this: grouping is by low-level gap only, so a split pulse stays one cluster and `cluster_count` is a correct computation, just not a description of the sub-structure. `firmware-scoped` example: one 136.25 ms gate cycle held a 45.2 ms high, a 0.2 ms notch, a 0.03 ms spike and another 45.2 ms high, so a single threshold reported `continuous_carrier`, `cluster_count=1`, 133 pulses, and nothing marked the split. Report the levels separately instead of claiming one pulse count.

If the waveform is not periodic/pulse-like, explicitly mark regime segmentation as not applicable and state which structure evidence supports that choice. If cycle support is insufficient, or any output is truncated/prefix-only, report the stage analysis as unresolved/`UNVERIFIED`; do not silently skip the regime pass and do not convert missing evidence into a negative claim. `inspect`, `summarize`, a screenshot, `events` pagination, and an M4/stride preview alone do not satisfy this gate.

Two fields mean "you are not looking at the whole record": `status=UNVERIFIED` with `edges.count_is_lower_bound=true` (the edge budget stopped the scan) and `truncated=true` with `items_complete=false` (the JSON budget kept a prefix). `classification` and `pulse_clusters.count` are computed **before** truncation and stay authoritative, but any later statistic over `edges.items` / `pulses.items` is prefix-only. Check `count` against `returned` before reusing either list.

```text
python3 scripts/analyze_waveform.py inspect --capture /path/to/capture --channel C4
python3 scripts/analyze_waveform.py summarize --capture /path/to/capture --channel C4 --preview-buckets 256
python3 scripts/analyze_waveform.py events --capture /path/to/capture --channel C4 --threshold-codes 20 35 --limit 100
python3 scripts/analyze_waveform.py window --capture /path/to/capture --channel C4 --start 123456 --count 512
python3 scripts/analyze_waveform.py events --capture /path/to/capture --channel C4 --threshold-codes 20 35 --start-time 2.01795 --end-time 2.01805 --limit 20
python3 scripts/analyze_waveform.py structure --capture /path/to/capture --channel C4 --threshold-codes 20 35
python3 scripts/analyze_waveform.py structure --capture /path/to/capture --channel C4 --threshold-volts 0.8 2.0 --cluster-gap-s 0.002 --max-edges 20000
python3 scripts/analyze_waveform.py regimes --capture /path/to/capture --channel C4 --threshold-codes 20 35 --measures auto --min-cycles-per-side 5
python3 scripts/analyze_waveform.py ringing --capture /path/to/capture --channel C4 --start-time 2.01795 --end-time 2.01805
python3 scripts/analyze_waveform.py window --capture /path/to/capture --channel C4 --start-time 2.01795 --end-time 2.01805
```

The analyzer validates the complete frame, merged file size, SHA-256, segment ranges, actual payload point counts, width, byte order, and sampling metadata before reading samples through NumPy `memmap`. It scans large records in bounded chunks and returns compact JSON rather than raw arrays. `summarize` reports exact integer-code statistics and an M4 preview labeled `visualization_only_lossy`; the preview must not be used as a substitute for event detection. To detect narrow pulses, scan the full record or use original-resolution extrema/event detection; do not use one-point or mean sampling as evidence that a signal is absent. `events` scans original-resolution samples and returns bounded pages with a stateless cursor; `--start-time/--end-time` limits the scan to a relative display-time range. `window` is the escalation path for inspecting samples around an event and accepts either sample indices or a half-open time range. `ringing` analyzes one bounded local window and reports heuristic edge overshoot, undershoot, residual crossings, frequency, and decay when enough evidence exists. It does not return a full local array, so call `window` separately when the AI needs the raw samples.

`structure` is the raw-edge fact layer: it scans every original sample (`evidence.raw_scan = true`, `evidence.stride_used = 1`) and returns the ordered edge table - event id, direction, sample, time, before/after codes, same-direction interval, and time uncertainty - rather than a paged view.

A clean-looking `status = OBSERVED` does **not** mean the thresholds were placed correctly; see gate step 0 for the placement evidence each threshold pair needs. No output field evaluates whether the chosen levels belong to the signal or to its noise.

A pulse table with **paired or equal-width pulses** (for example two 45.2 ms pulses separated by a 0.2 ms notch and a 0.03 ms spike) means one physical pulse is being cut by an intermediate level the thresholds do not represent; re-scan at the intermediate level rather than reporting the split count. `pulse_clusters` groups by low-level gap only, so it stays silent about this split.

`regimes` is a second analysis layer that derives complete cycle measurements from this raw structure and groups sustained changes into stages; it does not replace the edge table or the original capture. Rising and falling edges are paired in raw order into `pulses` with start/end sample and time, width, code levels, thresholds, boundary flags, and `status`; a high interval without a matching edge inside the scanned range is `INCOMPLETE` and is never padded. Pulses are grouped into `pulse_clusters` by a low-level gap that defaults to three times the observed median pulse period (or eight sample intervals when no period evidence exists) unless `--cluster-gap-s` is given; there is no fixed millisecond window. The result is labelled `continuous_carrier`, `short_burst`, `low_duty_pulse_train`, `pulse_train`, `single_pulse`, `no_crossing_observed`, or `insufficient_evidence`, and every label carries `classification.basis`, `classification.metrics`, and `classification.evidence` (edge ids, pulse ids, sample range) so it can be re-derived from raw samples.

`structure` fails closed on volume. `--max-edges` is a hard edge budget: when it is exceeded the response is `classification.status = UNVERIFIED` with `edges.count_is_lower_bound = true`, `edges.lower_bound`, `pulses.status = UNVERIFIED`, and `full_record_scanned = false`, never a silently truncated table presented as complete. JSON bounding is a separate, also explicit limit: when `--max-json-bytes` shortens `edges.items`, `pulses.items`, or `pulse_clusters.items`, the section keeps its authoritative `count` and reports `items_truncated = true`, `items_complete = false`, and the `json_output_truncated_items_are_prefixes` limitation.

`firmware-scoped` operational limit: `--max-json-bytes` is capped at 4 MiB, and the bounding loop re-serializes the whole document for every item it removes. A 25 M-point, 5 s record containing a 19.92 kHz pulse train (about 20 000 pulses / 39 000 edges) did not finish a single full-record `structure` call in 25 minutes, and `regimes` on the same record behaved the same way. Cover such a record with **contiguous sub-range windows that each fit under the budget** (`--max-json-bytes 4194304`; 0.2 s windows over 5 s took about 12 s in total, each window `truncated=false` with `edge_scan_complete=true`), then reconcile the windows. Report the result as contiguous windowed coverage of the full record, quote the window boundaries, and never present a single sub-range scan as a full-record result. A window holding only one complete cycle legitimately returns `regimes` `UNSUPPORTED`; take that stage's regime evidence from a window with enough complete cycles and state which window it came from.

`regimes` autonomously considers supported per-cycle measurements by default (`--measures auto`), or accepts an explicit list such as `period_s,duty_cycle,high_width_s`. It can identify sustained period/frequency or pulse-shape changes, summarize each stage and flag isolated cycles as anomalies. The default transition rule needs at least five complete cycles on each side; shorter candidate stages and uncertain boundaries remain unresolved rather than being asserted as stable stages. Smooth monotonic drift is reported as trend evidence within a regime, not forced into step changes. Output separates `data_integrity_status` from `segmentation_status`; an intact capture with uncertain interpretation is not a corrupt/incomplete waveform. When `--max-edges`, `--max-cycles`, or JSON output limits are exceeded, inspect `overall_status`, `coverage`, and each section's `items_complete`/`items_truncated` before relying on the report.

The M4 preview from `summarize` and any local `[::stride]` decimation are visualization only. Never derive an absence, no-drive, or duration conclusion from an aggregate, a window count, a mean, a preview, or a decimated view; use `structure` (or `events` plus `window`) on original-resolution samples. A negative statement must state the detection capability behind it: `evidence.observation_status = NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY` together with `evidence.detection_resolution_s` and `evidence.minimum_detectable_pulse_s`. Features narrower than one sample interval between the two thresholds can be missed, so "no crossing observed" is not "no drive".

All analysis times are relative to the waveform display origin reported in `sampling.origin_s`, not wall-clock time. The time range is half-open: `[start-time, end-time)`. Do not combine time arguments with sample-index arguments. `ringing` marks windows touching the capture boundary, edges without enough pre-context, and ring-down that remains above noise at the window end; those flags prevent a local estimate from being mistaken for proof that the physical event ended.

WORD captures retain raw signed little-endian codes. Unless an independent calibration JSON is supplied, WORD analysis reports `OBSERVED_UNVERIFIED` and emits code-domain values only; a 16-bit transport container is not automatically treated as a 16-bit voltage-calibrated ADC result. That refusal is justified and must not be bypassed by arithmetic on the descriptor: the observed descriptor `code_per_div=30` with `vdiv_with_probe=2 V/div` implies 0.0667 V/code (15 codes/V), while the same frame's own `:MEASure:SIMPle:VALue? PKPK` gives **3840 codes/V** - a factor of 256. A usable calibration can still be derived without any screenshot by dividing each channel's raw code span by the scope's PKPK reading for that channel; four channels agreed to four significant digits (C1 5.23333 V, C2 3.49583 V, C3 5.51667 V, C4 5.75417 V against raw spans giving 3840 codes/V on every channel). Write that into the calibration JSON shape below and the analyzer reports `status = VALID`, enabling `--threshold-volts`. BYTE voltage conversion uses descriptor VDIV, probe factor, offset, and codes/div after cross-checking the captured panel snapshot and a known logic-level channel such as ENABLE. A mismatch is reported as a calibration limitation rather than used to produce voltage fields. An observer/probe at the same frequency as the measured signal can alias into a false state change; use an unrelated observation rate or a discriminating comparator output. Interpret counter hypotheses only when they explain all observations, including periodic retry windows. The instrument's own whole-frame simple measurements are a magnitude check only: on a record that spent most of its length at 19.92 kHz, the whole-frame `FREQ` reported 7.3433 Hz, `PWID` reported the stage-1 45.4248 ms, and `DUTY` reported 33.357 %, so a whole-frame reading must never be used as the stage description. Analysis output defaults to stdout and must be written outside the raw capture directory with `--out`.

An independent WORD calibration file must bind evidence to the exact merged waveform SHA-256 and use this minimum shape:

```json
{
  "channels": {
    "C4": {
      "word_scale_verified": true,
      "capture_sha256": "<merged waveform SHA-256>",
      "word_codes_per_div": 19200,
      "vdiv_v_per_div": 5.0,
      "offset_v": 0.0,
      "evidence": "known DC reference and BYTE/WORD comparison"
    }
  }
}
```

The analyzer computes `code_scale_v = vdiv_v_per_div / word_codes_per_div`, so the two fields are only meaningful **together**: `word_codes_per_div` is codes per division *at that same panel V/div*, never codes per volt. The firmware-verified frame above ran C4 at `2 V/div` and produced `7680` codes/division, i.e. 3840 codes/V; the 5 V/div example therefore carries `3840 * 5 = 19200`, not `7680`. Copying the 7680 from a 2 V/div frame into a 5 V/div entry scales every resulting voltage by 2.5 and still reports `status = VALID` — the loader validates the hash, the boolean, the sign and a non-empty evidence string, but never cross-checks the two numbers against the frame's own span. Either supply `vdiv_v_per_div` equal to the panel setting of the frame being calibrated, or verify `word_codes_per_div / vdiv_v_per_div` against `(max_code - min_code) / PKPK` from the same frame.

The analyzer rejects stale or incomplete evidence back to code-domain output. It does not infer WORD voltage scaling from `code_per_div * 256` alone.

Deriving the scale from the frame's own `:MEASure:SIMPle:VALue? PKPK` is an **internal consistency check, not an independent voltage calibration**: both numbers come from the same instrument and the same acquisition. It is sufficient to place thresholds correctly and to reproduce the instrument's own readings, and it must be labelled that way (`OBSERVED_UNVERIFIED` for absolute accuracy). An independently verified scale needs a traceable reference such as a known DC source.

## Waveform Decode and Validation

For modern `WAVeform:PREamble?`, parse the documented little-endian fields in `scripts/scope_protocol.py`. Keep at least `wave_array_1`, `wave_array_count`, `start`, `interval`, `vdiv`, `offset`, `code_per_div`, `adc_bit`, `sample_interval`, `delay`, `tdiv`, and `probe`.

For BYTE data, decode signed samples as `byte - 256 if byte > 127 else byte`. Use `vdiv / code_per_div`; do not hard-code `/32`. For WORD data, retain the raw two-byte LSB payload and report `voltage_decode=unverified_for_WORD` until the device-specific left-alignment ratio is independently calibrated. A 16-bit transport container must not be called a 16-bit ADC result. The current observed descriptor reports `nominal_bits=16`, `code_per_div=30`, and `MAX_VALUE=7680`; the WORD transfer has been hardware-verified for byte completeness, not voltage scaling.

Use the validator to report all three quantities:

```text
scope_record = 25,000,000 points / 5 s
wavedesc     = 25,000,000 points / 5 s
downloaded   = 5,000,000 points / 1 s
status       = INCOMPLETE
```

Any empty, truncated, wrong-width, overlapping, or missing segment invalidates the complete channel. Do not infer missing samples or silently pad.

## Bundled Resources

- `scripts/scope_protocol.py`: byte-preserving TCP session, IEEE 488.2 block reader, preamble/descriptor parser, segment and frame validators. It does not implement the headerless `:PRINt?` PNG reader.
- `scripts/discover_scope.py`: read-only USBTMC/VISA and LAN `*IDN?` discovery; it never changes scope state or mounts storage.
- `scripts/capture_scope.py`: one-session raw TCP capture CLI with explicit immutable/configured modes, staged modern probes, complete segmented reads, and atomic merged output. `--prepare` is only valid with `--trigger`; `--existing-stopped` must never be combined with setup or trigger options.
- `scripts/test_scope_protocol.py`: offline tests for framing, 25M-vs-5M rejection, boundary errors, and WAVEDESC fields.
- `scripts/scope_protocol.py`: also exposes `configure_left_aligned_trigger` and `configure_memory_depth` for new captures; both preserve the no-`ARM` workflow.
- `scripts/waveform_analysis.py`: read-only manifest validation, BYTE/WORD memory-mapped access, exact bounded summaries, M4 visualization preview, time-ranged threshold/runt/long-interval events, full-resolution raw-edge pulse structure analysis (edges, pulses, pulse clusters, classification), per-cycle waveform regime segmentation, anomaly detection, raw window extraction, and bounded ringing screening.
- `scripts/analyze_waveform.py`: bounded JSON CLI with `inspect`, `summarize`, `events`, `structure`, `regimes`, `window`, and `ringing` subcommands.
- `scripts/test_waveform_analysis.py`: synthetic capture tests for integrity, relocation, BYTE/WORD behavior, statistics, M4 bounds, event chunk boundaries, cursors, scan budgets, sample/time windows, ringing estimates, window limits, raw-edge pulse structure reconstruction, and waveform regime changes/outliers/drift/boundaries/output budgets.
- Task-specific command references under `references/`: load only the page selected by the goal table above. `programming-guide.md` records waveform implementation notes and is not a general command catalog.
- `references/connection-and-storage.md`: discovery, connection configuration boundaries, USBTMC limitations, network storage, and direct binary transfer choices.

The protocol module exposes the handover API names: `scope_connect`, `scope_identify`, `scope_snapshot_configuration`, `scope_prepare_capture`, `scope_arm_single`, `scope_wait_ready`, `scope_wait_stop`, `scope_read_immutable_frame`, `scope_read_segment`, `scope_read_descriptor`, `scope_validate_frame`, `scope_restore_run_mode`, and `scope_disconnect`. `scope_arm_single` sends only `TRMD SINGLE`, never `ARM`. Descriptor reads remain an explicit post-download action.
- `references/programming-guide.md`: command semantics and manual page references used by this skill.

Run `python3 scripts/test_scope_protocol.py` and `python3 scripts/test_waveform_analysis.py` before relying on modified transport or analysis code. On firmware `4.8.12.1.1.6.5`, C4 passed both transport checks: the historical BYTE run returned `25,000,000` bytes; the automatic WORD run selected WORD from `nominal_bits=16`, read back `COMM_TYPE=1`/LSB and `WAV:INT=1`, and returned `25,000,000` points / `50,000,000` bytes over five segments. Both had a calculated `5.000000058 s` span and no `ARM`, `STOP`, `TRMD`, or `WFSU` writes. The analyzer accepts the historical BYTE artifact and reports verified BYTE voltage fields; it intentionally keeps WORD voltage scaling `OBSERVED_UNVERIFIED` until an independent calibration artifact is supplied.
