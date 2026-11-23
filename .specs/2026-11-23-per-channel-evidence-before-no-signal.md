# Spec Contract: Per-Channel Evidence Before Claiming "No Signal"

- **Created**: 2026-11-23
- **Status**: Completed and accepted offline (2026-11-23). Target-firmware replies for `:MEASure:SIMPle:SOURce?` and `:CHANnel<n>:SWITch?` remain `documented` pending a device check.
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/SKILL.md`, `skills/siglent-sds800xhd-control/references/signal-discovery-and-measurement.md`, `skills/siglent-sds800xhd-control/scripts/*` (helper for a per-channel snapshot)

## 1. Core Objective

Stop an agent from concluding that one channel carries no signal by looking at a
screenshot. Presence or absence of a signal must be established per channel from
read values, and an unreadable measurement must be reported as `UNVERIFIED`
rather than as `0`.

## 2. What Went Wrong (observed 2026-11-23, SDS824X HD)

A four-channel capture was taken while the DUT was being debugged. The operator
asked a question about three of the channels. The agent looked at the returned
PNG and the on-screen measurement panel, saw `***` values plus a small peak
figure, and stated that two of the channels had "no level" and that the probe
ground was probably floating.

Both statements were wrong: those two channels were carrying 3.3 V traffic the
whole time. Three separate mistakes combined:

1. **Screenshot instead of query.** No `:MEASure`/amplitude query per channel was
   issued. The on-screen measurement panel belongs to the *selected* channel, so
   it can never describe three channels at once.
2. **`***` read as zero.** A measurement that the instrument cannot compute is
   not a measured zero; it means "no evidence".
3. **Colour/overlap guessing.** Dense 500 kbaud traffic at 200 us/div becomes a
   solid band; which band belongs to which channel, and whether a channel is
   even drawn, cannot be resolved reliably from the rendered image.

The conclusion sent the operator to recheck power and grounding, which were
already correct, and cost one rebuild and flash cycle.

## 3. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Do not answer "channel X has no signal" from a screenshot, a
      rendered band, or a colour. Answer it only from a value read for channel X.
- [x] **C-02**: Treat a missing/uncomputable measurement (`***`, empty, timeout)
      as `UNVERIFIED`. Never convert it to `0 V`, "flat", or "no signal".
- [x] **C-03**: Never generalise the on-screen measurement panel to more than the
      selected channel.
- [x] **C-04**: A channel reading a true 0 V is a *finding*, not a diagnosis: it
      has at least four causes (undriven pin, missing per-board ground, channel
      off, wrong scale/clipping) and each needs its own check.
- [x] **C-05**: Keep existing read-only defaults; any snapshot helper stays
      read-only and must not alter acquisition, trigger or channel state.

## 4. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: The Skill states that signal presence is a per-channel read, and
      that a screenshot may only be used for shape/qualitative context.
- [x] **AC-02**: Guidance defines a minimal per-channel snapshot: `C<n>:TRA?`,
      `C<n>:VDIV?`, `C<n>:OFST?`, plus one amplitude/extrema measurement, and
      requires recording the raw responses. *(The `TRA?` spelling is superseded
      in the implementation by the documented `:CHANnel<n>:SWITch?`; see §5.)*
- [x] **AC-03**: Guidance requires the acquisition state (`SAST?`) and the
      trigger configuration to be recorded with the snapshot, because an armed
      (`Ready`) capture shows live traces that are not a completed frame.
- [x] **AC-04**: Guidance defines the triage order for an apparent 0 V: read the
      channel amplitude, read the channel switch/`VDIV`/`OFST`/coupling, confirm
      the probe ground is on the *same board's* GND (multi-MCU boards have
      separate references), and only after those setup/coupling/ground causes are
      excluded **plus independent electrical evidence** may "undriven" be
      concluded. `PKPK=0` alone is never that evidence, and any offline negative
      must retain its window and detection-capability limits. *(The switch read is
      implemented as `:CHANnel<n>:SWITch?`; see §5.)*
- [x] **AC-05**: A read-only helper (for example `channel_snapshot.py`) prints the
      per-channel table and marks anything unreadable as `UNVERIFIED`; no write
      commands, no acquisition change.
- [x] **AC-06**: Offline tests cover the three failure modes: unreadable
      measurement -> `UNVERIFIED`; channels reported individually; a screenshot
      path that must not be able to produce a "no signal" verdict.
- [x] **AC-07**: Documentation records this incident as the motivating evidence,
      including that the wrong conclusion directed the operator to check power and
      grounding that were already correct.

## 5. Implementation Record (2026-11-23)

Status: implemented and offline-verified. No instrument was connected; every
firmware-behaviour statement below is `documented` unless a prior verified note
says otherwise.

- **Official channel-state query replaces `C<n>:TRA?`.** AC-02's original
  `C<n>:TRA?` spelling is not a documented query; on the verified firmware a
  mid-session `C1:TRA?` timed out (`.specs/2026-11-04-verdict-gate-design.md`
  E12). The snapshot therefore uses `:CHANnel<n>:SWITch?`, documented in the
  programming guide (PDF p. 57 / printed p. 29; the PDF page is offset +28 from
  the printed page). `VDIV?` and `OFST?` remain the panel scale/offset reads,
  and `:CHANnel<n>:COUPling?` is added because `GND` coupling produces a flat
  trace that is not a zero-volt signal.
- **Measurement source.** `:MEASure:SIMPle:SOURce?` is documented at PDF p. 210
  / printed p. 182; `:MEASure:SOURce?`, which failed earlier, is not an
  implemented header. The helper reads the documented query before and after
  the metric reads and records a value only for the channel both replies name.
  Because changing the source is a write and no source was changed, the
  target firmware's reply shape for this query stays `documented` and was not
  hardware-verified in this change. `Cn:PAVA?` was not used or guessed.
- **Readable/unreadable values.** `***`, `****`, empty, non-scalar, non-finite
  (`1E999`), foreign/error echo headers, error text, an unattributable value,
  and a timeout are all `UNVERIFIED`. A bare NR3 is bound to `V` only from a
  reply suffix or a `:CHANnel<n>:UNIT?` readback of `V`; an `A` readback stays
  `A`, and an unreadable unit leaves only the raw reply with no exported numeric
  value. A negative `PKPK` is rejected as contradicting the magnitude
  definition. `PKPK = 0` is recorded as an observed zero with the explicit
  meaning "no variation in the current measurement window", never as an
  absolute 0 V or an undriven channel. The first transport failure stops every
  later query, preserves the rows already read, and does not reconnect.
- **Helper.** `scripts/channel_snapshot.py` (schema
  `channel-snapshot/v1`) prints a per-channel table and/or JSON with, per row,
  the query, raw reply, parsed value/unit, source, status, and reason. It sends
  only queries and never arms, stops, changes source, enables an item, changes
  format, or drains the error queue. Channel count comes only from evidence:
  `SDS824X HD` is established as 4-channel, the other documented series models
  are treated as the 2-channel minimum, `--model-channels 2|4` records a
  caller-confirmed count, and an unidentified model is refused before any
  channel query. The capability tables in `README.md` and `README.zh-CN.md`
  were updated from 7 to 8 scripts, and `manifest.json` now separates the
  hardware-verified `:MEASure:SIMPle:VALue?` value path from the
  `documented` source readback and snapshot queries.
- **Capture contract.** `capture_scope.py` now saves every requested waveform
  payload and descriptor before reading instrument measurements. The
  single-channel default attribution was removed: a measurement is bound only
  to the channel named by the before/after `:MEASure:SIMPle:SOURce?` readbacks,
  and every other requested channel keeps `UNVERIFIED` rows. A measurement
  transport failure keeps the verified frame, records
  `instrument_measurements_error`, and records a requested `--screenshot` as
  `NOT_ATTEMPTED` rather than sending another query. Existing manifests and
  bundles remain loadable; the bundle still records the single flat
  measurement shape.
- **Screenshots.** `references/screenshot-and-waveform.md` now states that a
  screenshot is qualitative context only and points to the per-channel
  snapshot. No code path turns a PNG, its container status, or its on-screen
  panel into a presence/absence verdict.
- **Strict reply validation.** `parse_scalar_reply` accepts only a bare finite
  NR3 or a scalar after the expected query header (the sent header or a
  documented short/long alias). It rejects non-finite values such as `1E999`,
  `ERROR 0`, another channel's header, and multi-token error text. The source
  readback accepts a bare `C1` or the documented source-query header plus `C1`,
  and rejects `ERROR C1`. `PKPK` must be non-negative; a negative reply is
  recorded raw-only and `UNVERIFIED`.
- **Unit-gated value export.** `_bind_units`/`_sanitize_block` keep a numeric
  metric only when the source is matched and the unit is proven `V` or `A`.
  Ampere values stay for the analyzer to reject as volts; an unknown unit leaves
  only the raw reply. The snapshot's top-level measurement block and the
  capture manifest/bundle therefore cannot expose an unconsumable bare number to
  the voltage cross-check. A row whose metrics are all unreadable is
  `query_status = COMPLETE` but `status = UNVERIFIED`; the snapshot's `status`
  describes the query flow and `evidence_status` describes usable channel
  evidence, so `COMPLETE` no longer implies every channel has a reading.
- **Trigger context validation.** `TRMD?`, `:TRIGger:TYPE?`, and the EDGE
  source/slope/level replies are parsed against documented values and expected
  headers. Placeholder or error text is `UNVERIFIED`; when the type is
  unreadable, no EDGE field is queried and all three are `UNVERIFIED` rather
  than `NOT_APPLICABLE`.
- **CLI guards.** The snapshot CLI requires an explicit `--host`, rejects the
  legacy shell port `5024` locally, and rejects a zero, negative, non-finite, or
  otherwise non-positive timeout before connecting.
- **Triage evidence.** The zero triage is produced only from a usable zero
  `PKPK`; an unread amplitude does not trigger it. Confirming the channel state,
  coupling, and same-board probe ground still does not prove an undriven pin:
  independent electrical evidence is required, and a negative conclusion from
  stored samples must state the original offline window and
  `NOT_OBSERVED_WITHIN_DETECTION_CAPABILITY` with its resolution and minimum
  detectable pulse.
- **Offline evidence.** `scripts/test_channel_snapshot.py` (27 tests) covers
  multi-channel requests where only the matching source has values, a source
  that changes between readbacks, `***`/`****`/empty/error text/non-finite
  overflow (`1E999`)/foreign echo headers, true zero vs unreadable, a negative
  `PKPK`, `Ready` vs `Stop`, unreadable trigger placeholder fields and the
  no-EDGE-probe rule when the type is unreadable, only-query command logs,
  model channel-count conservatism, unknown-unit raw-only evidence, the
  query-flow/evidence-status distinction, and the screenshot path being unable
  to produce a negative. `scripts/test_capture_scope.py` (8 tests) covers
  waveform/descriptor ordering, a single-channel download whose measurement
  source is another channel, `***`/empty/overflow/error text in the manifest,
  unknown unit not exported as a level, a healthy screenshot as the last step,
  and a measurement timeout that keeps the payload, skips the screenshot, and
  sends no later query. Acceptance runs passed 189 Siglent tests and 241
  offline waveform-analysis tests. The Skill validator passed, CLI discovery
  matched all nine Skill directories, and `git diff --check` passed.
- **Not verified here (hardware).** The target firmware's `:MEASure:SIMPle:SOURce?`
  reply shape, the `:CHANnel<n>:SWITch?` reply on the target, the `Ready`
  meaning actually reported during a live acquisition, and the 2-channel
  inference for models other than `SDS824X HD`. All remain `documented` until a
  real readback is captured.

## 6. Related

- Firmware-side counterpart (undriven diagnostic pin vs idle state encoded as
  zero duty): ArduPilot repo,
  `.agents/skills/firmware-debug-false-signals/SKILL.md`, commit `464090a7bc`.
