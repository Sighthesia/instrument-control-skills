# Fixture provenance

`hardware/` contains real responses captured from the GDS-2104A used for this
Skill. `synthetic/` contains constructed anomalies used only to exercise
rejection paths. A synthetic fixture is never evidence that the instrument
behaves that way.

## Capture record

- Instrument: GW Instek GDS-2104A, serial `GEN182193`, firmware `V1.18`
- Interface: USB CDC-ACM, `/dev/ttyACM1`, 115200 8N1, LF terminator
- Host capture date: 2026-11-26 (UTC); instrument clock showed 26-Nov-26
- Raw evidence directory (git-ignored):
  `artifacts/hw-verify/gds2000a-20261126/`
- Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013;
  the local copy is converted text, so only table-of-contents and List of
  Commands page numbers (pp. 24-34) are cited.

## Hardware fixtures

| File | SHA-256 | Source and expected status |
|---|---|---|
| `identity.txt` | `b021fdb934807d6e0133265026cfb25179263ce2f55d2d7e116f9611c08c3e9c` | `*IDN?` reply `GW,GDS-2104A,GEN182193,V1.18`; `COMPLETE` |
| `buzzer.txt` | `0855c353c8a126265186a268bbc57583247a8d131a7e602f0e48ac6105a09c48` | `:BUZZER?` reply `OFF`; value preserved, not parsed as a measurement |
| `error-none.txt` | `0869b2f462e7c8b16c895c21b1d15090442fc3880da74a9452a612ba949f27bd` | `:SYSTem:ERRor?` reply `+0, "No error."`; `COMPLETE` |
| `error-undefined-header.txt` | `3d1108cac1138f5c60fcfea36dffcca380c41f8faaffa7cb1e54086c60bcf2ed` | Error-queue reply after the undefined `:MEASure:VPP?`; `UNVERIFIED` |
| `error-parameter-not-allowed.txt` | `84034b815ccee16b158b17f4b774474b1bde9dacfb04d8fd1e939a15cbe9e576` | Error-queue reply after `:ACQuire:MEMory? CH1`; `UNVERIFIED` |
| `measure-pk2pk.txt` | `c3ed45201c5e17cf0f13dab0c7ef99be075df61a21a34ae5d26924b6c56e7ff9` | `:MEASure:PK2PK?` with source `CH1`; `8.000E-02`, `COMPLETE` |
| `measure-ch-off.txt` | `a096f06f216416ce762fedbd774cd032b4823deaab9f9d6d2475ad1ac22d2186` | `:MEASure:PK2PK?` with source `CH2` off; `Ch Off`, `INCOMPLETE` |
| `measure-sentinel.txt` | `35067c52d1c17a4171e718f04bd5a1e039820c84124f53196cfb47e0b9ce0546` | `:MEASUrement:MEAS1:VALue?` while `STATE?` was `0`; `9.9E+37`, treated as `INCOMPLETE` |
| `trigger-frequency-double-lf.txt` | `fef2ce29858d848985950d5668b52aa6b54aea83d4c51d261be4d37188205298` | `:TRIGger:FREQuency?` reply `2.000E+00` followed by two LFs; second LF kept as framing evidence |
| `acquire1-memory.bin` | `2b92d68aa4dd4a5797bbb426228d628ed779fb838a9ce4845c064220e2b04eca` | `:ACQuire1:MEMory?` after `:STOP`: ASCII header + `Waveform Data;` + `#510000` + 10,000 bytes + LF; `COMPLETE` structure, calibration `UNVERIFIED` |
| `display-output.bin` | `1775e99fee32598113ccd88dc0297fcdef0fe11d18e1f2641d29ce5d3b2564e7` | `:DISPlay:OUTPut?` (body-only command, not in the List of Commands): `#538822` + 38,822 bytes + LF; image decode not implemented, `UNVERIFIED` |

The two error fixtures are the error-queue lines returned for those commands;
the failing command itself returned no bytes. They are kept as text because that
is the exact error text the instrument produced.

## Synthetic fixtures

| File | Purpose | Expected status |
|---|---|---|
| `identity-missing-firmware.txt` | three identity fields | `INCOMPLETE` |
| `identity-wrong-family.txt` | model belongs to another generation | `INVALID` |
| `measurement-nan.txt` | non-finite token | `INVALID` |
| `measurement-malformed.txt` | malformed NR3 token | `INVALID` |
| `error-overflow.txt` | documented `-350, "Queue overflow"` shape | `INCOMPLETE` |
| `waveform-truncated.bin` | block declares 8 payload bytes, supplies 4 | `INCOMPLETE` |
| `waveform-length-mismatch.bin` | header says 4 points, block carries 2 | `INVALID` |
| `waveform-headerless.bin` | `#40008` + 8 bytes, as with `:HEADer OFF` | `UNVERIFIED` |
| `waveform-bad-header.bin` | no `Waveform Data;` marker | `INVALID` |
| `waveform-odd.bin` | odd payload byte count | `INVALID` |
| `waveform-trailing.bin` | extra bytes after the block | `INVALID` |

`assets/expected-*.json` are parser outputs for the hardware fixtures; they are
not captures themselves. The waveform expected file records code-domain
statistics only; it never contains a calibrated voltage.
