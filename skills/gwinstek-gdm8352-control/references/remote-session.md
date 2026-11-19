# Remote Session

All page numbers are PDF physical pages in the *GDM-8352 User Manual*, GW
Instek part no. `82DM-83520E01`.

## Choose the USB interface

The rear-panel USB device port is Type B. The manual's front-panel path is
`MENU → I/O → USB → USB-CDC` or `USB-TMC` (PDF pp. 91-92). `USB-CDC` presents
as a virtual serial port. `USB-TMC` is documented for VISA (the manual names
NI-VISA 3.0 or later), but was not exercised by this Skill. The session script
implements USB-CDC only; it does not change the interface setting.

The captured unit enumerated at `/dev/ttyACM0` as USB CDC-ACM, VID:PID
`2184:003b`. `lsusb` showing `GW Instek GDM-8351` is expected for this unit:
it is a stale USB descriptor, not the instrument identity. This host-side
evidence is from the 2026-11-19 capture on firmware `1.00`, serial `GEP848232`.
The unit was re-tested later the same day (`verify_all`, 11:38:50Z); that
evidence directory, `artifacts/verification/evidence/20261119T113850Z/`, is
git-ignored and is a local reference only.

**USB CDC ignores the host baud-rate setting on the captured unit.** Both
115200 and 9600 received the same correct responses. Explicitly passing
`--baud 115200` records a default; it does not configure USB link speed. Do not
apply this observation to RS-232 or USB-TMC.

## Frame one query and one response

- The script sends one allowlisted ASCII query followed by `\r\n` (`CR+LF`),
  the terminator observed on captured responses. Never batch commands or send a
  setter as a probe or cleanup.
- For incoming commands, the manual lists `CR`, `LF`, `CR+LF`, and `LF+CR` as
  EOL (PDF p. 99). For outgoing responses, the panel path is
  `MENU → TX TERM → TX EOL → [CR / LF / CR+LF / LF+CR] → Enter → EXIT`
  (PDF p. 94). Use `CR+LF` with this Skill. The offline framer can recognize all
  four from saved bytes, but the live reader stops at `LF` and would not
  preserve the trailing `CR` in `LF+CR`.
- Start with `*IDN?`. If the response is missing, invalid, or its model field
  does not identify `GDM8352`, stop and do not interpret later readings as
  GDM-8352 data. Apply this check before making other CLI calls: the single-query
  commands do not perform an identity handshake for you.

## Timeouts and error text

Measured on the verified unit (2026-11-19, values are measured, not manual
figures): `MEAS:VOLT:DC?` returned its first byte after about **0.262 s**,
`MEAS:CURR:DC?` after about **0.135 s**, and `READ?` after about **0.025 s**.
DC voltage is the slowest query, so give it a timeout budget of at least **1 s**;
the shipped 2 s default is intentionally above that and must not be reduced
towards the measured latency.

The session defaults to a 2 s read timeout (`--timeout` sets it) and two
attempts. Before each send, it clears pending input with `reset_input_buffer`
when available. This discards bytes already buffered; it cannot guarantee that
a late reply will not arrive after the reset. Keep only one query outstanding.
Retry the same allowlisted read-only query at most once after a zero-byte
timeout. A retry is a separate observation: never concatenate it with bytes
from another attempt. If bytes arrive without a terminator, keep them as an
`INCOMPLETE` frame instead of filling in missing bytes. If both attempts are
silent, report `INCOMPLETE`; silence is not a successful empty reply. Check
USB mode, device node, terminator, and documented query syntax before retrying
a failed session. Do not probe with setters or resets.

`SYST:ERR?` returned the free text `Command error` on the captured unit. Do not
interpret it as a numeric code or poll it as a readable error queue; the
hardware evidence only establishes that exact returned text. A `CONF?` timeout
is a different observation: this is not a documented query and no bytes were
received. See [response-and-evidence.md](response-and-evidence.md) and
[command-reference.md](command-reference.md).
