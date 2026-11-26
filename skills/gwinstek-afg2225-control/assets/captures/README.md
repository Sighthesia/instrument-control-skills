# Real Hardware Captures

These files are **real AFG-2225 responses** captured on 2026-11-26 from:

- GW Instek AFG-2225, serial `GEP902745`, firmware `V2.05`
- USB CDC-ACM VID:PID `2184:001c` at `/dev/ttyACM0`, 115200 8N1
- Output queried OFF before and after; no APPLy, no `OUTPut ON`, no
  `*RST`/`*SAV`/`*RCL`, no calibration

Every fixture is the exact response byte sequence, including `\r\n`, quotes, and
the unterminated error-queue message line. `captures.jsonl` records the command,
length, hex, base64, SHA-256, and the source file under
`artifacts/hw-verify/afg2225-20261126/` (git-ignored, local reference only).

| Fixture | Command | Response (Python byte literal) |
|---|---|---|
| `idn.txt` | `*IDN?` | `b"GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n"` |
| `version.txt` | `SYST:VERS?` | multi-line; see `captures.jsonl` |
| `output-off.txt` | `OUTP1?` | `b"0\r\n"` |
| `func-sine.txt` | `SOUR1:FUNC?` | `b"SIN\r\n"` |
| `freq.txt` | `SOUR1:FREQ?` | `b"+5.0000000000000E-01\r\n"` |
| `volt-unit-vpp.txt` | `SOUR1:VOLT:UNIT?` | `b"VPP\r\n"` |
| `amplitude.txt` | `SOUR1:AMPLITUDE?` | `b"+3.000E+00\r\n"` |
| `amplitude-max.txt` | `SOUR1:AMPLITUDE? MAX` | `b"+1.000E+01\r\n"` |
| `amplitude-min.txt` | `SOUR1:AMPLITUDE? MIN` | `b"+1.000E-03\r\n"` |
| `amplitude-short-rejected.empty` | `SOUR1:AMPL?` | zero bytes; next queue read `-113` |
| `dco-zero.txt` | `SOUR1:DCO?` | `b"+0.00E+00\r\n"` |
| `output-load-def.txt` | `OUTP1:LOAD?` | `b"DEF\r\n"` |
| `phase-zero.txt` | `SOUR1:PHAS?` | `b"+0.000E+00\r\n"` |
| `duty-50.txt` | `SOUR1:SQU:DCYC?` | `b"+5.00E+01\r\n"` |
| `counter-state-off.txt` | `COUN:STAT?` | `b"0\r\n"` |
| `counter-value-off.txt` | `COUN:VAL?` | `b"+0.0000E+00\r\n"`; counter off, not a measurement |
| `apply-query.txt` | `SOUR1:APPL?` | `b'"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"\r\n'` |
| `opc.txt` | `*OPC?` | `b"1\r\n"` |
| `esr.txt` | `*ESR?` | `b"32\r\n"`; single capture, value may change |
| `stb.txt` | `*STB?` | `b"164\r\n"`; single capture, value may change |
| `error-syntax.txt` | `SYST:ERR?` | `b"-102\r\nSyntax error."` |
| `error-undefined-header.txt` | `SYST:ERR?` | `b"-113\r\nUndefined header."` |
| `error-empty.txt` | `SYST:ERR?` | `b"\r\nNo error."` |
| `freq-write-readback.txt` | `SOUR1:FREQ?` after writing 1234.5 | `b"+1.2345000000000E+03\r\n"` |
| `amplitude-write-readback.txt` | `SOUR1:AMPLITUDE?` after writing 1.5 | `b"+1.500E+00\r\n"` |
| `dco-write-readback.txt` | `SOUR1:DCO?` after writing 0.5 | `b"+5.00E-01\r\n"` |
| `restored-apply.txt` | `SOUR1:APPL?` after restoring original values | `b'"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"\r\n'` |

Observed quirks, recorded rather than corrected:

- The error queue is two lines; the message line has no terminator. The empty
  queue is a blank code line followed by `No error.` (`\r\nNo error.`).
- `SOUR1:APPL?` returns a quoted string even though the manual example omits the
  quotes.
- `SOUR1:AMPL?` (and `? MAX` / `? MIN`) is rejected by V2.05; the long form
  `SOUR1:AMPLITUDE?` works.
- There is no SCPI beeper command. `SYST:BEEPer?`/`SYST:BUZZ?` queued
  `-113 Undefined header`; `:BUZZER?` queued `-102 Syntax error`. The beeper is
  panel-only (UTIL -> F3 System -> F3 Beep -> F2 OFF).
- The global amplitude unit was `VPP`, so `SOUR1:AMPLITUDE?` reads 3.0 Vpp; a
  bare amplitude number is not interpretable without `VOLT:UNIT?`.

Synthetic failure-mode fixtures are kept separately in `../fixtures/` and are
never hardware evidence.
