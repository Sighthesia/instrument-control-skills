# Axes, Spectra, and Sequences

## Independent axes

For spectra, sweeps, and time series, validate the independent axis separately from
the measured values:

- point count matches both value and axis arrays
- start, stop, interval, or bin width are finite and mutually consistent
- axis values are monotonic when the format promises ordering
- units and reference level are known for the intended claim

Do not invent an axis from array position when the instrument's sample interval or
frequency spacing is unavailable.

## Event records

For logs and event sequences, check sequence IDs, timestamps, record counts,
continuation/end markers, and ordering. A missing timestamp may prevent duration or
rate claims even when all event payloads are present.

## Extra and duplicate records

Keep duplicate, out-of-order, and trailing records visible in the report. A parser
may preserve them for forensic review, but a normalized analysis dataset must state
whether they were excluded and why.
