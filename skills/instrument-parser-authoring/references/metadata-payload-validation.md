# Metadata, Payload, and Validation

## Metadata is not payload

Metadata describes how to interpret data. Payload is the data itself. Keep them
separate so that a parser can report a valid header with an invalid body instead of
returning a misleading measurement.

Useful metadata includes:

- data kind and encoding
- declared element count and bytes per element
- unit and scale
- sample interval or independent-axis origin
- byte order and signedness
- acquisition configuration
- calibration source and status

## Validation checks

Apply only checks supported by the evidence:

1. Declared element count multiplied by bytes per element equals observed payload
   length.
2. Segments cover the expected range exactly once, with no gaps or overlaps.
3. Checksums, CRCs, or hashes match when supplied.
4. Numeric fields are finite and units are recognized.
5. Time or frequency axes are monotonic when the format promises ordering.
6. Configuration and status fields are compatible with the claimed operation.

If a check cannot be performed, record `not_checked` or `UNVERIFIED`; do not mark
it as passed.

## Normalization

Normalize only semantics supported by evidence. Retain raw codes when calibration
is uncertain. For example, a two-byte transport container is not automatically a
16-bit voltage-calibrated ADC result. Preserve the original encoding and expose a
calibration status alongside any converted values.
