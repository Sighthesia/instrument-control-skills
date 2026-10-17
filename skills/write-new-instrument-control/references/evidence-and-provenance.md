# Evidence and Provenance

## Preserve the chain

Record enough information to connect an analysis result back to the instrument
response:

- vendor, model, serial, and firmware when available
- transport kind and a non-secret endpoint identifier
- command or acquisition operation
- capture timestamp and timezone/clock basis
- raw response path and SHA-256
- normalized artifact path and SHA-256
- decoder/parser name and version
- manual title, revision, URL, and page/section
- calibration source, hash, and evidence
- known redactions and limitations

Do not place credentials in manifests or fixtures. Redact private network details
that are not needed for reproducible parsing.

## Evidence levels

- `documented`: claim follows an official manual but has no hardware evidence.
- `hardware-verified`: a real instrument response was checked.
- `firmware-scoped`: the real check records exact model, firmware, interface, and
  date.

Use the lowest level that supports the particular claim. A parser can be
`documented` while a voltage calibration remains `UNVERIFIED`.

## Calibration binding

External calibration must identify the exact raw or merged artifact by SHA-256 and
state how the reference was measured. Never apply a calibration file merely because
its instrument model matches.
