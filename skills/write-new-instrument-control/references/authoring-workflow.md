# Parser Authoring Workflow

## 1. Define the boundary

Write down the operation that produced the response and the artifact that the
parser must create. Keep instrument control outside the parser package. A parser
may consume a saved response and metadata, but it must not open a socket, call
VISA, or issue a configuration command.

Choose a data kind before writing field code:

- `waveform`: ordered samples with timing and encoding metadata
- `scalar-measurement`: one or more values with units and measurement context
- `spectrum`: ordered frequency bins and magnitude/phase metadata
- `status-record`: state, flags, counters, or event records

## 2. Build an evidence table

For each output field record:

| Field | Source | Location | Type | Unit | Validation |
|---|---|---|---|---|---|
| `sample_count` | programming manual | header offset or response field | integer | points | payload length |
| `sample_interval_s` | programming manual | preamble field | float | seconds | positive and finite |
| `value` | captured response | response token | float | instrument unit | parser and range |

Mark each source as `documented`, `observed`, or `inferred`. An observed value
does not prove that the interpretation is documented.

## 3. Implement in stages

Keep the following functions independently testable:

```text
read_frame(raw)              -> frame and framing status
parse_metadata(frame)        -> documented metadata
extract_payload(frame)       -> raw data fields or bytes
normalize(metadata, payload) -> normalized artifact data
validate(artifact)           -> integrity report
```

Do not combine all stages in a single `parse()` function. A caller should be able
to inspect the framing and raw payload when semantic parsing fails.

## 4. Test before hardware

Create a valid fixture from the manual's documented format or a captured response,
then add negative fixtures before adding convenience features. Every parser change
must preserve the raw fixture and expected-result comparison.

## 5. Publish conservatively

Include the parser, tests, fixture provenance, manual citation, manifest, and
`SUPPORT.md`. A parser based only on a manual can be useful, but label it
`documented` until hardware evidence exists.
