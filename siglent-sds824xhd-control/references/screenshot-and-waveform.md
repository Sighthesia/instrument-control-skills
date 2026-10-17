# Screenshot and Waveform Data

Load this reference when the agent needs visual inspection, raw waveform samples, or offline numerical analysis. Do not load decoder/search configuration unless the capture indicates a protocol or anomaly workflow.

## Screenshot

- **Target-tested MCP path**: `screenshot_tcp`, implemented through the adapter's `SCDP` command and returning BMP/raw image bytes.
- **Manual-supported SCPI path**: `:PRINt? PNG` or `:PRINt? BMP[,NORMal|INVerted]`. The manual specifies a binary screenshot response. `:PRINt?` is not a scalar ASCII query; use a byte-preserving block reader or the MCP screenshot helper.
- Inspect screenshots for clipping, ringing, pulses, setup mistakes, and on-screen decode/status context. A screenshot is evidence of display state, not a substitute for complete samples or a measurement report.

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

`SOURce`, width, byte order, interval, start, and point count are writes and therefore change the transfer view. After a single-shot `Stop`, this is the explicit `configured_capture` read path in this skill, not an immutable acquisition view. Do not mix a trigger through MCP with a later reconnect to run this script; use one transport session for the entire capture.

The target's five 5,000,000-point WORD segments transferred 25,000,000 points / 50,000,000 bytes with validated contiguous ranges. This proves transport completeness and byte order, not voltage calibration or 16 effective ADC bits. Keep WORD samples raw until device-specific scaling is calibrated. BYTE signed decoding is supported by the existing parser; use descriptor `code_per_div`, probe, V/div, and offset, not a hard-coded conversion constant.

For segmented acquisition, `:WAVeform:SEQuence?` returns `<value1>,<value2>`. The first value selects the frame (`0` requests all frames in the documented reconstruction workflow); when reading all frames, the second value is the starting frame for a memory-limited fragment. It is **Conditional**: the query is meaningful only after segmented acquisition is enabled and frames exist. The target returned `4294967295,1` with segmentation inactive, so do not interpret that value as a valid frame index. The manual directs clients to `WAVeform:PREamble?` fields `read_frames` and `sum_frame` to calculate the total number of fragment reads.

## Legacy Stopped-Frame Path

For an explicitly requested immutable stopped frame, use `C<n>:WF? DAT2` without `WFSU`, save each requested channel's raw response, then perform the descriptor step only under the documented handover ordering. The modern transfer-selection writes are forbidden in immutable mode.

Do not infer full record length from a CSV/downsampled point limit. Compare scope points, descriptor points, expected bytes, downloaded bytes, sample interval, and complete contiguous segment coverage. A partial read is `INCOMPLETE`/`INVALID`, never a full record.

## Binary Response Handling

- Binary responses use IEEE 488.2 definite-length blocks. The payload may contain newlines, NUL, or `#`; never line-split binary data.
- Preserve prefix, header, payload, length, and SHA-256. Validate exactly `points * bytes_per_point` bytes per segment.
- `WAVeform:PREamble?` itself returns a binary block containing the 346-byte little-endian WAVEDESC; it is not an ASCII structure.
- Current bundled `capture_scope.py` handles segmented waveform transfer. The MCP `safe_scpi_query_tcp` is only for known text responses, not screenshot or waveform binary transfers.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- `:PRINt?`: printed p. 15; screenshot example pp. 494-495.
- `WAVeform` command system and preamble: printed pp. 383-394.
- Analog reconstruction and slicing example: printed pp. 451-454.
- Target transfer verification and parser details: [`programming-guide.md`](programming-guide.md) and [`../SKILL.md`](../SKILL.md).
