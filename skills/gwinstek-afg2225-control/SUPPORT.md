# Parser Support Record

- Parser status: `hardware-verified` for the captured subset below; `documented`
  for every other command family
- Hardware verification: `true` (2026-11-26)
- Verified model/firmware/interface: GW Instek AFG-2225, serial `GEP902745`,
  firmware `V2.05`, USB CDC-ACM VID:PID `2184:001c` at `/dev/ttyACM0`,
  115200 8N1; the same link also answered at 9600 baud
- Manual source: [AFG-2225 Series User Manual, GW Instek part no. 82RF-22250M01](https://www.gwinstek.com/en-global/products/detail/AFG-2225) (local copy `ref/编程手册.pdf`)
- Supported data kinds: `identity`, `numeric`, `status-record` (error queue), and `waveform` (arbitrary DAC command) from saved data; the captured subset covers identity, numeric readback, and error-queue responses
- Evidence: raw bytes are in `assets/captures/` with a hash index in
  `assets/captures/captures.jsonl`; the full ordered exchange and probe records
  are in `artifacts/hw-verify/afg2225-20261126/` (git-ignored, local reference
  only)

## Verified subset (2026-11-26)

| Claim | Captured evidence |
|---|---|
| Identity parses as `GW INSTEK,AFG-2225,SN:GEP902745,V2.05`; response ends `\r\n` | `assets/captures/idn.txt` |
| Error queue is two lines: CRLF-terminated code plus an unterminated message, for example `-102\r\nSyntax error.` | `assets/captures/error-syntax.txt`, `assets/captures/error-undefined-header.txt` |
| Empty error queue is a blank code line plus `No error.` (`\r\nNo error.`) | `assets/captures/error-empty.txt` |
| Read-only queries answer for function, frequency, amplitude (long form only), offset, output state, load, phase, duty cycle, counter state/value, and `APPL?` | `assets/captures/` and `captures.jsonl` |
| `SOUR1:APPL?` returns a quoted composite, for example `"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"` | `assets/captures/apply-query.txt` |
| `SOUR1:FREQ`, `SOUR1:AMPLITUDE`, and `SOUR1:DCO` accept a single-parameter write, read back, and restore the original value; the output stayed OFF and the error queue stayed empty | `assets/captures/freq-write-readback.txt`, `amplitude-write-readback.txt`, `dco-write-readback.txt`, `restored-apply.txt` |
| One output-on loopback: `SIN`, 1 kHz, 1 Vpp (50 ohm reference), 0 V offset into a GDS-2104A CH1 at 1 MOhm measured 1.000E+03 Hz, 2.060E+00 Vpp, 7.27E-01 V RMS; `OUTP1 OFF` returned 0 and the original setup was restored | `artifacts/hw-verify/loopback-20261126/loopback-result.json` (git-ignored) |

This proves the command and framing path and one amplitude point; it is not
voltage accuracy, flatness, or calibration.

## Still unverified

- Binary ARB byte order. No `DATA:DAC` upload was sent, and volatile ARB memory
  has no readback/restore path in this Skill; ASCII decimal lists remain the
  default safe path and binary uploads stay `UNVERIFIED`.
- Modulation, sweep, and burst were not exercised command by command; their
  state, source, range, and interaction claims remain `documented`.
- APPLy writes were not sent (they turn the output on as a side effect).
  `OUTPut ON/OFF` was exercised once in the 1 kHz loopback above; behaviour
  across waveforms, levels, loads, and other frequencies remains `documented`.
- Amplitude flatness and voltage accuracy are not verified; the single 1 kHz
  loopback point does not replace a calibration.
- Counter enable and measurement were not exercised; `COUN:VAL?` was read only
  while `COUN:STAT=0`, so it is not a measurement.
- `SOUR<n>:AMPL?` is rejected by V2.05 with no response and
  `-113 Undefined header`; only `SOUR<n>:AMPLITUDE?` was verified.
- `115200 8N1` is the helper default, not a manual requirement; the link also
  answered at 9600, so the host baud rate is not a device setting.
- Accuracy, calibration, load-dependent amplitude/offset, and the community
  `SOURCE1:OUTPUT ON` / ARB DC-offset observations remain unverified.

Do not extend this record beyond the captured model, firmware, interface, and
test date. Any new instrument, firmware, or command family needs its own
preserved response, `*IDN?` identity, and test date.
