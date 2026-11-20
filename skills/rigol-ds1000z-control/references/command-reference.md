# Command Reference (Fallback Index, DS1000Z)

**This is a fallback index, not a starting point.** Load it only when the
task-specific reference and the scripts cannot answer a command question. Its
scope is what this Skill has already recorded from the *MSO1000Z/DS1000Z
Programming Guide*, PGA19108-1110, Software Version 00.04.03.SP2; that manual is
the authority and is not copied here. **Any command outside this index must be
verified against the manual before use, and the safety rules in `SKILL.md` still
apply**: no routine `*RST`, no `*SAV`/`*RCL`/`:SAVE`/`:RECAll`, no writing
`:LAN:` command, no `:AUToscale`, no reference/mask/calibration writes, and no
overwrite of operator files on the instrument or on disk.

`artifacts/rigol-ds1000z/command-pages.tsv` lists only command forms that begin
with `:`; the optional-root subsystems `[:SOURce[<n>]]` (built-in signal source,
PDF pp. 146-157) and `[:TRACe[<n>]]` (volatile memory of that source, PDF
pp. 164-168) are therefore absent from it. Matching that file is not proof that
the manual holds no further commands — check the optional-root sections below.

Status in the `说明` column:

- `hardware-verified` — an actual reply was captured from
  `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4`; the quote is in the
  note or in `artifacts/rigol-ds1000z/`.
- `documented` — from the manual only, untested on that firmware.
- `not implemented` — this Skill never sends it; read the cited page first.

Conventions: `<n>` is a channel/index number, `?` marks the query form, `\|`
separates alternative values inside `{}`, and `—` in the parameter column means
the manual defines no parameter. Numeric parameters take bare numbers in the
command's default unit; a unit suffix such as `12K` is rejected with
`-220,"Parameter error"` (`hardware-verified`, manual PDF p. 17 note 3).

## IEEE 488.2 common commands (PDF pp. 95-97)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `*CLS` | — | none | Clear event registers and the error queue | 95 |
| `*ESE <value>` | `*ESE?` | Integer, bits 1 and 6 unused (`X0XXXX0X`) | Standard event enable; default 0 | 95 |
| `*ESR?` | — | returns integer | Query and clear the event register; answered `32` (`hardware-verified`) | 96 |
| `*IDN?` | — | returns `RIGOL TECHNOLOGIES,<model>,<serial>,<software version>` | Gate the model first; answered `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4` (`hardware-verified`) | 96 |
| `*OPC` | `*OPC?` | `1` when the operation finished | `*OPC?` answered `1` (`hardware-verified`) | 96 |
| `*RST` | — | none | Restores the default state and destroys the operator setup; refused by this Skill | 96 |
| `*SRE <value>` | `*SRE?` | Integer 0 to 255, bits 0-1 unused | Service request enable; default 0 | 97 |
| `*STB?` | — | returns integer | Status byte; answered `4` (`hardware-verified`) | 97 |
| `*TST?` | — | returns integer | Self-test result; answered `0` (`hardware-verified`) | 97 |
| `*WAI` | — | none | Wait for the current operation | 97 |

`*OPT?` is **not** in the manual and returns `command error` on this firmware
(`hardware-verified`); the option inventory is only reachable through
`:SYSTem:OPTion:*` (PDF pp. 162-163).

## Run and acquisition control (PDF pp. 18-19)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:RUN` | — | none | Start acquisition; returns nothing, leave ~0.3-0.4 s (`hardware-verified`) | 18 |
| `:STOP` | — | none | Stop acquisition; required before RAW/MAXimum reads | 18 |
| `:SINGle` | — | none | One trigger then stop; `:TRIGger:STATus?` became `STOP` (`hardware-verified`) | 19 |
| `:TFORce` | — | none | Force a trigger; only in `NORMal`/`SINGle` sweep | 19 |
| `:CLEar` | — | none | Clear the display; the trace reappears immediately in RUN | 18 |
| `:AUToscale` | — | none | Rewrites vertical, timebase and trigger; operator authorization required, never sent | 18 |

## Acquisition (`:ACQuire`, PDF pp. 20-23)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:ACQuire:TYPE <type>` | `:ACQuire:TYPE?` | `{NORMal\|AVERages\|PEAK\|HRESolution}`, default `NORMal`; echoes `NORM`/`AVER`/`PEAK`/`HRES` | answered `NORM` (`hardware-verified`) | 22 |
| `:ACQuire:MDEPth <mdep>` | `:ACQuire:MDEPth?` | pts; 1 ch `{AUTO\|12000\|120000\|1200000\|12000000\|24000000}`, 2 ch `{AUTO\|6000\|60000\|600000\|6000000\|12000000}`, 3-4 ch `{AUTO\|3000\|30000\|300000\|3000000\|6000000}`, default `AUTO` | Writable **only while running**; stopped = `-200 Execution error`; `12K`-style suffixes = `-220` (`hardware-verified`) | 21 |
| `:ACQuire:AVERages <count>` | `:ACQuire:AVERages?` | Integer `2^n`, n = 1..10 (2 to 1024), default 2 | Applies only in `AVERages` mode | 20 |
| `:ACQuire:SRATe?` | — | NR3, Sa/s | Read-only; answered `1.000000e+09` (`hardware-verified`) | 23 |

## Calibration (`:CALibrate`, PDF p. 24): not implemented

> **Not implemented.** Documented in the manual but not exercised by this Skill:
> self-calibration can only be started by the operator from the front panel, and
> this Skill never sends `:CALibrate:STARt` or `:CALibrate:QUIT`.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:CALibrate:STARt` | — | none | Starts self-calibration; every input must be disconnected and most keys are disabled | 24 |
| `:CALibrate:QUIT` | — | none | Exits self-calibration at any time, including a mis-started one | 24 |

## Vertical (`:CHANnel<n>`, PDF pp. 25-31)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:CHANnel<n>:SCALe <scale>` | `:CHANnel<n>:SCALe?` | V/div; 1X 1 mV-10 V, 10X 10 mV-100 V; default 1 V at 10X | 1-2-5 steps unless `VERNier ON`; answered `5.000000e-01` (`hardware-verified`) | 30 |
| `:CHANnel<n>:RANGe <range>` | `:CHANnel<n>:RANGe?` | V; 1X 8 mV-80 V, 10X 80 mV-800 V; default 8 V at 10X | Sets scale = range/8 indirectly | 28 |
| `:CHANnel<n>:OFFSet <offset>` | `:CHANnel<n>:OFFSet?` | V; 1X scale≥500 mV/div: ±100 V, scale<500 mV/div: ±2 V; 10X doubles; default 0 V | The only vertical-position control; answered `-1.520000e+00` (`hardware-verified`) | 27 |
| `:CHANnel<n>:COUPling <coupling>` | `:CHANnel<n>:COUPling?` | `{AC\|DC\|GND}`, default `DC` | answered `DC` (`hardware-verified`) | 26 |
| `:CHANnel<n>:PROBe <atten>` | `:CHANnel<n>:PROBe?` | `{0.01\|0.02\|0.05\|0.1\|0.2\|0.5\|1\|2\|5\|10\|20\|50\|100\|200\|500\|1000}`, default 10 | Set before `SCALe`; answered `1.000000e+00` (`hardware-verified`) | 30 |
| `:CHANnel<n>:BWLimit <type>` | `:CHANnel<n>:BWLimit?` | `{20M\|OFF}`, default `OFF` | answered `OFF` (`hardware-verified`) | 25 |
| `:CHANnel<n>:INVert <bool>` | `:CHANnel<n>:INVert?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Inverts displayed and measured values | 27 |
| `:CHANnel<n>:DISPlay <bool>` | `:CHANnel<n>:DISPlay?` | `{{1\|ON}\|{0\|OFF}}`; default `1` CH1, `0` CH2-CH4 | CH1-CH4 read `1,0,0,0` (`hardware-verified`) | 26 |
| `:CHANnel<n>:UNITs <units>` | `:CHANnel<n>:UNITs?` | `{VOLTage\|WATT\|AMPere\|UNKNown}`, default `VOLTage`; echoes `VOLT`/`WATT`/`AMP`/`UNKN` | Changes the unit of amplitude commands and trigger level | 31 |
| `:CHANnel<n>:VERNier <bool>` | `:CHANnel<n>:VERNier?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Fine vertical adjust; answered `1` (`hardware-verified`) | 31 |
| `:CHANnel<n>:TCAL <val>` | `:CHANnel<n>:TCAL?` | s; -100 ns to 100 ns, default 0 s; `TIMEbase ≥ 10 µs/div` forbids adjustment | Zero-delay trim, not calibration; answered `0.000000e+00` (`hardware-verified`) | 29 |

`:CHANnel<n>:POSition` **does not exist** (manual pp. 25-31; `command error` on
hardware, `hardware-verified`). Use `:OFFSet`.

## Horizontal (`:TIMebase`, PDF pp. 169-173)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TIMebase:MODE <mode>` | `:TIMebase:MODE?` | `{MAIN\|XY\|ROLL}`, default `MAIN` | answered `MAIN` (`hardware-verified`) | 173 |
| `:TIMebase[:MAIN]:SCALe <scale>` | `:TIMebase[:MAIN]:SCALe?` | s/div; YT 5 ns/div-50 s/div, ROLL 200 ms/div-50 s/div, 1-2-5 steps; default 1 µs/div | answered `2.0000000e-04` (`hardware-verified`) | 173 |
| `:TIMebase[:MAIN]:OFFSet <offset>` | `:TIMebase[:MAIN]:OFFSet?` | s; RUN `-0.5*MDEPth/SRATe` to 1 s (or to 10×scale at ≥200 ms/div), STOP `-MDEPth/SRATe` to `1 s+0.5*MDEPth/SRATe`; default 0 | Invalid in ROLL while running | 172 |
| `:TIMebase:DELay:ENABle <bool>` | `:TIMebase:DELay:ENABle?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Delayed sweep on/off | 169 |
| `:TIMebase:DELay:SCALe <scale>` | `:TIMebase:DELay:SCALe?` | s/div; max = main scale, min = 50/(sample rate × amplification factor); default 500 ns/div | 1-2-5 steps only | 171 |
| `:TIMebase:DELay:OFFSet <offset>` | `:TIMebase:DELay:OFFSet?` | s; `-(LeftTime-DelayRange/2)` to `(RightTime-DelayRange/2)`; default 0 | Depends on main and delay scales | 170 |

## Trigger, common (`:TRIGger`, PDF pp. 172-177)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:MODE <mode>` | `:TRIGger:MODE?` | `{EDGE\|PULSe\|RUNT\|WIND\|NEDG\|SLOPe\|VIDeo\|PATTern\|DELay\|TIMeout\|DURation\|SHOLd\|RS232\|IIC\|SPI}`, default `EDGE`; echoes `EDGE`/`PULS`/`RUNT`/`WIND`/`NEDG`/`SLOP`/`VID`/`PATT`/`DEL`/`TIM`/`DUR`/`SHOL`/`RS232`/`IIC`/`SPI` | answered `EDGE` (`hardware-verified`) | 174 |
| `:TRIGger:SWEep <sweep>` | `:TRIGger:SWEep?` | `{AUTO\|NORMal\|SINGle}`, default `AUTO`; echoes `AUTO`/`NORM`/`SING` | `AUTO` never proves a trigger; answered `AUTO` (`hardware-verified`) | 175 |
| `:TRIGger:COUPling <couple>` | `:TRIGger:COUPling?` | `{AC\|DC\|LFReject\|HFReject}`, default `DC`; echoes `AC`/`DC`/`LFR`/`HFR`; edge trigger on an analog source only | answered `DC` (`hardware-verified`) | 175 |
| `:TRIGger:HOLDoff <value>` | `:TRIGger:HOLDoff?` | s; 16 ns-10 s, default 16 ns | Unavailable for video/timeout/setup-hold/Nth-edge/RS232/IIC/SPI | 176 |
| `:TRIGger:NREJect <bool>` | `:TRIGger:NREJect?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Unavailable when the source is digital | 176 |
| `:TRIGger:STATus?` | — | returns `TD`, `WAIT`, `RUN`, `AUTO`, `STOP` | `TD` running and `STOP` after `:STOP` (`hardware-verified`); other values `documented` | 175 |
| `:TRIGger:POSition?` | — | integer; `-2` not triggered, `-1` triggered outside memory | Trigger position inside the memory record | 177 |

## Edge trigger (`:TRIGger:EDGe`, PDF pp. 178-179)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:EDGe:SOURce <source>` | `:TRIGger:EDGe:SOURce?` | `{CHANnel1..CHANnel4\|AC\|D0..D15}`, default `CHANnel1`; echoes `CHAN1`..`CHAN4`/`AC`/`D0`..`D15` | answered `CHAN1` (`hardware-verified`) | 178 |
| `:TRIGger:EDGe:SLOPe <slope>` | `:TRIGger:EDGe:SLOPe?` | `{POSitive\|NEGative\|RFALl}`, default `POSitive`; echoes `POS`/`NEG`/`RFAL` | answered `POS` (`hardware-verified`) | 178 |
| `:TRIGger:EDGe:LEVel <level>` | `:TRIGger:EDGe:LEVel?` | source amplitude unit; `(-5×VScale-OFFSet)` to `(5×VScale-OFFSet)`, default 0 | Range moves with scale/offset; answered `1.500000e+00` (`hardware-verified`) | 179 |

