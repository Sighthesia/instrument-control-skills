---
name: gwinstek-gds2000a-control
description: Control and document workflows for a GW Instek GDS-2000A series digital storage oscilloscope over USB CDC serial, with RS-232C and optional Ethernet socket and GPIB transports. Use for identity/session setup, read-only state snapshots, channel/timebase/trigger configuration, run/stop/single capture, acquisition-memory waveform download and code-domain validation, individual measurements and slotted-measurement documentation, error-queue handling, raw screen-image readback, and conservative save/hardcopy workflows. Identity, read-only state, one waveform, selected measurements, and selected set/readback/restore paths are hardware-verified on a GDS-2104A V1.18; waveform voltage calibration and image decoding are unverified.
---

# GW Instek GDS-2000A Control

Use this Skill for the GW Instek GDS-2000A series. The verified unit is a
**GDS-2104A**: 4 channels, 100 MHz, 2 GS/s, serial `GEN182193`, firmware
`V1.18`, USB CDC-ACM `2184:0014` at `/dev/ttyACM1`, 115200 8N1, LF terminator,
captured **2026-11-26**. The manual covers the GDS-2000A series command set;
this Skill does not claim a complete model table. Gate CH3/CH4 and optional
features from `*IDN?` and the installed options.

Commands follow the official *GDS-2000A Series Programming Manual*, Version
1.4, August 2013. The local evidence copy is
`ref/GDS-2000A_Programming_Manual_v1.4.extracted.md`, a converted text file.
It has no body page breaks, so every page number cited in this Skill comes
from the manual's table of contents or from its **List of Commands in
Functional Order** (pp. 24-34). Do not invent a body page from the converted
text.

Optional hardware seen in the manual: **DS2-LAN** (Ethernet/socket server),
**DS2-GPIB** (GPIB), **DS2-FGN** (function generator), and **DS2-8LA/16LA**
(logic analyzer/bus decode). None of those options was exercised on the
verified unit; the DS2-FGN and logic-option queries returned `-240 Hardware
error`, and DVM/Datalog/GoNoGo queries returned empty lines or `-221 Settings
conflict`.

## Non-negotiable safety rules

- Confirm probe rating and input category before connecting anything. The
  documented maximum is **300 Vrms CAT I**; the verified unit's front panel is
  marked `300 Vpk MAX`, `1 MΩ // 16 pF`. Do not exceed the probe or input
  rating, even momentarily.
- The instrument is **earth-referenced**. Never float the scope or connect the
  probe ground clip to a live potential. Use a correctly CAT-rated
  differential probe for floating, differential, or mains measurements.
- Use properly rated probes, compensate them, and set
  `:CHANnel<n>:PROBe:RATio` and `:CHANnel<n>:PROBe:TYPe` to match the physical
  probe before trusting a scale or measurement.
- Do not assume an input, trigger, or saved state is safe. Read the channel
  display/coupling/scale and trigger state before arming a capture.
- Do not send `*RST`, `*SAV`, `*RCL`, `:AUTOSet`, `:SAVe:*`, or `:RECAll:*`
  as routine cleanup. They reset operator state or overwrite slots/files.
  Do not send `:DATe` or change the panel lock without explicit authorization;
  they change the clock or block local operation.
- Do not overwrite files on `Disk:/` or `USB:/`. The scripts refuse an existing
  local output unless `--overwrite` is explicit; they cannot enforce the same
  rule on the instrument's storage, so choose unique names.
- Do not use `:FORCe` as a timeout workaround. A capture that never becomes
  ready has a wrong trigger, source, or level; forcing hides that.
- Waveform voltages are not calibrated by this Skill. The programming manual
  gives no code-to-volts formula. Preserve raw signed-16-bit codes and treat
  every waveform as `code-domain-only`; `calibration.status` is always
  `UNVERIFIED`.
- A numeric response is not proof that the acquisition, trigger, probe, or
  calibration was valid. Keep the configuration context with the data.
- `:DISPlay:OUTPut?` returns a 16-bit RGB run-length image, not a decoded
  picture. No decoder is bundled; the raw block is `UNVERIFIED`.

## Evidence and scope

