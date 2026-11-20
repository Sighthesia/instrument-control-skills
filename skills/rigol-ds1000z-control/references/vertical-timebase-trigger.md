# Vertical, Timebase, and Trigger (DS1000Z)

Load this reference when you are about to set or read back a channel, the horizontal
timebase, or the trigger, and you need the accepted parameter names, units, and
ranges before sending a write.

Command syntax, ranges, and page numbers come from the *MSO1000Z/DS1000Z
Programming Guide*, PGA19108-1110, Software Version 00.04.03.SP2 (PDF physical
pages). Values marked `hardware-verified` were read back from the evidence unit
`RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4` over raw TCP 5555
(`artifacts/rigol-ds1000z/hardware-evidence.md`). Everything else is
`documented` and untested on that firmware.

## Unit handling

The Programming Guide states that setting commands "can only accept numbers and
set the parameters using the default units; it cannot recognize the units sent
with the parameters" (PDF p. 17, note 3). Send bare numbers in the command's
default unit. The firmware enforces this: `:ACQuire:MDEPth 12K` is rejected with
`-220,"Parameter error"` while `:ACQuire:MDEPth 12000` is accepted
(`hardware-verified`). Replies are NR3 scientific notation
(`5.000000e-01`), except where the manual documents an integer or a discrete
string.

## Channel commands (`:CHANnel<n>:`, PDF pp. 25-31)

`<n>` is `{1|2|3|4}` on every DS1000Z model; this Skill does not send digital
channels.

| Command | Parameter | Range / default | Unit | Page |
|---|---|---|---|---|
| `:CHANnel<n>:SCALe <scale>` / `?` | Real | 1X probe: 1 mV to 10 V; 10X probe: 10 mV to 100 V; default 1 V at 10X | V/div | 30 |
| `:CHANnel<n>:OFFSet <offset>` / `?` | Real | 1X, scale ≥ 500 mV/div: -100 V to +100 V; 1X, scale < 500 mV/div: -2 V to +2 V; 10X doubles both; default 0 V | V | 27 |
| `:CHANnel<n>:COUPling <coupling>` / `?` | Discrete | `{AC\|DC\|GND}`, default `DC` | — | 26 |
| `:CHANnel<n>:PROBe <atten>` / `?` | Discrete | `{0.01\|0.02\|0.05\|0.1\|0.2\|0.5\|1\|2\|5\|10\|20\|50\|100\|200\|500\|1000}`, default 10 | ratio | 30 |
| `:CHANnel<n>:BWLimit <type>` / `?` | Discrete | `{20M\|OFF}`, default `OFF` | — | 25 |
| `:CHANnel<n>:INVert <bool>` / `?` | Bool | `{{1\|ON}\|{0\|OFF}}`, default `0` | — | 27 |
| `:CHANnel<n>:DISPlay <bool>` / `?` | Bool | `{{1\|ON}\|{0\|OFF}}`; default `1` for CH1, `0` for CH2-CH4 | — | 26 |
| `:CHANnel<n>:UNITs <units>` / `?` | Discrete | `{VOLTage\|WATT\|AMPere\|UNKNown}`, default `VOLTage` | — | 31 |
| `:CHANnel<n>:VERNier <bool>` / `?` | Bool | `{{1\|ON}\|{0\|OFF}}`, default `0` | — | 31 |
| `:CHANnel<n>:TCAL <val>` / `?` | Real | -100 ns to 100 ns, default 0 s | s | 29 |
| `:CHANnel<n>:RANGe <range>` / `?` | Real | 1X: 8 mV to 80 V; 10X: 80 mV to 800 V; scale = range/8 | V | 28 |

Discrete queries echo the short form: `AC`, `DC`, `GND`; `20M` or `OFF`; `VOLT`,
`WATT`, `AMP`, `UNKN`; `1` or `0` for booleans (PDF pp. 25-31).

Notes that change how a write behaves:

- **There is no `:CHANnel<n>:POSition`.** Vertical position is the offset only.
  `:CHANnel1:POSition?` returns `command error` on `00.04.02.SP4`
  (`hardware-verified`) because the manual never defines it; a script written
  for another Rigol family that uses `POSition` silently fails here. Use
  `:CHANnel<n>:OFFSet` and read the value back.