## Other trigger types: present in the manual, not implemented here

Listed for header lookup only. Everything below is **`not implemented`** by this
Skill: it configures no source, level, or qualifier for these types and has no
evidence for them. Items marked "(Option)" depend on installed options that
cannot be queried (`*OPT?` fails, `hardware-verified`).

### Pulse width (`:TRIGger:PULSe`, PDF pp. 180-183)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:PULSe:SOURce <source>` | `:TRIGger:PULSe:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 180 |
| `:TRIGger:PULSe:WHEN <when>` | `:TRIGger:PULSe:WHEN?` | `{PGReater\|PLESs\|NLESs\|PGLess\|NGLess}`, default `PGReater` | not implemented | 181 |
| `:TRIGger:PULSe:WIDTh <width>` | `:TRIGger:PULSe:WIDTh?` | s; 8 ns-10 s (PLESs/NLESs default 2 µs) | not implemented | 181 |
| `:TRIGger:PULSe:UWIDth <width>` | `:TRIGger:PULSe:UWIDth?` | s; 16 ns-10 s, default 2 µs | Upper-limit pulse width | 182 |
| `:TRIGger:PULSe:LWIDth <width>` | `:TRIGger:PULSe:LWIDth?` | s; 8 ns-9.99 s, default 1 µs | Lower-limit pulse width | 182 |
| `:TRIGger:PULSe:LEVel <level>` | `:TRIGger:PULSe:LEVel?` | source unit; default 0 | not implemented | 183 |

### Rise/fall time (`:TRIGger:SLOPe`, PDF pp. 184-188)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:SLOPe:SOURce <source>` | `:TRIGger:SLOPe:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 184 |
| `:TRIGger:SLOPe:WHEN <when>` | `:TRIGger:SLOPe:WHEN?` | `{PGReater\|PLESs\|NLESs\|PGLess\|NGLess}`, default `PGReater` | not implemented | 185 |
| `:TRIGger:SLOPe:TIME <time>` | `:TRIGger:SLOPe:TIME?` | s; 8 ns-10 s (PLESs/NLESs default 2 µs) | not implemented | 185 |
| `:TRIGger:SLOPe:TUPPer <time>` | `:TRIGger:SLOPe:TUPPer?` | s; 16 ns-10 s, default 2 µs | Upper time limit | 186 |
| `:TRIGger:SLOPe:TLOWer <time>` | `:TRIGger:SLOPe:TLOWer?` | s; 8 ns-9.99 s, default 1 µs | Lower time limit | 186 |
| `:TRIGger:SLOPe:WINDow <window>` | `:TRIGger:SLOPe:WINDow?` | `{TA\|TB\|TAB}`, default `TA` | not implemented | 187 |
| `:TRIGger:SLOPe:ALEVel <level>` | `:TRIGger:SLOPe:ALEVel?` | source unit; default 2 V | Upper threshold | 187 |
| `:TRIGger:SLOPe:BLEVel <level>` | `:TRIGger:SLOPe:BLEVel?` | source unit; default 0 | Lower threshold | 188 |

### Video (`:TRIGger:VIDeo`, PDF pp. 189-191)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:VIDeo:SOURce <source>` | `:TRIGger:VIDeo:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 189 |
| `:TRIGger:VIDeo:POLarity <polarity>` | `:TRIGger:VIDeo:POLarity?` | `{POSitive\|NEGative}`, default `POSitive` | not implemented | 189 |
| `:TRIGger:VIDeo:MODE <mode>` | `:TRIGger:VIDeo:MODE?` | `{ODDField\|EVENfield\|LINE\|ALINes}`, default `ALINes` | not implemented | 190 |
| `:TRIGger:VIDeo:LINE <line>` | `:TRIGger:VIDeo:LINE?` | line number (`documented`) | Only with `MODE LINE` | 190 |
| `:TRIGger:VIDeo:STANdard <standard>` | `:TRIGger:VIDeo:STANdard?` | `{PALSecam\|NTSC\|480P\|576P}`, default `NTSC` | not implemented | 191 |
| `:TRIGger:VIDeo:LEVel <level>` | `:TRIGger:VIDeo:LEVel?` | source unit; default 0 | not implemented | 191 |

### Pattern (`:TRIGger:PATTern`, PDF pp. 192-194)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:PATTern:PATTern <pa_ch1>,…,<pa_ch4>,<pa_d0>,…,<pa_d15>` | `:TRIGger:PATTern:PATTern?` | per source `{H\|L\|X\|R\|F}`, default `X` | Not implemented; needs digital channels | 193 |
| `:TRIGger:PATTern:LEVel <chan>,<level>` | `:TRIGger:PATTern:LEVel?` | `<chan>` `{CHANnel1..CHANnel4}`, level in source unit, default 0 | Pattern threshold | 194 |

### Duration (`:TRIGger:DURATion`, PDF pp. 195-198)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:DURATion:SOURce <source>` | `:TRIGger:DURATion:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 195 |
| `:TRIGger:DURATion:TYPe <type_ch1>,…` | `:TRIGger:DURATion:TYPe?` | per source `{H\|L\|X}`, default `X` | not implemented | 196 |
| `:TRIGger:DURATion:WHEN <when>` | `:TRIGger:DURATion:WHEN?` | `{GREater\|LESS\|GLESs}`, default `GREater` | not implemented | 197 |
| `:TRIGger:DURATion:TUPPer <NR3>` | `:TRIGger:DURATion:TUPPer?` | s; LESS 8 ns-10 s, GLESs 16 ns-10 s, default 2 µs | Upper duration limit | 197 |
| `:TRIGger:DURATion:TLOWer <NR3>` | `:TRIGger:DURATion:TLOWer?` | s; 8 ns-9.99 s, default 1 µs | Lower duration limit | 198 |

### Timeout, option (`:TRIGger:TIMeout`, PDF pp. 199-200)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:TIMeout:SOURce <source>` | `:TRIGger:TIMeout:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 199 |
| `:TRIGger:TIMeout:SLOPe <slope>` | `:TRIGger:TIMeout:SLOPe?` | `{POSitive\|NEGative\|RFALl}`, default `POSitive` | not implemented | 199 |
| `:TRIGger:TIMeout:TIMe <NR3>` | `:TRIGger:TIMeout:TIMe?` | s; 16 ns-10 s, default 16 ns | not implemented | 200 |

### Runt, option (`:TRIGger:RUNT`, PDF pp. 201-204)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:RUNT:SOURce <source>` | `:TRIGger:RUNT:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 201 |
| `:TRIGger:RUNT:POLarity <polarity>` | `:TRIGger:RUNT:POLarity?` | `{POSitive\|NEGative}`, default `POSitive` | not implemented | 201 |
| `:TRIGger:RUNT:WHEN <when>` | `:TRIGger:RUNT:WHEN?` | `{NONE\|GREater\|LESS\|GLESs}`, default `NONE` | not implemented | 202 |
| `:TRIGger:RUNT:WUPPer <NR3>` | `:TRIGger:RUNT:WUPPer?` | s; GREater/LESS up to 10 s, GLESs 16 ns-10 s; default 2 µs | Upper width limit | 202 |
| `:TRIGger:RUNT:WLOWer <NR3>` | `:TRIGger:RUNT:WLOWer?` | s; from 8 ns up to 9.99 s, default 1 µs | Lower width limit | 203 |
| `:TRIGger:RUNT:ALEVel <level>` | `:TRIGger:RUNT:ALEVel?` | source unit; default 2 V | Upper threshold | 203 |
| `:TRIGger:RUNT:BLEVel <level>` | `:TRIGger:RUNT:BLEVel?` | source unit; default 0 | Lower threshold | 204 |

### Window, option (`:TRIGger:WINDows`, PDF pp. 205-207)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:WINDows:SOURce <source>` | `:TRIGger:WINDows:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 205 |
| `:TRIGger:WINDows:SLOPe <type>` | `:TRIGger:WINDows:SLOPe?` | `{POSitive\|NEGative\|RFALl}`, default `POSitive` | not implemented | 205 |
| `:TRIGger:WINDows:POSition <type>` | `:TRIGger:WINDows:POSition?` | `{EXIT\|ENTER\|TIMe}`, default `ENTER` | Trigger on entering, exiting, or after a time | 206 |
| `:TRIGger:WINDows:TIMe <NR3>` | `:TRIGger:WINDows:TIMe?` | s; 8 ns-10 s, default 1 µs | Only with `POSition TIMe` | 206 |
| `:TRIGger:WINDows:ALEVel <level>` | `:TRIGger:WINDows:ALEVel?` | source unit; default 2 V | Upper threshold | 207 |
| `:TRIGger:WINDows:BLEVel <level>` | `:TRIGger:WINDows:BLEVel?` | source unit; default 0 | Lower threshold | 207 |

