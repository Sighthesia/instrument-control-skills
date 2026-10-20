# Remote Session (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 33-39 (common commands), p. 163 (`:SYSTem`), pp. 250-253 (error queue),
p. 169 (Ethernet). Support level: `documented`.

## Transports

### USB CDC (all models)

- USB device Type-B, CDC-ACM virtual COM port on the host.
- The manual states no serial defaults. `115200 8N1` is an assumption used by
  `scripts/gds1000b_session.py`; change `--baud` if the host requires it.
- Linux commonly exposes `/dev/ttyACM0`; confirm the actual device node.

### Ethernet socket server (4-channel models only)

- Available on GDS-1054B, GDS-1074B, GDS-1104B.
- Off by default. Enable the socket server on the instrument first.
- Port selectable **1024-65535**; there is no manual default, so `--host` and
  `--port` are both required.
- Raw TCP, LF termination. `:ETHERnet:DHCP` applies only to
  GDS-1074B/GDS-1104B (manual p. 169).

## Framing

- Send commands terminated with LF.
- Accept LF, CR, CRLF, or LFCR on responses.
- One session, one query, one response. Do not send another query while a
  response is unread.
- Binary waveform responses are length-framed; read the IEEE block header and
  then exactly that many bytes. Never split a waveform on LF/CR.

## Identity

```text
*IDN?
```

Documented shape: `GW,GDS-<model>,P<serial>,V<version>` (pp. 33-34), for
example `GW,GDS-1202B,PXXXXXX,V1.00`.

- Vendor must be `GW`.
- Model must be one of the six GDS-1000B models; anything else is `INVALID`.
- Missing serial or firmware is `INCOMPLETE`.
- A malformed or empty field is `INVALID`.
- Identity does not prove the installed options or the interface in use.

## Settings snapshot

```text
*LRN?
```

Returns a long settings string. Preserve it verbatim for provenance; the Skill
does not parse every field. Use specific queries when a single value is needed.

## Common commands (pp. 33-39)

| Command | Effect | Caution |
|---|---|---|
| `*IDN?` | Identify instrument | Read-only |
| `*LRN?` | Learned settings string | Read-only; long response |
| `*RST` | Documented reset | Destroys operator setup; not routine cleanup |
| `*CLS` | Clear status/error queue | Only when authorized |
| `*ESE <n>` / `*ESE?` | Event status enable | Changes status reporting |
| `*ESR?` | Event status register | Clears the register when read |
| `*OPC` / `*OPC?` | Operation complete | `*OPC?` returns 1 when done |
| `*SRE <n>` / `*SRE?` | Service request enable | Changes SRQ behavior |
| `*STB?` | Status byte | Read-only |
| `*SAV <1..20>` | Save setup to slot | Overwrites that slot |
| `*RCL <1..20>` | Recall setup from slot | Replaces current setup |

Do not automate `*RST`, `*SAV`, or `*RCL` without explicit authorization.

## Panel lock

```text
:SYSTem:LOCK {OFF|ON|?}
```

Locking blocks local panel operation. Always release it when the remote
session ends, unless the operator wants it left locked.

## Error queue

```text
:SYSTem:ERRor?
```

Documented forms (pp. 250-253):

- `+0, "No error."` — queue empty.
- `-350, "Queue overflow"` — more errors occurred than the queue holds.
- `code, "message"` — one queued error; the code is a SCPI error number.

Rules used by this Skill:

- `+0, "No error."` -> `COMPLETE`.
- `-350` or `+350` with `Queue overflow` -> `INCOMPLETE`.
- Any other record in explicit error-queue mode -> `UNVERIFIED`; the message is
  preserved, not interpreted as success or failure.
- Automatic classification accepts only the two documented sentinels; other
  messages require calling `parse_error_queue(..., response_type="error-queue")`.

Drain repeatedly until `+0, "No error."`, with a bounded loop (the helper uses
20). A drained queue does not prove the command did what you intended.

## Session sequence

1. Open transport; do not send anything until the port is ready.
2. `*IDN?` and validate the model.
3. Read current state (trigger, timebase, channels) before writing.
4. `*CLS` only if clearing status is authorized.
5. Drain the error queue.
6. Configure.
7. Arm/acquire, then stop before downloading.
8. Drain the error queue again.
9. Close or release the transport; unlock the panel if you locked it.

## Status and errors

- `*ESR?` and `*STB?` are documented, but reading them clears or reports
  latched state; do not use them as a substitute for the error queue.
- A timeout or a response without a terminator is a transport failure, not an
  instrument result. Report it as such.
- Never merge a retried read into a "complete" record.
