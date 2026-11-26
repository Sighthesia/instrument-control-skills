# Measurements (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Measure commands: TOC pp. 78-99; slotted measurement commands: TOC pp. 101-107.
Support level: `:MEASure:PK2PK?`, the source-off sentinel, and the
slotted-measurement no-result sentinel are `hardware-verified`; every other
item is `documented`. Page numbers are table-of-contents or List of Commands
markers (pp. 24-34); the local converted copy has no body page breaks.

## Source selection

```text
:MEASure:SOURce1 {CH1|CH2|CH3|CH4|MATH|?}
:MEASure:SOURce2 {CH1|CH2|CH3|CH4|MATH|?}
:MEASure:SOURce1?
:MEASure:SOURce2?
```

`SOURce1` is the source for single-channel measurements; `SOURce2` is the
second source for delay/phase pairs. The manual's syntax is
`:MEASure:SOURce<n>` with `<n>` = 1 or 2. CH3/CH4 require a 4-channel model.
`MATH` is allowed but depends on the math configuration; this Skill does not
validate it.

The bare `:MEASure:SOURce` returned `-131 Invalid suffix` on V1.18; always send
the numeric suffix. The verified run changed `:MEASure:SOURce1` from `CH1` to
`CH2`, read `Ch Off`, and restored `CH1`.

## Individual items

Each item returns `<NR3>` or `Chan Off`/`Ch Off`. There is **no channel
parameter** on an individual item: `:MEASure:PK2PK? CH1` returned
`-108 Parameter not allowed`. Select the source first.

| Mnemonic | Command | Quantity | Implied unit |
|---|---|---|---|
| Fall time | `:MEASure:FALL?` | fall | s |
| Fall overshoot | `:MEASure:FOVShoot?` | fovshoot | % |
| Fall preshoot | `:MEASure:FPReshoot?` | fpreshoot | % |
| Frequency | `:MEASure:FREQuency?` | frequency | Hz |
| Negative width | `:MEASure:NWIDth?` | nwidth | s |
| Positive duty | `:MEASure:PDUTy?` | pduty | % |
| Period | `:MEASure:PERiod?` | period | s |
| Positive width | `:MEASure:PWIDth?` | pwidth | s |
| Rise time | `:MEASure:RISe?` | rise | s |
| Rise overshoot | `:MEASure:ROVShoot?` | rovshoot | % |
| Rise preshoot | `:MEASure:RPReshoot?` | rpreshoot | % |
| Positive pulses | `:MEASure:PPULSE?` | ppulse | count |
| Negative pulses | `:MEASure:NPULSE?` | npulse | count |
| Positive edges | `:MEASure:PEDGE?` | pedge | count |
| Negative edges | `:MEASure:NEDGE?` | nedge | count |
| Amplitude | `:MEASure:AMPlitude?` | amplitude | V or A |
| Mean | `:MEASure:MEAN?` | mean | V or A |
| Cycle mean | `:MEASure:CMEan?` | cmean | V or A |
| High level | `:MEASure:HIGH?` | high | V or A |
| Low level | `:MEASure:LOW?` | low | V or A |
| Maximum | `:MEASure:MAX?` | max | V or A |
| Minimum | `:MEASure:MIN?` | min | V or A |
| Peak-to-peak | `:MEASure:PK2PK?` | pk2pk | V or A |
| RMS | `:MEASure:RMS?` | rms | V or A |
| Area | `:MEASure:AREa?` | area | V·s or A·s |
| Cycle area | `:MEASure:CARea?` | carea | V·s or A·s |
| FRR delay | `:MEASure:FRRDelay?` | frrdelay | s |
| FRF delay | `:MEASure:FRFDelay?` | frfdelay | s |
| FFR delay | `:MEASure:FFRDelay?` | ffrdelay | s |
| FFF delay | `:MEASure:FFFDelay?` | fffdelay | s |
| LRR delay | `:MEASure:LRRDelay?` | lrrdelay | s |
| LRF delay | `:MEASure:LRFDelay?` | lrfdelay | s |
| LFR delay | `:MEASure:LFRDelay?` | lfrdelay | s |
| LFF delay | `:MEASure:LFFDelay?` | lffdelay | s |
| Phase | `:MEASure:PHAse?` | phase | deg |

Unit note: the manual documents the return as `<NR3>` and does not append a
unit suffix. The implied unit follows from the quantity name. For
voltage/current and area, the unit depends on `:CHANnel<n>:PROBe:TYPe`; the
Skill reports `"V or A"` / `"V·s or A·s"` unless the caller supplies
`--unit V|A` (or `V·s|A·s`). Relay pairs such as `FRRDelay` use source1 and
source2; select both before reading.

Count items (`PPULSE`, `NPULSE`, `PEDGE`, `NEDGE`) are unitless and still
return `<NR3>` in the manual's examples.

## Method and gating

```text
:MEASure:METHod {AUTo|HIStogram|MINMax|?}
:MEASure:GATing {OFF|SCREen|CURSor|?}
```

- `METHod` chooses how High/Low reference levels are derived. The verified unit
  reported `AUTO`.
- Gating restricts the measurement window to the full record, the screen, or
  the cursors. The verified unit reported `SCREEN`. Results from different
  gating settings are not comparable.
