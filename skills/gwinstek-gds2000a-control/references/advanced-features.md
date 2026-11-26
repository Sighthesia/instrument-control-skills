# Advanced Features (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Math: TOC pp. 53-60; cursors: TOC pp. 61-71; display: TOC pp. 71-74; reference:
TOC pp. 108-110; bus decode: TOC pp. 157-167; mark: TOC pp. 168-169; search:
TOC pp. 170-194; digital: TOC pp. 196-201; label: TOC pp. 203-210; utility:
TOC p. 212; segments: TOC pp. 213-220; DVM: TOC pp. 221-222; function
generator: TOC pp. 223-225; Go_NoGo/templates: TOC pp. 226-231; data logging:
TOC pp. 232-234. Support level: a few read-only state queries and the
`:BUZZER` set/readback are `hardware-verified`; **all configuration or
execution paths described here are `documented` and not implemented by this
Skill**. Page numbers are table-of-contents or List of Commands markers
(pp. 24-34); the local converted copy has no body page breaks.

These families are documented for orientation. The bundled scripts do not
implement them, and some are optional, licensed, or model-dependent. Confirm
the installed option and the displayed menu before sending any command.

## Math and FFT (TOC pp. 53-60)

```text
:MATH:DISP {OFF|ON|?}
:MATH:TYPe {DUAL|ADVanced|FFT|?}
:MATH:DUAL:SOURce<X> {CH1..CH4}
:MATH:DUAL:OPERator {PLUS|MINus|MULTiply|DIVide}
:MATH:DUAL:POSition <NRf>
:MATH:DUAL:SCALe <NRf>
:MATH:FFT:SOURce {CH1..CH4}
:MATH:FFT:MAG {DB|LINEar}
:MATH:FFT:WINDow ...
:MATH:FFT:POSition <NRf>
:MATH:FFT:SCALe <NRf>
:MATH:FFT:HORizontal:SCALe <NRf>
:MATH:ADVanced:OPERator ...
:MATH:ADVanced:SOURce ...
:MATH:ADVanced:EDIT:SOURce ...
:MATH:ADVanced:EDIT:OPERator ...
:MATH:ADVanced:POSition <NRf>
:MATH:ADVanced:SCALe <NRf>
```

Verified read-only state: `:MATH:DISP?` -> `OFF`, `:MATH:TYPe?` -> `DUAL`.

Math/FFT configuration is not implemented. Sources must be active, and CH3/CH4
require a 4-channel model. Division by zero, FFT windowing, and advanced
operators change the result's meaning, so record the operation and parameters
with the data. `MATH` as a measurement source depends on this configuration.

## Cursors (TOC pp. 61-71)

```text
:CURSor:MODe {OFF|ON|?}
:CURSor:SOURce {CH1..CH4|MATH|REF1..REF4}
:CURSor:HUNI ... / :CURSor:HUSE ...
:CURSor:VUNI ... / :CURSor:VUSE ...
:CURSor:H1Position ... / :CURSor:H2Position ... / :CURSor:HDELta?
:CURSor:V1Position ... / :CURSor:V2Position ... / :CURSor:VDELta?
:CURSor:XY:RECTangular:...
:CURSor:XY:POLar:...
:CURSor:XY:PRODuct:...
:CURSor:XY:RATio:...
```

Cursor configuration is not implemented. Cursor readings depend on mode,
source, and position. A cursor value is not a replacement for an automated
measurement; record both. Cursor state is part of the screenshot context.

## Display (TOC pp. 71-74)

```text
:DISPlay:INTensity:WAVEform {<NRf>|?}
:DISPlay:INTensity:GRATicule {<NRf>|?}
:DISPlay:PERSistence {OFF|INFInite|<seconds>|?}
:DISPlay:GRATicule {FULL|GRID|CROSs|FRAMe|?}
:DISPlay:WAVEform {VECTor|DOT|?}
:DISPlay:OUTPut?
```

Display configuration is not implemented. Display commands change what a
screenshot shows but not the acquired samples. Record non-default display
settings when a screenshot is evidence.

`:DISPlay:OUTPut?` is the raw screen-image readback; see
[save-and-screenshot.md](save-and-screenshot.md). It is body-only (Appendix A)
and the RLE image is not decoded.

