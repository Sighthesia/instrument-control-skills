# Counter, Cursor, and History

Load this reference only for precision frequency/period statistics, manually marked deltas, or a timestamp associated with an existing history frame. These commands are not needed for ordinary waveform capture.

## Counter

Manual-supported; target `:COUNter:CURRent?` returned `0.00E+00` and statistics returned `OFF` in the observed inactive/default state.

The counter is off by default. Reading `CURRent?` without enabling it returns a zero that looks like a measurement. Enable it first, and treat a zero as "no result" until the enable state and source are recorded.

```text
:COUNter {ON|OFF}                       # counter enable
:COUNter:MODE {FREQuency|PERiod|TOTalizer}
:COUNter:SOURce <channel>
:COUNter:LEVel <level>                  # counter trigger level
:COUNter:CURRent?
:COUNter:STATistics {ON|OFF}
:COUNter:STATistics:RESet
:COUNter:STATistics:VALue?
```

Totalizer mode has its own gate controls, which are required before a totalizer reading means anything:

```text
:COUNter:TOTalizer:GATE {ON|OFF}
:COUNter:TOTalizer:GATE:TYPE ...
:COUNter:TOTalizer:GATE:LEVel <level>
:COUNter:TOTalizer:GATE:SLOPe {RISe|FALL}
:COUNter:TOTalizer:SLOPe {RISe|FALL}
:COUNter:TOTalizer:RESet
```

The counter measures analog-channel input only. `MODE?` reports `FREQuency`, `PERiod`, or `TOTalizer`; `SOURce?` identifies the channel. Current value meaning depends on that mode. Statistics value format in frequency/period mode is:

```text
<current>,<mean>,<min>,<max>,<stdev>,<count>
```

It returns `OFF` if statistics are disabled, and statistics are documented only for frequency and period modes. Enabling/configuring the counter or statistics is state-changing; request authorization, configure source/mode, enable statistics if required, then query. `:FORMat:DATA` controls numeric precision; the counter's stated measurement precision is 7 digits, while default returned significant digits are 3 — set `:FORMat:DATA CUSTom,7` if you need that precision.

## Cursor

Manual-supported. A spot probe on the target timed out when cursor readouts were queried with cursors inactive. Enable/configure cursors only when requested; do not treat an inactive-cursor timeout as evidence that the SCPI command is unsupported.

```text
:CURSor {ON|OFF}
:CURSor:MODE {TRACk|MANual,{X|Y|XY}|MEASure}
:CURSor:SOURce1 <source>
:CURSor:SOURce2 <source>
:CURSor:X1 <value>
:CURSor:X2 <value>
:CURSor:Y1 <value>
:CURSor:Y2 <value>
:CURSor:X1?
:CURSor:X2?
:CURSor:XDELta?
:CURSor:IXDelta?
:CURSor:Y1?
:CURSor:Y2?
:CURSor:YDELta?
```

- Cursors must be enabled and the mode/sources set before positions or deltas mean anything; the target timed out on inactive-cursor queries.
- `MODE?` distinguishes `TRACk`, `MANual`, and `MEASure`; manual mode also has `X`, `Y`, or `XY` selection.
- `XDELta?` returns `X2-X1` in seconds.
- `IXDelta?` returns `1/(X2-X1)` in Hz.
- `YDELta?` returns `Y2-Y1` in the channel's vertical unit.

Multi-cursor families (`:CURSor:MANual:X<n>`, `:CURSor:MANual:Y<n>`, `:CURSor:MEASure<n>`, `:CURSor:TRACk<n>`, `:CURSor:XY:Y<n>`) exist on printed pp. 46-67 and are not reproduced here. Cursor placement/mode commands change display state.

## History

History is a buffer of past acquisitions, not a timestamp log. Enable it, then select and play frames. Reading `:HISTORy:TIME?` without an active selection is a conditional query, not proof the feature is unsupported.

```text
:HISTORy {ON|OFF}
:HISTORy:FRAMe <value>
:HISTORy:FRAMe?
:HISTORy:INTERval <value>
:HISTORy:LIST?
:HISTORy:PLAY ...
:HISTORy:TIME?
```

Frame count depends on memory depth: more points per frame means fewer stored frames. `:HISTORy:TIME?` returns `HH:MM:SS.ffffff` with no calendar date, so pair it with `:SYSTem:DATE?` and `:SYSTem:TIME?` (printed pp. 232, 238) when a wall-clock timestamp matters. Selecting or playing a frame changes the instrument view, so it is forbidden during an immutable read.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Counter enable, level, modes, current value, statistics, totalizer gate: printed pp. 31-36.
- Cursor enable, mode, sources, positions, deltas, multi-cursor families: printed pp. 38-67.
- History enable, frame, interval, list, play, timestamp: printed pp. 161-163.
