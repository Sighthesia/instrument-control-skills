# Command reference

> **Manual note.** The local evidence copy is `ref/GDS-2000A_Programming_Manual_v1.4.extracted.md`, a converted text file. It has no body page breaks, so body page numbers are unavailable. Every page number below comes from the manual's own table of contents or from the page markers in its **List of Commands in Functional Order** (pp. 24-34). Do not infer a body page from the converted text.

## Coverage and counting

- Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
- Authority for the form list: the manual's **List of Commands in Functional Order**, pp. 24-34. The list is the denominator; a grep of syntax lines is not.
- **Rows: 339. Distinct normalized forms: 339.** No form is duplicated after case folding and dropping the query `?`.
- The comparison helper `artifacts/gds-series-diff/compare_commands.py` reports 338 because it does not join one wrapped line: `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:DIRection ... 186`. Joining that continuation yields 339. The extra row is the wrapped line, not a new command.
- **Coverage: 339/339 list forms (100%).** Each row has a page and a status. The 339 rows below are the complete list; Appendix A adds 19 forms that the local copy's list omits, and Appendix B records 2 referenced-only spellings. Those appendices do not change the denominator.
- **Status: 51 hardware-verified, 288 documented.** `hardware-verified` is used only when a real reply or a set/readback pair was captured. A failed or empty query is `documented`, with the observed error in the note.
- Method and date: parsed the local converted list on 2026-11-26, joined wrapped lines, normalized case and optional `?`, and triaged residuals by hand. Re-do the count if the manual revision changes.
- Evidence: every `hardware-verified` note names a raw file or capture record under `artifacts/hw-verify/gds2000a-20261126/` (git-ignored). `raw/` is the final 2026-11-26 run; `explore-*.json` are the earlier read-only exploration records from the same session. No synthetic fixture is cited as hardware evidence.

## Sendable spelling rules

- The list often omits the query `?`; the body syntax and this Skill send the `?` form. Example: the list prints `:SYSTem:ERRor`, the body documents `:SYSTem:ERRor?`.
- Channel and slot families require a numeric suffix even when the list prints none. The verified unit requires `:CHANnel1:SCALe?`, `:ACQuire1:MEMory?`, `:ACQuire1:STATe?`, `:MEASure:SOURce1?`, and `:MEASUrement:MEAS1:VALue?`; the bare spellings returned `-113` or `-131`.
- Individual `:MEASure:*?` commands do **not** take a channel parameter. Select the source first with `:MEASure:SOURce1 CH1`; `:MEASure:PK2PK? CH1` returned `-108 Parameter not allowed`.
- `:ACQuire:MEMory?` and `:ACQuire:LMEMory?` are also suffix families: `:ACQuire1:MEMory?`. The bare `:ACQuire:MEMory?` returned an empty line, and `:ACQuire:MEMory? CH1` returned `-108`.
- `:FUNCtion:*` requires a module suffix, for example `:FUNCtion1:MODe?`; the list prints no suffix. The verified unit has no DS2-FGN option, so the suffixed query returned `-240`.
- `:TRIGger:*` and `:TIMebase:*` are global and take no channel suffix on this series.
- Send one command per write with LF (`\n`), then read before the next write. Do not concatenate commands.

## Manual defects and local-copy limits

1. **Query `?` omitted in the list.** Most rows print a set form even when the body documents a query. The index keeps the printed row and notes the sent query form.
2. **Instance suffix omitted.** The list prints `:ACQuire:MEMory?`, `:ACQuire:STATe?`, `:MEASure:SOURce`, and `:MEASUrement:MEAS:*` without the channel/slot number; the body examples use `:ACQuire1:`, `:MEASure:SOURce1`, and `:MEASUrement:MEAS1:`. Hardware agrees with the examples, not the list.
3. **Go_NoGo section missing from the list.** The body has Go_NoGo and Template commands on pp. 226-231, but the local list jumps from Function Generator (p. 225) to Data Logging (p. 232). This is an extraction/table-loss gap; whether the printed list contains those rows is `UNVERIFIED`. They are in Appendix A and are not counted in 339.
4. **Body-only `:DISPlay:OUTPut?`** is documented at p. 74 but absent from the list. It returns a 16-bit RGB run-length image, not a file. Appendix A records it.
5. **Body-only `:LISTer:DATA?`** is documented in the Bus Decode section (p. 167) but absent from the list. Appendix A records it.
6. **Function Generator suffix.** The list prints `:FUNCtion:MODe`; the body examples use `:FUNCtion1:`. On V1.18 the bare form returned `-131 Invalid suffix`, the suffixed form `-240 Hardware error` because the option is absent.
7. **Trigger-state spelling.** The manual returns `*ARMED`, `*AUTO`, `*READY`, `*SAVE`, `*TRIGGER`; the GDS-2104A returned `ARMED`, `AUTO`, `SAVE`, `READY` without the leading `*`.
8. **Measurement sentinel.** The manual documents `Chan Off`; the GDS-2104A returned `Ch Off`. `:MEASUrement:MEAS1:VALue?` with measurement state `0` returned `9.9E+37`, a no-result token the manual does not document. Both are treated as `INCOMPLETE`, never as a number.
9. **Waveform header separators.** The `:ACQuire1:MEMory?` example uses `;`; the `:ACQuire1:LMEMory?` example uses `,`. The parser accepts either; the captured memory header used `;`.
10. **Referenced-only logic-clock edge.** `:TRIGger:LOGic:INPut:CLOCK:EDGe` and `:SEARCH:TRIGger:LOGic:INPut:CLOCK:EDGe` are named as related commands but have no syntax heading or list row; Appendix B marks them `UNVERIFIED`.
11. **Double LF.** `:TRIGger:FREQuency?` returned `2.000E+00` followed by two LFs. The parser keeps the second LF as framing evidence; it is not a second response.
12. **`:TIMebase:EXPand?` contradiction.** The manual says it is available for firmware V1.18 or above and requires the Horizontal Expansion app; the V1.18 unit returned `-221 Settings conflict`. The command remains documented but not verified on this unit.

