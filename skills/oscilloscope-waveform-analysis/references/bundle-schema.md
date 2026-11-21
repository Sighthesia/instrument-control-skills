# `waveform-bundle/v1` — the interchange contract

Load this reference before writing a bundle from a device-control Skill, before
verifying one by hand, or when the loader refuses a document and the reason code
is not obvious. A bundle is the only input format that is self-describing: it
carries its own byte range, dtype, time axis, vertical scale and the claim limit
of that scale. CSV, NPZ and legacy Siglent captures are normalized into the same
internal shape by separate adapters.

A bundle is one UTF-8 JSON document plus the binary payload it names:

```text
/path/to/capture/
├── waveform-norm-ch1.bundle.json   # the document
└── waveform-norm-ch1.bin           # the payload, referenced by data.file
```

`data.file` is resolved relative to the bundle's own directory first and falls
back to the bare file name in that same directory, so a capture directory can be
copied without rewriting paths. An absolute path is honoured as given.

## Required sections

`load_capture` refuses a document that is not a JSON object, or whose `schema`
is present and is not exactly `waveform-bundle/v1` (`SCHEMA_UNSUPPORTED`).
All five of these sections must be objects (`BUNDLE_INVALID` otherwise):

```text
source, data, time_axis, vertical, integrity
```

```json
{
  "schema": "waveform-bundle/v1",
  "source": {
    "vendor": "rigol",
    "model": "DS1074Z",
    "idn": "RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4",
    "channel": "CH1",
    "captured_at": "2026-11-20T00:00:00Z"
  },
  "data": {
    "file": "waveform-norm-ch1.bin",
    "sha256": "<64-hex SHA-256 of the sample slice>",
    "file_sha256": "<64-hex SHA-256 of the whole referenced file>",
    "dtype": "u1",
    "points": 1200,
    "byte_offset": 0,
    "byte_length": 1200,
    "width_bytes": 1
  },
  "time_axis": {
    "sample_interval_s": 2.0e-6,
    "time_origin_s": -1.2e-3,
    "timebase_s": null,
    "horizontal_offset_s": null,
    "reference": "descriptor",
    "origin_formula": "time_origin_s + sample_index * sample_interval_s"
  },
  "vertical": {
    "units": "V",
    "scale_usable": true,
    "zero_code": 51.0,
    "code_scale_v": 0.02,
    "offset_v": 0.0,
    "vdiv_v_per_div": null,
    "adc_min_code": 0,
    "adc_max_code": 255,
    "full_scale_code": null,
    "calibration_status": "VERIFIED",
    "calibration_source": "rigol_preamble",
    "scale_reasons": []
  },
  "integrity": {
    "status": "COMPLETE",
    "bytes_complete": true,
    "checks": ["declared_points:pass"],
    "status_meaning": "payload framing/count integrity only"
  },
  "provenance": {
    "raw_file": null,
    "raw_sha256": null,
    "new_transition_proven": null,
    "screen_range": null,
    "screenshot": null
  },
  "instrument_measurements": null
}
```

## `source`

`source.channel` is the channel the payload belongs to (`CH1`, `C1`, or a bare
label). At most one payload per document, so a multi-channel capture is written
as one bundle per channel. Passing `--channel` for a different channel is
refused with `CHANNEL_MISSING`; omitting it selects the recorded channel. The
rest of the block is descriptive: `vendor`, `model`, `idn` and `captured_at` are
recorded evidence and are never parsed to derive a scale.

## `data` — byte range and identity

| Field | Rule |
|---|---|
| `file` | required, non-empty; resolved relative to the bundle directory, then by bare name |
| `dtype` | required; any NumPy integer, unsigned or floating dtype with an item size of 1, 2, 4 or 8 bytes (`i`, `u`, `f`). Anything else is `DTYPE_UNSUPPORTED` |
| `points` | required, positive integer; must equal the decoded sample count |
| `byte_offset` | optional, defaults to `0`, must not be negative |
| `byte_length` | optional, defaults to `points * itemsize`; must equal it exactly |
| `width_bytes` | optional; when present it must equal `itemsize(dtype)` |
| `sha256` | required; SHA-256 of the sample slice `[byte_offset, byte_offset + byte_length)` |
| `file_sha256` | optional; SHA-256 of the entire referenced file |

The admission order is fixed so a refusal names the real defect rather than a
downstream symptom:

1. `data.points * itemsize == data.byte_length` (`BUNDLE_INVALID`).
2. `data.byte_offset + data.byte_length` must fit inside the actual file size
   (`BUNDLE_INVALID`) — a truncated file is a length problem, not a hash problem.
3. `data.file_sha256`, when present, must match the whole file (`HASH_MISMATCH`).
4. `data.sha256` must match the slice (`HASH_MISMATCH`).
5. The decoded buffer must hold exactly `data.points` samples (`BUNDLE_INVALID`).
6. `integrity.status` must be `COMPLETE` (`CAPTURE_NOT_COMPLETE`).

