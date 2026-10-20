# Anomaly Search and Mask Testing

For long motor captures, use the local analyzer's time-bounded workflow before exporting any edge list to an AI context: `events --start-time/--end-time` locates a bounded set of switching edges, `ringing` screens one selected edge window, and `window` returns the corresponding raw samples. These local tools retain the complete-capture SHA-256 and report when a selected window may truncate the ring-down.

Load this reference when the symptom is intermittent runt/glitch/pulse-width/interval/slope behavior or a compliance/mask failure. These features require setup before reading results; do not enable or reconfigure them while preserving an immutable stopped frame.

## Search Configuration

The queries below report results only for whatever configuration was last active. Search is off by default, so `COUNT?` returning `0` usually means "not configured", not "no anomaly".

```text
:SEARch {ON|OFF}
:SEARch:MODE {EDGE|SLOPe|PULSE|INTerval|RUNT}
:SEARch:COUNT?
:SEARch:EVENt?
```

Per-mode parameters follow the selected mode: `:SEARch:EDGE:*`, `:SEARch:SLOPe:*`, `:SEARch:PULSE:*`, `:SEARch:INTerval:*`, `:SEARch:RUNT:*` (source, slope/polarity, threshold, and upper/lower limits, printed pp. 209-234). Set the mode first, then its parameters, then enable search. Enabling search requires a fresh acquisition before `COUNT?` reflects the configured search.

## Mask Test Results

Mask testing needs a mask and an enabled test before a count is meaningful. `:MTESt:COUNt?` alone cannot pass or fail anything.

```text
:MTESt:MASK:LOAD {INTernal,<num>|EXTernal,<path>}
:MTESt:TYPE {ALL_IN|ALL_OUT|ANY_IN|ANY_OUT}
:MTESt {ON|OFF}
:MTESt?
:MTESt:COUNt?
```

`ALL_IN` passes only when every waveform point is inside the mask; a single point outside fails it. `ALL_OUT`, `ANY_IN`, and `ANY_OUT` invert that logic, so a PASS/FAIL figure is meaningless without the recorded type. Response shape is `FAIL,<n>,PASS,<n>,TOTAL,<n>`; `TOTAL=0` means no evaluated samples, not pass. Mask creation, editing, and loading write files or internal slots, so treat them as authorized writes and never overwrite operator masks.

## History

Manual-supported, target query is conditional:

```text
:HISTORy:TIME?
```

Returns `HH:MM:SS.ffffff` for the currently selected history frame. This does not contain a calendar date; pair it with `:SYSTem:DATE?`/`:SYSTem:TIME?` when wall-clock time matters. A timeout can mean there is no valid selected history frame or the feature is inactive; do not automatically classify the command as unsupported. History frame selection/playback changes instrument view and must not be used during an immutable read.

## Interpretation Rules

- Zero search events only means none were found under the currently active search setup and current screen context.
- A nonzero count identifies candidates, not proof of circuit root cause. Retrieve the event waveform/segment and compare it with trigger and threshold conditions.
- Mask results need a nonzero `TOTAL` and a known mask/test configuration before PASS/FAIL is meaningful.
- Preserve the acquisition setup and command log alongside the result so event counts can be reproduced.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Search enable, mode, count, event, and mode-specific configuration: printed pp. 207-234.
- Mask test type, mask load, operate, count: printed pp. 218-223.
- History frame timestamp: printed p. 163.
