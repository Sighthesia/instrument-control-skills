# Response and Evidence (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Command list: TOC pp. 24-34; common commands: TOC pp. 37-40; acquisition and
waveform: TOC pp. 41-45; measurements: TOC pp. 78-107; error messages: TOC
pp. 235-238. Support level: parser code is exercised offline; the shipped
hardware fixtures are `hardware-verified`; every other response shape is
`documented` only. Page numbers are table-of-contents or List of Commands
markers (pp. 24-34); the local converted copy has no body page breaks.

## Parser stages

`scripts/gds2000a_protocol.py` is transport-independent and standard-library
only. The stages are independently callable:

1. `read_frame(raw)` — exactly one LF/CR/CRLF/LFCR-terminated line. Retains
   content, terminator, and trailing CR/LF/space/tab; rejects empty, missing
   terminator, oversized, and extra non-whitespace bytes.
2. `parse_metadata(frame, response_type=...)` — decodes text and classifies
   identity, measurement, or error-queue tokens. Automatic mode recognizes the
   error-queue shape, the identity shape, and a measurement sentinel or NR3
   token; anything else is `UNSUPPORTED`.
3. `extract_payload(metadata)` — exposes raw fields (`vendor`/`model`/`serial`/
   `firmware`, `numeric_token`/`sentinel`/`raw_unit`, or `code`/`message`)
   without conversion.
4. `normalize(metadata, payload, quantity=..., unit=...)` — validates identity
   fields, classifies the measurement or sentinel, resolves the implied unit,
   classifies the queue record, and builds the artifact with `status`,
   `checks`, and `reasons`.
5. `validate(artifact, raw, provenance=...)` — attaches the raw-byte SHA-256/
   base64 evidence, parser version, support level, and the final `integrity`
   block.

Waveform stages:

1. `parse_waveform_header(raw)` — ASCII header fields, `Waveform Data;`
   marker, separator, and IEEE block; or a headerless block.
2. `parse_ieee_block(raw, allow_terminator=...)` — definite-length framing
   with exact declared-length enforcement; `encode_ieee_block(payload)` is the
   inverse used by tests.
3. `parse_waveform(raw, include_samples=False, sample_byte_order="little",
   provenance=...)` — point count, header checks, code-domain statistics, and
   artifact construction.
4. `iter_samples(payload, byte_order="little")` — signed 16-bit unpacking.
5. `waveform_to_csv(raw, path, overwrite=False)` — streams `index,code`
   without materializing all samples.

High-level functions `parse_identity`, `parse_measurement`,
`parse_error_queue`, `drain_error_queue`, `parse_waveform`, and
`waveform_to_csv` compose the stages and return an artifact even on failure; a
caller can also run the stages and inspect the intermediate result.

## CLI

```text
python3 scripts/gds2000a_protocol.py identity assets/fixtures/hardware/identity.txt --provenance hardware-verified
python3 scripts/gds2000a_protocol.py measurement assets/fixtures/hardware/measure-pk2pk.txt --quantity pk2pk --provenance hardware-verified
python3 scripts/gds2000a_protocol.py error-queue assets/fixtures/hardware/error-none.txt --provenance hardware-verified
python3 scripts/gds2000a_protocol.py waveform assets/fixtures/hardware/acquire1-memory.bin --provenance hardware-verified
python3 scripts/gds2000a_protocol.py waveform-header assets/fixtures/hardware/acquire1-memory.bin
python3 scripts/gds2000a_protocol.py waveform assets/fixtures/hardware/acquire1-memory.bin --csv-out wave.csv
```

`--provenance` is one of `documented`, `synthetic`, or `hardware-verified`.
Only `hardware-verified` maps to the `hardware-verified` support level;
`synthetic` and `documented` both map to `documented`.

## Statuses

- `COMPLETE`: framing, required fields, unit/shape checks, and applicable
  structural counts pass for the stated claim.
- `INCOMPLETE`: a required byte, terminator, field, point, or response element
  is missing, or a documented non-value sentinel was returned.
- `INVALID`: framing, numeric, field, or type constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded but calibration, headerless metadata, or
  hardware acceptance is not proven; also used for a reported instrument error
  that is preserved but not interpreted.
- `UNSUPPORTED`: the response shape, transport shape, or feature is not
  implemented.

Never silently pad, truncate, clamp, interpolate, or guess. A retried or failed
read is never merged into a complete record. `COMPLETE` never means the value
is physically correct, calibrated, or from a valid acquisition.

## Identity

`*IDN?` -> `GW,GDS-<model>,<serial>,V<version>` (TOC pp. 37-40).

