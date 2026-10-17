# Scalar Measurement Checks

Scalar readings do not have waveform payload lengths, so completeness evidence must
come from the measurement sequence and instrument status.

Check, when available:

- expected reading count versus observed reading count
- response framing and token count
- units and measurement function
- range, resolution, NPLC, filter, and other configuration context
- overload, compliance, error, or questionable-status flags
- timestamps or sample indices and their ordering
- trigger, buffer, sweep, or end-of-sequence markers
- error queue state and whether the response belongs to the requested operation

Reading a valid-looking number does not prove that the instrument used the intended
function, range, or acquisition configuration. If the device exposes no sequence,
status, timestamp, or count evidence, report the reading but keep acquisition
completeness `UNVERIFIED`.

Repeated values may be summarized statistically only after documenting whether the
sequence is complete and whether the values share comparable configuration.
