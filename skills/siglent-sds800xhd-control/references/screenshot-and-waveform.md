# Screenshot and Waveform Data

Load this reference when the agent needs visual inspection, raw waveform samples, or offline numerical analysis. Do not load decoder/search configuration unless the capture indicates a protocol or anomaly workflow.

## Screenshot

- **Manual-supported SCPI path**: `:PRINt? PNG` or `:PRINt? BMP[,NORMal|INVerted]`. The manual specifies a binary screenshot response. `:PRINt?` is not a scalar ASCII query; use a byte-preserving binary reader.
- `:PRINt?` cannot hide the on-screen menus. When a menu-free image is needed, use the file path instead: `:SAVe:IMAGe "<path>",<BMP|JPG|PNG>,<ON|OFF>,MOFf` (manual printed p. 203). `MOFf` hides the top and right menus, `MON` keeps them; `invert ON` gives a light background for printing. Paths are `local/...` (internal), `net_storage/...` (mounted share), or `U-disk0/...`. This writes a file, so it needs authorization and must not overwrite an existing name.
- Inspect screenshots for clipping, ringing, pulses, setup mistakes, and on-screen decode/status context. A screenshot is evidence of display state, not a substitute for complete samples or a measurement report.
- `:DISPlay:PERSistence` (`OFF`, `INFinite`, `1S`, `5S`, `10S`, `30S` on SDS800X HD) keeps previous acquisitions on screen; it is how an intermittent glitch becomes visible in a screenshot at all. Record the setting with any screenshot used as evidence.

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
python3 scripts/analyze_waveform.py structure --capture /path/to/capture --channel C4 --threshold-codes 20 35
python3 scripts/analyze_waveform.py structure --capture /path/to/capture --channel C4 --threshold-volts 0.8 2.0 --cluster-gap-s 0.002 --max-edges 20000
python3 scripts/analyze_waveform.py regimes --capture /path/to/capture --channel C4 --threshold-codes 20 35 --measures auto --min-cycles-per-side 5
python3 scripts/analyze_waveform.py regimes --capture /path/to/capture --channel C4 --threshold-codes 20 35 --measures duty_cycle,high_width_s --relative-tolerance 0.08
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

## Binary Response Handling

- Binary responses use IEEE 488.2 definite-length blocks. The payload may contain newlines, NUL, or `#`; never line-split binary data.
- Preserve prefix, header, payload, length, and SHA-256. Validate exactly `points * bytes_per_point` bytes per segment.
- `WAVeform:PREamble?` itself returns a binary block containing the 346-byte little-endian WAVEDESC; it is not an ASCII structure.
- Current bundled `capture_scope.py` handles segmented waveform transfer. Use a byte-preserving binary reader for screenshot or waveform responses; a line-oriented text reader is not suitable.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- `:PRINt?`: printed p. 15; screenshot example pp. 494-495.
- `:SAVe:IMAGe` (file screenshot, menu on/off): printed p. 203.
- `:DISPlay:PERSistence`: printed p. 133.
- `WAVeform` command system and preamble: printed pp. 383-394.
- Analog reconstruction and slicing example: printed pp. 451-454.
- Target transfer verification and parser details: [`programming-guide.md`](programming-guide.md) and [`../SKILL.md`](../SKILL.md).