### Delay, option (`:TRIGger:DELay`, PDF pp. 208-211)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:DELay:SA <source>` | `:TRIGger:DELay:SA?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | Source A | 208 |
| `:TRIGger:DELay:SLOPA <slope>` | `:TRIGger:DELay:SLOPA?` | `{POSitive\|NEGative}`, default `POSitive` | Source A edge | 208 |
| `:TRIGger:DELay:SB <source>` | `:TRIGger:DELay:SB?` | `{CHANnel1..CHANnel4}`, default `CHANnel2` | Source B | 209 |
| `:TRIGger:DELay:SLOPB <slope>` | `:TRIGger:DELay:SLOPB?` | `{POSitive\|NEGative}`, default `POSitive` | Source B edge | 209 |
| `:TRIGger:DELay:TYPe <type>` | `:TRIGger:DELay:TYPe?` | `{GREater\|LESS\|GLESs\|GOUT}`, default `GREater` | not implemented | 210 |
| `:TRIGger:DELay:TUPPer <NR3>` | `:TRIGger:DELay:TUPPer?` | s; 16 ns-10 s, default 2 µs | Upper delay limit | 210 |
| `:TRIGger:DELay:TLOWer <NR3>` | `:TRIGger:DELay:TLOWer?` | s; GREater 8 ns-10 s, GOUT/GLESs 8 ns-9.99 s; default 1 µs | Lower delay limit | 211 |

### Setup/hold, option (`:TRIGger:SHOLd`, PDF pp. 212-214)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:SHOLd:DSrc <source>` | `:TRIGger:SHOLd:DSrc?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | Data source | 212 |
| `:TRIGger:SHOLd:CSrc <source>` | `:TRIGger:SHOLd:CSrc?` | `{CHANnel1..CHANnel4}`, default `CHANnel2` | Clock source | 212 |
| `:TRIGger:SHOLd:SLOPe <slope>` | `:TRIGger:SHOLd:SLOPe?` | `{POSitive\|NEGative}`, default `POSitive` | Clock edge | 213 |
| `:TRIGger:SHOLd:PATTern <pattern>` | `:TRIGger:SHOLd:PATTern?` | `{H\|L}`, default `H` | Data pattern | 213 |
| `:TRIGger:SHOLd:TYPe <type>` | `:TRIGger:SHOLd:TYPe?` | `{SETup\|HOLd\|SETHOLd}`, default `SETup` | not implemented | 213 |
| `:TRIGger:SHOLd:STIMe <NR3>` | `:TRIGger:SHOLd:STIMe?` | s; 8 ns-1 s, default 1 µs | Setup time | 214 |
| `:TRIGger:SHOLd:HTIMe <NR3>` | `:TRIGger:SHOLd:HTIMe?` | s; 8 ns-1 s, default 1 µs | Hold time | 214 |

### Nth edge, option (`:TRIGger:NEDGe`, PDF pp. 215-216)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:NEDGe:SOURce <source>` | `:TRIGger:NEDGe:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 215 |
| `:TRIGger:NEDGe:SLOPe <slope>` | `:TRIGger:NEDGe:SLOPe?` | `{POSitive\|NEGative}`, default `POSitive` | not implemented | 215 |
| `:TRIGger:NEDGe:IDLE <NR3>` | `:TRIGger:NEDGe:IDLE?` | s; 16 ns-10 s, default 1 µs | Idle time before counting | 216 |
| `:TRIGger:NEDGe:EDGE <NR1>` | `:TRIGger:NEDGe:EDGE?` | Integer 1 to 65535, default 2 | Edge count | 216 |
| `:TRIGger:NEDGe:LEVel <level>` | `:TRIGger:NEDGe:LEVel?` | source unit; default 0 | not implemented | 216 |

### RS232, option (`:TRIGger:RS232`, PDF pp. 217-221)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:RS232:SOURce <source>` | `:TRIGger:RS232:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 217 |
| `:TRIGger:RS232:WHEN <when>` | `:TRIGger:RS232:WHEN?` | `{STARt\|ERRor\|PARity\|DATA}`, default `STARt` | not implemented | 218 |
| `:TRIGger:RS232:PARity <parity>` | `:TRIGger:RS232:PARity?` | `{EVEN\|ODD\|NONE}` | Parity check | 218 |
| `:TRIGger:RS232:STOP <bit>` | `:TRIGger:RS232:STOP?` | `{1\|2}`, default `1` | Stop bits | 219 |
| `:TRIGger:RS232:DATA <data>` | `:TRIGger:RS232:DATA?` | Integer `0` to `2^n-1` where n = width, default 90 | Data value | 219 |
| `:TRIGger:RS232:WIDTh <width>` | `:TRIGger:RS232:WIDTh?` | `{5\|6\|7\|8}`, default `8` | Data bits | 219 |
| `:TRIGger:RS232:BAUD <baud_rate>` | `:TRIGger:RS232:BAUD?` | Discrete presets up to 1000000, default 9600 | not implemented | 220 |
| `:TRIGger:RS232:BUSer <user baud>` | `:TRIGger:RS232:BUSer?` | Integer 110 to 20000000, default 9600 | Custom baud | 220 |
| `:TRIGger:RS232:LEVel <level>` | `:TRIGger:RS232:LEVel?` | source unit; default 0 | not implemented | 221 |

### IIC, option (`:TRIGger:IIC`, PDF pp. 222-225)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:IIC:SCL <source>` | `:TRIGger:IIC:SCL?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 222 |
| `:TRIGger:IIC:SDA <source>` | `:TRIGger:IIC:SDA?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel2` | not implemented | 222 |
| `:TRIGger:IIC:WHEN <trig_type>` | `:TRIGger:IIC:WHEN?` | `{STARt\|RESTart\|STOP\|ACKLost\|ADDRess\|DATA\|ADATa}`, default `STARt` | Condition per PDF p. 223 | 223 |
| `:TRIGger:IIC:AWIDth <bits>` | `:TRIGger:IIC:AWIDth?` | `{7\|8\|10}`, default `7` | Address width | 223 |
| `:TRIGger:IIC:ADDRess <adr>` | `:TRIGger:IIC:ADDRess?` | Integer `0` to `2^n-1` (0-127/0-255/0-1023), default 1 | Address value | 224 |
| `:TRIGger:IIC:DIRection <dir>` | `:TRIGger:IIC:DIRection?` | `{READ\|WRITe\|RWRite}`, default `READ` | Transfer direction | 224 |
| `:TRIGger:IIC:DATA <data>` | `:TRIGger:IIC:DATA?` | Integer `0` to `2^n-1`, default 82 | Data value | 224 |
| `:TRIGger:IIC:CLEVel <level>` | `:TRIGger:IIC:CLEVel?` | source unit; default 0 | SCL threshold | 225 |
| `:TRIGger:IIC:DLEVel <level>` | `:TRIGger:IIC:DLEVel?` | source unit; default 0 | SDA threshold | 225 |

### SPI, option (`:TRIGger:SPI`, PDF pp. 226-231)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:TRIGger:SPI:SCL <source>` | `:TRIGger:SPI:SCL?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | not implemented | 226 |
| `:TRIGger:SPI:SDA <source>` | `:TRIGger:SPI:SDA?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel2` | not implemented | 227 |
| `:TRIGger:SPI:WHEN <trig_type>` | `:TRIGger:SPI:WHEN?` | `{CS\|TIMeout}`, default `CS` | not implemented | 227 |
| `:TRIGger:SPI:WIDTh <width>` | `:TRIGger:SPI:WIDTh?` | Integer 4 to 32, default 8 | Data width | 227 |
| `:TRIGger:SPI:DATA <data>` | `:TRIGger:SPI:DATA?` | Integer `0` to `2^n-1`, default 82 | Data value | 228 |
| `:TRIGger:SPI:TIMeout <time_value>` | `:TRIGger:SPI:TIMeout?` | s; 100 ns-1 s, default 1 µs | Only with `WHEN TIMeout` | 228 |
| `:TRIGger:SPI:SLOPe <slope>` | `:TRIGger:SPI:SLOPe?` | `{POSitive\|NEGative}`, default `POSitive` | Clock edge | 228 |
| `:TRIGger:SPI:CLEVel <level>` | `:TRIGger:SPI:CLEVel?` | source unit; default 0 | Clock threshold | 229 |
| `:TRIGger:SPI:DLEVel <level>` | `:TRIGger:SPI:DLEVel?` | source unit; default 0 | Data threshold | 229 |
| `:TRIGger:SPI:SLEVel <level>` | `:TRIGger:SPI:SLEVel?` | source unit; default 0 | CS threshold | 230 |
| `:TRIGger:SPI:MODE <mode>` | `:TRIGger:SPI:MODE?` | `{HIGH\|LOW}`, default `LOW` | CS polarity | 230 |
| `:TRIGger:SPI:CS <source>` | `:TRIGger:SPI:CS?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel3` | Chip-select source | 231 |

**CAN and LIN do not exist in this manual.** There is no `:TRIGger:CAN`,
`:TRIGger:LIN`, `:DECoder:CAN`, or `:DECoder:LIN` section for this family; do not
send those headers expecting a documented behaviour.

## Waveform readback (`:WAVeform`, PDF pp. 233-242)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:WAVeform:SOURce <source>` | `:WAVeform:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15\|MATH}`, default `CHANnel1` | `MATH` forces `MODE NORMal` | 233 |
| `:WAVeform:MODE <mode>` | `:WAVeform:MODE?` | `{NORMal\|MAXimum\|RAW}`, default `NORMal`; echoes `NORM`/`MAX`/`RAW` | RAW and MAXimum require the stop state | 234 |
| `:WAVeform:FORMat <format>` | `:WAVeform:FORMat?` | `{WORD\|BYTE\|ASCii}`, default `BYTE`; echoes `WORD`/`BYTE`/`ASC` | Sets the block encoding | 234 |
| `:WAVeform:DATA?` | — | TMC `#9` block (BYTE/WORD) or comma-separated volts (ASCii) | Batch limit per read: BYTE 250000, WORD 125000, ASCii 15625 points | 235 |
| `:WAVeform:STARt <sta>` | `:WAVeform:STARt?` | Integer; NORM 1-1200, MAX 1-effective points, RAW 1-memory depth; default 1 | Window start | 240 |
| `:WAVeform:STOP <stop>` | `:WAVeform:STOP?` | Integer; same ranges; default 1200 | Window end; rejected with `-220` while running | 241 |
| `:WAVeform:PREamble?` | — | 10 fields `format,type,points,count,xinc,xorig,xref,yinc,yorig,yref` | `type`: 0 NORM, 1 MAX, 2 RAW | 242 |
| `:WAVeform:XINCrement?` | — | NR3, s (Hz for FFT MATH) | `TimeScale/100` in NORM, `1/SampleRate` in RAW | 238 |
| `:WAVeform:XORigin?` | — | NR3, s | Start time of the data | 238 |
| `:WAVeform:XREFerence?` | — | returns 0 | Reference time | 239 |
| `:WAVeform:YINCrement?` | — | NR3, amplitude unit | `VerticalScale/25` in NORM; RAW value undocumented | 239 |
| `:WAVeform:YORigin?` | — | integer | `VerticalOffset/YINCrement` in NORM | 239 |
| `:WAVeform:YREFerence?` | — | integer | 127 in NORM (0 bottom, 255 top) | 240 |

`:WAVeform:POINts?` = `STOP - STARt + 1` answered on this firmware
(`hardware-verified`) but **is not in the Programming Guide**; treat it as
`UNVERIFIED` against any manual.

