# Modulation, Sweep, Burst, Counter, Phase, Coupling (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 218-270. Support level:
`documented`.

## Modulation commands

AM, FM, FSK, PM, SUM. Each has State/Source/Internal Function/Internal
Frequency plus a depth/deviation/rate/amplitude parameter. Pages 218-239.
Only one modulation type should be active at a time; enabling one may need
the others disabled.

| Family | Commands (short form) | Key ranges | Page |
|---|---|---|---|
| AM | `AM:STAT`, `AM:SOUR`, `AM:INT:FUNC`, `AM:INT:FREQ`, `AM:DEPT` | depth 0-120 %; modulation 2 mHz-20 kHz internal | 219-221 |
| FM | `FM:STAT`, `FM:SOUR`, `FM:INT:FUNC`, `FM:INT:FREQ`, `FM:DEV` | deviation DC-25 MHz sine, DC-15 MHz square, DC-1 MHz ramp | 224-226 |
| FSK | `FSK:STAT`, `FSK:SOUR`, `FSK:FREQ`, `FSK:INT:RATE` | hop 1 µHz-25 MHz sine, 1 µHz-15 MHz square/pulse, 1 µHz-1 MHz ramp | 228-230 |
| PM | `PM:STAT`, `PM:SOUR`, `PM:INT:FUNC`, `PM:INT:FREQ`, `PM:DEV` | deviation 0-360°; modulation 2 mHz-20 kHz internal | 233-235 |
| SUM | `SUM:STAT`, `SUM:SOUR`, `SUM:INT:FUNC`, `SUM:INT:FREQ`, `SUM:AMPL` | sum amplitude 0-100 %; modulation 2 mHz-20 kHz internal | 237-239 |

## Sweep commands

Pages 240-248.

| Command | Range / notes | Page |
|---|---|---|
| `SWE:STAT` | ON/OFF | 241 |
| `FREQ:STARt` / `FREQ:STOP` | start/stop frequency | 242 |
| `FREQ:CENTer` / `FREQ:SPAN` | center/span | 243-244 |
| `SWE:SPAC` | LIN/LOG | 245 |
| `SWE:TIME` | 1 ms-500 s | 245 |
| `SWE:SOUR` | IMM/EXT/MAN | 246 |
| `MARK:FREQ` | 1 µHz-25 MHz (1 µHz-1 MHz ramp) | 247 |
| `MARK` | ON/OFF | 247 |

`*OPC` sets the operation-complete bit when a sweep or burst completes;
`*OPC?` returns `1` after pending operations complete. `*WAI` is documented
for triggered sweep and burst modes (manual pp. 194-195, 246).

## Burst commands

Pages 249-258.

| Command | Notes | Page |
|---|---|---|
| `BURS:STAT` | ON/OFF | 251 |
| `BURS:MODE` | N Cycle / Gate | 251 |
| `BURS:NCYC` | cycle count | 252 |
| `BURS:INT:PER` | internal period | 253 |
| `BURS:PHAS` | phase | 254 |
| `BURS:TRIG:SOUR` | trigger source | 254 |
| `BURS:TRIG:DEL` | trigger delay | 255 |
| `BURS:TRIG:SLOP` | slope | 256 |
| `BURS:GATE:POL` | polarity | 257 |
| `BURS:OUTP:TRIG:SLOP` | output trigger slope | 257 |
| `OUTP:TRIG` | output trigger | 258 |

## Counter, phase, coupling

- Frequency counter: `COUNter:STATe {ON|OFF}`, `COUNter:GATe {0.01|0.1|1|10}`,
  `COUNter:VALue?` returns Hz (pp. 266-267).
- Phase: `SOURce[1|2]:PHASe -180..180`; `SOURce[1|2]:PHASe:SYNChronize`
  (pp. 267-268).
- Frequency coupling: `FREQuency:COUPle:MODE {OFF|OFFSet|RATio}`, offset, ratio;
  amplitude coupling and tracking (pp. 268-270).

## Trigger input/output

- Rear-panel Trigger INPUT accepts external trigger/gate signals.
- Rear-panel Trigger OUT provides the marker/SYNC output; `MARKer` controls
  whether it goes low at the marker frequency or outputs a 50 % square wave
  at sweep start (manual pp. 247-248).
- `*OPC`/`*OPC?`/`*WAI` signal completion; they are documented for sweep and
  burst, not as a general continuous-acquisition mechanism (manual pp. 194-195).

## Mode conflicts

- APPLy disables burst/modulation/sweep and sets trigger immediate.
- Enabling AM, FM, FSK, PM, or SUM disables the other modulation modes; only
  one modulation type is active at a time (manual pp. 219, 228, 233, 237).
- Enabling modulation disables burst or sweep (manual pp. 219, 228).
- Check the burst mode/source table on p. 249 before combining N-cycle, gate,
  and trigger sources.