Every failure is an `AnalysisError` with a named code; no partial capture is ever
returned, and no byte is repaired, padded or truncated.

## `time_axis`

```text
time(index) = time_origin_s + index * sample_interval_s
```

- `sample_interval_s` must be finite and `> 0` when present
  (`TIME_AXIS_INVALID`). It may be omitted only when the command line supplies
  `--sample-interval-s` or `--sample-rate-hz`; with neither, the load is
  refused. A declared interval that disagrees with the flag by more than `1e-6`
  relative is refused rather than overridden.
- `time_origin_s` defaults to `0.0`.
- `timebase_s` and `horizontal_offset_s` are recorded display configuration; a
  vendor that cannot read them writes `null` rather than a guess.
- `reference` states where the origin comes from (`trigger`, `descriptor`,
  `unverified`). It is descriptive: the loader always reports
  `time_correspondence.status = UNVERIFIED`, because descriptor-relative time is
  analyzable while trigger-aligned and wall-clock time are not.
- `origin_formula` records the vendor's formula in words. Nothing recomputes the
  origin from it.

The loader reports the resulting coordinate as sample index plus relative
display time; it never invents an absolute time.

## `vertical` — one formula, two separate claims

```text
voltage(sample) = (sample - zero_code) * code_scale_v + offset_v
```

`offset_v` is added **after** scaling. A vendor whose own conversion subtracts a
panel offset must therefore store its negation (the Siglent adapter does exactly
that), and a vendor whose zero point is a code midpoint stores it in `zero_code`
(the Rigol `yorigin + yreference`). For a floating-point dtype the identity
scale (`code_scale_v = 1.0`, `zero_code = 0.0`, `offset_v = 0.0`) means the
samples are already in physical units.

| Field | Rule |
|---|---|
| `units` | `V` or `code`. Defaults to `V` when omitted, so a code-domain bundle must say `code` |
| `scale_usable` | boolean, defaults to `true`. `false` forces the analysis into the code domain and appends `bundle_declares_scale_unusable` |
| `code_scale_v` | required and `> 0` when the resolved units are volts, except for a floating-point dtype where it defaults to `1.0` |
| `zero_code`, `offset_v` | finite numbers; default to `0.0` |
| `vdiv_v_per_div` | optional positive number, recorded display state; not used by the vertical formula |
| `adc_min_code`, `adc_max_code` | optional finite code bounds of the transporting ADC; these, not a nominal grid, define the clip rails |
| `full_scale_code` | optional nominal display rail, used only as a recorded reference |
| `calibration_status` | required; `VERIFIED`, `UNVERIFIED` or `CODE_ONLY` |
| `calibration_source` | free-form provenance of the scale (`rigol_preamble`, `gds1000b_header`, `siglent_descriptor`, `explicit_cli`, `external_file`, `none`) |
| `scale_reasons` | the exporter's own reasons, preserved verbatim beside the loader's findings |

`calibration_status` maps into this Skill's vocabulary as follows, and the map
is one-way — an exporter never writes the internal words:

| Recorded | Internal `calibration.status` | Meaning |
|---|---|---|
| `VERIFIED` | `VALID` | the exporter's own conversion is reproduced by the vertical block |
| `UNVERIFIED` | `OBSERVED_UNVERIFIED` | a scale exists but was never confirmed against a reference |
| `CODE_ONLY` | `CODE_ONLY` | no voltage scale is claimed |

A `CODE_ONLY` document whose `units` still says `V` is forced to `code` with
`bundle_records_code_only_calibration`, because a code-domain record cannot
produce volts from a label.

The loader then attaches the three separate claims described in
[Integrity and evidence](integrity-and-evidence.md). At load time
`bytes_complete` and `scale_usable` are decided from the record itself, while
`level_confirmed` needs a reconstructed amplitude: a fresh load reports
`UNKNOWN` with `level_reason` `instrument_measurement_absent` (no reading) or
`no_reconstructed_amplitude` (a reading exists but nothing has been measured
from the samples yet). The analysis subcommands re-attach the level claim with
the amplitude they actually computed.

## `integrity`

`integrity.status` must be `COMPLETE` for the payload to be read at all. The
`status_meaning` string is preserved so a reader can see what the exporter
thought it was asserting, and the recorded `checks` list is kept beside the
loader's own checks (`bundle_schema_waveform_bundle_v1`,
`payload_slice_sha256`, `byte_range_within_file`, `integer_point_width_agreement`,
`payload_file_sha256` when applied, `integrity_reports_complete`). Exporters must
not downgrade this field to force a load through: `COMPLETE` describes framing
and counts only.

## `provenance` and `instrument_measurements`

`provenance` is optional and normalization-only: `raw_file`, `raw_sha256`,
`new_transition_proven`, `screen_range` and `screenshot` are carried into the
capture unchanged. The evidence report reads them; no axis is upgraded by them,
because none of them carries a shared frame identifier.

`instrument_measurements` is optional. Two spellings are accepted:

```json
{ "metric": "PKPK", "value": 3.04, "unit": "V", "source_query": ":MEASure:VPP?" }
```

