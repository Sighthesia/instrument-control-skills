# Siglent SDS800X HD SCPI Skill

[English](README.md) · [简体中文](README.zh-CN.md)

An AgentSkill — plus deterministic Python helpers — that drives a Siglent
SDS800X HD series oscilloscope over a single raw SCPI TCP session: single-shot
captures, waveform downloads, measurements, screenshots, protocol decode, anomaly
search, and bounded local waveform analysis.

## Supported oscilloscopes

- SDS800X HD series (one shared platform and command set): **SDS802X HD**,
  **SDS804X HD**, **SDS812X HD**, **SDS814X HD**, **SDS822X HD**, **SDS824X HD** —
  2 or 4 channels, 70/100/200 MHz, 50 or 100 Mpts.
- Every behavior here was hardware-verified on an **SDS824X HD**, firmware
  `4.8.12.1.1.6.5`. Channel-count-, bandwidth-, and depth-dependent features must
  be confirmed on the connected model before being reported as verified.

## Supported operations

- **Discovery and connection** — read-only USB (USBTMC/VISA) and LAN `*IDN?`
  discovery, identity verification, storage/transfer-path selection.
- **Signal discovery and measurement** — find a signal, auto-range, inspect trigger
  and acquisition state, measure voltage/timing/jitter.
- **Screenshot and waveform capture** — single-shot captures, screenshots, segmented
  BYTE/WORD waveform downloads.
- **Protocol decode** — UART/I2C/SPI/CAN/LIN and other supported serial buses.
- **Anomaly search and mask testing** — runts, glitches, timing violations, mask
  failures.
- **Counter, cursor, and history** — frequency/period statistics, cursor deltas,
  history timestamps.
- **Local, read-only waveform analysis** (NumPy) — `inspect`, `summarize`,
  `events`, `window`, `ringing` over a completed capture.

## Install

### With the skills CLI (recommended)

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

### Offline / manual

The committed archive `dist/siglent-sds800xhd-control.skill` is a zip of the skill
folder. Unzip it into an agent's skills directory (for OpenCode, e.g.
`~/.config/opencode/skills/`).

## Workflows

- **Progressive reference loading** — start from the goal table in
  [`siglent-sds800xhd-control/SKILL.md`](siglent-sds800xhd-control/SKILL.md) and
  load only the one `references/` page that matches the current goal, instead of
  every page up front.
- **Single-shot capture** — connect once, snapshot config, start with `TRMD SINGLE`
  (never `ARM`), poll `SAST?` to `Ready`, stimulate the DUT, poll to `Stop`, then
  freeze the command set. Full-length transfer uses the segmented path in
  `capture_scope.py` (`WAV:SOURce` -> width/byte-order -> `WAV:INTerval` ->
  `WAV:STARt`/`WAV:POINt` -> `WAV:DATA?`), and only validates into one merged
  `waveform.bin` after every segment passes.
- **Immutable stopped frame** — read every channel's `WF? DAT2` first, save raw
  payloads, and only afterwards optionally issue `WF? DESC`. No state writes.
- **Configured repetitive capture** — explicitly labeled `configured_capture`; may
  use `WFSU` before a new capture, never after `Stop`. Optional left-aligned trigger
  strategy (`--left-aligned-trigger`) for trigger-following bursts.
- **Analysis pipeline** — capture -> `inspect` -> `summarize` -> `events`
  (optionally time-ranged) -> `ringing` -> `window`. Raw `waveform.bin` stays the
  authoritative evidence; summaries/previews are lossy aids.

## Repository layout

- `siglent-sds800xhd-control/` — the skill source.
  - `SKILL.md` — behavior contract and safety rules.
  - `scripts/` — stdlib Python helpers plus the offline unittest suite.
  - `references/` — progressive-load pages (Chinese); the `SKILL.md` goal table
    selects which one to read.
- `dist/siglent-sds800xhd-control.skill` — committed zip deliverable. Rebuild it
  after any change under the skill folder; it does not track the source by itself.
- `.specs/` — dated per-feature contracts (constraints + acceptance checklist).
- `docs/ref/*.pdf` — vendor manuals (untracked); `references/` cites them by page.
- `docs/superpowers/specs/` — design-intent docs.
- `artifacts/` — raw captures (untracked).

## Development

Tests are fully offline (synthetic fixtures, no scope) and only import correctly
with the working directory set to `scripts/`, because the modules use bare
intra-directory imports:

```bash
cd siglent-sds800xhd-control/scripts && python3 -m unittest discover -s . -p 'test_*.py'
```

- 44 tests, ~0.2 s. Single module/class/test:
  `python3 -m unittest test_waveform_analysis` or
  `python3 -m unittest test_scope_protocol.TestX.test_y`.
- Validate the skill (frontmatter, structure, references):
  `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py siglent-sds800xhd-control`
- Repackage after validation (validates first; auto-excludes `__pycache__`):
  `python3 ~/.agents/skills/skill-creator/scripts/package_skill.py siglent-sds800xhd-control dist`
  then check with `unzip -t dist/siglent-sds800xhd-control.skill`.
- `capture_scope.py` and `discover_scope.py` talk to real hardware (default
  `192.168.10.2:5025`; port `5024` is a legacy shell, never query it).

## Safety invariants

These are load-bearing; the offline tests enforce parts of them.

- Never send `ARM`. Single-shot start is `TRMD SINGLE`, and a valid capture requires
  the observed `Ready -> Stop` transition.
- Immutable stopped-frame reads send no `STOP`/`TRMD`/`RUN`/`ARM`/`WFSU`, config
  writes, or TCP reconnect. Read every channel's `WF? DAT2` before any `WF? DESC`.
- Keep `immutable_capture` vs `configured_capture` explicit; never silently restore
  instrument state.
- IEEE 488.2 binary blocks: find `#`, read the length-of-length digit then the exact
  payload; never split a payload on lines or retry a failed read into a "complete" file.
- BYTE vs WORD provenance is recorded. WORD voltage stays `OBSERVED_UNVERIFIED`
  unless a capture-SHA-bound calibration artifact is supplied.

## Dependencies

- Python 3 + stdlib only for `scope_protocol.py`, `capture_scope.py`,
  `discover_scope.py`.
- `numpy>=2.0,<3.0` (`siglent-sds800xhd-control/requirements-analysis.txt`) only for
  `waveform_analysis.py` / `analyze_waveform.py`.
- `pyvisa` is optional and only used by `discover_scope.py --usb`.
- SciPy is deliberately excluded.
