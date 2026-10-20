# Parser Support Record

- Parser status: `hardware-verified` / `firmware-scoped` for DC voltage and DC
  current over RS-232; `documented` for every other function and interface
- Hardware verification: `true` (2026-10-20)
- Verified model/firmware/interface: Keithley Model 2000, serial `0944865`,
  firmware `A17` / `A02`, RS-232 9600 8N1, front terminals (`INPUT HI`/`INPUT LO`
  for voltage, `AMPS`/`INPUT LO` in series for current)
- Manual source: [Model 2000 Multimeter User's Manual, 2000-900-01 Rev. J / August 2010](https://download.tek.com/manual/2000-900_J-Aug2010_User.pdf)
- Bundled scripts: `keithley2000_scalar.py` (one reading or one queue line), `keithley2000_protocol.py` (`*IDN?`, configuration readbacks, whole queue drain, function/unit mapping, reading assessment), `keithley2000_session.py` (optional RS-232 transport with lazy pyserial, `--dry-run`, guard flags, raw capture, `config` readback/setters for NPLC/digits/filter/REL, `constants` for identity/options/calibration metadata, and an exclusive port lock)
- Supported data kinds: one scalar ASCII reading, one or more error-queue lines, identity, or configuration readbacks
- Command evidence: all eleven front-panel functions were configured and read with open inputs on 2026-10-20; overflow (`+9.9E37`) appeared on resistance, 4-wire, continuity, diode, and temperature, while frequency/period reported `0` and DCV floated to tens of millivolts. This proves the command path, not measurement accuracy. On the same date the rate (NPLC 0.01-10), DIGits 4-7, REL set/acquire, filter MOVing/REPeat, and read-only instrument constants (SCPI version, line frequency, front/rear switch, power-on setup, calibration count/date/due/lock) were exercised with the same open inputs; evidence is in `assets/captures/rate-filter-rel-digits/`.
- Known limitations: no binary, block/buffer, or scanner parser; automatic classification recognizes only documented error-queue sentinels, while other queue responses require explicit error-queue mode; calibration, input-fuse continuity, and acquisition freshness are not inferred; `:READ?` with continuous initiation ON yields `-213,"Init ignored"` and a continuous-acquisition value, which the session helper reports as `UNVERIFIED` / `not_newly_triggered` (`-213` also appears when `:INITiate` is sent while the instrument is not idle); a floating input and a no-signal frequency/period can look like a valid reading; an armed `BUS` trigger with a pending fetch blocks the output queue until a device clear (`0x03`, exposed as `unblock`); the live session is verified against one instrument and one baud rate

Raw responses and the full exchange are in `assets/captures/`; the scope and
remaining gaps are recorded in `references/hardware-verification.md`.

Do not extend `hardware-verified` beyond the recorded model, firmware,
interface, and functions. Any new instrument, firmware, or measurement type
requires its own preserved response, `*IDN?` identity, and test date.