## How to read a row

- `documented`: the manual documents the form; this Skill has not sent it successfully. A note may record an observed error or a spelling caveat.
- `hardware-verified`: a real reply or set/readback pair was captured on the GDS-2104A (V1.18, serial GEN182193, USB CDC-ACM, 2026-11-26).
- A section marked **not implemented** is deliberate: the commands remain documented, but no workflow in this Skill sends them.

## List of Commands, in functional order

### Common

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `*IDN?` | 37 | hardware-verified | `*IDN?` -> `GW,GDS-2104A,GEN182193,V1.18`; raw/001-query-IDN.bin |
| `*LRN?` | 37 | documented | not sent; large settings dump |
| `*SAV` | 39 | documented | forbidden by this Skill: writes Set1-Set20 |
| `*RCL` | 40 | documented | forbidden by this Skill: changes panel state |
| `*RST` | 40 | documented | forbidden by this Skill: resets panel state |
| `*CLS` | 40 | documented | not sent; clears the error queue |

### Acquisition

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:ACQuire:AVERage` | 41 | documented | documented only; requires average mode |
| `:ACQuire:MODe` | 41 | hardware-verified | `:ACQuire:MODe?` -> `SAMPLE`; raw/011, raw/095 |
| `:ACQuire:MEMory?` | 42 | documented | bare form returned an empty line; send as `:ACQuire<n>:MEMory?`; fixed spelling verified in Appendix C |
| `:ACQuire:LMEMory?` | 43 | documented | bare form not sent; send as `:ACQuire<n>:LMEMory?`; 1,000,000-point capture exists in local evidence but is not shipped |
| `:ACQuire:STATe?` | 43 | documented | bare form returned `-113 Undefined header`; send as `:ACQuire<n>:STATe?`; raw/036 |
| `:ACQuire:INTERpolation` | 44 | documented | documented only; no final-run capture |
| `:ACQuire:FILTer` | 44 | documented | documented only; no final-run capture |
| `:ACQuire:RECOrdlength` | 44 | hardware-verified | `:ACQuire:RECOrdlength?` -> `AUTO`; raw/012, raw/096 |
| `:HEADer` | 45 | hardware-verified | `:HEADer?` -> `ON`; raw/013, raw/097 |

### Autoscale

**Not implemented:** Autoscale is not implemented; `:AUTOSet` changes acquisition and trigger state.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:AUTOSet` | 46 | documented |  |
| `:AUTORSET:MODe` | 46 | documented |  |

### Vertical

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:CHANnel:BWLimit` | 47 | hardware-verified | sent as `:CHANnel1:BWLimit?` -> `FULL`; explore-queries.json |
| `:CHANnel:COUPling` | 48 | hardware-verified | sent as `:CHANnel1:COUPling?`; set AC, read back, restored DC; raw/016, raw/047, raw/049 |
| `:CHANnel:DESKew` | 48 | hardware-verified | sent as `:CHANnel1:DESKew?` -> `0.000e+00`; explore-state.json |
| `:CHANnel:DISPlay` | 48 | hardware-verified | sent as `:CHANnel1:DISPlay?` -> `ON`; raw/014, raw/098 |
| `:CHANnel:EXPand` | 49 | hardware-verified | sent as `:CHANnel1:EXPand?` -> `GND`; explore-state.json |
| `:CHANnel:IMPedance?` | 49 | hardware-verified | sent as `:CHANnel1:IMPedance?` -> `1.000000E+06`; explore-queries.json |
| `:CHANnel:INVert` | 50 | hardware-verified | sent as `:CHANnel1:INVert?` -> `OFF`; explore-state.json |
| `:CHANnel:POSition` | 50 | hardware-verified | sent as `:CHANnel1:POSition?` -> `-2.360E+00`; explore-state.json |
| `:CHANnel:PROBe:RATio` | 51 | hardware-verified | sent as `:CHANnel1:PROBe:RATio?` -> `1.000000e+00`; explore-queries.json |
| `:CHANnel:PROBe:TYPe` | 51 | hardware-verified | sent as `:CHANnel1:PROBe:TYPe?` -> `VOLTAGE`; explore-queries.json |
| `:CHANnel:SCALe` | 51 | hardware-verified | sent as `:CHANnel1:SCALe?`; set 2.0 V/div, read back, restored 1.0 V/div; raw/015, raw/042, raw/044 |

### Math

**Not implemented:** Math/FFT is not implemented beyond read-only `:MATH:TYPe?` and `:MATH:DISP?` queries.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:MATH:DISP` | 53 | hardware-verified | `:MATH:DISP?` -> `OFF`; raw/072 |
| `:MATH:TYPe` | 54 | hardware-verified | `:MATH:TYPe?` -> `DUAL`; raw/071 |
| `:MATH:DUAL:SOURce` | 54 | documented |  |
| `:MATH:DUAL:OPERator` | 54 | documented |  |
| `:MATH:DUAL:POSition` | 55 | documented |  |
| `:MATH:DUAL:SCALe` | 55 | documented |  |
| `:MATH:FFT:SOURce` | 56 | documented |  |
| `:MATH:FFT:MAG` | 56 | documented |  |
| `:MATH:FFT:WINDow` | 56 | documented |  |
| `:MATH:FFT:POSition` | 57 | documented |  |
| `:MATH:FFT:SCALe` | 57 | documented |  |
| `:MATH:FFT:HORizontal:SCALe` | 58 | documented |  |
| `:MATH:ADVanced:OPERator` | 58 | documented |  |
| `:MATH:ADVanced:SOURce` | 58 | documented |  |
| `:MATH:ADVanced:EDIT:SOURce` | 59 | documented |  |
| `:MATH:ADVanced:EDIT:OPERator` | 59 | documented |  |
| `:MATH:ADVanced:POSition` | 60 | documented |  |
| `:MATH:ADVanced:SCALe` | 60 | documented |  |

