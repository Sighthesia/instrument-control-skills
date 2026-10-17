# SDS800X HD Programming Notes

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` in this repository.

## Modern waveform path

The programming guide's section 5.23 (PDF pages 411-422) defines the preferred binary path:

```text
WAV:SOURce <C1|C2|C3|C4>
WAV:WIDTh BYTE
WAV:INTerval 1
WAV:STARt <zero-based point>
WAV:POINt <point count>
WAV:DATA?
WAV:PREamble?
WAV:MAXPoint?
```

The guide says `WAV:MAXPoint?` returns the per-transfer maximum and that `START` plus `POINT` controls a slice. The official Python example on PDF pages 479-482 sets the start for each slice, reads `WAV:DATA?`, and concatenates exact binary-block payloads. The implementation in this skill improves that example by retaining every prefix/header/payload and validating ranges before concatenation. This documents the protocol path, not a claim that firmware 4.8.12.1.1.6.5 has already passed a full 25 Mpts transfer with this script.

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

The programming guide also documents the IEEE block form as `#N<N-Digits><payload length><payload>`. A response may carry bytes before `#`; those bytes are transport prefix, not waveform data.

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

Once `Stop` is observed after `Ready`, do not send state-changing acquisition commands until the caller explicitly releases the frame.