## Measurements (`:MEASure`, PDF pp. 131-141)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:MEASure:SOURce <sour>` | `:MEASure:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15\|MATH}`, default `CHANnel1` | Channels may be selected while off (that is how `9.9E37` appears) | 132 |
| `:MEASure:COUNter:SOURce <sour>` | `:MEASure:COUNter:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15\|OFF}`, default `OFF` | Frequency-counter source | 132 |
| `:MEASure:COUNter:VALue?` | — | NR3, Hz; `0.0000000e+00` when the counter is off | Answered `1.0000066e+03` (`hardware-verified`) | 133 |
| `:MEASure:ITEM <item>[,<src>[,<src>]]` | `:MEASure:ITEM? <item>[,<src>[,<src>]]` | item enum per PDF pp. 140-141; source defaults to `:MEASure:SOURce` | `ITEM? VPP` answered `3.040000e+00`, `ITEM? RTIMe` answered `9.9E37` (`hardware-verified`) | 141 |
| `:MEASure:ADISplay <bool>` | `:MEASure:ADISplay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | All-measurement panel, 29 parameters | 134 |
| `:MEASure:AMSource <src>[,<src>[,…]]` | `:MEASure:AMSource?` | `{CHANnel1..CHANnel4\|MATH}`, default `CHANnel1` | Sources for the all-measurement panel | 134 |
| `:MEASure:CLEar <item>` | — | `{ITEM1\|ITEM2\|ITEM3\|ITEM4\|ITEM5\|ALL}` | Clears one of the last five items | 133 |
| `:MEASure:RECover <item>` | — | same enum | Restores a cleared item | 133 |
| `:MEASure:SETup:MAX <value>` | `:MEASure:SETup:MAX?` | Integer 7 to 95 (% of amplitude), default 90 | Threshold upper limit for time/delay/phase | 135 |
| `:MEASure:SETup:MID <value>` | `:MEASure:SETup:MID?` | Integer 6 to 94 (%), default 50 | Threshold middle value | 135 |
| `:MEASure:SETup:MIN <value>` | `:MEASure:SETup:MIN?` | Integer 5 to 93 (%), default 10 | Threshold lower limit | 135-136 |
| `:MEASure:SETup:PSA <source>` | `:MEASure:SETup:PSA?` | `{CHANnel1..CHANnel4\|D0..D15}` | Phase source A | 136 |
| `:MEASure:SETup:PSB <source>` | `:MEASure:SETup:PSB?` | `{CHANnel1..CHANnel4\|D0..D15}` | Phase source B | 137 |
| `:MEASure:SETup:DSA <source>` | `:MEASure:SETup:DSA?` | `{CHANnel1..CHANnel4\|D0..D15}` | Delay source A | 137 |
| `:MEASure:SETup:DSB <source>` | `:MEASure:SETup:DSB?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel2` | Delay source B | 138 |
| `:MEASure:STATistic:DISPlay <bool>` | `:MEASure:STATistic:DISPlay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Statistics must be enabled before any result query; not implemented | 138 |
| `:MEASure:STATistic:MODE <mode>` | `:MEASure:STATistic:MODE?` | `{DIFFerence\|EXTRemum}`, default `EXTRemum`; echoes `DIFF`/`EXTR` | not implemented | 139 |
| `:MEASure:STATistic:RESet` | — | none | Clears the history; not implemented | 139 |
| `:MEASure:STATistic:ITEM <item>[,<src>[,…]]` | `:MEASure:STATistic:ITEM? <type>,<item>[,…]` | `<type>` `{MAXimum\|MINimum\|CURRent\|AVERages\|DEViation}` | Not enabled → `command error` plus `-410,"Query INTERRUPTED"` (`hardware-verified`) | 140 |

Item enumeration for `:MEASure:ITEM` and `:MEASure:STATistic:ITEM`
(PDF pp. 140-141, 37 items):

```text
VMAX VMIN VPP VTOP VBASe VAMP VAVG VRMS OVERshoot PREShoot MARea MPARea PERiod
FREQuency RTIMe FTIMe PWIDth NWIDth PDUTy NDUTy RDELay FDELay RPHase FPHase TVMAX
TVMIN PSLEWrate NSLEWrate VUPper VMID VLOWer VARIance PVRMS PPULses NPULses
PEDGes NEDGes
```

Shortcut queries that are **not in the manual** but answered on
`00.04.02.SP4` (`hardware-verified`); the item name behind each is the
documented equivalent:

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:MEASure:VPP?` | query only | NR3, V | `3.040000e+00`; item `VPP` | — |
| `:MEASure:VMAX?` | query only | NR3, V | `3.000000e+00`; item `VMAX` | — |
| `:MEASure:VMIN?` | query only | NR3, V | `-4.000000e-02`; item `VMIN` | — |
| `:MEASure:VAVG?` | query only | NR3, V | `1.493662e+00`; item `VAVG` | — |
| `:MEASure:VAMP?` | query only | NR3, V | `2.916700e+00`; item `VAMP` | — |
| `:MEASure:VRMS?` | query only | NR3, V | `2.082721e+00`; item `VRMS` | — |
| `:MEASure:VTOP?` | query only | NR3, V | `2.952131e+00`; item `VTOP` | — |
| `:MEASure:VBASe?` | query only | NR3, V | `3.098358e-02`; item `VBASe` | — |
| `:MEASure:OVERshoot?` | query only | NR3, ratio | `1.638704e-02`; item `OVERshoot` | — |
| `:MEASure:PREShoot?` | query only | NR3, ratio | `1.745327e-02`; item `PREShoot` | — |
| `:MEASure:FREQuency?` | query only | NR3, Hz | `9.999999e+02`; item `FREQuency` | — |
| `:MEASure:PERiod?` | query only | NR3, s | `1.000000e-03`; item `PERiod` | — |
| `:MEASure:PDUTy?` | query only | NR3, fraction | `5.039999e-01`; item `PDUTy` | — |
| `:MEASure:NDUTy?` | query only | NR3, fraction | `4.960000e-01`; item `NDUTy` | — |
| `:MEASure:PWIDth?` | query only | NR3, s | `5.040000e-04`; item `PWIDth` | — |
| `:MEASure:NWIDth?` | query only | NR3, s | `4.960000e-04`; item `NWIDth` | — |

Rejected with `command error` on `00.04.02.SP4` (`hardware-verified`):
`:MEASure:VAVerage?`, `:MEASure:RISetime?`, `:MEASure:FALLtime?`,
`:MEASure:+DUTy?`, `:MEASure:-DUTy?`, `:MEASure:+PULses?`, `:MEASure:-PULses?`,
`:MEASure:+EDGes?`, `:MEASure:-EDGes?`, `:MEASure:PHASe?`, `:MEASure:COUNter?`.
Use the item spellings instead (`RTIMe`, `FTIMe`, `PDUTy`, `NDUTy`, `PPULses`,
`NPULses`, `PEDGes`, `NEDGes`, `RPHase`/`FPHase`).

## Display (`:DISPlay`, PDF pp. 78-82)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:DISPlay:DATA?` | — | `[<color>,<invert>,<format>]`; `<color>` `{ON\|OFF}`, `<invert>` `{{1\|ON}\|{0\|OFF}}`, `<format>` `{BMP24\|BMP8\|PNG\|JPEG\|TIFF}` | Firmware accepts only 0-2 arguments and always returns BMP; 3 bytes past the declared length (`hardware-verified`) | 79 |
| `:DISPlay:CLEar` | — | none | Clear the display | 78 |
| `:DISPlay:TYPE <type>` | `:DISPlay:TYPE?` | `{VECTors\|DOTS}`, default `VECTors` | answered `VECT` (`hardware-verified`) | 80 |
| `:DISPlay:GRID <grid>` | `:DISPlay:GRID?` | `{FULL\|HALF\|NONE}`, default `FULL` | answered `FULL` (`hardware-verified`) | 82 |
| `:DISPlay:GRADing:TIME <time>` | `:DISPlay:GRADing:TIME?` | persistence time | Changes what the screenshot shows | 81 |
| `:DISPlay:WBRightness <time>` | `:DISPlay:WBRightness?` | waveform brightness | not implemented | 81 |
| `:DISPlay:GBRightness <brightness>` | `:DISPlay:GBRightness?` | Integer 0 to 100, default 50 | Grid brightness; `:DISPlay:BRIGhtness?` is `command error` (`hardware-verified`) | 82 |

## System (`:SYSTem`, PDF pp. 160-166)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:SYSTem:ERRor[:NEXT]?` | — | returns `<code>,"<text>"` | One entry per query, `0,"No error"` terminates; drain after every operation | 161 |
| `:SYSTem:AUToscale <bool>` | `:SYSTem:AUToscale?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Enables the AUTO key behaviour, not the `:AUToscale` action | 160 |
| `:SYSTem:BEEPer <bool>` | `:SYSTem:BEEPer?` | `{{1\|ON}\|{0\|OFF}}` | Key beeper | 161 |
| `:SYSTem:GAM?` | — | always 12 | Confirms the 12-division horizontal geometry | 161 |
| `:SYSTem:LANGuage <lang>` | `:SYSTem:LANGuage?` | `{SCHinese\|TCHinese\|ENGLish\|PORTuguese\|GERMan\|POLish\|KORean\|JAPAnese\|FRENch\|RUSSian}` | Survives `*RST`; not implemented | 161 |
| `:SYSTem:LOCKed <bool>` | `:SYSTem:LOCKed?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Panel lock; dangerous for a remote-only operator, not implemented | 162 |
| `:SYSTem:PON <pon>` | `:SYSTem:PON?` | `{LATest\|DEFault}`, default `LATest` | Power-on state | 162 |
| `:SYSTem:OPTion:INSTall <license>` | — | 28-byte ASCII license | Installs an option; never sent | 162 |
| `:SYSTem:OPTion:UNINSTall` | — | none | Removes options; never sent | 163 |
| `:SYSTem:RAM?` | — | always 4 | Number of analog channels | 163 |
| `:SYSTem:SETup <setup_stream>` | `:SYSTem:SETup?` | TMC block, e.g. `#9000002077` | The query returns `command error` on `00.04.02.SP4` (`hardware-verified`); the write restores state, never sent | 163 |

Unsupported headers on this firmware despite a plausible shape
(`hardware-verified`, `command error`): `:SYSTem:KEY?`, `:SYSTem:KEY:LOCK?`,
`:SYSTem:Expansion?`, `:INFO:MODEL?`, `:ACQuire:MDEPth:AUTO?`,
`:ACQuire:SAVer?`, `:DISPlay:BRIGhtness?`, `:WAVeform:WIDth?`,
`:MENU:MEASure?`. `*SYSTem:MODEL?` is accepted as an alias of `*IDN?`
(`hardware-verified`) but is not in the manual.

## Measured-only commands (answered on `00.04.02.SP4`, absent from the manual)

