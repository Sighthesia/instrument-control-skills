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

The following forms are firmware-observed, not manual spellings: `TRMD`, `SAST?`, `TRDL?`, `CHDR`, `WFSU`, and `C<n>:VDIV`/`C<n>:OFST` do not appear anywhere in the 495-page programming guide. For those, the manual equivalents are `:TRIGger:MODE`, `:TRIGger:STATus?`, `:TIMebase:DELay?`, `:CHANnel<n>:SCALe`/`:OFFSet` (and `WFSU` has no documented equivalent at all). Cite the firmware when using a short form, and cite the manual when using the long form.

`TRSE`, `TRSL`, and `TRLV` are a different case and must not be filed alongside them as harmless abbreviations. They appear nowhere in the manual, and their apparent argument grammar contradicts it: `TRSE EDGE,SR,C1,...` mixes the type node `EDGE` with the source node `SR`, while the manual keeps type, source, slope and level as separate `:TRIGger:EDGE:*` commands; `C1:TRSL`/`C1:TRLV` prefix a channel number onto functions the manual never makes per-channel. The `HT` token is defined nowhere at all. Use `:TRIGger:EDGE:SOURce`, `:TRIGger:EDGE:SLOPe`, and `:TRIGger:EDGE:LEVel`, which write the same settings and can be read back.

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

**Do not reproduce that block verbatim.** It is a handover transcript whose tokens are undefined by the vendor manual, and one of them is self-contradictory under the manual's own grammar:

- `TRSE EDGE,SR,C1,...` — `TRSE` is the short form of `:TRIGger:TYPE`, but `EDGE` in `:TRIGger:EDGE:*` is the *type* node, while `SR` is the *source* node. A `:TRIGger:TYPE` command cannot set a source; source, slope and level are three separate `:TRIGger:EDGE:*` commands.
- `HT` — never defined in the manual, in the handover, or in this Skill. Under the manual's own optional-shortening rule, the prefix `HT` can abbreviate `HOLDoff`, `HLDTime` (holdoff time), `HLDEVent` (holdoff events), `HSTart`, or a hypothetical `HTIMe`. Reading it as "high transition" is an assumption the document never authorised.
- `C1:TRSL POS` / `C1:TRLV 2.5` — no per-channel trigger slope or trigger level command exists in the manual. `TRSL`/`TRLV` are not listed anywhere; the documented commands are `:TRIGger:EDGE:SLOPe` and `:TRIGger:EDGE:LEVel`, neither of which takes a channel number.

A search of the full 495-page programming guide finds zero occurrences of `TRSE`, `TRSL`, `TRLV`, `TRMD`, `SAST`, `WFSU`, or a bare `HT` token; `CHDR OFF` appears only once, inside a C# example. Treat every token in that block as *firmware-observed but unreadable*, and never as a self-verifying configuration.

### Use the readable long form

Every setting in the sequence above has a documented long form with a matching query, and those queries read back correctly on firmware `4.8.12.1.1.6.5`:

```text
:TRIGger:TYPE EDGE          :TRIGger:TYPE?          -> EDGE
:TRIGger:EDGE:SOURce C2     :TRIGger:EDGE:SOURce?   -> C2
:TRIGger:EDGE:SLOPe RISing  :TRIGger:EDGE:SLOPe?    -> RISing
:TRIGger:EDGE:LEVel 1.5     :TRIGger:EDGE:LEVel?    -> 1.50E+00
:TRIGger:MODE SINGle        :TRIGger:MODE?          -> SINGle
```

`:TRIGger:EDGE:SLOPe` accepts `{RISing|FALLing|ALTernate}` (manual printed p. 250) — that is the *only* documented place where rising versus falling is stated, and it is a query you can read back. Use it instead of guessing what `HT` meant. `:TRIGger:EDGE:SOURce` accepts `{C<n>|D<d>|EX|EX5|LINE}` (manual printed pp. 250-251); note it also accepts the external-trigger and line inputs, so a source readback of `C2` is positive proof, not a default.

The supported read-only snapshot fields are `:TRIGger:TYPE?`, `:TRIGger:EDGE:SOURce?`, `:TRIGger:EDGE:SLOPe?`, `:TRIGger:EDGE:LEVel?`, `:TRIGger:EDGE:COUPling?`, `:TRIGger:EDGE:HOLDoff?`, `:TRIGger:EDGE:NREJect?`, and `:TRIGger:EDGE:IMPedance?`. All eight answered on `4.8.12.1.1.6.5`; a trigger configuration that cannot be read back must not be reported as verified.

Once `Stop` is observed after `Ready`, do not send state-changing acquisition commands until the caller explicitly releases the frame. `SAST?` replies may include a command prefix such as `SAST Stop`; normalize the state token for control decisions while preserving the raw reply in capture evidence. For signal interpretation, scan original-resolution samples for narrow pulses, validate voltage scaling against a known logic channel, avoid same-frequency observers that alias with the measured signal, and require a hypothesis to explain all periodic observations before declaring a counter frozen.