## Reference waveforms (TOC pp. 108-110)

```text
:REF:DISPlay {OFF|ON|?}
:REF:TIMebase:POSition <NRf>
:REF:TIMebase:SCALe <NRf>
:REF:OFFSet <NRf>
:REF:SCALe <NRf>
```

Reference waveform configuration is not implemented. A reference waveform must
first be saved before it can be displayed. `:REF:*` commands act on the
selected reference (REF1-REF4); confirm the target before changing or
displaying it.

## Bus decode and digital channels (TOC pp. 157-201)

```text
:BUS1 {ON|OFF|?}
:BUS1:STATE {ON|OFF|?}
:BUS1:TYPe {I2C|UART|SPI|PARallel|?}
:BUS1:I2C:...
:BUS1:UART:...
:BUS1:SPI:...
:BUS1:PARallel:...
:BUS1:DISplay:FORMAt ...
:D:DISPlay ... / :D:POSition ...
:DISPlay:DIGital:HEIght ...
:DIGital:GROUP:THREshold ...
:DIGital:ANAlog:A:DISPlay ... / :DIGital:ANAlog:A:RATio ...
:D:MEMory? / :D:LMEMory? / :DIGital:MEMory? / :DIGital:LMEMory?
:LISTer:DATA?
```

Requires the optional **DS2-8LA** or **DS2-16LA** logic analyzer/bus decode
hardware. The verified unit did not have it: `:BUS1:STATE?` returned no bytes
and `-240 Hardware error`. Bus decode and digital channels are not implemented.

- Threshold, bit rate, polarity, and source channel must match the physical
  bus. A decoded packet is not proof that the analog signal was valid.
- `:LISTer:DATA?` returns decode results; length and format depend on the bus
  and buffer, so preserve the raw response.
- Digital channel names D0-D15 are option-dependent; do not send them on a
  unit without the logic hardware.

## Search (TOC pp. 170-194)

```text
:SEARCH:STATE {ON|OFF|?}
:SEARCH:TOTAL?
:SEARCH:TRIGger:TYPe ...
:SEARCH:TRIGger:SOURce ...
:SEARCH:TRIGger:EDGE:SLOP ...
:SEARCH:TRIGger:LEVel ...
:SEARCH:TRIGger:LOGic:...
:SEARCH:TRIGger:BUS:...
:SEARCH:COPY ...
```

Verified read-only state: `:SEARCH:STATE?` -> `OFF`, `:SEARCH:TOTAL?` -> `0`.

Search configuration/execution is not implemented. Search scans the acquired
record for events without re-acquiring. Event definitions mirror trigger
types; results are positions within the record. Record length and timebase
determine resolution. A found event is not necessarily a real signal rather
than noise.

## Segments (TOC pp. 213-220)

```text
:SEGMents:STATE {ON|OFF|?}
:SEGMents:CURRent?
:SEGMents:TOTalnum?
:SEGMents:TIMe?
:SEGMents:DISPALL ...
:SEGMents:MEASure:...
:SEGMents:SAVe ...
```

Verified read-only state: `:SEGMents:STATE?` -> `OFF`,
`:SEGMents:TOTalnum?` -> `1.000E+01`.

Segment acquisition/measurement is not implemented. Segmented acquisition
stores many triggered records. Segment count, current segment, and
per-segment measurements must be recorded together; a single `VALUE?` without
the segment index is ambiguous.

## DVM (TOC pp. 221-222)

```text
:DVM:STATE {ON|OFF|?}
:DVM:SOURce {CH1..CH4|?}
:DVM:MODe ...
```

DVM is optional. On the verified unit `:DVM:STATE?` returned no bytes and
`-221 Settings conflict`; the DVM software was not active. DVM is not
implemented. Its value is not `:MEASure:MEAN?` or a cursor reading; record the
mode.

## Function generator (DS2-FGN, TOC pp. 223-225)

```text
:FUNCtion1:MODe ...
:FUNCtion1:FREQuency ...
:FUNCtion1:AMPlitude ...
:FUNCtion1:OFFSet ...
:FUNCtion1:DUTYcycle ...
```

