# Arbitrary Waveform (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 260-265. Support level:
`documented`.

## Memory and points

- 1-4096 points per waveform; 10 non-volatile 4k-point waveform memories.
- ARB sample rate 120 MSa/s; repetition rate 60 MHz.
- 10-bit amplitude resolution (±511 DAC codes).
- Waveform rate = frequency × points; rate range 120 MHz, frequency range
  60 MHz, points 1-4096 (manual p. 260).

## Upload workflow

1. `SOURce[1|2]:FUNCtion USER` to select the arbitrary waveform.
2. Set frequency/amplitude/offset via APPLy or low-level commands.
3. Download 1-4096 points into volatile memory via `DATA:DAC`.
4. Rate = Hz × points.

## DATA:DAC syntax

`DATA:DAC VOLATILE, <start>, {<binary block>|<value>, <value>, ...}`

- `<start>` is `0..4095`; points are `1..4096`; `start + points <= 4096`.
- Values are decimal/integer ±511.
- Binary block is IEEE 488.2 with **two bytes per point** (16-bit signed
  integer).
- `FUNCtion USER` selects the waveform for output (manual p. 261).

## IEEE 488.2 binary block

`#<digits><length><payload>`; the number of bytes is always twice the
number of data points (manual p. 261).

## Manual defect (preserve)

The manual example `DATA:DAC VOLATILE, #216 Binary Data` claims 5 values /
16 bytes, but 5 × 2 = 10 bytes. Never derive length from the example;
compute it from the actual point count (manual p. 261).

## Byte order (unverified)

The manual does **not** state binary byte order/endianness. Therefore:
- ASCII decimal list is the **default safe path**.
- Binary encoding requires an explicit operator `--byte-order little|big`
  and is labelled `UNVERIFIED` for byte order.

Community drivers exist but are not authoritative for this manual. The
`avian2/gwinstek-tools` driver (GPL-3.0) uses ASCII `DATA:DAC VOLATILE,0,...`
lists; `jmfrancklab/FLinst` uses an IEEE block with host-native little-endian
`int16` values. These observations do not prove this unit's byte order; verify
with an oscilloscope before relying on a binary upload.

## Editing commands

| Command | Page |
|---|---|
| `SOURce[1|2]:ARB:EDIT:COPY` | 262 |
| `SOURce[1|2]:ARB:EDIT:DELete` | 263 |
| `SOURce[1|2]:ARB:EDIT:DELete:ALL` | 263 |
| `SOURce[1|2]:ARB:EDIT:POINt` | 263 |
| `SOURce[1|2]:ARB:EDIT:LINE` | 264 |
| `SOURce[1|2]:ARB:EDIT:PROTect` | 264 |
| `SOURce[1|2]:ARB:EDIT:PROTect:ALL` | 265 |
| `SOURce[1|2]:ARB:EDIT:UNProtect` | 265 |
| `SOURce[1|2]:ARB:OUTPut` | 265 |

## Save/recall caveat

The instrument has 10 non-volatile 4k-point waveform memories, but the manual
states that `*SAV` saves only the instrument state, not waveform data
(manual p. 271). `DATA:DAC` writes volatile memory. Saving/loading ARB data is
a panel/AWES operation in the manual; this Skill does not claim a remote
non-volatile ARB save path. Do not infer one without hardware verification.

## CSV contract (Skill-defined)

- Comments start with `#`.
- One integer per row or comma/whitespace-separated integers.
- Values must be integers in ±511.
- No floats, no silent clamping/padding.

## Validation and quantization

- `scale_normalized` scales [-1, 1] to ±511 with half-away-from-zero rounding;
  never clamps.
- `validate_arb_samples` requires non-empty, ≤4096 points, all int, within
  ±511.
- Binary uploads are `UNVERIFIED` until byte order is confirmed on hardware.

## Load/offset safety

- Amplitude/offset double on 50 Ω -> high-Z change.
- `|Voffset| < Vmax - Vpp/2`.
- Community reports (unverified) that positive DC offset with ARB can
  invert the signal; no automatic workaround.