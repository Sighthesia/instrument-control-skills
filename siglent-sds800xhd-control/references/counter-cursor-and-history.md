# Counter, Cursor, and History

Load this reference only for precision frequency/period statistics, manually marked deltas, or a timestamp associated with an existing history frame. These commands are not needed for ordinary waveform capture.

## Counter

Manual-supported; target `:COUNter:CURRent?` returned `0.00E+00` and statistics returned `OFF` in the observed inactive/default state.

```text
:COUNter?
:COUNter:MODE?
:COUNter:SOURce?
:COUNter:CURRent?
:COUNter:STATistics?
:COUNter:STATistics:VALue?
```

The counter measures analog-channel input only. `MODE?` reports `FREQuency`, `PERiod`, or `TOTalizer`; `SOURce?` identifies the channel. Current value meaning depends on that mode. Statistics value format in frequency/period mode is:

```text
<current>,<mean>,<min>,<max>,<stdev>,<count>
```

It returns `OFF` if statistics are disabled, and statistics are documented only for frequency and period modes. Enabling/configuring the counter or statistics is state-changing; request authorization, configure source/mode, enable statistics if required, then query. `:FORMat:DATA` controls numeric precision; the counter's stated measurement precision is 7 digits, while default returned significant digits are 3.

## Cursor

Manual-supported. A spot probe on the target timed out when cursor readouts were queried with cursors inactive. Enable/configure cursors only when requested; do not treat an inactive-cursor timeout as evidence that the SCPI command is unsupported.

```text
:CURSor:MODE?
:CURSor:X1?
:CURSor:X2?
:CURSor:XDELta?
:CURSor:IXDelta?
:CURSor:Y1?
:CURSor:Y2?
:CURSor:YDELta?
```

- `MODE?` distinguishes `TRACk`, `MANual`, and `MEASure`; manual mode also has `X`, `Y`, or `XY` selection.
- `XDELta?` returns `X2-X1` in seconds.
- `IXDelta?` returns `1/(X2-X1)` in Hz.
- `YDELta?` returns `Y2-Y1` in the channel's vertical unit.

Before using deltas, read the cursor positions and sources if available, and verify the intended cursor mode/source. Cursor placement/mode commands change display state.

## History Timestamp

See [Anomaly search and mask testing](anomaly-search-and-mask-testing.md) for `:HISTORy:TIME?`, selection/playback caveats, and interpretation. Load that page only when there is an existing history frame or event to inspect.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Counter modes, current value, statistics: printed pp. 31-35.
- Cursor deltas and cursor modes: printed pp. 38-45.
- History timestamp: printed p. 163.
