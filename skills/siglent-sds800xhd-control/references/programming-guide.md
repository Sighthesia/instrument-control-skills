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
| 136 | transfer stride (`sparsing_factor`, `WAV:INTerval`) | int32 |
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

## WORD and BYTE sample decoding

For modern `WAVeform:PREamble?`, parse the documented little-endian fields and keep at least `wave_array_1`, `wave_array_count`, `start`, `interval`, `vdiv`, `offset`, `code_per_div`, `adc_bit`, `sample_interval`, `delay`, `tdiv`, and `probe`.

For BYTE data, decode signed samples as `byte - 256 if byte > 127 else byte`; `raw - 128` is a half-scale offset, not a two's-complement decode, and it shifts the zero point by 128 codes. Take the V/div from the panel snapshot `C<n>:VDIV?`, not from the legacy descriptor: on firmware `4.8.12.1.1.5` the descriptor reported `vdiv=0.2`/`probe=10` on all four channels (a flat `2 V/div`) while the panel ran `5/2/2/1 V/div`, so the descriptor reproduces only the channels that happened to be at 2 V/div and scales C1 by 2.5 and C4 by 2. A `valid` calibration therefore requires a parsed panel snapshot; an unparseable or missing reply is reported as `capture_snapshot_vdiv_unparseable` and drops the result to code domain rather than skipping the check. Do not hard-code `/32`; the observed `code_per_div` is `30`.

BYTE transfer has two limits that must be stated whenever BYTE voltages are quoted. Its representable span is only `±127 codes / 30 = ±4.23 divisions`, so a 10-division screen is truncated to the middle 4.23 divisions above and below the offset; on a 1 V/div channel a steady `+4.27 V` (`4.27 divisions`) is clipped to code `127` and arrives as `+4.23 V` with zero variance, and no post-processing recovers it — re-read that channel as WORD or lower V/div. Its quantization is `1 LSB = V/div ÷ 30` (`74 mV` at 2 V/div, `167 mV` at 5 V/div), so a record spending its time near the noise floor may occupy only a few dozen codes and carry 2-5 % amplitude uncertainty. WORD is 256× finer (`7680` codes/div, `3840` codes/V at 2 V/div): use it for any threshold decision.

For WORD data, retain the raw two-byte LSB payload and report `voltage_decode=unverified_for_WORD` until the device-specific left-alignment ratio is independently calibrated. A 16-bit transport container must not be called a 16-bit ADC result. The current observed descriptor reports `nominal_bits=16`, `code_per_div=30`, and `MAX_VALUE=7680`; the WORD transfer has been hardware-verified for byte completeness, not voltage scaling.

`start` is a sample index into the whole record, not zero. Add it to the reported origin (`horizontal_offset - timebase_s * 5 + start * sample_interval`); a slice that begins at record sample `15 000 000` of a 20 M-point record otherwise reports every event 1.5 s early while the capture still counts as `COMPLETE`.

### WORD calibration artifact

Unless an independent calibration JSON is supplied, WORD analysis reports `OBSERVED_UNVERIFIED` and emits code-domain values only. That refusal is justified and must not be bypassed by arithmetic on the descriptor: the observed descriptor `code_per_div=30` with `vdiv_with_probe=2 V/div` implies 0.0667 V/code (15 codes/V), while the same frame's own `:MEASure:SIMPle:VALue? PKPK` gives **3840 codes/V** — a factor of 256. A usable calibration can still be derived without any screenshot by dividing each channel's raw code span by the scope's PKPK reading for that channel; four channels agreed to four significant digits (C1 5.23333 V, C2 3.49583 V, C3 5.51667 V, C4 5.75417 V against raw spans giving 3840 codes/V on every channel). Write that into the calibration JSON below and the analyzer reports `status = VALID`, enabling `--threshold-volts`.

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

BYTE voltage conversion takes V/div from the captured panel snapshot `C<n>:VDIV?` (probe factor already applied by the panel), falling back to descriptor VDIV only when no snapshot exists; a parsed snapshot that disagrees with the descriptor wins, and the override is recorded as `panel_snapshot_vdiv_overrides_descriptor`. A mismatch is still reported as a calibration limitation rather than silently used to produce voltage fields, and an unparseable snapshot reply is a failed cross-check (`capture_snapshot_vdiv_unparseable`), never a skipped one.

