# Evidence and Provenance

## Preserve the chain

Record enough information to connect an analysis result back to the instrument
response:

- vendor, model, serial, and firmware when available
- transport kind and a non-secret endpoint identifier
- command or acquisition operation
- capture timestamp and timezone/clock basis
- raw response path and SHA-256
- normalized artifact path and SHA-256
- decoder/parser name and version
- manual title, revision, URL, and page/section
- calibration source, hash, and evidence
- known redactions and limitations

Do not place credentials in manifests or fixtures. Redact private network details
that are not needed for reproducible parsing.

## Evidence levels

- `documented`: claim follows an official manual but has no hardware evidence.
- `hardware-verified`: a real instrument response was checked.
- `firmware-scoped`: the real check records exact model, firmware, interface, and
  date.

Use the lowest level that supports the particular claim. A parser can be
`documented` while a voltage calibration remains `UNVERIFIED`.

## Label one claim at a time

| Claim | Label | Required record |
|---|---|---|
| Manual paragraph or table only | `documented` | title, revision, URL, physical page |
| Implemented but never sent or observed | `documented` | the above, plus the code path |
| One real response captured and checked | `hardware-verified` | model, firmware, interface, date, raw bytes and SHA-256 |
| Reproduced on the same model and firmware, scope stated | `firmware-scoped` | the above, plus the exact firmware and interface |
| Contradicts the manual | both: the manual claim stays `documented`, the observation is `hardware-verified` | page and capture, side by side |
| Inferred from naming or a sibling command | no level; mark inferred or `UNSUPPORTED` | what the inference rests on |
| Deliberately not implemented | `not implemented` | page and reason |

- A label attaches to a claim, not to a file. A `documented` Skill can hold one
  `hardware-verified` identity query; a `firmware-scoped` Skill can hold
  `UNVERIFIED` calibration.
- Name the unit of the claim ("every row in the curated table", "the NORM block
  parser"), not "the Skill is verified".
- A newer manual revision does not upgrade an observation, and a similar model
  does not inherit another model's evidence.
- The manifest firmware field is evidence only when an identity response was
  captured; otherwise it is `null`.
- When a row, a reference sentence, and the manifest disagree, the lowest label
  wins until the evidence is re-read.

## Calibration binding

External calibration must identify the exact raw or merged artifact by SHA-256 and
state how the reference was measured. Never apply a calibration file merely because
its instrument model matches.
