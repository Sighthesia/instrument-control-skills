# Vertical, Timebase, and Trigger (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Vertical: TOC pp. 47-51; timebase: TOC pp. 113-115; trigger: TOC pp. 116-147.
Support level: CH1 vertical queries and the CH1 scale/coupling set-readback,
timebase scale, trigger level, and several trigger queries are
`hardware-verified`; every other setting is `documented`. Page numbers are
table-of-contents or List of Commands markers (pp. 24-34); the local converted
copy has no body page breaks.

## Channel commands

```text
:CHANnel<n>:SCALe <NRf>                 # 2 mV/div .. 10 V/div at x1
:CHANnel<n>:POSition <NRf>
:CHANnel<n>:COUPling {AC|DC|GND}
:CHANnel<n>:PROBe:RATio <NRf>
:CHANnel<n>:PROBe:TYPe {VOLTage|CURRent}
:CHANnel<n>:BWLimit {FULL|200E+6|100E+6|20E+6}
:CHANnel<n>:DISPlay {ON|OFF}
:CHANnel<n>:INVert {ON|OFF}
:CHANnel<n>:DESKew <NRf>                # -50 ns .. 50 ns
:CHANnel<n>:EXPand {GND|CENTer}
:CHANnel<n>:IMPedance?
```

`<n>` is 1-4 on a 4-channel model. The verified unit is a GDS-2104A; only CH1
was exercised. Send CH3/CH4 only after confirming a 4-channel model from
`*IDN?`.

The manual's list prints these as `:CHANnel:BWLimit`, `:CHANnel:SCALe`, etc.,
without the instance number. The verified unit required the suffix:
`:CHANnel1:SCALe?`, `:CHANnel1:COUPling?`, and `:CHANnel1:IMPedance?`
answered; the bare family forms were not sent. Always include `<n>`.

Verified CH1 observations:

- `:CHANnel1:BWLimit?` -> `FULL`
- `:CHANnel1:COUPling?` -> `DC`; set `AC`, read back, restored `DC`
- `:CHANnel1:DESKew?` -> `0.000e+00`
- `:CHANnel1:DISPlay?` -> `ON`
- `:CHANnel1:EXPand?` -> `GND`
- `:CHANnel1:IMPedance?` -> `1.000000E+06`
- `:CHANnel1:INVert?` -> `OFF`
- `:CHANnel1:POSition?` -> `-2.360E+00`
- `:CHANnel1:PROBe:RATio?` -> `1.000000e+00`
- `:CHANnel1:PROBe:TYPe?` -> `VOLTAGE`
- `:CHANnel1:SCALe?` -> `1.000E+00`; set `2.0`, read back, restored `1.0`

Notes:

- `SCALe` assumes a x1 probe; with a x10 probe the effective scale is ten times
  larger. Set `PROBe:RATio` to match the physical probe before `SCALe`.
- `COUPling GND` disconnects the input and shows the ground reference. Do not
  interpret a flat trace as a zero-volt signal.
- `BWLimit 20E+6` inserts a 20 MHz limit; it changes rise time and noise.
  `200E+6`/`100E+6` are model/bandwidth-dependent.
- `INVert ON` changes displayed polarity, not the trigger source polarity.
- `EXPand` changes whether vertical expansion anchors on ground or center.
- `IMPedance?` is a read-only fixed value; the manual documents 1 MΩ. There is
  no selectable 50 Ω input command in this Skill.

## Timebase

```text
:TIMebase:SCALe <NRf>
:TIMebase:POSition <NRf>
:TIMebase:MODe {MAIN|WINDow|XY}
:TIMebase:EXPand {CENTer|TRIGger}
:TIMebase:WINDow:SCALe <NRf>
:TIMebase:WINDow:POSition <NRf>
```

Manual TOC pp. 113-115.

- `MODe WINDOW` and `XY` change what the main timebase and memory mean; record
  the mode with any waveform. The verified unit reported `MAIN`.
- `EXPand` requires the Horizontal Expansion app and firmware V1.18 or above.
  On the verified V1.18 unit, `:TIMebase:EXPand?` returned no bytes and
  `-221 Settings conflict`; it is documented only and not implemented.
- Window scale/position are only meaningful in window mode.
- The sample interval follows the timebase, record length, and acquisition
  mode; read `Sampling Period` from the waveform header rather than deriving it
  from a guessed formula.

Verified observations:

- `:TIMebase:MODe?` -> `MAIN`
- `:TIMebase:POSition?` -> `0.000E+00`
- `:TIMebase:SCALe?` -> `5.000000E-04`; set `1.000000E-03`, read back, restored

## Trigger sources and model constraints

```text
:TRIGger:SOURce {CH1|CH2|CH3|CH4|EXT|LINe|D0..D15|?}
```

- CH1/CH2 exist on every model.
- CH3/CH4 exist only on 4-channel models.
- EXT is the external trigger input; confirm it is present on the model.
- LINe is the AC line trigger.
- D0-D15 require the optional DS2-8LA/16LA logic hardware. The verified unit
  did not have it; bus/logic queries returned `-240`.
- The verified unit reported `:TRIGger:SOURce?` -> `CH1`.

## Trigger type and parameters

```text
:TRIGger:TYPe {EDGe|DELay|PULSEWidth|VIDeo|RUNT|RISEFall|LOGic|BUS|TIMEOut|?}
:TRIGger:MODe {AUTo|NORMal|?}
:TRIGger:COUPle {AC|DC|?}                   # edge and delay only
:TRIGger:NREJ {OFF|ON|?}
:TRIGger:REJect {OFF|HF|LF|?}
:TRIGger:HOLDoff <NRf>
:TRIGger:LEVel {TTL|ECL|SETTO50|<NRf>|?}
:TRIGger:HLEVel {TTL|ECL|<NRf>|?}
:TRIGger:LLEVel {TTL|ECL|<NRf>|?}
:TRIGger:EDGe:SLOP {RISe|FALL|EITher|?}
:TRIGger:FREQuency?
:TRIGger:ALTernate?
```

