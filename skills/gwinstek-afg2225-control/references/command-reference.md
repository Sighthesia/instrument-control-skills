# Command Reference (Fallback Index)

This is a fallback index, not a tutorial: read it only when the task-specific
reference named in `SKILL.md` and the scripts cannot answer the question. The
authoritative complete command set is the *AFG-2225 Series User Manual* (GW
Instek part no. 82RF-22250M01), which is not copied here. Its `Command List`
(manual pp. 189-192) was enumerated on 2026-11-20: it holds 104 command forms
and all of them are now in this table. Anything absent from this table must be
verified against the manual and labelled `documented` before use. Rows listed
under [Hardware-verified rows](#hardware-verified-rows-2026-11-26) cite a
captured reply; every other row remains `documented` only. The safety rules in
`SKILL.md` still apply: APPLy turns the output on; no routine `*RST`; no
automatic save/recall/calibration; load-impedance and
`|Voffset| < Vmax - Vpp/2` limits.

Short/long forms are printed exactly as the source records them. Where a source
gives only a short form (for example `SWE:STAT`), only that form is written here;
where a source gives the long form plus `[1&#124;2]` channel syntax
(`SOURce[1&#124;2]:FREQuency`), that form is preserved verbatim. Command spelling is
case-insensitive per the manual, but is not normalised in this table. A page
number is shown only where a skill document already cites one; pages are not
inferred.

## Hardware-verified rows (2026-11-26)

Captured from AFG-2225 serial `GEP902745`, firmware `V2.05`, USB CDC-ACM
`2184:001c` at `/dev/ttyACM0`; raw bytes are in `assets/captures/`. The scope is
identity, error-queue framing, read-only queries, and single-parameter
write/readback/restore. Everything not in this table is `documented`.

| Command | Captured reply (raw) | Note |
|---|---|---|
| `*IDN?` | `GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n` | identity |
| `SYSTem:VERSion?` | ` AFG-2225     Version-2.05_0112 \r\n\r\n FPGA:20130410\r\n\r\n SN: GEP902745\r\n\r\n MODE:Plant Pattern\r\n` | multi-line; not structurally parsed |
| `SYSTem:ERRor?` | `-102\r\nSyntax error.` | two lines; message unterminated |
| `SYSTem:ERRor?` | `\r\nNo error.` | empty queue; blank code line |
| `OUTPut[1&#124;2]?` | `0\r\n` | output OFF |
| `SOURce[1&#124;2]:FUNCtion?` | `SIN\r\n` | CH1 and CH2 |
| `SOURce[1&#124;2]:FREQuency?` | `+5.0000000000000E-01\r\n` | CH1 |
| `SOURce[1&#124;2]:AMPlitude?` | no response; queue read `-113 Undefined header` | short form rejected |
| `SOURce[1&#124;2]:AMPLITUDE?` | `+3.000E+00\r\n` | long form required; `MAX` -> `+1.000E+01`, `MIN` -> `+1.000E-03` |
| `SOURce[1&#124;2]:DCOffset?` | `+0.00E+00\r\n` | `MAX` -> `+3.50E+00`, `MIN` -> `-3.50E+00` |
| `OUTPut[1&#124;2]:LOAD?` | `DEF\r\n` | reference termination |
| `SOURce[1&#124;2]:VOLTage:UNIT?` | `VPP\r\n` | global amplitude unit |
| `SOURce[1&#124;2]:PHASe?` | `+0.000E+00\r\n` | CH1 and CH2 |
| `SOURce[1&#124;2]:SQUare:DCYCle?` | `+5.00E+01\r\n` | 50 % |
| `SOURce[1&#124;2]:APPLy?` | `"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"\r\n` | quoted on the wire |
| `COUNter:STATe?` | `0\r\n` | counter off |
| `COUNter:VALue?` | `+0.0000E+00\r\n` | counter off; not a measurement |
| `*OPC?` | `1\r\n` | single capture |
| `SOUR1:FREQ 1234.5` then `SOUR1:FREQ?` | `+1.2345000000000E+03\r\n` | restored to `+5.0000000000000E-01` |
| `SOUR1:AMPLITUDE 1.5` then `SOUR1:AMPLITUDE?` | `+1.500E+00\r\n` | restored to `+3.000E+00` |
| `SOUR1:DCO 0.5` then `SOUR1:DCO?` | `+5.00E-01\r\n` | restored to `+0.00E+00` |
| `SYSTem:BEEPer?`, `SYST:BUZZ?` | no response; queue read `-113 Undefined header` | no SCPI beeper |
| `:BUZZER?` | no response; queue read `-102 Syntax error` | no SCPI beeper |

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | Returns `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm`; verified raw `GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n`. Different model is `INVALID`; missing serial/firmware is `INCOMPLETE`. First step of every session. | remote-session.md (manual p. 193)<br>response-and-evidence.md (manual pp. 193-198)<br>SKILL.md |
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
| `SYSTem:VERSion?` | query | — | Multi-line raw on V2.05: `Version-2.05_0112`, `FPGA:20130410`, `SN: GEP902745`, `MODE:Plant Pattern`. Preserved as raw text; no structured firmware/FPGA fields are claimed. | remote-session.md (manual p. 194)<br>response-and-evidence.md<br>SKILL.md |
| `SYSTem:ERRor?` | query | — | Reads one error from the 20-entry FIFO. Verified wire format is two lines: `-102\r\nSyntax error.` (code CRLF-terminated, message unterminated); empty queue is `\r\nNo error.`. The manual prints only the single-line `-138 Suffix not allowed` form. | remote-session.md (manual pp. 193, 292)<br>response-and-evidence.md (manual pp. 287-292)<br>SKILL.md |
| `SYST:ERR?` | query | — | Short form used by the live helper; drained at most 20 times per call. | scripts/afg2225_session.py |
| `SYSTem:LOCal` | set | — | Return to local (front-panel) control. | remote-session.md (manual p. 199) |
| `SYSTem:REMote` | set | — | Enter remote mode; all panel keys lock except F5 (REM/LOCK). | remote-session.md (manual p. 199)<br>bench-setup.md (manual p. 182) |

## Output control and load

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `OUTPut[1&#124;2]` | set/query | ON/OFF | Output state defaults to off. Verify with `OUTP<n>?` rather than assuming a low-level command enabled it. The manual's `OUTP1 ON` did not work for one community reporter (unverified). | basic-waveforms.md (manual p. 213)<br>remote-session.md<br>SKILL.md |
| `OUTP<n>` | set/query | ON/OFF | Helper form; refuses `--channel` outside 1/2. | scripts/afg2225_session.py |
| `OUTP<n>?` | query | — | Readback of output state; mandatory before connecting a load. Verified raw `0\r\n` (OFF). Used in the snapshot sequence. | scripts/afg2225_session.py<br>SKILL.md |
| `OUTPut[1&#124;2]:LOAD` | set/query | `DEFault` (50 Ω) / `INFinity` (>10 kΩ) | **仅作参考设置**：实际负载不同则幅度与偏置随之变化（手册 p. 143）。且**在 ARB/MOD/SWEEP/BURST 激活时不可用**（p. 143）。切到 high-Z 时幅度/偏置翻倍，dBm 自动回落 Vpp。 | basic-waveforms.md (manual pp. 143, 213)<br>bench-setup.md |
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
| `SOURce[1&#124;2]:APPLy?` | query | — | Returns function/frequency/amplitude/offset. Verified raw `"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"\r\n`: quoted on the wire, unquoted in the manual example. | basic-waveforms.md (manual p. 205) |
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
| `SOUR<n>:FREQ?` | query | — | Readback of frequency; verified raw `+5.0000000000000E-01\r\n`. Used in the snapshot sequence and query example. | scripts/afg2225_session.py<br>scripts/test_afg2225_session.py |
| `SOURce[1&#124;2]:AMPlitude` | set/query | 1 mVpp-10 Vpp (50 Ω); 2 mVpp-20 Vpp (high-Z); 1-5 Vpp (50 Ω) at 20-25 MHz | Amplitude doubles from 50 Ω to high-Z. | basic-waveforms.md (manual pp. 209-210)<br>SKILL.md |
| `SOUR<n>:AMPL?` | query | — | **Rejected by V2.05**: no response, queue read `-113 Undefined header`; `? MAX` and `? MIN` are also rejected. Use `SOUR<n>:AMPLITUDE?` instead. | scripts/afg2225_session.py<br>captures/amplitude-short-rejected.empty |
| `SOURce[1&#124;2]:DCOffset` | set/query | ±5 Vpk ac+dc (50 Ω); ±10 Vpk (high-Z); ±2.5 Vpk (50 Ω) at 20-25 MHz; constraint `&#124;Voffset&#124; < Vmax - Vpp/2` | Offset doubles from 50 Ω to high-Z. Community report (unverified): positive DC offset with ARB can invert the signal; no automatic workaround. | basic-waveforms.md (manual pp. 210, 213)<br>SKILL.md |
| `SOUR<n>:DCO?` | query | — | Helper short form for offset readback; used in the snapshot sequence. | scripts/afg2225_session.py |
| `SOURce[1&#124;2]:VOLTage:UNIT` | set/query | `VPP` / `VRMS` / `DBM` | **全局默认单位**：此后所有未带单位的幅度命令都按此解释；切到 high-Z 时 dBm 不可用且自动回落 Vpp。不读回该命令，任何幅度数值都无法解释。手册 pp. 214-215。 | basic-waveforms.md (manual pp. 214-215)<br>scripts/afg2225_session.py |
| `SOURce<n>:VOLT:UNIT?` | query | — | Amplitude unit readback; verified raw `VPP\r\n`. `snapshot` pairs it with `SOUR<n>:AMPLITUDE?` (the long form). | scripts/afg2225_session.py |
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
| `DATA:DAC VOLATILE,<start>,{<binary block>&#124;v,...}` | set | IEEE 488.2 `#<digits><length><payload>`, two bytes per point (16-bit signed)；码值 ±511 | **±511 对应设定 Vpp 的峰值，不是满量程**：5 Vpp、0 偏置时 511 相当于 2.5 V；码值跨度不足只限制分辨率，不缩小 Vpp（手册 p. 261）。二进制字节序**手册未规定**，必须显式 `--byte-order little&#124;big` 并保持 `UNVERIFIED`。手册示例 `DATA:DAC VOLATILE, #216 Binary Data` 声称 5 值 / 16 字节但 5 × 2 = 10 字节 —— 保留该缺陷，长度按点数计算。 | arbitrary-waveform.md (manual p. 261)<br>scripts/afg2225_protocol.py<br>SKILL.md |
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
| `COUNter:STATe` | set/query | `{ON&#124;OFF}` | **必须显式使能**；未使能时 `VALue?` 仍返回看似正常的数字。使能后需等待至少一个 `GATe` 时间再读。实测 `COUN:STAT?` 返回 `0\r\n`（关闭）。手册 pp. 266-267。 | modulation-sweep-burst.md (manual pp. 266-267)<br>scripts/afg2225_session.py |
| `COUNter:GATe` | set/query | `{0.01&#124;0.1&#124;1&#124;10}` | 闸门时间（秒）；越长分辨率越高、刷新越慢，须与读数一起记录。手册 pp. 266-267。 | modulation-sweep-burst.md (manual pp. 266-267) |
| `COUNter:VALue?` | query | — | 返回 Hz；计数器关闭时读数无效。实测关闭状态下返回 `+0.0000E+00\r\n`，不是测量值。手册 pp. 266-267。 | modulation-sweep-burst.md (manual pp. 266-267) |

## Phase and coupling

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `SOURce[1&#124;2]:PHASe` | set/query | -180..180 | Channel phase. | modulation-sweep-burst.md (manual pp. 267-268) |
| `SOURce[1&#124;2]:PHASe:SYNChronize` | event | — | Phase synchronisation. | modulation-sweep-burst.md (manual pp. 267-268) |
| `FREQuency:COUPle:MODE` | set/query | `{OFF&#124;OFFSet&#124;RATio}` | Frequency coupling mode. | modulation-sweep-burst.md (manual pp. 268-270) |
| `SOURce[1&#124;2]:FREQuency:COUPle:OFFSet` | set/query | `{frequency}` | 频率耦合的偏置量（CH2 减 CH1），例如 `SOUR1:FREQ:COUP:OFFS 2khz`；查询返回 `+2.0000E+03` 形式的 NR3。仅当 `MODE` 为 `OFFSet` 时生效（手册 p. 269）。 | manual p. 269 |
| `SOURce[1&#124;2]:FREQuency:COUPle:RATio` | set/query | `{ratio}` | 频率耦合比例（CH2 比 CH1），例如 `SOUR1:FREQ:COUP:RAT 2`；查询返回 `+2.0000E+00` 形式的 NR3。仅当 `MODE` 为 `RATio` 时生效（手册 p. 269）。 | manual p. 269 |
| `AMPLitude:COUPle:STATe` | set/query | `{ON&#124;OFF}` | 幅度耦合开关；开启后写 CH1 会同时改写 CH2 的幅度**和偏置**，此时读 CH2 得到的不是调用方设定的值。手册 pp. 268-270。 | modulation-sweep-burst.md (manual pp. 268-270) |
| `TRACk` | set/query | `{ON&#124;OFF&#124;INVerted}` | 通道跟踪；`ON` 把 CH1 镜像到 CH2，`INVerted` 反相镜像。开启后 CH2 的读数不再独立。手册 pp. 268-270。 | modulation-sweep-burst.md (manual pp. 268-270) |

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
- **Amplitude units are global state**: `VOLTage:UNIT` sets the default unit for
  every later amplitude command (pp. 214-215), so an amplitude number without a
  matching `VOLTage:UNIT?` readback cannot be interpreted. The helper always
  appends `VPP` for APPLy, which makes its own commands deterministic but hides
  the instrument default; `snapshot` now reads the unit back.
- **Load is a reference, not a measurement**: `OUTPut:LOAD` does not adapt to
  the real load, and it is documented as unusable while ARB/MOD/SWEEP/BURST is
  active (p. 143). A high-Z reference into a 50 Ω load gives half the requested
  amplitude.
- **`DATA:DAC` ±511 is peak, not full scale** (p. 261): a reduced code span
  limits resolution, not Vpp.
- **Counter defaults off**: `COUNter:VALue?` without `COUNter:STATe ON` returns a
  number that is not a valid measurement.
- **`FUNC` can rewrite amplitude and frequency** (p. 206), so a
  `SOUR<n>:AMPLITUDE?`/`FREQ?` readback after a shape change may differ from
  what was requested.
- **High-Z amplitude derating**: 2-10 Vpp at 20-25 MHz, not the flat 2-20 Vpp.
- **Serial defaults**: the manual lists no baud/data/parity/stop defaults;
  `115200 8N1` is the helper default, not a manual requirement. The verified
  link also answered at 9600, so the host baud rate is not a device setting.
- **`OUTP1 ON` vs `SOURCE1:OUTPUT ON`**: the community report that
  `SOURCE1:OUTPUT ON` worked where `OUTP1 ON` did not is unverified. This table
  deliberately does not list `SOURCE[1&#124;2]:OUTPut` as a supported command.
- **Verified scope**: the 2026-11-26 run covered identity, the two-line error
  queue, read-only queries, and single-parameter write/readback/restore of
  `SOUR1:FREQ`, `SOUR1:AMPLITUDE`, and `SOUR1:DCO`. APPLy/output writes, ARB
  `DATA:DAC`, modulation, sweep, burst, counter enable/measurement, and
  calibration remain `documented` or `not_checked`.
- **No full command enumeration existed when the file was first written.** The
  original table was assembled from the Skill's own documents and scripts; the
  manual's `Command List` (pp. 189-192) was only enumerated on 2026-11-20, which
  is why the last two rows of the COUPLE table carried no real header before
  then. The two missing forms found in that pass were added and no others.
- **Detail pages, not the list, decide syntax.** The `Command List` is a table of
  contents; where it and a command page disagree (for example
  `COUNTER:STATE` on p. 191 versus `COUNter:STATe` on p. 266), the command page
  and the query/set syntax lines on it are what this table follows.
- **Query forms not individually recorded**: `FUNC?`/`FREQ?`/`DCO?`/
  `OUTP<n>?`/`OUTP<n>:LOAD?` appear in the live helper and were captured on
  2026-11-26; `AMPL?` is rejected, so the helper uses `AMPLITUDE?`. `*IDN?`,
  `SYSTem:ERRor?`, and the captured read-only queries are the response formats
  the Skill actually documents.
- **Two provenance tiers.** Rows derived from `SKILL.md`, the task references,
  and the scripts can carry values the Skill itself checked; rows marked only
  `manual p. N` in the Source column were transcribed from the manual's command
  page and are not cross-checked by any Skill document.
- **Ranges the skill never recorded**: `*ESE`/`*SRE` values, `FSK:INT:RATE`,
  `BURS:NCYC`, `BURS:INT:PER`, `BURS:TRIG:*`, and trigger-source discretes still
  show `—` above because the Skill never recorded them; the manual pages that
  hold them are cited on each row and must be read before use. The coupling
  offset and ratio headers, previously recorded only as the bare words
  "offset, ratio", are now written as `SOURce[1|2]:FREQuency:COUPle:OFFSet` and
  `SOURce[1|2]:FREQuency:COUPle:RATio` (manual p. 269).
- **Not covered by any skill document**: front-panel save/recall menus,
  firmware update, calibration, and AWES waveform transfer; the Skill
  deliberately does not automate them.
