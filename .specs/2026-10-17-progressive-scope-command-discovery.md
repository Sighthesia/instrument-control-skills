# Spec Contract: Progressive Scope Command Discovery

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `skills/siglent-sds800xhd-control/SKILL.md`, `skills/siglent-sds800xhd-control/references/`, `dist/siglent-sds800xhd-control.skill`

## 1. Core Objective
Enable an AI agent to discover relevant SDS800X HD SCPI commands progressively by debugging task, while keeping unrelated commands out of the active context and distinguishing read-only queries from state-changing setup.

## 2. Hard Constraints & Negative Rules (Non-negotiables)
- [x] **C-01**: Preserve existing capture safety rules, including never sending `ARM` and immutable stopped-frame protections.
- [x] **C-02**: Keep the main skill as a concise task router; place detailed command syntax in task-specific references.
- [x] **C-03**: Mark each command family's prerequisites, state-changing risk, response shape, and hardware-verification status.
- [x] **C-04**: Preserve full query arguments and responses over raw TCP; distinguish commands supported by the bundled scripts from documented commands sent directly.
- [x] **C-05**: Include all user-requested query families without exposing unrelated configuration commands in every workflow.
- [x] **C-06**: Update the distributed `.skill` archive so its contents match the source skill and references.
- [x] **C-07**: Preserve unrelated untracked artifacts and manuals.

## 3. Atomized Acceptance Criteria (Checklist)
- [x] **AC-01**: Main skill has a workflow-to-reference routing table and a query-first, minimum-relevant-context policy.
- [x] **AC-02**: Signal discovery and measurement reference covers identity, acquisition/trigger state, channel setup readback, autoset/auto-find, simple/advanced measurements, statistics, history, and limitations.
- [x] **AC-03**: Screenshot and waveform reference covers binary screenshot and modern/legacy waveform paths, response framing, and integrity limits.
- [x] **AC-04**: Protocol reference covers decode list versus bus summary, supported documented protocol names, and optional/unverified boundaries.
- [x] **AC-05**: Anomaly reference covers search, mask testing, history, event count/selection semantics, and setup prerequisites.
- [x] **AC-06**: Precision reference covers counter and cursor queries, modes, response formats, and inactive-feature timeout behavior.
- [x] **AC-07**: References map to the supplied programming guide pages and distinguish target hardware-tested behavior from manual-only support.
- [x] **AC-08**: Distributed skill archive contains all changed/new source files and passes archive integrity checks.
- [x] **AC-09**: Existing offline tests and skill structure checks pass.

## 4. Edge Cases & Boundary Conditions
- Parameterized queries such as `...:STATistics? ALL` and `...:SHIStory? 5` must preserve the arguments after `?` when sent through raw TCP.
- `TRIG:FREQ?` may return zero when no valid hardware frequency measurement is available; this is not proof of no signal.
- `ACQ:NUMACq?` counts acquired frames and resets after acquisition-affecting changes; it is not a generic average-completion indicator.
- `MEAS:ADV:P<n>:SHIS?` behavior depends on a finite measurement-history limit; unlimited mode returns current measurement data.
- Decode list results are more complete than the visible bus summary; bus summary may truncate when many events exist.
- History timestamps are time-of-day strings without an absolute date; queries may time out when no valid history frame exists.
- Cursor readouts require an active/configured cursor mode; inactive cursor queries may time out.
- `COUN:CURR?` depends on counter mode and source; statistics are available only for frequency/period modes with statistics enabled.
- Scope-side configuration and feature-enabling commands can change the displayed acquisition and must not be used during immutable stopped-frame reads.

## 5. Execution & Verification Log
- [x] Initial scaffolding
- [x] Implementation
- [x] Automated tests / manual verification: `python3 -m unittest discover -s skills/siglent-sds800xhd-control/scripts -p 'test_*.py'` (18 passed); `unzip -t dist/siglent-sds800xhd-control.skill` passed; target read-only command probe completed on SDS824X HD firmware `4.8.12.1.1.6.5`.
