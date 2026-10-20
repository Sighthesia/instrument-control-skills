---
name: gwinstek-gds1000b-control
description: Control and document workflows for a GW Instek GDS-1000B series digital storage oscilloscope over USB CDC serial or model-dependent Ethernet socket SCPI. Use for identity/session setup, channel/timebase/trigger configuration, run/stop/single capture, acquisition-memory waveform download and offline validation, individual and slotted measurements, error-queue handling, and file-based save/screenshot workflows. All capabilities are documented-only; waveform voltage calibration is unverified.
---

# GW Instek GDS-1000B Control

Use this Skill for the GW Instek GDS-1000B series: GDS-1054B (4-channel,
50 MHz), GDS-1072B (2-channel, 70 MHz), GDS-1074B (4-channel, 70 MHz),
GDS-1102B (2-channel, 100 MHz), GDS-1104B (4-channel, 100 MHz), and GDS-1202B
(2-channel, 200 MHz). Commands follow the official *GDS-1000B Series
Programming Manual*, Version 1.00, March 2015; the local evidence copy is
`ref/编程指令手册.pdf` and page numbers below are PDF physical pages.

The Skill is `documented` only. No real instrument response is bundled, so do
not claim `hardware-verified` or `firmware-scoped`.

## Non-negotiable safety rules

- Confirm probe rating and input category before connecting anything. The
  documented maximum is 300 Vrms CAT I, or 300 Vrms CAT II with a compatible
  10:1 probe; input impedance is 1 MΩ // 16 pF (14 pF on GDS-1202B).
- The instrument is earth-referenced. Never float the scope or connect the
  probe ground clip to a live potential. Use a correctly CAT-rated
  differential probe for floating or mains measurements.
- Use properly rated probes, compensate them, and respect the probe and
  channel rating at the selected attenuation.
- Do not assume an input, trigger, or saved state is safe. Read the channel
  display/coupling/scale and trigger state before arming a capture.
- Do not send `*RST`, `*SAV`, `*RCL`, `:SAVE`, `:RECAll`, or panel-lock changes
  as routine cleanup. They change operator state or files; use only when the
  operator authorizes them.
- Do not overwrite files on `Disk:/` or `USB:/`. The scripts refuse existing
  local output unless `--overwrite` is explicit.
- Waveform voltages are not calibrated by this Skill. Preserve raw codes and
  treat the documented `(code / 25) * Vertical Scale` result as `UNVERIFIED`;
  the manual's own example is internally inconsistent (pp. 42-43).
- A numeric response is not proof that the acquisition, trigger, or probe setup
  was valid. Keep the configuration context with the data.

## Evidence and scope

- **Support level**: `documented` only. No hardware response is included.
- **Manual**: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015.
  Common commands pp. 33-39; acquisition and waveform pp. 41-46; vertical
  pp. 48-53; advanced features pp. 54-77, 170-249; hardcopy pp. 78-80;
  measurements pp. 81-113; run/stop pp. 117-118; timebase pp. 119-121;
  trigger pp. 122-162; system pp. 163, 250-253; save/recall pp. 164-168;
  Ethernet p. 169.
- **External/transport evidence**: USB CDC-ACM creates a virtual COM port on
  the host, and Linux typically exposes `/dev/ttyACM0`. This is host/OS
  behavior, not a manual claim about serial framing.
- **Evidence gaps**: USB CDC baud/parity defaults, real-device acceptance of
  each sequence, waveform calibration, firmware-dependent behavior, and
  optional-license feature availability.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

Labels describe evidence, not feature count. This Skill is intentionally
`documented`.

## Device boundary

- **Models**: see the list above. 2-channel models expose CH1/CH2 plus EXT
  trigger; 4-channel models expose CH1-CH4.
- **Interfaces**: USB device (Type-B, CDC-ACM virtual COM) on every model.
  Ethernet socket server only on GDS-1054B/GDS-1074B/GDS-1104B; it is off by
  default, uses a selectable port 1024-65535, raw TCP, LF termination, and must
  be enabled on the instrument (manual p. 169). No GPIB.
- **Language**: SCPI 1994, partially compatible; IEEE 488.2 common commands.
- **Primary data kinds**: `identity` (`*IDN?`), `scalar-measurement`
  (`:MEASure:*?`), `status-record` (error queue), and `waveform`
  (`:ACQuire<X>:MEMory?`).
- **Not automatic**: calibration, firmware update, probe compensation,
  panel save/recall/delete, file overwrite, panel unlock.
