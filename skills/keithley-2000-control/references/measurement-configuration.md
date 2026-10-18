# Measurement configuration

Evidence: Model 2000 User's Manual, PDF physical pages 50-54 and 168-183,
195, 205-207. Record all settings that can change the meaning, stability,
freshness, or timing of a reading.

## Minimum configuration snapshot

Record the current function; front/rear input selection; terminal path; range and
auto-range; NPLC/aperture; AC bandwidth; digital filter type/count/state; digits;
REL and math; units; trigger source/count/delay; sample count; buffer/scan state;
and the instrument identity. Query back settings when the command family
provides a query. Unknown state is `UNVERIFIED`, not a guessed default.

## Range and auto-range

- `:SENSe:<function>:RANGe[:UPPer] <n>` selects range; `:AUTO <b>` toggles
  auto-range. A fixed range setting disables auto-range. Function-specific range
  limits differ; query or use documented per-function values rather than
  reusing one range across functions.
- Auto-range is useful for discovery, but the manual says not to use it when
  optimum speed is required. It ranges up at 120% and down at 10% of nominal
  range. The temperature, continuity, and diode functions have one range or do
  not use auto-range (PDF 50).
- Prefer the lowest range that safely accommodates the expected signal; if
  overload occurs, do not keep acquiring as if valid. Reconfigure only when
  authorized and confirm readback.

## Resolution, NPLC, and bandwidth

- `:SENSe:<function>:DIGits <n>` affects display resolution, not the remote
  reading format; it does not itself improve accuracy or speed (PDF 52).
- `:SENSe:<function>:NPLCycles <n>` controls integration where supported. The
  documented bus minimum can differ from the front-panel FAST setting. Higher
  NPLC generally improves noise rejection but reduces rate; record the actual
  value rather than saying only “fast/slow” (PDF 53, 171).
- AC voltage/current MED/SLOW modes use bandwidth selection (`3`, `30`, or
  `300` Hz lower-frequency limit) rather than ordinary NPLC changes; NPLC may be
  ignored in those cases (PDF 54, 179).
- Frequency/period use aperture/gate-time semantics. Do not present NPLC as if
  it had the same meaning for every function.

## Filter, relative value, and math

- The averaging filter supports MOVing or REPeat behavior and a conversion
  count. Record both. It is not supported for frequency, period, continuity, or
  diode test (PDF 51, 177-178).
- REL subtracts a saved reference from later readings. Store whether REL is
  enabled and its reference. For ACV, do **not** use REL to remove the typical
  5½-digit offset; the manual warns this creates an error (PDF 32, 52).
- Math may apply MX+B, percent, dB/dBm, buffer statistics, or limit testing.
  `:SENSe:DATA?` does not return calculated math results; read through the
  appropriate CALCulate command and record the calculation configuration
  (PDF 41-45, 151-156, 169).

## Function-specific setup

- Temperature: set and record `:UNIT:TEMPerature`, thermocouple `:TYPE`,
  reference-junction selection (`SIMulated` or real card), and simulated value
  when applicable (PDF 180-182, 205).
- Continuity: record threshold from `1 Ω` to `1000 Ω`; default is `10 Ω`
  (PDF 45, 182-183).
- Diode: record test-current range `10 µA`, `100 µA`, or `1 mA` (PDF 46, 182).
- AC voltage/current: record bandwidth and relevant unit/display choices;
  crest factor affects accuracy (PDF 29-30, 54).
- Voltage units may include V, dB, or dBm; dBm depends on reference impedance.
  Record the reference rather than normalizing a dB/dBm result to volts without
  evidence (PDF 43-44, 205-207).

## Manual ambiguities

The manual's display-resolution discussion and command tables do not always
state the same defaults for digits. Treat defaults as function/firmware-specific:
query the active value and do not hard-code a universal default. Report
`documented` when describing command behavior; use `UNVERIFIED` for unknown
connected-instrument state.
