# Capture and Waveform (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 41-46 (acquisition, header, memory), pp. 117-118 (run/stop), pp. 137-138
(trigger state). Support level: `documented`. Waveform calibration is
`UNVERIFIED`.

## Acquisition control

| Command | Meaning |
|---|---|
| `:RUN` / `:STOP` | Start continuous acquisition / stop acquisition |
| `:SINGle` | Arm a single acquisition |
| `:FORCe` | Force a trigger event |

`FORCe` is a deliberate override, not a timeout workaround. If a capture never
becomes ready, the trigger, source, or level is wrong; forcing hides that.

`:TRIGger:STATe?` returns one of `*ARMED`, `*AUTO`, `*READY`, `*SAVE`,
`*TRIGGER` (pp. 137-138). The exact sequence depends on trigger mode; do not
assume `*TRIGGER` means the acquisition-memory data is complete.

`:ACQuire<X>:STATe?` returns `0` (raw data not ready) or `1` (ready), and is
reset to zero when acquisition changes from STOP to RUN (p. 45).

Recommended gate:

```text
:HEADer ON
:SINGle
:TRIGger:STATe?          # informational
:ACQuire1:STATe?         # poll until 1
:STOP
:ACQuire1:MEMory?
```

Do not query `:MEMory?` while acquisition is running; stop first so the record
cannot change between the block length and its payload.

## Record length

```text
:ACQuire:RECOrdlength {1e3|1e4|1e5|1e6|1e7}
:ACQuire:RECOrdlength?
```

Documented values are 1000, 10 000, 100 000, 1 000 000, and 10 000 000 points
(p. 45). At two bytes per point, the largest record is about 20 MB.

The parser limit is `MAX_POINTS = 10_000_000` and
`MAX_PAYLOAD_BYTES = 20_000_000`. A declared size above either limit is
`UNSUPPORTED`; it is never truncated to fit.

## Header switch

```text
:HEADer {ON|OFF|?}
```

Default ON (p. 46). With `ON`, `:ACQuire<X>:MEMory?` returns:

1. an ASCII header of `name,value;` fields,
2. the literal marker `Waveform Data;`,
3. an IEEE 488.2 definite-length block.

With `OFF`, only the block is returned. There is then no scale, unit, source,
or timebase metadata, so the result is `UNVERIFIED`; point count is still
recoverable.

## Documented header fields

`Memory Length`, `Trigger Address`, `Trigger Level`, `Source`,
`Vertical Units`, `Probe Type`, `Probe Ratio`, `Vertical Scale`,
`Vertical Position`, `Horizontal Units`, `Horizontal Scale`,
`Horizontal Position`, `Horizontal Mode`, `Sampling Period`, `Firmware`,
`Time`, `Format`, `IntpDistance` (pp. 41-43). The parser requires
`Memory Length` and checks it against the block length. A missing `Vertical
Scale` makes the waveform `UNVERIFIED`; a missing `Vertical Units` is reported
as absent metadata but does not by itself invalidate the block. Duplicate field
names and fields without a comma are `INVALID`.

## IEEE 488.2 block

```text
#<n><length><payload>
```

- `<n>` is the number of digits in `<length>`; `<length>` is the payload size
  **in bytes**, not points.
- Each point is two bytes: signed 16-bit two's complement, range
  `-32768..32767`.
- The documented example is **big-endian**: `00 1C` = 28 (p. 41).
- Indefinite blocks (`#0`) are not supported.
- A block whose declared length exceeds the received bytes is `INCOMPLETE`.
  Extra bytes after the payload are `INVALID`, except one optional response
  terminator.
- `payload length % 2 != 0` is `INVALID`; an odd tail is never padded.

## Voltage conversion and caveat

Documented formula (pp. 42-43): `voltage = (code / 25) * Vertical Scale`.
`25` is the fixed AD factor, and the formula does **not** include the probe
ratio.

The manual example is internally inconsistent: the header prints
`Vertical Scale,5.000E+00` while the worked calculation uses `0.5`. Therefore:

- `calibration.status` is `UNVERIFIED` in every case and `analysis_allowed`
  is `code-domain-only`;
- `sample_value()` applies exactly the documented formula with the scale that
  was actually received;
- no `Vertical Position` offset or probe-ratio multiplication is invented;
- voltage output is labelled documented-only.

For calibrated work, use the instrument's own measurements or an independently
established transfer function; this Skill cannot provide one.

## Raw artifact fields

`parse_waveform(raw, include_samples=False)` returns `kind = "waveform"`,
`artifact = "acquisition-memory"`, `points`/`point_count`,
`bytes_per_point = 2`, `block_length`, `header`/`header_text`,
`header_present`/`headerless`, `sample_encoding`, `calibration`,
`analysis_allowed`, `payload_sha256`, and an `integrity` block with raw and
payload SHA-256 (the raw binary is saved by the caller, not embedded as base64).
Inline `samples` are opt-in and capped at 1 000 000 points; use CSV streaming
for larger records.

## CSV export

```text
python3 scripts/gds1000b_protocol.py waveform response.bin --csv-out wave.csv
```

Columns: `index,code,voltage_documented,voltage_unit`. `voltage_documented` is
empty when no `Vertical Scale` exists; it is never padded with zero. The
destination is written through a temporary file and refuses to replace an
existing file unless `--overwrite` is given. The CSV is code-domain evidence
first; the voltage column is a documented convenience, not calibration.

## Failure classification

| Condition | Status |
|---|---|
| Empty response / no `Waveform Data;` marker | `INCOMPLETE` / `INVALID` |
| Headerless block | `UNVERIFIED` |
| Missing `Memory Length` | `INCOMPLETE` |
| `Memory Length` != block points | `INVALID` |
| Declared length > received / > limits | `INCOMPLETE` / `UNSUPPORTED` |
| Odd payload length / extra non-terminator bytes | `INVALID` |

Never merge a failed or retried download into a complete record.