- **Optional/licensed**: digital filter, bus decode, and some advanced
  features. Treat them as conditional until the installed option is confirmed.

## Task-specific reference table

| Goal | Reference |
|---|---|
| Models, probes, input limits, grounding, warm-up, panel lock | [bench-setup.md](references/bench-setup.md) |
| USB CDC, Ethernet socket, terminators, `*IDN?`, status/error, save/recall | [remote-session.md](references/remote-session.md) |
| Run/stop/single, trigger state, record length, memory download, block format | [capture-and-waveform.md](references/capture-and-waveform.md) |
| Channel, timebase, and trigger configuration and constraints | [vertical-timebase-trigger.md](references/vertical-timebase-trigger.md) |
| Individual measurements and eight-slot statistics | [measurements.md](references/measurements.md) |
| Image/hardcopy save, waveform/setup save/recall, file limits | [save-and-screenshot.md](references/save-and-screenshot.md) |
| Math, cursors, display, decode, search, segments, DVM, Go-NoGo, datalog, remote disk | [advanced-features.md](references/advanced-features.md) |
| Parser stages, statuses, raw evidence, calibration caveat | [response-and-evidence.md](references/response-and-evidence.md) |
| Cross-check a command across subsystems, or answer a command question no task reference covers | [command-reference.md](references/command-reference.md) |

Load only the reference matching the current task. The command index is a
fallback, not a starting point: open it only when the task reference and the
scripts cannot answer the command question. It lists only commands this Skill
already records; anything absent must be verified against the programming manual
and labelled `documented` before use, and the safety rules above still apply.

## Standard remote session

1. Open the USB CDC port, or the already-enabled Ethernet socket. The scripts
   assume `115200 8N1` for USB; the manual states no default.
2. Send `*IDN?`; preserve the raw bytes; validate `GW,GDS-<model>,P<serial>,V<version>`.
3. Gate by model: channel count, EXT availability, Ethernet, and the
   `:ETHERnet:DHCP` command (only GDS-1074B/GDS-1104B).
4. Read the current state before changing it: trigger state, timebase, channel
   display/scale/coupling.
5. Clear status only when authorized; `*CLS` clears status and the error queue.
6. Drain `:SYSTem:ERRor?` and record each `code, "message"` until `+0, "No error."`.
7. Configure channel, timebase, and trigger settings.
8. Arm with `:SINGle` (or `:RUN`), poll state, then `:STOP` before downloading.
9. Drain the error queue again after the operation.

Query pairing: one session, one query, one response. Never send a second query
while an earlier response is unread. Write with LF; accept LF/CR/CRLF/LFCR
terminators on input.

## Capture and waveform workflow

1. Confirm the probe, channel display, coupling, scale, and trigger source.
2. `:HEADer ON` so the memory response carries scale and unit metadata
   (default ON, manual p. 46).
3. `:SINGle` (or `:RUN` for free-running capture). Do not auto-`:FORCe` after a
   timeout; forcing hides a wrong trigger setup.
4. Poll `:TRIGger:STATe?` (`*ARMED`, `*AUTO`, `*READY`, `*SAVE`, `*TRIGGER`) and
   `:ACQuire<X>:STATe?` (0 = not ready, 1 = ready, manual p. 45).
5. `:STOP` before `:ACQuire<X>:MEMory?`; download the header, `Waveform Data;`
   marker, and IEEE block.
6. Save the raw bytes first, then parse. Report point count, block length,
   payload SHA-256, and calibration status.
7. Keep memory record length (`1e3`-`1e7` points) within host limits; a 10 Mpt
   response is about 20 MB. Do not inline it into JSON; use CSV streaming and
   save the raw binary separately.

## Measurement workflow

- Select the source with `:MEASure:SOURce1/2 {CH1..CH4|MATH}`; only displayed,
  active channels produce values.
- Query an individual item, for example `:MEASure:FREQuency?` or
  `:MEASure:PK2PK?`. The response is `<NR3>` or `Chan Off`.
- Treat `Chan Off` as `INCOMPLETE`, never as zero.
- Voltage/current units depend on `:CHANnel<X>:PROBe:TYPe`; this Skill does not
  guess between V and A.
- For up to eight measurement slots and statistics, use the
  `:MEASUrement:MEAS<X>:*` family; confirm the slot is enabled before reading
  `VALue?`, `MAXimum?`, `MEAN?`, `MINImum?`, or `STDdev?`.
