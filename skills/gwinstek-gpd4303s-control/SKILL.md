---
name: gwinstek-gpd4303s-control
description: Control and document read-only monitoring workflows for a GW Instek GPD-4303S multi-channel DC power supply over its FTDI USB serial port at 9600 8N1. Use for identity and firmware checks, STATUS? register decoding (CC/CV, tracking mode, beep, output, baud), VSET/ISET setpoint readback, VOUT/IOUT output readback, HELP? command-list capture, response framing, and the safety rules that keep a probing command from energising a load.
---

# GW Instek GPD-4303S Control

Use this Skill for the GW Instek GPD-4303S DC power supply (CH1/CH2 0-30 V /
0-3 A independent, 0-60 V series, 0-6 A parallel; CH3 and CH4 auxiliary outputs)
over its rear-panel USB slave port. The implementation is based on the official
*GPD-X303S Series User Manual* (GW Instek part no. `82PD-433S0MC1`), local
evidence copy `ref/gwinstek/GPD-X303S_User_Manual_82PD-433S0MC1.pdf`; the remote
control chapter is PDF pp. 43-52 and the command reference pp. 46-52.

Read-only monitoring is `hardware-verified` for one instrument: GPD-4303S,
firmware `V2.08`, `/dev/ttyUSB0` at **9600 8N1**, 2026-11-19. Every command that
changes the output, a setpoint, the tracking mode, the memories, the baud rate,
or the remote/local state remains `documented` only.

## Non-negotiable safety rules

**Any probing send may energise the output. Before sending a command that is not
a plain `?` query, state the worst case out loud: which channel, which voltage,
which current limit, and what the load does when 24 V appears.**

The GPD makes this rule sharper than usual:

- `OUT<Boolean>` has **no channel parameter** (manual p. 50). The front-panel
  Output key switches *all* channel outputs at once (manual p. 25), and the
  observed `OUT0` returned every channel to `0.000V`.
- `OUT1` is **not** a toggle: the manual defines it as "Turns on the output", and
  on the verified unit repeating `OUT1` did not change the state. `OUT1?` does
  not exist and answers `Invalid Character.`, so the enable command cannot be
  undone by repeating it or by querying it. `OUT0` is the only observed way to
  turn the output off. This is probe-derived experience, not a manual statement.
- `TRACK<NR1>` changes the output topology: `1` series doubles the voltage
  (0-60 V), `2` parallel doubles the current (0-6 A) (manual pp. 33, 39, 55).
  It also turns the output off automatically (manual p. 25).
- **A `STATUS?` tracking decode is not panel confirmation.** Under the default
  `lsb-first` decode the observed `00110010` reads `tracking_code=11`, which the
  manual maps to series tracking (0-60 V); that is consistent with
  `VSET1? = VSET2? = 24.000V`. If `STATUS?` reports series or parallel tracking,
  the assumption that CH1 and CH2 are independent fails: confirm the mode at the
  front and rear panel before relying on independent-channel behaviour. This
  decode has not been confirmed on the panel.
- `SAV<NR1>` and `RCL<NR1>` turn the output off automatically and always store
  and recall output on/off, panel lock, and beep as **off** (manual pp. 41-42).
  A recall silently de-energises the outputs and unlocks the panel.
- `LOCAL` and `REMOTE` (manual pp. 48, 51) change who is allowed to touch the
  front panel, not whether the outputs are live.
- Remote mode is **not** an interlock: for safety reasons the front-panel Output
  key is not affected by the panel key lock (manual p. 53, A1).
- `BAUD<NR1>` changes the link rate live (`0` 115200, `1` 57600, `2` 9600;
  default 9600, manual p. 51). Sending it ends the session you sent it from.
- Commands must be 15 characters or fewer (manual p. 46). The verified unit
  answers any command it does not know with `Invalid Character.`; long SCPI
  forms such as `SYST:ERR?`, `*OPT?`, or `OUTPUT1 0` are rejected.
- A numeric response is not a calibration certificate. Program and read-back
  accuracy are ±(0.03 % of reading + 10 mV) and ±(0.3 % of reading + 10 mA), and
  meter resolution is 1 mV / 1 mA (manual pp. 55-56). A `0.000V` read-back does
  not prove that the terminals are de-energised.
- Do not run a state-changing command to "see what happens". Every write in this
  Skill is documented but unexercised, so its side effects on your unit are
  unverified.

## Evidence and scope

- **Verified instrument**: GW Instek GPD-4303S, serial `EP924162`, firmware
  `V2.08`, `/dev/ttyUSB0`, 9600 8N1, no flow control, captured 2026-11-19. A
  second read-only session later the same day (`verify_all`, 11:38:50Z)
  re-queried the same unit; its evidence is archived locally under
  `artifacts/verification/evidence/20261119T113850Z/` (git-ignored, local
  reference only). The output-on readings were not re-created, because
  re-energising the output is out of scope.