- **Verified instrument**: GW Instek GDS-2104A, serial `GEN182193`, firmware
  `V1.18`, USB CDC-ACM `2184:0014` at `/dev/ttyACM1`, 115200 8N1, LF, on
  **2026-11-26**. Raw captures and the full exchange are in
  `artifacts/hw-verify/gds2000a-20261126/` (git-ignored, local reference only).
  Shipped fixtures under `assets/fixtures/hardware/` are the raw bytes used by
  the offline parser and are indexed in `assets/fixtures/README.md`.
- **`hardware-verified` subset**: 51 of the 339 forms in the manual's List of
  Commands, plus 2 body-only forms recorded in Appendix A of
  `references/command-reference.md`. The evidence covers:
  - `*IDN?` identity `GW,GDS-2104A,GEN182193,V1.18`;
  - `:SYSTem:ERRor?` `+0, "No error."`, and preserved `-113`/`-108` records;
  - read-only queries for acquisition mode/record length/header, CH1 vertical
    settings, math display/type, hardcopy state, measurement gating/method,
    timebase, trigger, panel lock, save-image format/ink saver, search state/
    total, buzzer, Go-NoGo script state, and segment state/total;
  - set/readback/restore of `:CHANnel1:SCALe`, `:CHANnel1:COUPling`,
    `:TIMebase:SCALe`, `:TRIGger:LEVel`, and `:BUZZER`, with the original
    values restored and the error queue empty;
  - `:MEASure:SOURce1` change/restore, `:MEASure:PK2PK?` -> `8.000E-02`, and
    `Ch Off` for an inactive source;
  - `:STOP`, `:RUN`, and `:SINGle` transitions, with continuous acquisition
    restored;
  - one `:ACQuire1:MEMory?` 5,000-point CH1 waveform after `:STOP`, structure
    `COMPLETE`, calibration `UNVERIFIED`;
  - one `:DISPlay:OUTPut?` raw RLE block, declared 38,822 bytes, decode
    `UNVERIFIED`.
- **`documented` only / not implemented**: autoscale, `:FORCe`, math/FFT
  configuration, cursors, reference waveforms, all other measurement items,
  slotted-measurement configuration, most trigger subtypes, save/recall writes,
  hardcopy `:START`, file writes, bus decode/digital channels, labels, marks,
  search configuration, DVM, the DS2-FGN function generator, Go-NoGo/
  template execution, data logging, Ethernet, GPIB, RS-232C, and other GDS-2000A
  models. The complete list and per-row status are in
  [command-reference.md](references/command-reference.md).
- **Known evidence gaps**: code-to-volts conversion, image RLE decoding, actual
  save/hardcopy file writes, a shipped 1,000,000-point LMEMory capture,
  channel 2-4 behavior, measurement accuracy/calibration, optional-option
  behavior, other models, and the non-USB transports.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response or a set/readback pair was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

Labels describe evidence, not feature count. This Skill is
`hardware-verified` for the subset above and `documented` for every other
command family; do not extend one capture to another model, firmware, or
interface.

## Device boundary

- **Models**: GDS-2000A series. Verified only the GDS-2104A (4 channels,
  100 MHz, 2 GS/s). The parser accepts `GDS-<four digits>A` and infers the
  channel count from the model number (the last digit before the trailing
  `A` is `4` on a 4-channel model); that inference is a convenience, not a
  hardware probe.
- **Interfaces**: USB CDC-ACM on every model (`2184:0014` on the verified
  unit). RS-232C rear DB-9 is documented. Ethernet requires the optional
  **DS2-LAN** module and its socket server is off by default. GPIB requires
  the optional **DS2-GPIB** module. Ethernet, GPIB, and RS-232C were not
  exercised.
- **Language**: SCPI 1994, partially compatible; USB CDC-ACM. Commands are
  case-insensitive and use LF termination.
- **Primary data kinds**: `identity` (`*IDN?`), `scalar-measurement`
  (`:MEASure:*?`), `status-record` (error queue), `waveform`
  (`:ACQuire<n>:MEMory?`), and raw `screen-image` (`:DISPlay:OUTPut?`).
- **Not automatic**: calibration, firmware update, probe compensation, panel
  save/recall/delete, file overwrite, autoscale, force-trigger, image decode,
  and voltage conversion.
- **Optional/licensed**: DS2-LAN, DS2-GPIB, DS2-FGN, DS2-8LA/16LA, DVM,
  Datalog, Go-NoGo. Treat each as conditional until the installed option is
  confirmed.

## Task-specific reference table

