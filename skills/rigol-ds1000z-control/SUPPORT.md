# Parser Support Record

- Parser status: `firmware-scoped`
- Hardware verification: `true`
- Verified model/firmware/interface: `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4`, 4-channel 70 MHz model, raw TCP socket port 5555, captured 2026-11-20
- Manual source: *MSO1000Z/DS1000Z Programming Guide*, PGA19108-1110, Software Version 00.04.03.SP2, December 2015, and *DS1000Z Series User Guide*, UGA19115-1110, September 2020
- Supported data kinds: `identity` (`*IDN?` / `*SYSTem:MODEL?`), `scalar-measurement` (`:MEASure:*?`), `status-record` (`:SYSTem:ERRor?`), `waveform` (`:WAVeform:PREamble?` + `:WAVeform:DATA?`, NORM/MAXimum/RAW), `screenshot` (`:DISPlay:DATA?`, BMP), and `cursor-readout` (`:CURSor:<family>:*?`, MAN/TRACk/AUTO)
- Known limitations: waveform voltage calibration is unverified and NORM/RAW `yincrement` differ at the same V/div; the manual's software version (00.04.03.SP2) is newer than the verified firmware (00.04.02.SP4), so version-dependent behavior is `documented` only; the `:LAN:` query family answered on hardware but is absent from the Programming Guide and its write forms are refused; `*SAV`/`*RCL`/`:SAVE`/`:RECAll` are undocumented here and refused defensively; `:DISPlay:DATA?` returns three bytes past its declared length and needs trimming; MAXimum-mode bytes, VXI-11 RPC, `AVER`/`HRES` downloads, digital channels, and the `-S` source are unexercised

The hardware evidence behind this record is
`artifacts/rigol-ds1000z/hardware-evidence.md`, with raw captures and SHA-256
values in `artifacts/rigol-ds1000z/raw/`. Every capability statement in
`SKILL.md` and `references/` carries either `hardware-verified` (observed on
firmware 00.04.02.SP4) or `documented`.

Do not upgrade the scope of this record to another model or firmware without
preserving a fresh `*IDN?` response, the model, firmware, interface, and test
date. A different DS1000Z model shares the command set but not the verified
answers: on a DS1054Z or DS1104Z the `command error` list, memory-depth limits,
and screenshot timing must be re-observed before any `hardware-verified` claim is
reused.
