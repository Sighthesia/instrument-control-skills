# Fixture provenance

Every file here is derived from a real capture in `artifacts/rigol-ds1000z/raw/`
(that directory is local-only and git-ignored) or is a documented truncation or
mutation of one. Nothing in this directory was produced by a synthetic signal
generator, and nothing here is a claimed measurement of a new instrument.

Capture scope: `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4`,
raw TCP port 5555, 2026-11-20. Per-file SHA-256 and timing of every raw capture
live in `artifacts/rigol-ds1000z/session-log.json`; the observation log is
`artifacts/rigol-ds1000z/hardware-evidence.md`.

## Real bytes (copied verbatim)

| Fixture | Raw source | Response shape | Expected status |
|---|---|---|---|
| `identity.txt` | `identity-0.raw` | `*IDN?` → `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4\n` | `COMPLETE` |
| `error-queue-undefined.txt` | `error-queue-undefined.raw` | `:SYSTem:ERRor?` → `-113,"Undefined header; keyword cannot be found"\n` | `UNVERIFIED` (a real error is queued) |
| `preamble-norm.txt` | `waveform-norm-preamble.raw` | `:WAVeform:PREamble?` NORM, 1200 points, `yincrement` 0.02 | `COMPLETE` |
| `preamble-raw.txt` | `waveform-raw-preamble.raw` | `:WAVeform:PREamble?` RAW, 4000 points, `yincrement` 0.0209375 | `COMPLETE` |
| `waveform-norm-block.bin` | `waveform-norm-ch1.raw` (1212 bytes) | `:WAVeform:DATA?` NORM: `#9000001200` + 1200 codes + `\n` | `UNVERIFIED` alone (no preamble) |
| `waveform-raw-block.bin` | `waveform-raw-ch1-4000.raw` (4012 bytes) | `:WAVeform:DATA?` RAW: `#9000004000` + 4000 codes + `\n` | `UNVERIFIED` alone (no preamble) |
| `measurement-vpp.txt` | `measurements-ch1.json`, `:MEASure:VPP?` value | `3.040000e+00\n` | `COMPLETE` |
| `measurement-frequency.txt` | `measurements-ch1.json`, `:MEASure:FREQuency?` value | `9.999999e+02\n` | `COMPLETE` |

The CH1 signal during the session was a ~1 kHz square wave, 0–3 V. The NORM
capture reproduces the simultaneous measurements exactly: codes 49…201 with
`zero_code` 51 and `yincrement` 0.02 give −0.04 V … 3.00 V and Vpp 3.04 V, which
is `:MEASure:VMIN?` = −4.000000e-02, `:MEASure:VMAX?` = 3.000000e+00 and
`:MEASure:VPP?` = 3.040000e+00 on the same screen.

## Combined captures (real preamble + real block)

| Fixture | Composition | Expected status |
|---|---|---|
| `waveform-norm-ch1.bin` | `preamble-norm.txt` bytes followed by `waveform-norm-block.bin` bytes | `COMPLETE` |
| `waveform-raw-ch1.bin` | `preamble-raw.txt` bytes followed by `waveform-raw-block.bin` bytes | `COMPLETE` |

The instrument answers `:WAVeform:PREamble?` and `:WAVeform:DATA?` as two
separate responses. A combined file is this repository's replay container: the
preamble line (already LF-terminated) is followed by the untouched IEEE block.
`ds1000z_protocol.py` accepts it because it splits an ASCII prefix from the
leading `#`; nothing inside either part was rewritten.

## Documented answers that were not captured as bytes

