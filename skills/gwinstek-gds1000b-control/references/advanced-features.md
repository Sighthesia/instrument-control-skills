# Advanced Features (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 54-77 (math, cursors, display), pp. 170-249 (bus, search, segments, DVM,
Go-NoGo, datalog, remote disk). Support level: `documented`.

These families are documented for orientation. **The core scripts do not
implement them**, and some are optional, licensed, or model-dependent. Confirm
the installed option and the displayed menu before sending commands.

## Math (pp. 54-62)

```text
:MATH:DISP {OFF|ON|?}
:MATH:TYPe {DUAL|ADVanced|FFT|?}
:MATH:DUAL:SOURce<X> {CH1..CH4}
:MATH:DUAL:OPERator {PLUS|MINus|MULTiply|DIVide}
:MATH:DUAL:POSition <NRf> / :MATH:DUAL:SCALe <NRf>
:MATH:FFT:SOURce {CH1..CH4}
:MATH:FFT:MAG {DB|LINEar} / :MATH:FFT:WINDow ...
:MATH:FFT:POSition <NRf> / :MATH:FFT:SCALe <NRf>
:MATH:DEFine ...
```

Operations include add, subtract, multiply, divide, FFT, and advanced
expressions; exact mnemonics and limits are on pp. 54-62. Sources must be
active, and CH3/CH4 require a 4-channel model. Division by zero and FFT
windowing change the result's meaning, so record the operation and parameters
with the data. `MATH` as a measurement source depends on this configuration.
The digital filter (`:ACQuire:FILTer*`, pp. 43-44) applies only with the Digital
Filter app installed; do not assume it exists.

## Cursors (pp. 63-73)

```text
:CURSor:MODe {OFF|ON|?} / :CURSor:SOURce {CH1..CH4|MATH|REF1..REF4}
:CURSor:HUNI ... / :CURSor:HUSE ... / :CURSor:VUNI ... / :CURSor:VUSE ...
:CURSor:H1Position ... / :CURSor:H2Position ... / :CURSor:HDELta?
:CURSor:V1Position ... / :CURSor:V2Position ... / :CURSor:VDELta?
:CURSor:XY:... (rectangular, polar, product, ratio)
```

Cursor readings depend on mode, source, and position. A cursor value is not a
replacement for an automated measurement; record both. Cursor state is part of
the screenshot context.

## Display (pp. 74-77)

Display commands control persistence, intensity, grid, and related screen
settings. They change what a screenshot shows but not the acquired samples.
Record non-default display settings when a screenshot is evidence.

## Bus decode (pp. 171-184)

```text
:BUS1:STATE {ON|OFF|?}
:BUS1:TYPe {I2C|UART|SPI|CAN|LIN}
:BUS1:INPut ...
:BUS1:I2C:SCLK:SOURce ... / :BUS1:I2C:SDA:SOURce ...
:BUS1:UART:BITRate ... / :BUS1:UART:DATABits ... / :BUS1:UART:PARIty ...
:BUS1:SPI:SCLK:SOURce ... / :BUS1:SPI:MOSI:SOURce ...
:BUS1:CAN:... / :BUS1:LIN:...
:LISTer:DATA?
```

- Bus decode is an optional/licensed feature; confirm the option first.
- Threshold, bit rate, polarity, and source channel must match the physical
  bus. A decoded packet is not proof that the analog signal was valid.
- `:LISTer:DATA?` returns decode results; length and format depend on the bus
  and buffer, so preserve the raw response.
- Bus triggering (`:TRIGger:BUS:B1:*`, pp. 139-162) is a separate family with
  the same option caveat.

## Search (pp. 188-220)

```text
:SEARCH:STATE {ON|OFF|?}
:SEARCH:TOTAL?
:SEARCH:TRIGger:TYPe ... / :SEARCH:TRIGger:SOURce ...
:SEARCH:TRIGger:EDGE:SLOP ... / :SEARCH:TRIGger:LEVel ...
:SEARCH:FFTPeak:METHod ...
```

Search scans the acquired record for events without re-acquiring. Event
definitions mirror trigger types; results are positions within the record.
Record length and timebase determine resolution. A found event is not
necessarily a real signal rather than noise. Marks (`:MARK:CREATE`,
`:MARK:DELEte`, pp. 185-187) annotate record positions but are not measurement
evidence.

## Segments (pp. 227-235)

```text
:SEGMents:STATE {ON|OFF|?}
:SEGMents:CURRent? / :SEGMents:TOTalnum? / :SEGMents:TIMe?
:SEGMents:SAVe ... / :SEGMents:MEASure:...
```

Segmented acquisition stores many triggered records. Segment count, current
segment, and per-segment measurements must be recorded together; a single
`VALue?` without the segment index is ambiguous.

## DVM (pp. 236-237)

```text
:DVM:STATE {ON|OFF|?} / :DVM:SOURce {CH1..CH4}
:DVM:MODe ... / :DVM:VALue?
```

DVM is a separate measurement path with its own mode; its value is not
`:MEASure:MEAN?` or a cursor reading. Record the mode.

## Go-NoGo and templates (pp. 238-243)

```text
:GONogo:EXECute ... / :GONogo:CLEar ...
:GONogo:FUNCtion ... / :GONogo:NGCount? / :GONogo:NGDefine ...
:GONogo:SOURce ... / :GONogo:VIOLation?
:TEMPlate:MODe ... / :TEMPlate:MAXimum ... / :TEMPlate:MINimum ...
:TEMPlate:TOLerance ...
```

Go-NoGo tests a signal against a template. A pass/fail result depends on the
template and tolerance, which must be stored with the result. Template saves
write files or memory and follow the same no-overwrite rule.

## Data logging (pp. 244-246)

```text
:DATALOG:STATE {ON|OFF|?} / :DATALOG:SOURce ... / :DATALOG:SAVe ...
:DATALOG:INTerval <NRf> / :DATALOG:DURation <NRf>
```

Datalog writes periodic readings to storage. Duration × interval bounds the
file size; confirm storage and filename first. The Skill never starts a log.

## Remote disk (pp. 247-249)

```text
:REMOTEDisk:IPADDress ... / :REMOTEDisk:PATHName ...
:REMOTEDisk:USERName ... / :REMOTEDisk:PASSWord ...
:REMOTEDisk:MOUNT ... / :REMOTEDisk:AUTOMount ...
```

Remote disk mounts a network share on the instrument. Credentials travel in
clear text; never embed secrets in shared scripts or logs. A mount does not
imply SCPI file readback.

## Conditional support

| Feature | Condition |
|---|---|
| Bus decode / bus trigger | Optional license; confirm on the instrument |
| Digital filter | Digital Filter app installed |
| CH3/CH4 features | 4-channel model |
| EXT trigger | 2-channel model |
| Ethernet | 4-channel model; socket server enabled |
| Go-NoGo / templates | Firmware/menu support; confirm before use |
