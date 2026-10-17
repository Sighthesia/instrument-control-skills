---
name: siglent-sds824xhd-control
description: Control and capture waveforms from a Siglent SDS824X HD/SDS800X HD over one explicit raw SCPI TCP session. Use for single-shot captures, waveform downloads, signal measurements, screenshots, protocol decode, anomaly search, and progressive task-specific SCPI command discovery.
---

# Siglent SDS824X HD Control

Use this skill whenever an AI needs to operate the Siglent SDS824X HD, capture a stopped frame, download waveform data, decode it, or diagnose a mismatch between screen record length and downloaded files.

## Non-negotiable Safety Rules

- Never send `ARM`. `TRMD SINGLE` is the only accepted single-shot start operation on firmware `4.8.12.1.1.6.5`.
- A valid capture requires the observed state transition `Ready -> Stop`. A `Stop` observed without a prior `Ready` is not proof of a new capture.
- After `Stop`, do not send `STOP`, `ARM`, `RUN`, `TRMD`, trigger/timebase/channel configuration, `WFSU`, or a TCP reconnect while reading the frame.
- In an immutable legacy read, issue every channel's `WF? DAT2` first. Only after all payloads are saved may the caller explicitly issue `WF? DESC`.
- Keep `immutable_capture` and `configured_capture` explicit. Never silently send `WFSU`, restore `TRMD`, or clean up the instrument.
- Never use `max_points` as evidence of instrument record length. It is only a local CSV/downsampling setting.
- Preserve raw payloads and metadata before producing CSV. A short payload is `INCOMPLETE` or `INVALID`, never complete.

## Progressive Query Reference

Load only the reference matching the current debugging goal. Do not read every command reference up front, and do not expose unrelated configuration commands in the active workflow.

| Goal or observation | Read this reference |
|---|---|
| Identify the scope, find a signal, auto-range, inspect trigger/acquisition state, or evaluate voltage/timing/jitter | [Signal discovery and measurement](references/signal-discovery-and-measurement.md) |
| Inspect waveform shape visually, fetch a screenshot, or download samples for external analysis | [Screenshot and waveform data](references/screenshot-and-waveform.md) |
| Diagnose UART/I2C/SPI/CAN/LIN or another supported serial bus | [Protocol decode](references/protocol-decode.md) |
| Find runt pulses, glitches, timing violations, mask failures, or replay a captured fault | [Anomaly search and mask testing](references/anomaly-search-and-mask-testing.md) |
| Measure long-term frequency/period statistics, inspect cursor deltas, or inspect history timestamps | [Counter, cursor, and history](references/counter-cursor-and-history.md) |

Start with the matching reference's read-only snapshot. Use a setup/enable command only when that workflow requires it and the caller authorized changing scope state. Each reference distinguishes target-hardware-tested behavior from manual-documented behavior and notes feature prerequisites.

## Raw TCP Session

1. Connect once to SCPI TCP port `5025`; do not use legacy shell port `5024`.
2. Send `*IDN?` and save the returned identity before issuing model-specific commands.
3. Use `scripts/scope_protocol.py` for byte-preserving raw TCP queries and binary blocks; use `scripts/capture_scope.py` for complete segmented waveform downloads.
4. Apply channel or acquisition configuration only when explicitly requested, and do it before starting a new single acquisition.
5. Start a single acquisition with `TRMD SINGLE`; never send `ARM`. Poll `SAST?` until `Ready`, stimulate the DUT, then poll until `Stop`. Do not automatically retry.
6. Keep the same socket session for the complete capture. Do not trigger and then reconnect to read the frame.
7. Treat an export as unverified unless raw payload length and descriptor point count agree. A CSV or downsampled view alone does not prove a complete capture.

## Hardware Profile

- Target: `Siglent SDS824X HD`, IP `192.168.10.2`, SCPI TCP `5025`.
- Port `5024` is a legacy shell-like channel. It may begin with `Welcome to the SCPI instrument 'Siglent SDS824X HD'` and `>>`; never parse either as a query result.
- Channel mapping: `C1=ENABLE`, `C2=nFAULT`, `C3=HOC`, `C4=P4.1/CMP`.
- Typical setup: C1/C2/C4 `VDIV 2`, C3 `VDIV 5`, all `OFST 0`, probe `10`; edge trigger on C1 rising at `2.5 V`; `TRMD SINGLE`; `500 ms/div`; `5.00 MSa/s`; `25.0 Mpts`; about `-2 s` trigger delay.
- Expected record: `25,000,000` points, `200 ns` per point, `5 s`.

## Approved Workflows

### New Capture

