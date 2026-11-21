---
name: rigol-ds1000z-control
description: Control and document workflows for a RIGOL DS1000Z series digital storage oscilloscope (evidence captured on a DS1074Z, firmware 00.04.02.SP4) over a raw TCP socket with one-command-per-write LF framing. Use for identity and session setup, channel/timebase/trigger configuration, run/stop acquisition, screen and deep-memory waveform download with preamble handling and offline validation, individual measurements, error-queue handling, and BMP screenshot capture. Support level is firmware-scoped; waveform voltage calibration is not verified.
---

# RIGOL DS1000Z Control

Use this Skill for the RIGOL DS1000Z series digital storage oscilloscope: DS1054Z
(4-channel, 50 MHz), DS1074Z / DS1074Z-S / DS1074Z Plus (4-channel, 70 MHz),
DS1104Z / DS1104Z-S / DS1104Z Plus (4-channel, 100 MHz), and the `-S` variants
with a built-in signal source. Commands follow the *MSO1000Z/DS1000Z Programming
Guide*, PGA19108-1110, Software Version 00.04.03.SP2, December
2015; the operator-facing behavior is described in the *DS1000Z Series User
Guide*, UGA19115-1110, September 2020. Page numbers below are PDF physical pages
of the local text extracts, not the printed chapter-page labels.

All hardware evidence in this Skill was captured from one instrument:

```text
*IDN? -> RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4
```

That is a 4-channel 70 MHz model running firmware `00.04.02.SP4`, reached over a
raw TCP socket on port 5555. The operator described the unit as a "DS1104"; the
recorded identity is the authority and stays `DS1074Z`.

The manual's software version (`00.04.03.SP2`) is **newer** than the tested
firmware (`00.04.02.SP4`). Anything that depends on that difference is labelled
`documented`, never `hardware-verified`.

## Purpose

Give a maintainer one place to answer: how to reach a DS1000Z, which framing
rules the instrument actually enforces, how to bring back a screenshot or a
waveform without corrupting it, and which claims in this Skill rest on a real
response versus a manual paragraph.

## Non-negotiable safety rules

- Confirm probe rating and input category before connecting anything. The User
  Guide states the oscilloscope may be used only in **Measurement Category I**
  (PDF page 10) and that the mains input is installation (overvoltage) category
  II (PDF page 12). It gives no numeric input impedance and no numeric maximum
  input voltage; those live in the *DS1000Z Series Datasheet* and on the front
  panel, so this Skill does not state them.
- The instrument is earth-referenced through the protective earth of the power
  cord (User Guide PDF page 4). The probe ground lead must go to earth ground:
  "Do not connect the ground lead to high voltage" (PDF page 4). Never float the
  scope and never clip the ground lead to a live potential; use a correctly
  CAT-rated differential probe for floating or mains-referenced work.
- Obey "Observe All Terminal Ratings" (User Guide PDF page 4). Do not exceed the
  probe or channel rating at the selected attenuation.
- Compensate the probe before quantitative work (User Guide PDF pages 31-32).
  An uncompensated probe distorts amplitude and edge measurements; the probe
  compensation terminal is for adjustment only and "cannot be used for
  calibration" (PDF page 31).
- Do not assume an input, trigger, or saved state is safe. Read channel
  display/coupling/scale/probe ratio and the trigger state before arming.
- Do not send `*RST`, `*SAV`, `*RCL`, `:SAVE`, `:RECAll`, or any writing
  `:LAN:` command as routine cleanup. They change operator state, files, or
  network reachability. `scripts/ds1000z_session.py` refuses them
  unconditionally.
- Do not overwrite local output files. The session helper refuses an existing
  path unless `--overwrite` is explicit.
- Waveform voltages are **not calibrated** by this Skill. Preserve raw codes and
  treat reconstructed volts as `UNVERIFIED`; only the shape, relative level, and
  code statistics are supported claims.
- A numeric response is not proof that the acquisition, trigger, or probe setup
  was valid. Keep the configuration context with the data.