| Goal | Reference |
|---|---|
| Models, probes, input limits, grounding, pre-capture checklist | [bench-setup.md](references/bench-setup.md) |
| USB CDC, RS-232C, Ethernet, GPIB, framing, identity, status/error queue | [remote-session.md](references/remote-session.md) |
| Run/stop/single, acquisition memory, header, IEEE block, CSV export | [capture-and-waveform.md](references/capture-and-waveform.md) |
| Channel, timebase, trigger configuration and constraints | [vertical-timebase-trigger.md](references/vertical-timebase-trigger.md) |
| Individual measurements, sentinels, slotted measurements, statistics | [measurements.md](references/measurements.md) |
| Screen-image readback, hardcopy, image/waveform/setup save | [save-and-screenshot.md](references/save-and-screenshot.md) |
| Math, cursors, display, bus/decode, search, segments, DVM, function generator, Go-NoGo, datalog | [advanced-features.md](references/advanced-features.md) |
| Parser stages, statuses, raw evidence, calibration caveat, manual defects | [response-and-evidence.md](references/response-and-evidence.md) |
| Cross-check a command across subsystems, or answer a command question no task reference covers | [command-reference.md](references/command-reference.md) |

Load only the reference matching the current task. The command index is a
fallback, not a starting point: open it only when the task reference and the
scripts cannot answer the command question. It lists every form in the
manual's own command list; anything absent must be verified against the
programming manual and labelled `documented` before use, and the safety rules
above still apply.

## Sendable spelling rules