### Cursor

**Not implemented:** Cursor commands are not implemented.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:CURSor:MODe` | 62 | documented |  |
| `:CURSor:SOURce` | 62 | documented |  |
| `:CURSor:HUNI` | 63 | documented |  |
| `:CURSor:HUSE` | 63 | documented |  |
| `:CURSor:VUNI` | 64 | documented |  |
| `:CURSor:VUSE` | 64 | documented |  |
| `:CURSor:DDT` | 64 | documented |  |
| `:CURSor:H1Position` | 65 | documented |  |
| `:CURSor:H2Position` | 65 | documented |  |
| `:CURSor:HDELta` | 65 | documented |  |
| `:CURSor:V1Position` | 66 | documented |  |
| `:CURSor:V2Position` | 66 | documented |  |
| `:CURSor:VDELta` | 66 | documented |  |
| `:CURSor:XY:RECTangular:X:POSition` | 67 | documented |  |
| `:CURSor:XY:RECTangular:X:DELta` | 67 | documented |  |
| `:CURSor:XY:RECTangular:Y:POSition` | 68 | documented |  |
| `:CURSor:XY:RECTangular:Y:DELta` | 68 | documented |  |
| `:CURSor:XY:POLar:RADIUS:POSition` | 68 | documented |  |
| `:CURSor:XY:POLar:RADIUS:DELta` | 69 | documented |  |
| `:CURSor:XY:POLar:THETA:POSition` | 69 | documented |  |
| `:CURSor:XY:POLar:THETA:DELta` | 69 | documented |  |
| `:CURSor:XY:PRODuct:POSition` | 70 | documented |  |
| `:CURSor:XY:PRODuct:DELta` | 70 | documented |  |
| `:CURSor:XY:RATio:POSition` | 70 | documented |  |
| `:CURSor:XY:RATio:DELta` | 71 | documented |  |

### Display

**Not implemented:** Display configuration is not implemented; `:DISPlay:OUTPut?` is body-only (Appendix A).

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:DISPlay:INTensity:WAVEform` | 71 | documented |  |
| `:DISPlay:INTensity:GRATicule` | 72 | documented |  |
| `:DISPlay:PERSistence` | 72 | documented |  |
| `:DISPlay:GRATicule` | 72 | documented |  |
| `:DISPlay:WAVEform` | 74 | documented |  |

### Hardcopy

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:HARDcopy:START` | 75 | documented |  |
| `:HARDcopy:MODe` | 75 | hardware-verified | `:HARDcopy:MODe?` -> `SAVE`; raw/066 |
| `:HARDcopy:PRINTINKSaver` | 75 | hardware-verified | `:HARDcopy:PRINTINKSaver?` -> `ON`; raw/069 |
| `:HARDcopy:SAVEINKSaver` | 76 | hardware-verified | `:HARDcopy:SAVEINKSaver?` -> `OFF`; raw/070 |
| `:HARDcopy:SAVEFORMat` | 76 | hardware-verified | `:HARDcopy:SAVEFORMat?` -> `BMP`; raw/067 |
| `:HARDcopy:ASSIGN` | 77 | hardware-verified | `:HARDcopy:ASSIGN?` -> `IMAGE`; raw/068 |

### Measure

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:MEASure:GATing` | 79 | hardware-verified | `:MEASure:GATing?` -> `SCREEN`; explore-state.json |
| `:MEASure:SOURce` | 79 | documented | bare form returned `-131 Invalid suffix`; send as `:MEASure:SOURce<n>?`; fixed spelling verified in Appendix C |
| `:MEASure:METHod` | 80 | hardware-verified | `:MEASure:METHod?` -> `AUTO`; explore-state.json |
| `:MEASure:FALL` | 80 | documented |  |
| `:MEASure:FOVShoot` | 81 | documented |  |
| `:MEASure:FPReshoot` | 81 | documented |  |
| `:MEASure:FREQuency` | 82 | documented |  |
| `:MEASure:NWIDth` | 82 | documented |  |
| `:MEASure:PDUTy` | 83 | documented |  |
| `:MEASure:PERiod` | 83 | documented |  |
| `:MEASure:PWIDth` | 84 | documented |  |
| `:MEASure:RISe` | 84 | documented |  |
| `:MEASure:ROVShoot` | 85 | documented |  |
| `:MEASure:RPReshoot` | 85 | documented |  |
| `:MEASure:PPULSE` | 86 | documented |  |
| `:MEASure:NPULSE` | 87 | documented |  |
| `:MEASure:PEDGE` | 87 | documented |  |
| `:MEASure:NEDGE` | 88 | documented |  |
| `:MEASure:AMPlitude` | 88 | documented |  |
| `:MEASure:MEAN` | 89 | documented |  |
| `:MEASure:CMEan` | 89 | documented |  |
| `:MEASure:HIGH` | 90 | documented |  |
| `:MEASure:LOW` | 91 | documented |  |
| `:MEASure:MAX` | 91 | documented |  |
| `:MEASure:MIN` | 92 | documented |  |
| `:MEASure:PK2PK` | 92 | hardware-verified | `:MEASure:PK2PK?` with source CH1 -> `8.000E-02`; raw/021 |
| `:MEASure:RMS` | 93 | documented |  |
| `:MEASure:AREa` | 93 | documented |  |
| `:MEASure:CARea` | 94 | documented |  |
| `:MEASure:FRRDelay` | 95 | documented |  |
| `:MEASure:FRFDelay` | 95 | documented |  |
| `:MEASure:FFRDelay` | 96 | documented |  |
| `:MEASure:FFFDelay` | 96 | documented |  |
| `:MEASure:LRRDelay` | 97 | documented |  |
| `:MEASure:LRFDelay` | 98 | documented |  |
| `:MEASure:LFRDelay` | 98 | documented |  |
| `:MEASure:LFFDelay` | 99 | documented |  |
| `:MEASure:PHAse` | 99 | documented |  |

