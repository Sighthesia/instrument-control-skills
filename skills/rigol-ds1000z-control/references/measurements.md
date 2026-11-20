# Measurements (DS1000Z)

Load this reference when you need a numeric measurement: which source command
selects the channel, which query spellings this firmware accepts, what the
`9.9E37` reply means, and how to record a value so it stays interpretable.

Ranges and item enumerations come from the *MSO1000Z/DS1000Z Programming Guide*,
PGA19108-1110, Software Version 00.04.03.SP2 (PDF physical pages). Values marked
`hardware-verified` were returned by `RIGOL TECHNOLOGIES,DS1074Z,
DS1ZA171004155,00.04.02.SP4`; the replies are in
`artifacts/rigol-ds1000z/raw/measurements-ch1.json`. Everything else is
`documented` and untested on that firmware.

## Two query styles, and only one of them is in the manual

| Style | Documented? | Notes |
|---|---|---|
| `:MEASure:ITEM? <item>[,<src>[,<src>]]` | Yes, PDF p. 141 | The manual's only direct measurement query |
| `:MEASure:<PARameter>?` (e.g. `:MEASure:VPP?`) | **No** | Accepted by `00.04.02.SP4`, absent from the manual's `:MEASure` command list (PDF p. 131) |

The shortcut queries are `hardware-verified` but `UNVERIFIED` against any manual:
carry both labels and prefer `:MEASure:ITEM?` when a documented path is required.
The manual's `:MEASure` command list is `:SOURce`, `:COUNter:SOURce`,
`:COUNter:VALue?`, `:CLEar`, `:RECover`, `:ADISplay`, `:AMSource`,
`:SETup:MAX/MID/MIN`, `:SETup:PSA/PSB/DSA/DSB`, `:STATistic:*`, and `:ITEM`
(PDF p. 131).

## Source selection (`:MEASure:SOURce`, PDF p. 132)

| Command | Parameter | Range / default | Page |
|---|---|---|---|
| `:MEASure:SOURce <sour>` / `?` | Discrete | `{CHANnel1..CHANnel4\|D0..D15\|MATH}`, default `CHANnel1`; echoes `CHAN1`..`CHAN4`, `D0`..`D15`, `MATH` | 132 |
| `:MEASure:COUNter:SOURce <sour>` / `?` | Discrete | `{CHANnel1..CHANnel4\|D0..D15\|OFF}`, default `OFF` | 132 |
| `:MEASure:COUNter:VALue?` | — | Frequency counter result in Hz; returns `0.0000000e+00` when the counter is off | 133 |

- Analog channels may be selected whether or not they are displayed (PDF
  p. 132) — and that is exactly how the `9.9E37` sentinel appears (see below).
- `:MEASure:SOURce` does **not** cover delay or phase; those need
  `:MEASure:SETup:DSA`/`DSB` or `:MEASure:SETup:PSA`/`PSB` (PDF pp. 136-138).
- `:MEASure:COUNter:VALue?` is a separate path from `:MEASure:FREQuency?`: the
  counter uses its own source and answers `1.0000066e+03` where
  `:MEASure:FREQuency?` answered `9.999999e+02` on the same 1 kHz signal
  (`hardware-verified`). Record which one produced a frequency.

## Shortcut queries accepted by this firmware (`hardware-verified`)

All of these returned NR3 numbers in one sweep with `:MEASure:SOURce CHANnel1`
(1 kHz square, 0-3 V):

```text
:MEASure:VPP?       3.040000e+00     :MEASure:VMAX?      3.000000e+00
:MEASure:VMIN?      -4.000000e-02    :MEASure:VAVG?      1.493662e+00
:MEASure:VAMP?      2.916700e+00     :MEASure:VRMS?      2.082721e+00
:MEASure:VTOP?      2.952131e+00     :MEASure:VBASe?     3.098358e-02
:MEASure:OVERshoot? 1.638704e-02     :MEASure:PREShoot?  1.745327e-02
:MEASure:FREQuency? 9.999999e+02     :MEASure:PERiod?    1.000000e-03
:MEASure:PDUTy?     5.039999e-01     :MEASure:NDUTy?     4.960000e-01
:MEASure:PWIDth?    5.040000e-04     :MEASure:NWIDth?    4.960000e-04
:MEASure:COUNter:VALue? 1.0000066e+03
```

Accepted, and rejected, spellings differ inside the same family — do not
generalize from a working name:

