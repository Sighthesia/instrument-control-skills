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
