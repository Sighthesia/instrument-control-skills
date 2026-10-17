# Integrity and Provenance

## Status vocabulary

Use one primary status:

- `COMPLETE`: all applicable integrity checks pass.
- `INCOMPLETE`: required bytes, samples, segments, or records are missing.
- `INVALID`: the response contradicts its framing or metadata, or contains an
  unrecoverable structural error.
- `UNVERIFIED`: parsing succeeded but the available evidence cannot prove an
  important property such as completeness, units, calibration, or sequence.
- `UNSUPPORTED`: the parser deliberately does not implement this format or feature.

Do not collapse these into a boolean `valid` field. A useful report includes each
check, its status, its evidence, and its reason.

## Minimum provenance

Record, when available:

- vendor, model, serial, and firmware
- transport kind and non-secret endpoint identifier
- request or operation name
- capture timestamp
- raw response path and SHA-256
- parser name and version
- manual title, revision, URL, and page/section
- support level and known limitations

Do not store credentials or secrets in fixtures. Redact endpoint details that are
not needed to reproduce parsing.

## Evidence levels

`documented` means the implementation follows a cited manual. `replay-tested`
means preserved responses and negative cases pass offline. `hardware-verified`
requires a real response. `firmware-scoped` additionally records exact model,
firmware, interface, and test date. Do not upgrade a label because a parser is
syntactically plausible.