These reply on the bench unit but the Programming Guide documents no such header.
They are `UNVERIFIED` against the manual: do not cite a page for them, and do not
treat them as portable to another firmware.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:WAVeform:POINts?` | query only | NR3 integer, points | Measured: equals `STOP - STARt + 1` (`1200`, `4000`, `240000` observed). Read it back instead of trusting a `:WAVeform:STOP` write. | — |
| `:LAN:STATus?` / `:LAN:DHCP?` / `:LAN:IPADdress?` / `:LAN:SMASk?` / `:LAN:GATeway?` / `:LAN:MAC?` / `:LAN:MANual?` | query only | text / dotted quad / `ON\|OFF` | Measured; the manual has no `:LAN:` subsystem at all (only `:SYSTem:LANGuage`). Any `:LAN:` **write** is refused by the scripts. | — |

## Storage, reference, and mask (not implemented)

Every command below is **`not implemented`**: each one replaces operator data or
consumes instrument memory. They are indexed so a header can be checked, not so
they can be called.

### Image-save settings (`:STORage`, PDF pp. 158-159)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:STORage:IMAGe:TYPE <type>` | `:STORage:IMAGe:TYPE?` | `{PNG\|BMP8\|BMP24\|JPEG\|TIFF}`, default `PNG` | Affects front-panel file saves, not `:DISPlay:DATA?` | 158 |
| `:STORage:IMAGe:INVERT <bool>` | `:STORage:IMAGe:INVERT?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | not implemented | 158 |
| `:STORage:IMAGe:COLor <bool>` | `:STORage:IMAGe:COLor?` | `{ON\|OFF}`, default `ON` | not implemented | 159 |

### Reference waveforms (`:REFerence`, PDF pp. 142-145)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:REFerence<n>:SAVe` | — | `<n>` `{1..10}` | Overwrites that reference slot; never sent | 145 |
| `:REFerence<n>:RESet` | — | `<n>` `{1..10}` | Deletes the slot content; never sent | 144 |
| `:REFerence<n>:CURRent <n>` | `:REFerence<n>:CURRent?` | `{1..10}`, default 1 | Selects the current reference channel | 144 |
| `:REFerence<n>:ENABle <bool>` | `:REFerence<n>:ENABle?` | `{{1\|ON}\|{0\|OFF}}` | Shows/hides a reference | 142 |
| `:REFerence<n>:SOURce <source>` | `:REFerence<n>:SOURce?` | `{CHANnel1..CHANnel4\|D0..D15}`, default `CHANnel1` | Source of the reference | 143 |
| `:REFerence<n>:VSCale <scale>` | `:REFerence<n>:VSCale?` | V/div; 1X 1 mV-10 V, default 100 mV | Reference vertical scale | 143 |
| `:REFerence<n>:VOFFset <offset>` | `:REFerence<n>:VOFFset?` | ±10 × reference scale, default 0 | Reference vertical offset | 144 |
| `:REFerence<n>:COLor <color>` | `:REFerence<n>:COLor?` | `{GRAY\|GREEn\|LBLue\|MAGenta\|ORANge}`, default `GRAY` | Display colour | 145 |
| `:REFerence:DISPlay <bool>` | `:REFerence:DISPlay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Reference display master switch | 142 |

### Pass/fail mask (`:MASK`, PDF pp. 123-127)

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:MASK:ENABle <bool>` | `:MASK:ENABle?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Enables pass/fail testing | 123 |
| `:MASK:SOURce <source>` | `:MASK:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | Mask source | 124 |
| `:MASK:OPERate <oper>` | `:MASK:OPERate?` | `{RUN\|STOP}`, default `STOP` | Starts/stops the test | 124 |
| `:MASK:MDISplay <bool>` | `:MASK:MDISplay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Statistic information display | 125 |
| `:MASK:SOOutput <bool>` | `:MASK:SOOutput?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | "Stop on Fail" | 125 |
| `:MASK:OUTPut <bool>` | `:MASK:OUTPut?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Beeper on a failed waveform | 126 |
| `:MASK:X <x>` | `:MASK:X?` | div; 0.02 to 4 in 0.02 steps, default 0.02 | Horizontal mask tolerance | 126 |
| `:MASK:Y <y>` | `:MASK:Y?` | div; 0.04 to 5.12 in 0.04 steps, default 0.96 | Vertical mask tolerance | 126 |
| `:MASK:CREate` | — | none | Creates a mask from the current trace | 127 |
| `:MASK:PASSed?` | — | returns integer | Passed frames | 127 |
| `:MASK:FAILed?` | — | returns integers | Failed frames | 127 |
| `:MASK:TOTal?` | — | returns integer | Total frames | 127 |
| `:MASK:RESet` | — | none | Resets the counters | 127 |

No `*SAV`, `*RCL`, `:SAVE`, or `:RECAll` subsystem exists in this manual;
`grep` over the programming guide returns no such section.

## Cursors (`:CURSor`, PDF pp. 32-52): not implemented

> **Not implemented.** Documented in the manual but not exercised by this Skill:
> no cursor mode is set and no cursor value is read. Every row below is
> `documented` and `not implemented`.

68 commands exist. This Skill reads no cursor value and sets no cursor mode.
Every documented query has its own row: the queries the earlier revision
collapsed into `:AX? … :BYValue?` are now listed by name, so a read-only value
can be looked up without guessing which of the group it belongs to.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:CURSor:MODE <mode>` | `:CURSor:MODE?` | `{OFF\|MANual\|TRACk\|AUTO\|XY}`, default `OFF` | answered `MAN` (`hardware-verified`); not implemented | 32 |
| `:CURSor:MANual:TYPE <type>` | `:CURSor:MANual:TYPE?` | `{X\|Y}`, default `X` | not implemented | 33 |
| `:CURSor:MANual:SOURce <source>` | `:CURSor:MANual:SOURce?` | `{CHANnel1..CHANnel4\|MATH\|LA}`, default `CHANnel1` | not implemented | 34 |
| `:CURSor:MANual:TUNit <unit>` | `:CURSor:MANual:TUNit?` | `{S\|HZ\|DEGRee\|PERCent}`, default `S` | not implemented | 34 |
| `:CURSor:MANual:VUNit <unit>` | `:CURSor:MANual:VUNit?` | `{PERCent\|SOURce}`, default `SOURce` | not implemented | 35 |
| `:CURSor:MANual:AX <x>` | `:CURSor:MANual:AX?` | Integer 5 to 594, default 100 | Cursor A horizontal position | 35 |
| `:CURSor:MANual:BX <x>` | `:CURSor:MANual:BX?` | Integer 5 to 594, default 500 | Cursor B horizontal position | 36 |
| `:CURSor:MANual:AY <y>` | `:CURSor:MANual:AY?` | Integer 5 to 394, default 100 | Cursor A vertical position | 36 |
| `:CURSor:MANual:BY <y>` | `:CURSor:MANual:BY?` | Integer 5 to 394, default 300 | Cursor B vertical position | 37 |
| `:CURSor:MANual:AXValue?` | — | NR3 | Cursor A value | 37 |
| `:CURSor:MANual:AYValue?` | — | NR3 | Cursor A vertical value | 37 |
| `:CURSor:MANual:BXValue?` | — | NR3 | Cursor B value | 38 |
| `:CURSor:MANual:BYValue?` | — | NR3 | Cursor B vertical value | 38 |
| `:CURSor:MANual:XDELta?` | — | NR3 | Horizontal difference | 38 |
| `:CURSor:MANual:IXDELta?` | — | NR3 | Reciprocal of `XDELta` | 39 |
| `:CURSor:MANual:YDELta?` | — | NR3 | Vertical difference | 39 |
| `:CURSor:TRACk:SOURce1 <source>` | `:CURSor:TRACk:SOURce1?` | `{CHANnel1..CHANnel4\|MATH}`, default `CHANnel1` | not implemented | 40 |
| `:CURSor:TRACk:SOURce2 <source>` | `:CURSor:TRACk:SOURce2?` | `{CHANnel1..CHANnel4\|MATH}`, default `CHANnel1` | not implemented | 41 |
| `:CURSor:TRACk:AX <x>` | `:CURSor:TRACk:AX?` | Integer 5 to 594, default 100 | not implemented | 41 |
| `:CURSor:TRACk:BX <x>` | `:CURSor:TRACk:BX?` | Integer 5 to 594, default 500 | not implemented | 42 |
| `:CURSor:TRACk:AY?` | — | NR3 | Read-only | 42 |
| `:CURSor:TRACk:BY?` | — | NR3 | Read-only | 42 |
| `:CURSor:TRACk:AXValue?` | — | NR3, seconds | Read-only; X value of cursor A | 43 |
| `:CURSor:TRACk:AYValue?` | — | NR3, `:CHANnel<n>:UNITs` | Read-only; Y value of cursor A | 43 |
| `:CURSor:TRACk:BXValue?` | — | NR3, seconds | Read-only; X value of cursor B | 43 |
| `:CURSor:TRACk:BYValue?` | — | NR3, `:CHANnel<n>:UNITs` | Read-only; Y value of cursor B | 43 |
| `:CURSor:TRACk:XDELta?` | — | NR3, seconds | Read-only; BX - AX | 44 |
| `:CURSor:TRACk:YDELta?` | — | NR3, `:CHANnel<n>:UNITs` | Read-only; BY - AY | 44 |
| `:CURSor:TRACk:IXDELTA?` | — | NR3, Hz | Read-only; reciprocal of the absolute X difference | 44 |
| `:CURSor:AUTO:ITEM <item>` | `:CURSor:AUTO:ITEM?` | `{OFF\|ITEM1\|ITEM2\|ITEM3\|ITEM4\|ITEM5}`, default `OFF` | not implemented | 45 |
| `:CURSor:AUTO:AX?` | — | Integer 5 to 594; `4294967295` when the item needs no X cursor | Read-only, auto-cursor mode only | 46 |
| `:CURSor:AUTO:BX?` | — | Integer 5 to 594; `4294967295` when unused | Read-only | 46 |
| `:CURSor:AUTO:AY?` | — | Integer 5 to 394; `4294967295` when unused | Read-only | 46 |
| `:CURSor:AUTO:BY?` | — | Integer 5 to 394; `4294967295` when unused | Read-only | 47 |
| `:CURSor:AUTO:AXValue?` | — | NR3; `9.9E37` when the item needs no X cursor | Read-only | 47 |
| `:CURSor:AUTO:AYValue?` | — | NR3; `9.9E37` when unused | Read-only | 47 |
| `:CURSor:AUTO:BXValue?` | — | NR3; `9.9E37` when unused | Read-only | 47 |
| `:CURSor:AUTO:BYValue?` | — | NR3; `9.9E37` when unused | Read-only | 48 |
| `:CURSor:XY:AX <x>` | `:CURSor:XY:AX?` | Integer 5 to 394, default 100 | XY-mode cursor | 49 |
| `:CURSor:XY:BX <x>` | `:CURSor:XY:BX?` | Integer 5 to 394, default 300 | XY-mode cursor | 50 |
| `:CURSor:XY:AY <x>` | `:CURSor:XY:AY?` | Integer 5 to 394, default 100 | XY-mode cursor | 50 |
| `:CURSor:XY:BY <x>` | `:CURSor:XY:BY?` | Integer 5 to 394, default 300 | XY-mode cursor | 51 |
| `:CURSor:XY:AXValue?` | — | NR3, amplitude unit of the channel | Read-only; XY timebase mode only | 51 |
| `:CURSor:XY:AYValue?` | — | NR3, amplitude unit of the channel | Read-only | 51 |
| `:CURSor:XY:BXValue?` | — | NR3, amplitude unit of the channel | Read-only | 52 |
| `:CURSor:XY:BYValue?` | — | NR3, amplitude unit of the channel | Read-only | 52 |

## Math (`:MATH`, PDF pp. 106-122): not implemented

