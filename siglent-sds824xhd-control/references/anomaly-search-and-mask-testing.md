# Anomaly Search and Mask Testing

For long motor captures, use the local analyzer's time-bounded workflow before exporting any edge list to an AI context: `events --start-time/--end-time` locates a bounded set of switching edges, `ringing` screens one selected edge window, and `window` returns the corresponding raw samples. These local tools retain the complete-capture SHA-256 and report when a selected window may truncate the ring-down.

Load this reference when the symptom is intermittent runt/glitch/pulse-width/interval/slope behavior or a compliance/mask failure. These features require setup before reading results; do not enable or reconfigure them while preserving an immutable stopped frame.

## Search Results

Manual-supported; `COUNT?` and `EVENt?` were exercised on the target and returned `0` in the current state:

| Query | Meaning |
|---|---|
| `:SEARch?` | Search enable state. |
| `:SEARch:MODE?` | Search mode: `EDGE`, `SLOPe`, `PULSE`, `INTerval`, or `RUNT`. |
| `:SEARch:COUNT?` | Number of search events on the current screen; not a lifetime or full-history total. |
| `:SEARch:EVENt?` | Event-frame index currently located when acquisition is stopped. |

Search parameters are mode-specific. Read the selected mode's source, polarity/slope, threshold and limit before interpreting the count. Search configuration and event navigation can change display/acquisition context. Configure it only with explicit authorization and before a fresh acquisition, then capture/stop and query results.

## Mask Test Results

Target-tested query shape; response is `FAIL,<n>,PASS,<n>,TOTAL,<n>`:

```text
:MTESt?
:MTESt:COUNt?
```

The counter alone is not a complete pass/fail conclusion. Check test enabled state, selected source, mask/test type, and total count. `TOTAL=0` means no evaluated samples/frames, not pass. The mask/template setup and operation are state-changing; only configure when the caller requests a compliance test and a valid mask is available.

## History

Manual-supported, target query is conditional:

```text
:HISTORy:TIME?
```

Returns `HH:MM:SS.ffffff` for the currently selected history frame. This does not contain a calendar date. A timeout can mean there is no valid selected history frame or the feature is inactive; do not automatically classify the command as unsupported. History frame selection/playback changes instrument view and must not be used during an immutable read.

## Interpretation Rules

- Zero search events only means none were found under the currently active search setup and current screen context.
- A nonzero count identifies candidates, not proof of circuit root cause. Retrieve the event waveform/segment and compare it with trigger and threshold conditions.
- Mask results need a nonzero `TOTAL` and a known mask/test configuration before PASS/FAIL is meaningful.
- Preserve the acquisition setup and command log alongside the result so event counts can be reproduced.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Search mode/count/event and mode-specific configuration: printed pp. 207-235.
- Mask test count and test state: printed pp. 190-195.
- History frame timestamp: printed p. 163.