- **`hardware-verified` (read-only queries only)**: `*IDN?`, `STATUS?`, `HELP?`,
  and `VSET<X>?` / `ISET<X>?` / `VOUT<X>?` / `IOUT<X>?` **on CH1-CH4**. The
  captured bytes live in `assets/fixtures/captures/` with byte-level provenance,
  including `006-VSET3.raw` through `013-IOUT4.raw`; `HELP?` is indexed there as
  `help-transcribed.raw` because it was reconstructed from the recorded console
  transcript rather than written by the capture tool.
- **`documented` only**: `ISET<X>:<NR2>`, `VSET<X>:<NR2>`, `TRACK<NR1>`,
  `BEEP<Boolean>`, `OUT<Boolean>`, `RCL<NR1>`, `SAV<NR1>`, `BAUD<NR1>`,
  `LOCAL`, `REMOTE`, `ERR?`, and every error message except
  `Invalid Character.`.
- **Probe-derived observations, not manual claims** (recorded because they change
  the safety analysis, not because they are documented): `OUT1` is idempotent and
  there is no `OUT1?`; `OUT0` is the only observed off command; `OUT2` does not
  exist; `BEEP?` does not exist; the device replies `Invalid Character.` (capital
  `C`, trailing period) where manual p. 46 prints `Invalid character`.
- **Capture status**: the responses above were collected on 2026-11-19 from one
  GPD-4303S at firmware `V2.08` and re-queried later the same day; the write
  commands remain unverified.
- **`UNVERIFIED`**: the transmission order of the eight `STATUS?` characters.
  The manual defines the bit meanings but not their order. The `lsb-first`
  default is corroborated, but not proven, by two same-session observations:
  `00110010` decodes to `baud_code=10` -> 9600 bps, the rate the link actually
  used, and to `output=off`, matching `VOUT1?`-`VOUT4?` all reading `0.000V`.
  See [response-and-evidence.md](references/response-and-evidence.md).
- **External evidence (not manual text)**: the USB descriptor `0403:6001`
  ("Future Technology Devices International, Ltd FT232 Serial (UART) IC") was
  read with `lsusb`; the manual only says "USB slave port, rear panel".

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

These labels describe evidence, not feature count. This Skill is
`hardware-verified` for read-only monitoring and `documented` for control.

## Device boundary

- **Instrument**: GW Instek GPD-4303S. CH1/CH2 independent 0-30 V / 0-3 A,
  series 0-60 V / 0-3 A, parallel 0-30 V / 0-6 A; CH3 0-5 V / 0-3 A or
  5.001-10 V / 0-1 A; CH4 0-5 V / 0-1 A (manual p. 55).
- **Interface**: USB slave port on the rear panel only; FTDI bridge presenting a
  serial COM port. No LAN, GPIB, or RS-232.
- **Language**: the manual's own command set, not full SCPI. Commands are
  case-insensitive (manual p. 46; confirmed on hardware with `vout1?` and
  `Status?`).
- **Primary data kinds**: `scalar-value` (VSET/ISET setpoints and VOUT/IOUT
  read-back), `status-record` (`STATUS?`), `identity` (`*IDN?`),
  `command-list` (`HELP?`), `error-message` (the six messages of manual pp. 46-47).
- **Not automatic**: calibration, fuse replacement, firmware update, panel
  save/recall, baud changes, and any output on/off action.

## Task-specific reference table

| Goal | Reference |
|---|---|
| Open a session, set 9600 8N1, enter/leave remote mode, frame responses | [remote-session.md](references/remote-session.md) |
| Look up one command's syntax, range, return format, page, and evidence label | [command-reference.md](references/command-reference.md) |
| Understand the parser stages, `STATUS?` bit order, provenance, limitations | [response-and-evidence.md](references/response-and-evidence.md) |

The command reference is an index of the commands this Skill records, not a
substitute for the manual; anything absent must be verified against
*GPD-X303S Series User Manual* pp. 46-52 and labelled `documented` before use.

## Standard remote session

One session, one query, one response. Do not send a second query while an
earlier response is unread.

1. Confirm the load and the setpoints before opening the port; `VSET1?`,
   `VSET2?`, and `STATUS?` can show 24 V / 1 A programming on a 3 A supply.
2. Open `/dev/ttyUSB0` at **9600 8N1**, no flow control (manual p. 43;
   115200 did not work on the verified unit).
3. Send `*IDN?` and preserve the raw bytes; require
   `GW INSTEK,<model>,SN:<serial>,V<major>.<minor>`.
4. Send the read-only queries the task needs: `STATUS?`, `VSET<X>?`, `ISET<X>?`,
   `VOUT<X>?`, `IOUT<X>?`, `HELP?`.
5. Check `STATUS?` before touching a load: the output bit, the CC/CV bits, and
   the tracking bits describe the state the panel would show.
6. Never send a write command to "reset" or "clean up"; the correct cleanup is
   leaving the instrument exactly as found and telling the operator what it is.

## Offline parser and builders

`scripts/gpd4303s_protocol.py` is transport-independent and stdlib only:

