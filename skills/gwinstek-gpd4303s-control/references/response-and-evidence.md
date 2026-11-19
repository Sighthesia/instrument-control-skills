# Response and Evidence (GPD-4303S)

Source: *GPD-X303S Series User Manual*, GW Instek part no. `82PD-433S0MC1`,
PDF pp. 46-52 (syntax, error messages, command details), pp. 55-56 (accuracy and
resolution). Response formats are not documented in the manual; the shapes below
come from real captures on GPD-4303S serial `EP924162`, firmware `V2.08`,
`/dev/ttyUSB0` at 9600 8N1 on 2026-11-19.

## Parser stages

`scripts/gpd4303s_protocol.py` keeps the authoring stages independently callable:

1. `read_frame(raw)` — exactly one terminated line; returns content, terminator
   and trailing bytes; rejects empty (`INCOMPLETE`), unterminated (`INCOMPLETE`),
   oversized (`UNSUPPORTED`) and trailing-byte (`INVALID`) frames.
2. `read_multiline_frame(raw)` — the same checks for a CR/LF-separated multi-line
   body (`HELP?`), preserving every line and the raw bytes.
3. `parse_metadata(frame, response_type=...)` — ASCII decode and token
   classification (`identity`, `numeric`, `status`, `error-message`).
4. `extract_payload(metadata)` — raw fields only (`fields`, `numeric_token` /
   `raw_unit`, `raw_text`, `message`), no conversion.
5. `normalize(...)` — identity checks, unit resolution, status bit decoding; it
   builds `status`, `checks` and `reasons` but does not attach provenance.
6. `validate(artifact, raw)` — moves the checks into the final `integrity` block
   and adds raw SHA-256, raw base64, and the parser version.

`parse_identity`, `parse_reading`, `parse_status`, `parse_error_message`,
`parse_command_list` and `parse_response` compose them; `parse_response` picks
the stage from the query that produced the bytes, so a caller cannot accidentally
parse a `STATUS?` answer as a voltage.

## Statuses

- `COMPLETE`: framing, required fields and unit/identity agreement hold for the
  stated claim.
- `INCOMPLETE`: a terminator, field, or unit is missing, so the value cannot be
  attributed (for example a unitless `24.000`).
- `INVALID`: framing, numeric, unit, or identity constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded but completeness or semantics cannot be proven
  (`STATUS?` character order, sequential V/I reads).
- `UNSUPPORTED`: the response shape or message is not implemented.

Individual checks use `pass`, `fail`, and `not_checked`. Never silently pad,
truncate, clamp, interpolate, or guess.

## Identity

`*IDN?` -> `GW INSTEK,GPD-4303S,SN:EP924162,V2.08`.

- Four comma-separated fields, in the order vendor, model, serial, firmware.
- Vendor must be `GW INSTEK` and model `GPD-4303S` (case-insensitive) — anything
  else is `INVALID`, because a differently identified instrument invalidates the
  whole session.
- A three-field reply is `INCOMPLETE` (firmware missing); an empty serial or a
  serial without the `SN:` prefix is `INCOMPLETE`/`INVALID`.
- Firmware must look like `V<major>.<minor>`.

## Numeric values (VSET / ISET / VOUT / IOUT)

Observed wire format: `[-]?<digits>.<3 digits>` immediately followed by one unit
letter, no space:

```text
VSET1? -> 24.000V    ISET1? -> 1.000A
VOUT1? -> 23.994V    IOUT1? -> 0.002A      (output energised)
VOUT1? -> 0.000V     IOUT1? -> 0.000A      (output off)
```

Rules:

- The unit letter is **required**. The device always sends it; a unitless token
  is `INCOMPLETE` (`response_unit_missing`), never guessed from the command.
- The unit must match the quantity: `V` for voltage, `A` for current. A
  conflicting unit is `INVALID`. No scaling suffixes (`mV`, `mA`) are accepted,
  because none were ever observed; inventing a scale factor would be a guess.
- `resolution_digits` records how many decimals arrived (3 in every capture,
  matching the 1 mV / 1 mA meter resolution of manual p. 55).
- The numeric text is preserved as `raw_token`; the parsed value is a float.
- Read-back is **not** calibrated: ±(0.03 % of reading + 10 mV) for voltage and
  ±(0.3 % of reading + 10 mA) for current (manual p. 56). `0.000V` is a meter
  reading near zero, not proof of dead terminals.
