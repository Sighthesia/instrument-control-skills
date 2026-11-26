# Remote Session (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Interface configuration and command syntax: TOC pp. 6-23; common commands:
TOC pp. 37-40; system/error queue: TOC p. 148; Ethernet: TOC p. 155; error
messages: TOC pp. 235-238. Support level: `documented` for transports not
exercised; `hardware-verified` only for the USB CDC observations named below.
Page numbers are table-of-contents or List of Commands markers (pp. 24-34);
the local converted copy has no body page breaks.

## Transports

| Transport | Availability | Verified on this unit | Key settings |
|---|---|---|---|
| USB CDC-ACM | All models | **Yes** | Type-B device port; `2184:0014`; `/dev/ttyACM1`; 115200 8N1; LF |
| RS-232C | Rear DB-9, documented | No | 2400-115200 baud; parity none/odd/even; 8 data bits fixed; 1 or 2 stop bits; null modem |
| Ethernet socket | DS2-LAN option | No | Module required; socket server off by default; port 1024-65535; raw TCP; LF |
| GPIB | DS2-GPIB option | No | Address 1-30; 15 devices max; 20 m total, 2 m between devices |

### USB CDC-ACM

- The verified unit enumerated as USB `2184:0014` and appeared as
  `/dev/ttyACM1` on the host. A different host may enumerate it elsewhere.
- The session helper defaults to `/dev/ttyACM1` and `115200 8N1`. The manual
  states no USB CDC serial default; USB CDC is a virtual COM link, so the host
  baud value is not a device setting.
- `pyserial` is required only for live use. Offline parsing and `--dry-run`
  never import it.

### RS-232C

- Connector: rear DB-9 male. Pin 2 RxD, pin 3 TxD, pin 5 GND; pins 4 and 6-9
  are not connected.
- Set the baud rate, stop bit, and parity on the instrument before opening the
  host port. Data bits are fixed at 8.
- Use a null-modem connection between the instrument and the PC.
- This transport was not exercised. Do not treat RS-232C settings as verified
  because USB CDC worked.

### Ethernet socket server (DS2-LAN)

- The DS2-LAN module must be installed before the Ethernet menu is available.
- Configure DHCP/BOOTP or a static IP address, then enable the socket server.
  The socket server is **off by default**.
- Port range **1024-65535**; there is no manual default, so pass both host and
  port explicitly. HTTP uses fixed port 80; that is the web server, not the
  raw SCPI socket.
- Raw TCP with LF termination. Not exercised by this Skill.

### GPIB (DS2-GPIB)

- The DS2-GPIB module must be installed; the address menu appears only then.
- Address range **1-30**. Maximum 15 devices, 20 m total cable, 2 m between
  devices; assign a unique address; no loops or parallel connection.
- Not exercised by this Skill.

## Framing

- Send commands terminated with **LF** (`\n`). The manual's message terminator
  is LF (TOC p. 22).
- Accept **LF, CR, CRLF, or LFCR** on responses. The parser preserves the
  observed terminator.
- One session, one query, one response. Do not send another query while a
  response is unread.
- Send one command per write. Do not concatenate commands with `;` on one
  line.
- A waveform response is length-framed: read the ASCII header, the
  `Waveform Data;` marker, and then exactly the declared IEEE block length.
  Never split a waveform on LF/CR.
- A double LF was observed after `:TRIGger:FREQuency?` (`2.000E+00` followed by
  two LFs). The parser keeps the second LF as trailing framing evidence; it is
  not a second response and must not be paired with the next query.

## Transport reliability

Two failures were observed on the verified USB CDC-ACM link; neither is a
command-syntax defect:

- One loopback pass queued `-114, "Header suffix out of range"` although every
  command in that pass had been accepted individually and the immediate re-run
  was clean. Treat a lone `-114` after a burst of writes as a truncated or
  interleaved write, not as proof that the spelling is wrong; re-send one
  command per write and drain the queue before drawing a conclusion.
- Opening both CDC-ACM instrument ports at the same time blocked a `read()` on
  the scope for tens of seconds. Work one port at a time, close it before
  opening the other, and read responses with an idle-gap reader rather than an
exact byte count.

Every write should be followed by an error-queue read before the next write is
composed. A clean queue is the only evidence that the command was accepted.

## Identity

```text
*IDN?
```

Documented shape: `GW,GDS-<model>,<serial>,V<version>` (TOC pp. 37-40), for
example `GW,GDS-2104A,GEN182193,V1.18`.