```json
{ "CH1": { "pkpk": { "value": 3.04, "unit": "V", "raw": "3.04E+00" } } }
```

The flat spelling is normalized to the channel recorded in `source.channel` with
a lower-cased metric. The consumed metric vocabulary is `pkpk`, `top` and
`base`; a measurement under any other metric name is preserved in the document
but leaves `level_confirmed` at `UNKNOWN`. `source_query` is the exact query
that produced the reading and must be kept when one exists — it is what makes
the number attributable rather than invented. An empty or absent block produces
`UNKNOWN`, never a pass.

## Vendor adapter mappings

Each device-control Skill writes the vertical block that reproduces its own
conversion, so the offline formula never needs a vendor branch:

| Vendor | dtype | `zero_code` | `code_scale_v` | `offset_v` | `adc_min_code` / `adc_max_code` | `calibration_status` |
|---|---|---|---|---|---|---|
| Rigol DS1000Z (`:WAVeform:PREamble?` + `:WAVeform:DATA?`, BYTE) | `u1` | `yorigin + yreference` | `yincrement` | `0.0` | `0` / `255` | `VERIFIED`, source `rigol_preamble` |
| GW Instek GDS-1000B (`:ACQ<X>:MEM?` header + big-endian int16) | `>i2` | `0.0` | `vertical_scale / 25.0` | `0.0` | `-32768` / `32767` | `UNVERIFIED`, source `gds1000b_header` |
| Siglent SDS800X HD (modern BYTE/WORD or legacy DAT2) | `i1` / `<i2` | `0.0` | `effective_vdiv / codes_per_div` | `-(descriptor_offset * probe)` | `-128` / `127` or `-32768` / `32767` | `VERIFIED` only when the descriptor scale and the panel snapshot agree; otherwise `CODE_ONLY` with `scale_reasons` |
| Generic CSV / NPZ | float64 | `0.0` | `1.0` | `0.0` | `null` / `null` | n/a — the adapter sets `VALID` for volts and `CODE_ONLY` for codes |

Notes that keep the table from being read as a calibration claim:

- The Rigol `u1` range is the full unsigned 8-bit grid, so a byte capture cannot
  represent a level outside `[0, 255]` codes; the exporter states that range
  instead of a nominal five-division screen.
- The GDS-1000B formula matches `gds1000b_protocol.sample_value()` exactly, and
  its scale stays `UNVERIFIED` because that Skill never confirmed a voltage
  transfer function on hardware.
- A Siglent WORD (`<i2`) transfer has no externally verified code scale, so its
  bundle is written `CODE_ONLY` with `scale_reasons: ["word_code_scale_unverified"]`.
  A 16-bit transport container is never treated as a 16-bit calibrated ADC.
- A CSV or NPZ file states `units` explicitly, or the loader assumes volts. Its
  `sample_interval_s` comes from the file, from a uniform time column, or from
  `--sample-interval-s` / `--sample-rate-hz`; a disagreement is refused.

## Refusal codes an exporter will see

| Code | Trigger |
|---|---|
| `BUNDLE_INVALID` | missing section, missing or non-finite field, point/length/width disagreement, byte range beyond the file |
| `HASH_MISMATCH` | `data.file_sha256` or `data.sha256` disagrees with the bytes on disk |
| `CAPTURE_NOT_COMPLETE` | `integrity.status` is not `COMPLETE`; the recorded reasons are carried in `reasons` |
| `TIME_AXIS_INVALID` | missing, non-finite or non-positive interval, or a declared interval that contradicts the flag |
| `DTYPE_UNSUPPORTED` | a dtype this Skill cannot read as integer or floating samples |
| `SCHEMA_UNSUPPORTED` | a `schema` other than `waveform-bundle/v1`, or a JSON object that is neither a bundle nor a Siglent manifest |
| `CHANNEL_MISSING` | the requested channel differs from the recorded one |
| `CALIBRATION_INCONSISTENT` | `--vdiv`, `--offset` or `--calibration` was supplied for a self-describing bundle, CSV or NPZ file |
| `UNITS_UNSUPPORTED` | a units label other than volts or code |
| `PATH_UNRESOLVED` | the referenced payload cannot be read |
| `NUMPY_UNAVAILABLE` | NumPy 2.0 or newer is not installed |

## Rules for an exporter

1. Export only a `COMPLETE` record. A partially received, superseded or
   undecodable response must never become a bundle.
2. Hash what is on disk after writing, and record both the slice hash and the
   whole-file hash when they differ.
3. State the code bounds you actually transport. Never substitute a nominal
   five-division screen for `adc_min_code` / `adc_max_code`.
4. Keep `zero_code` and `offset_v` as the two knobs of the one formula; do not
   fold an offset into `zero_code` by dividing it by the scale.
5. Record a measurement only when the instrument returned one, with the query
   that produced it. Never synthesize the value the gate would like to see.
6. Do not write an internal status word (`VALID`, `OBSERVED_UNVERIFIED`) into
   `calibration_status`; the map above is one-way.
