# Response and Evidence (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 184-188, 193-198, 260-265,
287-292. Hardware evidence: AFG-2225 serial `GEP902745`, firmware `V2.05`,
USB CDC-ACM `2184:001c` at `/dev/ttyACM0`, captured 2026-11-26. Support level:
`hardware-verified` for the captured identity, numeric, and error-queue subset;
`documented` for the ARB command builders and unexercised command families.

## Observed wire format (2026-11-26)

Raw responses are preserved byte for byte in `assets/captures/`; these examples
show the Python byte literal, including quotes and line endings:

```text
*IDN?              -> b"GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n"
SOUR1:APPL?        -> b'"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"\r\n'
SOUR1:AMPLITUDE?   -> b"+3.000E+00\r\n"
SYST:ERR?          -> b"-102\r\nSyntax error."
SYST:ERR?          -> b"\r\nNo error."
SOUR1:AMPL?        -> b""   (no response; following queue read: -113 Undefined header)
```

The error queue has two lines: the first ends with CRLF, the second has no
terminator. The empty queue is a blank code line followed by `No error.`. The
manual prints only the single-line `-138 Suffix not allowed` form, so the parser
accepts both shapes. `SOUR<n>:APPL?` is quoted on the wire even though the
manual's example omits the quotes.

`SYSTem:VERSion?` is multi-line on the verified unit:

```text
 AFG-2225     Version-2.05_0112 \r\n
\r\n FPGA:20130410\r\n
\r\n SN: GEP902745\r\n
\r\n MODE:Plant Pattern\r\n
```

It is preserved as raw text; this Skill does not claim structured
firmware/FPGA fields from it.

## Parser stages

`scripts/afg2225_protocol.py` keeps the authoring stages independently
callable:

1. `read_frame(raw)`: one LF/CR/CRLF/LFCR line; retain content, terminator,
   and reject empty, missing-terminator, oversized, or trailing-byte frames.
2. `read_error_queue_frame(raw)`: accept the manual's single line or the
   observed two-line code/message form, join the two lines for classification,
   and reject a third line. Raw evidence still uses the original bytes.
3. `parse_metadata(frame, response_type=...)`: decode ASCII and classify
   identity, numeric, or error-queue tokens. Automatic mode classifies only
   the documented error-queue sentinels; other error messages become
   `UNSUPPORTED` unless `response_type="error-queue"` is explicit.
4. `extract_payload(metadata)`: expose raw fields (`fields`, `numeric_token`/
   `raw_unit`, or `code`/`message`) without conversion.
5. `normalize(metadata, payload, quantity=..., unit=...)`: resolve units,
   validate identity fields, classify queue records, and build the artifact
   with `status`, `checks`, and `reasons`.
6. `validate(artifact, raw)`: attach the raw-bytes SHA-256/base64 evidence,
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

`*IDN?` -> `GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n`.
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

Captured numeric readbacks include `SOUR1:FREQ?` ->
`+5.0000000000000E-01\r\n` and `SOUR1:AMPLITUDE?` -> `+3.000E+00\r\n` (the
amplitude unit comes from `SOUR1:VOLT:UNIT?`, observed `VPP`). The short query
`SOUR1:AMPL?` is rejected by V2.05; use the long form.

## Error queue parsing

- `0 No error` (manual single line) -> `COMPLETE`.
- Observed empty form `\r\nNo error.` -> `COMPLETE`, message `No error.`.
- `±350 Queue overflow` (with or without a trailing period) -> `INCOMPLETE`.
- Observed `-102\r\nSyntax error.` -> `UNVERIFIED` for the nonzero code.
- Other messages in `auto` mode -> `UNSUPPORTED` (explicit mode required).
- Explicit `error-queue` mode accepts any code/message -> `UNVERIFIED` for
  nonzero codes.
- A third line after the message is `INVALID`.

## Version query

`SYSTem:VERSion?` is preserved as raw text. The manual shows only a placeholder
format (`AFG-2225 VX.XXX_XXXX`), so this Skill does not claim structured
firmware/FPGA fields from it. The verified unit returned
`Version-2.05_0112`, `FPGA:20130410`, `SN: GEP902745`, and
`MODE:Plant Pattern` across several lines.

## Raw evidence

Every result preserves raw bytes as SHA-256 and base64. No silent padding,
truncation, clamping, interpolation, or guessing. Real captures live in
`assets/captures/`; synthetic failure-mode fixtures live separately in
`assets/fixtures/`.

## Provenance fields

- Manual title, revision (82RF-22250M01), pages.
- Parser name/version (`afg2225-protocol` 0.2.0).
- Parser artifacts stamp `support_level: documented`; the capture provenance is
  the manifest, `assets/captures/captures.jsonl`, and this record, not the
  parser default.
- Hardware verification: true for the captured subset, 2026-11-26.
- Verified instrument: AFG-2225, serial `GEP902745`, firmware `V2.05`, USB
  CDC-ACM `2184:001c` at `/dev/ttyACM0`.

## Loopback (2026-11-26)

AFG-2225 CH1 was connected to a GDS-2104A CH1 (1 MOhm, 1x, DC). With
`SOUR1:FUNC SIN`, `SOUR1:FREQ 1000`, `SOUR1:AMPLITUDE 1`, `SOUR1:DCO 0`, and
`OUTP1 ON`, the scope reported:

```text
:MEASure:FREQuency? -> 1.000E+03
:MEASure:PERiod?    -> 1.000E-03
:MEASure:PK2PK?     -> 2.060E+00
:MEASure:RMS?       -> 7.270E-01
```

`SOUR1:AMPLITUDE` is a 50 ohm-reference value, so 1 Vpp becomes about 2 Vpp at
1 MOhm; the measured 2.06 Vpp matches that doubling within the scope's
display resolution. `OUTP1 OFF` returned `0`, both error queues were empty, and
the original `SIN 0.5 Hz / 3 Vpp / 0 V` setup was restored. Full record:
`artifacts/hw-verify/loopback-20261126/loopback-result.json` (git-ignored).
One point at one frequency is not an amplitude-accuracy or flatness check.

## Known limitations

- Hardware verification is limited to the captured read-only,
  single-parameter write/readback subset, and the single loopback point.
- Binary ARB byte order unverified; no `DATA:DAC` upload was sent.
- Modulation, sweep, and burst were not exercised command by command.
- APPLy writes were not sent. `OUTPut ON/OFF` was exercised once in the loopback
  above; other waveforms, levels, and loads remain `documented`.
- Amplitude flatness and accuracy are not verified by the single loopback point.
- USB CDC only; no LAN/GPIB/RS-232.
- No calibration, firmware update, panel save/delete automation.
- Manual example byte-count defect (5 values / 16 bytes vs 10 bytes).
- `115200 8N1` is the helper default; the verified link also answered at 9600.
- No SCPI beeper command exists; the beeper is panel-only.
