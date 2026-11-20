# Cursors (:CURSor)

Load this reference when you need the on-screen cursor readings: which family to
query for the current cursor mode, what the three reply shapes mean, and why a
mode switch needs a longer wait than any other write.

Manual sections are the *MSO1000Z/DS1000Z Programming Guide* (PGA19108-1110,
software version 00.04.03.SP2), PDF physical pages 32-52 (sections 2-16..2-36).
Rows marked `hardware-verified` were returned by `RIGOL TECHNOLOGIES,DS1074Z,
DS1ZA171004155,00.04.02.SP4`; the rest is `documented` only.

## The four families

| Mode (`:CURSor:MODE?`) | Family | Queries | Manual |
|---|---|---|---|
| `OFF` | none — cursors disabled | — | p. 32 |
| `MAN` | manual | `:CURSor:MANual:{TYPE,SOURce,TUNit,VUNit,AX,BX,AY,BY,AXValue,BXValue,AYValue,BYValue,XDELta,IXDELta,YDELta}?` | pp. 33-39 |
| `TRAC` | track | `:CURSor:TRACk:{SOURce1,SOURce2,AX,BX,AY,BY,AXValue,BXValue,AYValue,BYValue,XDELta,YDELta,IXDELTA}?` | pp. 40-44 |
| `AUTO` | auto | `:CURSor:AUTO:{ITEM,AX,BX,AY,BY,AXValue,BXValue,AYValue,BYValue}?` | pp. 45-48 |
| `XY` | XY | `:CURSor:XY:{AX,BX,AY,BY,AXValue,BXValue,AYValue,BYValue}?` | pp. 49-52 |

- `TRACk` reads back as **four** characters, `TRAC` (`hardware-verified`).
- Every family answers in **every** mode (`hardware-verified`): `:CURSor:AUTO:*`
  queried while the mode is `MAN` returns data, not `command error`. Never infer
  the mode from which replies arrived — read `:CURSor:MODE?` and translate only
  that family (`parse_cursor_readout` does this and lists the rest in
  `ignored_readings`).
- Pixel positions (`AX?`, `BX?`, …) and physical readings (`AXValue?`, …) are
  different quantities; the parser never converts one into the other.
- No reply carries a unit. Manual mode resolves X through
  `:CURSor:MANual:TUNit?` (`S`→s, `HZ`→Hz, `DEGR`→deg, `PERC`→%) and Y through
  `:CURSor:MANual:VUNit?`; `SOUR` means "whatever `:CHANnel<n>:UNITs` is", which
  this Skill does not query, so that unit stays `null` instead of being assumed
  to be volts. Track X is documented as seconds, `1/|dX|` as Hz.

## Three reply shapes

| Reply | Meaning | Parser result |
|---|---|---|
| an integer (`100`) | screen pixel; manual X 5..594, Y 5..394, XY 5..394 | `COMPLETE`, `unit` `pixel` |
| NR3 (`-8.000000e-04`) | a cursor reading or difference | `COMPLETE`, numeric `value` |
| `9.9E37` | **no cursor result** (auto item lacks that cursor, no XY timebase, …) | `INCOMPLETE`, `value` `null`, `no_cursor_result` |
| `4294967295` | uint32 -1: position not set, or no value for this source (manual `YDELta?` with LA, p. 2-23) | `INCOMPLETE`, `value` `null`, `cursor_position_unset` (positions) or `cursor_value_unset` (values/deltas) |
| 0 bytes | the measured dropped-query transient | `INCOMPLETE`, `empty_response` |
| `command error` | header undefined on this firmware | `UNSUPPORTED`, `instrument_command_error` |

`hardware-verified`, mode `MAN`, 1 kHz square on CH1: `AX?` 100, `BX?` 500,
`AY?` 100, `BY?` 300, `AXValue?` -8.000000e-04, `BXValue?` 8.000000e-04,
`XDELta?` 1.600000e-03, `IXDELta?` 6.250000e+02, `YDELta?` -2.000000e+00. In
`AUTO` mode the same unit answers `AY?`/`BY?` = `4294967295` and
`AYValue?`/`BYValue?` = `9.9E37`, i.e. both sentinels in one readout.