Deriving the scale from the frame's own `:MEASure:SIMPle:VALue? PKPK` is an **internal consistency check, not an independent voltage calibration**: both numbers come from the same instrument and the same acquisition. It is sufficient to place thresholds correctly and to reproduce the instrument's own readings, and it must be labelled that way (`OBSERVED_UNVERIFIED` for absolute accuracy). An independently verified scale needs a traceable reference such as a known DC source. The analyzer rejects stale or incomplete evidence back to code-domain output and does not infer WORD voltage scaling from `code_per_div * 256` alone.

## Record ranges and time coordinates

`documented`, CN11G printed p. 21: `:ACQuire:POINts?` queries the sample count of the waveform currently on screen. Printed p. 388 defines WAVEDESC offset 116 as waveform points, offset 132 as the transfer start (`WAV:STARt`), offset 136 as the transfer stride (`WAV:INTerval`), and offset 176 as the sampling interval in seconds. Screen points, descriptor waveform points, and downloaded points are separate quantities; equal counts alone establish no sample/time correspondence.

For modern transfers, `validate_frame(..., scope_points_semantics="screen")` validates payload coverage against the descriptor. It retains `scope_record` for compatibility, marks its screen semantics, and reports `screen_record` and `range_correspondence` separately. `COMPLETE` means descriptor/download payload integrity only. Missing samples, inconsistent widths/bytes, gaps, overlaps and failed hashes remain failures; full acquisition-memory extent and screen mapping are not inferred.

Old modern manifests whose only recorded failure was the screen-count/duration comparison require the explicit analyzer option `--revalidate-screen-range`. Revalidation checks the original reasons against the original fields, recomputes the report in memory, and runs the existing payload checks. Output preserves the original status/reasons and the SHA-256 of the source manifest. Write derived JSON outside the raw capture directory; never edit the raw manifest to make it pass. Unknown reasons and other acquisition modes are refused.

Printed pp. 391-392 and the modern Python example on p. 454 give `t = delay - timebase * 10 / 2 + index * sample_interval`, with the first index zero, delay at offset 180, and timebase at offset 324. The analyzer also accounts for the descriptor's starting sample. These are reported descriptor coordinates, not independently established trigger or decoder alignment. The C# structure comment on p. 438 uses a different description of `horizontal_offset`; it is not grounds to substitute that interpretation for the explicit modern reconstruction formula. Compare identified events under both interfaces before asserting time alignment; never add a fixed correction merely to match one recording.

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

The short forms are not merely cosmetic replacements for the long ones. Three concrete traps, all reproduced on `4.8.12.1.1.6.5`:

- **The short form takes a different value word than the long form.** `:TRIGger:EDGE:SLOPe RISing` is accepted; `C4:TRSL RIS` is `-224,"Illegal parameter value"`. The short form wants `POSitive`/`NEGative`. Configuring from the long-form spelling and then "fixing it" with the short form is how a slope silently stays what it was.
- **A per-channel level write moves the trigger source.** With the source on `C3`, writing `C4:TRLV 2.5` left the source on `C4`. A subsequent `TRSE?` readback then reports the channel you just touched, which looks like success while an unrelated channel became the trigger. Assert `:TRIGger:EDGE:SOURce` *after* any level write and verify the source last.
- **`TRSE` only lands as the first command of a TCP write.** Alone or as line 1 of one batch it applies; as line 2 or later it is dropped with `-113,"Undefined header"` and every later line of that batch is affected too. This is why a capture script can appear to "randomly" lose its trigger source between runs.


Once `Stop` is observed after `Ready`, do not send state-changing acquisition commands until the caller explicitly releases the frame. `SAST?` replies may include a command prefix such as `SAST Stop`; normalize the state token for control decisions while preserving the raw reply in capture evidence. For signal interpretation, scan original-resolution samples for narrow pulses, validate voltage scaling against a known logic channel, avoid same-frequency observers that alias with the measured signal, and require a hypothesis to explain all periodic observations before declaring a counter frozen.
