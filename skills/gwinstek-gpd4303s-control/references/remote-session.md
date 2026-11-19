# Remote Session (GPD-4303S)

Source: *GPD-X303S Series User Manual*, GW Instek part no. `82PD-433S0MC1`,
REMOTE CONTROL chapter, PDF pp. 43-45, plus command syntax p. 46 and the panel
lock note p. 53. Host evidence (USB descriptor, device node) is marked as
external because the manual does not print it.

## Interface

- **USB slave port on the rear panel only** (manual p. 43). No LAN, GPIB, or
  RS-232 interface is documented for the GPD-X303S series.
- On the verified unit the port presents an FTDI FT232R bridge and the host node
  is `/dev/ttyUSB0`. `lsusb` reports `0403:6001 Future Technology Devices
  International, Ltd FT232 Serial (UART) IC`. **This is host-side evidence, not
  manual text**; the manual only says "USB slave port, rear panel".
- The manual's accessory list includes the GTL-246 USB 2.0 A-B cable (p. 56), so
  the host sees a plain USB-serial bridge rather than USBTMC.

## COM settings (manual p. 43)

| Setting | Manual | Observed on the verified unit |
|---|---|---|
| Baud rate | 9600 / 57600 / 115200 | **9600 only.** A session opened at 115200 received nothing; every captured response came from 9600 8N1. |
| Parity | None | None |
| Data bits | 8 | 8 |
| Stop bits | 1 | 1 |
| Flow control | None | None |

The default baud rate is 9600 bps (manual p. 51: `BAUD<NR1>` `2` = 9600). Do not
send `BAUD0` or `BAUD1` to "try" another rate: the command changes the rate of the
session that sends it and you lose the link.

## Terminators and framing

- Commands must end with `0x0A` (LF) or `0x0D0A` (CR LF) (manual p. 46). The
  verified sessions sent CR LF, which is what `scripts/gpd4303s_session.py`
  does by default.
- Responses end with CR LF. A single-line response is `content + \r\n`.
- `HELP?` is the one multi-line response: 18 lines separated by CR, with the
  final line terminated by CR LF (934 bytes observed). A reader that stops at
  the first line truncates it; a reader that waits for LF only works because the
  last line ends with LF. `gpd4303s_protocol.read_multiline_frame` keeps every
  line and the raw bytes.
- The instrument does not echo the command. The response to a query is the value
  or message only.
- One query, one response. Do not send a second query while a response is
  unread; there is no sequence numbering to detect a mismatch.

## Remote mode

Entering (manual p. 44):

1. Connect the USB cable to the rear-panel slave port.
2. The link is established automatically and the front panel shows `USB…YES`.
3. The panel is locked automatically (`Lock` indicator on).

Leaving (manual p. 44), any one of:

- send `LOCAL` from the terminal,
- press the front-panel `LOCK` key,
- disconnect the USB cable.

The panel then shows `USB…NO`, the lock indicator goes out, and the unit returns
to local operation.

**Remote mode is not an interlock.** Manual p. 53 (FAQ A1): "For safety reasons
the output key is not affected by the panel key lock feature." A person standing
at the instrument can still switch the outputs on or off while your session owns
the port. Treat the output state as shared state, not as something the remote
session controls.

## Functionality check (manual p. 43)

Send `*IDN?` and require the documented shape before trusting anything else:

```text
*IDN?  ->  GW INSTEK,GPD-4303S,SN:EP924162,V2.08\r\n
```

The manual prints the reply as `GW INSTEK, GPD-x303S, SN: xxxxxxxx, Vx.xx`; the
verified unit sends no space after the commas and spells the model `GPD-4303S`.
Field order is vendor, model, serial, firmware.

## Session flow

1. Confirm the load, the channel, and the programmed V/I (`VSET<X>?`,
   `ISET<X>?`) before energising anything.
2. Open `/dev/ttyUSB0` at 9600 8N1, no flow control.
3. `*IDN?`; preserve the raw bytes; check model and firmware.
4. `STATUS?`; decode the output bit, the CC/CV bits, and the tracking bits.
5. `VOUT<X>?` / `IOUT<X>?` for the channels that matter. These are separate
   queries: the voltage and the current are not simultaneous samples.
6. `HELP?` when the firmware's own command list is needed. It lists 17 commands
   and omits `HELP?` itself.
7. Do not send a write command as "cleanup". Leave the instrument as you found it
   and report its state.

## Failure modes seen in practice

| Symptom | Meaning | Action |
|---|---|---|
| `could not open port /dev/ttyUSB0` | The bridge is not enumerated | Check the cable and `lsusb`; do not retry blindly at another baud rate |
| Nothing received at 115200 | The unit is at 9600 (its documented default) | Reopen at 9600 8N1 |
| `Invalid Character.` | The command is not in this firmware's table, or the syntax is wrong | Re-check the 15-character limit and the exact form in [command-reference.md](command-reference.md) |
| No response at all to a write command | Accepted silently, or ignored — the wire cannot tell you which | Never infer success; verify with a query (`VSET<X>?`, `VOUT<X>?`, `STATUS?`) |
| Response arrives in two chunks | Normal at 9600 bps | Read until the terminator, not with a single fixed-size read |

## Probe hazard record

During an earlier probe session on the same instrument, `OUT1` was sent without
knowing its semantics. CH1 went from `0.000V` to `23.994V` at a programmed
24 V / 1 A. The unit was returned to `0.000V` only by `OUT0`, because:

- `OUT1` is an enable, not a toggle (repeating it does not disable the output),
- `OUT1?` does not exist and answers `Invalid Character.`, so the state cannot be
  read back with the same command family,
- `STATUS?` bit 5 is the only documented output-state read-back, and its
  character order is not documented (see
  [response-and-evidence.md](response-and-evidence.md)).

This is probe-derived experience, not a manual statement. It is the reason this
Skill ships a read-only helper and refuses every write command.
