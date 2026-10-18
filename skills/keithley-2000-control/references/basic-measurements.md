# Basic measurement methods

Use the Model 2000 user manual as the operating authority for the connected
instrument and leads. The ranges below summarize the manual, not a substitute
for the instrument's safety rating, probe rating, local electrical rules, or
current calibration.

## Function and connection selection

| Measurement | SCPI function token | Terminals / prerequisites | Manual location (PDF physical page) |
|---|---|---|---|
| DC voltage | `VOLTage[:DC]` | `INPUT HI` / `INPUT LO`; front or rear inputs selected | 29-32 |
| AC voltage | `VOLTage:AC` | `INPUT HI` / `INPUT LO`; front or rear inputs selected; account for crest factor and bandwidth | 29-32 |
| DC current | `CURRent[:DC]` | **Front** `AMPS` / `INPUT LO`; verify source can safely be opened and inserted in series | 33-34 |
| AC current | `CURRent:AC` | **Front** `AMPS` / `INPUT LO`; AC crest-factor considerations apply | 33-34 |
| 2-wire resistance | `RESistance` | `INPUT HI` / `INPUT LO`; de-energize the circuit before connecting | 35-36 |
| 4-wire resistance | `FRESistance` | `INPUT HI` / `INPUT LO` and `SENSE Ω4 WIRE HI` / `LO`; use Kelvin wiring | 35-36 |
| Frequency | `FREQuency` | Voltage inputs; signal >10% of selected full-scale range | 37-38 |
| Period | `PERiod` | Voltage inputs; signal >10% of selected full-scale range | 37-38 |
| Temperature | `TEMPerature` | Documented `-200 °C` to `+1372 °C` range depends on thermocouple; requires supported thermocouple/card path, thermocouple type, units, and simulated or real reference junction | 39-40, 145 |
| Continuity | `CONTinuity` | `INPUT HI` / `INPUT LO`; one range, configurable threshold | 45-46, 182-183 |
| Diode test | `DIODe` | `INPUT HI` / `INPUT LO`; test current is sourced from `INPUT HI` | 46, 182 |

The command tokens above are the manual's `:SENSe:FUNCtion` names (PDF 168).
They are also used by `:CONFigure:<function>`, `:MEASure:<function>?`, and the
function table on PDF 134-138. Use the exact spelling supported by the
instrument's SCPI parser; SCPI keywords are not case-sensitive.

## Before applying leads

1. Ask what the source is, whether it is energized, its expected voltage/current,
   available energy, polarity, and whether the requested measurement would
   interrupt the circuit.
2. Select a function only after confirming the connection path and instrument
   input selection. For front/rear voltage/resistance paths, read
   `:SYSTem:FRSWitch?` when remote state evidence is needed (`1` = front,
   `0` = rear; PDF 193).
3. For voltage or resistance, do not exceed `1000 V peak` between `INPUT HI`
   and `INPUT LO`. AC voltage is specified up to `750 V RMS` / `1000 V peak`;
   observe the `8 × 10^7 V·Hz` limit where applicable (PDF 29-30, 35, 38).
   Also keep common-mode voltage between `INPUT LO` and chassis ground at or
   below `500 V peak` (PDF 22).
4. For current, require the **front** input switch position and front `AMPS`
   terminal. Maximum input is `3 A DC or RMS` and `250 V`; the AMPS jack has a
   `3 A, 250 V, fast-blow, 5 × 20 mm` fuse (PDF 33-34). The instrument cannot
   query fuse continuity; do not infer a good fuse from identity or configuration.
5. Do not measure resistance, continuity, or diode behavior on an energized
   circuit unless an approved procedure explicitly establishes safe conditions.

## Function notes

### Voltage

- The manual specifies DCV from `0.1 µV` to `1000 V`, and ACV from `0.1 µV` to
  `750 V RMS` / `1000 V peak` (PDF 29).
- AC accuracy depends on waveform crest factor and frequency (PDF 29-30).
- For low-level signals, manage shielding, loop area, magnetic pickup, and
  thermal EMFs; connect an input shield to `INPUT LO` as appropriate (PDF 30-31).
- Do not zero the typical 5½-digit ACV shorted-input offset with REL. The manual
  says this offset is expected and REL would introduce an error (PDF 32).

### Current

- Insert the meter in series using front `AMPS` and `INPUT LO`. Never place the
  current input across a voltage source.
- Stop if the source current/voltage, available energy, or fuse status cannot be
  established. A displayed overflow or an error does not prove the fuse is good
  or identify the cause.
- The specified ranges are `10 nA` to `3 A` for DCI and `1 µA` to `3 A RMS` for
  ACI (PDF 33); actual input limits still govern.

### Resistance

- The manual documents 2-wire and 4-wire resistance from `100 µΩ` to `120 MΩ`
  (PDF 35). Use 4-wire sensing when lead/contact resistance would compromise
  the result.
- Shield resistances above `100 kΩ` as appropriate; connect the shield
  electrically to `INPUT LO` (PDF 36).
- Do not infer continuity of the external DUT from a resistance reading without
  considering test current and circuit state.

### Frequency and period

- Frequency range: `3 Hz` to `500 kHz`; period range: `2 µs` to `333 ms` (PDF
  37).
- The signal must exceed `10%` of the selected full-scale voltage range; use the
  AC voltage input path and observe the `8 × 10^7 V·Hz` limit (PDF 37-38).

### Temperature

- Temperature is thermocouple-based, and available range depends on sensor type.
  The manual describes a Model 2001-TCSCAN card or supported external switch
  system/card (PDF 39).
- The SCPI table gives a temperature reference span of `-200` to `+1372`; the
  usable measurement range depends on thermocouple type and reference setup
  (PDF 145).
- Record temperature unit, thermocouple type (`J`, `K`, or `T`), and reference
  junction selection/value. The simulated junction temperature and real card
  reference have different evidence; without the actual configuration, mark the
  reading `INCOMPLETE` or `UNVERIFIED` (PDF 40, 180-181).

### Continuity and diode

- Continuity uses a single range; the threshold is configurable from `1 Ω` to
  `1000 Ω` and defaults to `10 Ω` (PDF 45, 182-183). Include the threshold and
  test-rate context with a result.
- Diode test sources current from `INPUT HI`; selectable test current is `10 µA`,
  `100 µA`, or `1 mA`. A result above `10 V` is reported as overflow (PDF 46,
  182).

## Evidence limits

Manual ranges and connection descriptions are `documented`. They do not establish
the connected instrument's calibration, fuse continuity, actual terminals,
firmware behavior, or safe state of an external circuit. Record those separately.
