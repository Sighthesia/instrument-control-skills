# Spec Contract: SDS824X HD Scope Control Skill

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `SKILL.md`, `scripts/`, `references/`, `.specs/`

## 1. Core Objective
Create an agent skill and deterministic helper scripts for operating the Siglent SDS824X HD via raw TCP and documented SCPI. Preserve single-shot captures, parse binary responses safely, and refuse to label partial waveform downloads complete.

## 2. Hard Constraints & Negative Rules (Non-negotiables)
- [x] **C-01**: Never send `ARM`; use `TRMD SINGLE` and verify `Ready -> Stop`.
- [x] **C-02**: Immutable frame reading must not implicitly send `STOP`, `TRMD`, `RUN`, `ARM`, `WFSU`, configuration writes, reconnect, cleanup, or restore commands.
- [x] **C-03**: Read all channel `DAT2` payloads before any `DESC` query.
- [x] **C-04**: Keep `immutable_capture` and `configured_capture` explicit; never implicitly apply `WFSU`.
- [x] **C-05**: Do not claim/document modern waveform segmentation support unless command semantics are verified in the supplied programming guide; explicitly mark any unverified device behavior.
- [x] **C-06**: Retain raw binary payloads, response prefixes, command logs, metadata, segment checksums, and validity reports.
- [x] **C-07**: Do not modify or remove the pre-existing untracked `docs/` manuals.

## 3. Atomized Acceptance Criteria (Checklist)
- [x] **AC-01**: Skill has valid frontmatter and provides operating instructions grounded in the bundled raw TCP scripts and documented SCPI.
- [x] **AC-02**: Helper parser finds IEEE 488.2 blocks amid arbitrary prefixes/NULs and exactly reads declared payload lengths; malformed/truncated blocks fail closed.
- [x] **AC-03**: Capture workflow exposes distinct immutable/configured modes and logs every command; immutable mode cannot issue forbidden state-changing commands.
- [x] **AC-04**: Segmented reads validate exact start/count, cover the descriptor count without gaps/overlaps, report times/checksums, and invalidate the whole channel on any bad segment.
- [x] **AC-05**: Frame validator compares displayed/configured record points and duration, descriptor points/interval/offset/trigger position, and actual downloaded points/duration; partial downloads are `INCOMPLETE`/invalid.
- [x] **AC-06**: Preserve per-channel descriptor and configuration snapshot values (VDIV, OFST, SARA, TDIV, TRDL, WFSU where available) and raw data before any CSV/downsampling output.
- [x] **AC-07**: Automated tests cover binary framing, banner/noise, truncation, segment boundaries, checksum, and incomplete 25M-vs-5M capture rejection without connecting to hardware.
- [x] **AC-08**: Validate skill structure and run the complete local test suite; document any hardware-only verification boundary.
- [x] **AC-09**: Modern WAV segmented capture supports a staged hardware probe and full-range download without `ARM`, `STOP`, `WFSU`, reconnect, or implicit restore after `Ready -> Stop`.
- [x] **AC-10**: The modern path writes one complete merged raw waveform only after all requested segments pass exact range and payload validation; a failed probe or segment leaves the result non-complete.
- [x] **AC-11**: Modern WAV capture selects BYTE/WORD from the actual descriptor, explicitly controls and verifies byte order, and validates payload bytes as `points * bytes_per_point`.
- [x] **AC-12**: WORD mode preserves raw 2-byte samples and reports width, nominal bits, byte order, expected/downloaded bytes, and precision without reclassifying the historical BYTE capture.

## 4. Edge Cases & Boundary Conditions
- TCP startup banner and `>>` prompt; arbitrary ASCII and NUL bytes before binary marker.
- Binary block marker split across reads, multi-digit length-of-length, payload containing `#`, NUL, CR/LF, or arbitrary bytes.
- Short reads, timeout, wrong declared length, empty segment, duplicate/overlapping/gapped ranges, and descriptor/data mismatch.
- Stop frame is volatile; any uncertain or unsupported command must fail closed rather than retry/reconnect or alter instrument state.
- `max_points` controls local derived output only and must never be treated as device record length.

## 5. Execution & Verification Log
- [x] Initial scaffolding
- [x] Implementation
- [x] Automated tests / manual verification