- Rise time, fall time, duty cycle, pulse width, and phase are derived from the
  method's reference levels. A rise time quoted without the method and gating
  is not reproducible.
- This Skill does not expose separate reference-level percentage commands;
  read them with the instrument's own menus or documented query forms if they
  exist in the firmware.

## Slotted measurements (documented, not configured by the helper)

```text
:MEASUrement:MEAS<n>:SOURce1 {CH1|CH2|CH3|CH4|MATH|?}
:MEASUrement:MEAS<n>:SOURce2 {CH1|CH2|CH3|CH4|MATH|?}
:MEASUrement:MEAS<n>:TYPe <type>
:MEASUrement:MEAS<n>:STATE {OFF|ON|1|0|?}
:MEASUrement:MEAS<n>:VALue?
:MEASUrement:MEAS<n>:MAXimum?
:MEASUrement:MEAS<n>:MEAN?
:MEASUrement:MEAS<n>:MINImum?
:MEASUrement:MEAS<n>:STDdev?
```

Manual TOC pp. 101-107. `<n>` selects one of eight measurement slots. The list
omits the slot number; send `:MEASUrement:MEAS1:...`.

- `TYPe` is a required write, not a read-only label. The documented enum is
  `PK2pk`, `MAXimum`, `MINImum`, `AMPlitude`, `HIGH`, `LOW`, `MEAN`, `CMEan`,
  `RMS`, `CRMs`, `AREa`, `CARea`, `ROVShoot`, `FOVShoot`, `RPReshoot`,
  `FPReshoot`, `FREQuency`, `PERIod`, `RISe`, `FALL`, `PWIdth`, `NWIdth`,
  `PDUTy`, `PPULSE`, `NPULSE`, `PEDGE`, `NEDGE`, `FRRDelay`, `FRFDelay`,
  `FFRDelay`, `FFFDelay`, `LRRDelay`, `LRFDelay`, `LFRDelay`, `LFFDelay`,
  `PHAse`.
- `STATE` returns `0`/`1`, not `OFF`/`ON`. A `0` means the slot is off; a
  following `VALue?` result is not a measurement. The verified unit returned
  `9.9E+37` for `:MEASUrement:MEAS1:VALue?` while `STATE?` was `0`; the parser
  treats that token as `INCOMPLETE`.
- Source, type, and state are set independently. `VALue?` and the statistics
  queries are only meaningful when the slot is enabled and the source is
  valid.
- The bundled helper queries individual `:MEASure:*?` items; it does not
  configure slotted measurements.

## Statistics

```text
:MEASUrement:STATIstics:MODe {OFF|ON|?}
:MEASUrement:STATIstics:WEIghting {2..1000|?}
:MEASUrement:STATIstics {RESET}
```

- `MODe ON` displays statistics; it does not necessarily reset them.
- `WEIghting` sets the sample count used for statistics (2-1000).
- `:MEASUrement:STATIstics {RESET}` clears accumulated values. Do not reset
  operator statistics without authorization.
- `MAXimum?`, `MEAN?`, `MINImum?`, and `STDdev?` describe the accumulated
  sample set, not one acquisition.

## Acquisition context

A measurement is only meaningful with its context. Record:

- `*IDN?` model, serial, and firmware;
- `:MEASure:SOURce1?`, `:MEASure:SOURce2?`;
- `:MEASure:METHod?`, `:MEASure:GATing?`;
- channel scale, coupling, probe ratio/type, bandwidth limit;
- timebase scale/mode/position;
- trigger type, source, level, mode, coupling, and state;
- acquisition mode, record length, and whether the acquisition was stopped.

## Visible-window behaviour (2026-11-26)

`:MEASure:*?` answers from the visible acquisition window on this firmware. A
real 2 Vpp sine on CH1 was reported as `?` for frequency, period, and amplitude
while CH1 sat at **1 V/div with position -2.48 div**, which pushed the trace
off the screen. Setting `:CHANnel1:SCALe 0.5` and `:CHANnel1:POSition 0` made
the same signal read `1.000E+03 Hz`, `1.000E-03 s`, `2.060E+00 Vpp`, and
`7.270E-01 V RMS`.

Do not report "no signal" from a `?` alone. First centre the channel, make the
signal span at least about two divisions, check `:CHANnel1:DISPlay?`, and check
`:TRIGger:STATe?`; only then treat `?` as evidence about the input.

## Status handling

| Response | Status | Meaning |
|---|---|---|
| `<NR3>` | `COMPLETE` | Structurally valid measurement |
| `Ch Off` / `Chan Off` | `INCOMPLETE` | Source channel not activated; `value: null` |
| `9.9E+37` / `9.9E37` | `INCOMPLETE` | Slotted measurement disabled/no result |
| `NaN`, `Inf` | `INVALID` | Not a documented finite value |
| Non-numeric text | `INVALID` | Not an `<NR3>` |
| Unit suffix | `INVALID` | The instrument returns a bare NR3 token |
| Missing terminator | `INCOMPLETE` | Transport framing failed |
| Extra bytes after the line | `INVALID` | Response pairing is ambiguous |

A finite number is not proof that the probe, coupling, gating, or trigger was
correct. A `COMPLETE` measurement is structurally valid, not calibrated.