- Vendor must be `GW`; model must match `GDS-<four digits>A`.
- A three-field reply is padded with an empty firmware field and reported
  `INCOMPLETE`; a four-field reply with an empty or malformed field is
  `INCOMPLETE` or `INVALID`.
- Serial must match `P?[0-9A-Za-z]+`; firmware must match
  `V<digits>.<alphanumeric>`.
- The profile reports `channels: 4` when the last digit before the trailing
  `A` is `4`, otherwise `2`. That inference is labelled
  `channel_count_source` and is not a hardware query.
- Identity does not prove installed options, interface, or calibration.

## Scalar measurement

- Individual responses are `<NR3>` or a source-off sentinel. The manual prints
  `Chan Off`; V1.18 returned `Ch Off`. Both are `INCOMPLETE` with
  `value: null`; neither is zero.
- `9.9E+37` (and the equivalent `9.9E37`) is an observed no-result sentinel
  when a slotted measurement is disabled; it is `INCOMPLETE`. The manual does
  not document it.
- NaN/Inf, unit suffixes, or other text are `INVALID`. The parser accepts only
  a finite NR3 token with no suffix.
- The implied unit follows the quantity:
  - time: `s`; frequency: `Hz`; duty/overshoot/preshoot: `%`; phase: `deg`;
  - voltage/current quantities: `V or A` (`source-dependent`);
  - area: `V·s or A·s` (`source-dependent`);
  - counts: `None` (`unitless`).
- A caller-supplied unit from the allowed set (`V`, `A`, `%`, `Hz`, `s`,
  `deg`, `V·s`, `A·s`) replaces the implied unit and is marked
  `caller-supplied`; count quantities reject a unit. The parser does not prove
  that the supplied unit is dimensionally correct for the quantity.
- A finite value does not prove probe, coupling, gating, trigger, or
  calibration validity.

`parse_measurement` requires `quantity=`; an unsupported quantity is
`INVALID`. `:MEASure:SOURce1`/`SOURce2` select the source; individual
`:MEASure:*?` commands take no channel parameter.

## Error queue

- `+0, "No error."` -> `COMPLETE`.
- `±350, "Queue overflow"` -> `INCOMPLETE`.
- Any other code/message -> `UNVERIFIED`, with code and message preserved.
- Both straight and typographic quotes are accepted as delimiters; an
  unterminated quote is `INVALID`. Message text is never edited.
- `drain_error_queue` returns `COMPLETE` only when a `+0` record appears; a
  bounded drain without `+0` is `INCOMPLETE` (`no_no_error_record_observed`).

Reading the queue removes the record. A drained queue is not proof that the
preceding command was semantically correct.

## Waveform

`:ACQuire<n>:MEMory?` after `:STOP` returns an ASCII header, the literal
`Waveform Data;`, and an IEEE 488.2 definite-length block. The shipped capture
is 5,000 points / 10,000 payload bytes + one LF.

- Header fields include `Format`, `Memory Length`, `Trigger Address`,
  `Trigger Level`, `Source`, `Vertical Units`, `Probe Type`, `Probe`,
  `Vertical Scale`, `Vertical Position`, `Horizontal Units`,
  `Horizontal Scale`, `Horizontal Position`, `Horizontal Mode`,
  `Sampling Period`, `Firmware`, and `Time` (TOC pp. 41-43).
- The parser requires `Memory Length` for a header-present response and checks
  it against the block; a mismatch is `INVALID`.
- A missing `Vertical Scale` changes the status to `UNVERIFIED`
  (`vertical_scale_missing`).
- A missing `Sampling Period` is recorded as `sampling_period_missing` but does
  not by itself change the structural status. A `COMPLETE` waveform with that
  reason has a valid block but no verified time axis; do not read it as a
  complete acquisition claim.
- A headerless block (`:HEADer OFF`) is `UNVERIFIED`
  (`headerless_block_has_no_scale_or_units`); the point count is known, scale
  and units are not.
- A truncated block is `INCOMPLETE`; an odd payload is `INVALID`; extra
  non-terminator bytes are `INVALID`; an indefinite `#0` block and a declared
  size beyond the parser limits are `UNSUPPORTED`.
- Header fields may be separated by `;` or `,`. Duplicate field names,
  missing commas, non-ASCII header bytes, and unexpected bytes between the
  marker and `#` are `INVALID`.
- The payload is signed 16-bit. **Byte order is not stated by the manual.**
  Little-endian is labelled `observed`, inferred from the GDS-2104A capture;
  do not present it as documented.

## Calibration caveat

The GDS-2000A programming manual documents **no code-to-volts formula**. The
parser therefore emits:

