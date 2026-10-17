# Contributing

This repository is a collection of self-contained Agent Skills for instrument
control, parser authoring, and evidence-aware data workflows. Keep contributions
small, executable offline where possible, and explicit about what has or has not
been tested on hardware.

## Add a Skill

Create one directory under `skills/<skill-name>/` with:

```text
SKILL.md
references/       # progressive-load documentation when needed
scripts/          # deterministic helpers when needed
assets/           # templates or fixtures when needed
```

The directory name must match the `name` in `SKILL.md` frontmatter. Keep the
frontmatter description trigger-oriented and keep the body focused on procedural
guidance. Add the Skill to `registry.yaml` with its category, path, data kinds,
transports, support level, and limitations.

## Control Skills

Keep instrument commands and state rules inside the device Skill. Preserve raw
responses and record identity, interface, firmware, timestamps, and hashes where
available. Do not claim a model or firmware is verified without a real response.

Offline tests must not connect to hardware, scan a network, or enumerate VISA
resources. Use fake or replay transports for command and response tests.

## Parser and Analysis Contributions

Separate framing, metadata, payload extraction, normalization, and validation.
Return distinct outcomes such as `COMPLETE`, `INCOMPLETE`, `INVALID`,
`UNVERIFIED`, and `UNSUPPORTED`. Do not silently pad, truncate, interpolate, or
guess missing calibration.

Parser contributions should include binary-safe fixtures, expected results, and
negative cases for truncation, malformed headers, and declared-length mismatch.
Use `write-new-instrument-control` as the authoring guide and template source.
Its five synthetic examples under `assets/examples/` are the reference patterns
for waveform, scalar, sweep, segmented, and event data; run them with:

```bash
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
```

## Evidence Levels

Use the most conservative label:

- `documented`: based on a cited official manual; no replay or hardware claim.
- `replay-tested`: preserved fixtures and negative cases pass offline.
- `hardware-verified`: exercised against a real instrument response.
- `firmware-scoped`: hardware evidence records exact model, firmware, interface,
  and test date.

These labels describe evidence, not feature count. A broad implementation can
remain `documented` or `replay-tested`.

## Manuals and Copyright

Do not commit complete vendor manuals unless their license explicitly permits it.
Prefer an official URL, manual title and revision, page/section references, and
small factual excerpts needed to explain a parser decision.

## Verification

Before submitting a change:

1. Run the affected offline tests.
2. Run `quick_validate.py` for every changed Skill.
3. Rebuild and test its `.skill` archive.
4. Run `npx skills@latest add . --list` and confirm discovery.
5. Update `registry.yaml`, relevant README language versions, and limitations.

Do not commit `artifacts/` or `__pycache__/`.
