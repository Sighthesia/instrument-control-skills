# Command Reference (GPD-4303S)

Source: *GPD-X303S Series User Manual*, GW Instek part no. `82PD-433S0MC1`,
REMOTE CONTROL chapter, PDF pp. 43-52. Pages below are PDF physical pages.
This index lists the 18 command forms the manual documents; anything absent must
be verified against the manual and labelled `documented` before use.

Evidence labels are per command **and per channel**, not per Skill.
`hardware-verified` means a real response for **that query form on that
channel** was captured on GPD-4303S serial `EP924162`, firmware `V2.08`,
`/dev/ttyUSB0` at 9600 8N1, on 2026-11-19; the same unit was re-queried later
the same day (`verify_all`, 11:38:50Z). CH3/CH4 now have preserved raw response
bytes under `assets/fixtures/captures/`: `006`-`009` for
VSET3/VSET4/ISET3/ISET4 and `010`-`013` for VOUT3/VOUT4/IOUT3/IOUT4. CH1/CH2
retain the earlier VOUT/IOUT captures (`002`-`005`) and transcript-recorded
VSET/ISET responses. No write command was ever sent, so no write command is
`hardware-verified`.

## Conventions (manual p. 46)

| Item | Rule |
|---|---|
| Case | Commands are not case-sensitive. Confirmed on the verified unit: `vout1?` and `Status?` answered normally. |
| Command format | `ISET<X>:<NR2>` + terminator: header, output channel, `:`, parameter, terminator. |
| Terminator | `0x0A` (LF) or `0x0D0A` (CR LF). The verified sessions sent CR LF and the instrument replies CR LF. |
| Length | "The command length must be 15 characters or less." The manual does not say whether the terminator counts, so keep the body at 14 characters or fewer before sending anything. |
| Channel `<X>` | `1` = CH1, `2` = CH2, and for the 4303S `3` = CH3, `4` = CH4 (manual pp. 48-49; confirmed by `HELP?`). |
| Parameter types | `<Boolean>` = `0`/`1`; `<NR1>` = integer; `<NR2>` = decimal number (manual p. 46). |
| Response time | "Minimum 10ms" for every command; "Minimum 50ms" for `HELP?`, measured at 115200 bps (manual pp. 48-52). At 9600 bps the transfer time dominates: `HELP?` returns 934 bytes, about 1 s of wire time. |
| Response format | The manual documents no response format for the value queries. The observed format is fixed-width NR2 with three decimals plus a unit letter, for example `24.000V`, `1.000A`, `0.002A`. |

## Query commands

| Command | Channel / parameter | Return format | Page | Evidence |
|---|---|---:|---:|---|
| `*IDN?` | — | `GW INSTEK,<model>,SN:<serial>,V<m>.<n>` — observed `GW INSTEK,GPD-4303S,SN:EP924162,V2.08` (no space after commas). Manual shows `GW INSTEK, GPD-X3303, SN: xxxxxxxx, Vx.xx`, so the spacing and model string in the manual are not faithful. | 50-51 | `hardware-verified` |
| `VSET<X>?` | `1`-`4` | Voltage setpoint, observed `24.000V` on CH1/CH2, `3.300V` on CH3, `2.500V` on CH4. Unit `V`, three decimals. | 49 | `hardware-verified` on CH1-CH4 (CH3/CH4 raw files `006`, `007`) |
| `ISET<X>?` | `1`-`4` | Current setpoint, observed `1.000A` on CH1/CH2/CH4, `3.000A` on CH3. Unit `A`, three decimals. | 48 | `hardware-verified` on CH1-CH4 (CH3/CH4 raw files `008`, `009`) |
| `VOUT<X>?` | `1`-`4` | Measured output voltage, observed `0.000V` with the output off and `23.994V` / `23.987V` on CH1/CH2 while energised. Unit `V`. | 49 | `hardware-verified` on CH1-CH4 (raw files `002`-`005` and `010`, `011`) |
| `IOUT<X>?` | `1`-`4` | Measured output current, observed `0.000A` with the output off and `0.002A` on CH1 while energised. Unit `A`. | 49 | `hardware-verified` on CH1-CH4 (raw files `003`, `005`, `012`, `013`) |
| `STATUS?` | — | Exactly eight characters of `0`/`1`, observed `00111010`, `11110110`, `00110010`. Bit meanings are documented on p. 50; the character order is not. | 50 | `hardware-verified` (framing); bit decode `UNVERIFIED` |
| `HELP?` | — | Command list, 18 CR-separated lines ending in CR LF, 934 bytes observed. `HELP?` itself is not listed (manual p. 52). | 52 | `hardware-verified` (raw `assets/fixtures/captures/help-transcribed.raw`, reconstructed from the session transcript) |
| `ERR?` | — | "Returns the last error message" (manual p. 52). Not exercised; this Skill never sends it. | 52 | `documented` |

`STATUS?` bit map (manual p. 50), quoted as printed:

| Bit | Item | Description |
|---|---|---|
| 0 | CH1 | `0`=CC mode, `1`=CV mode |
| 1 | CH2 | `0`=CC mode, `1`=CV mode |
| 2, 3 | Tracking | `01`=Independent, `11`=Tracking series, `10`=Tracking parallel |
| 4 | Beep | `0`=Off, `1`=On |
| 5 | Output | `0`=Off, `1`=On |
| 6, 7 | Baud | `00`=115200bps, `01`=57600bps, `10`=9600bps |

