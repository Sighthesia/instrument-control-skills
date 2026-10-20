# Vertical, Timebase, and Trigger (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 48-53 (channel), pp. 119-121 (timebase), pp. 122-162 (trigger).
Support level: `documented`.

## Channel commands

```text
:CHANnel<X>:SCALe <NRf>          # 2 mV/div .. 10 V/div at x1
:CHANnel<X>:POSition <NRf>
:CHANnel<X>:COUPling {AC|DC|GND}
:CHANnel<X>:PROBe:RATio <NRf>
:CHANnel<X>:PROBe:TYPe {VOLTage|CURRent}
:CHANnel<X>:BWLimit {FULL|20E6}
:CHANnel<X>:DISPlay {ON|OFF}
:CHANnel<X>:INVert {ON|OFF}
:CHANnel<X>:DESKew <NRf>         # -50 ns .. 50 ns
:CHANnel<X>:EXPand {GND|CENTer}
:CHANnel<X>:IMPedance?           # fixed 1 MΩ
```

`X` is 1-2 on 2-channel models and 1-4 on 4-channel models. Sending CH3/CH4 to
a 2-channel instrument is an error; this Skill cannot detect the model from a
command alone, so check `*IDN?` first.

Notes:

- `SCALe` assumes a x1 probe; with a x10 probe the effective scale is ten times
  larger. Set `PROBe:RATio` to match the physical probe.
- `COUPling GND` disconnects the input and shows the ground reference. Do not
  interpret a flat trace as a zero-volt signal.
- `BWLimit 20E6` inserts a 20 MHz limit; it changes rise time and noise.
- `INVert ON` changes displayed polarity, not the trigger source polarity.
- `IMPedance?` is a read-only fixed value; there is no selectable 50 Ω input.

## Timebase

```text
:TIMebase:SCALe <NRf>            # 5 ns/div .. 100 s/div
:TIMebase:POSition <NRf>
:TIMebase:MODe {MAIN|WINDOW|XY}
:TIMebase:EXPand {CENTer|TRIGger}
:TIMebase:WINDow:SCALe <NRf>
:TIMebase:WINDow:POSition <NRf>
```

- `MODe WINDOW` and `XY` change what the main timebase and memory mean; record
  the mode with any waveform.
- `EXPand` changes whether horizontal expansion anchors on the center or the
  trigger point.
- Window scale/position are only meaningful in window mode.
- The sample interval follows the timebase and record length; read
  `Sampling Period` from the waveform header rather than deriving it from a
  guessed formula.

## Trigger sources and model constraints

```text
:TRIGger:SOURce {CH1|CH2|CH3|CH4|EXT|LINe}
```

- CH1/CH2 exist on every model.
- CH3/CH4 exist only on 4-channel models.
- EXT exists only on 2-channel models (GDS-1072B/GDS-1102B/GDS-1202B).
- LINe is the AC line trigger.

## Trigger type

```text
:TRIGger:TYPe {EDGE|DELay|PULSEWidth|VIDeo|RUNT|RISEFall|BUS|TIMEOut}
```

Subtypes have their own parameters. Only configure a subtype when the type is
selected, and record the type in the capture context. BUS decode is an
optional/licensed feature and may not exist on every instrument.

## Common trigger parameters

```text
:TRIGger:LEVel {TTL|ECL|SETTO50|<NRf>}
:TRIGger:HLEVel <NRf>
:TRIGger:LLEVel <NRf>
:TRIGger:MODe {AUTO|NORMAL}
:TRIGger:COUPle {AC|DC|HF|LF}
:TRIGger:NREJ {OFF|ON}
:TRIGger:HOLDoff <NRf>
:TRIGger:EDGe:SLOP {RISE|FALL|EITHER}
:TRIGger:FREQuency?
```

- `AUTO` forces a sweep when no trigger occurs; `NORMAL` waits. A timeout in
  `NORMAL` is a configuration result, not a transport bug.
- `LEVel TTL`/`ECL`/`SETTO50` are presets; `<NRf>` is an explicit level.
- `HLEVel`/`LLEVel` matter for rise/fall and pulse-runt triggers.
- `COUPle` changes the trigger signal path and can hide DC or high-frequency
  content; record it.
- `NREJ` (noise rejection) changes timing sensitivity.
- `HOLDoff` prevents retriggering during a burst or frame.
- `:TRIGger:FREQuency?` returns the measured trigger frequency; it is a
  measurement, not a configuration readback.

## Edge trigger

```text
:TRIGger:EDGe:SLOP {RISE|FALL|EITHER}
:TRIGger:SOURce {CH1|CH2|CH3|CH4|EXT|LINe}
```

The effective source is the general `:TRIGger:SOURce`; record both the type and
the source.

## Delay, pulse-width, runt, rise-fall, video, timeout

These types add qualifiers such as delay time, pulse width, runt levels, or
video standard/line/field. They are documented on pp. 122-162. The Skill does
not enumerate every qualifier in the core scripts; read the manual section for
the selected type and record every non-default parameter.

`TIMEOut` triggers after a defined time without an edge; it is useful for
finding a missing signal but is not a substitute for a valid level.

## Trigger state

`:TRIGger:STATe?` returns `*ARMED`, `*AUTO`, `*READY`, `*SAVE`, or
`*TRIGGER` (pp. 137-138). Interpretation:

- `*ARMED`: waiting for the trigger condition.
- `*AUTO`: automatic mode is sweeping without a trigger.
- `*READY`: pretrigger information is complete and the scope is ready to accept
  a trigger; it does not mean the post-trigger record is complete.
- `*TRIGGER`: a trigger occurred and post-trigger acquisition is in progress.
- `*SAVE`: the scope is in save mode and is not acquiring; do not treat it as
  generic readiness.

For a deterministic download, use `:SINGle`, wait for
`:ACQuire<X>:STATe?` = 1, then `:STOP`.

## Snapshot fields to record

- `*IDN?`
- `:TRIGger:STATe?`, `:TRIGger:TYPe?`, `:TRIGger:SOURce?`, `:TRIGger:MODe?`,
  `:TRIGger:LEVel?`, `:TRIGger:COUPle?`
- `:TIMebase:MODe?`, `:TIMebase:SCALe?`, `:TIMebase:POSition?`
- per channel: `:CHANnel<n>:DISPlay?`, `:SCALe?`, `:POSition?`, `:COUPling?`,
  `:PROBe:RATio?`, `:PROBe:TYPe?`, `:BWLimit?`
- `:ACQuire:RECOrdlength?`

A waveform without this context is structurally valid but not reproducible.