```bash
python3 scripts/gpd4303s_protocol.py identity assets/fixtures/idn.txt
python3 scripts/gpd4303s_protocol.py reading assets/fixtures/vout1-on.txt --query VOUT1?
python3 scripts/gpd4303s_protocol.py status assets/fixtures/status-output-off.txt
python3 scripts/gpd4303s_protocol.py status assets/fixtures/status-output-off.txt --bit-order msb-first
python3 scripts/gpd4303s_protocol.py error assets/fixtures/invalid-character.txt
python3 scripts/gpd4303s_protocol.py help assets/fixtures/help-list.txt
python3 scripts/gpd4303s_protocol.py classify 'VSET1:24.000'
```

Stages: `read_frame`/`read_multiline_frame` (framing) -> `parse_metadata`
(token classification) -> `extract_payload` (raw fields) -> `normalize` (unit
check, identity check, status decode) -> `validate` (integrity block and raw
SHA-256/base64). `parse_identity`, `parse_reading`, `parse_status`,
`parse_error_message`, `parse_command_list`, and `parse_response` compose them.

`classify_command` recognises every documented form and reports the manual page,
the evidence level, whether the command changes instrument state, the channel,
the parameter, and any syntax or range problem. `build_query` is the only
function that produces wire bytes, and it accepts **only** documented read-only
queries, so no code path in this Skill can construct `OUT1`.

## Optional live transport

`scripts/gpd4303s_session.py` imports `pyserial` lazily and supports `--dry-run`,
which prints the exact bytes without opening a port. It sends only
`*IDN?`, `STATUS?`, `VSET<X>?`, `ISET<X>?`, `VOUT<X>?`, `IOUT<X>?`, and `HELP?`;
every other command is refused locally before a byte reaches the port, including
the documented `ERR?` (read-only, but outside the exercised set).

```bash
python3 scripts/gpd4303s_session.py --dry-run read --channels 1,2
python3 scripts/gpd4303s_session.py --port /dev/ttyUSB0 idn
python3 scripts/gpd4303s_session.py --port /dev/ttyUSB0 status
python3 scripts/gpd4303s_session.py --port /dev/ttyUSB0 settings --channels 1,2
python3 scripts/gpd4303s_session.py --port /dev/ttyUSB0 read --channels 1,2
```

`--capture-dir DIR` writes every response byte-for-byte as `<run>-<n>-<cmd>.raw`
plus a JSONL index with command, request bytes, response bytes, SHA-256, and
timestamp. That is how the fixtures in `assets/fixtures/` were produced.

Exit codes: `0` parsed, `1` an integrity failure (`INVALID`/`INCOMPLETE`/
`UNSUPPORTED`), `2` refused command, transport, or usage error.

## Integrity statuses

- `COMPLETE`: framing, required fields, and the unit/quantity agreement hold for
  the stated claim.
- `INCOMPLETE`: a terminator, field, or unit is missing, so the value cannot be
  attributed.
- `INVALID`: framing, numeric, unit, or identity constraints contradict the raw
  bytes.
- `UNVERIFIED`: parsing succeeded, but completeness or semantics (the `STATUS?`
  bit order, sequential V/I reads, uncalibrated read-back) cannot be proven.
- `UNSUPPORTED`: the response shape or message is not one this Skill implements.

Never silently pad, truncate, clamp, interpolate, or guess. A parsed value is
not proof of a calibrated output or of a de-energised terminal.

## Verification commands

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/gwinstek-gpd4303s-control
cd skills/gwinstek-gpd4303s-control/scripts && python3 -m unittest -v
```

## Known limitations / manual defects

- Every write command is `documented` only; no output, setpoint, tracking,
  memory, baud, or remote/local command was exercised, by design.
- The `STATUS?` character order is not documented; the decode defaults to
  `lsb-first`, reports the alternate decode next to it, and records the two
  same-session corroborations (`baud_9600_matches_link`,
  `output_off_matches_vout_zero`) without upgrading the check to `pass`.
- The `lsb-first` tracking decode (`11` -> series) has not been confirmed on the
  panel; do not assume CH1 and CH2 are independent when `STATUS?` reports a
  tracking mode.
- The `STATUS?` description on p. 50 says "Returns the GPD-X3303S", and p. 51
  prints the `*IDN?` example as `GPD-X3303`; the verified unit answers
  `GPD-4303S`. The manual's model strings are copy-paste defects.
- The manual documents `ERR?` (pp. 47, 52) but this Skill never sends it,
  because it was not part of the exercised interaction set.
- The manual's error table prints `Invalid character`; the device sends
  `Invalid Character.` (capital `C`, trailing period).
- `HELP?` answers with a 934-byte, 18-line, CR-separated block ending in CR LF
  and omits `HELP?` itself, matching manual p. 52.
- USB descriptor `0403:6001` and the `/dev/ttyUSB0` node are host evidence, not
  manual text; the manual only specifies a rear-panel USB slave port.
- The 15-character command limit does not say whether the terminator counts;
  keep the body at 14 characters or fewer if a command is ever sent.