- One command per write. Sending several commands in a single write silently
  discards all but the first (`hardware-verified`).

## Evidence and scope

- **Support level**: `firmware-scoped`. Model `DS1074Z`, firmware
  `00.04.02.SP4`, interface raw TCP 5555, captured 2026-11-20.
- **Manual (commands)**: *MSO1000Z/DS1000Z Programming Guide*,
  Software Version 00.04.03.SP2, Dec 2015. Common commands PDF pp. 95-97;
  acquisition PDF pp. 20-23; vertical PDF pp. 25-31; display PDF pp. 78-82;
  measurements PDF pp. 128-141; reference/store PDF pp. 142-159; system
  PDF pp. 160-168; timebase PDF pp. 169-173; trigger PDF pp. 174-231;
  waveform PDF pp. 232-242; block/preamble detail PDF p. 242.
- **Manual (operation)**: *DS1000Z Series User Guide*, Sep 2020. Model table
  PDF p. 18; safety summary PDF pp. 4-5; measurement category PDF p. 10;
  ventilation/environment PDF pp. 11-12; probe connection and compensation
  PDF pp. 29-32; vertical scale range PDF p. 54; LAN configuration PDF p. 236;
  remote control via LAN PDF p. 252.
- **Interface note**: the Programming Guide documents USB-TMC and VXI-11 based
  LAN control (PDF pp. 12, 14) and contains **no `:LAN:` subsystem**: `grep -c
  ":LAN"` over the extracted manual returns 7 hits, all of them
  `:SYSTem:LANGuage` (PDF pp. 160-161). Raw TCP port 5555 is therefore
  `hardware-verified`, not `documented`.
- **Evidence file**: `artifacts/rigol-ds1000z/hardware-evidence.md`, with raw
  captures and SHA-256 values in `artifacts/rigol-ds1000z/raw/`.
- **Evidence gaps**: MAXimum-mode byte semantics on other firmware, VXI-11 RPC
  path (UDP portmapper only answered; TCP 111 did not), `:ACQuire:TYPE AVER` /
  `HRES` waveform downloads, digital channels (MSO models), the `-S` signal
  source, and any voltage calibration.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

Labels describe evidence, not feature count. This Skill is `firmware-scoped` for
the DS1074Z at `00.04.02.SP4`, and `documented` for everything that only the
manual supports.

## Device boundary

- **Models**: DS1054Z, DS1074Z, DS1104Z and their `-S` / `Plus` variants. All are
  analog 4-channel; MSO1000Z models add digital channels and use the same
  command set, but this Skill does not cover digital channels.
- **Interfaces observed**: raw TCP socket on port **5555** (answered `*IDN?`),
  UDP portmapper 111 answering VXI-11 `GETPORT` with TCP 617, HTTP port 80 open,
  TCP 5025 **closed** (`hardware-verified`).
- **Interfaces documented**: USB Device (USB-TMC) and LAN/VXI-11 (Programming
  Guide PDF pp. 12, 14; User Guide PDF pp. 236, 252). The panel's VISA address
  field read `TCPIP0::10.99.0.194::INSTR` (`hardware-verified`).
- **Language**: SCPI / IEEE 488.2 subset with Rigol extensions. Responses are
  terminated by LF only; there is no CR (`hardware-verified`).
- **Primary data kinds**: `identity` (`*IDN?`, `*SYSTem:MODEL?`),
  `scalar-measurement` (`:MEASure:*?`), `status-record`
  (`:SYSTem:ERRor?`), `waveform` (`:WAVeform:PREamble?` + `:WAVeform:DATA?`),
  `screenshot` (`:DISPlay:DATA?`), and `cursor-readout` (`:CURSor:<family>:*?`).
- **Not automatic**: calibration, firmware update, probe compensation,
  autoscale, panel lock/unlock, destructive reset, LAN reconfiguration.
