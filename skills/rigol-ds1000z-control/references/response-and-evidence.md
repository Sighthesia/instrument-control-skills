# Response and Evidence (DS1000Z)

Manual: *MSO1000Z/DS1000Z Programming Guide*, Software Version 00.04.03.SP2,
Dec 2015 (PDF physical pages); error queue PDF p. 161, waveform PDF pp. 232-242,
preamble PDF p. 242, display data PDF p. 79, measurements PDF pp. 128-141.
Support level: `firmware-scoped` on firmware `00.04.02.SP4`.

## Parser stages

`scripts/ds1000z_protocol.py` is transport-independent and standard-library only.
The stages are independently callable:

1. `read_frame(raw)` — one LF-terminated response line. Retains content, records
   whether a terminator was present, and rejects empty or oversized frames.
   An unterminated frame is **not** an error to repair: it is returned as
   unterminated so the caller can classify it.
2. `parse_metadata(frame, response_type=...)` — decodes text and classifies
   identity, measurement, error-queue, or preamble tokens.
3. `extract_payload(metadata)` — exposes raw fields (`vendor`/`model`/`serial`/
   `firmware`, the numeric token or the `9.9E37` sentinel, or the queue
   `code`/`message`) without conversion.
4. `normalize(metadata, payload, ...)` — validates the fields, resolves units,
   classifies the record, and builds the artifact with `status`, `checks`, and
   `reasons`.
5. `validate(artifact, raw)` — attaches the raw-byte SHA-256, parser version,
   support level, and the integrity block.

Waveform stages:

1. `parse_preamble(raw)` — the ten comma-separated fields `format`, `type`,
   `points`, `count`, `xincrement`, `xorigin`, `xreference`, `yincrement`,
   `yorigin`, `yreference` (manual PDF p. 242).
2. `parse_ieee_block(raw)` / `parse_block(raw)` — `#9` + nine ASCII length digits
   + payload, plus at most the trailing LF. Enforces the declared length exactly.
3. `parse_waveform(...)` / `normalize_waveform(...)` — point count versus declared
   payload length, preamble `points` versus `STOP - STARt + 1`, mode field versus
   requested mode, calibration status, and artifact construction; `iter_codes`,
   `sample_voltage`, and `waveform_to_csv` expose the per-point view.
4. `validate(...)` — raw and payload SHA-256, parser version, limitations.

Screenshot handling adds one mandatory stage: trim the payload to the declared
length, record the discarded byte count (three on the evidence unit), then check
the BMP header with `parse_bmp_header` (`BM`, `bfSize`, pixel offset) before
writing a file.

## Statuses

- `COMPLETE`: framing, required fields, units, and applicable structural
  checks pass for the stated claim.
- `INCOMPLETE`: a required byte, terminator, field, point, or response element
  is missing.
- `INVALID`: framing, numeric, field, or type constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded but calibration, freshness, undocumented
  metadata, or hardware acceptance is not proven.
- `UNSUPPORTED`: the response shape or feature is not implemented.

Never silently pad, truncate, clamp, interpolate, or guess. Line responses keep
the raw bytes as SHA-256 and note the terminator state; waveform and screenshot
artifacts keep declared and observed lengths plus both SHA-256 values and leave
the raw binary file to the caller.

## Mapping the DS1000Z's own behaviours onto statuses

These cases were all observed on firmware `00.04.02.SP4`
(`hardware-verified`); the classification is this Skill's decision:

| Observation | Status | Why |
|---|---|---|
| Reply line ends with LF | `COMPLETE` | Framing complete, terminator present |
| `command error` (13 bytes, no terminator) after an undefined header | `INCOMPLETE` | Reply truncated by the instrument; the frame carries no terminator and no value |
| Any reply cut off at the read timeout | `INCOMPLETE` | Missing bytes; never treat the partial text as a value |
| `9.9E37` from `:MEASure:*?` | `INCOMPLETE` | Documented "no result" sentinel, not a measurement; the reason must say so |
| A measurement reply that is not one bare numeric token, for example `VPP,3.040000e+00` | `INVALID` | The firmware answers `:MEASure:ITEM?` with the bare NR3 value only; an item-name prefix means the wrong shape arrived |
| `-350,"Queue overflow"` in the error queue | `INCOMPLETE` | The real error was lost before it could be read |
| Error record `-220` or `-200` on a write | `UNVERIFIED` | The instrument reported an error; the write failed and the previous value may still be in force. The message is preserved, never read as success |
| Any other queued error record (`-113`, …) | `UNVERIFIED` | A real error exists but its cause is the operator's to interpret |
| Preamble `points` disagreeing with `STOP - STARt + 1`, or a mode field that contradicts the requested mode | `INVALID` | Metadata contradicts the request and the raw bytes |
| `#9` declared length ≠ observed payload length (waveform) | `INVALID` | Framing defect in the response |
| `:DISPlay:DATA?` with three bytes past the declared length, after trimming | `COMPLETE` | Trimmed to the declared length; the defect is recorded in the artifact, not hidden |
| Same screenshot, untrimmed | `INVALID` | The stream fails the declared-length check and `file(1)` rejects it |
| Any waveform code-to-volt conversion | `UNVERIFIED` | Calibration is not proven for either mode |
| A waveform block for a channel that is not displayed | `UNVERIFIED` | The instrument returns bytes with a nonsense increment; the block is not evidence that the channel setup is valid |

A report may contain passing checks and still be `UNVERIFIED` when an essential
property has no evidence; for example a structurally perfect RAW capture still
has unknown voltage calibration.

## Calibration caveat (do not skip)

The reproducible relation on the evidence unit is

```text
volts = (code - yorigin - yreference) * yincrement
```

with zero code at `yorigin + yreference` (51 in NORM at 0.5 V/div). It reproduced
`:MEASure:VPP?` on the same screen, which is a consistency check — **not** a
calibration. Two facts block a calibration claim:

- `yincrement` differs between modes at the same V/div: 0.02 in NORM or
  MAXimum-style screen data versus 0.0209375 in RAW at 0.5 V/div
  (`hardware-verified`). Reusing a NORM increment for RAW bytes produces a 4.7 %
  amplitude error that looks like a real reading.
- The probe compensation terminal is explicitly not a voltage reference (User
  Guide PDF page 31), so the instrument's own front panel cannot supply the
  reference for an in-repo calibration.

Never apply a calibration file merely because the model matches. A calibration
must name the exact raw artifact by SHA-256 and state how the reference was
measured; without that, keep volts `UNVERIFIED` and support code-domain claims
only.

## Provenance chain

Record enough to reconnect an artifact to the instrument response:

- vendor, model, serial, firmware (from `*IDN?`), plus `:LAN:MAC?` when
  available
- transport kind and endpoint (host/port), with bench-specific addresses kept out
  of committed fixtures
- the exact command, or the acquisition operation
- capture timestamp with timezone
- raw response path and SHA-256
- normalized artifact path and SHA-256
- parser name and version and the support level that applied
- manual title, revision, and the pages used
- calibration status (`none` for every artifact this Skill produces)
- known limitations and redactions

## Analysis gate

Expose an explicit gate rather than letting a consumer infer it:

- `COMPLETE` structure, screenshots -> image use allowed; no electrical claim.
- `COMPLETE` waveform, calibration unknown -> shape, timing, relative level, and
  code statistics allowed; absolute volts not allowed.
- `INCOMPLETE` waveform -> no complete-record duration, frequency, or amplitude
  claims.
- `UNVERIFIED` scalar sequence -> report values, but do not claim acquisition
  completeness or stable timing.
- A failed or retried read is never merged into a complete record.
