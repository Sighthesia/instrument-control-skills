# Instrument Types and Examples

Choose the example by the data claim and response framing, not by vendor name.
The examples are synthetic teaching formats and are not supported instrument
drivers.

| Instrument/data type | Response example | Main checks | Example |
|---|---|---|---|
| Oscilloscope waveform | IEEE 488.2 definite-length block | point count, bytes/point, raw bytes, calibration | `assets/examples/oscilloscope_ieee_block/` |
| Multimeter scalar reading | line-oriented CSV-like text | function, unit, status, reading count | `assets/examples/multimeter_scalar_text/` |
| Analyzer/sweep | CSV with independent axis | columns, numeric rows, axis monotonicity, duplicates | `assets/examples/analyzer_csv_sweep/` |
| Segmented data source | framed records with sequence/range fields | gaps, overlaps, duplicate sequence, payload width | `assets/examples/segmented_binary_records/` |
| Logger/status source | JSON-lines event records | sequence, timestamp ordering, end marker | `assets/examples/status_event_records/` |

Each example contains a JSON description, a uniquely named pure parser, tests,
expected output, and raw/negative fixtures. They show how to adapt the same
authoring stages to different data shapes without introducing a common runtime
adapter class.

## Research-informed boundaries

- PyVISA documents separate ASCII and binary value paths and requires explicit
  datatype, endianness, header, termination, and sometimes expected point count;
  use that as a checklist when designing a control Skill.
- PyVISA-sim models query/response dialogues, end-of-message rules, and raw bytes;
  it is a reference for control-layer simulation, not a dependency of these parser
  examples.
- PyMeasure documents transport adapters below instrument semantics and custom
  framing/address/checksum handling above the byte transport.
- QCoDeS community drivers demonstrate separate implementation, examples, and test
  contributions with per-driver support responsibility.

Sources:

- https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html
- https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html
- https://pymeasure.readthedocs.io/en/latest/api/adapters.html
- https://pymeasure.readthedocs.io/en/latest/dev/adding_instruments/advanced_communication.html
- https://github.com/QCoDeS/Qcodes_contrib_drivers