61 commands exist. This Skill never enables the math trace, so any
`:WAVeform:SOURce MATH` read is `UNSUPPORTED`; the 10 fields of a MATH preamble
would need the FFT or operator context recorded.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:MATH:DISPlay <bool>` | `:MATH:DISPlay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | answered `0` (`hardware-verified`); not implemented | 106 |
| `:MATH:OPERator <opt>` | `:MATH:OPERator?` | `{ADD\|SUBTract\|MULTiply\|DIVision\|AND\|OR\|XOR\|NOT\|FFT\|INTG\|DIFF\|SQRT\|LOG\|LN\|EXP\|ABS\|FILTer}`, default `ADD` | answered `ADD` (`hardware-verified`); not implemented | 106 |
| `:MATH:SOURce1 <src>` | `:MATH:SOURce1?` | `{CHANnel1..CHANnel4\|FX}`, default `CHANnel1` | not implemented | 107 |
| `:MATH:SOURce2 <src>` | `:MATH:SOURce2?` | `{CHANnel1..CHANnel4\|FX}`, default `CHANnel1` | not implemented | 108 |
| `:MATH:LSOUrce1 <src>` | `:MATH:LSOUrce1?` | `{D0..D15}`, default `D0` | Digital math source | 108 |
| `:MATH:LSOUrce2 <src>` | `:MATH:LSOUrce2?` | `{D0..D15}`, default `D1` | Digital math source | 109 |
| `:MATH:SCALe <scale>` | `:MATH:SCALe?` | 1 p to 5 T in 1-2-5 steps, default 1.00 V | not implemented | 109 |
| `:MATH:OFFSet <offs>` | `:MATH:OFFSet?` | default 0.00 V | not implemented | 110 |
| `:MATH:INVert <bool>` | `:MATH:INVert?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | not implemented | 110 |
| `:MATH:RESet` | — | none | Resets the math settings | 111 |
| `:MATH:FFT:SOURce <src>` | `:MATH:FFT:SOURce?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | FFT source | 111 |
| `:MATH:FFT:WINDow <wnd>` | `:MATH:FFT:WINDow?` | `{RECTangle\|BLACkman\|HANNing\|HAMMing\|FLATtop\|TRIangle}`, default `RECTangle` | FFT window | 111 |
| `:MATH:FFT:SPLit <bool>` | `:MATH:FFT:SPLit?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Split-screen FFT | 112 |
| `:MATH:FFT:UNIT <unit>` | `:MATH:FFT:UNIT?` | `{VRMS\|DB}`, default `DB` | FFT vertical unit | 112 |
| `:MATH:FFT:HSCale <hsc>` | `:MATH:FFT:HSCale?` | Hz/div, default 5 MHz | FFT horizontal scale | 113 |
| `:MATH:FFT:HCENter <cent>` | `:MATH:FFT:HCENter?` | Hz, default 5 MHz | FFT centre frequency | 114 |
| `:MATH:FFT:MODE <mode>` | `:MATH:FFT:MODE?` | `{TRACe\|MEMory}`, default `TRACe` | FFT source freshness | 114 |
| `:MATH:FILTer:TYPE <type>` | `:MATH:FILTer:TYPE?` | `{LPASs\|HPASs\|BPASs\|BSTOP}`, default `LPASs` | Digital filter type | 115 |
| `:MATH:FILTer:W1 <freq1>` | `:MATH:FILTer:W1?` | Hz, range per PDF p. 116 | Filter width 1 | 116 |
| `:MATH:FILTer:W2 <freq2>` | `:MATH:FILTer:W2?` | Hz, default 0.1 × screen sample rate | Filter width 2 | 117 |
| `:MATH:OPTion:STARt <sta>` | `:MATH:OPTion:STARt?` | Integer 0 to (end-1), default 0 | Logic-analyzer option window | 117 |
| `:MATH:OPTion:END <end>` | `:MATH:OPTion:END?` | Integer (start+1) to 1199, default 1199 | Logic-analyzer option window | 118 |
| `:MATH:OPTion:INVert <bool>` | `:MATH:OPTion:INVert?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | not implemented | 118 |
| `:MATH:OPTion:SENSitivity <sens>` | `:MATH:OPTion:SENSitivity?` | 0 to 0.96 in 0.08 steps, default 0 | not implemented | 119 |
| `:MATH:OPTion:DIStance <dist>` | `:MATH:OPTion:DIStance?` | Integer 3 to 201, default 3 | not implemented | 119 |
| `:MATH:OPTion:ASCale <bool>` | `:MATH:OPTion:ASCale?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Auto scale for the math option | 120 |
| `:MATH:OPTion:THReshold1 <thre>` | `:MATH:OPTion:THReshold1?` | V, default 0.00 V | not implemented | 120 |
| `:MATH:OPTion:THReshold2 <thre>` | `:MATH:OPTion:THReshold2?` | V, default 0.00 V | not implemented | 121 |
| `:MATH:OPTion:FX:SOURce1 <src>` | `:MATH:OPTion:FX:SOURce1?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 121 |
| `:MATH:OPTion:FX:SOURce2 <src>` | `:MATH:OPTion:FX:SOURce2?` | `{CHANnel1..CHANnel4}`, default `CHANnel1` | not implemented | 122 |
| `:MATH:OPTion:FX:OPERator <op>` | `:MATH:OPTion:FX:OPERator?` | `{ADD\|SUBTract\|MULTiply\|DIVision}`, default `ADD` | not implemented | 122 |

## Digital channels, decoding, recording, and signal source: not implemented

### Digital channels (`:LA`, PDF pp. 98-104)