The manual's list prints family forms, not always the exact spelling the
instrument accepts. The verified unit required these rules; full evidence is
in [command-reference.md](references/command-reference.md#sendable-spelling-rules).

- `:CHANnel<n>:*`, `:ACQuire<n>:*`, `:MEASure:SOURce<n>`, and
  `:MEASUrement:MEAS<n>:*` need a numeric suffix. Bare
  `:CHANnel:SCALe?`-style spellings were not sent; bare
  `:ACQuire:MEMory?` returned an empty line, bare `:ACQuire:STATe?` returned
  `-113`, and bare `:MEASure:SOURce` returned `-131`.
- Individual `:MEASure:*?` commands do **not** take a channel parameter.
  Select the source first with `:MEASure:SOURce1 CH1`; `:MEASure:PK2PK? CH1`
  returned `-108 Parameter not allowed`.
- `:TRIGger:*` and `:TIMebase:*` are global and take no channel suffix on this
  series.
- `:FUNCtion:*` requires a module suffix such as `:FUNCtion1:`; the DS2-FGN
  option is not installed on the verified unit, so even the suffixed query
  returned `-240`.
- Send one command per write with LF (`\n`), then read before the next write.
  Do not concatenate commands.

## Standard remote session

1. Open the USB CDC port, or an already-enabled Ethernet socket, RS-232C, or
   GPIB link. The helper assumes `/dev/ttyACM1`, `115200 8N1`; the manual states
   no USB CDC default, so pass `--port`/`--baud` when the host differs.
2. Send `*IDN?`; preserve the raw bytes; validate
   `GW,GDS-<model>,<serial>,V<version>`.
3. Gate by model: channel count, CH3/CH4 availability, and installed options.
   Do not send a CH3/CH4 command to a 2-channel model.
4. Read the current state before changing it: trigger state, timebase, channel
   display/scale/coupling, and `:HEADer?`.
5. Clear status only when authorized; `*CLS` clears status and the error queue.
6. Drain `:SYSTem:ERRor?` and record each `code, "message"` until
   `+0, "No error."`.
7. Configure channel, timebase, and trigger settings.
8. Arm with `:SINGle` (or `:RUN`), poll `:ACQuire1:STATe?`/`:TRIGger:STATe?`,
   then `:STOP` before downloading memory.
9. Drain the error queue again after the operation, restore any state you
   changed, and close the session.

Query pairing: one session, one query, one response. Never send a second query
while an earlier response is unread. Write with LF; accept LF/CR/CRLF/LFCR
terminators on input. A double LF after `:TRIGger:FREQuency?` was observed and
is kept as framing evidence, not treated as a second response.

## Capture and waveform workflow

1. Confirm the probe, channel display, coupling, scale, probe ratio/type, and
   trigger source.
2. Keep `:HEADer ON` so the memory response carries scale and unit metadata
   (default ON, TOC p. 45).
3. Set the acquisition mode deliberately. `SAMPle` is the verified mode;
   `PDETect` changes what a point means, and `AVERage` needs its own count.
   Record the mode with the data.
4. `:SINGle` (or `:RUN` for free-running capture). Do not auto-`:FORCe` after a
   timeout; forcing hides a wrong trigger setup.
5. Poll `:TRIGger:STATe?` and `:ACQuire1:STATe?` (0 = not ready, 1 = ready,
   TOC p. 43). In `AUTO` mode a completed record is not a triggered record.
6. `:STOP` before `:ACQuire1:MEMory?`; download the ASCII header, the
   `Waveform Data;` marker, and the IEEE 488.2 block.
7. Save the raw bytes first, then parse. Report point count, block length,
   payload SHA-256, read end, and calibration status.
8. Do not present a voltage. This manual documents no code-to-volts formula;
   `analysis_allowed` is `code-domain-only`.
9. If the helper stopped a running acquisition, restore continuous acquisition.
   On V1.18 `:RUN` alone did not leave `READY`/`SAVE`; a `:STOP` followed by
   `:RUN` restored `AUTO`/`ARMED`.

## Measurement workflow

- Select the source with `:MEASure:SOURce1 CH1` (or `CH2`-`CH4` on a
  4-channel model), query an individual item such as `:MEASure:PK2PK?`, then
  restore the original source. The helper does this and drains the error queue.
- The response is `<NR3>` or `Chan Off`/`Ch Off`. Treat both source-off
  spellings as `INCOMPLETE`, never as zero. Treat `9.9E+37` (observed while a
  slotted measurement was disabled) as `INCOMPLETE`, never as a reading.
- Voltage/current units depend on `:CHANnel<n>:PROBe:TYPe`; the Skill reports
  `V or A` rather than guessing. Area is `V·s or A·s`. Counts are unitless.
- For slotted measurements, set `:MEASUrement:MEAS<n>:SOURce1`,
  `:TYPe`, and `:STATE` before reading `:VALue?`, `:MAXimum?`, `:MEAN?`,
  `:MINImum?`, or `:STDdev?`. A disabled slot returned the `9.9E+37` sentinel.
  The bundled helper does not configure slots.
- Record the acquisition context (mode, record length, timebase, vertical
  scale, probe ratio, coupling, trigger type/source/level/mode) with the value.
  A finite number is not proof that the setup was valid.

## Save and screenshot workflow

- `:DISPlay:OUTPut?` returns the screen as a 16-bit RGB run-length encoded
  block (`#<n><len>[count][color]...` plus LF). The verified response declared
  38,822 payload bytes. No decoder is bundled, so save the raw bytes and report
  `UNVERIFIED`; do not call it a PNG or a verified image.
- Saved files on `Disk:/` or `USB:/` cannot be read back over SCPI. `:SAVe:*`
  writes a file on the instrument; no command returns its bytes.
- `:HARDcopy:START` is a write that can print or save. The final run queried
  `:HARDcopy:MODe?` (`SAVE`), `:ASSIGN?` (`IMAGE`), `:SAVEFORMat?` (`BMP`),
  and the two ink-saver states, but did not send `:START`.
- Never overwrite operator files automatically. Use a unique filename stem of
  at most 8 characters and the matching file format. Report the exact path written; do not
  claim the file was downloaded.

## Offline parser and builders

`scripts/gds2000a_protocol.py` is transport-independent and standard-library
only:

```text
python3 scripts/gds2000a_protocol.py identity assets/fixtures/hardware/identity.txt --provenance hardware-verified
python3 scripts/gds2000a_protocol.py measurement assets/fixtures/hardware/measure-pk2pk.txt --quantity pk2pk --provenance hardware-verified
python3 scripts/gds2000a_protocol.py error-queue assets/fixtures/hardware/error-none.txt --provenance hardware-verified
python3 scripts/gds2000a_protocol.py waveform assets/fixtures/hardware/acquire1-memory.bin --provenance hardware-verified
python3 scripts/gds2000a_protocol.py waveform-header assets/fixtures/hardware/acquire1-memory.bin
python3 scripts/gds2000a_protocol.py waveform assets/fixtures/hardware/acquire1-memory.bin --csv-out wave.csv
```

Stages: `read_frame` -> `parse_metadata` -> `extract_payload` -> `normalize` ->
`validate`. Waveform stages: `parse_waveform_header` -> `parse_ieee_block` ->
`parse_waveform`; `iter_samples` uses `struct.iter_unpack("<h", payload)`
(little-endian is observed, not documented), and `waveform_to_csv` streams
`index,code`. The high-level `parse_identity`, `parse_measurement`,
`parse_error_queue`, `drain_error_queue`, `parse_waveform`, and
`waveform_to_csv` compose the stages; intermediate results remain inspectable.

Optional live transport: `scripts/gds2000a_session.py` (lazy pyserial import;
`--dry-run` prints exact bytes and opens nothing). It never runs `*RST`,
`*SAV`, `*RCL`, autoscale, calibration, or automatic file overwrite.

```text
python3 scripts/gds2000a_session.py --dry-run idn
python3 scripts/gds2000a_session.py --dry-run state
python3 scripts/gds2000a_session.py --dry-run measure --item pk2pk --channel 1
python3 scripts/gds2000a_session.py --dry-run waveform --channel 1 --out ch1.bin
python3 scripts/gds2000a_session.py --dry-run screenshot --out screen.bin
```

Live use requires operator authorization. The helper's default provenance is
`hardware-verified`; pass `--provenance documented` when the bytes do not come
from the captured unit/firmware.

## Integrity statuses

- `COMPLETE`: every applicable **structural and count** check passes for the stated claim (framing, required fields, point/row counts, terminator); it never means the data is correct, covers what the caller wanted, or is within calibration.
- `INCOMPLETE`: a required byte, terminator, field, point, segment, or status element is missing.
- `INVALID`: framing, counts, or type constraints contradict the observed bytes.
- `UNVERIFIED`: parsing found no contradiction, but the available evidence cannot prove completeness, units, calibration, or acquisition state.
- `UNSUPPORTED`: this Skill does not implement that response shape or feature.

A structural status never stands in for a different claim: **bytes complete**,
**scale usable**, **same frame**, and **the number is a physical level** are four
separate conclusions. Where an artifact reports one of them, it names it.
Waveform `COMPLETE` means the block and declared point count agree; it does not
mean the codes are calibrated volts or that the trigger setup was valid.

Never silently pad, truncate, clamp, interpolate, or guess. Line-response
artifacts preserve raw bytes as SHA-256 and base64; waveform artifacts preserve
raw and payload SHA-256 and leave the raw binary file to the caller.

## Verification commands

```bash
python3 -m unittest discover -s skills/gwinstek-gds2000a-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/gwinstek-gds2000a-control
```

The tests are offline. Nothing in the verification path opens a serial port,
enumerates VISA resources, or fetches a URL, so a passing run does not re-verify
hardware behavior.

## Known limitations and manual defects

- Hardware evidence covers one GDS-2104A, firmware V1.18, USB CDC-ACM, on one
  date. Do not extend it to another unit, firmware, model, or interface.
- Waveform code-to-volts conversion is not documented by this manual; every
  waveform is `code-domain-only`.
- The screen-image RLE decoder is not implemented.
- Actual `:SAVe:*` and `:HARDcopy:START` file writes were not exercised.
- Channel 2-4, the 1,000,000-point `:ACQuire1:LMEMory?` capture, and the
  optional DS2-LAN/DS2-GPIB/DS2-FGN/DS2-8LA/16LA features are unverified.
- The manual's List of Commands omits query `?` on most rows and omits channel/
  slot suffixes; hardware required the suffixed, query forms. The local list
  is also missing the Go_NoGo/Template block (TOC pp. 226-231), which is why
  those forms are in Appendix A rather than the 339-row denominator.
- The manual documents trigger states with a leading `*`; V1.18 returned
  `ARMED`, `AUTO`, `SAVE`, and `READY` without it.
- The manual documents `Chan Off`; V1.18 returned `Ch Off`.
- `:TIMebase:EXPand?` is documented for firmware V1.18 or above but returned
  `-221 Settings conflict` on the verified unit (Horizontal Expansion app not
  installed).
- `:TRIGger:FREQuency?` returned `2.000E+00` followed by two LFs; the extra LF
  is framing evidence, not a second response.
- The bundled scripts have no hardware evidence for Ethernet, GPIB, or
  RS-232C; their settings are documented only.
