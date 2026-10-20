---
name: keithley-2000-control
description: Control and document measurement workflows for a Keithley Model 2000 bench multimeter using its documented SCPI command set. Use for safe DC/AC voltage and current, 2-wire/4-wire resistance, frequency/period, thermocouple temperature, diode, and continuity measurements; for READ/FETCh/MEASure result selection, response parsing, configuration context, status/error handling, and conditional trigger, buffer, limit, or scanner workflows.
---

# Keithley 2000 Control

Use this Skill for the Keithley Model 2000 (6½-digit) bench multimeter and its
documented SCPI/IEEE-488 or RS-232 workflows. The implementation is based on
the official *Model 2000 Multimeter User's Manual*, `2000-900-01 Rev. J / August
2010`.

DC voltage and DC current over RS-232 are `hardware-verified` /
`firmware-scoped` for one instrument (serial `0944865`, firmware `A17`/`A02`,
9600 8N1, 2026-10-20); see [Hardware verification](references/hardware-verification.md).
Every other function and interface remains `documented`.

## Non-negotiable safety rules

- Do not connect or switch measurement leads based only on a requested function.
  Confirm the circuit state, expected magnitude, input terminals, and maximum
  input first.
- For voltage, frequency, period, resistance, diode, and continuity, use the
  `INPUT HI`/`INPUT LO` path and verify the front/rear input selection. Do not
  exceed `1000 V peak` between `INPUT HI` and `INPUT LO` or the documented
  `8 × 10^7 V·Hz` voltage-frequency product limit.
- Keep common-mode voltage between `INPUT LO` and chassis ground at or below
  `500 V peak`; differential input limits do not override this limit.
- For DC/AC current, use the **front** `AMPS` and `INPUT LO` terminals. The AMPS
  input is protected by a `3 A, 250 V` fast-blow fuse; do not exceed `3 A` or
  `250 V`. Never automatically select current when the external circuit state is
  unknown. Fuse condition is not queryable and remains `UNVERIFIED` without a
  suitable test.
- Treat high-energy circuits as a separate safety problem. A current or low-
  impedance range can short a source even when the intended measurement is
  voltage. Stop and require an operator-approved connection procedure.
- Do not replace a fuse through software. If replacement is required, power off,
  disconnect line power, leads, and other equipment, and use the same fuse type
  and rating as the manual specifies.
- Do not use `*OPC?` while `:INITiate:CONTinuous ON` is active: the manual warns
  this can lock the instrument. Do not send `*RST` merely as cleanup; it does
  not clear the error queue and can cancel a pending operation-complete query.
- Do not disable autozero casually. If using `:SYSTem:AZERo:STATe`, first enter
  idle (`:INITiate:CONTinuous OFF`, then `:ABORt`), record the prior state, and
  restore autozero after the authorized operation.
- A numerical response is not proof of a valid measurement. Preserve the raw
  bytes and configuration context, and classify overloads, missing metadata,
  stale fetches, and incomplete sequences conservatively.

## Evidence and scope

Read the task-specific reference instead of loading every command detail:

| Goal | Reference |
|---|---|
| Select a safe basic measurement and its terminals | [Basic measurement methods](references/basic-measurements.md) |
| Open a remote session, choose a read command, or diagnose errors | [SCPI remote workflow](references/scpi-remote-workflow.md) |
| Configure range, resolution, NPLC, filter, units, or math context | [Measurement configuration](references/measurement-configuration.md) |
| Use trigger, buffer, limit, or scanner features | [Conditional acquisition](references/conditional-acquisition.md) |
| Understand parser stages, statuses, and manual provenance | [Response and evidence](references/response-and-evidence.md) |
| Check what a real Model 2000 returned, and what stays unverified | [Hardware verification](references/hardware-verification.md) |

The local evidence file is `ref/2000-900_J-Aug2010_User.pdf`. It is a copy of
the official Keithley/Tektronix document available at
<https://download.tek.com/manual/2000-900_J-Aug2010_User.pdf>. Cite the manual
as Rev. J / August 2010 and include the PDF physical page in reports. The PDF
metadata records a 2011-10-12 build date; this is not a firmware or hardware
verification date.

## Device boundary

- **Instrument**: Keithley Instruments Model 2000 Multimeter.
- **Interfaces**: one selected remote interface at a time: IEEE-488/GPIB or
  RS-232. The interface and command language are selected from the front panel
  and stored in nonvolatile memory; they are not safely inferred or changed by
  a remote command.
- **Language**: the workflows here require SCPI. `*IDN?` identifies the model,
  serial, and firmware, but does **not** prove that SCPI is the selected language.
- **Primary data kind**: `scalar-measurement`; one or more readings with function,
  unit, acquisition context, raw response hash, and integrity status.
- **Support level**: `hardware-verified` / `firmware-scoped` for DC voltage and
  DC current over RS-232 (serial `0944865`, firmware `A17`/`A02`); the
  configure/read path of all eleven functions was exercised with open inputs,
  which is command evidence, not measurement accuracy. `documented` for all
  other interfaces. Do not extend one capture to another instrument, firmware,
  or interface.
- **Not automatic**: calibration, fuse diagnosis, safe probing, line-power
  changes, interface/language switching, and scanner availability.

## Standard remote session

Use one transport session and pair every query with exactly one response. Do not
send a second query while an earlier response is unread.

1. Establish the already-configured GPIB or RS-232 session with the host-side
   termination settings required by that interface. RS-232 is a direct
   straight-through DB-9 connection, not a null-modem connection; the manual
  documents 8N1, software flow control, and a factory baud rate of 4800. For
  RS-232, the manual lists `+808 ASCII only with RS-232`; use ASCII responses
  rather than attempting binary transfers. Frame responses on the configured
  terminator (the verified unit sends CR only), not on an assumed LF: a host
  reader that waits for LF can accumulate extra bytes.
2. Send `*IDN?`; preserve the raw response and record vendor, model, serial,
   firmware, interface, and timestamp.
3. Confirm with the operator or setup record that the Model 2000 is in SCPI
   language. Do not treat a successful `*IDN?` as language confirmation.
4. Query `*OPT?` when the workflow needs option-card evidence and
   `:SYSTem:FRSWitch?` when it needs front/rear-input evidence. Optionally query
   `:SYSTem:VERSion?` to record the SCPI standard revision. Record each
   query/response.
5. Clear only the status that the caller authorized. `*CLS` clears status
   registers and the error queue; `*RST` resets measurement state but does not
   clear the error queue. Prefer an explicit configuration sequence over an
   unrequested reset.
6. Drain `:SYSTem:ERRor?` / `:STATus:QUEue:NEXT?` until the exact response
   `0,No error` (allow documented whitespace/line terminators). Preserve every
   nonzero error, including positive Keithley messages and negative SCPI errors.
7. Configure the input function, terminal path, range, resolution, rate, and
   acquisition options before taking a reading. Query the relevant settings back
   when the result matters.
8. Acquire with the command selected below. Save the raw response before parsing.
9. Query the active function separately when required: `:FUNCtion?` or a captured
   configuration snapshot. `:SENSe:DATA?` does not include the function name.
10. Drain the error queue again and attach the final state to the measurement
    envelope. Do not silently retry a failed query or merge a later response.

## Read-command decision

| Need | Preferred sequence | Important semantics |
|---|---|---|
| Fresh one-shot reading with explicit function | `:CONFigure:<function>` then `:READ?` | `READ?` performs `ABORt; INITiate; FETCh?`; readings are stored in the buffer. If continuous initiation is ON, `:INITiate` is ignored and queues `-213,"Init ignored"` while `:FETCh?` still returns a value: that value is a continuous-acquisition result, not a newly triggered one. |
| Fresh one-shot reading with the instrument selecting the function | `:MEASure:<function>?` | Convenience command performs `ABORt; CONFigure; READ?`; it resets/overrides math, buffer, scan, and continuous-trigger context. |
| Retrieve the latest post-processed value | `:FETCh?` | Does not trigger; may return the same old reading repeatedly. It can miss readings with rapid external triggers. |
| Retrieve the latest raw or REL-adjusted value | `:SENSe:DATA?` | Does not return math results or the function name; pair with `:FUNCtion?` and a configuration snapshot. |
| Require a new value | Prefer an explicit one-shot `:READ?` sequence | The supplied Rev. J PDF mentions `:DATA:FRESh?` only as a cross-reference on p.135; it does not include its command description. Do not rely on it without matching firmware documentation or hardware verification. |
| Repeated readings | Configure trigger/sample count or continuous initiation, then use the documented fetch/buffer path | Do not combine `:INITiate:CONTinuous ON` with `:READ?` or an unsafe `*OPC?` sequence. Check `:INITiate:CONTinuous?` and drain `-213` before trusting a `:READ?` as newly triggered. `-213` also appears when `:INITiate` is sent while the instrument is not idle (for example an armed `BUS` trigger). |

For each artifact record the command sequence, raw bytes, response order,
function, unit, terminal/input selection, range/auto-range, digits, NPLC or
rate, filter/bandwidth, math/REL state, trigger/buffer state, instrument
identity, interface, parser version, and manual citation. If those fields are
not available, report the reading but retain `acquisition_completeness:
UNVERIFIED` or `INCOMPLETE` as appropriate.

### Basic one-shot SCPI example

Use separate writes and consume each query response before sending the next
query. This documented example assumes SCPI is already selected and the operator
has authorized changing the active measurement setup:

```text
:SENSe:FUNCtion 'VOLTage:DC'
:SENSe:VOLTage:DC:RANGe:AUTO ON
:READ?
```

Save the exact `:READ?` response bytes, then query the active function and
`:SYSTem:ERRor?`. Do not run this over a session with an unread query response.
For a compact one-shot, `:MEASure:VOLTage:DC?` is documented, but it resets the
selected function settings and disables math, buffer, scan, and continuous
initiation context; use it only when that state change is intended.

## Offline parsers

Use `scripts/keithley2000_scalar.py` for saved ASCII response bytes. It is
transport-independent and never opens a socket or sends a command:

```text
python3 scripts/keithley2000_scalar.py assets/fixtures/valid-reading.txt
python3 scripts/keithley2000_scalar.py assets/fixtures/overflow-reading.txt
```

Use `scripts/keithley2000_protocol.py` for the responses that are not a single
scalar reading:

```text
python3 scripts/keithley2000_protocol.py identity assets/captures/identity.txt
python3 scripts/keithley2000_protocol.py config  saved/VOLT-DC-token.txt --query ':FUNCtion?'
python3 scripts/keithley2000_protocol.py queue   saved/queue-drain.txt
```

It parses `*IDN?` into vendor/model/serial/digital+display firmware (and flags
whether the identity matches the recorded capture), classifies configuration
readbacks (`"VOLT:DC"`, `1010.000000`, `1`, `READ,,`), and parses a whole
multi-line error-queue drain in order. It also supplies `default_unit()` /
`sense_path()` / `assess_reading()` so the caller does not have to hand-map
function tokens or guess whether a reading was newly triggered.

The parser stages are deliberately separate:

```text
read_frame(raw)              -> line frame, terminator/trailing evidence
parse_metadata(frame)        -> numeric/status/unit/channel tokens
extract_payload(metadata)    -> raw reading fields
normalize(metadata, payload) -> scalar-measurement artifact
validate(artifact, raw, frame) -> COMPLETE/INCOMPLETE/INVALID/UNVERIFIED/UNSUPPORTED
```

The default parser accepts the documented ASCII reading shape produced by
`:FORMat:DATA ASCII` and `:FORMat:ELEMents` combinations:

- reading only: `+1.000000E+01VDC`
- reading with channel/unit element: `+1.000000E+01VDC, 0INTCHAN` (the channel
  number and `INTCHAN`/`EXTCHAN` marker form one token).
- The function and acquisition context are supplied separately; multi-field
  comma-separated test metadata is not supported by this parser.
- The verified unit leaves the factory `:FORMat:ELEMents READ,,` selected, so
  `:READ?` returns a bare `+2.52756984E+01` with no unit. Supply `--unit VDC`
  from the configuration record, or select `:FORMat:ELEMents READ,CHAN,UNIT`
  to get `+2.52742641E+01VDC,00INTCHAN`; without either, the parser correctly
  reports `INCOMPLETE` / `unit_missing`.

It preserves the complete original bytes and SHA-256. It recognizes the
documented overflow sentinel `9.9E37` (with optional sign, with or without a
unit suffix) as `OVERFLOW`/`UNVERIFIED`, never as a finite measurement. Empty,
unterminated, malformed, non-finite, missing-unit,
and trailing-byte cases fail closed. CSV/multi-reading responses with ambiguous
element boundaries and IEEE-754 `SREAL`/`DREAL` responses are not guessed by the
scalar parser; report `UNSUPPORTED` or use a separately documented framing
implementation. Automatic error-queue detection recognizes only `0,No error`
and `±350, Queue Overflow`; pass `--response-type error-queue` to parse other
error messages.

## Live session helper (optional)

`scripts/keithley2000_session.py` is the only bundled script that opens the
port. It uses 8N1 with no flow control, writes one command at a time terminated
by CR, and consumes exactly one CR/LF-terminated response per query. pyserial is
imported lazily; `--dry-run` prints the exact bytes without opening anything.

```text
python3 scripts/keithley2000_session.py identify
python3 scripts/keithley2000_session.py errors
python3 scripts/keithley2000_session.py read --function VOLT:DC --count 3 --output captures/
python3 scripts/keithley2000_session.py read --function VOLT:DC --no-configure
python3 scripts/keithley2000_session.py walk --confirm-open-input --output captures/
python3 scripts/keithley2000_session.py query ':FUNCtion?'
python3 scripts/keithley2000_session.py write ':CONFigure:VOLT:DC'
python3 scripts/keithley2000_session.py unblock
```

Guards, all verified against the 2026-10-20 capture:

- `read`/`walk` refuse `CURR:DC`/`CURR:AC` unless `--allow-current` is given,
  because the AMPS/INPUT LO path must already be wired in series by the
  operator; the tool never assumes that wiring.
- `walk` requires `--confirm-open-input`, since it expects disconnected leads
  and reports overflow as the correct result.
- `*RST`, `*CLS`, `:SYSTem:PRESet`, `:CALibration...`,
  `:SYSTem:AZERo:STATe`, and `:INITiate:CONTinuous` are refused unless
  `--allow-state-change` is given.
- `--no-configure` reads the current setup untouched; with continuous
  initiation ON this reproduces `-213` and the result is reported `UNVERIFIED`
  with freshness `not_newly_triggered`.
- A timed-out query means the session is desynchronised; do not retry it. An
  armed `BUS`/`EXTernal` trigger with a pending `:FETCh?` blocks the output
  queue and every later query. Run `unblock` (device clear `0x03`, then
  `*IDN?`), restore `:TRIGger:SOURce IMMediate`, and drain the error queue.
  `:ABORt` alone did not clear the blocked queue on the verified unit.
- Range/threshold writes are function-specific: frequency and period use
  `:SENSe:<fn>:THReshold:VOLTage:RANGe`, continuity uses
  `:SENSe:CONTinuity:THReshold`, diode uses `:SENSe:DIODe:CURRent:RANGe`, and
  temperature has no range. `:SENSe:FREQuency:RANGe?` is not a Model 2000
  command and returns no response (a session timeout), so never generalize the
  voltage/current/resistance range syntax.

## Conditional advanced features

Load [Conditional acquisition](references/conditional-acquisition.md) before
using any of these:

- trigger sources, delay, external trigger, sample/measure counts, or continuous
  initiation;
- reading hold/autosettle;
- `:TRACe`/`:DATA` buffer storage and statistics;
- `:CALCulate3` limit testing;
- internal/external scanner cards and `:ROUTe`/`:SCAN` operations.

Gate scanner workflows with `*OPT?` and the actual card/switch topology. Gate
temperature workflows with thermocouple type and reference-junction settings.
Gate all repeated acquisition with expected counts, buffer markers, error/state
registers, and an explicit end-of-sequence check.

## Integrity and support reporting

Use these statuses conservatively:

- `COMPLETE`: framing, required fields, expected count, and applicable status
  checks pass for the stated claim.
- `INCOMPLETE`: required response, unit, count, terminator, or sequence evidence
  is missing.
- `INVALID`: framing, numeric, ordering, or declared/observed constraints
  contradict the raw bytes.
- `UNVERIFIED`: parsing succeeded but freshness, calibration, fuse state,
  configuration, or acquisition completeness is not proven.
- `UNSUPPORTED`: this Skill does not implement the response format or feature
  prerequisite.

Never call a valid-looking number calibrated, fresh, complete, or hardware
verified without the corresponding evidence. Keep `documented`,
`hardware-verified`, and `firmware-scoped` as evidence labels, not feature
counts. The current hardware evidence covers DC voltage and DC current over
RS-232 on serial `0944865`, firmware `A17`/`A02`, tested 2026-10-20; raw
captures and the exact scope are in
[Hardware verification](references/hardware-verification.md).

Floating and no-signal inputs produce plausible-looking numbers: an open
`INPUT HI`/`INPUT LO` autoranges to 100 mV and reports tens of millivolts,
`FREQuency`/`PERiod` report `0` rather than overflow, and open resistance,
continuity, diode, and temperature inputs report `+9.9E37`. Confirm the input is
actually connected before treating any of these as a measurement.

## Verification commands

Run from the repository root:

```bash
python3 -m unittest discover -s skills/keithley-2000-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/keithley-2000-control
npx skills@latest add . --list
```

Tests must use saved fixtures only. They must never connect to a real Model
2000.