- Vendor must be `GW`.
- Model must match `GDS-<four digits>A`; anything else is `INVALID`.
- Serial may be `P`-prefixed or alphanumeric; an empty serial is `INCOMPLETE`.
- Firmware must start with `V`; missing firmware is `INCOMPLETE`.
- A three-field reply is treated as missing firmware, not as a different
  shape. Extra fields are `INVALID`.
- Identity does not prove installed options or the transport in use.

## Settings snapshot

```text
*LRN?
```

Returns a long learned-settings string (TOC p. 37). Preserve it verbatim for
provenance; the Skill does not parse every field. Use specific queries when a
single value is needed.

## Common commands (TOC pp. 37-40)

| Command | Effect | Caution |
|---|---|---|
| `*IDN?` | Identify instrument | Read-only |
| `*LRN?` | Learned settings string | Read-only; long response |
| `*RST` | Documented reset | Destroys operator setup; not routine cleanup |
| `*CLS` | Clear status/error queue | Only when authorized |
| `*SAV <1..20>` | Save setup to a slot | Overwrites that slot |
| `*RCL <1..20>` | Recall setup from a slot | Replaces current setup |

The verified run did not send `*RST`, `*SAV`, `*RCL`, or `*CLS`.

## Panel lock

```text
:SYSTem:LOCK {OFF|ON|?}
```

Locking blocks local panel operation. Always release it when the remote
session ends, unless the operator wants it left locked. The verified unit
reported `OFF`; the run did not change it.

## Error queue

```text
:SYSTem:ERRor?
```

Documented/observed forms (TOC pp. 148, 235-238):

- `+0, "No error."` — queue empty; `COMPLETE`.
- `-350, "Queue overflow"` — more errors occurred than the queue holds;
  `INCOMPLETE`.
- `code, "message"` — one queued error; the code is a SCPI error number. Any
  other code is `UNVERIFIED`: the message is preserved, not interpreted as
  success or as proof the command failed.

Observed on the verified unit:

- `-113, "Undefined header"` after undefined or unsuffixed commands such as
  `:MEASure:VPP?` and `:ACQuire:STATe?`.
- `-108, "Parameter not allowed"` after `:MEASure:PK2PK? CH1` and
  `:ACQuire:MEMory? CH1`.

Rules:

- Drain repeatedly until `+0, "No error."`, with a bounded loop (the helper
  uses 32 replies).
- A drained queue does not prove the command did what you intended. It proves
  the instrument reported no further errors.
- Do not merge a failed or retried read into a `COMPLETE` record.

## Sendable spelling rules

The manual's list prints family forms; the instrument required specific
suffixes and query forms. The verified rules are:

- `:CHANnel<n>:*`, `:ACQuire<n>:*`, `:MEASure:SOURce<n>`, and
  `:MEASUrement:MEAS<n>:*` need a numeric suffix. Bare `:ACQuire:MEMory?`
  returned an empty line; bare `:ACQuire:STATe?` returned `-113`; bare
  `:MEASure:SOURce` returned `-131`.
- Individual `:MEASure:*?` commands take no channel parameter. Select the
  source first with `:MEASure:SOURce1 CH1`. `:MEASure:PK2PK? CH1` returned
  `-108`.
- `:TRIGger:*` and `:TIMebase:*` are global and take no channel suffix.
- `:FUNCtion:*` requires a module suffix such as `:FUNCtion1:`; the DS2-FGN
  option was absent, so even the suffixed query returned `-240`.
- The full verified spellings are in
  [command-reference.md](command-reference.md#appendix-c-verified-sendable-spellings-not-printed-in-the-list).

## Session sequence

1. Open the selected transport; do not send anything until the port is ready.
2. `*IDN?` and validate the model.
3. Read current state (trigger, timebase, channels, header) before writing.
4. `*CLS` only if clearing status is authorized.
5. Drain the error queue.
6. Configure the channel, timebase, and trigger.
7. Arm/acquire, then `:STOP` before downloading memory.
8. Drain the error queue again.
9. Restore any state you changed; close the transport; unlock the panel if you
   locked it.

## Status and errors

- A timeout or a response without a terminator is a transport failure, not an
  instrument result. Report it as such.
- A line response with extra non-whitespace bytes is `INVALID`; it means the
  response pairing is ambiguous. Do not try to resynchronise by guessing.
- A binary block that ends at the deadline is `INCOMPLETE`; preserve the
  partial bytes and report the read end (`declared_length`,
  `declared_length_no_terminator`, `line_terminator`, or `deadline`).
- Reading the error queue or `*CLS` changes status state; do not do it
  silently in the middle of a measurement sequence.
- `:TRIGger:STATe?` returns `ARMED`, `AUTO`, `SAVE`, or `READY` on V1.18,
  without the leading `*` shown in the manual. Treat it as evidence of state,
  not as a measurement.