> **Not implemented.** Applies only to MSO1000Z and DS1000Z Plus models with the
> MSO upgrade (PDF p. 17, note 2); no digital channel was exercised on the
> DS1074Z. Every row is `documented`.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:LA:ACTive {<digital>\|<group>\|NONE}` | `:LA:ACTive?` | `<digital>` = D0..D15; `<group>` = `{GROUP1\|GROUP2\|GROUP3\|GROUP4}`; `NONE` clears the selection | Selects the active channel/group for the cursor and label operations | 98 |
| `:LA:AUTosort <n>` | `:LA:AUTosort?` | `{0\|1}`, default `1` | `0` = D15..D0 top-to-bottom, `1` = D0..D15 | 98 |
| `:LA:DIGital<n>:DISPlay <bool>` | `:LA:DIGital<n>:DISPlay?` | `<n>` 0..15; `{{1\|ON}\|{0\|OFF}}` | Show or hide one digital channel | 99 |
| `:LA:DIGital<n>:POSition <position>` | `:LA:DIGital<n>:POSition?` | `<n>` 0..15; `<position>` integer | Vertical position of one digital channel | 100 |
| `:LA:DIGital<n>:LABel <label>` | `:LA:DIGital<n>:LABel?` | `<n>` 0..15; string label | Channel label shown on screen | 100 |
| `:LA:DISPlay {<digital>\|<group>\|<pod>},<bool>` | `:LA:DISPlay? {<digital>\|<group>\|<pod>}` | `<group>` = `{GROUP1..GROUP4}`, `<pod>` = `{POD1\|POD2}`, `<bool>` = `{{1\|ON}\|{0\|OFF}}` | Bulk show/hide for a channel, group or pod | 101 |
| `:LA:POD<n>:DISPlay <bool>` | `:LA:POD<n>:DISPlay?` | `<n>` 1..2; `<bool>` = `{{1\|ON}\|{0\|OFF}}` | Show or hide a pod | 102 |
| `:LA:POD<n>:THReshold <thre>` | `:LA:POD<n>:THReshold?` | `<n>` 1..2; `-15.0 V` to `+15.0 V`, default `1.40 V` | Logic threshold of a pod | 102 |
| `:LA:SIZE <size>` | `:LA:SIZE?` | `{SMALl\|LARGe}`, default `SMALl` | Waveform display height of the digital channels | 103 |
| `:LA:STATe <bool>` | `:LA:STATe?` | `{{1\|ON}\|{0\|OFF}}`, default `0\|OFF` | Enables the logic analyser | 103 |
| `:LA:TCALibrate <tcal>` | `:LA:TCALibrate?` | Real, `-100 ns` to `100 ns`, default `0.00 s`; step depends on the timebase (100 ps at 5 ns/div) | Delay calibration of the digital channels | 104 |

### Protocol decoding (`:DECoder<n>`, PDF pp. 53-77)

> **Not implemented.** Documented in the manual but not exercised by this Skill:
> `:DECoder` and `:ETABle` are decoder subsystems whose digital sources need MSO
> channels (`UART`/`IIC`/`SPI` decoding are licensed options), `:FUNCtion` is the
> waveform record/playback option (PDF p. 87), not the `-S` signal source.
> Model/option dependent.

`<n>` is `{1|2}` for every command below. 47 commands, 93 settable or
queryable forms (the page index counts one more: the `:DECoder<n>:PARallel`
sub-heading at PDF p. 72, which has no syntax of its own).
Sources may be analog `CHANnel1..4` or digital `D0..D15`; only the digital
sources need the MSO upgrade (PDF p. 17, note 2). Every row is `documented` and
`not implemented`: read from the manual, never sent by this Skill. There is **no
CAN and no LIN decoder** in this manual, and no `:DECoder<n>:BUS` command.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:DECoder<n>:MODE <mode>` | `:DECoder<n>:MODE?` | `{PARallel\|UART\|SPI\|IIC}`, default `PARallel` | UART/IIC/SPI are licensed options; parallel decoding is standard | 53 |
| `:DECoder<n>:DISPlay <bool>` | `:DECoder<n>:DISPlay?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Turns the decoder on; `:ETABle<n>:*` is only valid when this is on | 54 |
| `:DECoder<n>:FORMat <fmt>` | `:DECoder<n>:FORMat?` | `{HEX\|ASCii\|DEC\|BIN\|LINE}`, default `ASCii` | `LINE` is valid only for serial buses with LSB/MSB endian | 54 |
| `:DECoder<n>:POSition <pos>` | `:DECoder<n>:POSition?` | Integer 50 to 350, default 350 (decoder 1) / 300 (decoder 2) | Vertical position of the bus, 0 = top of the 400-part screen | 55 |
| `:DECoder<n>:THREshold:CHANnel1 <thre>` | `:DECoder<n>:THREshold:CHANnel1?` | V; -4 x vertical scale - offset to 4 x vertical scale - offset; no default | Manual threshold of analog channel 1 | 56 |
| `:DECoder<n>:THREshold:CHANnel2 <thre>` | `:DECoder<n>:THREshold:CHANnel2?` | as `:THREshold:CHANnel1` | Manual threshold of analog channel 2 | 56 |
| `:DECoder<n>:THREshold:CHANnel3 <thre>` | `:DECoder<n>:THREshold:CHANnel3?` | as `:THREshold:CHANnel1` | Manual threshold of analog channel 3 | 56 |
| `:DECoder<n>:THREshold:CHANnel4 <thre>` | `:DECoder<n>:THREshold:CHANnel4?` | as `:THREshold:CHANnel1` | Manual threshold of analog channel 4 | 56 |
| `:DECoder<n>:THREshold:AUTO <bool>` | `:DECoder<n>:THREshold:AUTO?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Must be `OFF` before the per-channel thresholds take effect | 57 |
| `:DECoder<n>:CONFig:LABel <bool>` | `:DECoder<n>:CONFig:LABel?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Show the bus label | 57 |
| `:DECoder<n>:CONFig:LINE <bool>` | `:DECoder<n>:CONFig:LINE?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Show the bus line | 58 |
| `:DECoder<n>:CONFig:FORMat <bool>` | `:DECoder<n>:CONFig:FORMat?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Show the display format | 58 |
| `:DECoder<n>:CONFig:ENDian <bool>` | `:DECoder<n>:CONFig:ENDian?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Invalid in parallel decoding | 59 |
| `:DECoder<n>:CONFig:WIDth <bool>` | `:DECoder<n>:CONFig:WIDth?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Show the width of every frame | 59 |
| `:DECoder<n>:CONFig:SRATe?` | — | returns NR3, Sa/s | Sample rate of the decoded data; follows the timebase while the data source is `TRACe` | 59 |
| `:DECoder<n>:UART:TX <tx>` | `:DECoder<n>:UART:TX?` | `{D0..D15\|CHANnel1..CHANnel4\|OFF}`, default `CHANnel1` | TX and RX cannot both be `OFF` | 60 |
| `:DECoder<n>:UART:RX <rx>` | `:DECoder<n>:UART:RX?` | `{D0..D15\|CHANnel1..CHANnel4\|OFF}`, default `OFF` | TX and RX cannot both be `OFF` | 61 |
| `:DECoder<n>:UART:POLarity <pol>` | `:DECoder<n>:UART:POLarity?` | `{NEGative\|POSitive}`, default `POSitive` | RS232 itself uses negative polarity | 61 |
| `:DECoder<n>:UART:ENDian <endian>` | `:DECoder<n>:UART:ENDian?` | `{LSB\|MSB}`, default `LSB` | — | 62 |
| `:DECoder<n>:UART:BAUD <baud>` | `:DECoder<n>:UART:BAUD?` | Integer 110 to 20M, bps, default 9600 | — | 62 |
| `:DECoder<n>:UART:WIDTh <wid>` | `:DECoder<n>:UART:WIDTh?` | Integer 5 to 8, default 8 | Data bits per frame | 62 |
| `:DECoder<n>:UART:STOP <stop>` | `:DECoder<n>:UART:STOP?` | `{1\|1.5\|2}`, default 1 | — | 63 |
| `:DECoder<n>:UART:PARity <parity>` | `:DECoder<n>:UART:PARity?` | `{NONE\|EVEN\|ODD}`, default `NONE` | — | 63 |
| `:DECoder<n>:IIC:CLK <clk>` | `:DECoder<n>:IIC:CLK?` | `{D0..D15\|CHANnel1..CHANnel4}`, default `CHANnel1` | SCL source | 64 |
| `:DECoder<n>:IIC:DATA <dat>` | `:DECoder<n>:IIC:DATA?` | `{D0..D15\|CHANnel1..CHANnel4}`, default `CHANnel2` | SDA source | 64 |
| `:DECoder<n>:IIC:ADDRess <addr>` | `:DECoder<n>:IIC:ADDRess?` | `{NORMal\|RW}`, default `NORMal` | Whether `:TRIGger:IIC:AWIDth` includes the R/W bit | 65 |
| `:DECoder<n>:SPI:CLK <clk>` | `:DECoder<n>:SPI:CLK?` | `{D0..D15\|CHANnel1..CHANnel4}`, default `CHANnel1` | SCLK source | 66 |
| `:DECoder<n>:SPI:MISO <miso>` | `:DECoder<n>:SPI:MISO?` | `{D0..D15\|CHANnel1..CHANnel4\|OFF}`, default `CHANnel2` | MISO and MOSI cannot both be `OFF` | 67 |
| `:DECoder<n>:SPI:MOSI <mosi>` | `:DECoder<n>:SPI:MOSI?` | `{D0..D15\|CHANnel1..CHANnel4\|OFF}`, default `CHANnel2` | MISO and MOSI cannot both be `OFF` | 67 |
| `:DECoder<n>:SPI:CS <cs>` | `:DECoder<n>:SPI:CS?` | `{D0..D15\|CHANnel1..CHANnel4}`, default `CHANnel3` | Valid only in `:DECoder<n>:SPI:MODE CS` | 68 |
| `:DECoder<n>:SPI:SELect <CsNcs>` | `:DECoder<n>:SPI:SELect?` | `{NCS\|CS}`, default `NCS` | CS polarity; valid only in CS mode | 68 |
| `:DECoder<n>:SPI:MODE <CsTmo>` | `:DECoder<n>:SPI:MODE?` | `{CS\|TIMeout}`, default `TIMeout` | Frame-synchronisation source; chooses which of `:CS`/`:TIMeout` applies | 69 |
| `:DECoder<n>:SPI:TIMeout <tmo>` | `:DECoder<n>:SPI:TIMeout?` | Real, seconds, default `1.00us` | Must exceed the longest clock pulse and stay below the inter-frame idle time | 69 |
| `:DECoder<n>:SPI:POLarity <pol>` | `:DECoder<n>:SPI:POLarity?` | `{NEGative\|POSitive}`, default `POSitive` | Polarity of the SDA data line | 70 |
| `:DECoder<n>:SPI:EDGE <edge>` | `:DECoder<n>:SPI:EDGE?` | `{RISE\|FALL}`, default `RISE` | Clock edge that samples the data line | 70 |
| `:DECoder<n>:SPI:ENDian <endian>` | `:DECoder<n>:SPI:ENDian?` | `{LSB\|MSB}`, default `MSB` | — | 70 |
| `:DECoder<n>:SPI:WIDTh <wid>` | `:DECoder<n>:SPI:WIDTh?` | Integer 8 to 32, default 8 | Bits per frame | 71 |
| `:DECoder<n>:PARallel:CLK <clk>` | `:DECoder<n>:PARallel:CLK?` | `{D0..D15\|CHANnel1..CHANnel4\|OFF}`, default `CHANnel1` | `OFF` means the instrument samples on data transitions | 72 |
| `:DECoder<n>:PARallel:EDGE <edge>` | `:DECoder<n>:PARallel:EDGE?` | `{RISE\|FALL\|BOTH}`, default `RISE` | Sampling edge of the clock channel | 73 |
| `:DECoder<n>:PARallel:WIDTh <wid>` | `:DECoder<n>:PARallel:WIDTh?` | Integer 1 to 16, default 8 | Data bits per frame; feed `:BITX`/`:SOURce` afterwards | 73 |
| `:DECoder<n>:PARallel:BITX <bit>` | `:DECoder<n>:PARallel:BITX?` | Integer 0 to (data width - 1), default 0 | Selects the bit that `:DECoder<n>:PARallel:SOURce` addresses | 74 |
| `:DECoder<n>:PARallel:SOURce <src>` | `:DECoder<n>:PARallel:SOURce?` | `{D0..D15\|CHANnel1..CHANnel4}`, default follows the selected bit | Channel source of the bit chosen by `:DECoder<n>:PARallel:BITX` | 74 |
| `:DECoder<n>:PARallel:POLarity <pol>` | `:DECoder<n>:PARallel:POLarity?` | `{NEGative\|POSitive}`, default `POSitive` | Data polarity | 75 |
| `:DECoder<n>:PARallel:NREJect <bool>` | `:DECoder<n>:PARallel:NREJect?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Drops pulses shorter than `:DECoder<n>:PARallel:NRTime` | 75 |
| `:DECoder<n>:PARallel:NRTime <time>` | `:DECoder<n>:PARallel:NRTime?` | Real, seconds 0.00 to 100 ms, default 0.00 | Needs `:DECoder<n>:PARallel:NREJect ON` first | 76 |
| `:DECoder<n>:PARallel:CCOMpensation <comp>` | `:DECoder<n>:PARallel:CCOMpensation?` | Real, seconds -100 ms to 100 ms, default 0.00 | Invalid when `:PARallel:CLK` is `OFF` | 76 |
| `:DECoder<n>:PARallel:PLOT <bool>` | `:DECoder<n>:PARallel:PLOT?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Draws the bus data as a vector diagram | 77 |

### Decoding event table (`:ETABle<n>`, PDF pp. 83-86)

> **Not implemented.** Documented in the manual but not exercised by this Skill:
> `:DECoder` and `:ETABle` are decoder subsystems whose digital sources need MSO
> channels (`UART`/`IIC`/`SPI` decoding are licensed options), `:FUNCtion` is the
> waveform record/playback option (PDF p. 87), not the `-S` signal source.
> Model/option dependent.

`<n>` is `{1|2}`. 7 commands, 13 command forms. Every row is `documented` and
`not implemented`. The table only lists decoded bus data, so `:ETABle<n>:DISP`
needs a decoder that is switched on (`:DECoder<n>:DISPlay`, PDF p. 83).

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:ETABle<n>:DISP <bool>` | `:ETABle<n>:DISP?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Valid only when `:DECoder<n>:DISPlay` is on | 83 |
| `:ETABle<n>:FORMat <fmt>` | `:ETABle<n>:FORMat?` | `{HEX\|ASCii\|DEC}`, default `HEX` | — | 83 |
| `:ETABle<n>:VIEW <view>` | `:ETABle<n>:VIEW?` | `{PACKage\|DETail\|PAYLoad}`, default `PACKage` | `DETail`/`PAYLoad` show the row/column selected by `:ROW`/`:COLumn` | 84 |
| `:ETABle<n>:COLumn <col>` | `:ETABle<n>:COLumn?` | `{DATA\|TX\|RX\|MISO\|MOSI}`, no default | Which columns exist depends on `:DECoder<n>:MODE`; a source set to `OFF` cannot be selected | 84 |
| `:ETABle<n>:ROW <row>` | `:ETABle<n>:ROW?` | Integer 1 to the number of rows in the current table, default 1 | The query returns `0` when the table is empty | 85 |
| `:ETABle<n>:SORT <sort>` | `:ETABle<n>:SORT?` | `{ASCend\|DESCend}`, default `ASCend` | Order of the decoded events | 85 |
| `:ETABle<n>:DATA?` | — | TMC block (`#900000dddd` + data) | Reads the table; the frame layout is a figure in the manual, not text | 86 |

### Waveform record and playback (`:FUNCtion`, PDF pp. 87-94)

> **Not implemented.** Documented in the manual but not exercised by this Skill:
> `:DECoder` and `:ETABle` are decoder subsystems whose digital sources need MSO
> channels (`UART`/`IIC`/`SPI` decoding are licensed options), `:FUNCtion` is the
> waveform record/playback option (PDF p. 87), not the `-S` signal source.
> Model/option dependent.

