---
name: gwinstek-gdm8352-control
description: Read-only control and documentation workflows for the GW Instek GDM-8352 5.5-digit dual-display digital multimeter over USB CDC-ACM. Use for identity and firmware checks, DC/AC voltage and current measurement queries, READ? two-display framing, beeper-state decoding, system-error text, IEEE 488.2 numeric preservation, and the safety rules for floating inputs, input ratings, and state-changing configuration commands.
---

# GW Instek GDM-8352 Control

Use this Skill for the GW Instek GDM-8352 dual-display digital multimeter over
its rear-panel USB device port. The implementation follows the official
*GDM-8352 User Manual*, GW Instek part no. `82DM-83520E01`; the local evidence
copy is `ref/gwinstek/GDM-8352_User_Manual_82DM-83520E01.pdf`. The command tables
are PDF pp. 99-106 and the command reference PDF pp. 107-141. All page numbers in
this Skill are **PDF physical pages**; the manual's printed folio is one higher.

Read-only monitoring is `hardware-verified` for one instrument: GDM-8352,
firmware `1.00`, serial `GEP848232`, USB CDC-ACM `2184:003b`,
`/dev/ttyACM0`, captured 2026-11-19. The shipped code refuses every setter,
including `CONF:*`, `SENS:*`, `*RST`, `*CLS`, calibration, display, trigger, and
beep commands. Only the read-only queries in
`scripts/gdm8352_protocol.py::QUERY_SPECS` can reach a port.

## Non-negotiable safety rules

**A DMM reading is only valid in the function and range that produced it. Before
sending any command that is not a plain `?` query, state which function, which
range, which input terminal, and what the reading will mean afterwards.**

- **The inputs are floating.** The COM terminal may sit up to **500 Vpk** above
  earth, and the instrument is rated **CAT II 600 V only** (manual PDF p. 6). Do
  not connect it to building installation, distribution, or mains circuits;
  the manual explicitly excludes measurement at power or building installation
  sites (PDF p. 6). Treat the input terminals as live until you have proved
  otherwise.
- **Respect the input ratings.** Voltage input must not exceed **DC 1000 V / AC
  750 V**; current input must not exceed **12 A**; COM-to-earth must not exceed
  **500 Vpk** (PDF p. 6). The 1 A and 10 A terminals are separate current paths.
  A range or terminal change does not make an over-range connection safe.
- **Function and range changes change the reading context.** `CONFigure:*`,
  `CONFigure2:*`, `SENSe:*`, and any `MEASure*?` form with a range parameter can
  switch function, range, input terminal, filter, or detector rate. A number
  captured after such a command is not comparable with the number before it.
  This Skill refuses range parameters and every `CONF`/`SENS` write.
- **`CONF:*` and `SENS:*` writes require explicit human confirmation.** They
  alter instrument state even when they return no data. Never send one as a
  probe, as "cleanup", or to see whether the instrument accepts it. The same
  applies to `CALCulate:*`, `TRIGger:*`, `SAMPle:*`, `DISPlay:*`, `DIGitalio:*`,
  `STATus:*`, and `SYSTem:*` writes.
- **Never send `*RST`, `*CLS`, or any calibration command.** `*RST` recalls the
  default panel setup (manual PDF p. 139), `*CLS` clears event registers (PDF
  p. 138), and the manual documents no calibration command that is safe to
  invoke remotely. All three classes are outside this Skill's scope.
- **`READ?` returns two display values, not one measurement.** The manual says
  "Returns 1st and 2nd display value" (PDF p. 130). The first field is the first
  display; the second field belongs to the second display. `READ?` conveys
  neither function nor unit for either field, and the manual does not document
  what the second display is measuring, so its function and unit stay
  `UNVERIFIED`. Never label the second field as a current, voltage, or "zero".
