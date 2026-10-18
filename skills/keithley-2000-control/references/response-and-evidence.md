# Response parsing and evidence

## Supported data shape

The bundled offline parser supports one line-framed ASCII reading from the
Model 2000. The manual's ASCII `:FORMat` example shows a reading with unit, and
optionally channel number and channel type. `:SENSe:DATA?` instead returns an
exponent-form numeric reading without a function identifier (PDF 159-162,
168-169). Preserve the exact transport bytes, including terminators.

Examples documented by the manual:

```text
+1.23456789E+00VDC, 0INTCHAN
+1.000000E+01
+9.9E37
```

The overflow token is documented without a unit. These examples are not complete
acquisition records. `function`, query command, unit, range, NPLC, filter,
trigger context, identity, and acquisition freshness must be associated from a
separate command/configuration record.

## Parser stages

`scripts/keithley2000_scalar.py` keeps these stages independently callable:

1. `read_frame(raw)`: locate one CR, LF, CRLF, or LFCR line terminator; retain
   line content, terminator, and trailing bytes. Reject missing terminator and
   unsupported-size/binary frames.
2. `parse_metadata(frame)`: distinguish a measurement line from an error-queue
   line; parse value, unit, optional channel, and channel type without discarding
   original tokens.
3. `extract_payload(metadata)`: expose one scalar value/status; do not infer
   multiple samples from commas or silently split a buffer response.
4. `normalize(metadata, payload)`: produce a `scalar-measurement` with the raw
   token, numeric value where applicable, unit, optional channel, and caller-
   supplied context.
5. `validate(artifact, raw, frame)`: report framing, numeric, unit,
   function/context, error status, and raw SHA-256 checks; reject trailing bytes.
   No stage changes source bytes.

## Status semantics

| Status | Use |
|---|---|
| `COMPLETE` | One supported scalar line is framed, numeric, has an interpretable unit and supplied function context, and the caller supplied an explicit complete-acquisition assertion. This is a structural claim only. |
| `INCOMPLETE` | Empty/truncated or unterminated line, or a required unit/context field is missing. |
| `INVALID` | Contradictory framing, malformed numeric token, non-finite number, or unexpected trailing/extra line. |
| `UNVERIFIED` | Overflow sentinel, error response, or valid scalar without enough function/acquisition evidence. Calibration remains independently `UNVERIFIED`. |
| `UNSUPPORTED` | Binary `#0`, multi-reading/buffer response, ambiguous data-element layout, or any unimplemented response shape. |

Do not upgrade a structural parse to calibrated/fresh merely because a value
parsed. The fixture support level is `documented`; fixtures are synthetic and
not real instrument captures.

## Error queue response

The `:SYSTem:ERRor?` response is a separate artifact, not a reading. The manual
documents a FIFO of up to 10 entries, negative SCPI error codes, positive
Keithley message codes, and `0,No error` as the empty queue indication (PDF 190,
194). Preserve message quoting/spacing and line terminator; do not discard
positive messages. `350, Queue Overflow` or `-350, Queue Overflow` signals
potentially lost earlier errors. Automatic classification recognizes only these
sentinels; use explicit error-queue mode for other codes.

## Provenance and hardware verification

For any real capture, retain at least:

- unmodified raw command and response bytes, plus SHA-256;
- instrument `*IDN?` bytes and parsed vendor/model/serial/firmware;
- transport/interface and host termination policy;
- command sequence and acquisition timestamp;
- queried configuration, error queue before/after, expected and observed count;
- parser name/version, this manual revision and PDF physical page references;
- separate structural, acquisition, calibration, and support statuses.

Label implementation `documented` until a real response is tested. To use
`hardware-verified`, preserve the exact response, Model 2000 identity, firmware,
interface, and test date. Scope a result to that firmware/interface; do not
generalize to every Model 2000 from one test.

## Manual source and known limits

- Official PDF: <https://download.tek.com/manual/2000-900_J-Aug2010_User.pdf>
- Title: *Model 2000 Multimeter User's Manual*.
- Revision: `2000-900-01 Rev. J / August 2010`.
- PDF physical pages are used for citations. PDF metadata records a 2011-10-12
  build timestamp; it is not evidence about hardware or firmware.
- The manual's cited Appendix A speed/accuracy note is not present as a retrievable
  appendix in the supplied PDF. Do not invent or reproduce its contents.
- This Skill intentionally does not parse binary buffers, multi-reading buffer
  exports, or scanner records. It does not perform calibration, control hardware,
  or verify input-fuse condition.