1. Connect once and identify the scope.
2. Snapshot configuration before changing anything.
3. If requested, configure channels and trigger before starting acquisition.
4. Issue `TRMD SINGLE`; never issue `ARM`.
5. Poll `SAST?` until `Ready`; stimulate the DUT; poll until `Stop`.
6. Freeze the command set. Do not restore `TRMD AUTO` automatically.
7. For a full-length transfer, use the modern segmented path with the bundled script. Treat it as `configured_capture` because the scope receives transfer-selection writes after `Stop`; the path is verified for complete transfer integrity, but it is not called immutable:
   - `WAV:SOURce Cn`
   - `WAV:WIDTh WORD` when the preamble reports more than 8 nominal bits; use `--wav-width byte` only for an explicitly labeled lossy historical comparison
   - `WAV:BYTeorder LSB` for WORD transfers, followed by `WAV:BYT?` readback
   - `WAV:INTerval 1`
   - `WAV:STARt <start>`
   - `WAV:POINt <count>`
   - `WAV:DATA?`
8. Save one raw binary file and one metadata file per segment. For BYTE expect `count` payload bytes; for WORD expect `count * 2` payload bytes. Check each returned payload length and checksum.
9. Build the full report only after all segments have contiguous ranges from `0` through `array_count - 1`.

For a trigger-following burst, configure the optional horizontal strategy before step 4:

```text
python3 scripts/capture_scope.py \
  --out /path/to/capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --prepare --trigger \
  --left-aligned-trigger --trigger-margin-div 1 \
  --memory-depth auto --reference-position 10 \
  --wav-width auto
```

This queries `TIM:SCAL?`, sets `TIM:DEL = (5 - margin_div) * timebase`, and verifies the timebase, delay, memory-depth, and optional `TIM:REF:POS` readbacks before `TRMD SINGLE`. With `margin_div=1`, the trigger has one division of pre-trigger context and nine divisions of post-trigger window. The strategy is opt-in and is not valid with `--existing-stopped`; use a larger margin when pre-trigger history is important.

Example for the current stopped C4 frame:

```text
python3 scripts/capture_scope.py \
  --host 192.168.10.2 --port 5025 \
  --out /path/to/c4-capture --channels C4 \
  --mode modern --capture-mode configured_capture \
  --existing-stopped --segment-points 5000000 \
  --probe-points 10000,1000000 \
  --wav-width auto
```

The command writes `C4/segment-*.bin`, response/prefix files, per-segment JSON, `C4/waveform.bin`, and `manifest.json`. It creates `waveform.bin` only after the complete range validates.

### Existing Immutable Stopped Frame

Use this only when the caller explicitly says the current stopped frame is the target.

1. Do not send `STOP`, `TRMD`, `RUN`, `ARM`, `WFSU`, or configuration writes.
2. Read `C1:WF? DAT2`, `C2:WF? DAT2`, `C3:WF? DAT2`, and `C4:WF? DAT2` as requested; save every raw response.
3. After all DAT2 reads finish, optionally issue `C<n>:WF? DESC` as a separate explicit diagnostic step.
4. Compare `array_count`/`data_length` from the descriptor with actual payload bytes. For 8-bit DAT2, bytes equal points.

### Configured Repetitive Capture

This is not immutable. It may use `WFSU SP,1,NP,0,FP,0` before the new `TRMD SINGLE` capture and may select a fresh waveform memory view. Label artifacts `configured_capture`, record every WFSU command, and do not use the result to make claims about the original stopped frame. Never send WFSU after `Stop` in a stopped-frame read.

## Binary Response Rules

Use `scripts/scope_protocol.py` for all byte parsing.

- Search until `#` is found; arbitrary ASCII, NUL bytes, prompts, and status bytes may precede it.
- Read one ASCII digit `N`, then exactly `N` ASCII decimal length bytes, then exactly that many payload bytes.
- Validate the payload length. Keep `prefix`, the complete block header, payload, and SHA-256.
- A payload may contain `#`, NUL, CR, or LF; never split it on lines.
- A timeout, missing marker, non-decimal length, or short payload fails closed.

## Local AI Waveform Analysis

Use the bundled read-only analyzer after a capture has produced a complete `manifest.json`. It never reconnects to or writes the oscilloscope and it never replaces the raw `waveform.bin` evidence:

```text
python3 scripts/analyze_waveform.py inspect --capture /path/to/capture --channel C4
python3 scripts/analyze_waveform.py summarize --capture /path/to/capture --channel C4 --preview-buckets 256
python3 scripts/analyze_waveform.py events --capture /path/to/capture --channel C4 --threshold-codes 20 35 --limit 100
python3 scripts/analyze_waveform.py window --capture /path/to/capture --channel C4 --start 123456 --count 512
```

The analyzer validates the complete frame, merged file size, SHA-256, segment ranges, width, byte order, and sampling metadata before reading samples through NumPy `memmap`. It scans large records in bounded chunks and returns compact JSON rather than raw arrays. `summarize` reports exact integer-code statistics and an M4 preview labeled `visualization_only_lossy`; the preview must not be used as a substitute for event detection. `events` scans original-resolution samples and returns bounded pages with a stateless cursor. `window` is the escalation path for inspecting samples around an event.