| Fixture | Why it is not a capture | Expected status |
|---|---|---|
| `measurement-no-result.txt` (`9.9E37\n`) | The sentinel was observed in this session (`:MEASure:VPP?` and `:MEASure:FREQuency?` with `:MEASure:SOURce CHAN2` while CH2 was off) but only the measurement table was saved, not these two raw replies | `INCOMPLETE` (`value` is `null`, `sentinel` is `9.9E37`) |
| `measurement-syntax-error.txt` (`10.9e+3e+3\n`) | Malformed NR3, constructed to prove that a non-NR3 reply is `INVALID` rather than a number | `INVALID` |
| `error-queue-none.txt` (`0,"No error"\n`) | The empty-queue terminator is documented (`0,"No error"`); the session's two `:SYSTem:ERRor?` queries both returned the queued `-113` entry, so the terminator was not captured | `COMPLETE` |
| `error-queue-overflow.txt` (`-350,"Queue overflow"\n`) | Documented `-350` after 16 queued entries; overflowing the queue was not performed on the instrument | `INCOMPLETE` |
| `command-error.bin` (`command error`, 13 bytes, no terminator) | Literal reply observed repeatedly in this session for undefined headers (`:OPT?`, `:MEASure:RISetime?`, …), but captured only in the measurement table as text | `UNSUPPORTED` |

## Constructed and damaged cases

| Fixture | Construction | Expected status |
|---|---|---|
| `identity-missing-firmware.txt` | Real identity line with the firmware field removed | `INCOMPLETE` |
| `identity-wrong-vendor.txt` | Real identity line with the vendor replaced by `GW INSTEK` | `INVALID` |
| `preamble-truncated.txt` | Real NORM preamble with the trailing `yreference` field removed (9 fields) | `INVALID` |
| `preamble-stale-window.txt` | The measured contradiction: `:WAVeform:STOP` left at a RAW value, then NORM, so the preamble reports 240001 points with the 2 µs screen increment | `INVALID` |
| `preamble-max.txt` | `:WAVeform:MODE MAXimum` was measured to set the mode field to 1 and make `:WAVeform:POINts?` report 240000 for window 1..240000. Only `mode` and `points` come from that observation; the remaining fields repeat the measured RAW window (`xincrement` 1e-09, `yincrement` 0.0209375, `yorigin` -72, `yreference` 121) and are not claimed as a MAX capture | `COMPLETE` |
| `waveform-length-short.bin` | Real NORM block relabelled with 1200 declared bytes but only 1198 bytes supplied | `INCOMPLETE` |
| `waveform-length-extra.bin` | Real NORM block with two extra bytes before the terminator | `INVALID` |
| `waveform-points-mismatch.bin` | Real NORM preamble (1200 points) with a block that carries 1000 points | `INVALID` |
| `block-unknown-trailing.bin` | Four-byte block followed by `ZZ\n` (not the known firmware quirk) | `INVALID` |

## Screenshots

The real `:DISPlay:DATA?` capture is 1 152 068 bytes: `#9` + `001152054` + a
complete 800×480 24-bit BMP + three extra bytes `;0\n` past the declared length
(full capture SHA-256 in `expected-screenshot.json`; see also
`artifacts/rigol-ds1000z/hardware-evidence.md`). A 1.1 MB file is not committed,
so the screenshot cases are built from the real block shape at small size.

| Fixture | Construction | Expected status |
|---|---|---|
| `screenshot-color-head.bin` | The **real** 11-byte block header `#9001152054` followed by the real 54-byte BMP header and the real `;0\n` tail: the declared 1 152 054-byte payload is deliberately not shipped | `INCOMPLETE` (declared length not satisfied) |
| `screenshot-compact.bin` | Same `#9` + nine-digit + BMP + `;0\n` shape, with a fully consistent 4×4 24-bit BMP so the complete path can be tested at 116 bytes | `COMPLETE` with reason `firmware_trailing_bytes_after_block` and limitation `panel_geometry_differs_from_800x480` |
| `screenshot-bad-signature.bin` | `BM` replaced by `XX` inside an otherwise valid block | `INVALID` |
| `screenshot-size-mismatch.bin` | BMP `bfSize` field changed so it no longer equals the declared block length | `INVALID` |

`screenshot-compact.bin` is a constructed fixture, not a scope screenshot: its
geometry is 4×4, so the parser reports `matches_scope_panel: false`. The 3-byte
`;0\n` tail is the real firmware quirk, reproduced byte for byte.

## Notes

- Binary files are raw response bytes; they are not encoded or compressed.
- `assets/expected-*.json` hold the status and key fields asserted by the
  offline tests. They are expectations, not captures.
- No fixture may be quoted as evidence of a measurement on another instrument
  or firmware.
