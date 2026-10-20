# Command Reference (Fallback Index)

This is a fallback index, not a tutorial: read it only when the task-specific
reference named in `SKILL.md` and the scripts cannot answer the question. Its
scope is strictly the commands already recorded inside this Skill (`SKILL.md`,
`references/*.md`, `scripts/*.py`). The authoritative complete command set is
the *AFG-2225 Series User Manual* (GW Instek part no. 82RF-22250M01), which is
not copied here. Anything absent from this table must be verified against the
manual and labelled `documented` before use. Every command below remains
`documented` only, and the safety rules in `SKILL.md` still apply: APPLy turns
the output on; no routine `*RST`; no automatic save/recall/calibration;
load-impedance and `|Voffset| < Vmax - Vpp/2` limits.

Short/long forms are printed exactly as the source records them. Where a source
gives only a short form (for example `SWE:STAT`), only that form is written here;
where a source gives the long form plus `[1&#124;2]` channel syntax
(`SOURce[1&#124;2]:FREQuency`), that form is preserved verbatim. Command spelling is
case-insensitive per the manual, but is not normalised in this table. A page
number is shown only where a skill document already cites one; pages are not
inferred.

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | Returns `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm`. Different model is `INVALID`; missing serial/firmware is `INCOMPLETE`. First step of every session. | remote-session.md (manual p. 193)<br>response-and-evidence.md (manual pp. 193-198)<br>SKILL.md |
| `*CLS` | set | — | Clears status registers and the error queue. Use only when clearing status/error state is authorized. | remote-session.md (manual p. 196)<br>SKILL.md |
| `*ESE` | set | — | Event status enable; the skill records no value range. | remote-session.md (manual p. 196) |
| `*ESR?` | query | — | Event status register. | remote-session.md (manual p. 197) |
| `*STB?` | query | — | Status byte. | remote-session.md (manual p. 197) |
| `*SRE` | set | — | Service request enable; the skill records no value range. | remote-session.md (manual p. 198) |
| `*OPC` | event | — | Sets the operation-complete bit when a sweep or burst completes; documented for sweep and burst, not as a general continuous-acquisition mechanism. | remote-session.md (manual p. 194)<br>modulation-sweep-burst.md (manual pp. 194-195) |
| `*OPC?` | query | — | Returns `1` after pending operations complete. | remote-session.md (manual p. 195)<br>modulation-sweep-burst.md (manual pp. 194-195) |
| `*WAI` | event | — | Waits until complete; documented for triggered sweep and burst modes. | remote-session.md (manual p. 195)<br>modulation-sweep-burst.md (manual pp. 194-195, 246) |
| `*RST` | set | — | Factory reset; does not delete saved states. **Never** as routine cleanup. Manual does not state its effect on the error queue. | remote-session.md (manual p. 194)<br>SKILL.md |
| `*SAV` | set | `{0..9}` | Saves the current instrument state to a non-volatile slot; saves state, **not** waveform data. Never run automatically. | remote-session.md (manual pp. 271-272)<br>arbitrary-waveform.md (manual p. 271)<br>SKILL.md |
| `*RCL` | set | `{0..9}` | Recalls a saved instrument state. Never run automatically; do not overwrite operator-owned slots. | remote-session.md (manual pp. 271-272)<br>SKILL.md |

