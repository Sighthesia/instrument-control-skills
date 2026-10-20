# Conditional acquisition features

These features are documented but not assumed available or configured. Check
the installed options, external wiring, current state, and intended sequence
before use. Manual citations use PDF physical pages from the Model 2000 User's
Manual.

## Trigger model

The model proceeds through idle, control source/event detection, optional delay,
device action, and output trigger (PDF 55-59, 201-204). The SCPI trigger family
includes `:INITiate`, `:INITiate:CONTinuous`, `:ABORt`,
`:TRIGger:COUNt`, `:TRIGger:DELay`, `:TRIGger:SOURce`,
`:TRIGger:TIMer`, and `:SAMPle:COUNt`.

- Configure and query the source (`IMMediate`, `TIMer`, `MANual`, `BUS`, or
  `EXTernal`), count, delay, and sample count deliberately.
- Trigger count is `1` to `9999` or `INF`; sample count is `1` to `1024`.
- Delay is `0` to `999999.999 s`; timer interval is `0.001` to
  `999999.999 s`.
- External `EXT TRIG` input is TTL-compatible and triggers on a falling edge;
  minimum pulse width is `2 µs`. VMC output minimum pulse width is `10 µs`
  (PDF 58-59). Verify Trigger Link wiring and line assignment before connecting
  instruments.
- Do not combine continuous initiation with `:READ?`; avoid `*OPC?` while
  continuous initiation is on. Keep timeout/recovery operator-controlled.
- `:INITiate` is also ignored with `-213,"Init ignored"` when the instrument is
  not idle — for example after `:INITiate` has armed a `BUS` or `EXTernal`
  trigger. Observed on 2026-10-20: the first `:INITiate` was clean, the second
  one while still armed queued `-213`.
- While an armed acquisition is waiting for its trigger, a `:FETCh?`/`:READ?`
  never produces output. Every later query then times out because the output
  queue is blocked; recover with a device clear (`0x03`, `:ABORt` alone did not
  clear the blocked queue in the verified session) and then restore
  `:TRIGger:SOURce IMMediate` before any other work.
- When continuous initiation is on, sample count must be one. `:READ?` with
  sample count greater than one and pre-existing buffer readings returns `-225`
  (out of memory).
- No automatic retry after an external-trigger timeout: retrying can misalign
  the requested sequence and the external DUT/channel state.

## Reading hold

Hold/autosettle uses a seed reading, a percentage window (`0.01` to `20`), and a
consecutive reading count (`2` to `100`) (PDF 57-58, 170). It changes when a
reading is considered settled. Record window/count/state and do not interpret
the released value as an unfiltered single conversion.

## Buffer and statistics

The trace buffer has capacity `2` to `1024` readings and supports a reading
source (`SENSe[1]`, `CALCulate[1]`, `NONE`), control (`NEVer`, `NEXT`), clear,
free-space query, and data query (PDF 64-66, 199-200).

- Record the buffer capacity, source, control, expected count, observed count,
  and end-of-sequence evidence. Buffer data is not persistent across power loss.
- Inspect overflow/half-full/full status and error messages; preserve any
  overflow evidence. Never make a complete sequence by padding missing readings.
- Buffer transfer format/element selection applies to buffer data. Binary
  `SREal`/`DREal` framing is not decoded by the bundled scalar parser.
- Buffer statistics (mean, standard deviation, maximum, minimum) are a derived
  result; preserve the contributing readings or report that they were not
  independently captured (PDF 153-154).

## Limit tests

Limit operations compare readings against configured upper/lower values; they
are applied after MX+B/percent math and are not supported for continuity (PDF
67-68, 155-156). Record thresholds, math state/order, enable state, fail/result
query, and limit event status. Do not infer which bound failed from a single
boolean result if the event/status evidence is unavailable.

## Scanning

Scanning requires a compatible internal scanner card or external switch system.
Gate internal scan workflows on `*OPT?` and confirmed channel topology; gate
external scans on a separately configured switch and trigger link (PDF 69-78,
163-167).

- Internal scan lists contain `2` to `10` consecutive channels; skipping an
  internal channel is not allowed. External scan lists can contain `2` to `800`
  external channels and require a configured external switch system.
- Do not issue single-channel `:ROUTe:CLOSe` commands while a scan is active.
- Record scan list, scan mode, channel count, settling/hold, trigger source,
  per-channel reading count, and completion marker.
- If the option card, switch, wiring, or topology is unknown, report
  `UNSUPPORTED` rather than attempting a scan.

## Avoid unrelated system operations

Self-test, calibration, line-power/fuse operations, saved power-on setup, and
front-panel lockout are not part of routine measurement acquisition. Do not
initiate or modify them unless specifically requested and the corresponding
manual procedure has been reviewed. The manual places system operations in
PDF 79-80 and calibration details outside the scope of this Skill.