14 commands, 26 command forms. The manual heads this section ":FUNCtion Commands
(Option)" (PDF p. 87): it records frames into instrument memory and replays
them. Every row is `documented` and `not implemented`. `:WRECord:ENABle` needs
timebase mode `YT` and a timebase below 200 ms (PDF p. 89), and while recording
is enabled or a recording is playing, `:AUToscale`, `:RUN` and `:STOP` are
refused (PDF p. 18).

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:FUNCtion:WRECord:FEND <frame>` | `:FUNCtion:WRECord:FEND?` | Integer 1 to the current maximum, default 5000 | End frame of the recording | 87 |
| `:FUNCtion:WRECord:FMAX?` | — | returns integer, frames | Read-only; ceiling falls as the memory depth rises | 88 |
| `:FUNCtion:WRECord:FINTerval <interval>` | `:FUNCtion:WRECord:FINTerval?` | Real, seconds 100 ns to 10 s, default 100 ns | Interval between recorded frames | 88 |
| `:FUNCtion:WRECord:PROMpt <bool>` | `:FUNCtion:WRECord:PROMpt?` | `{{1\|ON}\|{0\|OFF}}`, default `1` | Sound when the recording finishes, independent of `:SYSTem:BEEPer` | 88 |
| `:FUNCtion:WRECord:OPERate <opt>` | `:FUNCtion:WRECord:OPERate?` | `{RUN\|STOP}`, no default | Needs `:WRECord:ENABle ON` first | 89 |
| `:FUNCtion:WRECord:ENABle <bool>` | `:FUNCtion:WRECord:ENABle?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Needs timebase mode `YT` and a timebase below 200 ms | 89 |
| `:FUNCtion:WREPlay:FSTart <sta>` | `:FUNCtion:WREPlay:FSTart?` | Integer 1 to the frames recorded, default 1 | Cannot exceed `:WREPlay:FEND`; only while a recording exists and playback is idle | 90 |
| `:FUNCtion:WREPlay:FEND <end>` | `:FUNCtion:WREPlay:FEND?` | Integer 1 to the frames recorded, default = frames recorded | Cannot be below `:WREPlay:FSTart` | 91 |
| `:FUNCtion:WREPlay:FMAX?` | — | returns integer, frames | Read-only; equals the frames recorded | 91 |
| `:FUNCtion:WREPlay:FINTerval <interval>` | `:FUNCtion:WREPlay:FINTerval?` | Real, seconds 100 ns to 10 s, default 100 ns | Interval between played frames | 92 |
| `:FUNCtion:WREPlay:MODE <mode>` | `:FUNCtion:WREPlay:MODE?` | `{REPeat\|SINGle}`, default `SINGle` | Cycle or one-shot playback | 92 |
| `:FUNCtion:WREPlay:DIRection <dir>` | `:FUNCtion:WREPlay:DIRection?` | `{FORWard\|BACKward}`, default `FORWard` | Playback direction | 93 |
| `:FUNCtion:WREPlay:OPERate <opt>` | `:FUNCtion:WREPlay:OPERate?` | `{PLAY\|PAUSe\|STOP}`, default `STOP` | Only valid once a waveform has been recorded | 93 |
| `:FUNCtion:WREPlay:FCURrent <cur>` | `:FUNCtion:WREPlay:FCURrent?` | Integer 1 to the frames recorded, default = frames recorded | Current frame during playback | 94 |

### Signal source (`[:SOURce[<n>]]`, PDF pp. 146-157)

> **Not implemented.** The built-in signal source exists only on `-S`/Plus
> models (PDF p. 146: "only applicable to models with source channels of
> MSO1000Z/DS1000Z series"); no command here was exercised on `DS1074Z`.
> Model/option dependent.

25 commands, 42 command forms. Every row is `documented` and `not implemented`.
`[:SOURce[<n>]]` and both `[<n>]` arguments are optional and fall back to source
1 (PDF p. 147). This subsystem does **not**
appear in `artifacts/rigol-ds1000z/command-pages.tsv` (that file only lists
forms beginning with `:`), so the rows below were read from the manual pages.
`[:TRACe[<n>]]` (PDF pp. 164-168) edits the volatile waveform memory of the
same source and is tabulated in the next section.

### Volatile waveform memory (`[:TRACe[<n>]]`, PDF pp. 164-168)

> **Not implemented.** Needs the built-in signal source of `-S`/Plus models; no
> command here was exercised on `DS1074Z`. Every row is `documented`.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `[:TRACe[<n>]]:DATA volatile,<value>[,<value>...]` | — | `<n>` = `{1\|2}`, default 1; `<value>` Real `-1` to `1` | Downloads floating-point voltages into the volatile memory | 164 |
| `[:TRACe[<n>]]:DATA:DAC16 volatile,<flag>,<binary_block_data>` | — | `<flag>` = `{END}`; 16-bit binary block | Downloads a 16-bit block (two bytes per point) | 165 |
| `[:TRACe[<n>]]:DATA:DAC volatile,[<binary_block_data>\|<value>,<value>...]` | — | `<value>` Integer `0` to `16383` | Decimal or binary download; switches the source to the volatile waveform | 166 |
| `[:TRACe[<n>]]:DATA:POINts volatile,<data>` | `[:TRACe[<n>]]:DATA:POINts? volatile` | `<data>` Integer `1` to `16384`, default `2` | Initial number of points; re-initialises every point to the offset value | 167 |
| `[:TRACe[<n>]]:DATA:POINts:INTerpolate <mode>` | `[:TRACe[<n>]]:DATA:POINts:INTerpolate?` | `{LINear\|OFF}`, default `OFF`; query returns `LIN` or `OFF` | Linear interpolation between downloaded points | 167 |
| `[:TRACe[<n>]]:DATA:VALue volatile,<points>,<data>` | `[:TRACe[<n>]]:DATA:VALue? volatile,<points>` | `<points>` Integer `1..` the initial number of points; `<data>` Integer `0` to `16383` | Modify or query one point of the volatile memory | 168 |
| `[:TRACe[<n>]]:DATA:LOAD?` | query only | returns the load state | Reports whether a download is in progress | 168 |

PDF p. 151 prints a stray space inside the offset command
(`:VOLTage[:LEVel] [:IMMediate]:OFFSet`); the sent form carries none.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `[:SOURce[<n>]]:OUTPut[<n>][:STATe] <bool>` | `[:SOURce[<n>]]:OUTPut[<n>][:STATe]?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | Output relay of the selected source channel | 147 |
| `[:SOURce[<n>]]:OUTPut[<n>]:IMPedance <impedance>` | `[:SOURce[<n>]]:OUTPut[<n>]:IMPedance?` | `{OMEG\|FIFTy}`, default `OMEG` | `OMEG` = high-Z, `FIFTy` = 50 ohm | 147 |
| `[:SOURce[<n>]]:FREQuency[:FIXed] <frequency>` | `[:SOURce[<n>]]:FREQuency[:FIXed]?` | Real, Hz, default 1 kHz; sine 0.1 Hz to 25 MHz, square to 15 MHz, pulse to 1 MHz, ramp to 100 kHz, arb to 10 MHz | Carrier frequency while modulation is on | 148 |
| `[:SOURce[<n>]]:PHASe[:ADJust] <phase>` | `[:SOURce[<n>]]:PHASe[:ADJust]?` | Real, degrees 0 to 360, default 0 | — | 148 |
| `[:SOURce[<n>]]:PHASe:INITiate` | — | none | Aligns the phase of the two source channels | 149 |
| `[:SOURce[<n>]]:FUNCtion[:SHAPe] <wave>` | `[:SOURce[<n>]]:FUNCtion[:SHAPe]?` | `{SINusoid\|SQUare\|RAMP\|PULSe\|NOISe\|DC\|EXTernal\|SINC\|EXPRise\|EXPFall\|ECG\|GAUSs\|LORentz\|HAVersine}`, default `SINusoid` | `EXTernal` means arbitrary; selecting pulse/noise/DC turns modulation off | 149 |
| `[:SOURce[<n>]]:FUNCtion:RAMP:SYMMetry <val>` | `[:SOURce[<n>]]:FUNCtion:RAMP:SYMMetry?` | Real, percent 0 to 100, default 10 | Rising-ramp share of the whole period | 150 |
| `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate][:AMPLitude] <Amplitude>` | `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate][:AMPLitude]?` | Real, Vpp, default 5 Vpp; high-Z 20 mVpp to 5 Vpp, 50 ohm 10 mVpp to 2.5 Vpp | Range follows `:OUTPut<[n]>:IMPedance` | 150 |
| `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate]:OFFSet <offset>` | `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate]:OFFSet?` | Real, VDC, default 0; high-Z (-2.5 V + amp/2) to (2.5 V - amp/2), 50 ohm half of that | Range follows the impedance and the current amplitude | 151 |
| `[:SOURce[<n>]]:PULSe:DCYCle <percent>` | `[:SOURce[<n>]]:PULSe:DCYCle?` | Real, percent 10 to 90, default 20 | High-level share of the pulse period | 151 |
| `[:SOURce[<n>]]:MOD[:STATe] <bool>` | `[:SOURce[<n>]]:MOD[:STATe]?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | AM/FM modulation; carrier may not be noise or DC | 152 |
| `[:SOURce[<n>]]:MOD:TYPe <type>` | `[:SOURce[<n>]]:MOD:TYPe?` | `{AM\|FM}`, default `AM` | — | 152 |
| `[:SOURce[<n>]]:MOD:AM[:DEPTh] <depth>` | `[:SOURce[<n>]]:MOD:AM[:DEPTh]?` | Real, percent 0 to 120, default 100 | Above 100 % the envelope distorts | 153 |
| `[:SOURce[<n>]]:MOD:AM:INTernal:FREQuency <frequency>` | `[:SOURce[<n>]]:MOD:AM:INTernal:FREQuency?` | Real, Hz 1 to 50 kHz, default 1 kHz | Modulating frequency | 153 |
| `[:SOURce[<n>]]:MOD:FM:INTernal:FREQuency <frequency>` | `[:SOURce[<n>]]:MOD:FM:INTernal:FREQuency?` | Real, Hz 1 to 50 kHz, default 1 kHz | Modulating frequency | 153 |
| `[:SOURce[<n>]]:MOD:AM:INTernal:FUNCtion <wave>` | `[:SOURce[<n>]]:MOD:AM:INTernal:FUNCtion?` | `{SINusoid\|SQUare\|TRIangle\|NOISe}`, default `SINusoid` | — | 154 |
| `[:SOURce[<n>]]:MOD:FM:INTernal:FUNCtion <wave>` | `[:SOURce[<n>]]:MOD:FM:INTernal:FUNCtion?` | `{SINusoid\|SQUare\|TRIangle\|NOISe}`, default `SINusoid` | — | 154 |
| `[:SOURce[<n>]]:MOD:FM[:DEVIation] <dev>` | `[:SOURce[<n>]]:MOD:FM[:DEVIation]?` | Real, Hz 0 to the carrier frequency, default 1 kHz | Only settable while `:MOD:TYPe` is `FM` | 155 |
| `[:SOURce[<n>]]:APPLy?` | — | returns `<wave>,<freq>,<amp>,<offset>,<phase>` | Read-only snapshot; missing values come back as `DEF` | 155 |
| `[:SOURce[<n>]]:APPLy:NOISe [<amp>[,<offset>]]` | — | Real; amp 20 mVpp to 5 Vpp high-Z, offset as `:VOLTage:OFFSet` | Configure and emit a noise waveform | 156 |
| `[:SOURce[<n>]]:APPLy:PULSe [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | freq 0.1 Hz to 1 MHz, phase 0 to 360 deg | Configure and emit a pulse waveform | 156 |
| `[:SOURce[<n>]]:APPLy:RAMP [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | freq 0.1 Hz to 100 kHz, phase 0 to 360 deg | Configure and emit a ramp waveform | 156 |
| `[:SOURce[<n>]]:APPLy:SINusoid [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | freq 0.1 Hz to 25 MHz, phase 0 to 360 deg | Configure and emit a sine waveform | 156 |
| `[:SOURce[<n>]]:APPLy:SQUare [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | freq 0.1 Hz to 15 MHz, phase 0 to 360 deg | Configure and emit a square waveform | 156 |
| `[:SOURce[<n>]]:APPLy:USER [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | freq 0.1 Hz to 10 MHz, phase 0 to 360 deg | Configure and emit the arbitrary waveform in volatile memory | 156 |

## Verification note

This index is generated from `artifacts/rigol-ds1000z/command-pages.tsv`, which
maps each command to the PDF physical page it was found on, and from the page
text of the *MSO1000Z/DS1000Z Programming Guide* (PGA19108-1110). The
`[:SOURce[<n>]]` table was transcribed from PDF pp. 146-157 by hand because
that index only carries forms that begin with `:`. A page number here is a
starting point for a manual lookup, not proof that the firmware accepts the
command: on `00.04.02.SP4` documented commands do answer `command error` (see
the lists above), so check `:SYSTem:ERRor?` instead of trusting the manual.
