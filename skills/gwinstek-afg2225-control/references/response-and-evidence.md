# Response and Evidence (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 184-188, 193-198, 260-265,
287-292. Support level: `documented`.

## Parser stages

`scripts/afg2225_protocol.py` keeps the authoring stages independently
callable:

1. `read_frame(raw)`: one LF/CR/CRLF/LFCR line; retain content, terminator,
   and reject empty, missing-terminator, oversized, or trailing-byte frames.
2. `parse_metadata(frame, response_type=...)`: decode ASCII and classify
   identity, numeric, or error-queue tokens. Automatic mode classifies only
   the documented error-queue sentinels; other error messages become
   `UNSUPPORTED` unless `response_type="error-queue"` is explicit.
3. `extract_payload(metadata)`: expose raw fields (`fields`, `numeric_token`/
   `raw_unit`, or `code`/`message`) without conversion.
4. `normalize(metadata, payload, quantity=..., unit=...)`: resolve units,
   validate identity fields, classify queue records, and build the artifact
   with `status`, `checks`, and `reasons`.
5. `validate(artifact, raw)`: attach the raw-bytes SHA-256/base64 evidence,
   parser version, support level, and final `integrity` block.

The convenience functions `parse_identity`, `parse_numeric`, and
`parse_error_queue` compose these stages; a caller can inspect any intermediate
result when a later stage fails. `load_arb_csv` -> `validate_arb_samples` ->
`encode_ieee_block`/`build_data_dac_*` -> `build_arb_artifact` is the ARB
equivalent.

## Statuses

- `COMPLETE`: all applicable structural checks pass.
- `INCOMPLETE`: required bytes/samples/fields/terminator/sequence missing.
- `INVALID`: framing/numeric/ordering/type constraints contradict raw bytes.
- `UNVERIFIED`: parsing succeeded but completeness/calibration/freshness not
  proven.
- `UNSUPPORTED`: format or feature not implemented.

## Identity parsing

`*IDN?` -> `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm`.
- Different model -> `INVALID`.
- Missing serial/firmware -> `INCOMPLETE`.
- Malformed fields -> `INVALID`.

## Numeric parsing

- Accept signed NR3/NRf with an optional documented suffix.
- `quantity` declares the implied unit when the response is unitless.
- Normalize suffixed values to a canonical base unit (`kHz` -> `Hz`,
  `ms` -> `s`) and retain `raw_value`/`raw_unit`; never treat `1 kHz` as
  `1 Hz`.
- Reject NaN/Inf/non-numeric tokens, unknown suffixes, and suffixes that
  conflict with the declared quantity.
- Missing unit resolution for a quantity that requires one -> `INCOMPLETE`.
- A unitless count may legitimately have `unit: null`.

## Error queue parsing

- `0 No error` -> `COMPLETE`.
- `±350 Queue overflow` -> `INCOMPLETE`.
- Other messages in `auto` mode -> `UNSUPPORTED` (explicit mode required).
- Explicit `error-queue` mode accepts any code/message -> `UNVERIFIED` for
  nonzero codes.

## Version query

`SYSTem:VERSion?` is preserved as raw text. The manual shows only a placeholder
format (`AFG-2225 VX.XXX_XXXX`), so this Skill does not claim structured
firmware/FPGA fields from it.

## Raw evidence

Every result preserves raw bytes as SHA-256 and base64. No silent padding,
truncation, clamping, interpolation, or guessing.

## Provenance fields

- Manual title, revision (82RF-22250M01), pages.
- Parser name/version (`afg2225-protocol` 0.1.0).
- Support level `documented`.
- Hardware verification: false.
- All fixtures are synthetic; see `assets/fixtures/README.md` for the
  documented basis of each one.

## Known limitations

- No hardware verification.
- Binary ARB byte order unverified.
- USB CDC only; no LAN/GPIB/RS-232.
- No calibration, firmware update, panel save/delete automation.
- Manual example byte-count defect (5 values / 16 bytes vs 10 bytes).
- `115200 8N1` is an assumption, not a manual default.