# Bench Setup (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013. This
page covers physical and session setup; the programming manual documents
command behavior, not a complete operator safety manual. Page numbers are
table-of-contents or List of Commands markers (pp. 24-34); the local converted
copy has no body page breaks.

## Verified unit and series

| Item | Value |
|---|---|
| Verified model | GW Instek GDS-2104A |
| Channels | 4 (CH1-CH4) |
| Bandwidth | 100 MHz |
| Sample rate | 2 GS/s |
| Serial | `GEN182193` |
| Firmware | `V1.18` |
| Verified interface | USB CDC-ACM `2184:0014`, `/dev/ttyACM1`, 115200 8N1, LF |
| Capture date | 2026-11-26 |

The Skill targets the GDS-2000A series. The manual and its examples also name
GDS-2064A, GDS-2074A, and GDS-2204A, but only the GDS-2104A above was tested.
Do not assume a full model/spec table from the examples, and do not assume that
another model has the same bandwidth, channel count, or installed options.

## Channel count and model gate

- `*IDN?` returns `GW,GDS-<model>,<serial>,V<version>`. The parser accepts the
  `GDS-<four digits>A` family and infers the channel count from the model
  number: the last digit before the trailing `A` being `4` means 4 channels,
  otherwise 2.
  That inference is a convenience, not an instrument query.
- Send CH3/CH4 commands only on a 4-channel model. The scripts validate
  CH1-CH4 syntactically; they cannot know which model is connected, so gate
  CH3/CH4 from `*IDN?` yourself.
- Digital channels D0-D15, bus decode, and logic triggering require the
  optional DS2-8LA/16LA hardware. The verified unit did not have it.
- The DS2-FGN function generator, DS2-LAN Ethernet, and DS2-GPIB modules are
  separate options. Querying an absent option returned `-240` or `-221`; do
  not assume an option from the model name alone.

## Probes and input limits

- Maximum input: **300 Vrms CAT I**.
- The verified unit's front panel is marked `300 Vpk MAX`, `1 MΩ // 16 pF`.
  Use the marking on the actual instrument when it differs.
- Use a probe rated for the measured voltage and category. A x1 probe does not
  provide the CAT II rating of a proper x10 probe.
- Compensate the probe before quantitative measurements; an uncompensated
  probe distorts amplitude and edge measurements.
- Set `:CHANnel<n>:PROBe:RATio` to match the physical probe and
  `:CHANnel<n>:PROBe:TYPe {VOLTage|CURRent}` to match the probe type before
  setting scale or trusting a measurement.
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
- Treat the CAT rating as a channel/probe system limit, not just a number for
  the scope connector.

## Warm-up and environment

- Allow the instrument to reach a stable operating temperature before
  quantitative work; the programming manual does not state a warm-up period.
- Keep ventilation clear; do not block the fan or place the instrument on soft
  surfaces.
- Use the documented AC input and do not modify the power cord or earth
  connection.
- Keep the bench free of loose probes and grounds that could contact a live
  potential when the scope is remote-controlled.

## Transport selection

- **USB CDC-ACM (all models)**: Type-B device port, CDC virtual COM on the
  host. The verified unit enumerated as `2184:0014` at `/dev/ttyACM1` and was
  opened at `115200 8N1`. The manual states no USB CDC serial default; the
  baud setting is a host convention, not a device requirement.
- **RS-232C (rear DB-9, documented)**: baud 2400, 4800, 9600, 19200, 38400,
  57600, or 115200; parity none/odd/even; 8 data bits fixed; 1 or 2 stop bits.
  Use a null-modem connection (pin 2 RxD, pin 3 TxD, pin 5 GND). Set the same
  values on the instrument and host. Not exercised by this Skill.
- **Ethernet (DS2-LAN option)**: the module must be installed, the IP
  configuration set, and the socket server enabled. The socket server is
  **off by default**, uses a selectable port **1024-65535**, and is raw TCP
  with LF termination. The HTTP port is fixed at 80. Not exercised.
- **GPIB (DS2-GPIB option)**: address 1-30; maximum 15 devices, 20 m cable
  length, 2 m between devices; no loop or parallel connection. Not exercised.
- **No automatic transport switching.** Pass the actual port or host
  explicitly; do not assume `/dev/ttyACM1` on another host.

## Panel lock and remote state

- `:SYSTem:LOCK {OFF|ON|?}` locks or releases the front panel. Lock only when
  the operator asks; it prevents local intervention. The verified unit reported
  `OFF`.
- Remote commands can change channel, timebase, trigger, and saved state. Read
  the current state before writing.
- Do not use `*RST` as a cleanup step. It returns the instrument to documented
  defaults and discards the operator's setup.
- Do not use `*SAV`, `*RCL`, `:SAVe:*`, or `:RECAll:*` as routine cleanup.
  They overwrite or replace stored state and files.
- If you change a channel, timebase, trigger, or measurement source, restore
  the original value and drain the error queue before ending the session.

## Storage and file paths

- Image and waveform files use `Disk:/` (internal) or `USB:/` (external flash
  drive). Do not assume a directory exists or that USB media is present.
- Image filenames are limited to 8 characters. Match the extension to
  `:SAVe:IMAGe:FILEFormat` (`PNG` or `BMP`).
- Never overwrite an operator file. Choose a unique name, or confirm the
  overwrite with the operator first.
- A successful save command means the instrument accepted the request; it does
  not prove the file exists, is readable, or contains the expected data. Drain
  `:SYSTem:ERRor?` and report the exact path.

## Pre-capture checklist

1. Model, channel count, and installed options confirmed from `*IDN?` and the
   front panel.
2. Probe type, ratio, and compensation confirmed.
3. Input category and voltage within the 300 Vrms CAT I rating.
4. Ground clip connected only to an earth-referenced potential.
5. Channel display, coupling, scale, bandwidth limit, and position set
   intentionally.
6. Trigger source, type, level, slope, coupling, and mode set intentionally.
7. Timebase scale/position and acquisition mode/record length appropriate to
   the signal.
8. Save paths and filenames confirmed before any file operation.
9. Error queue drained and a known-good `*IDN?` recorded in the session log.