- `VOUT` and `IOUT` are separate queries, so a V/I pair is sequential, not
  simultaneous. The session snapshot therefore reports `UNVERIFIED` for the pair
  even when every individual reading is `COMPLETE`.

## `STATUS?` bit order

The manual (p. 50) defines the bit meanings but never says whether the leftmost
character is bit 0 or bit 7. Three real captures exist:

| Capture | Wire text | State at capture time |
|---|---|---|
| 1 | `00111010` | output off, beep on |
| 2 | `11110110` | output **on** (`OUT1` probe; CH1 at 23.994 V) |
| 3 | `00110010` | output off, beep off |

Reading the leftmost character as bit 0 (`lsb-first`, the default):

- baud field (bits 6, 7) is `10` in all three captures -> 9600 bps, which matches
  the only rate the instrument actually answered at (115200 received nothing).
- output bit (bit 5) is off / on / off, exactly following the observed `OUT1` and
  `OUT0` sequence.
- beep bit (bit 4) changes between captures, following the `BEEP0`/`BEEP1` probes.

Reading the leftmost character as bit 7 (`msb-first`) gives baud codes
`00`/`11`/`00` -> 115200/undefined/115200, which contradicts the live 9600 link,
and an output bit that does not follow the observed sequence.

The default is therefore `lsb-first` **as an inference, not a documented fact**:
`parse_status` returns `integrity.status = UNVERIFIED`, the check
`status_bit_order` is `not_checked`, and every result carries both
`decoded` (the selected order) and `decoded_alternate_order`. Use
`--bit-order msb-first` to see the other reading.

Unresolved: under `lsb-first` the tracking field reads `11` (series) in all three
captures. The panel's `SER/INDEP` key would confirm it, but `TRACK<NR1>` is a
write command and was not sent, so this Skill does not claim to know the unit's
tracking mode — it reports the bits.

## Error messages

The device replies with the message text itself, terminated by CR LF. Matching is
case-insensitive and ignores a trailing period, because the verified unit sends
`Invalid Character.` where manual p. 46 prints `Invalid character`; the artifact
records `written_as_documented: false` in that case. Text that is not one of the
six documented messages is `UNSUPPORTED` rather than being pattern-matched into a
diagnosis.

## `HELP?` command list

934 bytes, 18 lines separated by CR, final line terminated by CR LF. Each
non-indented line starts with a mnemonic; `extract_advertised_commands` returns
the 17 mnemonics, which is a direct check of which commands this firmware
advertises. `HELP?` itself is absent, as manual p. 52 says. The channel hint line
(`x:1=CH1,2=CH2 (4303:3=CH3,4=CH4)`) is indented and is deliberately skipped.

## Fixture provenance

`assets/fixtures/captures/` holds the byte-level evidence, plus
`captures.jsonl` with command, request bytes, response bytes, SHA-256 and
timestamp. Six of the seven entries were written directly by
`gpd4303s_session.py --capture-dir`; the `HELP?` entry carries
`capture_method: console-transcript` because it was reconstructed after the
instrument disconnected (see its row below). The descriptive copies are
byte-identical to those capture files (a unit test asserts it).

Only CH1 and CH2 have preserved raw response bytes. The CH3/CH4 responses appear
in the session transcript but were never written to `captures/`, so those
channel-scoped claims are `documented`, not `hardware-verified`.

