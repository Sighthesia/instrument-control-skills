# Spec Contract: Multi-Skill Repository Skeleton

- **Created**: 2026-10-17 21:10
- **Status**: Completed
- **Target Files/Modules**: `skills/`, `registry.yaml`, `CONTRIBUTING.md`, `README.md`, `README.zh-CN.md`, existing path references, `dist/`

## 1. Core Objective

Convert the repository into a multi-Skill community skeleton while preserving the existing Siglent skill behavior and the independent instrument parser authoring skill.

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: Do not introduce a shared adapter inheritance framework or change instrument runtime behavior.
- [x] **C-02**: Keep each Skill self-contained and discoverable under `skills/<skill-name>/SKILL.md`.
- [x] **C-03**: Preserve the exact one-line `npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill` installation command in both READMEs.
- [x] **C-04**: Do not stage or commit existing untracked `artifacts/` or any `__pycache__/` files.
- [x] **C-05**: Rebuild both committed `.skill` archives from their new source paths.

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: Existing Siglent source is located at `skills/siglent-sds800xhd-control/` with its Skill name unchanged.
- [x] **AC-02**: Existing parser authoring Skill remains at `skills/instrument-parser-authoring/` and remains discoverable.
- [x] **AC-03**: `registry.yaml` lists both active Skills, their categories, paths, supported data/operation scope, and evidence/support status.
- [x] **AC-04**: `CONTRIBUTING.md` defines the contribution boundary, Skill layout, support levels, replay-test expectations, and manual copyright rule.
- [x] **AC-05**: English and Chinese READMEs describe the multi-Skill repository and contain correct new paths and development commands.
- [x] **AC-06**: All tracked path references to the old root-level Siglent directory are updated, while internal Skill-relative paths remain valid.
- [x] **AC-07**: Both `dist/siglent-sds800xhd-control.skill` and `dist/instrument-parser-authoring.skill` are rebuilt and pass archive checks.
- [x] **AC-08**: Existing 44 Siglent tests, parser-template tests, validators, and `npx skills@latest add . --list` pass.
- [x] **AC-09**: Changes are committed with an English Conventional Commit message and unrelated untracked files remain uncommitted.

## 4. Edge Cases & Boundary Conditions

- The package output must retain each Skill's own root name even though its source is under `skills/`.
- README commands must work from the repository root after relocation.
- Historical specs may contain old source paths; update them so future maintenance commands do not point to nonexistent files.
- Registry entries must not claim Keithley or other future instruments before an actual Skill exists.

## 5. Execution & Verification Log

- [x] Initial skeleton and source relocation
- [x] Registry and contribution guide
- [x] README and path-reference updates
- [x] Repackage and test
- [x] Acceptance audit and commit
