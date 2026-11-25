# Screenshot and Waveform Data

Load this reference when the agent needs visual inspection, raw waveform samples, or offline numerical analysis. Do not load decoder/search configuration unless the capture indicates a protocol or anomaly workflow.

> **A screenshot is qualitative context only.** It can show shape, overlap, and clipping; it can never establish that a channel carries no signal, is at 0 V, or is flat. The on-screen measurement panel belongs only to the selected simple-measurement source (`:MEASure:SIMPle:SOURce?`), not to a trigger or threshold source. Before any per-channel presence/absence statement, take the read-only snapshot in [Signal discovery and measurement](signal-discovery-and-measurement.md#per-channel-evidence-before-a-no-signal-verdict) (`scripts/channel_snapshot.py`) and record the raw replies.

## Screenshot

- **Manual-supported SCPI path**: `:PRINt? PNG` or `:PRINt? BMP[,NORMal|INVerted]`. The manual documents a binary *image* response but does not specify IEEE 488.2 block framing; `:PRINt?` is neither a scalar ASCII query nor a well-formed block. On firmware `4.8.12.1.1.6.5` the framing is a **raw PNG stream with no header** (see *Verified screenshot transfer* below): read bytes, never `readline()`, and do not call `query_block()`.
- `:PRINt?` cannot hide the on-screen menus. When a menu-free image is needed, use the file path instead: `:SAVe:IMAGe "<path>",<BMP|JPG|PNG>,<ON|OFF>,MOFf` (manual printed p. 203). `MOFf` hides the top and right menus, `MON` keeps them; `invert ON` gives a light background for printing. Paths are `local/...` (internal), `net_storage/...` (mounted share), or `U-disk0/...`. This writes a file, so it needs authorization and must not overwrite an existing name.
- Inspect screenshots for clipping, ringing, pulses, setup mistakes, and on-screen decode/status context. A screenshot is evidence of display state, not a substitute for complete samples or a measurement report.

### `firmware-scoped` screenshot transfer and per-region zoom (SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP 5025)

- `:PRINt? PNG` on this firmware answers with a **raw PNG stream and no IEEE 488.2 block header**, terminated by one `LF`. The first byte is the PNG signature (`89 50 4E 47 ...`), the last bytes are `... IEND AE 42 60 82 0A`; a `#` can appear inside the stream. `scope_protocol.query_block()` fails closed on it (`invalid IEEE length-of-length: b'~'`), which is correct: read until the `IEND` chunk plus the trailing `LF` with a byte bound and keep the SHA-256 instead of assuming block framing. Observed image: 1024 × 600 RGB, roughly 27–39 kB for a four-channel screen. `scripts/screenshot_capture.py` is the bundled reader for exactly this framing; it is documented and offline-tested, not yet exercised against a physical instrument, so its output is `documented` evidence plus structural verification, never `hardware-verified`.
- Standalone use: `python3 scripts/screenshot_capture.py --host <ip> --out <capture-dir>/shot.png`, with optional `--max-bytes` (default 8 MiB) and `--max-seconds` (default 15 s). A `.json` sidecar is written beside the PNG. `status = COMPLETE` and `container_valid = true` mean the signature, a legal IHDR bit-depth/colour-type pair, chunk order (IHDR first, contiguous `IDAT`, `PLTE` before `IDAT`, one `PLTE`, no unknown critical chunk), every chunk length and CRC, and `IEND` plus one `LF` were validated inside both bounds; a structural violation is `INVALID` and everything else is `INCOMPLETE`. The raw file always holds the bytes that arrived, including a partial or invalid stream. **Container validity is not image validity**: no PNG decoder runs, so `image_decode_status` stays `UNVERIFIED` and an empty or random `IDAT` whose CRCs are correct still passes the container check. Do not describe `container_valid` as a viewable, correct, or same-frame image. A non-finite or too-small bound is rejected before anything is created. The whole attempt including the TCP connect must fit `--max-seconds`, so the session timeout is `min(--timeout, --max-seconds)` while the requested value stays recorded as `requested_timeout_s` next to `session_timeout_s`. Existing artifacts are never replaced, a failed TCP connect produces a JSON record with no PNG, the pre-existing socket timeout is restored (a restore failure is recorded as `timeout_restore_error` beside the original outcome instead of replacing it), and no reconnect is attempted.
- `:PRINt?` is a query that carries an argument; it changes no acquisition state and is safe while a frame is stopped. It is the only argument-bearing command allowlisted after `Stop`: `scripts/scope_protocol.py` permits the exact `:PRINt? PNG` spelling and keeps `BMP`, `JPG`, extra arguments, or any other write forbidden.
- **A complete screenshot proves PNG container structure only.** It does not prove that the image is decodable or viewable, that it shows the same frame as a downloaded waveform, or that it covers the waveform samples. Every screenshot record carries `frame_association: UNVERIFIED` with its reason, and `image_decode_status: UNVERIFIED` because no decoder runs. With `capture_scope.py --screenshot`, the screenshot is attempted once on the same socket after all waveform payloads are written: a screenshot failure is recorded in `manifest.screenshot` and leaves the verified payload intact, the attempt is last so no query follows it, and the scope is never reconnected. Conversely, a failed waveform read means no screenshot is attempted.
- **Every screenshot record is explicitly qualitative.** The JSON carries `qualitative_only: true`, a `warning` string saying an image cannot establish presence, level, or a flat channel, and a `next_action` that points at `scripts/channel_snapshot.py`; the CLI prints the same record. Those fields are part of the contract, not decoration: a screenshot attempt never substitutes for per-channel read evidence, and a reading of the record that ignores the flag is a misreading.
- To compare different time regions of **one stopped frame**, zoom the display rather than re-arming: write `:TIMebase:SCALe` and `:TIMebase:DELay` only after that frame's waveform transfer is complete. `firmware-scoped` on the target: across six zoom changes the state stayed `Stop` and `:ACQuire:NUMACq?` did not change, so no new acquisition started. This is still forbidden *during* a stopped-frame read.
- `:MEASure:SIMPle` (source set with `:MEASure:SIMPle:SOURce`) evaluates the **zoomed window**, so a zoomed screenshot can carry a per-region instrument-side readout, e.g. `FREQ 7.3424889 Hz` / `PER 136.1936 ms` / `DUTY 33.367 %` at 50 ms/div versus `FREQ 19.920 kHz` / `PER 50.20 µs` / `DUTY 7.573 %` at 10 ms/div on the same frame. An item the scope cannot evaluate returns `****` (seen for `FREQ`, `PER`, `DUTY` on a window with no valid cycle). At the full-record zoom the same measurement collapses to one number and does not separate regions (`7.3433 Hz` for a record that was 19.92 kHz for most of its length), so a screenshot readout never replaces `structure`/`regimes` segmentation.
- `:DISPlay:PERSistence` (`OFF`, `INFinite`, `1S`, `5S`, `10S`, `30S` on SDS800X HD) keeps previous acquisitions on screen; it is how an intermittent glitch becomes visible in a screenshot at all. Record the setting with any screenshot used as evidence.

## Capture Workflows

Three capture modes exist and they are never mixed; label every artifact with the mode it was written under. Voltage and code scaling of the downloaded samples is in [Programming notes](programming-guide.md#word-and-byte-sample-decoding).

### New Capture

1. Connect once and identify the scope.
2. Snapshot configuration before changing anything.
3. If requested, configure channels and trigger before starting acquisition.
4. Issue `TRMD SINGLE`; never issue `ARM`.
5. Poll `SAST?` until `Ready`; stimulate the DUT; poll until `Stop`.
6. Freeze the command set. Do not restore `TRMD AUTO` automatically.
7. Download through the modern segmented path below. Treat it as `configured_capture`, because the scope receives transfer-selection writes after `Stop`; the path is verified for transfer integrity, but it is not immutable. Apply the commands in the order `WAV:SOURce Cn`, `WAV:WIDTh WORD` when the preamble reports more than 8 nominal bits (use `--wav-width byte` only for an explicitly labelled lossy historical comparison), `WAV:BYTeorder LSB` for WORD followed by a `WAV:BYT?` readback, `WAV:INTerval 1` verified through `WAV:INT?`, `WAV:STARt`, `WAV:POINt`, `WAV:DATA?`.
8. Save one raw binary file and one metadata file per segment. For BYTE expect `count` payload bytes, for WORD `count * 2`. On the verified firmware a request above 250,000 points returned 250,000 points while `WAV:POIN?` echoed the request; that value is not a universal limit, and the payload length is authoritative.
9. Build the full report only after all segments have contiguous ranges from `0` through `array_count - 1`.

For a trigger-following burst, configure the optional left-aligned horizontal strategy before step 4:

```text
python3 scripts/capture_scope.py \
  --out /path/to/capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --prepare --trigger \
  --left-aligned-trigger --trigger-margin-div 1 \
  --memory-depth auto --reference-position 10 \
  --wav-width auto
```

It queries `TIM:SCAL?`, sets `TIM:DEL = (5 - margin_div) * timebase`, and verifies the timebase, delay, memory-depth and optional `TIM:REF:POS` readbacks before `TRMD SINGLE`. With `margin_div=1` the trigger keeps one division of pre-trigger context and nine divisions of post-trigger window. The strategy is opt-in, invalid with `--existing-stopped`, and a larger margin is the right choice when pre-trigger history matters.

Example for an already stopped C4 frame:

```text
python3 scripts/capture_scope.py \
  --host 192.168.10.2 --port 5025 \
  --out /path/to/c4-capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --existing-stopped --segment-points 5000000 \
  --probe-points 10000,1000000 \
  --wav-width auto
```

It writes `C4/segment-*.bin`, response/prefix files, per-segment JSON, `C4/waveform.bin` and `manifest.json`, and creates `waveform.bin` only after the complete range validates. `--prepare` is valid only with `--trigger`, and `--existing-stopped` must never be combined with setup or trigger options. `--channel-mapping C1=ENABLE,C4=MISO` records a caller-declared name per channel as `channel_mapping` with `channel_mapping_source: user-supplied`; without the flag both keep `null`/`unknown`, because the scope exposes no name readback. `--screenshot` is opt-in: one `:PRINt? PNG` on the same socket, only after every waveform payload is saved, so a failed screenshot is recorded as `manifest.screenshot` and never downgrades verified payload integrity. Instrument measurements are read only after every requested payload and descriptor is saved, only the channel named by both `:MEASure:SIMPle:SOURce?` readbacks receives a numeric value, and a measurement transport failure keeps the frame, records `instrument_measurements_error`, and marks the requested screenshot `NOT_ATTEMPTED` instead of issuing another query.

### Existing Immutable Stopped Frame

Use this only when the caller explicitly says the current stopped frame is the target.

1. Do not send `STOP`, `TRMD`, `RUN`, `ARM`, `WFSU`, or configuration writes.
2. Read `C1:WF? DAT2`, `C2:WF? DAT2`, `C3:WF? DAT2` and `C4:WF? DAT2` as requested; save every raw response.
3. Only after all DAT2 reads finish, optionally issue `C<n>:WF? DESC` as a separate explicit diagnostic step.
4. Compare `array_count`/`data_length` from the descriptor with the actual payload bytes. For 8-bit DAT2, bytes equal points.

### Configured Repetitive Capture

This is not immutable. `WFSU SP,1,NP,0,FP,0` may be used before a new `TRMD SINGLE` capture and a fresh waveform-memory view may be selected. Label the artifacts `configured_capture`, record every WFSU command, and never use the result to make claims about the original stopped frame. Never send WFSU after `Stop` in a stopped-frame read.

## Preferred Modern Waveform Transfer

The following binary path is documented and the segmented C4 transfer was hardware-tested on firmware `4.8.12.1.1.6.5`:

```text
:WAVeform:SOURce Cn
:WAVeform:PREamble?
:WAVeform:MAXPoint?
:WAVeform:WIDTh WORD             # when selected from descriptor precision
:WAVeform:BYTeorder LSB          # WORD; query and verify readback
:WAVeform:INTerval 1
:WAVeform:STARt <zero-based-point>
:WAVeform:POINt <count>
:WAVeform:DATA?
:WAVeform:SEQuence?             # only when segmented acquisition is enabled
```

`SOURce`, width, byte order, interval, start, and point count are writes and therefore change the transfer view. After a single-shot `Stop`, this is the explicit `configured_capture` read path in this skill, not an immutable acquisition view. Use one TCP session for the entire capture; do not trigger and reconnect to run the download.

Always use `WAV:INTerval 1` and verify `WAV:INT?` before reading. Do local extraction such as `samples[::stride]` only after the complete-resolution payload has passed integrity checks. The instrument's interval extraction has firmware-dependent coordinate semantics and must not be used to establish event timing.

On the verified SDS824X HD firmware, requests above 250,000 points were observed to return a 250,000-point payload while `WAV:POIN?` echoed the requested value. This is an observed firmware behavior, not a universal SDS800X HD limit. Treat `len(block.payload) / bytes_per_point` as the returned point count, retain the raw response and the readback as evidence, and fail closed when it differs from the requested count. Never advance the next `WAV:STARt` from the request or from an unverified readback.

The target's five 5,000,000-point WORD segments transferred 25,000,000 points / 50,000,000 bytes with validated contiguous ranges. This proves transport completeness and byte order, not voltage calibration or 16 effective ADC bits. Keep WORD samples raw until device-specific scaling is calibrated. BYTE signed decoding is supported by the existing parser; use descriptor `code_per_div`, probe, V/div, and offset, not a hard-coded conversion constant.

For segmented acquisition, `:WAVeform:SEQuence?` returns `<value1>,<value2>`. The first value selects the frame (`0` requests all frames in the documented reconstruction workflow); when reading all frames, the second value is the starting frame for a memory-limited fragment. It is **Conditional**: the query is meaningful only after segmented acquisition is enabled and frames exist. The target returned `4294967295,1` with segmentation inactive, so do not interpret that value as a valid frame index. The manual directs clients to `WAVeform:PREamble?` fields `read_frames` and `sum_frame` to calculate the total number of fragment reads.

## Legacy Stopped-Frame Path

For an explicitly requested immutable stopped frame, use `C<n>:WF? DAT2` without `WFSU`, save each requested channel's raw response, then perform the descriptor step only under the documented handover ordering. The modern transfer-selection writes are forbidden in immutable mode.

Do not infer full record length from a CSV/downsampled point limit. Compare scope points, descriptor points, expected bytes, downloaded bytes, sample interval, and complete contiguous segment coverage. A partial read is `INCOMPLETE`/`INVALID`, never a full record.

Signal presence requires a full-record scan, extrema detection, or event detection at original resolution. A one-point sample, mean, or sparse preview can miss a narrow pulse with a very low duty cycle; M4 previews are visualization-only. Before interpreting voltage, cross-check the conversion with a known logic-level channel such as ENABLE. If the panel V/div, probe factor, offset, or code conversion does not reproduce that reference, keep the result in code domain and mark calibration unverified. An observer driven at the same frequency as the measured signal can alias into a false state-change indication; use an unrelated observation rate or emit a discriminating comparison such as `CNT < CCR`. Any counter hypothesis must explain all observations, including periodic retry windows, before it is accepted.

### Exhaustive edge and pulse structure

Use `structure` as the fact layer before stating whether a signal was absent, driven, or continuously active:

**Agent workflow gate:** for any record-wide conclusion about periodic signal presence, frequency/duty stability, phase changes, or anomalies, `structure` over the full original-resolution record is mandatory first. If its coverage or completeness flags are not complete, the result is not evidence for a record-wide conclusion. When complete cycles exist or phase change is part of the question, run `regimes` on the same full record and thresholds; do not replace it with a screenshot, summary, fixed-window count, or paged `events` result. Report every returned regime, transition, unresolved phase, and anomaly, and use bounded `window` reads only to inspect their referenced samples. A non-periodic record may be marked regime-analysis-not-applicable only with the supporting structure evidence stated.

```text
# Optional: when the independent `oscilloscope-waveform-analysis` Skill is installed,
# set ANALYZE to its `scripts/analyze_waveform.py`:
python3 "$ANALYZE" structure --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35
python3 "$ANALYZE" structure --capture /path/to/capture/C4.bundle.json --threshold-volts 0.8 2.0 --cluster-gap-s 0.002 --max-edges 20000
python3 "$ANALYZE" regimes --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35 --measures auto --min-cycles-per-side 5
python3 "$ANALYZE" regimes --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35 --measures duty_cycle,high_width_s --relative-tolerance 0.08
```

The analyzer scans every original sample (`stride_used=1`) and emits the ordered threshold edge table, paired high-level pulses, pulse clusters, and classification basis. Each edge records its sample, interpolated crossing time, before/after codes, adjacent same-direction interval, and one-sample timing uncertainty. Each pulse references its edge IDs and sample/time span. A pulse touching a scan boundary without both threshold crossings is `INCOMPLETE`; its width is a lower bound, never padded or inferred. Clusters group observed pulses by low-level gap, with the default gap derived from observed pulse periods when available; cluster grouping is descriptive and does not replace the underlying edge/pulse table.

`--max-edges` is a hard work/output bound. When exceeded, counts are lower bounds and classification is `UNVERIFIED`; the result must not be described as an exhaustive table. The independent `--max-json-bytes` bound may shorten returned lists, but keeps each section's true count and sets `items_truncated=true` and `items_complete=false`.

M4 previews, sparse sampling, means, and fixed-window edge counts are visualization or summary tools only. They cannot prove that a signal is absent, that a channel is undriven, or that a high level persisted for a stated duration. A negative observation must include the scanned range, thresholds, `detection_resolution_s`, and `minimum_detectable_pulse_s`, and be phrased as `NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY`, not as a universal absence claim. A cluster or window aggregate never substitutes for the individual pulse intervals: a short burst and a long carrier may both have edges in the same coarse window.

### Regime changes and per-cycle anomalies

Use `regimes` after confirming the `structure` edge/pulse evidence when a record may contain stable waveform phases (for example, a frequency step from 100 Hz to 200 Hz):

- `--measures auto` selects supported per-cycle measures that show sustained change; the result records selected, rejected, and unavailable features with reasons. Use an explicit list when the question targets a specific property, such as `duty_cycle,high_width_s`.
- A regime transition requires at least five complete cycles on both sides by default. Isolated outlier cycles are reported as anomalies, not new regimes. A shorter candidate phase is unresolved; a smooth ramp remains one regime with trend evidence and an unresolved drift annotation.
- Check `data_integrity_status` separately from `segmentation_status`: a complete capture may have an unresolved interpretation. Voltage measurements are unavailable unless calibration is valid; code-domain features remain usable.
- Inspect per-cycle features, transition uncertainty, anomaly source references, and `coverage.count_reconciliation`. `max-edges`, `max-cycles`, and JSON byte limits can make the output a lower-bound or compact summary; never interpret a truncated/prefix result as a full segmentation.

Regime segmentation is a heuristic analysis of per-cycle measurements, not a fault diagnosis. Verify detected boundaries against the referenced raw pulse/edge indexes and bounded `window` reads before explaining cause.

## Local Offline Analysis Gate (optional companion Skill)

Offline analysis, verdict gating, and five-axis evidence reporting live in the independent `oscilloscope-waveform-analysis` Skill. It consumes the portable `<channel>.bundle.json` (`waveform-bundle/v1`) or a legacy `manifest.json`, never contacts the instrument, and never replaces the raw `waveform.bin` evidence. Point `ANALYZE` at its `scripts/analyze_waveform.py` and `EVIDENCE` at its `scripts/waveform_evidence.py`; never assume a fixed relative path, and if that Skill is not installed stop at capture integrity and do not invent ad-hoc verdict claims.

```text
python3 "$ANALYZE" inspect --capture /path/to/capture/C4.bundle.json
python3 "$ANALYZE" summarize --capture /path/to/capture/C4.bundle.json --preview-buckets 256
python3 "$ANALYZE" events --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35 --limit 100
python3 "$ANALYZE" window --capture /path/to/capture/C4.bundle.json --start 123456 --count 512
python3 "$ANALYZE" events --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35 --start-time 2.01795 --end-time 2.01805 --limit 20
python3 "$ANALYZE" structure --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35
python3 "$ANALYZE" structure --capture /path/to/capture/C4.bundle.json --threshold-volts 0.8 2.0 --cluster-gap-s 0.002 --max-edges 20000
python3 "$ANALYZE" regimes --capture /path/to/capture/C4.bundle.json --threshold-codes 20 35 --measures auto --min-cycles-per-side 5
python3 "$ANALYZE" ringing --capture /path/to/capture/C4.bundle.json --start-time 2.01795 --end-time 2.01805
python3 "$ANALYZE" window --capture /path/to/capture/C4.bundle.json --start-time 2.01795 --end-time 2.01805
```

### Pre-analysis evidence gate

Complete this gate before any analyzer subcommand that produces a conclusion. It is the single authority for measurement provenance, channel identity, record completeness, analysis time, pulse-boundary semantics, threshold placement, and drive claims. `inspect` is the integrity entry, not analysis evidence.

- **Try to preserve the instrument's own readings first; their absence must not block offline analysis.** Record every existing readout verbatim with its item, source channel, threshold settings, measurement window, gating, and definition (what the value is computed over). Read that context instead of assuming it: `:MEASure:SIMPle:SOURce?` reports the channel whose value a readout describes, while `:MEASure:THReshold:SOURce?`, `:MEASure:THReshold:TYPE?` and `:MEASure:THReshold:PERCent?` or `:MEASure:THReshold:ABSolute?` report the threshold source that the following threshold queries address and its high/mid/low settings (documented, programming guide printed pp. 182-185). Record both sources separately and never assume they agree: when the measurement source and the queried threshold source differ, the measurement channel's own thresholds were not read, so its threshold levels stay `unknown` and any statistics comparison stays `UNVERIFIED`. Do not rewrite `:MEASure:THReshold:SOURce` to read another channel's levels — that changes instrument state. If a readout is unavailable — an unsafe or undocumented query, or no readout exists — record it as `unavailable` with the unknown metadata and continue with evidence-based offline analysis. Do not change the instrument configuration to make it queryable. A missing readout blocks only statistical-consistency claims and inferences beyond the offline evidence; it does not block a conclusion the captured samples support on their own.
- **Compare statistics only on identical measurement conditions.** An instrument readout and an analyzer statistic may be compared only when they come from the same capture, channel, measurement window, gating, threshold, and count definition. Classify each condition as matched, `unknown` (not recorded, not queryable, or not established), `not_exposed` (no control for it is exposed by the interfaces and documents this Skill records), or `not_applicable` (the quantity is not part of this measurement). `not_exposed` records only the scope of this Skill's records: it is not evidence that the instrument has no such control, so the measurement behaviour behind it stays `UNVERIFIED` unless the absence is independently established. `not_applicable` likewise describes the quantity, not a value. Neither classification turns a differing threshold, window, or count definition into agreement. Any `unknown` or differing condition keeps the comparison `UNVERIFIED` rather than reconciling the numbers; a whole-frame instrument statistic never describes a stage or anomaly, and no comparison substitutes for full-record analysis.
- **Keep the measurement window separate from the display window.** Record the display timebase state in effect when the reading was taken — `TIMebase:SCALe`, `TIMebase:DELay`, and `TIMebase:REFerence:POSition`, from the manifest `capture_configuration` snapshot for that setup — as display configuration, and record the range a readout actually evaluates as a separate item from evidence about that readout (`firmware-scoped`: on this target a zoom change moved a `:MEASure:SIMPle` value, so the zoomed window drove it — one observed case, not a documented rule). When the evaluated range is not established, record it `unknown`; do not infer it from the display timebase values, and do not default it equal to the display window. The display state is also not proof of measurement gating: the only gating control this Skill records is `:FUNCtion<x>:INTegrate:GATE` (math integrate), so basic-measurement gating is `not_exposed` only in the sense that the recorded interfaces and documents expose none — the measurement's own gating behaviour stays `UNVERIFIED`. Compare a reading with a sub-range analyzer statistic only when the analyzer range equals the recorded evaluation range.
- **Resolve the channel map before attributing a signal name.** The bench mapping in [`SKILL.md`](../SKILL.md) *Session Baseline* is one verified setup, not a default. `capture_scope.py` records `channel_mapping` only from `--channel-mapping`, together with `channel_mapping_source` (`user-supplied`, otherwise `unknown`); the scope exposes no channel-name readback, so no tool output can confirm wiring. A manifest from an earlier capture script instead carries the fixed template `{"C1": "ENABLE", "C2": "nFAULT", "C3": "HOC", "C4": "P4.1/CMP"}`: treat that exact constant as an unverified template carrying no per-capture wiring evidence, not as the capture's declaration. Compare whatever the caller states with the wiring, probe, and user-supplied channel description, and never relabel a channel so the data fits an expected signal.
- **An unresolved signal name blocks attribution, not analysis.** When no channel mapping is confirmed, analyse the physical channel (`C2`) and report its signal name `UNVERIFIED`; physical-channel conclusions, including statistics compared on that same physical channel, stand on the captured samples. A functional or protocol claim ("this is nFAULT", "this is the HOC drive", "this frame proves reception") requires the resolved identity, and only those claims are blocked. Stop and report the analysis `UNVERIFIED` only when the `inspect` integrity record itself is missing or not `COMPLETE`.
- **Open the complete descriptor record through the manifest.** `capture_scope.py` writes `<channel>.bundle.json` beside `manifest.json` for every `COMPLETE` channel. Verify payload completeness from `manifest.json` (`frame_report.status == "COMPLETE"`, `segment_report.status == "COMPLETE"`, matching file size / SHA-256) or run `analyze_waveform.py inspect` and require `integrity.status = COMPLETE`, `capture.points` matching the WAVEDESC waveform point count, and `integrity.segments_verified` matching the manifest's segment count. `ACQ:POIN?` reports screen waveform points (manual printed p. 21); modern captures mark `scope_record.semantics = screen` and report that quantity separately. Payload completeness proves coverage of the descriptor record, not the whole acquisition memory or its correspondence to the screen. Read `screen_range` and `time_correspondence` and state their unresolved conditions. Older `INCOMPLETE` modern manifests may be checked with explicit `--revalidate-screen-range`: only recorded screen-count/duration comparison failures can be reclassified, all file and segment checks still run, and the derived output retains the source manifest hash and original failure reasons without changing raw artifacts. Unknown failure reasons remain a refusal. Never glob `*.bin` or treat a single segment as the record; use the manifest's merged `waveform.bin`.
- **Use descriptor time and CLI time windows.** Take time from `sampling.origin_s` and `sampling.interval_s`, and pass ranges as `--start-time/--end-time`. These are descriptor-reported coordinates; screen, trigger and decoder alignment remain `UNVERIFIED` until independently established. The modern time formula follows manual printed pp. 391-392 and 454; retain it rather than compensating a measured offset with a fixed constant. Do not derive time from filenames or a guessed sample rate, or treat a segment-local index as a record index.
- **A rising edge is not a complete positive pulse.** Report pulses touching a scan or capture boundary separately as boundary/`INCOMPLETE` items, never padded or dropped. Read the pulse fields together: `pulses.count` is every pulse the scan produced, `pulses.complete_count` counts those with both edges inside the record, `pulses.incomplete_count` counts the boundary ones, and `pulses.status` is `COMPLETE` or `COMPLETE_WITH_INCOMPLETE_BOUNDARY_PULSES`. Compare `PPULSES` or `NPULSES` only after confirming what the instrument counts: the manual defines them as the positive or negative pulse count in the screen waveform without stating how a pulse cut by the screen edge is treated. Neither `complete_count` nor `count` is automatically equivalent to that reading. Match the evaluated window and boundary rule before claiming agreement; otherwise report the separate counts and keep equivalence `UNVERIFIED`.
- **Hysteresis thresholds must sit outside the noise band**, derived as in step 1 of the mandatory gate below. A local minimum or maximum is not a crossing and does not prove activity: activity requires recorded threshold crossings on original-resolution samples under the stated thresholds.
- **A low MISO level is not proof of active drive or protocol reception.** It shows only the sampled level of that line. A received-frame claim needs an actual frame decode plus its protocol context; an active-drive claim needs independent electrical evidence. A decode does not prove drive, and a level reading does not prove reception.

The gate is complete when every recorded readout carries its status (`preserved` or `unavailable` with the unknown metadata) and its source, threshold, and window context — display configuration and evaluation range recorded separately, each `unknown` when not established; the channel map is recorded with its source (`user-supplied` or `unknown`); the `inspect` integrity confirmation is recorded; and every unresolved condition is named. A missing readout leaves statistical consistency `UNVERIFIED` and does not stop offline analysis; an unresolved signal name leaves attribution `UNVERIFIED` and does not stop physical-channel analysis.

### Mandatory analysis gate

Evidence labels in this subsection are `firmware-scoped`: SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP `5025`. Before any conclusion about periodic-signal presence/absence, drive, frequency stability/change, duty/pulse timing, or a long record's phases:

0. **Run the verdict pre-screen first.** After the pre-analysis gate has confirmed the record, run `analyze_waveform.py verdict --capture <capture-dir>/<Cn>.bundle.json` (or `--capture <capture-dir> --channel <Cn>`) as the first conclusion subcommand, before any other analyzer subcommand. The conclusion must quote `claims.can_claim`, must not assert anything in `claims.cannot_claim`, and must reproduce every `claims.must_state` entry verbatim. A `REFUSED` verdict is a complete answer and must be reported as such, never worked around with hand-rolled arithmetic, a new threshold pair, or a narrower sampling claim. When a refusal hides a possible sparse event, the permitted escalation is `waveform_evidence.py --capture <capture-dir>/<Cn>.bundle.json --out <outside-path>.json` (add `--svg <outside-path>.svg` for the raw-code view): it preserves `status = REFUSED`, exposes the candidate excursions the refusal already localised, and extracts a bounded number of original-resolution windows. Those windows are observations of raw codes, not levels, edges, pulses, protocol activity, absence, or stability, and the returned subset is never a review of every candidate. Steps 1-5 are the escalation path when the verdict is `OBSERVED` but the task needs stage, transition, or anomaly detail a pre-screen cannot give.
1. **Prove the thresholds are placed on the signal's own levels, not on its noise.** The analyzer only reports whether a threshold was *reached*, never whether it was *reached in the right place*: a threshold inside the noise band returns a healthy `OBSERVED` / `low_duty_pulse_train` result whose silent prefix, first-edge time and pulse count are all wrong, with no field flagging it. Derive the levels first from `summarize.summary.percentiles_v` (calibrated) or `percentiles_code` (code domain — the two are mutually exclusive: a `VALID` calibration emits only the `_v` family plus `underlying_code_statistics`, which carries min/max but no percentiles). Place `high` under the code where p95 and p99 coincide and `low` above p50; for a bipolar or multi-level record take the boundary codes from a deliberately low `structure` pass and read `edges.items[].before_code` / `after_code`. `summarize` accepts no time range, so a whole-record percentile describes the whole record only — reproduce any single-region claim with a sub-range `structure` pass. `firmware-scoped` failure: on a 5 s record whose first 0.45 s sat at a 0.02-0.4 V noise floor, thresholds of 0.13/0.39 V moved the first edge from 0.0962 s to -0.4141 s (silent prefix 0.086 s instead of 0.596 s), added 67 spurious crossings, and still reported `status = OBSERVED`. State the evidence for each threshold pair you use.
2. Run `structure` on the **full record** at original resolution with explicit hysteresis thresholds. Inspect `coverage.full_record_scanned`, `edges.items_complete`, `pulses.items_complete`, and `evidence.observation_status`. If any is incomplete, truncated, `UNVERIFIED`, or limited to a time subrange, state the limitation and do not make a record-wide claim.
3. If the structure contains at least two complete cycles, or the task asks whether a periodic regime changed, run `regimes` on the **same full record, channel, thresholds, and calibration context**. Inspect `data_integrity_status`, `segmentation_status`, `overall_status`, `coverage.count_reconciliation.reconciles`, regime/transition/cycle counts, unresolved phases, anomalies, and each returned item's completeness flags before drawing conclusions.
4. Reconcile each claim with the returned per-cycle values and edge/pulse references. Report every regime and every unresolved candidate phase, including brief phases; do not summarize away a detected stage or anomaly. Use `window` only to inspect samples around referenced transitions/anomalies, never as a replacement for full-record structure.
5. **Re-scan at a second threshold pair whenever the pulse table shows paired or equal-width pulses** — the signature of one real pulse being cut into several segments by an intermediate level. `pulse_clusters` cannot reveal this: grouping is by low-level gap only, so a split pulse stays one cluster and `cluster_count` is a correct computation, just not a description of the sub-structure. `firmware-scoped` example: one 136.25 ms gate cycle held a 45.2 ms high, a 0.2 ms notch, a 0.03 ms spike and another 45.2 ms high, so a single threshold reported `continuous_carrier`, `cluster_count=1`, 133 pulses, and nothing marked the split. Report the levels separately instead of claiming one pulse count.

If the waveform is not periodic/pulse-like, explicitly mark regime segmentation as not applicable and state which structure evidence supports that choice. If cycle support is insufficient, or any output is truncated/prefix-only, report the stage analysis as unresolved/`UNVERIFIED`; do not silently skip the regime pass and do not convert missing evidence into a negative claim. `inspect`, `summarize`, a screenshot, `events` pagination, and an M4/stride preview alone do not satisfy this gate.

Two fields mean "you are not looking at the whole record": `status=UNVERIFIED` with `edges.count_is_lower_bound=true` (the edge budget stopped the scan) and `truncated=true` with `items_complete=false` (the JSON budget kept a prefix). `classification` and `pulse_clusters.count` are computed **before** truncation and stay authoritative, but any later statistic over `edges.items` / `pulses.items` is prefix-only. Check `count` against `returned` before reusing either list.

### Analyzer behaviour worth knowing before quoting it

The analyzer validates the complete frame, merged file size, SHA-256, segment ranges, actual payload point counts, width, byte order, and sampling metadata before reading samples through NumPy `memmap`. It scans large records in bounded chunks and returns compact JSON rather than raw arrays. `summarize` reports exact integer-code statistics and an M4 preview labelled `visualization_only_lossy`; the preview must not be used as a substitute for event detection. To detect narrow pulses, scan the full record or use original-resolution extrema/event detection; one-point or mean sampling is never evidence that a signal is absent. `events` scans original-resolution samples and returns bounded pages with a stateless cursor, and `--start-time/--end-time` limit the scan to a relative display-time range. `window` is the escalation path for inspecting samples around an event and accepts either sample indices or a half-open time range. `ringing` analyses one bounded local window and reports heuristic edge overshoot, undershoot, residual crossings, frequency, and decay when enough evidence exists; it does not return a full local array, so call `window` when the raw samples are needed, and it marks windows touching the capture boundary, edges without enough pre-context, and ring-down still above noise at the window end so a local estimate is never mistaken for proof that the physical event ended.

`firmware-scoped` operational limit: `--max-json-bytes` is capped at 4 MiB, and the bounding loop re-serializes the whole document for every item it removes. A 25 M-point, 5 s record containing a 19.92 kHz pulse train (about 20 000 pulses / 39 000 edges) did not finish a single full-record `structure` call in 25 minutes, and `regimes` on the same record behaved the same way. Cover such a record with **contiguous sub-range windows that each fit under the budget** (`--max-json-bytes 4194304`; 0.2 s windows over 5 s took about 12 s in total, each window `truncated=false` with `edge_scan_complete=true`), then reconcile the windows. Report the result as contiguous windowed coverage of the full record, quote the window boundaries, and never present a single sub-range scan as a full-record result. A window holding only one complete cycle legitimately returns `regimes` `UNSUPPORTED`; take that stage's regime evidence from a window with enough complete cycles and state which window it came from.

All analysis times are relative to the waveform display origin reported in `sampling.origin_s`, not wall-clock time, and the range is half-open `[start-time, end-time)`. Do not combine time arguments with sample-index arguments. Analysis output defaults to stdout and must be written outside the raw capture directory with `--out`.

The instrument's own whole-frame simple measurements are a magnitude check only: on a record that spent most of its length at 19.92 kHz, the whole-frame `FREQ` reported 7.3433 Hz, `PWID` reported the stage-1 45.4248 ms, and `DUTY` reported 33.357 %, so a whole-frame reading must never be used as the stage description. An observer or probe at the same frequency as the measured signal can alias into a false state change; use an unrelated observation rate or a discriminating comparator output, and interpret counter hypotheses only when they explain all observations, including periodic retry windows. WORD and BYTE calibration shapes, the `code_per_div`/`PKPK` cross-check, and the WORD calibration JSON are in [Programming notes](programming-guide.md#word-and-byte-sample-decoding).

## Binary Response Handling

- **Waveform** binary responses (`WAVeform:DATA?`, `WAVeform:PREamble?`, `C<n>:WF? DAT2`) use IEEE 488.2 definite-length blocks. The payload may contain newlines, NUL, or `#`; never line-split binary data.
- Framing mechanics: search until `#` is found (arbitrary ASCII, NUL bytes, prompts and status bytes may precede it), read one ASCII digit `N`, then exactly `N` ASCII decimal length bytes, then exactly that many payload bytes. Validate that length, and keep `prefix`, the complete block header, payload, and SHA-256. A timeout, missing marker, non-decimal length, or short payload fails closed.
- Any empty, truncated, wrong-width, overlapping or missing segment invalidates the complete channel; never infer missing samples or silently pad. Compare the descriptor's `array_count`/`data_length` with the actual payload bytes, and expect `count` payload bytes for BYTE and `count * 2` for WORD.
- **`:PRINt?` is the documented exception**: on firmware `4.8.12.1.1.6.5` it returns a raw PNG stream with no block header, so the framing rules above must not be applied to it and `read_ieee_block()` correctly fails with `invalid IEEE length-of-length`. Read bounded bytes until `IEND` plus the trailing `LF`; `scripts/screenshot_capture.py` performs that read with a total byte bound and a total elapsed-time bound, and validates the container only (signature, legal IHDR pair, chunk order, CRCs, `IEND`+`LF`). It does not decode the image.
- Preserve prefix, header, payload, length, and SHA-256. Validate exactly `points * bytes_per_point` bytes per segment.
- `WAVeform:PREamble?` itself returns a binary block containing the 346-byte little-endian WAVEDESC; it is not an ASCII structure.
- Current bundled `capture_scope.py` handles segmented waveform transfer and, with `--screenshot`, one post-capture PNG. For waveform responses use `scripts/scope_protocol.py`; for screenshots use `scripts/screenshot_capture.py`, which reads by chunk length and CRC until `IEND` plus one `LF`. Do not write a second reader at the call site, and never hand either response type to a line-oriented text reader.

## Evidence and Manual Pages

Source: `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- `:PRINt?`: printed p. 15; screenshot example pp. 494-495.
- `:SAVe:IMAGe` (file screenshot, menu on/off): printed p. 203.
- `:DISPlay:PERSistence`: printed p. 133.
- `WAVeform` command system and preamble: printed pp. 383-394.
- Analog reconstruction and slicing example: printed pp. 451-454.
- Target transfer verification and parser details: [`programming-guide.md`](programming-guide.md) and [`../SKILL.md`](../SKILL.md).