- **Firmware gaps**: `*OPT?`, `:SYSTem:SETup?`, `:SYSTem:KEY?`,
  `:SYSTem:KEY:LOCK?`, `:SYSTem:Expansion?`, `:INFO:MODEL?`,
  `:CHANnel1:POSition?`, `:WAVeform:WIDTh?`, `:DISPlay:BRIGhtness?` all return
  `command error` on `00.04.02.SP4` although several are in the manual
  (`hardware-verified`; see [command-reference.md](references/command-reference.md)).

## Task-specific reference table

| Goal | Reference |
|---|---|
| Models, probes, input category, grounding, probe compensation, environment | [bench-setup.md](references/bench-setup.md) |
| TCP 5555 session, terminators, framing rules, identity, error queue, status | [remote-session.md](references/remote-session.md) |
| Channel, timebase, and trigger configuration and the measured constraints | [vertical-timebase-trigger.md](references/vertical-timebase-trigger.md) |
| Run/stop, memory depth, preamble, deep-memory download, block format | [capture-and-waveform.md](references/capture-and-waveform.md) |
| Individual measurements, the `9.9E37` sentinel, rejected measurement items | [measurements.md](references/measurements.md) |
| Cursor modes, cursor query families, the three sentinel outcomes, mode-switch latency | [cursors.md](references/cursors.md) |
| Screenshot capture, image format defects, storage/recall command families | [save-and-screenshot.md](references/save-and-screenshot.md) |
| Parser stages, statuses, raw evidence, preamble-to-volts caveat | [response-and-evidence.md](references/response-and-evidence.md) |
| Cross-check a command across subsystems, or answer a command question no task reference covers | [command-reference.md](references/command-reference.md) |

Load only the reference matching the current task. The command index is a
fallback, not a starting point: open it only when the task reference and the
scripts cannot answer the command question. Anything absent from it must be
verified against the Programming Guide and labelled `documented` before use, and
the safety rules above still apply. On `00.04.02.SP4` a documented command can
still answer `command error`; check the error queue instead of assuming the
manual is right.

## Standard remote session

1. Open the raw TCP socket (`--host`, `--port 5555`, explicit timeout). Nothing
   is sent until the socket is connected.
2. Send `*IDN?` as a single write, terminated with LF. Preserve the raw bytes and
   validate `RIGOL TECHNOLOGIES,DS1<...>,<serial>,<firmware>`. Expected on the
   evidence unit: `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4`.
3. Gate by model: 4 analog channels, no digital channels unless MSO. Do not
   assume `:LAN:` queries exist outside the tested firmware; they are
   undocumented in the Programming Guide.
4. Read current state before changing it: `:TRIGger:STATus?`,
   `:TIMebase:MAIN:SCALe?`, and per channel `:CHANnel<n>:DISPlay?`,
   `:SCALe?`, `:OFFSet?`, `:COUPling?`, `:PROBe?`.
5. Drain `:SYSTem:ERRor?` until `0,"No error"`.
6. Configure channel, timebase, and trigger.
7. Acquire (`:RUN` or `:SINGle`), poll `:TRIGger:STATus?`, `:STOP` before a RAW
   or MAXimum download.
8. Drain the error queue again after the operation.

Query pairing: **one command per write, one response per query, read before the
next write** (`hardware-verified`). Three queries in one `sendall` produced one
answer; the other two were dropped. Writes (`:STOP`, `:WAVeform:MODE RAW`, …)
return nothing, so leave ~0.3-0.4 s before the next command on the same socket.

An undefined command header returns the literal ASCII `command error`
(13 bytes, **no terminator**) and queues `-113,"Undefined header; ..."`. A reader
that waits for LF hangs until its idle timeout, so the session helper falls back
to an idle-timeout read and reports the frame as unterminated rather than
inventing a line.

## Capture and waveform workflow

1. Confirm probe, channel display, coupling, scale, probe ratio, and trigger
   source. A waveform block is returned even for a channel that is **not
   displayed** with a nonsense increment, so the block alone proves nothing
   (`hardware-verified`).