- `SCALe` and `OFFSet` interact with `PROBe`. Set `PROBe` to match the physical
  probe first, then `SCALe`; otherwise the accepted range is the wrong one
  (`documented`, PDF pp. 27, 30).
- With `VERNier OFF` the scale is restricted to the 1-2-5 sequence; with
  `VERNier ON` intermediate values are accepted (`documented`, PDF p. 31). The
  evidence unit read back `:CHANnel1:VERnier?` = `1` while `:CHANnel1:SCALe?` was
  `5.000000e-01` (`hardware-verified`), so fine adjust can be on while the scale
  still looks like a 1-2-5 step. Read `VERNier` before assuming a scale write
  landed on an exact 1-2-5 value, and record it with the capture.
- `TCAL` is not a user calibration: it is a per-channel zero-delay trim, and the
  manual states it **cannot be adjusted at all when the horizontal timebase is
  10 µs/div or larger** (PDF p. 29). The evidence unit read `:CHANnel1:TCAL?` =
  `0.000000e+00` at a 200 µs/div timebase, which is the documented behaviour and
  not evidence of calibration (`hardware-verified`).
- `COUPling GND` blocks both DC and AC (PDF p. 26). A flat trace in `GND` is a
  configuration artefact, never a 0 V reading.
- `INVert ON` flips the displayed and measured values of that channel without
  changing the trigger source polarity (`documented`, PDF p. 27).
- `BWLimit 20M` attenuates content above 20 MHz and lowers noise; it changes
  rise time, so record it with any timing measurement (`documented`, PDF p. 25).
- `UNITs` changes the amplitude display unit; other amplitude commands and
  `:TRIGger:EDGe:LEVel` then use that unit, not volts (`documented`, PDF p. 31).

Configuration of the evidence unit at capture time (`hardware-verified`):

```text
:CHANnel1:SCALe?   5.000000e-01    0.5 V/div
:CHANnel1:OFFSet?  -1.520000e+00   -1.52 V
:CHANnel1:COUPling? DC
:CHANnel1:PROBe?   1.000000e+00    1X
:CHANnel1:BWLimit? OFF
:CHANnel1:DISPlay? 1   (:CHANnel2..4:DISPlay? = 0, 0, 0)
:CHANnel1:VERnier? 1
:CHANnel1:TCAL?    0.000000e+00
```

## Timebase (`:TIMebase`, PDF pp. 169-173)

| Command | Parameter | Range / default | Unit | Page |
|---|---|---|---|---|
| `:TIMebase:MODE <mode>` / `?` | Discrete | `{MAIN\|XY\|ROLL}`, default `MAIN`; `MAIN` is YT mode | — | 173 |
| `:TIMebase[:MAIN]:SCALe <scale>` / `?` | Real | YT: 5 ns/div to 50 s/div in 1-2-5 steps; ROLL: 200 ms/div to 50 s/div; default 1 µs/div | s/div | 173 |
| `:TIMebase[:MAIN]:OFFSet <offset>` / `?` | Real | Depends on mode and run state (see below), default 0 | s | 172 |
| `:TIMebase:DELay:ENABle <bool>` / `?` | Bool | `{{1\|ON}\|{0\|OFF}}`, default `0` | — | 169 |
| `:TIMebase:DELay:SCALe <scale>` / `?` | Real | Up to the main scale, down to 50/(sample rate × amplification factor); default 500 ns/div | s/div | 171 |
| `:TIMebase:DELay:OFFSet <offset>` / `?` | Real | `-(LeftTime - DelayRange/2)` to `(RightTime - DelayRange/2)`, default 0 | s | 170 |

- `OFFSet` range is written out only in prose: `RUN` allows
  `-0.5 × MemDepth/SampleRate` to 1 s (or to `10 × MainScale` at 200 ms/div and
  above); `STOP` allows `-MemDepth/SampleRate` to `1 s + 0.5 × MemDepth/SampleRate`;
  in ROLL mode the command is invalid while running (PDF p. 172). Derive the
  bound from `:ACQuire:MDEPth?` and `:ACQuire:SRATe?` rather than hard-coding.
- `MODE XY` and `MODE ROLL` change what the horizontal axis, the memory, and
  `:WAVeform` mean. Record `:TIMebase:MODE?` with every waveform.
- The horizontal screen is 12 divisions on this family (PDF pp. 21, 23), so
  `waveform length = 12 × timebase` and `memory depth = sample rate × waveform
  length`.