WORD captures retain raw signed little-endian codes. Unless an independent calibration JSON is supplied, WORD analysis reports `OBSERVED_UNVERIFIED` and emits code-domain values only; a 16-bit transport container is not automatically treated as a 16-bit voltage-calibrated ADC result. BYTE voltage conversion uses descriptor VDIV, probe factor, offset, and codes/div after cross-checking the captured panel snapshot; a mismatch is reported as a calibration limitation rather than used to produce voltage fields. Analysis output defaults to stdout and must be written outside the raw capture directory with `--out`.

An independent WORD calibration file must bind evidence to the exact merged waveform SHA-256 and use this minimum shape:

```json
{
  "channels": {
    "C4": {
      "word_scale_verified": true,
      "capture_sha256": "<merged waveform SHA-256>",
      "word_codes_per_div": 7680,
      "vdiv_v_per_div": 5.0,
      "offset_v": 0.0,
      "evidence": "known DC reference and BYTE/WORD comparison"
    }
  }
}
```

The analyzer rejects stale or incomplete evidence back to code-domain output. It does not infer WORD voltage scaling from `code_per_div * 256` alone.

## Waveform Decode and Validation

For modern `WAVeform:PREamble?`, parse the documented little-endian fields in `scripts/scope_protocol.py`. Keep at least `wave_array_1`, `wave_array_count`, `start`, `interval`, `vdiv`, `offset`, `code_per_div`, `adc_bit`, `sample_interval`, `delay`, `tdiv`, and `probe`.

For BYTE data, decode signed samples as `byte - 256 if byte > 127 else byte`. Use `vdiv / code_per_div`; do not hard-code `/32`. For WORD data, retain the raw two-byte LSB payload and report `voltage_decode=unverified_for_WORD` until the device-specific left-alignment ratio is independently calibrated. A 16-bit transport container must not be called a 16-bit ADC result. The current observed descriptor reports `nominal_bits=16`, `code_per_div=30`, and `MAX_VALUE=7680`; the WORD transfer has been hardware-verified for byte completeness, not voltage scaling.

Use the validator to report all three quantities:

```text
scope_record = 25,000,000 points / 5 s
wavedesc     = 25,000,000 points / 5 s
downloaded   = 5,000,000 points / 1 s
status       = INCOMPLETE
```

Any empty, truncated, wrong-width, overlapping, or missing segment invalidates the complete channel. Do not infer missing samples or silently pad.

## Bundled Resources

- `scripts/scope_protocol.py`: byte-preserving TCP session, IEEE 488.2 block reader, preamble/descriptor parser, segment and frame validators.
- `scripts/capture_scope.py`: one-session raw TCP capture CLI with explicit immutable/configured modes, staged modern probes, complete segmented reads, and atomic merged output. `--prepare` is only valid with `--trigger`; `--existing-stopped` must never be combined with setup or trigger options.
- `scripts/test_scope_protocol.py`: offline tests for framing, 25M-vs-5M rejection, boundary errors, and WAVEDESC fields.
- `scripts/scope_protocol.py`: also exposes `configure_left_aligned_trigger` and `configure_memory_depth` for new captures; both preserve the no-`ARM` workflow.
- `scripts/waveform_analysis.py`: read-only manifest validation, BYTE/WORD memory-mapped access, exact bounded summaries, M4 visualization preview, threshold/runt/long-interval events, and raw window extraction.
- `scripts/analyze_waveform.py`: bounded JSON CLI with `inspect`, `summarize`, `events`, and `window` subcommands.
- `scripts/test_waveform_analysis.py`: synthetic capture tests for integrity, relocation, BYTE/WORD behavior, statistics, M4 bounds, event chunk boundaries, cursors, scan budgets, and window limits.
- Task-specific command references under `references/`: load only the page selected by the goal table above. `programming-guide.md` records waveform implementation notes and is not a general command catalog.

The protocol module exposes the handover API names: `scope_connect`, `scope_identify`, `scope_snapshot_configuration`, `scope_prepare_capture`, `scope_arm_single`, `scope_wait_ready`, `scope_wait_stop`, `scope_read_immutable_frame`, `scope_read_segment`, `scope_read_descriptor`, `scope_validate_frame`, `scope_restore_run_mode`, and `scope_disconnect`. `scope_arm_single` sends only `TRMD SINGLE`, never `ARM`. Descriptor reads remain an explicit post-download action.
- `references/programming-guide.md`: command semantics and manual page references used by this skill.

Run `python3 scripts/test_scope_protocol.py` and `python3 scripts/test_waveform_analysis.py` before relying on modified transport or analysis code. On firmware `4.8.12.1.1.6.5`, C4 passed both transport checks: the historical BYTE run returned `25,000,000` bytes; the automatic WORD run selected WORD from `nominal_bits=16`, read back `COMM_TYPE=1`/LSB and `WAV:INT=1`, and returned `25,000,000` points / `50,000,000` bytes over five segments. Both had a calculated `5.000000058 s` span and no `ARM`, `STOP`, `TRMD`, or `WFSU` writes. The analyzer accepts the historical BYTE artifact and reports verified BYTE voltage fields; it intentionally keeps WORD voltage scaling `OBSERVED_UNVERIFIED` until an independent calibration artifact is supplied.