Requires the optional **DS2-FGN** module. The verified unit did not have it:
the bare `:FUNCtion:MODe?` returned `-131 Invalid suffix`, and the suffixed
`:FUNCtion1:MODe?` returned `-240 Hardware error`. The function generator is
not implemented. Do not treat the output as a calibrated source.

## Go_NoGo and templates (TOC pp. 226-231)

```text
:GONogo:CLEar ...
:GONogo:EXECute ...
:GONogo:FUNCtion ...
:GONogo:NGCount? ...
:GONogo:NGDefine ...
:GONogo:SOURce ...
:GONogo:VIOLation? ...
:GONogo:SCRipt? ...
:TEMPlate:MODe ...
:TEMPlate:MAXimum ...
:TEMPlate:MINimum ...
:TEMPlate:POSition:MAXimum ...
:TEMPlate:POSition:MINimum ...
:TEMPlate:TOLerance ...
:TEMPlate:SAVe:...
```

The Go_NoGo app was not active on the verified unit. Most queries returned an
empty line; `:GONogo:SCRipt?` returned `OFF`. The local List of Commands omits
this block (TOC pp. 226-231), so these forms are in Appendix A rather than the
339-row denominator. Go-NoGo is not implemented.

A pass/fail result depends on the template and tolerance, which must be stored
with the result. Template saves write files or memory and follow the same
no-overwrite rule.

## Data logging (TOC pp. 232-234)

```text
:DATALOG:STATE {ON|OFF|?}
:DATALOG:SOURce ...
:DATALOG:SAVe ...
:DATALOG:INTerval <NRf>
:DATALOG:DURation <NRf>
```

Requires the Datalog App and the **DS2-LAN** option, and firmware V1.18 or
above. On the verified unit `:DATALOG:STATE?` returned no bytes and `-221
Settings conflict`. Datalog is not implemented.

Datalog writes periodic readings to storage. Duration x interval bounds the
file size; confirm storage and filename first. The Skill never starts a log.

## Labels and marks (TOC pp. 168-169, 203-210)

```text
:CHANnel<n>:LABel ... / :CHANnel<n>:LABel:DISPlay ...
:REF:LABel ... / :REF:LABel:DISPlay ...        # examples use :REF1:
:BUS1:LABel ... / :BUS1:LABel:DISPlay ...
:D:LABel ... / :D:LABel:DISPlay ...            # examples use :D0:
:DIGital:ANAlog:A:LABel ...
:SET:LABel ...
:MARK ... / :MARK:CREATE ... / :MARK:DELEte ...
```

Labels and marks are not implemented. They annotate display/record positions
but are not measurement evidence. Do not treat a label or mark as a captured
value.

## Ethernet and time (TOC pp. 155-156)

```text
:ETHERnet:DHCP {OFF|ON|?}
:DATe "<YYYYMMDDhhmmss>"
```

`:ETHERnet:DHCP` requires the **DS2-LAN** option. Ethernet is documented in
[remote-session.md](remote-session.md) and was not exercised. `:DATe` changes
the instrument clock and is not implemented; do not set it without operator
authorization.

## Utility

`:BUZZER {OFF|ON|?}` was verified: `:BUZZER?` -> `OFF`, and `:BUZZER OFF`
read back `OFF`. It is not part of the advanced measurement families; it is
listed here because it is a panel/utility setting.

## Conditional support

| Feature | Condition |
|---|---|
| Math/FFT configuration | Model/firmware support; verify channels and mode |
| Cursors, display, reference | Model/firmware support; confirm menus |
| Bus decode / digital channels / bus trigger | DS2-8LA or DS2-16LA installed |
| DVM | DVM software active |
| Function generator | DS2-FGN installed |
| Go_NoGo / templates | Go_NoGo app active |
| Data logging | Datalog App + DS2-LAN, firmware V1.18+ |
| Ethernet | DS2-LAN installed, socket server enabled |
| GPIB | DS2-GPIB installed |
| CH3/CH4 | 4-channel model |
| Digital D0-D15 | DS2-8LA/16LA installed |

When an option is absent, the verified unit returned `-240 Hardware error`,
`-221 Settings conflict`, or an empty line. Preserve the error; do not
silently fall back to another feature.