- **A `CONF?` timeout is not an instrument fault.** `CONF?` is not a manual
  command; the documented queries are `CONF:FUNC?`, `CONF:RANG?`, and
  `CONF:AUTO?` (PDF pp. 110-111). On the verified unit `CONF?` produced no bytes
  within the timeout. That means "invalid query", not "instrument dead" and not
  "empty answer". Use the documented query form.
- **Silence is never success.** A write may be accepted silently or ignored
  silently; the wire cannot distinguish them. Only a subsequent documented
  query can establish state, and only for the value that query reports.
- **Remote control is not an interlock.** A person at the front panel can change
  the function, range, or terminals while a session owns the port. A reading is
  a snapshot of shared state, not a claim about what the DMM is still doing.
- **Do not treat a number as calibration.** The captured readings are
  uncalibrated read-back from one instrument, not a calibration certificate.
  This Skill makes no accuracy, uncertainty, or traceability claim.

## Evidence and scope

- **Verified instrument**: GW Instek GDM-8352, serial `GEP848232`, firmware
  `1.00`, USB CDC-ACM `2184:003b`, host node `/dev/ttyACM0`, captured
  2026-11-19; the device was disconnected after capture and was not re-tested.
- **`hardware-verified` commands** (exactly these seven): `*IDN?`,
  `MEAS:VOLT:DC?`, `MEAS:CURR:DC?`, `READ?`, `SYST:BEEP:STAT?`,
  `SYST:BEEP:STAT OFF` (accepted with no response), and `SYST:ERR?` (only the
  fact that it returned the free text `Command error`). Every one of these
  carries the provenance sentence above. Raw bytes exist for the six queries in
  `assets/fixtures/`; `SYST:BEEP:STAT OFF` is recorded only in the hardware
  ground-truth log because a silent write produces no bytes.
- **`documented` only**: every `CONFigure`, `CONFigure2`, `SENSe`, `CALCulate`,
  `TRIGger`, `SAMPle`, `SYSTem`, `DISPlay`, `DIGitalio`, `STATus`, interface,
  IEEE 488.2 common command, and every measurement function other than DC
  voltage and DC current. That includes `MEAS:VOLT:AC?`, `MEAS:CURR:AC?`, the
  resistance, frequency, period, continuity, diode, capacitance, and temperature
  queries, and all second-display (`MEASure2`) forms.
- **`UNVERIFIED` semantics inside verified commands**: the second `READ?` field's
  function and unit; the unit of every response that carries no suffix (the unit
  is taken from the command); the temperature unit (`°C` or `°F`); the
  `CONF:RANG?` unit; and the return layout of `MEAS:PER?`, `MEAS:CONT?`,
  `MEAS:DIOD?`, and `MEAS:CAP?`, whose manual entries give no example response.
- **Manual version**: *GDM-8352 User Manual*, GW Instek part no.
  `82DM-83520E01`, Chinese edition, 157 PDF pages. The command syntax rules are
  PDF pp. 96-99, the command tables PDF pp. 99-106, and the command reference
  PDF pp. 107-141.
- **Transport evidence (host-side, not manual text)**: the verified unit
  enumerated as USB CDC-ACM with VID:PID `2184:003b`; `lsusb` describes the
  descriptor as `GW Instek GDM-8351`, a stale descriptor string. The manual only
  documents a rear-panel USB device port selectable as USB-CDC or USB-TMC (PDF
  pp. 91-92). The USB CDC interface ignores the host baud-rate setting: on the
  verified unit both 115200 and 9600 received correct responses. The code records
  115200 as a default because the field must hold a documented rate, not because
  the CDC link uses it.
- **Known evidence gaps**: no `CONFigure`, `SENSe`, `CALCulate`, `TRIGger`,
  `SAMPle`, `SYSTem` (other than beeper off), `DISPlay`, `DIGitalio`, `STATus`,
  interface, or IEEE 488.2 common command was exercised; no input source was
  attached for a cross-check; no function or range was deliberately changed
  during the verified session; and the device was not re-tested, so every
  capture is a single non-repeatable observation.
