# Fixture Provenance

All fixtures in this directory are **synthetic**. They reproduce response and
command shapes documented in the *AFG-2225 Series User Manual* (GW Instek part
no. 82RF-22250M01); none is a real instrument capture.

| Fixture | Documented basis | Expected result |
|---|---|---|
| `identity.txt` | `*IDN?` format `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm` (p. 193) | `assets/expected-identity.json` |
| `identity-wrong-model.txt` | Same shape with a non-AFG model; must be `INVALID` | test assertion |
| `identity-missing-firmware.txt` | Same shape without the firmware field; must be `INCOMPLETE` | test assertion |
| `frequency.txt` | NR3 numeric response shape, for example `SOUR1:FREQ?` (p. 207) | `assets/expected-numeric.json` |
| `frequency-bad.txt` | Non-finite token; must be `INVALID` | test assertion |
| `error-none.txt` | Empty error queue: documented as `No error` (p. 292) | test assertion |
| `error-suffix.txt` | Documented error example `-138 Suffix not allowed` (p. 273) | `assets/expected-error-queue.json` |
| `error-overflow.txt` | Documented `-350 Queue overflow` (p. 275) | test assertion |
| `arb-valid.csv` | Skill-defined CSV of DAC codes in `±511`, 1-4096 points (p. 261) | `assets/expected-arb-ascii.json` |
| `arb-out-of-range.csv` | DAC code outside `±511`; must fail validation | test assertion |
| `arb-too-many.csv` | 4097 points; exceeds the 4096-point limit (p. 260) | test assertion |
| `arb-non-integer.csv` | Non-integer token; must be `INVALID` | test assertion |

The ARB CSV format is defined by this Skill, not by a vendor AWES CSV
specification. Raw bytes are preserved in every parser artifact as SHA-256 and
base64; the expected JSON files are checked against the current parser output.

No fixture may be upgraded to a hardware capture without recording the real
`*IDN?` response, firmware, interface, date, and raw command sequence.