### Measurement

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:MEASUrement:MEAS:SOURCE` | 101 | documented | list omits slot number; send as `:MEASUrement:MEAS<n>:SOURce<n>?`; `MEAS1` readback is in the earlier explore records |
| `:MEASUrement:MEAS:TYPe` | 102 | documented | list omits slot number; send as `:MEASUrement:MEAS<n>:TYPe?`; `MEAS1` readback is in the earlier explore records |
| `:MEASUrement:MEAS:STATE` | 102 | documented | list omits slot number; send as `:MEASUrement:MEAS<n>:STATE?`; `MEAS1` readback is in the earlier explore records |
| `:MEASUrement:MEAS:VALue` | 103 | documented | list omits slot number; send as `:MEASUrement:MEAS<n>:VALue?`; state 0 returned `9.9E+37`, treated as INCOMPLETE |
| `:MEASUrement:MEAS:MAXimum` | 104 | documented |  |
| `:MEASUrement:MEAS:MEAN` | 105 | documented |  |
| `:MEASUrement:MEAS:MINImum` | 105 | documented |  |
| `:MEASUrement:MEAS:STDdev` | 106 | documented |  |
| `:MEASUrement:STATIstics:MODe` | 106 | documented |  |
| `:MEASUrement:STATIstics:WEIghting` | 107 | documented |  |
| `:MEASUrement:STATIstics` | 107 | documented |  |

### Reference

**Not implemented:** Reference waveform commands are not implemented.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:REF:DISPlay` | 108 | documented |  |
| `:REF:TIMebase:POSition` | 108 | documented |  |
| `:REF:TIMebase:SCALe` | 109 | documented |  |
| `:REF:OFFSet` | 109 | documented |  |
| `:REF:SCALe` | 110 | documented |  |

### Run

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:RUN` | 111 | hardware-verified | write only; `:STOP` -> state `SAVE`, then `:RUN` -> state `AUTO`; raw/030-raw/033 |

### Stop

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:STOP` | 111 | hardware-verified | write only; led to state `SAVE`; also used before waveform download; raw/027, raw/031 |

### Single

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:SINGle` | 111 | hardware-verified | write only; led to `READY`/acquire state 0; restored with STOP then RUN; raw/034-raw/039 |

### Force

**Not implemented:** `:FORCe` is not implemented; forcing hides a wrong trigger setup.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:FORCe` | 112 | documented |  |

