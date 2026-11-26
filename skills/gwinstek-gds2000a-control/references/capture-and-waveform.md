# Capture and Waveform (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Acquisition: TOC pp. 41-45; RUN/STOP/SINGle/FORCe: TOC pp. 111-112; trigger
state: TOC p. 131. Support level: acquisition queries, `:RUN`/`:STOP`/
`:SINGle`, and one `:ACQuire1:MEMory?` capture are `hardware-verified` on the
GDS-2104A; waveform voltage conversion is `UNVERIFIED`. Page numbers are
table-of-contents or List of Commands markers (pp. 24-34); the local converted
copy has no body page breaks.

## Acquisition control

| Command | Meaning | Status |
|---|---|---|
| `:RUN` | Continuous acquisition | Hardware-verified; `AUTO` after `:STOP` then `:RUN` |
| `:STOP` | Stop acquisition | Hardware-verified; state `SAVE` |
| `:SINGle` | Arm one acquisition | Hardware-verified; state `READY`, acquire state `0` |
| `:FORCe` | Force a trigger event | Documented only; not implemented |

`FORCe` is a deliberate override, not a timeout workaround. If a capture never
becomes ready, the trigger, source, or level is wrong; forcing hides that.

The verified transitions were `AUTO` -> `:STOP` -> `SAVE` -> `:RUN` -> `AUTO`.
On V1.18, `:RUN` alone did not leave `READY`/`SAVE`; a `:STOP` followed by
`:RUN` restored continuous acquisition. Do not treat a single `:RUN` as proof
of an armed trigger.

## Trigger state

`:TRIGger:STATe?` returns one of the documented `*ARMED`, `*AUTO`, `*READY`,
`*SAVE`, `*TRIGGER` values (TOC p. 131). The verified unit returned `ARMED`,
`AUTO`, `SAVE`, and `READY` **without** the leading `*`; accept both spellings.

- `ARMED`: waiting for the trigger condition.
- `AUTO`: automatic mode is sweeping without a trigger. The manual calls this
  "Auto trigger (Untriggered roll)" (TOC p. 120); a completed record is a
  frame, not a triggered frame.
- `READY`: pretrigger information is complete and the scope is ready to accept
  a trigger; it does not mean the post-trigger record is complete.
- `SAVE`: stop/save state; do not treat it as generic readiness.
- `TRIGGER`: a trigger occurred and post-trigger acquisition is in progress.

## Acquisition state

`:ACQuire<n>:STATe?` returns `0` (raw data not ready) or `1` (ready), and is
reset to zero when acquisition changes from STOP to RUN (TOC p. 43). It is a
suffixed family: `:ACQuire1:STATe?`. The bare form returned `-113 Undefined
header` on V1.18. The earlier exploration read `:ACQuire1:STATe?` as `1`; the
shipped final-run evidence is the waveform, not a separate state log.

## Acquisition mode

```text
:ACQuire:MODe {SAMPle|PDETect|AVERage|?}
:ACQuire:AVERage {2|4|8|16|32|64|128|256|?}
:ACQuire:INTERpolation {ET|SINC|?}
:ACQuire:FILTer {OFF|0.02|0.04..0.98|?}
```

All are setters/queries (TOC pp. 41-44). The verified unit reported
`:ACQuire:MODe?` -> `SAMPLE`. The other modes/values are documented only.

- `PDETect` changes what one "point" means: it reports the min/max excursion per
  sample interval, so a peak-detect record is not the same signal as a
  sample-mode record of the same length. It makes narrow glitches visible and
  inflates apparent noise.
- `AVERage` needs `:ACQuire:AVERage`; the count is 2, 4, 8, 16, 32, 64, 128, or
  256. An averaged record has different noise and edge noise than a single-shot
  record, so an averaged capture is not comparable to an unaveraged one.
- `INTERpolation SINC` reconstructs edges between samples. Rise time,
  overshoot, and ringing measured from a SINC record are **interpolated**, not
  sampled.
- `FILTer` is documented but not implemented by this Skill; do not send it as
  part of a default capture.

Record the mode, average count, interpolation, filter, record length, and
whether the acquisition was stopped with every waveform. A waveform without
this context is structurally valid but not reproducible.

## Record length

```text
:ACQuire:RECOrdlength {AUTO|SHORT|?}
```

The GDS-2000A manual documents two values: `AUTO` and `SHORT` (TOC p. 44). The
verified unit reported `AUTO`. Do not copy a fixed 1,000-10,000,000-point list
from another GDS series; the actual point count is carried by the waveform
header (`Memory Length`) and the block length.

`:ACQuire<n>:LMEMory?` returns the long-memory/detail format. The manual's
example is 1,000,000 points; that capture exists only in local evidence and is
not shipped. The parser limit is `MAX_POINTS = 10_000_000` and
`MAX_PAYLOAD_BYTES = 20_000_000`; a declared size above either limit is
`UNSUPPORTED`, never truncated.

## Header switch

```text
:HEADer {ON|OFF|?}
```

Default ON (TOC p. 45). The verified unit reported `ON`. With `ON`,
`:ACQuire<n>:MEMory?` returns:

1. an ASCII header of `name,value;` or `name,value,` fields,
2. the literal marker `Waveform Data;`,
3. an IEEE 488.2 definite-length block,
4. an optional response terminator.

With `OFF`, only the block is returned. There is then no scale, unit, source,
or timebase metadata, so the result is `UNVERIFIED`; point count is still
recoverable.

## Documented header fields

The captured header used these fields:

```text
Format, Memory Length, IntpDistance, Trigger Address, Trigger Level, Source,
Vertical Units, Vertical Units Div, Vertical Units Extend Div, Label,
Probe Type, Probe, Vertical Scale, Vertical Position, Horizontal Units,
Horizontal Scale, Horizontal Position, Horizontal Mode, SincET Mode,
Sampling Period, Horizontal Old Scale, Horizontal Old Position, Firmware, Time
```