- `:TIMebase[:MAIN]:SCALe` is also documented as invalid while the instrument is
  transitioning to the stop state at 200 ms/div or above (PDF p. 173); that
  transition case was not exercised on hardware.
- Evidence unit read `:TIMebase:MAIN:SCALe?` = `2.0000000e-04` (200 µs/div) and
  `:TIMebase:MODE?` = `MAIN` (`hardware-verified`). Note the NR3 digit count: the
  timebase queries answer with eight significant digits, unlike the seven in the
  channel replies, so parse as float, not with a fixed-width splitter.

## Trigger, common settings (`:TRIGger`, PDF pp. 174-177)

| Command | Parameter | Range / default | Unit | Page |
|---|---|---|---|---|
| `:TRIGger:MODE <mode>` / `?` | Discrete | `{EDGE\|PULSe\|RUNT\|WIND\|NEDG\|SLOPe\|VIDeo\|PATTern\|DELay\|TIMeout\|DURation\|SHOLd\|RS232\|IIC\|SPI}`, default `EDGE` | — | 174 |
| `:TRIGger:SWEep <sweep>` / `?` | Discrete | `{AUTO\|NORMal\|SINGle}`, default `AUTO` | — | 175 |
| `:TRIGger:COUPling <couple>` / `?` | Discrete | `{AC\|DC\|LFReject\|HFReject}`, default `DC`; edge trigger on an analog source only | — | 175 |
| `:TRIGger:HOLDoff <value>` / `?` | Real | 16 ns to 10 s, default 16 ns | s | 176 |
| `:TRIGger:NREJect <bool>` / `?` | Bool | `{{1\|ON}\|{0\|OFF}}`, default `0` | — | 176 |
| `:TRIGger:STATus?` | — | Returns `TD`, `WAIT`, `RUN`, `AUTO`, or `STOP` | — | 175 |
| `:TRIGger:POSition?` | — | Integer; `-2` = not triggered, `-1` = triggered before the memory | pts | 177 |

- Discrete queries echo the short form: `MODE?` returns `EDGE`, `PULS`, `RUNT`,
  `WIND`, `NEDG`, `SLOP`, `VID`, `PATT`, `DEL`, `TIM`, `DUR`, `SHOL`, `RS232`,
  `IIC`, or `SPI`; `SWEep?` returns `AUTO`, `NORM`, or `SING`; `COUPling?` returns
  `AC`, `DC`, `LFR`, or `HFR` (PDF pp. 174-175).
- `SWEep AUTO` keeps sweeping without a trigger, so a completed frame proves an
  acquisition, not a triggered one. Use `NORMal` when the capture depends on the
  trigger condition (`documented`, PDF p. 175).
- `HOLDoff` is unavailable when the type is video, timeout, setup/hold, Nth
  edge, RS232, IIC, or SPI (PDF p. 176). Setting it then has no effect.
- `NREJect` is unavailable when the trigger source is a digital channel
  (PDF p. 176).
- `:TRIGger:STATus?` is the only reliable readiness signal. The evidence unit
  answered `TD` while running and `STOP` after `:SINGle` / `:STOP`
  (`hardware-verified`); `WAIT`, `RUN`, and `AUTO` are `documented` but were not
  observed. See [capture-and-waveform.md](capture-and-waveform.md) for the
  decision table.
- Evidence unit: `:TRIGger:MODE?` = `EDGE`, `:TRIGger:SWEep?` = `AUTO`,
  `:TRIGger:COUPling?` = `DC` (`hardware-verified`).

## Edge trigger (`:TRIGger:EDGe`, PDF pp. 178-179)

| Command | Parameter | Range / default | Unit | Page |
|---|---|---|---|---|
| `:TRIGger:EDGe:SOURce <source>` / `?` | Discrete | `{CHANnel1..CHANnel4\|AC\|D0..D15}`, default `CHANnel1` | — | 178 |
| `:TRIGger:EDGe:SLOPe <slope>` / `?` | Discrete | `{POSitive\|NEGative\|RFALl}`, default `POSitive` | — | 178 |
| `:TRIGger:EDGe:LEVel <level>` / `?` | Real | `(-5 × VerticalScale - OFFSet)` to `(5 × VerticalScale - OFFSet)`, default 0 | source amplitude unit | 179 |

