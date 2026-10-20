# Parser Support Record

- Parser status: `hardware-verified` / `firmware-scoped` for DC voltage and DC
  current over RS-232; `documented` for every other function and interface
- Hardware verification: `true` (2026-10-20)
- Verified model/firmware/interface: Keithley Model 2000, serial `0944865`,
  firmware `A17` / `A02`, RS-232 9600 8N1, front terminals (`INPUT HI`/`INPUT LO`
  for voltage, `AMPS`/`INPUT LO` in series for current)
- Manual source: [Model 2000 Multimeter User's Manual, 2000-900-01 Rev. J / August 2010](https://download.tek.com/manual/2000-900_J-Aug2010_User.pdf)
- Supported data kinds: one scalar ASCII reading or one error-queue line from a saved response
- Known limitations: no transport driver; no binary, multi-reading, or scanner parser; automatic classification recognizes only documented error-queue sentinels, while other queue responses require explicit error-queue mode; calibration, input-fuse continuity, and acquisition freshness are not inferred; `:READ?` with continuous initiation ON yields `-213,"Init ignored"` and a continuous-acquisition value

Raw responses and the full exchange are in `assets/captures/`; the scope and
remaining gaps are recorded in `references/hardware-verification.md`.

Do not extend `hardware-verified` beyond the recorded model, firmware,
interface, and functions. Any new instrument, firmware, or measurement type
requires its own preserved response, `*IDN?` identity, and test date.
