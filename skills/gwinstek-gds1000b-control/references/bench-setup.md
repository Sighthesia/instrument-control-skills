# Bench Setup (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015.
Support level: `documented`. This page covers physical setup; the programming
manual documents command behavior, not a full operator's safety manual.

## Models and channels

| Model | Channels | Bandwidth | EXT trigger | Ethernet |
|---|---|---|---|---|
| GDS-1054B | 4 (CH1-CH4) | 50 MHz | no | yes |
| GDS-1072B | 2 (CH1/CH2) | 70 MHz | yes | no |
| GDS-1074B | 4 (CH1-CH4) | 70 MHz | no | yes |
| GDS-1102B | 2 (CH1/CH2) | 100 MHz | yes | no |
| GDS-1104B | 4 (CH1-CH4) | 100 MHz | no | yes |
| GDS-1202B | 2 (CH1/CH2) | 200 MHz | yes | no |

Channel count and EXT availability change which trigger sources and channel
commands are valid. The scripts validate CH1-CH4 syntactically; they cannot
know which model is connected, so gate CH3/CH4 and EXT yourself.

## Probes and input limits

- Maximum input: **300 Vrms CAT I**, or **300 Vrms CAT II with a compatible
  10:1 probe**.
- Input impedance: **1 MΩ // 16 pF**, and **14 pF on GDS-1202B**.
- Use a probe rated for the measured voltage and category. A x1 probe does not
  provide the CAT II rating of a proper x10 probe.
- Compensate the probe before quantitative measurements; an uncompensated
  probe distorts amplitude and edge measurements.
- Set `:CHANnel<X>:PROBe:RATio` to match the actual probe so scale readback and
  measurements use the correct attenuation.
- Do not exceed the probe or input rating, even momentarily. A scope input is
  not a universal high-voltage probe.

## Grounding

- The instrument is **earth-referenced**. The probe ground clip is connected to
  earth through the instrument.
- Never connect the ground clip to a live potential, and never float the scope
  by lifting its protective earth.
- For floating, differential, or mains measurements, use a correctly
  CAT-rated differential probe or an isolation arrangement approved by the
  responsible engineer. This Skill cannot make that decision.

## Warm-up and environment

- Allow **30 minutes warm-up at 20-30 °C** before relying on specifications.
- Keep ventilation clear; do not block the fan or place the instrument on soft
  surfaces.
- Use the documented AC input and do not modify the power cord or earth
  connection.

## Transport selection

- **USB device port (all models)**: Type-B CDC-ACM virtual COM. The manual does
  not state baud/parity defaults; the scripts assume `115200 8N1` and label that
  as an assumption.
- **Ethernet (4-channel models only)**: the socket server is **off by
  default**, the port is selectable **1024-65535**, and communication is raw
  TCP with LF termination (manual p. 169). Enable it from the instrument
  before connecting.
- **No GPIB** and no documented RS-232 control port.

## Panel lock and remote state

- `:SYSTem:LOCK {OFF|ON|?}` locks or releases the front panel. Lock only when
  the operator asks; it prevents local intervention.
- Remote commands can change channel, timebase, trigger, and saved state.
  Read the current state before writing.
- Do not use `*RST` as a cleanup step. It returns the instrument to documented
  defaults and discards the operator's setup.

## Pre-capture checklist

1. Model and channel count confirmed.
2. Probe type, ratio, and compensation confirmed.
3. Input category and voltage within rating.
4. Ground clip connected only to earth-referenced potential.
5. Channel display, coupling, scale, and offset set intentionally.
6. Trigger source, level, slope, and mode set intentionally.
7. Timebase and record length appropriate to the signal.
8. Save paths and filenames confirmed before any file operation.
