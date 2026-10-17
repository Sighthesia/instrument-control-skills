# Spec Contract: Instrument Parser Authoring Skill

- **Created**: 2026-10-17 19:30
- **Status**: Completed
- **Target Files/Modules**: `skills/instrument-parser-authoring/`, `dist/instrument-parser-authoring.skill`, `README.md`, `README.zh-CN.md`

## 1. Core Objective

Create a standalone AgentSkill that guides contributors through authoring tested instrument-data parsers from programming manuals, raw responses, and replay fixtures without requiring a hardware-specific inheritance framework.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Keep the skill independent of any vendor, model, transport, or instrument family.
- [x] **C-02**: Do not modify the existing Siglent control implementation or its packaged `.skill` archive.
- [x] **C-03**: Separate framing, metadata, payload extraction, normalization, and validation responsibilities.
- [x] **C-04**: Treat incomplete, invalid, unsupported, and unverified evidence as distinct outcomes; never infer completeness from a successful parse alone.
- [x] **C-05**: Include no vendor manuals or copyrighted manual copies; require source links and page/section citations instead.
- [x] **C-06**: Keep bundled templates dependency-free and suitable for offline replay tests.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: A discoverable `instrument-parser-authoring/SKILL.md` exists with valid frontmatter and concise trigger-oriented instructions.
- [x] **AC-02**: The skill documents an end-to-end authoring workflow from input classification through normalized artifact and support-level declaration.
- [x] **AC-03**: References cover response framing, metadata/payload separation, integrity validation, provenance/support levels, and replay testing.
- [x] **AC-04**: Bundled templates include a parser module, offline unittest module, manifest example, and expected-result fixture.
- [x] **AC-05**: The parser template exposes explicit stages for framing, metadata, payload, normalization, and validation, with no hardware connection code.
- [x] **AC-06**: The test template covers at least valid, truncated, malformed, and length-mismatch evidence paths.
- [x] **AC-07**: The manifest example records instrument identity, source evidence, data kind, support level, raw artifact, and integrity status.
- [x] **AC-08**: README files list the new skill and explain its purpose without adding extra installation commands beyond the established one-line command.
- [x] **AC-09**: `quick_validate.py`, the new template tests, package creation, archive integrity, and `npx skills@latest add . --list` all pass.
- [x] **AC-10**: Changes are committed with an English Conventional Commit message; existing untracked artifacts remain uncommitted.

## 4. Edge Cases & Boundary Conditions

- A response can contain a valid payload with an invalid or unknown header.
- Declared length can differ from physical payload length, including both truncation and extra trailing bytes.
- A parser may successfully extract a value while lacking enough evidence to validate units, calibration, or acquisition completeness.
- Some formats have no declared length or checksum; the correct result may be `UNVERIFIED` rather than `COMPLETE`.
- A fixture must preserve binary bytes and must not be represented only as decoded text.
- The parser template must remain useful for scalar text, IEEE 488.2 binary blocks, and custom binary formats without embedding one vendor's assumptions.

## 5. Execution & Verification Log

- [x] Initial scaffolding
- [x] Skill and references implementation
- [x] Parser/test/manifest templates implementation
- [x] README index updates
- [x] Automated validation and package verification
- [x] Commit and final acceptance audit
