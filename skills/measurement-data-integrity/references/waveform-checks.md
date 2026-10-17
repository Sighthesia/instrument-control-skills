# Waveform Checks

Apply only checks supported by the waveform decoder and acquisition evidence.

## Required structural checks

1. Declared point count is finite and non-negative.
2. Declared bytes per point is known and the expected payload size equals the
   observed payload size.
3. Segment starts and counts cover the intended range exactly once, without gaps or
   overlaps.
4. Each segment file size and hash match its metadata before merging.
5. Sample interval and time origin are present and finite when time-domain claims
   are made.
6. The waveform encoding, signedness, byte order, and width match the decoder.

## Boundary rules

An empty, short, overlapping, or wrong-width segment invalidates the complete
merged waveform. Do not infer missing samples or pad the tail. A complete payload
can still have `UNVERIFIED` voltage calibration; keep code-domain and physical-unit
claims separate.

## Analysis consequences

- No complete range: do not report full-record duration or frequency as measured.
- Unknown sample interval: sample-index statistics may be valid, time statistics
  are unverified.
- Unknown scale or offset: report raw codes or relative amplitude only.
- Boundary-touching event windows: flag that local context is missing.