2. For screen-rate data use `:WAVeform:MODE NORM` (1200 points typical). For deep
   memory: set `:ACQuire:MDEPth` while the acquisition is running, let it
   acquire, then `:STOP`, then `:WAVeform:MODE RAW`. Writing the memory depth
   while stopped fails with `-200,"Execution error"`.
3. Set the window explicitly: `:WAVeform:STARt` / `:WAVeform:STOP`. A RAW window
   write made while the acquisition runs is rejected with `-220,"Parameter
   error"` (observed with `:WAVeform:STOP 100000`), and the window silently keeps
   its old value, so read `:WAVeform:POINts?` back instead of trusting the
   write.
4. Read `:WAVeform:PREamble?` (10 comma-separated fields: format, type/mode,
   points, count, xincrement, xorigin, xreference, yincrement, yorigin,
   yreference) and cross-check `points` against `STOP - STARt + 1` and against
   the mode. Field 2 is `0` in NORM, `1` in MAXimum, `2` in RAW
   (NORM and RAW `hardware-verified`, MAXimum observed at field value `1`).
5. Read `:WAVeform:DATA?` as a `#9` + nine ASCII length digits + payload + LF
   block. NORM 1200 points arrived as 1212 bytes total; RAW 4000 points as 4012
   bytes; RAW 240 000 points took 638 ms (`hardware-verified`).
6. Save the raw bytes first (session helper writes bytes plus SHA-256), then
   parse. Report point count, declared versus observed length, both SHA-256
   values, and the calibration status.
7. Never reuse a NORM `yincrement` for RAW bytes: 0.5 V/div gave 0.02 in NORM and
   0.0209375 in RAW (`hardware-verified`). Reconstruct volts as
   `(code - yorigin - yreference) * yincrement` and mark the result `UNVERIFIED`,
   because calibration is not proven even when the formula reproduces
   `:MEASure:VPP?` on the same screen.

## Measurement workflow

- `:MEASure:SOURce CHANnel<n>` selects the source. Query individual items such
  as `:MEASure:VPP?` or `:MEASure:FREQuency?`; responses are NR3
  (`hardware-verified`).
- `9.9E37` means "no result" and is **never** a number. With the source channel
  not displayed, `:MEASure:VPP?` and `:MEASure:FREQuency?` both returned
  `9.9E37` (`hardware-verified`). Map it to `INCOMPLETE`, not to zero.
- `:MEASure:ITEM? <item>` works for `VPP` and `FREQuency` and returns the bare
  NR3 value with no item-name prefix. Select the channel with
  `:MEASure:SOURce` instead of appending it to the item: the source-qualified
  form `:MEASure:ITEM? VPP,CHANnel2` returned `9.9E37`, not a value
  (`hardware-verified`).
- The following documented families answered `command error` on
  `00.04.02.SP4` and must not be assumed present: `:MEASure:VAVerage?`,
  `RISetime?`, `FALLtime?`, `+DUTy?`, `-DUTy?`, `+PULses?`, `-PULses?`,
  `+EDGes?`, `-EDGes?`, `PHASe?`, `COUNter?`, `:MEASure:STATistic:ITEM?`
  (`hardware-verified`).
- Record the acquisition context (timebase, vertical scale, probe ratio,
  coupling, trigger source/level) with every value: the instrument will happily
  measure a wrong setup.

## Screenshot workflow

- `:DISPlay:DATA?` returns `#9` + declared length + an 800×480 24-bit BMP, plus
  **three extra bytes (`;0\n`) past the declared length**: 1 152 054 declared,
  1 152 068 observed (`hardware-verified`). Trim to the declared length before
  writing the file, or `file(1)` rejects the stream.
- Latency is 2.2-6.2 s per capture (`hardware-verified`); set the read timeout
  accordingly and never re-send the query on a slow read.
