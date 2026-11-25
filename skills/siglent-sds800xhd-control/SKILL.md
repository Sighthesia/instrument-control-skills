---
name: siglent-sds800xhd-control
description: Control and capture waveforms from a Siglent SDS800X HD series oscilloscope (verified on SDS824X HD) over one explicit raw SCPI TCP session. Use for single-shot captures, waveform downloads, signal measurements, screenshots, protocol decode, anomaly search, and progressive task-specific SCPI command discovery.
---

# Siglent SDS800X HD Control

Use this skill to find a signal, take a single-shot capture, download waveform samples, take a screenshot, decode a bus, or explain a mismatch between the screen record and a downloaded file on any SDS800X HD series instrument (SDS802X/804X/812X/814X/822X/824X HD; 2 or 4 channels, 50 or 100 Mpts). **What "verified" covers is per claim, not per Skill**: the raw TCP session, the capture and waveform-download path, the `:MEASure:SIMPle:VALue?` readings, and the failure modes below were exercised on an `SDS824X HD` (firmware `4.8.12.1.1.6.5`, SCPI TCP `5025`); the `channel_snapshot.py` sample-probe/source-readback helper, the `:PRINt?` reader, and the decode-list reader are `documented` + offline-tested only (not yet hardware-verified), and model-dependent limits must be confirmed against the connected instrument. Offline waveform analysis, verdict gating, and five-axis evidence reporting are **optional** and ship as the independent `oscilloscope-waveform-analysis` Skill, which consumes the portable `<channel>.bundle.json` (`waveform-bundle/v1`) files this Skill writes.

## Default One-Command Check

Run this first for any "does this channel carry a signal / is it 0 V / is the waveform sane" question:

```text
python3 scripts/channel_snapshot.py --host <ip> --channels C1 C2 ... --out-dir <dir>
```

One explicit TCP session and one raw reply per row; `--out-dir` writes `snapshot.json` plus `screen.png`, with the screenshot taken **last** on that same session. It reads per-channel switch, V/div, offset, coupling and unit, the acquisition and trigger context, the horizontal context (`TIM:SCAL?`, `ACQ:SRAT?`, `ACQ:POIN?`), and source-verified simple-measurement amplitude — only the channel both `:MEASure:SIMPle:SOURce?` readbacks name receives a value. On a **stopped** frame it then probes each enabled channel through `WAV:SOUR/WIDT/BYT/INT/STAR/POIN/PRE?/DATA?` and reports `code_min`/`code_max`/`code_span`, clipping against the signed transfer bounds, coverage (`coverage_mode`, `sampled_points`, `total_points`, `coverage_ratio`), and `activity_hint` (`ACTIVE_CODES`, `FLAT_IN_FULL_RECORD`, `FLAT_IN_SAMPLED_SLICES_ONLY`, `CLIPPED`, `UNVERIFIED`). A record longer than the slice budget is read as three slices (`PARTIAL_SLICES`), not as the whole record. `--strict-readonly` disables every `WAV:*` write for a 0-write query-only session; `--slice-points` sets the slice budget; `--screenshot <png>` or `--out-dir <dir>` adds the closing PNG, and without one `visual_context.status` is `NOT_CAPTURED`. `next_actions` carries the ordered follow-ups and is part of the evidence, not optional advice.

