# Reference Basis

This document records where the repository's authoring rules and data-analysis
routines come from. It is the detailed companion to the short reference list in
`README.md`.

## Authoring conventions

`skills/write-new-instrument-control/SKILL.md` is the normative contract for a
new device Skill. Its references are loaded per stage:

| Area | Reference | Rules |
|---|---|---|
| Authoring stages | `references/authoring-workflow.md` | Instrument boundary, evidence table, the `read_frame → parse_metadata → extract_payload → normalize → validate` split, test-before-hardware, conservative publication |
| Instrument types | `references/instrument-types-and-examples.md` | Choosing an example by data claim and response format; five teaching formats and their main checks |
| Response framing | `references/response-framing.md` | Line-oriented text, CSV, IEEE 488.2 definite-length blocks, length-prefixed binary, segmented/packetized records; failure mapping and allocation limits |
| Metadata and payload | `references/metadata-payload-validation.md` | Metadata versus payload, applicable length/segment/checksum/axis checks, normalization limited to evidenced semantics |
| Integrity status | `references/status-and-reports.md` | `COMPLETE`/`INCOMPLETE`/`INVALID`/`UNVERIFIED`/`UNSUPPORTED`; per-check `pass`/`fail`/`not_checked`; report shape and analysis gates |
| Data-specific checks | `references/waveform-checks.md`, `references/scalar-checks.md`, `references/axes-and-sequences.md` | Point and byte counts, segment coverage, axes and units, reading count and instrument status, ordering and duplicate records |
| Evidence and provenance | `references/evidence-and-provenance.md` | Model, firmware, interface, command, raw response, SHA-256, parser version, manual citation, calibration binding |
| Offline testing | `references/replay-testing.md` | Valid and negative fixtures, expected results, no sockets or VISA in tests |

`references/integrity-and-provenance.md` is an earlier, shorter restatement of
the status and evidence rules and is not referenced by `SKILL.md`.

## Communication and parsing basis

The guide is written from published specifications and established open-source
instrument libraries. No implementation code is copied, and none of these
projects becomes a runtime dependency.

- **IEEE 488.2** binary block framing (`#<length-of-length><length><payload>`) is
  the reference for oscilloscope waveform transfers and other definite-length
  responses.
- **Vendor programming manuals** (for example SCPI manuals) are the only accepted
  source for command, field, and unit claims. They are cited by revision and page
  or section and are never copied into the repository.
- **PyVISA** — [reading and writing values](https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html)
  documents the decisions a transfer must make explicit: datatype, endianness,
  header, termination, and expected point count.
- **PyVISA-sim** — [simulated instruments](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html)
  informs query/response dialogues, end-of-message rules, and raw-byte replay
  testing.
