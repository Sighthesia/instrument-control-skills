# Response and Evidence (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 33-46 (identity, acquisition), pp. 81-113 (measurements), pp. 250-253
(error queue). Support level: `documented`. No hardware response is bundled.

## Parser stages

`scripts/gds1000b_protocol.py` is transport-independent and standard-library
only. The stages are independently callable:

1. `read_frame(raw)` — exactly one LF/CR/CRLF/LFCR-terminated line. Retains
   content and terminator; rejects empty, missing-terminator, oversized, and
   trailing-byte frames.
2. `parse_metadata(frame, response_type=...)` — decodes text and classifies
   identity, measurement, or error-queue tokens. Automatic mode recognizes the
   documented identity/measurement shapes; for the error queue it recognizes
   only the two documented sentinels, and other error messages require explicit
   error-queue mode.
3. `extract_payload(metadata)` — exposes raw fields (`vendor`/`model`/`serial`/
   `firmware`, `numeric_token`/`chan_off`, or `code`/`message`) without
   conversion.
4. `normalize(metadata, payload, quantity=..., unit=...)` — validates identity
   fields, resolves the implied unit, classifies the queue record, and builds
   the artifact with `status`, `checks`, and `reasons`.
5. `validate(artifact, raw)` — attaches the raw-byte SHA-256/base64 evidence,
   parser version, support level, and the final `integrity` block.

Waveform stages:

1. `parse_waveform_header(raw)` — ASCII header fields, `Waveform Data;`
   marker, and IEEE block; or a headerless block.
2. `parse_ieee_block(raw)` / `encode_ieee_block(payload)` — definite-length
   framing, with exact declared-length enforcement.
3. `normalize_waveform(raw, include_samples=False)` — point count, length
   checks, calibration status, and artifact construction.
4. `iter_samples(payload)` — `struct.iter_unpack(">h", payload)`.
5. `sample_value(code, vertical_scale, ad_factor=25)` — documented conversion
   only.

High-level functions `parse_identity`, `parse_measurement`,
`parse_error_queue`, and `parse_waveform` compose the stages and return an
artifact even on failure. A caller can also run the stages and inspect the
intermediate result.

## Statuses

- `COMPLETE`: framing, required fields, units, and applicable structural
  checks pass for the stated claim.
- `INCOMPLETE`: a required byte, terminator, field, point, or response element
  is missing.
- `INVALID`: framing, numeric, field, or type constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded but calibration, freshness, headerless
  metadata, or hardware acceptance is not proven.
- `UNSUPPORTED`: the response shape or feature is not implemented.

Never silently pad, truncate, clamp, interpolate, or guess. A retried or failed
read is never merged into a complete record.

## Identity

`*IDN?` -> `GW,GDS-<model>,P<serial>,V<version>` (pp. 33-34).

- Vendor must be `GW`; model must be in the six-model GDS-1000B set.
- Serial must start with `P`; firmware must start with `V`.
- Missing serial or firmware -> `INCOMPLETE`.
- Unknown model, wrong vendor, bad prefix, or extra fields -> `INVALID`.
- The profile table (`channels`, `bandwidth_mhz`, `ethernet`) is
  documented-only and is not a substitute for reading the front panel.

## Scalar measurement

- Response is `<NR3>` or `Chan Off` (pp. 81-105).
- `Chan Off` -> `INCOMPLETE` with `value: null`; never zero.
- NaN/Inf, unit suffixes, or other text -> `INVALID`.
- The implied unit follows the quantity; voltage/current and area are
  source-dependent (`V or A`, `V·s or A·s`) because
  `:CHANnel<X>:PROBe:TYPe` decides.
- A finite value does not prove probe, coupling, gating, or trigger validity.

## Error queue

- `+0, "No error."` -> `COMPLETE`.
- `±350, "Queue overflow"` -> `INCOMPLETE`.
- Other codes in explicit error-queue mode -> `UNVERIFIED`, with code and
  message preserved.
- Other codes in automatic mode -> `UNSUPPORTED`; the caller must opt in to
  explicit error-queue parsing.
- Both straight and typographic quotes are accepted as delimiters; an
  unterminated quote is `INVALID`. Message text is never edited.

## Waveform

- A header-present response with a valid marker, `Memory Length`, matching
  block length, and `Vertical Scale` is `COMPLETE` structurally.
- A missing `Vertical Scale` makes the waveform `UNVERIFIED`; a missing
  `Vertical Units` is reported as absent metadata but does not by itself
  invalidate the block.
- A headerless block (`:HEADer OFF`) is `UNVERIFIED`: point count is known,
  scale and units are not.
- A missing marker, mismatched `Memory Length`, odd payload length, or extra
  bytes -> `INVALID`.
- A truncated block or missing `Memory Length` -> `INCOMPLETE`.
- Declared size beyond the parser limits -> `UNSUPPORTED`.
- `calibration.status` is always `UNVERIFIED`; `analysis_allowed` is
  `code-domain-only`.
- `payload_sha256` identifies the exact sample bytes; the artifact carries the
  raw and payload hashes, while the raw binary is saved by the caller (not
  embedded as base64 for large waveforms).

## Calibration caveat

The documented formula is `(code / 25) * Vertical Scale` (pp. 42-43). The
manual's own example prints `Vertical Scale,5.000E+00` but calculates with
`0.5`, so the formula is not independently validated. The parser:

- applies the scale that was actually received;
- does not apply `Vertical Position`, probe ratio, or an invented offset;
- labels every voltage result documented-only;
- never upgrades calibration to `COMPLETE` from a fixture.

## Raw evidence and provenance

Line-response artifacts preserve `integrity.raw_sha256` and
`integrity.raw_response_base64`; waveform artifacts preserve raw and payload
SHA-256 and leave the raw binary file to the caller. Every artifact also records:

- parser name/version (`gds1000b-protocol/0.1.0`);
- support level `documented`;
- calibration status and manual page references.

Fixtures are synthetic and described in `assets/fixtures/README.md`. They are
not hardware evidence.

## Known limitations

- No hardware verification; every capability is `documented`.
- USB CDC serial defaults are unstated; `115200 8N1` is an assumption.
- Ethernet is 4-channel only and off by default.
- Waveform voltage conversion is uncalibrated.
- No SCPI image/file readback.
- Headerless responses lose scale and units.
- Optional/licensed features are not implemented in the scripts.
- The parser accepts only the documented response shapes; a firmware-specific
  variant is `UNSUPPORTED`, not guessed.
