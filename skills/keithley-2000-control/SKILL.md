---
name: keithley-2000-control
description: Control and document measurement workflows for a Keithley Model 2000 bench multimeter using its documented SCPI command set. Use for safe DC/AC voltage and current, 2-wire/4-wire resistance, frequency/period, thermocouple temperature, diode, and continuity measurements; for READ/FETCh/MEASure result selection, response parsing, configuration context, status/error handling, and conditional trigger, buffer, limit, or scanner workflows.
---

# Keithley 2000 Control

Use this Skill for the Keithley Model 2000 (6½-digit) bench multimeter and its
documented SCPI/IEEE-488 or RS-232 workflows. The implementation is based on
the official *Model 2000 Multimeter User's Manual*, `2000-900-01 Rev. J / August
2010`; it is `documented` only until a real instrument response is captured with
model, firmware, interface, and test date.

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
- **Support level**: `documented`; no hardware response is bundled. Upgrade to
  `hardware-verified` only after preserving the raw exchange and exact identity.
- **Not automatic**: calibration, fuse diagnosis, safe probing, line-power
  changes, interface/language switching, and scanner availability.

## Standard remote session

Use one transport session and pair every query with exactly one response. Do not
send a second query while an earlier response is unread.

1. Establish the already-configured GPIB or RS-232 session with the host-side
   termination settings required by that interface. RS-232 is a direct
   straight-through DB-9 connection, not a null-modem connection; the manual
   documents 8N1, software flow control, and a factory baud rate of 4800.
2. Send `*IDN?`; preserve the raw response and record vendor, model, serial,
   firmware, interface, and timestamp.
3. Confirm with the operator or setup record that the Model 2000 is in SCPI
   language. Do not treat a successful `*IDN?` as language confirmation.
4. Query `*OPT?`, `:SYSTem:VERSion?`, and `:SYSTem:FRSWitch?` when the workflow
   needs option-card or front/rear-input evidence. Record each query/response.
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
| Fresh one-shot reading with explicit function | `:CONFigure:<function>` then `:READ?` | `READ?` performs `ABORt; INITiate; FETCh?`; readings are stored in the buffer. |
| Fresh one-shot reading with the instrument selecting the function | `:MEASure:<function>?` | Convenience command performs `ABORt; CONFigure; READ?`; it resets/overrides math, buffer, scan, and continuous-trigger context. |
| Retrieve the latest post-processed value | `:FETCh?` | Does not trigger; may return the same old reading repeatedly. It can miss readings with rapid external triggers. |
| Retrieve the latest raw or REL-adjusted value | `:SENSe:DATA?` | Does not return math results or the function name; pair with `:FUNCtion?` and a configuration snapshot. |
| Require a new value when supported | `:DATA:FRESh?` | Use only after checking the active firmware/manual behavior and the current trigger state. |
| Repeated readings | Configure trigger/sample count or continuous initiation, then use the documented fetch/buffer path | Do not combine `:INITiate:CONTinuous ON` with `:READ?` or an unsafe `*OPC?` sequence. |

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

## Offline parser

Use `scripts/keithley2000_scalar.py` for saved ASCII response bytes. It is
transport-independent and never opens a socket or sends a command:

```text
python3 scripts/keithley2000_scalar.py assets/fixtures/valid-reading.txt
python3 scripts/keithley2000_scalar.py assets/fixtures/overflow-reading.txt
```

The parser stages are deliberately separate:

```text
read_frame(raw)              -> line frame, terminator/trailing evidence
parse_metadata(frame)        -> numeric/status/unit/channel tokens
extract_payload(metadata)    -> raw reading fields
normalize(metadata, payload) -> scalar-measurement artifact
validate(artifact, raw)      -> COMPLETE/INCOMPLETE/INVALID/UNVERIFIED/UNSUPPORTED
```

The default parser accepts the documented ASCII reading shape produced by
`:FORMat:DATA ASCII` and `:FORMat:ELEMents` combinations:

- reading only: `+1.000000E+01VDC`
- reading, channel, units: `+1.000000E+01VDC,0,INTCHAN`
- an explicit test fixture may use comma-separated `value,unit,function,status,count`
  metadata to exercise validation without claiming it is a vendor response shape.

It preserves the complete original bytes and SHA-256. It recognizes the
documented overflow sentinel `+9.9E37` as `OVERFLOW`/`UNVERIFIED`, never as a
finite measurement. Empty, unterminated, malformed, non-finite, missing-unit,
and trailing-byte cases fail closed. CSV/multi-reading responses with ambiguous
element boundaries and IEEE-754 `SREAL`/`DREAL` responses are not guessed by the
scalar parser; report `UNSUPPORTED` or use a separately documented framing
implementation.

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
counts.

## Verification commands

Run from the repository root:

```bash
python3 -m unittest discover -s skills/keithley-2000-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/keithley-2000-control
npx skills@latest add . --list
```

Tests must use saved fixtures only. They must never connect to a real Model
2000.