| Rejected on `00.04.02.SP4` (`command error`) | Correct documented spelling |
|---|---|
| `:MEASure:+DUTy?` / `:MEASure:-DUTy?` | `:MEASure:PDUTy?` / `:MEASure:NDUTy?` |
| `:MEASure:+PULses?` / `:MEASure:-PULses?` | `PPULses` / `NPULses` items |
| `:MEASure:+EDGes?` / `:MEASure:-EDGes?` | `PEDGes` / `NEDGes` items |
| `:MEASure:PHASe?` | `RPHase` / `FPHase` items |
| `:MEASure:RISetime?` / `:MEASure:FALLtime?` | `RTIMe` / `FTIMe` items |
| `:MEASure:VAVerage?` | `VAVG` (shortcut works) |
| `:MEASure:COUNter?` | `:MEASure:COUNter:VALue?` |
| `:MEASure:STATistic:ITEM?` (statistics not enabled) | Enable `:MEASure:STATistic:DISPlay` first |

The rejected names are the ones a programmer familiar with other Rigol families
would guess; a `command error` here is an evidence result, not a transport fault.

## Items accepted by `:MEASure:ITEM?` (PDF pp. 140-141)

The `<item>` enumeration is identical for `:MEASure:ITEM` and
`:MEASure:STATistic:ITEM` (PDF pp. 140-141), 37 parameters in total:

```text
VMAX VMIN VPP VTOP VBASe VAMP VAVG VRMS OVERshoot PREShoot MARea MPARea PERiod
FREQuency RTIMe FTIMe PWIDth NWIDth PDUTy NDUTy RDELay FDELay RPHase FPHase TVMAX
TVMIN PSLEWrate NSLEWrate VUPper VMID VLOWer VARIance PVRMS PPULses NPULses
PEDGes NEDGes
```

- `[,<src>[,<src>]]` is optional; when omitted the source is the one set by
  `:MEASure:SOURce` (PDF p. 141). When given, `PERiod`, `FREQuency`, `PWIDth`,
  `NWIDth`, `PDUTy`, `NDUTy`, `RDELay`, `FDELay`, `RPHase`, `FPHase` also accept
  `D0`-`D15`; every other item accepts only `CHANnel1`..`CHANnel4` or `MATH`.
- `RDELay`, `FDELay`, `RPHase`, `FPHase` require **two** sources; omitting them
  makes the command invalid, and the defaults come from
  `:MEASure:SETup:DSA`/`DSB` or `PSA`/`PSB` (PDF p. 141).
- Observed: `:MEASure:ITEM? VPP` → `3.040000e+00` and
  `:MEASure:ITEM? FREQuency` → `9.999999e+02` (`hardware-verified`). The manual
  says the query "returns the measurement result in scientific notation"
  (PDF p. 141); keep the raw reply bytes so a reader can see whether the
  firmware echoed the item name.
- `:MEASure:ITEM? RTIMe` returned `9.9E37` on this unit — the item name is
  accepted, but no result was available at that vertical scale
  (`hardware-verified`). `9.9E37` is not a rise time.

## `9.9E37` means "no result", never zero

With `:MEASure:SOURce CHAN2` while CH2 was not displayed, `:MEASure:VPP?` and
`:MEASure:FREQuency?` both returned `9.9E37` (`hardware-verified`).

- Map `9.9E37` (and any `9.9e37` variant) to `INCOMPLETE` with the reason
  "no result / channel not displayed". A `float(reply)` pipeline turns this into
  a plausible-looking 9.9e37 reading; never cast before checking the sentinel.
- `0.0000000e+00` from `:MEASure:COUNter:VALue?` is different: it is the
  documented reply when the counter is disabled (PDF p. 133), so report it as
  "counter off", not as a measurement.
- A real number is also not proof of a valid setup: the instrument measures
  whatever the channel is configured to show.

## Units the replies do not state

NR3 replies carry no unit, and two of them are easy to mislabel
(`hardware-verified`):

- `:MEASure:PDUTy?` = `5.039999e-01` and `:MEASure:NDUTy?` = `4.960000e-01` are
  **fractions**, not percent. The manual defines +Duty as "the ratio of the
  positive pulse width to the period" (PDF p. 128).
- `:MEASure:OVERshoot?` = `1.638704e-02` and `:MEASure:PREShoot?` = `1.745327e-02`
  also came back as fractions of the amplitude while the manual defines them as a
  "ratio" (PDF p. 130). Report the raw token and let the caller scale it.

Voltage items are in the current `:CHANnel<n>:UNITs` unit, not necessarily volts
(PDF p. 31). Frequency is Hz, period/width/delay are seconds, phase is degrees
(PDF p. 129), and area items are volt-seconds (PDF p. 131).

## Statistics subsystem: present in the manual, not implemented here