### Timebase

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:TIMebase:EXPand` | 113 | documented | query returned no bytes and `-221 Settings conflict` on V1.18 (app not installed); raw/078 |
| `:TIMebase:POSition` | 113 | hardware-verified | `:TIMebase:POSition?` -> `0.000E+00`; explore-state.json |
| `:TIMebase:SCALe` | 114 | hardware-verified | set 1.000000e-03, read back, restored 5.000000e-04; raw/009, raw/052, raw/054 |
| `:TIMebase:MODe` | 114 | hardware-verified | `:TIMebase:MODe?` -> `MAIN`; raw/010, raw/094 |
| `:TIMebase:WINDow:POSition` | 114 | documented |  |
| `:TIMebase:WINDow:SCALe` | 115 | documented |  |

### Trigger

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:TRIGger:FREQuency` | 117 | hardware-verified | `:TRIGger:FREQuency?` -> `2.000E+00` plus a second LF; fixture hardware/trigger-frequency-double-lf.txt |
| `:TRIGger:TYPe` | 118 | hardware-verified | `:TRIGger:TYPe?` -> `EDGE`; raw/006, raw/090 |
| `:TRIGger:SOURce` | 118 | hardware-verified | `:TRIGger:SOURce?` -> `CH1`; raw/007, raw/091 |
| `:TRIGger:COUPle` | 119 | hardware-verified | `:TRIGger:COUPle?` -> `DC`; explore-state.json |
| `:TRIGger:NREJ` | 119 | hardware-verified | `:TRIGger:NREJ?` -> `OFF`; explore-state.json |
| `:TRIGger:REJect` | 119 | hardware-verified | `:TRIGger:REJect?` -> `OFF`; explore-state.json |
| `:TRIGger:MODe` | 120 | hardware-verified | `:TRIGger:MODe?` -> `AUTO`; raw/005, raw/089 |
| `:TRIGger:HOLDoff` | 120 | hardware-verified | `:TRIGger:HOLDoff?` -> `1.000e-08`; explore-state.json |
| `:TRIGger:LEVel` | 120 | hardware-verified | set 2.600E+00, read back, restored 2.520E+00; raw/008, raw/057, raw/059 |
| `:TRIGger:HLEVel` | 121 | documented |  |
| `:TRIGger:LLEVel` | 122 | documented |  |
| `:TRIGger:EDGe:SLOP` | 122 | hardware-verified | `:TRIGger:EDGe:SLOP?` -> `RISE`; explore-state.json |
| `:TRIGger:DELay:SLOP` | 123 | documented |  |
| `:TRIGger:DELay:TYPe` | 123 | documented |  |
| `:TRIGger:DELay:TIMe` | 123 | documented |  |
| `:TRIGger:DELay:EVENt` | 124 | documented |  |
| `:TRIGger:DELay:LEVel` | 124 | documented |  |
| `:TRIGger:PULSEWidth:POLarity` | 124 | documented |  |
| `:TRIGger:RUNT:POLarity` | 125 | documented |  |
| `:TRIGger:RUNT:WHEn` | 125 | documented |  |
| `:TRIGger:RUNT:TIMe` | 126 | documented |  |
| `:TRIGger:RISEFall:SLOP` | 126 | documented |  |
| `:TRIGger:RISEFall:WHEn` | 127 | documented |  |
| `:TRIGger:RISEFall:TIMe` | 127 | documented |  |
| `:TRIGger:VIDeo:TYPe` | 128 | documented |  |
| `:TRIGger:VIDeo:FIELd` | 128 | documented |  |
| `:TRIGger:VIDeo:LINe` | 129 | documented |  |
| `:TRIGger:VIDeo:POLarity` | 129 | documented |  |
| `:TRIGger:PULSe:WHEn` | 129 | documented |  |
| `:TRIGger:PULSe:TIMe` | 130 | documented |  |
| `:TRIGger:ALTernate` | 131 | documented |  |
| `:TRIGger:STATe` | 131 | hardware-verified | `:TRIGger:STATe?` -> `AUTO`/`ARMED`/`SAVE`/`READY` (no leading `*`); raw/004, raw/031, raw/035, raw/039 |
| `:TRIGger:EXTERnal:PROBe:TYPe` | 132 | documented |  |
| `:TRIGger:EXTERnal:PROBe:RATio` | 132 | documented |  |
| `:TRIGger:BUS:TYPe` | 132 | documented |  |
| `:TRIGger:BUS:B1:I2C:CONDition` | 133 | documented |  |
| `:TRIGger:BUS:B1:I2C:ADDRess:MODe` | 134 | documented |  |
| `:TRIGger:BUS:B1:I2C:ADDRess:TYPe` | 134 | documented |  |
| `:TRIGger:BUS:B1:I2C:ADDRess:VALue` | 135 | documented |  |
| `:TRIGger:BUS:B1:I2C:ADDRess:DIRection` | 135 | documented |  |
| `:TRIGger:BUS:B1:I2C:DATa:SIZe` | 136 | documented |  |
| `:TRIGger:BUS:B1:I2C:DATa:VALue` | 136 | documented |  |
| `:TRIGger:BUS:B1:UART:CONDition` | 137 | documented |  |
| `:TRIGger:BUS:B1:UART:RX:DATa:SIZe` | 138 | documented |  |
| `:TRIGger:BUS:B1:UART:RX:DATa:VALue` | 138 | documented |  |
| `:TRIGger:BUS:B1:UART:TX:DATa:SIZe` | 139 | documented |  |
| `:TRIGger:BUS:B1:UART:TX:DATa:VALue` | 139 | documented |  |
| `:TRIGger:BUS:B1:SPI:CONDition` | 140 | documented |  |
| `:TRIGger:BUS:B1:SPI:DATa:SIZe` | 141 | documented |  |
| `:TRIGger:BUS:B1:SPI:DATa:MISO:VALue` | 141 | documented |  |
| `:TRIGger:BUS:B1:SPI:DATa:MOSI:VALue` | 142 | documented |  |
| `:TRIGger:BUS:B1:PARallel:VALue` | 143 | documented |  |
| `:TRIGger:LOGic:FUNCtion` | 143 | documented |  |
| `:TRIGger:LOGic:INPut:CLOCK:SOURce` | 144 | documented |  |
| `:TRIGger:LOGic:PATtern` | 144 | documented |  |
| `:TRIGger:LOGic:PATtern:INPut:D` | 145 | documented |  |
| `:TRIGger:LOGic:PATtern:DELTatime` | 145 | documented |  |
| `:TRIGger:LOGic:PATtern:WHEn` | 146 | documented |  |
| `:TRIGger:TIMEOut:WHEn` | 147 | documented |  |
| `:TRIGger:TIMEOut:TIMER` | 147 | documented |  |