- **Synthetic fixtures** live under `assets/fixtures/synthetic/` and are
  deliberately bad responses used to prove failure handling. They are not
  hardware evidence and must never be presented as captures.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence for this command. |
| `hardware-verified` | A real instrument response was captured and checked for this exact command and firmware. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

These labels describe evidence, not feature count. This Skill is
`hardware-verified` for the seven commands listed above and `documented` for
everything else.

## Device boundary

- **Instrument**: GW Instek GDM-8352 5.5-digit dual-display DMM. DC voltage to
  1000 V, AC voltage to 750 V, AC/DC current to 10 A on the 10 A terminal, plus
  2-wire/4-wire resistance, frequency, period, continuity, diode, capacitance,
  and thermocouple temperature. The manual's specifications are on PDF
  pp. 143-149; none of those ranges is verified by this Skill.
- **Interface**: rear-panel USB device port, selectable as USB-CDC or USB-TMC
  (PDF pp. 91-92). The verified session used USB-CDC; no USB-TMC session was
  run.
- **Protocol**: SCPI 1994 and IEEE 488.2, partially compatible (PDF p. 96).
  Commands are case-insensitive; short and long forms are both accepted when
  complete (PDF p. 97).
- **Data kinds**: `identity`, `scalar-value`, `two-display-reading`,
  `beep-state`, `system-error`, `function-setting`, `range-setting`,
  `auto-range`, and `temperature-unit`.
- **Not supported by this Skill**: any command that changes function, range,
  input terminal, filter, detector rate, trigger, sample count, display, digital
  I/O, status registers, or local/remote state; calibration; firmware update;
  and `*RST`/`*CLS`.

## Task-specific reference table

| Goal | Reference |
|---|---|
| Choose USB-CDC vs USB-TMC, frame commands and responses, set a timeout, diagnose a timeout | [remote-session.md](references/remote-session.md) |
| Look up one command's syntax, parameters, return format, page, and evidence label | [command-reference.md](references/command-reference.md) |
| Understand the parser stages, IEEE 488.2 text preservation, `READ?` field separation, beeper texts, and fixture provenance | [response-and-evidence.md](references/response-and-evidence.md) |
| See the per-command evidence table and the deliberately unclaimed surface | [SUPPORT.md](SUPPORT.md) |

The command reference is an index of commands the manual documents. A row
labelled `documented` is **not** implemented as a builder: `build_query` accepts
only the read-only queries in `QUERY_SPECS` and raises `CommandRefused` for
everything else. A row labelled `hardware-verified` is still a read-only query,
not permission to change the instrument.

## Quick start (offline)

The instrument may be disconnected. These commands print the exact request
bytes without importing `pyserial` or opening a port:

```bash
cd scripts
python3 gdm8352_session.py --dry-run idn
python3 gdm8352_session.py --dry-run measure --function dc-voltage
python3 gdm8352_session.py --dry-run read
python3 gdm8352_session.py --dry-run raw 'SYST:BEEP:STAT?'
```

For a live session, open only the read-only queries:

```bash
python3 gdm8352_session.py --port /dev/ttyACM0 idn
python3 gdm8352_session.py --port /dev/ttyACM0 measure --function dc-voltage
```

A live run sends the query and parses the response; it does not switch function,
range, terminal, or display. If `*IDN?` does not identify a GDM-8352, stop and
do not interpret later readings as GDM-8352 data.

## Integrity statuses

- `COMPLETE`: framing and every required field agree with the stated claim.
- `INCOMPLETE`: a terminator, field, or value is missing.
- `INVALID`: the bytes contradict a framing, numeric, unit, or identity rule.
- `UNVERIFIED`: parsing succeeded but a semantic or completeness claim cannot be
  proven (second `READ?` display, unitless response, return layout).
- `UNSUPPORTED`: the query or response shape is not implemented.

Never pad, truncate, clamp, interpolate, guess a missing calibration, or merge a
failed/retried read into a complete result.