| Fixture | Response | How it was obtained | Level |
|---|---|---|---|
| `idn.txt`, `status-output-off.txt`, `vout1-off.txt`, `iout1-off.txt`, `vout2-off.txt`, `iout2-off.txt` | `…V2.08`, `00110010`, `0.000V`, `0.000A` | Written by `--capture-dir` on 2026-11-19, GPD-4303S V2.08 at 9600 8N1 | `hardware-verified` |
| `vset1.txt`, `vset2.txt` | `24.000V`, `24.000V` | **Real read-only `VSET1?`/`VSET2?` responses** from the same 2026-11-19 session on the same unit (V2.08, 9600 8N1), recorded verbatim in the session transcript. Not manual text, not synthetic. | `hardware-verified` (CH1/CH2) |
| `iset1.txt`, `iset2.txt` | `1.000A`, `1.000A` | **Real read-only `ISET1?`/`ISET2?` responses**, same session and unit, transcribed from the transcript | `hardware-verified` (CH1/CH2) |
| `vset3.txt`, `vset4.txt` | `3.300V`, `2.500V` | **Real read-only `VSET3?`/`VSET4?` responses**, same session and unit, transcribed from the transcript — but no raw response bytes were preserved, so the claim is not `hardware-verified`. Channel numbering comes from manual pp. 48-49 and the `HELP?` hint `x:1=CH1,2=CH2 (4303:3=CH3,4=CH4)`. | `documented` (CH3/CH4) |
| `iset3.txt`, `iset4.txt` | `3.000A`, `1.000A` | **Real read-only `ISET3?`/`ISET4?` responses**, same session and unit, transcript only, no preserved raw bytes | `documented` (CH3/CH4) |
| `vout3-off.txt`, `vout4-off.txt`, `iout3-off.txt`, `iout4-off.txt` | `0.000V`, `0.000V`, `0.000A`, `0.000A` | **Real read-only `VOUT3?`/`VOUT4?`/`IOUT3?`/`IOUT4?` responses**, same session and unit, transcript only, no preserved raw bytes | `documented` (CH3/CH4) |
| `vout1-on.txt`, `vout2-on.txt`, `iout1-on.txt` | `23.994V`, `23.987V`, `0.002A` | Real `VOUT1?`/`VOUT2?`/`IOUT1?` responses from the **earlier probe session** recorded in `artifacts/manuals/ground-truth.md`; not re-captured, because re-energising the output is out of scope | `hardware-verified` |
| `status-output-on.txt`, `status-output-off-beep-on.txt` | `11110110`, `00111010` | Same earlier probe session (`ground-truth.md`) | `hardware-verified` |
| `help-list.txt` | 18-line command list | Real `HELP?` response returned 2026-11-19 (934 bytes at capture time); reconstructed from the recorded console transcript after the instrument disconnected, and the reconstructed length equals the reported 934 bytes. Preserved as `assets/fixtures/captures/help-transcribed.raw` (SHA-256 `cc99fc5c…`) and indexed in `captures.jsonl` with `capture_method: console-transcript`. Not written by `--capture-dir`, not manual text, not synthetic. | `hardware-verified` (transcript-reconstructed raw) |
| `invalid-character.txt` | `Invalid Character.` | Real reply to an unknown command, recorded in `ground-truth.md` | `hardware-verified` |
| `vout1-lowercase-probe.txt` | `0.000V` | Real reply to `vout1?`, proving the "not case-sensitive" rule of manual p. 46 | `hardware-verified` |
| `synthetic/*.txt` | wrong model, missing firmware, unitless value, wrong unit, short/non-binary status, undocumented error text, missing terminator, extra line | **Synthetic negatives** built to exercise failure paths; no instrument produced them | synthetic |

Every capture in this Skill is a single, non-repeatable observation: the
instrument was disconnected from the host after the session and was not
re-measured. Do not extend any of it to another unit, firmware, or interface, and
do not upgrade a write command to `hardware-verified` on the strength of a
read-only capture.

## Provenance fields in artifacts

- `raw_sha256` and `raw_response_base64` on every result; raw bytes are preserved
  before decoding.
- `parser`: `gpd4303s-protocol/0.1.0` (or `gpd4303s-session/0.1.0` for session
  snapshots).
- `evidence.command`, `evidence.command_evidence` (per-command level) and
  `evidence.pdf_page` on dispatched responses.
- `bit_order` and `decoded_alternate_order` on `STATUS?` results.
- Capture index (`captures.jsonl`): run id, timestamp, port, baud, command,
  request bytes, response bytes, SHA-256, raw file name.

## Known limitations

- `STATUS?` character order is undocumented; the decode is an inference.
- No write command was exercised, so no side effect of `OUT`, `VSET`, `ISET`,
  `TRACK`, `SAV`, `RCL`, `BAUD`, `LOCAL`, or `REMOTE` is verified.
- Only `Invalid Character.` was seen on the wire; the other five error messages
  are untested, and the manual's letter mapping did not match this firmware for
  unknown commands.
- Read-back is uncalibrated and the V/I pair is not simultaneous.
- The 15-character limit's treatment of the terminator is not documented.
