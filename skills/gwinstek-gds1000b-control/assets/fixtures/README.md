# Fixture provenance

Every file in this directory is **synthetic**. None is a real instrument
capture, and none may be presented as hardware evidence.

Manual basis: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015
(local evidence copy `ref/编程指令手册.pdf`; PDF physical pages cited below).
All model names, serial prefixes, error strings, and header field names come
from that manual. Values are chosen for parser coverage, not measured.

| Fixture | Basis | Expected status |
|---|---|---|
| `identity.txt` | `*IDN?` shape `GW,GDS-<model>,P<serial>,V<version>` (PDF pp. 33-34); `GDS-1102B` is a 2-channel model | `COMPLETE` |
| `identity-wrong-model.txt` | Same shape with an absent `GDS-9999B` model | `INVALID` |
| `identity-missing-firmware.txt` | Same shape with the firmware field omitted | `INCOMPLETE` |
| `measure-frequency.txt` | `:MEASure:FREQuency?` returns `<NR3>` (PDF p. 86); value is arbitrary | `COMPLETE` |
| `measure-chan-off.txt` | Documented `Chan Off` return for an inactive source (PDF pp. 81-105) | `INCOMPLETE` |
| `error-none.txt` | Empty-queue example `+0, "No error."` (PDF pp. 250-253) | `COMPLETE` |
| `error-undefined.txt` | Documented error format `code, "message"` (PDF pp. 250-253); message text is an example only | `UNSUPPORTED` in auto mode, `UNVERIFIED` in explicit error-queue mode |
| `error-overflow.txt` | Documented `-350, "Queue overflow"` (PDF pp. 250-253) | `INCOMPLETE` |
| `waveform-valid.bin` | ASCII header + `Waveform Data;` + `#40008` + big-endian int16 codes `0, 25, -25, 50`; `Memory Length,4`; `Vertical Scale,5.000E-01` (PDF pp. 41-43) | `COMPLETE` (calibration `UNVERIFIED`) |
| `waveform-truncated.bin` | Declares 8 payload bytes, supplies 4 | `INCOMPLETE` |
| `waveform-length-mismatch.bin` | `Memory Length,4` but the block declares 4 bytes (2 points) | `INVALID` |
| `waveform-headerless.bin` | `#40008` + 8 bytes, as produced with `:HEADer OFF` (PDF p. 46) | `UNVERIFIED` |
| `waveform-bad-header.bin` | ASCII header present, `Waveform Data;` marker absent | `INVALID` |

`assets/expected-*.json` hold the status and stable fields asserted by the
offline tests. They are not captures either.

Notes:

- The manual's own waveform example prints `Vertical Scale,5.000E+00` in the
  header while its calculation uses `0.5`. The fixture deliberately uses
  `5.000E-01` and the parser never "repairs" a scale it reads; calibration stays
  `UNVERIFIED` either way.
- Binary files are raw response bytes, including the ASCII header; they are not
  encoded or compressed.
