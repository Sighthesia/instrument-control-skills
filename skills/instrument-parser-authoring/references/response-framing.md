# Response Framing

Framing answers one question: where does this response begin and end? Solve that
before interpreting units, fields, or samples.

## Common formats

- **Line-oriented text**: preserve bytes through the line terminator, then decode
  with an explicit encoding and error policy.
- **CSV**: preserve the original bytes and define quoting, delimiter, header, and
  row-count behavior before using a CSV parser.
- **IEEE 488.2 definite-length block**: find `#`, read the length-of-length digit,
  read exactly that many length digits, then read exactly the declared payload.
  Never split binary payload on CR or LF.
- **Length-prefixed custom binary**: validate the prefix width, byte order, and
  maximum length before allocating or reading the body.
- **Packetized or segmented data**: preserve sequence numbers and validate gaps,
  duplicates, overlaps, and final-record markers.

## Failure rules

Return `INVALID` for an impossible marker, non-numeric length, illegal field width,
or malformed header. Return `INCOMPLETE` for a short body, missing segment, or
truncated stream. Return `UNVERIFIED` when the format has no evidence that can
prove completeness. Keep extra trailing bytes as evidence; do not silently discard
them.

## Resource limits

Reject unreasonable declared lengths before allocating memory. Prefer bounded
streaming reads, temporary files, and memory mapping for large captures. A parser
must not turn a corrupt length field into an unbounded allocation.