Contracts, the apparent-zero triage order, and the JSON field semantics are in [Signal discovery and measurement](references/signal-discovery-and-measurement.md#per-channel-evidence-before-a-no-signal-verdict); the screenshot contract and its qualitative-only limits are in [Screenshot and waveform data](references/screenshot-and-waveform.md).

## Bidirectional Blind-Spot and Second-Capture Rules

Two one-sided observations are both wrong, and each hides the other's failure:

- **A PNG alone never decides presence.** A rendered band, a colour, a screenshot, or the on-screen measurement panel cannot establish that a channel is flat, at 0 V, or undriven; the panel describes only the selected simple-measurement source. A screenshot is qualitative context only.
- **Numbers or partial slices alone never decide the record.** Local values, one measurement window, or a `PARTIAL_SLICES` probe cannot support either "no signal across the record" or "the waveform is normal". A record-wide statement needs the coverage figures plus a whole-screen visual overview or a full-record read, cross-checked against each other.

**Second-Capture Rule.** For "no signal", "0 V", "waveform abnormal", "suspect hardware, power or ground fault", or "reflash the firmware", one observation is never enough. Take a second capture from a different view as `next_actions` directs — a wider or zoomed timebase, a changed V/div range, or a full record plus a screenshot that cross-check — and use it to falsify a scope setup cause first, a board cause only afterwards.

**3-Line Evidence Gate.** Before reporting a hardware or fault conclusion, list these three lines in the answer itself:

1. each channel's raw readings with code span and coverage (`sampled_points`/`total_points`/`coverage_ratio`/`coverage_mode`);
2. whether the visual whole-frame evidence (screenshot or full record) and the trigger/acquisition state were actually inspected;
3. the second-capture result, plus every setup, same-board GND, and `UNVERIFIED` item still not excluded.

Without all three the honest outcome is `UNVERIFIED` plus the required next action.

## Non-Negotiable Safety Rules

- **Never send `ARM`.** `TRMD SINGLE` is the only accepted single-shot start (documented spelling `:TRIGger:MODE SINGle`, printed pp. 243-244); `TRMD` is firmware-verified, `ARM` appears nowhere in the manual and was rejected on the target.
- **Configure only what can be read back:** `:TRIGger:TYPE`, `:TRIGger:EDGE:SOURce`, `:TRIGger:EDGE:SLOPe`, `:TRIGger:EDGE:LEVel`. Never use `TRSE EDGE,SR,C1,HT,OFF` / `C1:TRSL POS` / `C1:TRLV 2.5`: `HT` is defined nowhere and no per-channel slope or level command exists, so that block asserts a trigger direction it can never prove.
- **A capture is the observed transition `Ready -> Stop`** from `SAST?`. A `Stop` without a prior `Ready` is not proof of a new capture.
- **Roll is not a capture path.** `:ACQuire:MODE ROLL` never reports `Ready`; leave it with `:ACQuire:MODE YT` before arming and never treat `Roll` as `Ready` or as a `Stop` precursor.
- **After `Stop` the frame is frozen:** no `STOP`, `ARM`, `RUN`, `TRMD`, trigger/timebase/channel configuration, `WFSU`, or TCP reconnect while reading it, and in an immutable read every `C<n>:WF? DAT2` precedes any `WF? DESC`.
- **One command per `write()`.** `\n`-separated batches and `;` compounds lose the tail (line-2 `TRSE` is reproducibly `-113,"Undefined header"`); `scripts/scope_protocol.py` already sends one command per `sendall`.
- **Every write is read back and `SYSTem:ERRor?` is drained to `0,"No error"`.** Silence is the normal outcome of a rejected *or inapplicable* write: acquisition-context writes are discarded while `SAST?` is `Stop`, and `TIM:SCAL` is clamped by `TDIV_max = ACQ:POIN? / (SARA * 10)`, neither with any error. A read-back holding the old value is a failure to diagnose, never a reason to retry another spelling, reset the scope, or reconnect.
- **Never invent a query spelling.** An undefined-header *query* returns no bytes yet still queues `-113`, so every later `readline()` is short by one reply; that cascade is off-by-one response skew, not a dead instrument — re-read `*IDN?`, or open a new session to recover.
- **Raw payloads and metadata come before any CSV.** `max_points` is a local CSV/downsampling setting, never evidence of instrument record length; a short payload is `INCOMPLETE` or `INVALID`, never complete. Signal presence is a per-channel read, never a screenshot inference.

## Session Baseline

- Connect once to SCPI TCP `5025`; port `5024` is a legacy shell which may answer `Welcome to the SCPI instrument 'Siglent SDS824X HD'` and `>>` — never parse either as a query result. Send `*IDN?` and keep the identity before model-specific commands.
- Verified target: `Siglent SDS824X HD`, IP `192.168.10.2`, firmware `4.8.12.1.1.6.5`. Channels on that bench: `C1=ENABLE`, `C2=nFAULT`, `C3=HOC`, `C4=P4.1/CMP` — a bench note, not a default. The scope exposes no channel-name readback, so names exist only through `capture_scope.py --channel-mapping`.
- Typical verified setup and record: `500 ms/div`, `5.00 MSa/s`, `25.0 Mpts`, delay about `-2 s`, giving `25,000,000` points at `200 ns` per point (`5 s`).
- Apply the acquisition context in the order `:ACQuire:MMANagement` -> `:ACQuire:MDEPth` -> `:ACQuire:SRATe` -> `:TIMebase:SCALe` -> `:TIMebase:DELay`; the reverse order cannot reach a long timebase because `TDIV_max = ACQ:POIN? / (SARA * 10)`. Sample rate is directly settable only in `FSRate` mode.
- Keep one socket session for the whole capture, and treat an export as unverified unless raw payload length and descriptor point count agree.

## Progressive Query Reference

Load only the reference matching the current goal, and do not read every command file up front.

| Goal or observation | Read this reference |
|---|---|
| One-command channel check, find a signal, auto-range, apparent 0 V, or snapshot/`next_actions` field semantics | [Signal discovery and measurement](references/signal-discovery-and-measurement.md) |
| Screenshot, waveform capture workflow (new / left-aligned trigger / existing stopped frame / configured repetitive), binary response rules, the offline analysis gates, WORD/BYTE scaling | [Screenshot and waveform data](references/screenshot-and-waveform.md) |
| WAVEDESC fields, capture-state notes, manual-versus-firmware spellings, record ranges and time coordinates | [Programming notes](references/programming-guide.md) |
| Assemble an evidence package, review a `REFUSED` sparse-event verdict, decide what a capture can prove | [Waveform evidence report](references/waveform-evidence.md) |
| Discover a scope, verify USB/LAN identity, connection setup, storage transfer path, front-panel lock | [Connection and storage](references/connection-and-storage.md) |
| Diagnose UART/I2C/SPI/CAN/LIN or another serial bus | [Protocol decode](references/protocol-decode.md) — read `LIST<n>:RESult?` before any host-side reconstruction |
| Runt pulses, glitches, timing violations, mask failures, replaying a captured fault | [Anomaly search and mask testing](references/anomaly-search-and-mask-testing.md) |
| Long-term frequency/period statistics, cursor deltas, history timestamps | [Counter, cursor, and history](references/counter-cursor-and-history.md) |
| Math traces, FFT, reference traces, save/recall of setups and data | [Math and storage](references/math-and-storage.md) |
| Cross-check a command, answer a question no task reference covers, diagnose a setting that "did not take" | [Command reference (fallback)](references/command-reference.md) |

The fallback index is not a starting point: use it only after the matching task reference and the bundled scripts fail to answer, and anything missing from it must be verified against the programming guide and labelled `documented` before use. Reads are the default and safe at any time; writes change the acquisition context, so they belong before `TRMD SINGLE` and never during a stopped-frame read. **A setting has a write form only when it actually does**: `SARA?` reads the sample rate but `SARA <value>` is rejected `-113`, and the write spellings are `:ACQuire:SRATe` or `ACQ:SRAT`. The most often missed writes are `:ACQuire:MMANagement`/`:ACQuire:SRATe` (a rate applies only in `FSRate` mode), `:TRIGger:TYPE` for non-edge triggering, `:SEARch`/`:MTESt` enable, `:MEASure:SIMPle:ITEM`, and `:FORMat:DATA` (the default precision is only 3 significant digits). When a setting does not take effect the next step is a read, not another write.

## Bundled Scripts and Integrity Statuses

- `scripts/channel_snapshot.py` — the default read-only check above (`channel-snapshot/v1`).
- `scripts/scope_protocol.py` — byte-preserving TCP session, IEEE 488.2 block reader, WAVEDESC parser, segment/frame validators, write-integrity helpers (`write_and_verify`, `drain_error_queue`, acquisition-context planning); it deliberately does not read headerless `:PRINt?`.
- `scripts/screenshot_capture.py` — bounded `:PRINt? PNG` reader (`--host <ip> --out <dir>/shot.png`, `.json` sidecar). Container structure only: no decoder runs, so `image_decode_status` stays `UNVERIFIED` and `frame_association` stays `UNVERIFIED`.
- `scripts/capture_scope.py` — one-session capture CLI: explicit `immutable_capture`/`configured_capture`, staged modern probes, segmented reads, atomic merged output, `<channel>.bundle.json` per `COMPLETE` channel, opt-in `--screenshot` last.
- `scripts/discover_scope.py` — read-only USBTMC/VISA and LAN `*IDN?` discovery. `scripts/read_decode_list.py` — read-only decode-list fetch with idle-drain reader and `SYST:ERR?` diagnosis. `scripts/configure_scope.py` + `scripts/scope_command_catalog.py` — catalog lookup and plan-only/checked configuration.
- `scripts/test_*.py` — offline suites; run `python3 -m unittest discover -s scripts -p 'test_*.py'` after touching transport, capture, snapshot, or screenshot code.
- Handover API names in `scope_protocol.py`: `scope_connect`, `scope_identify`, `scope_snapshot_configuration`, `scope_prepare_capture`, `scope_arm_single`, `scope_wait_ready`, `scope_wait_stop`, `scope_read_immutable_frame`, `scope_read_segment`, `scope_read_descriptor`, `scope_validate_frame`, `scope_restore_run_mode`, `scope_disconnect`; `scope_arm_single` sends only `TRMD SINGLE`.

| Status | Means exactly | Never means |
|---|---|---|
| `COMPLETE` | every structural and count check passes for the stated claim: framing, required fields, point/row counts, terminator | the data is correct, covers what the caller wanted, or is calibrated |
| `INCOMPLETE` | a required byte, terminator, field, point, segment, or status element is missing | — |
| `INVALID` | framing, counts, or type constraints contradict the observed bytes | — |
| `UNVERIFIED` | parsing found no contradiction, but the evidence cannot prove completeness, units, calibration, or acquisition state | — |
| `UNSUPPORTED` | this Skill does not implement that response shape or feature | — |

No single status carries all four claims: **bytes complete**, **scale usable**, **same frame**, and **the number is a physical level**. A reader asks for each separately; `analysis_allowed`/`cannot_claim` is driven by the level claim, not by `COMPLETE`. Derived values that only reproduce the instrument's own reading are `OBSERVED_UNVERIFIED`, never calibrated.