| Command | Range / default | Page |
|---|---|---|
| `:MEASure:STATistic:DISPlay <bool>` / `?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | 138 |
| `:MEASure:STATistic:MODE <mode>` / `?` | `{DIFFerence\|EXTRemum}`, default `EXTRemum`; echoes `DIFF` or `EXTR` | 139 |
| `:MEASure:STATistic:RESet` | — | 139 |
| `:MEASure:STATistic:ITEM <item>[,<src>[,<src>]]` / `:MEASure:STATistic:ITEM? <type>,<item>[,…]` | `<type>` = `{MAXimum\|MINimum\|CURRent\|AVERages\|DEViation}`, default none | 140 |

The statistics must be enabled before a result query means anything. On the
evidence unit with statistics **not** enabled, `:MEASure:STATistic:ITEM?
MAXimum,VPP` returned `command error` and the error queue then showed
`-410,"Query INTERRUPTED"` (`hardware-verified`). This Skill does not implement
the statistics subsystem: it sends no `:MEASure:STATistic:*` write, reports
statistics as `UNSUPPORTED`, and does not retry the failed query.

## Other `:MEASure` commands (documented, not used by this Skill)

| Command | Purpose | Page |
|---|---|---|
| `:MEASure:ADISplay <bool>` / `?` | All-measurement screen panel (29 parameters at once) | 134 |
| `:MEASure:AMSource <src>[,<src>...]` / `?` | Sources for the all-measurement panel | 134 |
| `:MEASure:CLEar <item>` | Clear one of the last five enabled items (`ITEM1..ITEM5`, `ALL`) | 133 |
| `:MEASure:RECover <item>` | Restore a cleared item | 133 |
| `:MEASure:SETup:MAX` / `MID` / `MIN` | Threshold levels for time measurements | 135-136 |
| `:MEASure:SETup:PSA` / `PSB` | Phase-measurement sources | 136-137 |
| `:MEASure:SETup:DSA` / `DSB` | Delay-measurement sources | 137-138 |

These change the on-screen measurement panel or the threshold definition used by
`RTIMe`, `FTIMe`, `PDUTy`, and similar items. Because the thresholds alter the
number, a threshold change must be recorded with the value; since this Skill does
not set them, it records that they are at whatever the operator left.

## Recording a measurement

A measurement value must travel with the acquisition context, or it is not
reproducible:

```text
*IDN?
:MEASure:SOURce?                     which channel the number describes
:ACQuire:TYPE? :ACQuire:MDEPth? :ACQuire:SRATe?
:TIMebase:MAIN:SCALe? :TIMebase:MODE?
:CHANnel<n>:SCALe? :OFFSet? :COUPling? :PROBe? :BWLimit? :INVert? :VERNier?
:TRIGger:SWEep? :TRIGger:EDGe:SOURce? :TRIGger:EDGe:LEVel? :TRIGger:EDGe:SLOPe?
:SYSTem:ERRor?                       drained until 0,"No error"
```

- `:CHANnel<n>:VERNier?` and `:CHANnel<n>:INVert?` matter: an inverted channel
  inverts the reported voltage, and fine adjust can leave the scale on a
  non-1-2-5 value.
- `:TRIGger:SWEep AUTO` means the record was not necessarily triggered; a
  frequency or duty-cycle result from an untriggered frame is a statement about
  the displayed window, not about a stable signal.
- Drain the error queue after a measurement sweep. A `command error` is 13 bytes
  with no terminator, so a reader that waits for LF stalls; the queued
  `-113,"Undefined header"` makes the failure auditable afterwards.

## Statuses for this workflow

- `COMPLETE`: a numeric NR3 reply, source confirmed, and the context above
  recorded.
- `INCOMPLETE`: `9.9E37`, counter-disabled `0.0`, or a context field missing.
- `INVALID`: the reply is not NR3 (for example the literal `command error`) or
  the unit contradicts the item.
- `UNVERIFIED`: the value came from a shortcut query that no manual documents,
  or from a setup whose thresholds or trigger state were not confirmed.
- `UNSUPPORTED`: statistics, delay/phase with two sources, and all-measurement
  panel control.

## CLI

```text
python3 scripts/ds1000z_protocol.py measurement assets/fixtures/measurement-vpp.txt --quantity vpp
python3 scripts/ds1000z_session.py --host 10.99.0.194 --allow-writes measurement --quantity vpp --channel 1
```

`--quantity` accepts `vpp`, `vmax`, `vmin`, `vavg`, `vamp`, `vrms`, `vtop`,
`vbase`, `overshoot`, `preshoot`, `frequency`, `period`, `pduty`, `nduty`,
`pwidth`, `nwidth`, `counter`, `rtime`, `ftime` (plus the aliases `pk2pk` and
`freq`); an unknown quantity fails with status `INVALID` and reason
`quantity_unknown` instead of being sent. The parser maps `9.9E37` to
`INCOMPLETE` with reason `no_measurement_result_sentinel`. The live
`measurement` subcommand sets `:MEASure:SOURce` only when `--channel` is given,
and that write needs `--allow-writes`.