## System, status, error, and remote/local

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SYSTem:VERSion?` | query | — | Preserved as raw text. Manual shows only a placeholder (`AFG-2225 VX.XXX_XXXX`), so no structured firmware/FPGA fields are claimed. | remote-session.md (manual p. 194)<br>response-and-evidence.md<br>SKILL.md |
| `SYSTem:ERRor?` | query | — | Reads one error from the 20-entry FIFO. Full queue returns `-350 Queue overflow`; empty queue returns `0 No error` or a bare `No error`. Drain until `No error`; the empty-queue wire format is not shown in the manual. | remote-session.md (manual pp. 193, 292)<br>response-and-evidence.md (manual pp. 287-292)<br>SKILL.md |
| `SYST:ERR?` | query | — | Short form used by the live helper; drained at most 20 times per call. | scripts/afg2225_session.py |
| `SYSTem:LOCal` | set | — | Return to local (front-panel) control. | remote-session.md (manual p. 199) |
| `SYSTem:REMote` | set | — | Enter remote mode; all panel keys lock except F5 (REM/LOCK). | remote-session.md (manual p. 199)<br>bench-setup.md (manual p. 182) |

## Output control and load

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `OUTPut[1&#124;2]` | set/query | ON/OFF | Output state defaults to off. Verify with `OUTP<n>?` rather than assuming a low-level command enabled it. The manual's `OUTP1 ON` did not work for one community reporter (unverified). | basic-waveforms.md (manual p. 213)<br>remote-session.md<br>SKILL.md |
| `OUTP<n>` | set/query | ON/OFF | Helper form; refuses `--channel` outside 1/2. | scripts/afg2225_session.py |
| `OUTP<n>?` | query | — | Readback of output state; mandatory before connecting a load. Used in the snapshot sequence. | scripts/afg2225_session.py<br>SKILL.md |
| `OUTPut[1&#124;2]:LOAD` | set/query | `DEFault` (50 Ω) / `INFinity` (>10 kΩ) | Reference setting only; if it disagrees with the real load, amplitude and offset are wrong. Amplitude and offset double from 50 Ω to high-Z. Set before amplitude/offset. | basic-waveforms.md (manual p. 213)<br>bench-setup.md (manual p. 213) |
| `OUTP<n>:LOAD` | set | `DEF` (50 Ω) / `INF` (high impedance) | Helper short form; emitted before every APPLy and ARB upload. | scripts/afg2225_session.py |
| `OUTP<n>:LOAD?` | query | — | Readback of reference termination; used in the snapshot sequence. | scripts/afg2225_session.py |
| `OUTP:TRIG` | set | — | Burst trigger output on the rear-panel Trigger OUT. | modulation-sweep-burst.md (manual p. 258) |

## High-level APPLy

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SOURce[1&#124;2]:APPLy:SINusoid` | set | `[freq[,amp[,offset]]]`; 1 µHz-25 MHz | Sets trigger immediate, disables burst/modulation/sweep, and turns the output **on**. Defaults 1 kHz, 100 mVpp (50 Ω), 0 V. Amp 1 mVpp-10 Vpp, offset -4.99 V..4.99 V. | basic-waveforms.md (manual pp. 200-205, 202)<br>SKILL.md |
| `SOURce[1&#124;2]:APPLy:SQUare` | set | `[freq[,amp[,offset]]]`; 1 µHz-25 MHz | Same side effects. Forces 50 % duty; use `SQU:DCYC` to change it. | basic-waveforms.md (manual p. 202)<br>SKILL.md |
| `SOURce[1&#124;2]:APPLy:RAMP` | set | `[freq[,amp[,offset]]]`; 1 µHz-1 MHz | Same side effects. Forces 50 % symmetry; use `RAMP:SYMM` to change it. | basic-waveforms.md (manual p. 203)<br>SKILL.md |
| `SOURce[1&#124;2]:APPLy:PULSe` | set | `[freq[,amp[,offset]]]`; 500 µHz-25 MHz | Same side effects. | basic-waveforms.md (manual p. 203)<br>SKILL.md |
| `SOURce[1&#124;2]:APPLy:NOISe` | set | frequency not applicable — use `DEF` | Same side effects. The manual requires a frequency or `DEF` placeholder before the nested amplitude and offset. | basic-waveforms.md (manual p. 204)<br>scripts/afg2225_session.py |
| `SOURce[1&#124;2]:APPLy:USER` | set | `[freq[,amp[,offset]]]`; 1 µHz-60 MHz | The only APPLy shape consistent with an ARB upload; other shapes switch away from the arbitrary waveform and turn the output on. | basic-waveforms.md (manual p. 204)<br>arbitrary-waveform.md (manual p. 260) |
| `SOURce[1&#124;2]:APPLy?` | query | — | Returns function/frequency/amplitude/offset. | basic-waveforms.md (manual p. 205) |
| `SOUR<n>:APPL:SIN` | set | `freq,ampVPP,offsetV` | Helper short form, e.g. `SOUR1:APPL:SIN 1000,2.0VPP,0.5V`. Requires `--load`; prints that the output is turned on. | scripts/afg2225_session.py<br>scripts/test_afg2225_session.py |
| `SOUR<n>:APPL:<shape>` | set | `freq,ampVPP,offsetV`; `<shape>` in SIN/SQU/RAMP/PULS/NOIS/USER | Helper template used by the `apply` subcommand, e.g. `SOUR1:APPL:SIN 1000,2.0VPP,0.5V`. `SQU`, `RAMP`, `PULS`, and `USER` are emitted through this template only. Requires `--load`. | SKILL.md<br>scripts/afg2225_session.py<br>scripts/test_afg2225_session.py |

## Low-level waveform (FUNC, FREQ, AMPL, DCO, duty, symmetry, pulse)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SOURce[1&#124;2]:FUNCtion` | set/query | SIN/SQU/RAMP/PULS/NOIS/USER | Selecting a waveform does not assert the output state; query `OUTP<n>?`. `USER` selects the arbitrary waveform. | basic-waveforms.md (manual p. 206)<br>arbitrary-waveform.md (manual p. 261)<br>SKILL.md |
| `SOUR<n>:FUNC` | set/query | SIN/SQU/RAMP/PULS/NOIS/USER | Helper short form. | scripts/afg2225_session.py |
| `SOUR<n>:FUNC?` | query | — | Readback of the selected function; used in the snapshot sequence. | scripts/afg2225_session.py |
| `SOUR<n>:FUNC USER` | set | USER | Sent before `DATA:DAC` in the ARB upload order; helper does not enable the output. | scripts/afg2225_session.py<br>scripts/test_afg2225_session.py<br>SKILL.md |
| `SOURce[1&#124;2]:FREQuency` | set/query | 1 µHz-25 MHz (sine/square); 1 µHz-1 MHz (ramp); 500 µHz-25 MHz (pulse) | For ARB, rate = frequency × points. | basic-waveforms.md (manual p. 207)<br>arbitrary-waveform.md (manual p. 260) |
| `SOUR<n>:FREQ` | set/query | — | Helper short form. | scripts/afg2225_session.py |
| `SOUR<n>:FREQ?` | query | — | Readback of frequency; snapshot sequence and query example. | scripts/afg2225_session.py<br>scripts/test_afg2225_session.py |
| `SOURce[1&#124;2]:AMPlitude` | set/query | 1 mVpp-10 Vpp (50 Ω); 2 mVpp-20 Vpp (high-Z); 1-5 Vpp (50 Ω) at 20-25 MHz | Amplitude doubles from 50 Ω to high-Z. | basic-waveforms.md (manual pp. 209-210)<br>SKILL.md |
| `SOUR<n>:AMPL?` | query | — | Readback of amplitude; used in the snapshot sequence. | scripts/afg2225_session.py |
| `SOURce[1&#124;2]:DCOffset` | set/query | ±5 Vpk ac+dc (50 Ω); ±10 Vpk (high-Z); ±2.5 Vpk (50 Ω) at 20-25 MHz; constraint `&#124;Voffset&#124; < Vmax - Vpp/2` | Offset doubles from 50 Ω to high-Z. Community report (unverified): positive DC offset with ARB can invert the signal; no automatic workaround. | basic-waveforms.md (manual pp. 210, 213)<br>SKILL.md |
| `SOUR<n>:DCO?` | query | — | Helper short form for offset readback; used in the snapshot sequence. | scripts/afg2225_session.py |
| `SOURce[1&#124;2]:VOLTage:UNIT` | set/query | `VPP` / `VRMS` / `DBM` | dBm unavailable in high-Z mode. | basic-waveforms.md (manual p. 214)<br>SKILL.md |
| `SOURce[1&#124;2]:SQUare:DCYCle` | set/query | 1-99 % (≤100 kHz), 10-90 % (≤1 MHz), 50 % (25 MHz) | APPLy:SQU forces 50 %. | basic-waveforms.md (manual p. 211)<br>SKILL.md |
| `SQU:DCYC` | set/query | — | Short form named in the low-level command list. | SKILL.md (manual pp. 200-215) |
| `SOURce[1&#124;2]:RAMP:SYMMetry` | set/query | 0-100 % | APPLy:RAMP forces 50 %. | basic-waveforms.md (manual p. 212)<br>SKILL.md |
| `RAMP:SYMM` | set/query | 0-100 % | Short form named in the low-level command list. | SKILL.md (manual pp. 200-215) |
| `SOURce[1&#124;2]:PULSe:PERiod` | set/query | 40 ns-2000 s | Pulse period limit. | basic-waveforms.md (manual p. 216)<br>SKILL.md |
| `SOURce[1&#124;2]:PULSe:WIDTh` | set/query | 20 ns-1999.9 s; width > 1.6 × edge time and width < period − 1.6 × edge time | Pulse width limit. | basic-waveforms.md (manual p. 217)<br>SKILL.md |
| `PULS:*` | set/query | — | Umbrella for pulse commands; individual members are the two `PULSe` rows above. | SKILL.md (manual pp. 200-215) |

## Arbitrary waveform (FUNC USER, DATA:DAC, memory, edit)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `DATA:DAC VOLATILE,<start>,...` | set | `<start>` 0..4095; points 1..4096; `start + points <= 4096`; values ±511 | Writes volatile memory. ASCII decimal list is the default safe path. `FUNC USER` should be selected first. | arbitrary-waveform.md (manual pp. 260-261)<br>SKILL.md |
| `DATA:DAC VOLATILE,<start>,{<binary block>&#124;v,...}` | set | IEEE 488.2 `#<digits><length><payload>`, two bytes per point (16-bit signed) | Binary byte order is **not** stated by the manual; requires an explicit `--byte-order little&#124;big` and stays `UNVERIFIED`. Manual example `DATA:DAC VOLATILE, #216 Binary Data` claims 5 values / 16 bytes but 5 × 2 = 10 bytes — preserve this defect, compute length from the point count. | arbitrary-waveform.md (manual p. 261)<br>scripts/afg2225_protocol.py<br>SKILL.md |
| `DATA:DAC VOLATILE,0,-511,0,511` | set | ASCII list | Exact bytes built and asserted by the protocol tests. | scripts/afg2225_protocol.py<br>scripts/test_afg2225_protocol.py |
| `SOURce[1&#124;2]:ARB:EDIT:COPY` | set | `[start[,length[,paste]]]`; addresses 0..4095 | Copies a segment. Do not copy over a waveform currently output. | arbitrary-waveform.md (manual pp. 262-265) |
| `SOURce[1&#124;2]:ARB:EDIT:DELete` | set | `[start[,length]]`; addresses 0..4095 | Deletes a segment. Do not delete a waveform currently output. | arbitrary-waveform.md (manual p. 263) |
| `SOURce[1&#124;2]:ARB:EDIT:DELete:ALL` | set | — | Deletes all; never run automatically. | arbitrary-waveform.md (manual p. 263) |
| `SOURce[1&#124;2]:ARB:EDIT:POINt` | set | `[address[,data]]`; address 0..4095, data ±511 | Edits a single point. | arbitrary-waveform.md (manual p. 263) |
| `SOURce[1&#124;2]:ARB:EDIT:LINE` | set | `[addr1[,data1[,addr2[,data2]]]]`; data ±511 | Edits points on a line. | arbitrary-waveform.md (manual p. 264) |
| `SOURce[1&#124;2]:ARB:EDIT:PROTect` | set | — | Protects a waveform; never run automatically. | arbitrary-waveform.md (manual p. 264) |
| `SOURce[1&#124;2]:ARB:EDIT:PROTect:ALL` | set | — | Protects all; never run automatically. | arbitrary-waveform.md (manual p. 265) |
| `SOURce[1&#124;2]:ARB:EDIT:UNProtect` | set | — | Removes protection. | arbitrary-waveform.md (manual p. 265) |
| `SOURce[1&#124;2]:ARB:OUTPut` | set | `[start[,length]]`; manual prints 0..4096 with `start + length` not exceeding the current waveform | Outputs the current volatile waveform or a segment. Do not delete/protect a waveform currently output. | arbitrary-waveform.md (manual pp. 262-265) |

## Modulation (AM / FM / FSK / PM / SUM)

Enabling one modulation type disables the others; enabling modulation also
disables burst or sweep. Families are at manual pp. 218-239.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `AM:STAT` | set/query | ON/OFF | Enabling AM disables FM/FSK/PM/SUM and burst/sweep. | modulation-sweep-burst.md (manual pp. 219-221) |
| `AM:SOUR` | set/query | — | Modulation source (internal or external MOD INPUT). | modulation-sweep-burst.md (manual pp. 219-221)<br>bench-setup.md (manual p. 219) |
| `AM:INT:FUNC` | set/query | — | Internal modulation waveform. | modulation-sweep-burst.md (manual pp. 219-221) |
| `AM:INT:FREQ` | set/query | 2 mHz-20 kHz (internal modulation) | — | modulation-sweep-burst.md (manual pp. 219-221) |
| `AM:DEPT` | set/query | 0-120 % | — | modulation-sweep-burst.md (manual pp. 219-221) |
| `FM:STAT` | set/query | ON/OFF | Enabling FM disables the other modulation modes and burst/sweep. | modulation-sweep-burst.md (manual pp. 224-226) |
| `FM:SOUR` | set/query | — | Modulation source. | modulation-sweep-burst.md (manual pp. 224-226) |
| `FM:INT:FUNC` | set/query | — | Internal modulation waveform. | modulation-sweep-burst.md (manual pp. 224-226) |
| `FM:INT:FREQ` | set/query | 2 mHz-20 kHz (internal modulation) | — | modulation-sweep-burst.md (manual pp. 224-226) |
| `FM:DEV` | set/query | deviation DC-25 MHz sine, DC-15 MHz square, DC-1 MHz ramp | — | modulation-sweep-burst.md (manual pp. 224-226) |
| `FSK:STAT` | set/query | ON/OFF | Enabling FSK disables the other modulation modes and burst/sweep. | modulation-sweep-burst.md (manual pp. 228-230) |
| `FSK:SOUR` | set/query | — | Modulation source. | modulation-sweep-burst.md (manual pp. 228-230) |
| `FSK:FREQ` | set/query | hop 1 µHz-25 MHz sine, 1 µHz-15 MHz square/pulse, 1 µHz-1 MHz ramp | Hop frequency. | modulation-sweep-burst.md (manual pp. 228-230) |
| `FSK:INT:RATE` | set/query | — | Internal hop rate; no range recorded in the skill. | modulation-sweep-burst.md (manual pp. 228-230) |
| `PM:STAT` | set/query | ON/OFF | Enabling PM disables the other modulation modes. | modulation-sweep-burst.md (manual pp. 233-235) |
| `PM:SOUR` | set/query | — | Modulation source. | modulation-sweep-burst.md (manual pp. 233-235) |
| `PM:INT:FUNC` | set/query | — | Internal modulation waveform. | modulation-sweep-burst.md (manual pp. 233-235) |
| `PM:INT:FREQ` | set/query | 2 mHz-20 kHz (internal modulation) | — | modulation-sweep-burst.md (manual pp. 233-235) |
| `PM:DEV` | set/query | 0-360° | — | modulation-sweep-burst.md (manual pp. 233-235) |
| `SUM:STAT` | set/query | ON/OFF | Enabling SUM disables the other modulation modes. | modulation-sweep-burst.md (manual pp. 237-239) |
| `SUM:SOUR` | set/query | — | Modulation source. | modulation-sweep-burst.md (manual pp. 237-239) |
| `SUM:INT:FUNC` | set/query | — | Internal modulation waveform. | modulation-sweep-burst.md (manual pp. 237-239) |
| `SUM:INT:FREQ` | set/query | 2 mHz-20 kHz (internal modulation) | — | modulation-sweep-burst.md (manual pp. 237-239) |
| `SUM:AMPL` | set/query | 0-100 % | Sum amplitude. | modulation-sweep-burst.md (manual pp. 237-239) |

## Sweep

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SWE:STAT` | set/query | ON/OFF | Enabling sweep conflicts with modulation and burst; APPLy disables sweep. | modulation-sweep-burst.md (manual p. 241) |
| `FREQ:STARt` | set/query | — | Sweep start frequency. | modulation-sweep-burst.md (manual p. 242) |
| `FREQ:STOP` | set/query | — | Sweep stop frequency. | modulation-sweep-burst.md (manual p. 242) |
| `FREQ:CENTer` | set/query | — | Sweep center frequency. | modulation-sweep-burst.md (manual p. 243) |
| `FREQ:SPAN` | set/query | — | Sweep span. | modulation-sweep-burst.md (manual p. 244) |
| `SWE:SPAC` | set/query | LIN/LOG | Sweep spacing. | modulation-sweep-burst.md (manual p. 245) |
| `SWE:TIME` | set/query | 1 ms-500 s | Sweep time. | modulation-sweep-burst.md (manual p. 245) |
| `SWE:SOUR` | set/query | IMM/EXT/MAN | Sweep source; `*WAI` is documented for triggered sweeps. | modulation-sweep-burst.md (manual p. 246) |
| `MARK:FREQ` | set/query | 1 µHz-25 MHz (1 µHz-1 MHz ramp) | Marker frequency. | modulation-sweep-burst.md (manual p. 247) |
| `MARK` | set/query | ON/OFF | Marker on/off; `MARKer` controls whether Trigger OUT goes low at the marker frequency or outputs a 50 % square wave at sweep start. | modulation-sweep-burst.md (manual pp. 247-248) |

## Burst

Check the burst mode/source table at manual p. 249 before combining N-cycle,
gate, and trigger sources. Trigger IN is the rear-panel external trigger/gate.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `BURS:STAT` | set/query | ON/OFF | Enabling burst conflicts with modulation and sweep; APPLy disables burst. | modulation-sweep-burst.md (manual p. 251) |
| `BURS:MODE` | set/query | N Cycle / Gate | — | modulation-sweep-burst.md (manual p. 251) |
| `BURS:NCYC` | set/query | — | Cycle count; no range recorded in the skill. | modulation-sweep-burst.md (manual p. 252) |
| `BURS:INT:PER` | set/query | — | Internal period. | modulation-sweep-burst.md (manual p. 253) |
| `BURS:PHAS` | set/query | — | Burst phase. | modulation-sweep-burst.md (manual p. 254) |
| `BURS:TRIG:SOUR` | set/query | — | Trigger source. | modulation-sweep-burst.md (manual p. 254) |
| `BURS:TRIG:DEL` | set/query | — | Trigger delay. | modulation-sweep-burst.md (manual p. 255) |
| `BURS:TRIG:SLOP` | set/query | — | Trigger slope. | modulation-sweep-burst.md (manual p. 256) |
| `BURS:GATE:POL` | set/query | — | Gate polarity. | modulation-sweep-burst.md (manual p. 257) |
| `BURS:OUTP:TRIG:SLOP` | set/query | — | Output trigger slope. | modulation-sweep-burst.md (manual p. 257) |

## Counter

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `COUNter:STATe` | set/query | `{ON&#124;OFF}` | Frequency-counter input is on the rear panel. | modulation-sweep-burst.md (manual pp. 266-267)<br>bench-setup.md (manual p. 266) |
| `COUNter:GATe` | set/query | `{0.01&#124;0.1&#124;1&#124;10}` | Gate time. | modulation-sweep-burst.md (manual pp. 266-267) |
| `COUNter:VALue?` | query | — | Returns Hz. | modulation-sweep-burst.md (manual pp. 266-267) |

## Phase and coupling

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SOURce[1&#124;2]:PHASe` | set/query | -180..180 | Channel phase. | modulation-sweep-burst.md (manual pp. 267-268) |
| `SOURce[1&#124;2]:PHASe:SYNChronize` | event | — | Phase synchronisation. | modulation-sweep-burst.md (manual pp. 267-268) |
| `FREQuency:COUPle:MODE` | set/query | `{OFF&#124;OFFSet&#124;RATio}` | Frequency coupling mode. | modulation-sweep-burst.md (manual pp. 268-270) |
| offset | set/query | — | Frequency-coupling offset. The reference gives the bare words "offset, ratio" after `FREQuency:COUPle:MODE`, with no full header; verify the header against the manual before use. | modulation-sweep-burst.md (manual pp. 268-270) |
| ratio | set/query | — | Frequency-coupling ratio; same caveat as the offset row. | modulation-sweep-burst.md (manual pp. 268-270) |

## Save / recall

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `MEMory:STATe:DELete` | set | `{0..9}` | Deletes one saved state. Do not delete operator-owned slots automatically. | remote-session.md (manual pp. 271-272) |
| `MEMory:STATe:DELete ALL` | set | ALL | Deletes all saved states; never run automatically. | remote-session.md (manual pp. 271-272)<br>SKILL.md |

`*SAV`, `*RCL`, and `*RST` are listed under IEEE 488.2 common commands. `*SAV`
saves instrument state only; there is no claimed remote non-volatile ARB save
path, and waveform save/load is a panel/AWES operation in the manual.

## Coverage gaps

- **Binary ARB byte order**: the manual does not state endianness; binary
  uploads stay `UNVERIFIED` until confirmed on hardware with an oscilloscope.
  The manual's own byte-count example is defective (5 values / 16 bytes vs
  10 bytes).
- **Serial defaults**: the manual lists no baud/data/parity/stop defaults;
  `115200 8N1` in the transport helper is an assumption.
- **`OUTP1 ON` vs `SOURCE1:OUTPUT ON`**: the community report that
  `SOURCE1:OUTPUT ON` worked where `OUTP1 ON` did not is unverified. This table
  deliberately does not list `SOURCE[1&#124;2]:OUTPut` as a supported command.
- **Real-device acceptance**: no command sequence in this table has been run on
  an AFG-2225; every row is `documented` only, not `hardware-verified` or
  `firmware-scoped`.
- **No full command enumeration existed before this file**: this index was
  assembled from the skill's own documents and scripts, so commands the manual
  documents but the skill never recorded are missing here.
- **Query forms not individually recorded**: `FUNC?`/`FREQ?`/`AMPL?`/`DCO?`/
  `OUTP<n>?`/`OUTP<n>:LOAD?` appear in the live helper, but the manual's
  per-command query pages were not cited for them; `*IDN?` and `SYSTem:ERRor?`
  are the only response formats the skill actually documents.
- **Ranges the skill never recorded**: `*ESE`/`*SRE` values, `FSK:INT:RATE`,
  `BURS:NCYC`, `BURS:INT:PER`, `BURS:TRIG:*`, trigger-source discretes, and the
  coupling offset/ratio command headers — all show `—` above and must be read
  from the manual before use.
- **Not covered by any skill document**: front-panel save/recall menus,
  firmware update, calibration, and AWES waveform transfer; the Skill
  deliberately does not automate them.
