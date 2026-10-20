# Measurements (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 81-113. Support level: `documented`.

## Source selection

```text
:MEASure:SOURce1 {CH1|CH2|CH3|CH4|MATH}
:MEASure:SOURce2 {CH1|CH2|CH3|CH4|MATH}
:MEASure:SOURce1?
:MEASure:SOURce2?
```

`SOURce1` and `SOURce2` are the two measurement sources used by individual
items and by phase/delay pairs. The manual's syntax is
`:MEASure:SOURce<X>` with `<X>` = 1 or 2 (p. 82). CH3/CH4 require a 4-channel
model.

`MATH` is allowed as a source, but its correctness depends on the math
configuration (`:MATH:*`), which this Skill does not validate.

## Individual items

Each item returns `<NR3>` or `Chan Off`:

- `<NR3>`: a number in scientific or decimal notation.
- `Chan Off`: the selected source channel is not activated. Treat as
  `INCOMPLETE`, never as zero.

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
| Cycle RMS | `:MEASure:CRMS?` | crms | V or A |
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
unit suffix. The implied unit follows from the quantity name (time, hertz,
percent, degrees, voltage/current, or count). For voltage/current and area,
the unit depends on `:CHANnel<X>:PROBe:TYPe`; the Skill reports
`"V or A"` / `"V·s or A·s"` unless the caller supplies `--unit V|A` (or
`V·s|A·s`). Relay pairs such as `FRRDelay` use source1 and source2; select both
before reading.

Count items (`PPULSE`, `NPULSE`, `PEDGE`, `NEDGE`) are unitless and still
return `<NR3>` in the manual's examples.

## Method and reference levels

```text
:MEASure:METHod {AUTO|HISTogram|MINMax}
:MEASure:GATing {OFF|SCREEN|CURSOR}
```

- `METHod` chooses how High/Low reference levels are derived.
- Gating restricts the measurement window to the screen or cursors; results
  from different gating settings are not comparable.
- Reference percentages (high/low, middle) are documented around pp. 82-84.
  Record any non-default value with the measurement.

## Advanced eight-slot measurements

```text
:MEASUrement:MEAS<X>:SOURCE<X> {CH1|CH2|CH3|CH4|MATH}
:MEASUrement:MEAS<X>:TYPe <type>
:MEASUrement:MEAS<X>:STATE {OFF|ON|?}
:MEASUrement:MEAS<X>:VALue?
:MEASUrement:MEAS<X>:MAXimum?
:MEASUrement:MEAS<X>:MEAN?
:MEASUrement:MEAS<X>:MINImum?
:MEASUrement:MEAS<X>:STDdev?
```

Manual pp. 106-113. `<X>` selects one of eight measurement slots. The slot type
is set independently, and `VALue?` etc. are only meaningful when the slot is
enabled and the source is valid.

Statistics:

```text
:MEASUrement:STATIstics:MODe {OFF|ON|?}
:MEASUrement:STATIstics:WEIghting {<NR1>|?}   # 2..1000 samples
:MEASUrement:STATIstics {RESET}
```

- `MODe ON` displays statistics; it does not necessarily reset them.
- `WEIghting` sets the sample count used for statistics (2-1000).
- `:MEASUrement:STATIstics RESET` clears accumulated values. Do not reset
  operator statistics without authorization.
- `MAXimum?`, `MEAN?`, `MINImum?`, and `STDdev?` describe the accumulated
  sample set, not one acquisition.

## Acquisition context

A measurement is only meaningful with its context. Record:

- `*IDN?` model and firmware;
- `:MEASure:SOURce1?`, `:MEASure:SOURce2?`;
- `:MEASure:METHod?`, `:MEASure:GATing?`;
- channel scale, coupling, probe ratio/type, bandwidth limit;
- timebase scale and mode;
- trigger type, source, level, mode, coupling;
- record length and whether the acquisition was stopped.

## Status handling

| Response | Status | Meaning |
|---|---|---|
| `<NR3>` | `COMPLETE` | Structurally valid measurement |
| `Chan Off` | `INCOMPLETE` | Source not active |
| `NaN`, `Inf` | `INVALID` | Not a documented finite value |
| Non-numeric text | `INVALID` | Not an `<NR3>` |
| Missing terminator | `INCOMPLETE` | Transport framing failed |
| Extra bytes after the line | `INVALID` | Response pairing is ambiguous |

A finite number is not proof that the probe, coupling, or trigger was correct.
