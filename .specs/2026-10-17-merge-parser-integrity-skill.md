# Spec Contract: Merge Parser and Integrity Guidance Skill

- **Created**: 2026-10-17 22:00
- **Status**: Completed
- **Target Files/Modules**: `skills/write-new-instrument-control/`, `dist/write-new-instrument-control.skill`, `registry.yaml`, `README.md`, `README.zh-CN.md`, `CONTRIBUTING.md`

## 1. Core Objective

Rename `instrument-parser-authoring` to the clearer `write-new-instrument-control` and merge all `measurement-data-integrity` guidance and assets into that single authoring Skill.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Keep the merged Skill vendor-neutral and independent of any runtime adapter framework.
- [x] **C-02**: Do not modify the existing Siglent control implementation or its Skill name.
- [x] **C-03**: Remove the standalone `measurement-data-integrity` Skill and package after its content is merged.
- [x] **C-04**: Preserve the one-line `npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill` command in both READMEs.
- [x] **C-05**: Do not stage existing `artifacts/` or `__pycache__/` files.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: Source directory and frontmatter name are `write-new-instrument-control`.
- [x] **AC-02**: Merged Skill includes parser authoring workflow, framing, metadata/payload, replay testing, integrity status, provenance, waveform/scalar/axis checks, and report template.
- [x] **AC-03**: Existing parser template and its six tests remain functional.
- [x] **AC-04**: Registry contains exactly two active Skills: Siglent control and `write-new-instrument-control`.
- [x] **AC-05**: README, Chinese README, and CONTRIBUTING references use the new name and explain the merged scope.
- [x] **AC-06**: `dist/write-new-instrument-control.skill` is created; `dist/instrument-parser-authoring.skill` and `dist/measurement-data-integrity.skill` are removed.
- [x] **AC-07**: Three stale Skill discovery results become two; all validators, tests, package checks, and CLI discovery pass.
- [x] **AC-08**: Changes are committed with an English Conventional Commit message.

## 4. Edge Cases & Boundary Conditions

- Historical `.specs` files may retain old names as historical context, but active README/registry/contribution paths must be current.
- References inside the merged Skill must remain one-level relative to its new root.
- The merged Skill must not imply that it connects to instruments; it guides creation of control Skills and their parsing/integrity workflows.
- Package output must preserve the new Skill root name.

## 5. Execution & Verification Log

- [x] Source rename and content merge
- [x] Registry/documentation updates
- [x] Package cleanup and rebuild
- [x] Validation, tests, and discovery check
- [x] Acceptance audit and commit
