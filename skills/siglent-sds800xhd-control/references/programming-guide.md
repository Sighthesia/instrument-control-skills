# SDS800X HD Programming Notes

Source: `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` in this repository.

## Modern waveform path

The programming guide's section 5.23 (PDF pages 411-422) defines the preferred binary path:

```text
WAV:SOURce <C1|C2|C3|C4>
WAV:WIDTh WORD   # required when the preamble nominal bits exceed 8
WAV:BYTeorder LSB
WAV:INTerval 1
WAV:STARt <zero-based point>
WAV:POINt <point count>
WAV:DATA?
WAV:PREamble?
WAV:MAXPoint?
```

The guide says `WAV:MAXPoint?` returns the per-transfer maximum in points and that `START` plus `POINT` controls a slice. The official Python example on PDF pages 479-482 sets the start for each slice, reads `WAV:DATA?`, and concatenates exact binary-block payloads. The implementation in this skill retains every prefix/header/payload and validates both point ranges and `points * bytes_per_point` before concatenation.

Observed firmware behavior on the verified SDS824X HD: a request above 250,000 points can return 250,000 payload points while `WAV:POIN?` echoes the request. The readback is therefore advisory only; actual points are `len(payload) // bytes_per_point`, and a mismatch is an incomplete/invalid segment rather than a reason to advance the start by a guessed amount. This 250,000 value is not claimed as a universal model or firmware limit.

The path has now been verified on firmware `4.8.12.1.1.6.5` with the current stopped C4 frame in both historical BYTE and WORD transport modes. WORD used `COMM_TYPE=1`, `COMM_ORDER=LSB`, five `5,000,000`-point segments of `10,000,000` bytes each, and a merged output of `50,000,000` bytes. This verifies raw transfer completeness and byte order; it does not by itself calibrate WORD voltage scaling or prove 16 effective ADC bits.

`WAV:PREamble?` returns an IEEE binary block. For an analog waveform, the documented little-endian offsets are:

| Offset | Field | Type |
|---:|---|---|
| 60 | `wave_array_1` data bytes | int32 |
| 116 | `wave_array_count` points | int32 |
| 132 | `start` | int32 |
| 136 | `interval` | int32 |
| 156 | raw VDIV | float32 |
| 160 | raw offset | float32 |
| 164 | codes/div | float32 |
| 172 | ADC bits | int16 |
| 176 | sample interval | float32 |
| 180 | horizontal delay | float64 |
| 324 | timebase enum | int16 |
| 328 | probe coefficient | float32 |
| 344 | source enum | int16 |

The guide's voltage formula is `sample_code * (vdiv / codes_per_div) - offset`, with the probe coefficient applied to the raw VDIV and offset. The exact artifact must keep the raw preamble so a later decoder can audit this interpretation.

## Legacy path

The handover documents the firmware-specific path:

```text
CHDR OFF
C<n>:WF? DAT2
C<n>:WF? DESC
WFSU SP,1,NP,0,FP,0
```

On the target firmware, `ARM` is forbidden. `WFSU` may refresh or replace a stopped frame, so it is never implicit in immutable mode. `DAT2` before `DESC` is required by the handover for this firmware; read all channel DAT2 payloads before any descriptor query.

These are handover short forms, not manual spellings: `TRMD`, `SAST?`, `TRSE`, `TRSL`, `TRLV`, `TRDL?`, `CHDR`, `WFSU`, `C<n>:VDIV`, and `C<n>:OFST` do not appear anywhere in the programming guide. The manual equivalents are `:TRIGger:MODE`, `:TRIGger:STATus?`, `:TRIGger:EDGE:*`, and `:CHANnel<n>:SCALe`/`:OFFSet`. Cite the firmware when using a short form, and cite the manual when using the long form.

The programming guide documents the IEEE block form as `#N<N-Digits><payload length><payload>`. A response may carry bytes before `#`; that prefix behaviour comes from the handover capture of this firmware, not from the manual, and the bytes are transport prefix, not waveform data.

## Capture state

The handover's verified sequence is:

```text
TRSE EDGE,SR,C1,HT,OFF
C1:TRSL POS
C1:TRLV 2.5
TRMD SINGLE
SAST?        -> Ready
stimulate DUT
SAST?        -> Stop
```

Once `Stop` is observed after `Ready`, do not send state-changing acquisition commands until the caller explicitly releases the frame. `SAST?` replies may include a command prefix such as `SAST Stop`; normalize the state token for control decisions while preserving the raw reply in capture evidence. For signal interpretation, scan original-resolution samples for narrow pulses, validate voltage scaling against a known logic channel, avoid same-frequency observers that alias with the measured signal, and require a hypothesis to explain all periodic observations before declaring a counter frozen.