```text
calibration.status = UNVERIFIED
analysis_allowed   = code-domain-only
```

It does not multiply by a vertical scale, add a position offset, or apply a
probe ratio. The header's `Vertical Scale` and `Sampling Period` are preserved
as metadata, not used to invent volts or seconds per sample. For calibrated
work, use the instrument's own measurements or an independently established
transfer function; this Skill cannot provide one.

## Raw evidence and provenance

Line-response artifacts preserve `integrity.raw_sha256`,
`integrity.raw_bytes`, and `integrity.raw_response_base64`. Waveform artifacts
preserve top-level `raw_sha256`, `raw_bytes`, `payload_sha256`, and an
`integrity` block; the raw binary is saved by the caller, not embedded as
base64 for large waveforms. Every artifact records:

- parser name/version (`gds2000a-protocol/0.1.0`);
- input provenance and support level;
- status, checks, and reasons;
- calibration status and `analysis_allowed` for waveforms.

## Fixtures

`assets/fixtures/hardware/` contains real GDS-2104A responses and raw blocks.
`assets/fixtures/synthetic/` contains constructed rejection cases only. The
hashes and source of every fixture are recorded in
`assets/fixtures/README.md`; `assets/expected-*.json` are parser outputs, not
captures. A synthetic fixture is never evidence that the instrument behaves
that way.

## Manual defects and local-copy limits

Record these instead of copying them into sendable commands:

1. **Query `?` omitted in the list.** Most rows print a set form even when the
   body documents a query. Send the query form.
2. **Instance suffix omitted.** The list prints `:ACQuire:MEMory?`,
   `:ACQuire:STATe?`, `:MEASure:SOURce`, and `:MEASUrement:MEAS:*` without the
   channel/slot number; hardware required `:ACQuire1:`, `:MEASure:SOURce1`,
   and `:MEASUrement:MEAS1:`.
3. **Go_NoGo section missing from the local list.** The body has Go_NoGo and
   Template commands on TOC pp. 226-231, but the local list jumps from Function
   Generator (p. 225) to Data Logging (p. 232). Those forms are in Appendix A
   and are not counted in the 339-row denominator.
4. **Body-only `:DISPlay:OUTPut?`.** Documented at TOC p. 74 but absent from
   the list. It returns a 16-bit RGB run-length image, not a file.
5. **Body-only `:LISTer:DATA?`.** Documented in the Bus Decode section (TOC
   p. 167) but absent from the list.
6. **Function Generator suffix.** The list prints `:FUNCtion:MODe`; body
   examples use `:FUNCtion1:`. On V1.18 the bare form returned `-131`, the
   suffixed form `-240` because DS2-FGN is absent.
7. **Trigger-state spelling.** The manual returns `*ARMED`, `*AUTO`, `*READY`,
   `*SAVE`, `*TRIGGER`; V1.18 returned `ARMED`, `AUTO`, `SAVE`, `READY`
   without the leading `*`.
8. **Measurement sentinel.** The manual documents `Chan Off`; V1.18 returned
   `Ch Off`. `:MEASUrement:MEAS1:VALue?` with state `0` returned `9.9E+37`, a
   no-result token the manual does not document. Both are `INCOMPLETE`.
9. **Waveform header separators.** The `:ACQuire1:MEMory?` example uses `;`;
   the `:ACQuire1:LMEMory?` example uses `,`. The parser accepts either; the
   captured memory header used `;`.
10. **Referenced-only logic-clock edge.**
    `:TRIGger:LOGic:INPut:CLOCK:EDGe` and
    `:SEARCH:TRIGger:LOGic:INPut:CLOCK:EDGe` are named as related commands but
    have no syntax heading or list row; Appendix B marks them `UNVERIFIED`.
11. **Double LF.** `:TRIGger:FREQuency?` returned `2.000E+00` followed by two
    LFs. The parser keeps the second LF as framing evidence; it is not a second
    response.
12. **`:TIMebase:EXPand?` contradiction.** The manual says it is available for
    firmware V1.18 or above and requires the Horizontal Expansion app; the
    V1.18 unit returned `-221 Settings conflict`. The command remains
    documented, not verified on this unit.

## Known limitations

- Hardware evidence covers one GDS-2104A, firmware V1.18, USB CDC-ACM, on
  2026-11-26. Do not extend it.
- Waveform voltage conversion is unavailable; every waveform is code-domain.
- The image RLE decoder is not implemented.
- CH2-CH4, optional features, and non-USB transports are unverified.
- The parser accepts only the response shapes it implements; a firmware-
  specific variant is `UNSUPPORTED` or `INVALID`, never guessed.