### System

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:SYSTem:LOCK` | 148 | hardware-verified | `:SYSTem:LOCK?` -> `OFF`; read-only, explored before the final run; explore-state.json |
| `:SYSTem:ERRor` | 148 | hardware-verified | `:SYSTem:ERRor?` -> `+0, "No error."`; non-zero errors preserved in raw/084, raw/085, raw/086, raw/087 |

### Save/Recall

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:RECAll:SETUp` | 149 | documented |  |
| `:RECAll:WAVEform` | 150 | documented |  |
| `:SAVe:IMAGe` | 150 | documented |  |
| `:SAVe:IMAGe:FILEFormat` | 151 | hardware-verified | `:SAVe:IMAGe:FILEFormat?` -> `BMP`; raw/064 |
| `:SAVe:IMAGe:INKSaver` | 151 | hardware-verified | `:SAVe:IMAGe:INKSaver?` -> `OFF`; raw/065 |
| `:SAVe:SETUp` | 151 | documented |  |
| `:SAVe:WAVEform` | 152 | documented |  |
| `:SAVe:WAVEform:FILEFormat` | 153 | documented |  |

### Ethernet

**Not implemented:** Ethernet is not verified; the DS2-LAN option is required.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:ETHERnet:DHCP` | 155 | documented |  |

### Time

**Not implemented:** `:DATe` is not implemented; it changes the instrument clock.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:DATe` | 156 | documented |  |

### Bus Decode

**Not implemented:** Bus decode is not implemented; the DS2-8LA/16LA option is not present on the verified unit (query `-240`).

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:BUS1` | 157 | documented | documented only; DS2-8LA/16LA logic option |
| `:BUS1:STATE` | 158 | documented | query returned no bytes and `-240 Hardware error`; logic option not installed; raw/082 |
| `:BUS1:TYPe` | 158 | documented | documented only; logic option not installed |
| `:BUS1:I2C:ADDRess:RWINClude` | 159 | documented |  |
| `:BUS1:I2C:SCLK:SOURce` | 159 | documented |  |
| `:BUS1:I2C:SDA:SOURce` | 159 | documented |  |
| `:BUS1:UART:BITRate` | 160 | documented |  |
| `:BUS1:UART:PARIty` | 161 | documented |  |
| `:BUS1:UART:PACKEt` | 161 | documented |  |
| `:BUS1:UART:EOFPAcket` | 161 | documented |  |
| `:BUS1:UART:TX:SOURce` | 162 | documented |  |
| `:BUS1:UART:RX:SOURce` | 162 | documented |  |
| `:BUS1:SPI:SCLK:POLARity` | 163 | documented |  |
| `:BUS1:SPI:SS:POLARity` | 163 | documented |  |
| `:BUS1:SPI:WORDSize` | 163 | documented |  |
| `:BUS1:SPI:BITORder` | 164 | documented |  |
| `:BUS1:SPI:SCLK:SOURce` | 164 | documented |  |
| `:BUS1:SPI:SS:SOURce` | 164 | documented |  |
| `:BUS1:SPI:MOSI:SOURce` | 165 | documented |  |
| `:BUS1:SPI:MISO:SOURce` | 165 | documented |  |
| `:BUS1:PARallel:BIT:SOURce` | 165 | documented |  |
| `:BUS1:PARallel:CLOCK:EDGE` | 166 | documented |  |
| `:BUS1:PARallel:CLOCK:SOURce` | 166 | documented |  |
| `:BUS1:PARallel:WIDth` | 167 | documented |  |
| `:BUS1:DISplay:FORMAt` | 167 | documented |  |

### Mark

**Not implemented:** Mark commands are not implemented.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:MARK` | 168 | documented |  |
| `:MARK:CREATE` | 168 | documented |  |
| `:MARK:DELEte` | 169 | documented |  |

### Search