- Record the acquisition context (timebase, vertical scale, probe ratio,
  coupling, trigger) with the value.

## Save and screenshot workflow

- `:DISPlay:OUTPut?` returns the screen image as 16-bit RGB run-length encoded
  data (manual p. 77). It is the only image readback path; no bundled parser
  decodes it yet, so treat any saved response as raw bytes, `UNVERIFIED`.
- Saved files are still not readable: `:SAVe:IMAGe` writes `Disk:/` or
  `USB:/` and nothing returns those bytes.
- `:SAVe:IMAGe "Disk:/pic1.PNG"` with `:SAVe:IMAGe:FILEFormat {PNG|BMP}`
  (manual pp. 165-166). Filenames are limited to 8 characters.
- Hardcopy: `:HARDcopy:MODe {PRINT|SAVE}`, `ASSIGN`, `SAVEFORMat`, `START`
  (manual pp. 78-80).
- Waveform/setup save and recall use `:SAVe:WAVEform` / `:RECAll:WAVEform` and
  `:SAVe:SETUp` / `:RECAll:SETUp` (manual pp. 164-168).
- Never overwrite operator files automatically; report the exact path written.

## Offline parser and builders

`scripts/gds1000b_protocol.py` is transport-independent and standard-library
only:

```text
python3 scripts/gds1000b_protocol.py identity assets/fixtures/identity.txt
python3 scripts/gds1000b_protocol.py measure assets/fixtures/measure-frequency.txt --quantity frequency
python3 scripts/gds1000b_protocol.py error-queue assets/fixtures/error-none.txt
python3 scripts/gds1000b_protocol.py waveform assets/fixtures/waveform-valid.bin --csv-out wave.csv
python3 scripts/gds1000b_protocol.py waveform-header assets/fixtures/waveform-valid.bin
```

Stages: `read_frame` -> `parse_metadata` -> `extract_payload` -> `normalize` ->
`validate`. Waveform stages: `parse_waveform_header` -> `parse_ieee_block` ->
`normalize_waveform` -> `validate`; `iter_samples` uses
`struct.iter_unpack(">h", payload)`. The high-level `parse_identity`,
`parse_measurement`, `parse_error_queue`, and `parse_waveform` compose the
stages; intermediate results remain inspectable.

Optional live transport: `scripts/gds1000b_session.py` (lazy pyserial/socket
import; `--dry-run` prints exact bytes and opens nothing). It never runs
`*RST`, `*SAV`, `*RCL`, calibration, or automatic file overwrite.

## Integrity statuses

- `COMPLETE`: framing, required fields, units, and applicable structural
  checks pass for the stated claim.
- `INCOMPLETE`: a required byte, terminator, field, point, or response element
  is missing (including `Chan Off` and queue overflow).
- `INVALID`: framing, numeric, field, or type constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded but calibration, freshness, headerless
  metadata, or hardware acceptance is not proven.
- `UNSUPPORTED`: the response shape or feature is not implemented.

Never silently pad, truncate, clamp, interpolate, or guess. Line-response
artifacts preserve raw bytes as SHA-256 and base64; waveform artifacts preserve
raw and payload SHA-256 and leave the raw binary file to the caller.

## Verification commands

```bash
python3 -m unittest discover -s skills/gwinstek-gds1000b-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/gwinstek-gds1000b-control
npx skills@latest add . --list
```

There is no hardware in this repository's verification path.

## Known limitations / manual defects

- No hardware verification; every capability is `documented`.
- Waveform voltage conversion is uncalibrated, and the manual's header example
  (`Vertical Scale,5.000E+00`) disagrees with its calculation (`0.5`).
- `115200 8N1` for USB CDC is an assumption; the manual gives no default.
- Ethernet socket server is off by default and must be enabled from the front
  panel. The interface chapter describes it for the GDS-1000B generally (manual
  pp. 10-11); only `:ETHERnet:DHCP` is restricted to GDS-1074B/GDS-1104B
  (manual p. 169). Do not assume the socket server is absent on 2-channel
  models.
- `:DISPlay:OUTPut?` returns a run-length encoded screen image (manual p. 77);
  saved files (`Disk:/`, `USB:/`) are still not readable over SCPI.
- `:HEADer OFF` removes scale and unit metadata; such blocks are `UNVERIFIED`.
- Advanced features (bus decode, digital filter, some trigger types) are
  option- or model-dependent; the scripts do not implement them.
- Ground-referenced inputs and CAT ratings remain the operator's responsibility.