- Accepted arguments on `00.04.02.SP4`: bare, `ON`, `OFF`, `ON,OFF`, `ON,ON`
  (colour/mono and inverted variants, distinct payload hashes). Rejected with
  `-220,"Parameter error"`: any third format argument, including
  `ON,OFF,BMP`, `OFF,OFF,PNG`, `OFF,OFF,JPEG`. Image format is fixed BMP on this
  firmware; `:STORage:IMAGe:TYPE` affects file saves, not `:DISPlay:DATA?`.
- The scripts write to a new path only unless `--overwrite` is given, and report
  the exact path plus SHA-256.

## Offline parser and builders

`scripts/ds1000z_protocol.py` is transport-independent and standard-library only:

```text
python3 scripts/ds1000z_protocol.py identity assets/fixtures/identity.txt
python3 scripts/ds1000z_protocol.py error-queue assets/fixtures/error-queue-undefined.txt --response-type error-queue
python3 scripts/ds1000z_protocol.py measurement assets/fixtures/measurement-vpp.txt --quantity vpp
python3 scripts/ds1000z_protocol.py preamble assets/fixtures/preamble-norm.txt
python3 scripts/ds1000z_protocol.py waveform assets/fixtures/waveform-norm-ch1.bin --csv-out wave.csv
# Live session can also export a portable waveform-bundle/v1 alongside raw bytes:
# python3 scripts/ds1000z_session.py --host <ip> waveform --channel 1 --out ch1.bin --bundle-out ch1.bundle.json
python3 scripts/ds1000z_protocol.py screenshot assets/fixtures/screenshot-compact.bin --out screen.bmp
python3 scripts/ds1000z_protocol.py block assets/fixtures/waveform-norm-block.bin
python3 scripts/ds1000z_protocol.py cursor assets/fixtures/cursor-manual-values.txt --mode MAN
```

Stages: `read_frame` -> `parse_metadata` -> `extract_payload` -> `normalize` ->
`validate`. Waveform stages: `parse_preamble` -> `parse_ieee_block` /
`parse_block` -> `normalize_waveform` -> `validate`, with `iter_codes`,
`sample_voltage`, `waveform_to_csv`, and `export_waveform_bundle` (`waveform-bundle/v1`) for the per-point and portable-bundle views. Intermediate
results stay inspectable.

`scripts/ds1000z_session.py` is the live transport (standard-library `socket`,
lazy import): `--host --port 5555 --timeout`, `--dry-run` prints the exact bytes
and opens nothing, writes require `--allow-writes`, raw bytes and their SHA-256
are always saved, and it refuses `*RST`, `*SAV`, `*RCL`, `:SAVE`, `:RECAll`, and
every writing `:LAN:` command unconditionally. `cursor` reads one cursor-readout
report for the mode the instrument is already in; `cursor --mode TRACk` needs
`--allow-writes`, waits for the slow mode switch, and restores the previous mode
with the observed before/after values in `mode_restore`.

## Integrity statuses

- `COMPLETE`: every applicable **structural and count** check passes for the stated claim (framing, required fields, point/row counts, terminator); it never means the data is correct, covers what the caller wanted, or is within calibration.
- `INCOMPLETE`: a required byte, terminator, field, point, segment, or status element is missing.
- `INVALID`: framing, counts, or type constraints contradict the observed bytes.
- `UNVERIFIED`: parsing found no contradiction, but the available evidence cannot prove completeness, units, calibration, or acquisition state.
- `UNSUPPORTED`: this Skill does not implement that response shape or feature.

A structural status never stands in for a different claim: **bytes complete**,
**scale usable**, **same frame**, and **the number is a physical level** are four
separate conclusions. Where an artifact reports one of them, it names it.

Never silently pad, truncate, clamp, interpolate, or guess. Line responses keep
the raw bytes as SHA-256 (and note whether the frame carried a terminator);
waveform and screenshot artifacts keep declared and observed lengths plus both
SHA-256 values and leave the raw binary to the caller.

## Verification commands

```bash
python3 -m unittest discover -s skills/rigol-ds1000z-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/rigol-ds1000z-control
npx skills@latest add . --list
```