**Not implemented:** Search configuration/execution is not implemented; only `:SEARCH:STATE?` and `:SEARCH:TOTAL?` were read.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:SEARCH:COPY` | 171 | documented |  |
| `:SEARCH:STATE` | 171 | hardware-verified | `:SEARCH:STATE?` -> `OFF`; raw/075 |
| `:SEARCH:TOTAL` | 172 | hardware-verified | `:SEARCH:TOTAL?` -> `0`; raw/076 |
| `:SEARCH:TRIGger:TYPe` | 172 | documented |  |
| `:SEARCH:TRIGger:SOURce` | 172 | documented |  |
| `:SEARCH:TRIGger:EDGE:SLOP` | 173 | documented |  |
| `:SEARCH:TRIGger:LEVel` | 173 | documented |  |
| `:SEARCH:TRIGger:HLEVel` | 174 | documented |  |
| `:SEARCH:TRIGger:LLEVel` | 174 | documented |  |
| `:SEARCH:TRIGger:PULSEWidth:POLarity` | 175 | documented |  |
| `:SEARCH:TRIGger:RUNT:POLarity` | 175 | documented |  |
| `:SEARCH:TRIGger:RISEFall:SLOP` | 176 | documented |  |
| `:SEARCH:TRIGger:PULSe:WHEn` | 176 | documented |  |
| `:SEARCH:TRIGger:PULSe:TIMe` | 177 | documented |  |
| `:SEARCH:TRIGger:RUNT:WHEn` | 177 | documented |  |
| `:SEARCH:TRIGger:RUNT:TIMe` | 178 | documented |  |
| `:SEARCH:TRIGger:RISEFall:WHEn` | 178 | documented |  |
| `:SEARCH:TRIGger:RISEFall:TIMe` | 179 | documented |  |
| `:SEARCH:TRIGger:LOGic:FUNCtion` | 179 | documented |  |
| `:SEARCH:TRIGger:LOGic:INPut:CLOCK:SOURce` | 180 | documented |  |
| `:SEARCH:TRIGger:LOGic:PATtern` | 180 | documented |  |
| `:SEARCH:TRIGger:LOGic:PATtern:INPut:D` | 181 | documented |  |
| `:SEARCH:TRIGger:LOGic:PATtern:DELTatime` | 181 | documented |  |
| `:SEARCH:TRIGger:LOGic:PATtern:WHEn` | 182 | documented |  |
| `:SEARCH:TRIGger:BUS:TYPe` | 183 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:CONDition` | 183 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:MODe` | 184 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:TYPe` | 185 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:VALue` | 185 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:DIRection` | 186 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:DATa:SIZe` | 187 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:I2C:DATa:VALue` | 187 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:UART:CONDition` | 188 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:SIZe` | 189 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:VALue` | 189 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:SIZe` | 190 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:VALue` | 191 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:SPI:CONDition` | 191 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:SPI:DATa:SIZe` | 192 | documented |  |
| `:SEARCH:TRIGger:BUS:B1:PARallel:VALue` | 194 | documented |  |

### Digital

**Not implemented:** Digital/logic channels are not implemented; the logic probe option is not present.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:D:DISPlay` | 196 | documented |  |
| `:D:POSition` | 196 | documented |  |
| `:DISPlay:DIGital:HEIght` | 197 | documented |  |
| `:DIGital:GROUP:THREshold` | 197 | documented |  |
| `:DIGital:ANAlog:A:DISPlay` | 198 | documented |  |
| `:DIGital:ANAlog:A:RATio` | 199 | documented |  |
| `:D:MEMory` | 199 | documented |  |
| `:D:LMEMory` | 200 | documented |  |
| `:DIGital:MEMory` | 201 | documented |  |
| `:DIGital:LMEMory` | 201 | documented |  |

### Label

**Not implemented:** Label commands are not implemented.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:CHANnel:LABel` | 203 | documented |  |
| `:CHANnel:LABel:DISPlay` | 204 | documented |  |
| `:REF:LABel` | 205 | documented |  |
| `:REF:LABel:DISPlay` | 205 | documented |  |
| `:BUS1:LABel` | 206 | documented |  |
| `:BUS1:LABel:DISPlay` | 207 | documented |  |
| `:D:LABel` | 207 | documented |  |
| `:D:LABel:DISPlay` | 208 | documented |  |
| `:DIGital:ANAlog:A:LABel` | 209 | documented |  |
| `:DIGital:ANAlog:A:LABel:DISPlay` | 210 | documented |  |
| `:SET:LABel` | 210 | documented |  |

### Utility

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:BUZZER` | 212 | hardware-verified | `:BUZZER?` -> `OFF`; set `:BUZZER OFF` read back `OFF`; raw/002, raw/060, raw/062 |

### Segment

**Not implemented:** Segment acquisition/measurement is not implemented; only `:SEGMents:STATE?` and `:SEGMents:TOTalnum?` were read.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:SEGMents:STATE` | 213 | hardware-verified | `:SEGMents:STATE?` -> `OFF`; raw/073 |
| `:SEGMents:CURRent` | 214 | documented |  |
| `:SEGMents:TOTalnum` | 214 | hardware-verified | `:SEGMents:TOTalnum?` -> `1.000E+01`; raw/074 |
| `:SEGMents:TIMe` | 214 | documented |  |
| `:SEGMents:DISPALL` | 215 | documented |  |
| `:SEGMents:MEASure:MODe` | 215 | documented |  |
| `:SEGMents:MEASure:PLOT:SOURce` | 216 | documented |  |
| `:SEGMents:MEASure:PLOT:DIVide` | 216 | documented |  |
| `:SEGMents:MEASure:PLOT:SELect` | 217 | documented |  |
| `:SEGMents:MEASure:PLOT:RESults` | 217 | documented |  |
| `:SEGMents:MEASure:TABle:SOURce` | 217 | documented |  |
| `:SEGMents:MEASure:TABle:SELect` | 218 | documented |  |
| `:SEGMents:MEASure:TABle:LIST` | 218 | documented |  |
| `:SEGMents:MEASure:TABle:SAVe` | 219 | documented |  |
| `:SEGMents:SAVe` | 219 | documented |  |
| `:SEGMents:SAVe:SOURce` | 219 | documented |  |
| `:SEGMents:SAVe:SELect:STARt` | 220 | documented |  |
| `:SEGMents:SAVe:SELect:END` | 220 | documented |  |

### DVM

**Not implemented:** DVM is not implemented; the optional DVM software is not active (query `-221`).

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:DVM:STATE` | 221 | documented | query returned no bytes and `-221 Settings conflict`; optional DVM software not active; raw/079 |
| `:DVM:SOURce` | 221 | documented | documented only; DVM option not active |
| `:DVM:MODe` | 222 | documented | documented only; DVM option not active |

