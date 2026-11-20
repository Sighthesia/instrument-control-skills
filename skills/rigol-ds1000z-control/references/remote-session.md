# Remote Session (DS1000Z)

Manuals: *MSO1000Z/DS1000Z Programming Guide*, Software Version 00.04.03.SP2,
Dec 2015 (PDF physical pages cited) and *DS1000Z Series User Guide*, Sep 2020.
Support level: `firmware-scoped` on firmware `00.04.02.SP4`; `documented` for
every statement that only the manual supports.

## Transports

### Raw TCP socket on port 5555 (`hardware-verified`)

- TCP port 5555 accepts a connection and answers SCPI directly: `*IDN?` on
  5555 returned `RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4\n`.
- Port 80 (LXI web page) and TCP/UDP 111 (portmapper) are also open. TCP 5025
  (the common SCPI socket) is **closed**.
- The Programming Guide never mentions a socket port: `grep -c ":LAN"` over the
  extracted manual returns 7 hits, all `:SYSTem:LANGuage` (PDF pp. 160-161).
  Port 5555 is evidence, not manual text.
- The User Guide documents the LAN path only as Ultra Sigma / VXI-11 discovery
  with a `TCPIP::<ip>::INSTR` resource (PDF page 252). The scope's own LAN panel
  showed `TCPIP0::10.99.0.194::INSTR` (`hardware-verified`).

### Documented interfaces

- USB Device, USB-TMC (`Utility → IO Setting → USB Device → Computer`); the
  Programming Guide's connection walkthrough is USB-based (PDF pp. 12, 14).
- LAN interface with a `VISA Address` field on the LAN settings page (User Guide
  PDF page 236). A connected USB Device takes precedence and disables LAN
  control; a LAN-only connection enables LAN by default (User Guide PDF
  page 236).
- VXI-11: UDP portmapper answered `GETPORT` for program 395183 (DEVICE_CORE,
  version 1) with TCP port 617 (`hardware-verified`). The RPC session itself was
  not exercised; treat client-library VXI-11 use as `UNVERIFIED`. Port 111
  accepted a TCP connection but did not answer an ONC RPC call.

## Framing rules (all `hardware-verified`)

1. **One command per write.** Three queries in one `sendall` produced exactly one
   answer (the first); the others were silently dropped, with one late answer
   arriving about 3 s later. Two commands written separately, each read before
   the next write, both answered.
2. **Responses are terminated by LF only.** No CR is appended. Accept LF and
   tolerate CRLF, but do not require CR.
3. **Commands must end with LF.** A command sent without a terminator was still
   executed after a short delay because the parser works on received chunks; that
   is not a reason to omit the terminator. LF and CRLF are both accepted.
4. **Writes answer nothing.** `:STOP`, `:WAVeform:MODE RAW`, `:CHANnel1:SCALe …`
   produce no response byte. Leave about 0.3-0.4 s before the next command on the
   same socket instead of immediately pipelining.
5. **An undefined header returns the bare string `command error`.** Exactly 13
   ASCII bytes, **no terminator**, plus a queued `-113,"Undefined header; …"`.
   A reader that blocks until LF hangs until its idle timeout. `:WAVeform:DATA?`
   for a rejected window is not retried automatically: report the failure.

Practical rule for the session helper: after each write, read with a short idle
timeout; if only non-terminated bytes arrive, treat the frame as unterminated and
report it. Never synthesise a terminator or prepend one to the next response.

**Block reads are the exception.** A definite-length block arrives in bursts with
gaps longer than the text idle timeout: a live 1 152 054-byte `:DISPlay:DATA?`
capture stalled after exactly 51 200 bytes and a 0.3 s idle timeout truncated it
at that point (`hardware-verified`). Read a block until the declared length plus
its LF is present or an overall deadline expires, and never end a block read on
a single idle gap.

Latency observed: ordinary queries 1-150 ms; unsupported query ≈ full read
timeout (because of rule 5); `:DISPlay:DATA?` 2.2-6.2 s.

## Identity

```text
*IDN?
```

Observed reply (`hardware-verified`):

```text
RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4
```

- `*SYSTem:MODEL?` returned the identical string on this firmware, so it is a
  supported alias. `:INFO:MODEL?` returned `command error`.
- Validate four fields: vendor `RIGOL TECHNOLOGIES` (also written `RIGOL` on some
  manuals), a model starting `DS1`, a serial, and a firmware version.
- Missing field -> `INCOMPLETE`; empty or malformed field -> `INVALID`.
- Identity proves the model and firmware only. It does not prove the installed
  options (`*OPT?` fails on `00.04.02.SP4`), the channel configuration, or the
  interface you are actually using.

## State read-back before any change

There is no settings-dump command on this firmware: `:SYSTem:SETup?` returned
`command error` even though the Programming Guide documents `:SYSTem:SETup`
(PDF page 163). Read the state with individual queries (`hardware-verified`
shapes):

```text
:TRIGger:STATus?        TD | WAIT | RUN | AUTO | STOP
:TIMebase:MAIN:SCALe?   2.0000000e-04          (NR3, seconds/div)
:ACQuire:TYPE?          NORM | PEAK | AVER | HRES
:ACQuire:MDEPth?        AUTO | 12000 | 120000 | 1200000
:ACQuire:SRATe?         1.000000e+09
:CHANnel<n>:DISPlay?    1 | 0
:CHANnel<n>:SCALe?      5.000000e-01
:CHANnel<n>:OFFSet?     -1.520000e+00
:CHANnel<n>:COUPling?   DC | AC | GND
:CHANnel<n>:PROBe?      1.000000e+00 … 1000
:CHANnel<n>:BWLimit?    OFF | 20M
:TRIGger:MODE?          EDGE | …
:TRIGger:EDGE:SOURce?   CHAN1 … CHAN4
:TRIGger:EDGE:LEVel?    1.500000e+00
:WAVeform:MODE?         NORM | MAX | RAW
:WAVeform:SOURce?       CHAN1 … CHAN4 | D0 … D15 | MATH
:WAVeform:POINts?       integer
```