Manual TOC pp. 116-147.

- `AUTO` is documented as **"Auto trigger (Untriggered roll)"**: it keeps
  sweeping even with no trigger. A completed download in `AUTO` proves a
  **frame**, never a **triggered frame**. Use `NORMAL` for any capture whose
  value depends on a trigger condition. A timeout in `NORMAL` is a
  configuration result, not a transport bug.
- `LEVel` accepts presets `TTL`, `ECL`, `SETTO50` and a numeric level. The
  verified run set a numeric `2.600E+00`, read it back, and restored
  `2.520E+00`.
- `HLEVel`/`LLEVel` matter for rise/fall and pulse-runt triggers.
- `COUPle` is AC or DC only; frequency rejection is a separate
  `:TRIGger:REJect` setting (`OFF`, `HF`, `LF`).
- `NREJ` (noise rejection) changes timing sensitivity.
- `HOLDoff` prevents retriggering during a burst or frame.
- `:TRIGger:FREQuency?` returns the measured trigger frequency; it is a
  measurement, not a configuration readback. V1.18 returned `2.000E+00`
  followed by two LFs; the second LF is framing evidence.

Verified trigger observations:

- `:TRIGger:TYPe?` -> `EDGE`
- `:TRIGger:SOURce?` -> `CH1`
- `:TRIGger:COUPle?` -> `DC`
- `:TRIGger:NREJ?` -> `OFF`
- `:TRIGger:REJect?` -> `OFF`
- `:TRIGger:MODe?` -> `AUTO`
- `:TRIGger:HOLDoff?` -> `1.000e-08`
- `:TRIGger:EDGe:SLOP?` -> `RISE`
- `:TRIGger:STATe?` -> `AUTO`/`ARMED`/`SAVE`/`READY`
- `:TRIGger:LEVel?` -> `2.520E+00`

## Trigger state

`:TRIGger:STATe?` returns `ARMED`, `AUTO`, `SAVE`, or `READY` on V1.18; the
manual prints `*ARMED`, `*AUTO`, `*READY`, `*SAVE`, `*TRIGGER` (TOC p. 131).
Accept both spellings. Interpretation:

- `ARMED`: waiting for the trigger condition.
- `AUTO`: automatic mode is sweeping without a trigger; the record is not a
  triggered record.
- `READY`: pretrigger information has been acquired and the scope is ready to
  accept a trigger; it does not mean the post-trigger record is complete.
- `SAVE`: stop/save state; do not treat it as generic readiness.

For a deterministic download, use `:SINGle`, wait for
`:ACQuire1:STATe?` = 1, then `:STOP`. The bundled `capture` helper does not
force a trigger and restores continuous acquisition after a download.

## Trigger subtypes (documented, not implemented)

These types add qualifiers; read the manual section for the selected type and
record every non-default parameter. The Skill does not implement their
configuration:

- Delay: `:TRIGger:DELay:SLOP`, `:DELay:TYPe`, `:DELay:TIMe`,
  `:DELay:EVENt`, `:DELay:LEVel`.
- Pulse width: `:TRIGger:PULSEWidth:POLarity`, `:TRIGger:PULSe:WHEn`,
  `:TRIGger:PULSe:TIMe`.
- Runt: `:TRIGger:RUNT:POLarity`, `:RUNT:WHEn`, `:RUNT:TIMe`.
- Rise/fall: `:TRIGger:RISEFall:SLOP`, `:RISEFall:WHEn`, `:RISEFall:TIMe`.
- Video: `:TRIGger:VIDeo:TYPe`, `:VIDeo:FIELd`, `:VIDeo:LINe`,
  `:VIDeo:POLarity`.
- Logic/bus: `:TRIGger:LOGic:*`, `:TRIGger:BUS:*` (optional DS2-8LA/16LA).
- Timeout: `:TRIGger:TIMEOut:WHEn`, `:TIMEOut:TIMER`.
- Alternate: `:TRIGger:ALTernate`.

## Snapshot fields to record

- `*IDN?`
- `:TRIGger:STATe?`, `:TRIGger:TYPe?`, `:TRIGger:SOURce?`, `:TRIGger:MODe?`,
  `:TRIGger:LEVel?`, `:TRIGger:COUPle?`, `:TRIGger:NREJ?`,
  `:TRIGger:REJect?`, `:TRIGger:HOLDoff?`
- `:TIMebase:MODe?`, `:TIMebase:SCALe?`, `:TIMebase:POSition?`
- per channel: `:CHANnel<n>:DISPlay?`, `:SCALe?`, `:POSition?`, `:COUPling?`,
  `:PROBe:RATio?`, `:PROBe:TYPe?`, `:BWLimit?`
- `:ACQuire:MODe?`, `:ACQuire:RECOrdlength?`, `:HEADer?`

A waveform without this context is structurally valid but not reproducible.

## Manual defects relevant here

- The list omits the channel/slot suffix; send `:CHANnel1:...`,
  `:ACQuire1:...`, `:MEASure:SOURce1 ...`.
- The manual prints trigger states with a leading `*`; V1.18 omitted it.
- `:TIMebase:EXPand?` is documented for V1.18 but returned `-221 Settings
  conflict` because the Horizontal Expansion app was not installed.
- `:TRIGger:FREQuency?` returned an extra LF; it is not a second response.