- `SOURce` echoes `CHAN1`..`CHAN4`, `AC`, or `D0`..`D15`; `SLOPe` echoes `POS`,
  `NEG`, or `RFAL` (PDF p. 178). `AC` means the AC power line, not AC coupling.
- `LEVel` is expressed in the current amplitude unit of the source channel, and
  its allowed range moves with `:CHANnel<n>:SCALe` and `:CHANnel<n>:OFFSet`
  (PDF p. 179). Change the level before widening the vertical scale, not after.
- `LEVel` is unavailable when the source is a digital channel (PDF p. 179).
- Digital-channel sources (`D0`-`D15`) and the CH3/CH4 exclusion rules against
  enabled digital groups (PDF p. 178) do not apply to this Skill, which never
  enables digital channels.
- Evidence unit: `:TRIGger:EDGe:SOURce?` = `CHAN1`,
  `:TRIGger:EDGe:LEVel?` = `1.500000e+00`, `:TRIGger:EDGe:SLOPe?` = `POS`
  (`hardware-verified`).

A complete, known-good edge setup as read back from the evidence unit:

```text
:TRIGger:MODE EDGE       :TRIGger:SWEep AUTO       :TRIGger:COUPling DC
:TRIGger:EDGe:SOURce CHANnel1
:TRIGger:EDGe:LEVel 1.5
:TRIGger:EDGe:SLOPe POSitive
:TIMebase:MODE MAIN      :TIMebase:MAIN:SCALe 0.0002
:CHANnel1:SCALe 0.5      :CHANnel1:OFFSet -1.52   :CHANnel1:COUPling DC
```

## Other trigger types: present in the manual, not implemented here

These subtypes exist in the Programming Guide and are documented for the family,
but this Skill configures **none** of them: it never sends these writes, its
snapshot fields do not cover them, and no evidence was collected for them. Treat
them as `documented` only, read the cited pages before use, and record every
non-default qualifier with the capture.

| Type | Manual section (PDF page) |
|---|---|
| `:TRIGger:PULSe` (pulse width) | 180 |
| `:TRIGger:SLOPe` (rise/fall time) | 184 |
| `:TRIGger:VIDeo` | 189 |
| `:TRIGger:PATTern` | 192 |
| `:TRIGger:DURATion` | 195 |
| `:TRIGger:TIMeout` (option) | 199 |
| `:TRIGger:RUNT` (option) | 201 |
| `:TRIGger:WINDows` (option) | 205 |
| `:TRIGger:DELay` (option) | 208 |
| `:TRIGger:SHOLd` (option) | 212 |
| `:TRIGger:NEDGe` (option) | 215 |
| `:TRIGger:RS232` (option) | 217 |
| `:TRIGger:IIC` (option) | 222 |
| `:TRIGger:SPI` (option) | 226 |

The manual marks timeout, runt, window, delay, setup/hold, Nth edge, RS232, IIC,
and SPI as "(Option)" (PDF p. 174), so their availability depends on installed
options that this Skill cannot query: `*OPT?` returns `command error` on
`00.04.02.SP4` (`hardware-verified`), and the option list is visible only via
`:SYSTem:OPTion:INSTall` / `:SYSTem:OPTion:UNINSTall` (PDF p. 162), which are
writes. **CAN and LIN trigger/decode do not appear in this manual at all**; do
not invent `:TRIGger:CAN` or `:TRIGger:LIN` headers for this family.

## Snapshot fields to record with any acquisition

Capture this context with every waveform or measurement; a value without it is
structurally valid but not reproducible.

```text
*IDN?
:TRIGger:STATus?  :TRIGger:MODE?  :TRIGger:SWEep?  :TRIGger:COUPling?
:TRIGger:HOLDoff?  :TRIGger:EDGe:SOURce?  :TRIGger:EDGe:LEVel?  :TRIGger:EDGe:SLOPe?
:TIMebase:MODE?   :TIMebase:MAIN:SCALe?  :TIMebase:MAIN:OFFSet?
per displayed channel: :CHANnel<n>:DISPlay? :SCALe? :OFFSet? :COUPling? :PROBe?
                       :BWLimit? :INVert? :UNITs? :VERNier?
:ACQuire:TYPE? :ACQuire:MDEPth? :ACQuire:SRATe?
```

Each of these is one query per write with the reply read before the next write
(`hardware-verified`; see [remote-session.md](remote-session.md)).