The parser requires `Memory Length` for a header-present response and checks
it against the block length. A missing `Vertical Scale` makes the waveform
`UNVERIFIED`; a missing `Sampling Period` is reported as a reason without
changing the structural status. Duplicate field names and fields without a
comma are `INVALID`. A comma-separated header with an odd token count is
`UNVERIFIED`, because the parser cannot pair every name with a value. A `;`
header was captured; the parser also accepts a comma-separated header,
matching the LMEMory example.

## IEEE 488.2 block

```text
#<n><length><payload>
```

- `<n>` is the number of digits in `<length>`; `<length>` is the payload size
  **in bytes**, not points.
- Each point is two bytes: signed 16-bit two's complement, range
  `-32768..32767`.
- The shipped capture is `#510000` + 10,000 payload bytes (5,000 points) + one
  LF. The manual's example also uses `#510000`.
- Indefinite blocks (`#0`) are not supported.
- A block whose declared length exceeds the received bytes is `INCOMPLETE`.
  Extra bytes after the payload are `INVALID`, except one optional response
  terminator.
- `payload length % 2 != 0` is `INVALID`; an odd tail is never padded.

## Byte order and calibration

The manual does **not** state the sample byte order for `:ACQuire<n>:MEMory?`.
Little-endian is labelled `observed`: the GDS-2104A capture is consistent with
little-endian signed 16-bit codes, and big-endian interpretation produces
codes far outside the displayed range. Do not present little-endian as a
documented wire rule.

The manual also documents no code-to-volts formula. Therefore:

- `calibration.status` is always `UNVERIFIED`;
- `analysis_allowed` is `code-domain-only`;
- `sample_byte_order_status` is `observed`;
- no vertical position, probe ratio, or invented offset is applied;
- `code_min`, `code_max`, and `code_mean` are raw code statistics, not volts.

For calibrated work, use the instrument's own measurements or an independently
established transfer function; this Skill cannot provide one.

## Raw artifact fields

`parse_waveform(raw, include_samples=False)` returns `kind = "waveform"`,
`artifact = "acquisition-memory"`, `points`/`point_count`,
`bytes_per_point = 2`, `block_length`, `declared_block_bytes`,
`trailing_bytes`/`trailing_hex`, `header`/`header_text`,
`header_present`/`headerless`, `source`, `vertical_units`, `vertical_scale`,
`sampling_period`, `trigger_address`, `firmware`, `device_time`,
`sample_encoding`, `sample_byte_order`, `calibration`, `analysis_allowed`,
`code_min`/`code_max`/`code_mean`, `payload_sha256`, `raw_sha256`, and an
`integrity` block. Inline `samples` are opt-in and capped at 1,000,000 points;
use CSV streaming for larger records.

## CSV export

```text
python3 scripts/gds2000a_protocol.py waveform capture.bin --csv-out wave.csv
```

Columns: `index,code`. There is no voltage column; the Skill does not invent
one. The destination refuses to replace an existing file unless `--overwrite`
is given. The CSV is code-domain evidence first.

## Session capture helper

`scripts/gds2000a_session.py waveform --channel 1 --out ch1.bin` performs:

1. read `:TRIGger:STATe?`;
2. stop only if the state is not already `SAVE`/`STOP`/`STOPPED`;
3. query `:ACQuire1:MEMory?` with a definite-length block read;
4. restore continuous acquisition with `:RUN`, or with `:STOP` then `:RUN` if
   V1.18 stayed in `READY`/`SAVE`;
5. drain `:SYSTem:ERRor?`;
6. print the artifact, including `transport.read_end` (`declared_length`,
   `declared_length_no_terminator`, `line_terminator`, or `deadline`).

It never runs `*RST`, `*SAV`, `*RCL`, autoscale, calibration, or automatic
file overwrite. `--dry-run` prints the exact bytes and opens nothing.

## Failure classification

| Condition | Status |
|---|---|
| Empty response / truncated block | `INCOMPLETE` |
| Headerless block | `UNVERIFIED` |
| Missing `Memory Length` (header present) | `INCOMPLETE` |
| `Memory Length` != block points | `INVALID` |
| Missing `Vertical Scale` | `UNVERIFIED` |
| Missing `Sampling Period` | status unchanged; reason `sampling_period_missing` |
| Odd payload length / extra non-terminator bytes | `INVALID` |
| Indefinite block / declared size above limits | `UNSUPPORTED` |
| `:HEADer OFF` | `UNVERIFIED` |

Never merge a failed or retried download into a complete record.

## Capture context to record

- `*IDN?` model, serial, and firmware;
- `:ACQuire:MODe?`, `:ACQuire:AVERage?`, `:ACQuire:INTERpolation?`,
  `:ACQuire:FILTer?`;
- `:ACQuire:RECOrdlength?`, `:HEADer?`;
- `:TIMebase:MODe?`, `:TIMebase:SCALe?`, `:TIMebase:POSition?`;
- per channel: `:CHANnel<n>:DISPlay?`, `:CHANnel<n>:SCALe?`,
  `:CHANnel<n>:COUPling?`, `:CHANnel<n>:PROBe:RATio?`,
  `:CHANnel<n>:PROBe:TYPe?`, `:CHANnel<n>:BWLimit?`;
- `:TRIGger:TYPe?`, `:TRIGger:SOURce?`, `:TRIGger:MODe?`,
  `:TRIGger:LEVel?`, `:TRIGger:COUPle?`, `:TRIGger:STATe?`;
- whether the acquisition was stopped by the Skill and how it was restored.
