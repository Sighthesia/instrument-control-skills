# Hardware verification record

Scope: one Keithley Model 2000, one RS-232 session. Live-source (quantitative)
evidence covers DC voltage and DC current; the configuration and read path of
all eleven front-panel functions was exercised with open inputs. Everything not
listed here remains `documented`.

Evidence: *Model 2000 Multimeter User's Manual*, `2000-900-01 Rev. J / August
2010`; PDF physical pages 85-87 (RS-232), 121-126 (`:READ?`, `:INITiate`),
134-138 (configure), 159-162 (format elements), 169 (`:SENSe:DATA?`), 190-194
(error queue), 212 (`+808`).

## Instrument and transport

| Field | Observed value |
|---|---|
| `*IDN?` (raw) | `KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  ` |
| Vendor / model | Keithley Instruments / Model 2000 |
| Serial | `0944865` |
| Firmware | `A17` / `A02` (digital / display) |
| Interface | RS-232, straight-through DB-9, 9600 baud, 8N1, no flow control |
| Command set | SCPI (`:SYSTem:VERSion?` → `1991.0`) |
| Options (`*OPT?`) | `0,0` (no switch card reported) |
| Input path (`:SYSTem:FRSWitch?`) | `1` (front terminals) |
| Host | Linux, `pyserial 3.5` |
| Test date | 2026-10-20 (`2026-10-20T05:51:33Z` capture start) |
| Source under test | ~25.2 V nominal DC from an external supply, `INPUT HI`/`INPUT LO` |
| Current under test | same supply feeding a load through the meter, front `AMPS` + `INPUT LO` in series |

Raw bytes for every response below are in `assets/captures/`, with the full
ordered exchange in `assets/captures/session.json`.

## Confirmed behaviours

| Behaviour | Command | Raw response |
|---|---|---|
| Identity parses into 4 comma fields | `*IDN?` | `KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02  \r` |
| Front input selected | `:SYSTem:FRSWitch?` | `1\r` |
| Empty error queue is quoted | `:SYSTem:ERRor?` | `0,"No error"\r` |
| DCV one-shot reading | `:READ?` | `+2.52756984E+01\r` |
| Active function, quoted token | `:FUNCtion?` | `"VOLT:DC"\r` |
| Autorange resolved to 100 V | `:SENSe:VOLTage:DC:RANGe?` | `100.000000\r` |
| Undefined header is queued, not silently dropped | `:BOGUS:COMMand` | `-113,"Undefined header"\r` |
| Reading with `READ,CHAN,UNIT` elements | `:READ?` | `+2.52742641E+01VDC,00INTCHAN\r` |

Ten consecutive `:READ?` values with `:INITiate:CONTinuous OFF`, autorange, and
NPLC 1 spanned 25.27314 V to 25.27485 V (mean 25.27402 V, population σ ≈ 0.54 mV,
≈ 68 ppm span). The task source was nominally 25.2 V; the ~0.3 % difference is
consistent with the source's own accuracy and is **not** evidence about Model
2000 calibration, which stays `UNVERIFIED`.

## DC current

Leads were moved by the operator to the front `AMPS` + `INPUT LO` terminals with
the meter in series between the supply and its load; the meter was verified on
the front path (`:SYSTem:FRSWitch?` → `1`) before acquisition. Sequence:

```text
:CONFigure:CURRent:DC
:SENSe:CURRent:DC:RANGe 3        ; top range first: lowest burden, no fuse risk
:SENSe:CURRent:DC:NPLC 1
:READ?                           ; x3
:SENSe:CURRent:DC:RANGe:AUTO ON
:READ?                           ; x3
```

Observed behaviour:

| Field | Value |
|---|---|
| `:FUNCtion?` after configure | `"CURR:DC"` |
| `:SENSe:CURRent:DC:RANGe?` after `RANGe 3` | `3.1000` (top-range full scale) |
| Error queue after every step | `0,"No error"` |
| 3 A-range readings | 0.20220 A, 0.20228 A, 0.20221 A |
| Autorange readings | 0.20225 A, 0.20220 A, 0.20219 A |
| Autorange resolution | `:SENSe:CURRent:DC:RANGe?` → `1.0000` (1 A range) |

Mean ≈ 202.22 mA, span ≈ 97 µA (≈ 480 ppm) across six readings, consistent with
a ~5 W load on the 25.2 V supply. No `-213` appeared because `:CONFigure`
leaves continuous initiation off. Nothing here verifies the 3 A fuse rating,
the meter's current calibration, or the burden-voltage error introduced into
the circuit.

## Deviation found: `:READ?` under continuous initiation

The instrument arrived free-running (`:INITiate:CONTinuous?` → `1`). In that
state every `:READ?` returned a numeric reading **and** queued
`-213,"Init ignored"`:

```text
:READ?              -> +2.52741937E+01
:SYSTem:ERRor?      -> -213,"Init ignored"
:SYSTem:ERRor?      -> 0,"No error"
```

This matches the manual: `:READ?` expands to `:ABORt; :INITiate; :FETCh?`; with
continuous initiation enabled the `:INITiate` generates an error and is ignored,
but the `:FETCh?` still executes (PDF 121-122, 125). Consequence for evidence:
the number is real but comes from the continuous acquisition, so it must not be
reported as a newly triggered reading. Pattern to use:

```text
:INITiate:CONTinuous?
* if 1 -> record it, and either accept FETCh?-quality freshness or disable it
:INITiate:CONTinuous OFF
:READ?                 ; no -213, each value is newly triggered
```

After `:MEASure:VOLTage:DC?` the error queue was clean because `:CONFigure`
inside `:MEASure` turns continuous initiation off, which is the documented
state change the Skill already warns about.

## Data-element note

With the factory `:FORMat:ELEMents READ,,` (confirmed by query), `:READ?`
returns a bare numeric line with no unit, so the offline parser reports
`INCOMPLETE` / `unit_missing` unless the caller supplies `--unit`. Setting
`:FORMat:ELEMents READ,CHAN,UNIT` yields `+2.52742641E+01VDC,00INTCHAN`, which
the parser classifies `COMPLETE` with `unit_source: response`. The observed
channel field has two digits (`00INTCHAN`); the manual's one-digit example
(`0INTCHAN`) is also accepted.

## RS-232 framing note

Responses on this session end with a single CR (`0x0D`) and no LF. A host
reader that waits for LF can over-read: an early probe that used
`serial.readline()` accumulated three copies of the `*IDN?` line. Read until CR
and pair exactly one response with each query.

## Function walk with disconnected leads

With every lead removed, all eleven front-panel functions were configured and
read in sequence (`:CONFigure:<function>` → `:READ?` → `:SYSTem:ERRor?`). Every
step answered `0,"No error"`; raw bytes are in `assets/captures/open-inputs/`
with `session-open-inputs.json`.

| Function | Config readback | `:READ?` | Interpretation |
|---|---|---|---|
| `VOLTage:DC` | FS `1010.000000`, autorange `1` | `-5.73E-02` | floating input on the 100 mV range; meaningless |
| `VOLTage:AC` | FS `757.500000`, autorange `1` | `+1.69E-03` | AC pickup on open leads |
| `CURRent:DC` | FS `3.1000`, autorange `1` | `-2.36E-08` | no current path |
| `CURRent:AC` | FS `3.1000`, autorange `1` | `+2.91E-03` | AC-current offset at 3.1 A FS |
| `RESistance` | FS `120000000.0`, autorange `1` | `+9.9E37` | open circuit → overflow |
| `FRESistance` | FS `120000000.000`, autorange `1` | `+9.9E37` | open circuit → overflow |
| `FREQuency` | threshold `10.000000` | `+0.00E+00` | no signal; **not** a valid 0 Hz |
| `PERiod` | threshold `10.000000` | `+0.00E+00` | no signal; **not** a valid 0 s |
| `CONTinuity` | threshold `10.0` | `+9.9E37` | open circuit → overflow |
| `DIODe` | current range `0.00100` (1 mA) | `+9.9E37` | open → above 10 V → overflow |
| `TEMPerature` | TC type `J` | `+9.9E37` | no thermocouple on the terminals |

Consequences for evidence:

- The overflow sentinel appears on real bytes; the offline parser returns
  `reading_status: OVERFLOW`, `integrity: UNVERIFIED`, `value: null`. Never
  convert it to a finite number or to "0 Ω".
- Frequency and period report `0` instead of overflow. A parser cannot tell
  that apart from a genuine 0 Hz; treat `0` Hz/0 s as no-signal unless the
  input amplitude requirement (signal above 10 % of the selected voltage range)
  is separately established.
- DC voltage autoranges down to 100 mV on an open input and then reports tens of
  millivolts of drift (−16 mV to −57 mV over three reads). A disconnected or
  floating input must not be reported as a measured voltage.
- Setting `:SENSe:DIODe:CURRent:RANGe 1e-4` read back `0.00010`, confirming the
  documented three-range diode bias control.

## Bundled helper checks

The same session was re-run through `scripts/keithley2000_session.py` on
2026-10-20:

- `identify` parsed the identity and reported `matches recorded capture: True`.
- `walk --confirm-open-input --output ...` reproduced the open-input table above
  and wrote one raw file per function plus `walk.json` and a session log.
- `read --function VOLT:DC --no-configure` with continuous initiation ON
  returned a value **and** reported `flags=['init_ignored']`, status
  `UNVERIFIED`, freshness `not_newly_triggered` — the workflow gap that a
  hand-run parser leaves open.
- `read --function CURR:DC` was refused without `--allow-current`, and `walk`
  without `--confirm-open-input`; `*RST` and `:INITiate:CONTinuous` were
  refused without `--allow-state-change`.
- `unblock` sent the device clear on a healthy link, verified `*IDN?`, and left
  continuous initiation and the error queue unchanged.
- `config` applied NPLC 0.5, DIGits 6, a moving filter with count 5, and a
  0.05 V REL reference, read every value back, then restored NPLC 1, DIGits 7,
  filter off, and REL off; `config --rel-acquire` captured the latest reading
  (`-0.263604 V`) as the reference.
- `constants` reproduced the table above and reported the calibration due date
  as overdue.
- A second concurrent session was refused with "serial port is already open
  by another session"; the exclusive `flock` prevents interleaved readbacks.
- The frequency/period range readback is
  `:SENSe:<fn>:THReshold:VOLTage:RANGe?`. Writing the voltage/current/resistance
  form (`:SENSe:FREQuency:RANGe?`) is invalid: the firmware returns **no
  response**, which the transport reports as a timeout and treats as a
  desynchronised session.

## Error 213: two causes, one blocked-queue trap

`-213,"Init ignored"` has two distinct causes, both confirmed on 2026-10-20:

| Cause | Sequence | Queue |
|---|---|---|
| Continuous initiation ON | `:INITiate:CONTinuous ON` then `:READ?` (or `:INITiate`) | `-213` then `0,"No error"`; `:FETCh?` still returns the free-running value |
| Instrument not idle | `:TRIGger:SOURce BUS`, `:INITiate` (armed), `:INITiate` again | `-213`; the first acquisition is still armed |

`-213` is therefore intermittent between scripts without any firmware fault:
whether it appears depends on the state the previous script left behind.
`:CONFigure` and `:MEASure` disable continuous initiation, so scripts that
configure first are clean; scripts that issue `:READ?` against the operator's
free-running setup queue `-213` every time. `:ABORt` does not help while
continuous initiation is on, because the operation restarts at the top of the
trigger model.

The second cause has an extra hazard. With an armed `BUS` trigger, a pending
`:FETCh?` never completes, so the output queue stays blocked and **every**
subsequent query times out:

```text
:INITiate            (TRIGger:SOURce BUS, armed)
:FETCh?              -> no response (timeout)
*IDN?                -> no response (timeout)
:ABORt               -> still no response
0x03 (device clear)  -> instrument replies "DCL" and the link works again
```

Recovery used on the verified unit: send `0x03`, then restore
`:TRIGger:SOURce IMMediate` and re-check `:SYSTem:ERRor?`. The bundled session
helper exposes this as `unblock`. Treat a timeout as a desynchronised session —
never retry the same query and merge whatever arrives later.

## Rate, resolution, REL, filter, and instrument constants

Read-only queries and configuration sweeps on 2026-10-20, leads disconnected,
RS-232. Evidence: `assets/captures/rate-filter-rel-digits/` (`results.json`,
`exchange.txt`, `session-characteristics.json`, `instrument-constants.txt`).
Every step ended with `0,"No error"`.

### Rate (NPLC)

Fixed 10 V range; five `:READ?` calls per setting; host-measured wall time:

| NPLC | readback | autozero OFF | autozero ON |
|---|---|---|---|
| 0.01 | 0.01 | 40.4 ms | - |
| 0.1 | 0.10 | 41.4 ms | - |
| 1 | 1.00 | 59.7 ms | 66.8 ms |
| 10 | 10.00 | 239.0 ms | 649.4 ms |

The ~40 ms floor is command/trigger/serial overhead at 9600 baud, so 0.01 and
0.1 PLC are indistinguishable end-to-end. At 50 Hz, 1 PLC is 20 ms and 10 PLC
is 200 ms; the rest is autozero and host overhead. With autorange enabled on an
open input, 10 PLC reads ranged from about 0.65 s to 1.88 s, so fix the range
before measuring rate.

### DIGits

`:DIGits?` read back 4, 5, 6, and 7 exactly after each write. Every reading
string still carried 9 significant digits (for example `-3.86448877E+00`), so
DIGits changes display resolution only, not the remote reading format - as the
manual states (PDF 52).

### REL (reference)

Exercised on DC current with the current input open (functional check only; no
current source):

| State | Result |
|---|---|
| baseline, REL off | mean `-2.568E-08 A` over 5 reads |
| `:REFerence 0.05`, `:STATe ON` | mean `-0.050000 A` over 3 reads (delta `-0.050000 A`) |
| `:REFerence:STATe OFF` | mean `-3.17E-08 A` |
| `:REFerence:ACQuire` | reference became `-3.3000081E-08`; next reads mean `8.5E-09 A` |

### Filter

DCI open input, NPLC 0.1, count 10, 20 `:FETCh?` samples per mode:

| Mode | stdev |
|---|---|
| OFF | 555 nA |
| MOVing | 269 nA |
| REPeat | 191 nA |

State, type, and count read back correctly. The open current input is not a
calibrated noise source; this shows the filter is applied and reduces scatter,
not a specified noise-rejection figure.

### Instrument constants (query-only)

| Query | Response |
|---|---|
| `*IDN?` | `KEITHLEY INSTRUMENTS INC.,MODEL 2000,0944865,A17  /A02` |
| `*OPT?` | `0,0` (no scanner option reported) |
| `:SYSTem:VERSion?` | `1991.0` |
| `:SYSTem:LFRequency?` | `50` |
| `:SYSTem:FRSWitch?` | `1` (front inputs) |
| `:SYSTem:POSetup?` | `SAV0` |
| `:SYSTem:AZERo:STATe?` | `1` |
| `:CAL:PROT:COUN?` | `6` |
| `:CAL:PROT:DATE?` | `2008,06,20` |
| `:CAL:PROT:NDUE?` | `2009,06,20` |
| `:CAL:PROT:LOCK?` | `0` (locked) |

The calibration due date is in the past (2009-06-20); this records calibration
metadata only, not accuracy or drift. Lock state `0` means locked, so a
calibration write needs an explicit unlock procedure. No calibration command
other than these queries was sent.

## Not verified

- Calibration constants, adjustment procedures, and accuracy after the 2009 due date (only count/date/due/lock metadata was read); input-fuse continuity, thermal EMF, and long-term drift.
- AC voltage/current, resistance, 4-wire, frequency/period, temperature, diode,
  continuity, trigger/buffer/limit/scan workflows.
- Overflow (`+9.9E37`) from a live over-range source; it was only observed from
  open-circuit resistance, continuity, diode, and temperature inputs.
- GPIB/IEEE-488, other baud rates, `*OPC?` sequencing, sample count > 1.
- Burden voltage and its effect on the DUT while the AMPS path is in series.
- Thermocouple temperature with an actual sensor connected.