The manual does not say whether the leftmost character is bit 0 or bit 7. See
[response-and-evidence.md](response-and-evidence.md) for the capture-consistent
default and the reason the alternate decode is always printed next to it.
The `00110010` capture corroborates the `lsb-first` default twice: bits 6, 7 read
`10` -> 9600 bps, matching the 9600 8N1 link that produced the response, and bit
5 reads `0` -> output off, matching `VOUT1?`-`VOUT4?` all reading `0.000V`.
Neither observation is a manual statement, so the check remains `not_checked`
with reason `status_bit_order_not_documented`. Under the same decode the
tracking field reads `11` (series); the panel has not confirmed that mode.

## Set and mode commands

None of these was sent. Every one changes instrument state; the "side effect"
column is what the manual says happens, not something observed here.

| Command | Parameter range | Side effect / notes | Page | Evidence |
|---|---|---|---:|---|
| `ISET<X>:<NR2>` | `0`-`3.200` A; `X` = 1-4 | Sets the current limit for the channel. Out-of-range input is expected to answer `Data out of range` (p. 46). | 48 | `documented` |
| `VSET<X>:<NR2>` | `0`-`32.000` V; `X` = 1-4 | Sets the voltage for the channel. The programming range (32.000 V) is wider than the 30 V CH1/CH2 rating (p. 55); do not treat 32 V as a safe setting. | 48 | `documented` |
| `TRACK<NR1>` | `0` independent, `1` series, `2` parallel | Changes the output topology: series doubles voltage (0-60 V), parallel doubles current (0-6 A). Automatically turns the output off (p. 25). CH2 output cannot be set while tracking (error `e`, p. 47). | 49 | `documented` |
| `BEEP<Boolean>` | `0` off, `1` on | Beep only; the beep is enabled by default and beeps on output on/off, mode switching, save/recall, and panel lock (p. 25). | 50 | `documented` |
| `OUT<Boolean>` | `0` off, `1` on | **No channel parameter.** The panel Output key switches all outputs at once (p. 25) and the panel lock does not block it (p. 53). `OUT1` is an enable, not a toggle, and `OUT1?` does not exist on the verified unit; `OUT0` is the only observed off command. | 50 | `documented` |
| `RCL<NR1>` | `1`-`4` | Recalls a stored panel setup. Always recalls output on/off, panel lock, and beep as off, and turns the output off (pp. 25, 42). | 51 | `documented` |
| `SAV<NR1>` | `1`-`4` | Stores the panel setup. Always stores output on/off, panel lock, and beep as off, and turns the output off (pp. 25, 41). | 51 | `documented` |
| `BAUD<NR1>` | `0` 115200, `1` 57600, `2` 9600 | Changes the link rate of the session that sends it. Default 9600 bps (p. 51). | 51 | `documented` |
| `LOCAL` | — | Leaves remote mode; the front panel is usable again and the LOCK indicator goes out (pp. 44, 51). | 51 | `documented` |
| `REMOTE` | — | Enters remote mode and locks the panel keys (pp. 44, 48). The panel lock does not stop the Output key (p. 53). | 48 | `documented` |

## Error messages (manual pp. 46-47)

The GPD answers an unacceptable command with the message text itself, not with a
queue code; the verified unit answered every unknown command with
`Invalid Character.`.

| # | Manual text | Meaning | Manual example | Page | Observed on this firmware |
|---|---|---|---|---:|---|
| a | `Program mnemonic too long` | The command length must be 15 characters or less. | — | 46 | no |
| b | `Invalid character` | Invalid characters, such as symbols. | `VOUT#` | 46 | **yes**, written `Invalid Character.` (capital `C`, trailing period) |
| c | `Missing parameter` | The parameter is missing. | `VSET:` (should have a number) | 46 | no |
| d | `Data out of range` | The value exceeds the specification. | `VSET:33` (should be ≤ 32 V) | 46 | no |
| e | `Command not allowed` | The command is not allowed in this circumstance. | setting CH2 output while in tracking mode | 47 | no |
| f | `Undefined header` | The command does not exist, or the syntax is wrong. | — | 47 | no; the verified unit answered unknown and long-SCPI commands (`SYST:ERR?`, `*OPT?`, `TRACK?`) with `Invalid Character.` instead |

Consequences for this Skill: (b) is the only message with hardware evidence, and
it is the message the device used for command forms the manual would classify as
(f). Do not build a diagnosis on the manual's letter mapping without checking the
actual reply on your unit.

## Command coverage

- 18 documented command forms: 8 queries (`*IDN?`, `VSET<X>?`, `ISET<X>?`,
  `VOUT<X>?`, `IOUT<X>?`, `STATUS?`, `HELP?`, `ERR?`) and 10 set/mode commands
  (`ISET<X>:<NR2>`, `VSET<X>:<NR2>`, `TRACK<NR1>`, `BEEP<Boolean>`,
  `OUT<Boolean>`, `RCL<NR1>`, `SAV<NR1>`, `BAUD<NR1>`, `LOCAL`, `REMOTE`).
- 7 of the 8 query forms are `hardware-verified` on all four channels: `*IDN?`,
  `STATUS?`, `HELP?`, and `VSET<X>?` / `ISET<X>?` / `VOUT<X>?` / `IOUT<X>?` with
  `X` = 1-4. `ERR?` stays `documented`.
- 10 set/mode commands are `documented` only, and the live helper refuses all of
  them before writing to the port.
