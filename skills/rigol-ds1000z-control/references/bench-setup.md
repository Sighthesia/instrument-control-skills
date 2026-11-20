# Bench Setup (DS1000Z)

Manual: *DS1000Z Series User Guide*, UGA19115-1110, September 2020 (PDF physical
pages cited). Support level: `documented` for this page, except where a bullet
says `hardware-verified`. The User Guide is an operator document: it gives the
safety rules and the panel values, but not the electrical input specifications.

## Models and channels

Bandwidth and channel counts as listed in the User Guide model table (PDF
page 18) and overview (PDF page 15):

| Model | Analog bandwidth | Analog channels | Source channels | Digital channels |
|---|---|---|---|---|
| DS1104Z-S Plus | 100 MHz | 4 | 2 | 16 (needs RPL1116) |
| DS1074Z-S Plus | 70 MHz | 4 | 2 | 16 (needs RPL1116) |
| DS1104Z Plus | 100 MHz | 4 | — | 16 (needs RPL1116) |
| DS1074Z Plus | 70 MHz | 4 | — | 16 (needs RPL1116) |
| DS1054Z | 50 MHz | 4 | — | — |

- The 2020 table lists only the `Plus` / `-S` variants plus DS1054Z. The evidence
  unit reports plain `DS1074Z` (`*IDN?` = `RIGOL TECHNOLOGIES,DS1074Z,
  DS1ZA171004155,00.04.02.SP4`, `hardware-verified`), so its exact name is taken
  from the identity response, not from the table. Treat the response as
  authoritative and re-read it before reusing any evidence label.
- Every DS1000Z model has 4 analog channels (CH1-CH4). Digital channels exist
  only on `Plus`/MSO models with the RPL1116 logic probe; the digital channel
  input terminal "does not support hot plugging" (PDF page 30). This Skill does
  not cover digital channels.
- 1 GSa/s real-time sample rate and up to 24 Mpts standard memory are overview
  claims (PDF page 15). The settable memory depth and the allowed `:WAVeform`
  window are firmware-specific; see
  [capture-and-waveform.md](capture-and-waveform.md).

## Input category and earthing

- The instrument may be used **only within Measurement Category I** (PDF page
  10). Category I means circuits not directly connected to mains. Do not treat a
  scope input as a CAT II/III/IV measurement point.
- The mains input is installation (overvoltage) category II (PDF page 12). This
  describes how the instrument may be powered, not what it may measure.
- The instrument is grounded through the protective earth lead of the power cord;
  connect that earth terminal **before** any input or output terminal (PDF
  page 4).
- Probe ground lead: it is at earth potential. "Do not connect the ground lead to
  high voltage" (PDF page 4). The User Guide's warning is a hazard statement, not
  a voltage limit, so no number is repeated here.
- For floating or mains-referenced measurements use a correctly rated
  differential probe. The instrument's own inputs are single-ended and
  earth-referenced.

## Ratings the manual does not give

The User Guide contains **no numeric input impedance, no numeric maximum input
voltage, and no CAT rating per range**. Its instruction is "Observe All Terminal
Ratings … check your manual for more information about ratings" (PDF page 4),
with the ratings themselves in the *DS1000Z Series Datasheet* and printed on the
front panel next to the BNC connectors. Do not fill this gap from memory, from
another Rigol family, or from an online summary. If a task needs a numeric input
limit, read the datasheet for the exact model and record it with a citation.

The numbers the User Guide does provide are the vertical scale range at a given
probe ratio (below) and the environment limits (further down). Neither is an
absolute input limit.

## Probes

- Connect the passive probe BNC to an analog channel input and the ground clip or
  spring to the circuit ground terminal (PDF page 29). Probe models are listed in
  the datasheet, not the User Guide.
- Run the function inspection before the first measurement: `Storage → Default`,
  ground clip on the ground terminal, probe tip on the compensation signal
  output, probe at 10X, then `AUTO`; a clean square wave means the channel and
  probe are usable (PDF page 31).
- Compensate the probe: adjust the low-frequency compensation trimmer with a
  nonmetallic driver until the displayed square wave matches the "perfectly
  compensated" figure (PDF pages 31-32).
- The compensation terminal output "can only be used for probe compensation
  adjustment and cannot be used for calibration" (PDF page 31). It is not a
  voltage reference, so it cannot calibrate waveform volts. That is one reason
  this Skill keeps voltage reconstruction `UNVERIFIED`.
- Set the probe ratio on the instrument to match the physical probe:
  `0.01X … 1000X` in 1-2-5 steps, default `10X` (PDF page 53). A wrong ratio
  scales both the trace and the automatic measurements.

## Vertical range at the selected ratio

- With the default 10X probe ratio the adjustable vertical scale is
  **10 mV/div to 100 V/div**, in 1-2-5 steps in coarse mode, with a finer mode
  available (PDF page 54). The range depends on the probe ratio.
- The overview chapter separately claims a "1 mV/div to 10 V/div" dynamic range
  (PDF page 15). The two statements describe different quantities (fine
  adjustment versus standard coarse range) and the chapter 2 text is the
  operational one; do not quote the overview as a settable range.
- Channel coupling (`DC`/`AC`/`GND`) and the 20 MHz bandwidth limit change what
  the instrument displays but not what the input terminal must survive
  (PDF pages 52-53).

## Bench environment

- Ventilation: keep at least 10 cm clearance beside, above, and behind the
  instrument (PDF page 11).
- Operating temperature 0 °C to +50 °C; non-operating -40 °C to +70 °C
  (PDF page 12).
- Humidity: ≤95 % RH from 0 °C to +30 °C, ≤75 % RH from +30 °C to +40 °C, ≤45 %
  RH from +40 °C to +50 °C (PDF page 12).
- Altitude: operating below 3 km, non-operating below 15 km (PDF page 12).
- Pollution degree 2 (PDF pages 12-13).
- If the instrument shows a suspected failure, have it inspected by authorized
  personnel before further operation (PDF page 5).

## Network path for a remote session

- The LAN interface is on the rear panel (PDF page 236). `Utility → IO Setting →
  LAN Conf.` shows the connection status, MAC address, VISA address, and the
  IP configuration type (PDF page 236).
- The RemoteIO menu selects USB Device or LAN; a connected USB Device
  (`USB Device → Computer`) takes precedence and disables LAN control, while a
  LAN-only connection enables the LAN interface by default (PDF page 236).
- The evidence session used a direct cable to a dedicated host interface with the
  scope as a DHCP client on `10.99.0.194`, raw TCP port 5555
  (`hardware-verified`). That address and the host profile belong to the bench,
  not to the Skill; do not hard-code them.
- `:LAN:DHCP?`, `:LAN:MAC?`, and `:LAN:STATus?` answered on the evidence unit but
  are absent from the Programming Guide. Read
  [remote-session.md](remote-session.md) before touching anything
  `:LAN:`-related, and never write static addressing without a local recovery
  path.

## Pre-capture checklist

1. Probe and channel rating appropriate for the signal; ground clip on earth.
2. Probe ratio set to match the probe; probe compensated.
3. Channel displayed, coupling and scale read back from the instrument.
4. Trigger source, level, slope, and sweep read back from the instrument.
5. Acquisition state known (`:TRIGger:STATus?`), error queue drained.
6. The measured value is recorded together with that configuration, not on its
   own.