- **PyMeasure** — [adapters](https://pymeasure.readthedocs.io/en/latest/api/adapters.html)
  and [advanced communication](https://pymeasure.readthedocs.io/en/latest/dev/adding_instruments/advanced_communication.html)
  support keeping transport below instrument semantics and framing/checksums above
  the byte layer.
- **QCoDeS community drivers** — [Qcodes_contrib_drivers](https://github.com/QCoDeS/Qcodes_contrib_drivers)
  model the separation of driver, examples, and tests, with support responsibility
  on the contributor.
- **PyVISA communication API shape** — [PyVISA documentation](https://github.com/pyvisa/pyvisa/blob/main/docs/source/introduction/communication.md)
  is cited in `skills/siglent-sds800xhd-control/references/connection-and-storage.md`
  for resource-manager usage; actual resource strings remain VISA-implementation
  dependent.

## Waveform analysis

The local analyzer (`skills/siglent-sds800xhd-control/scripts/waveform_analysis.py`
and `scripts/analyze_waveform.py`) implements threshold crossings, interpolated
edge times, pulse and runt widths, missing or long intervals, 10–90% transition
duration, and overshoot/undershoot/ringing screening.

These routines are bounded heuristics written for this repository. They are not
certified measurements, are not claimed to comply with any standard below, and
return their parameters, coverage, and `insufficient_evidence` or boundary flags
with every estimate.

- **IEEE Std 181-2011**, *IEEE Standard for Transitions, Pulses, and Related
  Waveforms* ([standards.ieee.org](https://standards.ieee.org/ieee/181/4414/);
  superseded by IEEE 181-2025) defines state levels, transition duration, pulse
  amplitude, and waveform aberrations such as overshoot and ringing. The `events`
  and `ringing` vocabulary follows it.
- **IEC 60469:2013**, *Transitions, pulses and related waveforms — Terms,
  definitions and algorithms* ([webstore.iec.ch](https://webstore.iec.ch/en/publication/2211))
  is the equivalent international standard and additionally specifies algorithms
  for computing state levels and pulse parameters.
- **M4 aggregation** — Jugel et al., *M4: A Visualization-Oriented Time Series
  Data Aggregation*, VLDB 2014
  ([paper](https://www.vldb.org/pvldb/vol7/p797-jugel.pdf)) informs only the lossy
  `visualization_only_lossy` preview.
- **NumPy memory-mapped access** — [`numpy.memmap`](https://numpy.org/doc/stable/reference/generated/numpy.memmap.html)
  is the chunked read path for large captures.
- **SciPy detectors** — [`find_peaks`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html)
  and [`welch`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
  are recorded for future specific detectors; SciPy is not a dependency.
- **Waveform-tool interaction model** — [wavekit-mcp](https://github.com/cxzzzz/wavekit-mcp)
  was reviewed for tool shape only; no code or parser is reused.

The design rationale behind these choices is recorded in
`docs/superpowers/specs/2026-10-17-ai-waveform-analysis-design.md`
(“Reuse and References”) and `.specs/2026-10-17-time-ranged-ringing-analysis.md`.

## Multimeter data handling

`skills/keithley-2000-control/` derives its parsing and validation rules from the
vendor manual (2000-900-01 Rev. J / August 2010) with page citations per command;
no open-source parser implementation is referenced.

## GDS-1000B oscilloscope data handling

`skills/gwinstek-gds1000b-control/` derives its command, range, and page claims
from the *GDS-1000B Series Programming Manual*, Version 1.00, March 2015. Its
waveform framing follows the manual's documented ASCII header plus IEEE 488.2
block, signed big-endian 16-bit samples, and fixed AD factor 25. The documented
voltage formula is labelled unverified because the manual's own example uses a
different scale value from the header. The Skill also records the model profile
(channel count, bandwidth, Ethernet) from the vendor specification table; USB
CDC host behavior is treated as host/OS evidence, not a manual claim.

## Function generator data handling

`skills/gwinstek-afg2225-control/` derives command, range, and page claims from
the *AFG-2225 Series User Manual* (GW Instek part no. 82RF-22250M01). Its USB
CDC identity is external evidence, not manual text:

- **Linux kernel** — commit
  [`cf84a691a61606a2e7269907d3727e2d9fa148ee`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=cf84a691a61606a2e7269907d3727e2d9fa148ee)
  adds `USB_DEVICE(0x2184, 0x001c)` for the AFG-2225 to `cdc-acm` (CDC-ACM, not
  USBTMC; byte-swapped `bInterfaceSubClass` 0x20).
- **avian2/gwinstek-tools** — [repository](https://github.com/avian2/gwinstek-tools)
  (GPL-3.0) uses `/dev/ttyACM0` and ASCII `DATA:DAC VOLATILE,0,...` lists; its
  README records unverified observations about ARB DC-offset inversion and
  `SOURCE1:OUTPUT ON`.
- **jmfrancklab/FLinst** — [repository](https://github.com/jmfrancklab/FLinst)
  uses an IEEE block with host-native `int16` data; this does not establish the
  byte order for this instrument.

No implementation code is copied. Community observations are labelled
`unverified` in the Skill and are never used as automatic workarounds.
