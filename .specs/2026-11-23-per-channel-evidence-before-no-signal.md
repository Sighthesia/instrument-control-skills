# Spec Contract: Per-Channel Evidence Before Claiming "No Signal"

- **Created**: 2026-11-23
- **Status**: Proposed (skill improvement; not yet implemented)
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

Cost: one full wrong hypothesis (grounding/power) and one wasted rebuild+flash
cycle on the target.

## 3. Hard Constraints & Negative Rules (Non-negotiables)

- [ ] **C-01**: Do not answer "channel X has no signal" from a screenshot, a
      rendered band, or a colour. Answer it only from a value read for channel X.
- [ ] **C-02**: Treat a missing/uncomputable measurement (`***`, empty, timeout)
      as `UNVERIFIED`. Never convert it to `0 V`, "flat", or "no signal".
- [ ] **C-03**: Never generalise the on-screen measurement panel to more than the
      selected channel.
- [ ] **C-04**: A channel reading a true 0 V is a *finding*, not a diagnosis: it
      has at least four causes (undriven pin, missing per-board ground, channel
      off, wrong scale/clipping) and each needs its own check.
- [ ] **C-05**: Keep existing read-only defaults; any snapshot helper stays
      read-only and must not alter acquisition, trigger or channel state.

## 4. Atomized Acceptance Criteria (Checklist)

- [ ] **AC-01**: The Skill states that signal presence is a per-channel read, and
      that a screenshot may only be used for shape/qualitative context.
- [ ] **AC-02**: Guidance defines a minimal per-channel snapshot: `C<n>:TRA?`,
      `C<n>:VDIV?`, `C<n>:OFST?`, plus one amplitude/extrema measurement, and
      requires recording the raw responses.
- [ ] **AC-03**: Guidance requires the acquisition state (`SAST?`) and the
      trigger configuration to be recorded with the snapshot, because an armed
      (`Ready`) capture shows live traces that are not a completed frame.
- [ ] **AC-04**: Guidance defines the triage order for an apparent 0 V: read the
      channel amplitude, read `TRA`/`VDIV`/`OFST`, confirm the probe ground is on
      the *same board's* GND (multi-MCU boards have separate references), and only
      then conclude "undriven".
- [ ] **AC-05**: A read-only helper (for example `channel_snapshot.py`) prints the
      per-channel table and marks anything unreadable as `UNVERIFIED`; no write
      commands, no acquisition change.
- [ ] **AC-06**: Offline tests cover the three failure modes: unreadable
      measurement -> `UNVERIFIED`; channels reported individually; a screenshot
      path that must not be able to produce a "no signal" verdict.
- [ ] **AC-07**: Documentation records this incident as the motivating evidence,
      including that the wrong conclusion directed the operator to check power and
      grounding that were already correct.

## 5. Related

- Firmware-side counterpart (undriven diagnostic pin vs idle state encoded as
  zero duty): ArduPilot repo,
  `.agents/skills/firmware-debug-false-signals/SKILL.md`, commit `464090a7bc`.