## Mode writes are silent and slow

- `:CURSor:MODE <mode>` returns nothing; `MAN`, `TRACk` and `AUTO` are accepted
  and read back as `MAN`, `TRAC`, `AUTO` (`hardware-verified`).
- The write also **lengthens the response delay**. A query sent after only 0.4 s
  came back empty and the late answer was then read as the reply to the *next*
  command (`hardware-verified`). Wait **at least 0.8-1.0 s**, or settle and then
  discard late bytes; the session does both (`Session.cursor_settle_delay`,
  default 1.0 s, and `Session.discard_pending`).
- Restore the previous mode: read it before the switch, write it back in a
  `finally`, then re-query to prove it. `cursor --mode` records `mode_restore`
  with `status` `pass`/`fail`.

## XY is model/firmware-dependent

`:CURSor:MODE XY` was **rejected** on this unit with `-200,"Execution error"`
and the mode stayed `TRAC` (`hardware-verified`); XY cursors only apply while
`:TIMebase:MODE` is `XY` (manual pp. 32, 49). The `:CURSor:XY:*` queries still
answer in other modes, with `9.9E37` values (`hardware-verified`). Treat XY as
`model/firmware-dependent`, never as a promised capability.

## Values are display-layer readings

Cursor values are what the instrument draws for the current timebase, vertical
scale and cursor placement. They are **not** calibrated metrology results: they
move when an operator moves a cursor, they inherit the channel amplitude unit,
and nothing here proves absolute accuracy. Say `UNVERIFIED` in that sense even
when the artifact status is `COMPLETE`, and keep the acquisition context with any
number you quote.

## CLI

```text
# read-only: follow the active mode, no writes, one cursor-readout report
python3 scripts/ds1000z_session.py --host 169.254.1.5 cursor

# switch to track cursors, collect that family, restore the prior mode
python3 scripts/ds1000z_session.py --host 169.254.1.5 --allow-writes cursor --mode TRACk

# show the exact bytes a run would send, without opening a socket
python3 scripts/ds1000z_session.py --dry-run --host 169.254.1.5 cursor
```

`--mode` accepts `MAN`, `TRACk`, `AUTO` (needs `--allow-writes`); `XY` is refused
with an explanation. `--out-raw DIR` saves every raw reply to `DIR/<quantity>.raw`
through `save_raw` (no overwrite unless `--overwrite`). The report is a
`cursor-readout`: `mode`, `family`, `type`/`source`/`sources`/`item`, `t_unit`,
`v_unit`, `positions`, `values`, `deltas`, `units`, plus `readings` carrying each
reply's `sha256`, `repr`, status and reasons.

Offline replay takes one family's replies as a bundle, one LF-terminated reply
per line, in the query order of that family; `--mode` names the family, so a
bundle whose line count does not match that family is refused as
`cursor_bundle_length` instead of shifting every reading by one:

```bash
python3 scripts/ds1000z_protocol.py cursor assets/fixtures/cursor-manual-values.txt --mode MAN
python3 scripts/ds1000z_protocol.py cursor assets/fixtures/cursor-track-values.txt --mode TRAC
```

The same replay is available as a function when a caller already holds the
replies:

```python
from ds1000z_protocol import CURSOR_FAMILY_QUERIES, parse_cursor_readout

mode = open("assets/fixtures/cursor-mode-man.txt", "rb").read()
lines = open("assets/fixtures/cursor-manual-values.txt", "rb").read().splitlines(keepends=True)
readings = dict(zip(CURSOR_FAMILY_QUERIES["manual"], lines), mode=mode)
print(parse_cursor_readout(mode, readings)["positions"])
```

A cursor fixture is a replay container: the exact replies of one family in query
order, one LF-terminated reply per line, nothing rewritten. `cursor-xy-values.txt`
was captured while the mode was `MAN`, because this firmware refuses
`:CURSor:MODE XY`. `assets/expected-cursor.json` holds the expected values.