The unit tests are offline. Nothing in the repository's verification path opens a
socket, so a passing run does not re-verify hardware behavior.

## Known limitations / manual defects

- **No `:LAN:` subsystem in the Programming Guide.** `:LAN:DHCP?`,
  `:LAN:IPADdress?`, `:LAN:SMASk?`, `:LAN:GATeway?`, `:LAN:MAC?`,
  `:LAN:STATus?`, `:LAN:MANual?` answered on the evidence unit
  (`hardware-verified`) but appear nowhere in the manual (`grep` shows only
  `:SYSTem:LANGuage`). Their names are therefore `UNVERIFIED` against any manual,
  and their write forms are dangerous: a wrong static address can make the scope
  unreachable. The scripts refuse them.
- `:LAN:MANual?` returned `1` while DHCP was on, so that flag cannot be read as
  "static addressing is active".
- **No `*SAV` / `*RCL`, no `:SAVE` / `:RECAll`** in the Programming Guide. Setup
  and file storage live under `:SYSTem:SETup` (PDF p. 163), `:STORage:*`
  (PDF p. 158), and `:REFerence<n>:SAVe` (PDF p. 145). An IEEE 488.2-style
  `*SAV` / `*RCL` pair is therefore not documented for this series; the scripts
  reject it defensively and the firmware behavior stays untested.
- **Firmware below the manual**: the manual describes 00.04.03.SP2, the evidence
  unit runs 00.04.02.SP4. Several documented queries answer `command error`
  (list above and in [command-reference.md](references/command-reference.md)).
- **Cursor reads have three outcomes, not two.** A cursor reading is a number,
  `9.9E37` (no result) or `4294967295` (uint32 −1: the cursor position is not
  set, seen on `:CURSor:TRACk:AY?`/`BY?`). Both non-numeric outcomes arrive as
  `value`/`position` `null` with a reason, never as a number
  (`hardware-verified`). Every `:CURSor` family answers in every mode, so the
  readout follows `:CURSor:MODE?`; a y-axis value's unit is the channel's own
  unit (`VUNit` = `SOUR`) and is left `null` rather than assumed to be volts.
  `:CURSor:MODE XY` was refused with `-200,"Execution error"` on this firmware,
  and the mode write is silent but slower than a normal command: allow ≥0.8 s
  before the next query or the reply lands on the wrong command.
- **`9.9E37` is a sentinel, not a measurement.** Any pipeline that parses with a
  float cast silently produces a 9.9e37 reading.
- **Preamble can contradict the mode.** Leaving `STOP = 240001` and switching to
  NORM made `:WAVeform:POINts?` and the preamble report 240 001 points with a
  2 µs increment for a 1200-point screen capture (`hardware-verified`). Always
  set the window and cross-check.
- **`:ACQuire:MDEPth` is only writable while running.** Accepted as bare numbers
  (`12000`, `120000`, `1200000`) with `:TRIGger:STATus?` = `TD`; rejected with
  `-200,"Execution error"` when stopped. Suffixed forms (`12K`, `1.2M`, `24M`)
  and `DEFAULT` fail with `-220,"Parameter error"`; bare `AUTO` is always
  accepted (`hardware-verified`).
- **`:DISPlay:DATA?` framing defect**: three bytes past the declared length.
  Trimming is mandatory, and the trailing bytes should be preserved in the raw
  capture so the defect stays auditable.
- **Error queue depth is 16** and overflow reports `-350,"Queue overflow"`;
  `0,"No error"` is the terminator record, one entry per query
  (`hardware-verified`).
- **Voltage calibration is not verified** for either mode, and the NORM/RAW
  increments differ for the same V/div.
- VXI-11 was only probed through the UDP portmapper; the RPC path itself is
  `UNVERIFIED`, and the scripts use raw TCP 5555 instead.
- Digital channels (MSO models), the `-S` signal source, pass/fail, and other
  advanced subsystems are outside this Skill.