## Common commands (Programming Guide PDF pp. 95-97)

| Command | Page | Effect | Caution |
|---|---|---|---|
| `*IDN?` | 96 | Identify instrument | Read-only |
| `*CLS` | 95 | Clear status and error queue | Destroys pending error evidence |
| `*ESE` / `*ESE?` | 95 | Standard event enable | Changes status reporting |
| `*ESR?` | 95 | Standard event register | Reading clears it |
| `*OPC` / `*OPC?` | 96 | Operation complete | `*OPC?` returns `1` |
| `*RST` | 96 | Documented reset | Destroys operator setup; not routine cleanup |
| `*SRE` / `*SRE?` | 96 | Service request enable | Changes SRQ behavior |
| `*STB?` | 96 | Status byte | Read-only |
| `*TST?` | 97 | Self-test | Returns `0` on the evidence unit |
| `*WAI` | 97 | Wait for pending operations | — |

`*ESR?` returned `32`, `*STB?` returned `4`, `*OPC?` returned `1`, and `*TST?`
returned `0` on the evidence unit (`hardware-verified`). Those values are a
snapshot, not expected constants.

`*SAV` and `*RCL` are **not in the Programming Guide at all** (0 grep hits), and
no `:SAVE` / `:RECAll` subsystem exists either: storage is `:STORage:*`
(PDF page 158), `:SYSTem:SETup` (PDF page 163), and `:REFerence<n>:SAVe`
(PDF page 145). The scripts therefore reject `*SAV`, `*RCL`, `:SAVE`, and
`:RECAll` as undocumented write commands. That is a defensive decision made from
the manual, not an observed firmware failure.

## Error queue

```text
:SYSTem:ERRor?
```

Documented (PDF page 161). Observed behavior (`hardware-verified`):

- Queue depth is **16** entries; further errors report `-350,"Queue overflow"`
  instead of growing the queue.
- `0,"No error"` is a record returned by the query itself (one entry per query),
  not a separate acknowledgement.
- Observed records: `-113,"Undefined header; keyword cannot be found"`,
  `-113,"Undefined header; command cannot be found"`, `-220,"Parameter error"`
  (bad parameter or rejected window), `-200,"Execution error"` (for example
  `:ACQuire:MDEPth` while acquisition is stopped), `-350,"Queue overflow"`.

Classification rules used by this Skill:

- `0,"No error"` -> `COMPLETE` (queue drained for this query).
- `-350` / `Queue overflow` -> `INCOMPLETE`; the true error was lost.
- Any other record (`-113`, `-220`, `-200`, …) -> `UNVERIFIED`: report the code and
  message verbatim. Do not read `-220` or `-200` as success and do not invent a
  corrective action from the code alone.
- Drain repeatedly until `0,"No error"` with a bounded loop (stop after ~20
  iterations and report that the queue did not drain).

An empty queue does not prove the command did what you intended; some rejected
writes leave the previous value in place silently (see
[capture-and-waveform.md](capture-and-waveform.md)).

## The undocumented `:LAN:` query family

These answered on firmware `00.04.02.SP4` (`hardware-verified`) and have **no
Programming Guide section**:

```text
:LAN:DHCP?     :LAN:IPADdress?   :LAN:SMASk?   :LAN:GATeway?
:LAN:MAC?      :LAN:STATus?      :LAN:MANual?
```

- `:LAN:DHCP?` -> `1`, `:LAN:STATus?` -> `CONFIGURED`, `:LAN:MANual?` -> `1`,
  `:LAN:MAC?` -> `00-19-AF-34-5D-28`.
- `:LAN:MANual?` reported `1` while DHCP was still on, so it cannot be read as
  "static addressing is active".
- Treat the names as `UNVERIFIED` against any manual, and treat the write forms
  as dangerous: a wrong static address or mask can make the instrument
  unreachable with no local recovery. `scripts/ds1000z_session.py` refuses every
  writing `:LAN:` command unconditionally.
- The MAC address is stable hardware identity and is safe to record for
  provenance; IP addresses belong to the bench, so keep them out of committed
  fixtures.

## Session sequence

1. Open the socket with an explicit timeout; send nothing until it is connected.
2. `*IDN?` as one write; read the frame; validate model and firmware.
3. Read the state you are about to change (see read-back list above).
4. `*CLS` only when clearing the status is authorized.
5. Drain `:SYSTem:ERRor?` to `0,"No error"`.
6. Configure channel, timebase, and trigger; one command per write, 0.3-0.4 s
   apart, and read back the values you depend on.
7. Acquire; `:STOP` before any RAW or MAXimum download.
8. Drain the error queue again.
9. Close the socket. Leave the instrument in a documented state (acquisition
   running, `:WAVeform:MODE NORM`, `:WAVeform:SOURce` restored,
   `:MEASure:SOURce` restored).

## Failure handling

- A timeout, a socket error, or bytes without a terminator is a transport result,
  not an instrument value. Report it as `INCOMPLETE` (missing terminator) or as a
  transport error, and say which.
- Never merge a retried read into a "complete" record: keep the first attempt and
  the retry as separate artifacts with separate hashes.
- Never re-send a slow query (`:DISPlay:DATA?`, RAW `:WAVeform:DATA?`) before the
  timeout expires; both can take seconds and a second write breaks rule 1.
- If the identity response is unreadable, stop. Do not guess the model from the
  number of responding channels.
