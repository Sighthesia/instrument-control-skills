# Fixture Provenance

All fixtures in this directory are **synthetic**. They reproduce response and
command shapes documented in the *AFG-2225 Series User Manual* (GW Instek part
no. 82RF-22250M01); none is a real instrument capture. Real hardware responses
are kept separately in `../captures/` with their own README and hash index.

The expected JSON files for identity, frequency, amplitude, and error queue are
derived from the real captures in `../captures/`, not from these synthetic
files. The synthetic files here exercise documented failure modes and parser
compatibility, including the manual's single-line error format.

| Fixture | Documented basis | Expected result |
|---|---|---|
| `identity.txt` | `*IDN?` format `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm` (p. 193) | synthetic only; real capture is `captures/idn.txt` |
| `identity-wrong-model.txt` | Same shape with a non-AFG model; must be `INVALID` | test assertion |
| `identity-missing-firmware.txt` | Same shape without the firmware field; must be `INCOMPLETE` | test assertion |
| `frequency.txt` | NR3 numeric response shape, for example `SOUR1:FREQ?` (p. 207) | synthetic only; real capture is `captures/freq.txt` |
| `frequency-bad.txt` | Non-finite token; must be `INVALID` | test assertion |
| `error-none.txt` | Empty error queue, manual `No error` (p. 292) | synthetic only; real capture is `captures/error-empty.txt` |
| `error-suffix.txt` | Documented single-line error `-138 Suffix not allowed` (p. 273) | parser-compatibility fixture; real two-line capture is `captures/error-syntax.txt` |
| `error-overflow.txt` | Documented `-350 Queue overflow` (p. 275) | test assertion |
| `arb-valid.csv` | Skill-defined CSV of DAC codes in `±511`, 1-4096 points (p. 261) | `assets/expected-arb-ascii.json` (synthetic command, not a hardware upload) |
| `arb-out-of-range.csv` | DAC code outside `±511`; must fail validation | test assertion |
| `arb-too-many.csv` | 4097 points; exceeds the 4096-point limit (p. 260) | test assertion |
| `arb-non-integer.csv` | Non-integer token; must be `INVALID` | test assertion |

The ARB CSV format is defined by this Skill, not by a vendor AWES CSV
specification. Raw bytes are preserved in every parser artifact as SHA-256 and
base64; the expected JSON files are checked against the current parser output.

No fixture may be upgraded to a hardware capture without recording the real
`*IDN?` response, firmware, interface, date, and raw command sequence. Hardware
captures belong in `../captures/`, never here.