### Function Generator

**Not implemented:** Function generator is not implemented; the DS2-FGN option is not present (query `-240`). Function commands require a module suffix such as `:FUNCtion1:`.

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:FUNCtion:MODe` | 223 | documented | bare form returned `-131 Invalid suffix`; DS2-FGN option query `:FUNCtion1:MODe?` returned `-240 Hardware error`; raw/080 |
| `:FUNCtion:FREQuency` | 223 | documented | documented only; DS2-FGN option not installed |
| `:FUNCtion:AMPlitude` | 224 | documented | documented only; DS2-FGN option not installed |
| `:FUNCtion:OFFSet` | 224 | documented | documented only; DS2-FGN option not installed |
| `:FUNCtion:DUTYcycle` | 225 | documented | documented only; DS2-FGN option not installed |

### Data Logging

**Not implemented:** Data logging is not implemented; the Datalog App/DS2-LAN is not active (query `-221`).

| Form (as printed) | Page | Status | Note / sent as |
|---|---:|---|---|
| `:DATALOG:STATE` | 232 | documented | query returned no bytes and `-221 Settings conflict`; Datalog App/DS2-LAN not active; raw/081 |
| `:DATALOG:SOURce` | 232 | documented | documented only; Datalog App not active |
| `:DATALOG:SAVe` | 233 | documented | documented only; writes files, not sent |
| `:DATALOG:INTerval` | 233 | documented | documented only; Datalog App not active |
| `:DATALOG:DURation` | 234 | documented | documented only; Datalog App not active |

## Appendix A: body forms absent from the local list

These 19 forms have a body heading or syntax line but are absent from the local copy's List of Commands. They are **not** counted in the 339-row denominator. The Go_NoGo/Template block (pp. 226-231) is the likely table-extraction loss described above.

| Form | Page | Status | Note |
|---|---:|---|---|
| `:DISPlay:OUTPut?` | 74 | hardware-verified | `#538822` + 38,822-byte 16-bit RGB RLE image + LF; decode not implemented; raw/083; fixture hardware/display-output.bin |
| `:LISTer:DATA?` | 167 | documented | body heading only; binary Event Table data; not sent |
| `:GONogo:CLEar` | 226 | documented | GoNoGo App not active; not sent |
| `:GONogo:EXECute` | 226 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:FUNCtion` | 227 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:NGCount` | 227 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:NGDefine` | 227 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:SOURce` | 228 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:VIOLation` | 228 | documented | GoNoGo App not active; query returned an empty line |
| `:GONogo:SCRipt` | 228 | hardware-verified | `:GONogo:SCRipt?` -> `OFF`; raw/077 |
| `:TEMPlate:MODe` | 229 | documented | GoNoGo App not active; query returned an empty line |
| `:TEMPlate:MAXimum` | 229 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:MINimum` | 229 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:POSition:MAXimum` | 230 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:POSition:MINimum` | 230 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:SAVe:MAXimum` | 231 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:SAVe:MINimum` | 231 | documented | GoNoGo App not active; not sent |
| `:TEMPlate:TOLerance` | 231 | documented | GoNoGo App not active; query returned an empty line |
| `:TEMPlate:SAVe:AUTo` | 231 | documented | GoNoGo App not active; not sent |

## Appendix B: referenced-only spellings

These are named in related-command prose but have no syntax line or list row. They are not commands this Skill can claim as documented syntax; treat them as `UNVERIFIED`.

| Form | Page | Status | Note |
|---|---:|---|---|
| `:TRIGger:LOGic:INPut:CLOCK:EDGe` | 144 | documented | referenced as a related command in the logic-trigger section; no syntax heading or list row; UNVERIFIED against the manual |
| `:SEARCH:TRIGger:LOGic:INPut:CLOCK:EDGe` | 180 | documented | referenced as a related command in the search logic section; no syntax heading or list row; UNVERIFIED against the manual |

## Appendix C: verified sendable spellings not printed in the list

The list prints the family form; the instrument accepted these exact spellings. They are cited here so a reader can reproduce the hardware-verified claims without guessing a suffix.

| Sent form | Evidence | Result |
|---|---|---|
| `:ACQuire1:MEMory?` | raw/027-block-ACQuire1_MEMory.bin | 5,000-point waveform, `COMPLETE` structure, calibration `UNVERIFIED` |
| `:ACQuire1:LMEMory?` | earlier capture only | 1,000,000-point capture, not shipped |
| `:ACQuire1:STATe?` | raw/036-query-ACQuire1_STATe.bin | `1` |
| `:MEASure:SOURce1?` | raw/019-query-MEASure_SOURce1.bin | `CH1` |
| `:MEASure:SOURce1 CH2` | commands.jsonl write record | source changed; `Ch Off` read |
| `:MEASure:SOURce1 CH1` | commands.jsonl write record | source restored |
| `:MEASUrement:MEAS1:VALue?` | fixture hardware/measure-sentinel.txt | `9.9E+37` -> `INCOMPLETE` |
| `:DISPlay:OUTPut?` | raw/083-block-DISPlay_OUTPut.bin | `#538822` + 38,822 bytes + LF; image decode `UNVERIFIED` |

## Page-number limit

The local copy is converted text. The numbers above are the list/TOC markers only; a body page cannot be recovered from this copy. If the PDF is available, cite its physical pages, not a guessed offset.
