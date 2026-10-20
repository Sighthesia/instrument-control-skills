# Remote Session (AFG-2225)

Manual: *AFG-2225 Series User Manual*, GW Instek part no. 82RF-22250M01,
REMOTE INTERFACE chapter, PDF pp. 180-199. Support level: `documented`.

## Interface

- **USB device port only** (Type-B slave, USB 1.1/2.0 full speed). No
  LAN, GPIB, or RS-232 (manual p. 181).
- USB CDC-ACM virtual COM port, **not** USBTMC. Linux device ID
  `0x2184:0x001c` is **external evidence** from the Linux kernel commit
  `cf84a691a61606a2e7269907d3727e2d9fa148ee`; the manual does not list
  VID/PID (external, not manual).
- The manual asks the operator to set COM port, baud rate, stop bit, data
  bit, and parity, but lists no defaults. `115200 8N1` used by the optional
  transport is an **assumption**, not a manual default.
- Terminators: LF, CR, or LF/CR; EOI is also listed. In terminal programs use
  `^j` or `^m` (manual pp. 182, 187).
- All panel keys lock in remote mode except F5 (REM/LOCK) (manual p. 182).

## Standard and command forms

- Compatible with IEEE 488.2 (1992, fully) and SCPI (1994, partially)
  (manual p. 184).
- Commands are case-insensitive; short/long forms must be complete
  (manual pp. 185-186).
- Parameters: NR1/NR2/NR3/NRf/NRf+, Boolean, discrete, etc.
  (manual pp. 186-187).
- Message terminators: LF, CR, or EOI; separators: space, colon, semicolon,
  comma (manual pp. 187-188).

## Identity and version

| Command | Type | Manual page | Notes |
|---|---|---|---|
| `*IDN?` | query | 193 | `GW INSTEK,AFG-2225,SN:XXXXXXXX,Vm.mm` |
| `SYSTem:VERSion?` | query | 194 | instrument/firmware/FPGA revision string |

## Status and error

| Command | Type | Manual page | Notes |
|---|---|---|---|
| `*CLS` | command | 196 | clears status registers and error queue |
| `*ESE` | command | 196 | event status enable |
| `*ESR?` | query | 197 | event status register |
| `*STB?` | query | 197 | status byte |
| `*SRE` | command | 198 | service request enable |
| `*OPC` | command | 194 | operation complete bit |
| `*OPC?` | query | 195 | returns 1 when complete |
| `*WAI` | command | 195 | wait until complete |
| `*RST` | command | 194 | factory reset; does not delete saved states |
| `SYSTem:ERRor?` | query | 193, 292 | reads one error from the 20-entry FIFO |

- Error queue: 20 entries, FIFO. Full queue returns `-350 Queue overflow`;
  empty queue returns `0 No error` or a bare `No error` (manual p. 292, which
  does not show the empty-queue wire format). `*CLS` clears the error
  queue; `*RST` resets instrument settings and does not delete saved states,
  but the manual does not state its effect on the error queue (manual p. 194).

## Remote/local

| Command | Type | Manual page |
|---|---|---|
| `SYSTem:LOCal` | command | 199 |
| `SYSTem:REMote` | command | 199 |

## Standard session flow

1. Open the already-configured USB CDC COM port (no default baud in manual).
2. Send `*IDN?`; preserve raw bytes; validate vendor/model/serial/firmware.
3. Query `SYSTem:VERSion?` when firmware evidence is needed.
4. Clear only authorized status (`*CLS`); `*RST` only if operator authorizes.
5. Drain `SYSTem:ERRor?` until `0 No error`/`No error`.
6. Configure waveform/output settings.
7. Turn output on only when authorized; verify `OUTP<n>?` rather than assuming
   a low-level command changed the output state.
8. Verify readback where a query exists.
9. Drain the error queue again.

## Save/recall (manual pp. 271-272)

| Command | Meaning |
|---|---|
| `*SAV {0..9}` | Save the current instrument state to a non-volatile slot. |
| `*RCL {0..9}` | Recall a saved instrument state. |
| `MEMory:STATe:DELete {0..9}` | Delete one saved state. |
| `MEMory:STATe:DELete ALL` | Delete all saved states. |

`*SAV` saves instrument state, not waveform data. Do not delete or overwrite
operator-owned slots automatically.

## Query pairing

One transport session, one query, one response. Do not send a second query
while an earlier response is unread. Preserve raw bytes and SHA-256 for
every response.

## Manual citation index

| Topic | PDF pages |
|---|---:|
| USB connection and remote terminal | 180-182 |
| Command syntax and forms | 184-188 |
| System/common commands | 193-195 |
| Status register commands | 196-198 |
| Remote/local | 199 |
| Error queue and status model | 287-292 |