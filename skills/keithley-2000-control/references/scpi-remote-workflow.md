# SCPI remote workflow

Evidence: *Model 2000 Multimeter User's Manual*, `2000-900-01 Rev. J / August
2010`; remote operation and SCPI references, PDF physical pages 81-90, 98-117,
118-137, 190-194, 201-204, and 252-256.

## Interface and language preflight

- The Model 2000 uses one selected remote interface at a time: GPIB/IEEE-488 or
  RS-232. The interface and command language are selected from the front panel
  and stored in nonvolatile memory. Remote commands cannot safely establish or
  switch that selection.
- Confirm the selected language is **SCPI** before sending SCPI subsystem
  commands. `*IDN?` returns Keithley, model, serial, and digital/display firmware
  identifiers, but does not identify the selected command language.
- Use the GPIB primary address configured on the instrument; the manual gives
  factory address 16. Do not assume it remains unchanged.
- RS-232 uses 8 data bits, 1 stop bit, no parity; the factory baud rate is 4800.
  The manual documents no hardware flow control, optional XON/XOFF, command
  processing on CR, and TX termination as LF, CR, or LFCR. Use a straight-through
  DB-9 cable, not a null modem. The controller and instrument settings must
  agree (PDF 85-87).
- Never infer an EOI/newline policy for GPIB from RS-232 settings. Use the
  transport's documented message boundary and preserve exact received bytes.

## Query pairing and state preservation

1. Save the complete response bytes for `*IDN?` and retain the parsed fields as
   metadata, not as proof that the command language is SCPI.
2. Snapshot current function, input selection, range, auto-range, NPLC, bandwidth,
   filter, math/REL, trigger, buffer, and scan state as relevant before changing
   configuration.
3. Send one program message at a time unless the transport and the exact
   multi-command response ordering are explicitly managed. For every query,
   consume exactly its response before issuing another query. Reading an empty
   output queue is a query error; ignoring an output response makes later values
   ambiguous (PDF 117, 121).
4. Never issue a broad reset as routine cleanup. `*RST` and `:SYSTem:PRESet`
   have different defaults; `*RST` does not clear the error queue. Both can
   change trigger/function state and invalidate the caller's prior setup.
5. Query `:SYSTem:ERRor?` after setup and acquisition. Drain the FIFO until
   `0,No error`; preserve all messages in order. The queue holds up to 10
   messages; a full queue reports `350, Queue Overflow`. Negative codes are
   SCPI-defined; positive codes are Keithley-defined (PDF 190, 194).
6. Do not automatically clear a pre-existing error queue. Record it first;
   send `*CLS` only when authorized because it clears event/status registers and
   the error queue.

## Choose the acquisition command

| Command | Meaning | Caveat |
|---|---|---|
| `:CONFigure:<function>` | Select and configure a one-shot measurement | Resets that function's parameters to `*RST` values; disables continuous initiation, math, buffer operation, and scanning and returns trigger defaults (PDF 134-135). |
| `:READ?` | Trigger and acquire in one-shot mode | Executes `:ABORt`, `:INITiate`, `:FETCh?`; uses sample count and stores readings. If sample count >1 and readings are already in the buffer, it returns `-225` (PDF 136). |
| `:MEASure:<function>?` | Convenience one-shot measurement | Executes `:ABORt`, `:CONFigure:<function>`, `:READ?`; has the `:CONFigure` side effects above (PDF 137). |
| `:FETCh?` | Return latest post-processed reading without triggering | Can return the same stale value repeatedly; rapid external triggers can lose readings (PDF 135). |
| `:SENSe:DATA?` | Return latest raw or REL-adjusted reading in exponent form | No function name; no math result. Pair it with `:FUNCtion?` and configuration metadata (PDF 169). |
| `:DATA:FRESh?` | Request a fresh reading | Consult the Model 2000 command description and current trigger mode first; do not substitute `:FETCh?` when freshness is required. |

For continuous or externally triggered measurements, explicitly configure the
trigger model and select a compatible readout path. `:READ?` is not allowed
with continuous initiation active; `:INITiate:CONTinuous ON` combined with
`*OPC?` can lock the instrument (PDF 125, 136, 201).

## Response format

- `:SENSe:DATA?` and `:CALCulate:DATA?` are always ASCII. `:FORMat:DATA` controls
  buffer transfer formats: `ASCii`, IEEE-754 `SREal` or `DREal`; binary uses a
  `#0` header per measurement conversion and selected normal/swapped byte order
  (PDF 159-161).
- ASCII may include `READing`, `CHANnel`, and `UNITs` elements. In the documented
  representation, a reading may look like `+1.23456789E+00VDC, 0INTCHAN`;
  overflow is `+9.9E37` with no unit. Binary does not support the `UNITs` element
  (PDF 159, 162).
- Do not assume the scalar parser can decode a buffer dump, multiple readings,
  binary transfer, or concatenated response. Preserve raw bytes and report
  `UNSUPPORTED` until framing and field order are explicitly implemented.
- The Model 2000 manual documents ASCII-only RS-232 behavior for certain
  transfers; do not enable binary over RS-232 without checking the relevant
  command/interface constraints and error queue.

## Error and status handling

- Parse error-queue replies as `code,message`, preserving the original text and
  sign. `0,No error` is the empty-queue sentinel, not an empty response.
- Treat overload (`OVERFLOW` on the display, or `+9.9E37` in ASCII) as a
  measurement status, not as a finite value. Treat `350, Queue Overflow` as
  evidence that earlier error messages may have been lost.
- For status-register workflows, consult the manual's status-byte, standard
  event, measurement, operation, and questionable register definitions (PDF
  98-107, 183-190). Do not read event registers as a harmless snapshot: event
  queries clear the corresponding latched events.
- Keep command errors, execution errors, device-dependent errors, query errors,
  instrument overloads, and missing/stale responses as distinct findings.

## Manual citation index

| Topic | PDF physical pages |
|---|---:|
| Interface selection and language | 81-84 |
| RS-232 settings and cable | 85-87 |
| GPIB address and bus | 88-97 |
| Status model and queues | 98-107, 117, 190-194 |
| SCPI syntax and common commands | 111-131 |
| Signal-oriented measurement commands | 134-137 |
| Format and data elements | 159-162 |
| Function and data query | 168-169 |
| Trigger subsystem | 201-204 |
