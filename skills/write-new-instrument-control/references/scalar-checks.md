# Scalar Measurement Checks

Scalar readings do not have waveform payload lengths, so completeness evidence must
come from the measurement sequence and instrument status.

Check, when available:

- expected reading count versus observed reading count
- response framing and token count
- units and measurement function
- range, resolution, NPLC, filter, and other configuration context
- overload, compliance, error, or questionable-status flags
- documented sentinels for no-result, overflow, or not-set, matched before any
  numeric conversion
- timestamps or sample indices and their ordering
- trigger, buffer, sweep, or end-of-sequence markers
- error queue state and whether the response belongs to the requested operation

Reading a valid-looking number does not prove that the instrument used the intended
function, range, or acquisition configuration. If the device exposes no sequence,
status, timestamp, or count evidence, report the reading but keep acquisition
completeness `UNVERIFIED`.

Repeated values may be summarized statistically only after documenting whether the
sequence is complete and whether the values share comparable configuration.

## Non-values before numbers

Enumerate the instrument's non-values before parsing any number. A no-result or
not-set sentinel is often syntactically a valid number, and a float cast turns it
into a plausible measurement.

- Match the literal token against an enumerated sentinel table before numeric
  conversion. Keep that table per query family, with a manual page and whether
  the value was observed.
- Report a sentinel as a `null` field with a reason, and make the enclosing
  status `INCOMPLETE`. Never map it to `0`, `NaN`, the minimum, or "no signal".
- Expect more than one shape. Common ones are a large decimal such as `9.9E37`
  for "no result", an all-ones integer such as `4294967295` (uint32 -1) for "not
  set", and an overflow token the manual documents without a unit. Which one a
  query returns is instrument- and firmware-specific; record the observed shapes
  in the sentinel table rather than assuming one.
- The manual may be silent about the sentinel. If so, report a suspected sentinel
  as `assumed`, prove it by observation on the instrument, and never introduce a
  magnitude cutoff the manual does not state.
- A sentinel does not mean zero signal; it means the instrument did not produce a
  value. State which of the two was observed.
- Exclude `null` values from statistics and report the reduced count; a mean over
  the remaining readings is not the mean of the requested set.
