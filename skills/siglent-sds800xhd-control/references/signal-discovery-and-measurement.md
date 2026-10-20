# Signal Discovery and Measurement

Load this reference when the goal is to find an active signal, choose useful vertical/horizontal settings, confirm a trigger, or quantify voltage, timing, or jitter. Do not load protocol, mask-test, or cursor commands unless the observed signal calls for them.

## Status Labels

- **Target-tested**: query or workflow was exercised on SDS824X HD firmware `4.8.12.1.1.6.5`.
- **Manual-supported**: documented in the supplied SDS800X HD Programming Guide, but not individually hardware-tested here.
- **Session-dependent**: query forms requiring arguments or multiline output must be sent/read through a raw TCP session that preserves the complete response.
- **Conditional**: valid only after a feature is active or the signal produces valid data.

## Minimal Read-Only Snapshot

The following scalar forms are **Target-tested** on TCP 5025:

| Query | Use / response |
|---|---|
| `*IDN?` | Vendor, model, serial, firmware; identify before using model-specific commands. |
| `*OPC?` | Returns `1` when pending operations finish. It does not prove a trigger occurred. |
| `:TRIGger:STATus?` | `Arm`, `Ready`, `Auto`, `Trig'd`, `Stop`, or `Roll`. |
| `:TRIGger:FREQuency?` | Hardware frequency counter in Hz. `0` means no valid counter result, not necessarily no signal. |
| `:ACQuire:NUMACq?` | Acquired frame count; resets after operations affecting acquisition, including horizontal/vertical changes. Not a generic averaging-complete flag. |
| `:ACQuire:POINts?` | Current record point count. |
| `:ACQuire:SRATe?` | Current sample rate in Sa/s. |
| `:ACQuire:MMANagement?` | Current memory-management mode: `AUTO`, `FSRate`, or `FMDepth`. Determines whether the sample rate or the memory depth is the setting you control. |
| `:TIMebase:SCALe?`, `:TIMebase:DELay?` | Main timebase in s/div and horizontal delay in s. |
| `:TIMebase:REFerence:POSition?` | Horizontal reference position percentage, 0..100, for delay-fixed expansion. |
| `:ACQuire:MDEPth?` | Current acquisition memory-depth class; SDS800X HD lists 100M/50M/25M classes by active channel count. |
| `:CHANnel<n>:SCALe?`, `:CHANnel<n>:OFFSet?`, `:CHANnel<n>:SWITch?`, `:CHANnel<n>:COUPling?`, `:CHANnel<n>:PROBe?` | Per-channel V/div, offset, channel state, AC/DC/GND coupling, and probe attenuation. Substitute channel number 1-4. |
| `:TRIGger:EDGE:LEVel?` | Edge trigger threshold in V. |

Example target snapshot observed: record `25 Mpts`, sample rate `5 MSa/s`, timebase `0.5 s/div`, trigger delay `+2 s` in `TIMebase:DELay?`, edge level `2.5 V`. Do not assume the delay sign is the same as a legacy `TRDL?` field without checking that path's convention.

### Trigger-Following Window Strategy

Manual-supported and implemented as an explicit option in `scripts/capture_scope.py`. The 10-division YT time axis uses `t = Delay - 5 * Timebase + index * sample_interval`. To place the trigger `margin_div` divisions from the left edge:

```text
Delay = (5 - margin_div) * Timebase
pre-trigger  = margin_div * Timebase
post-trigger = (10 - margin_div) * Timebase
```

For `margin_div=1`, this is `Delay=+4*Timebase`, one division before the trigger and nine divisions after it. Use this only for events expected to continue after the trigger. Set `TIM:SCAL`, `TIM:DEL`, optional `TIM:REF:POS`, and `ACQ:MDEP` before `TRMD SINGLE`; never apply them while reading an existing stopped frame.

## Sample Rate and Memory Management

`:ACQuire:MMANagement` decides which of the two settings is authoritative. Query it before assuming that a written sample rate or memory depth survived, and write it before the setting it governs (manual printed p. 18).

| Mode | Behaviour | Which setting you control |
|---|---|---|
| `AUTO` | keeps the maximum sample rate and derives memory depth and sample rate from the timebase | neither; both follow the timebase |
| `FSRate` | fixed sample rate; memory depth follows the timebase | `:ACQuire:SRATe` |
| `FMDepth` | fixed memory depth; sample rate follows the timebase | `:ACQuire:MDEPth` |

Sample rate is settable only in `FSRate` mode:

```text
:ACQuire:MMANagement FSRate
:ACQuire:SRATe 5.00E9
:ACQuire:SRATe?            # read back; the manual warns a value above the
                           # settable maximum is matched to the nearest one
```

`SARA` / `ACQ:SRAT` are the short forms. The documented example is `5.00E9`; the manual states no discrete rate list, only that an out-of-range request is snapped to a settable value, so always read the rate back and record it as observed, not requested. Setting the rate changes the acquisition context, so it is an authorized write before `TRMD SINGLE` only; never while reading a stopped frame.

Memory depth is a per-channel-count table, not a three-value choice. For SDS800X HD the manual lists `{10k|100k|1M|10M|100M}` single channel, `{10k|100k|1M|10M|50M}` dual channel, and `{10k|100k|1M|10M|25M}` four channel (manual printed pp. 19-20). `scripts/scope_protocol.py` currently accepts only `100M`, `50M`, and `25M` as the default-per-channel-count convenience values; the smaller classes are documented but not implemented by the script. Digital channels, averaging/ERES acquisition type, and roll mode all reduce the usable depth.

## Other Acquisition Settings

Manual-supported, not hardware-tested in this Skill. These change the acquisition context, so any write belongs before `TRMD SINGLE` and never during a stopped-frame read.

| Command | Values | Why it matters |
|---|---|---|
| `:ACQuire:MODE` | `YT`, `XY`, `ROLL` | `ROLL` limits usable memory depth; `XY` changes what the horizontal axis means. |
| `:ACQuire:AMODe` | `FAST`, `SLOW` | Fast capture improves the odds of catching an anomaly but is not a substitute for a real trigger. |
| `:ACQuire:TYPE` | `NORMal`, `PEAK`, `AVERage,<times>`, `ERES,<bits>` | `PEAK` can show glitches narrower than one sample; averaging and ERES limit depth and are unavailable while segmented acquisition is on. `<times>` is 4..8192 in powers of two; `<bits>` is 0.5..4.0 in 0.5 steps (manual printed p. 23). |
| `:ACQuire:INTerpolation` | `ON` (Sinc), `OFF` (linear) | Changes how samples are joined; do not compare measurements taken under different interpolation. |
| `:ACQuire:SEQuence` | `ON`, `OFF` | Enables segmented acquisition; pair with `:ACQuire:SEQuence:COUNt` and `:WAVeform:SEQuence?`. |
| `:ACQuire:SEQuence:COUNt` | integer; upper bound depends on model and timebase | Record it with any segmented capture. |
| `:ACQuire:RESolution` | `8Bits`, `10Bits` | The manual attributes this to SDS2000X Plus; confirm support on the connected model instead of assuming it. |
| `:ACQuire:CSWeep` | — (event) | Clears sweeps and restarts acquisition, like the front-panel Clear Sweeps key. It is a state change, not cleanup. |

## Signal Discovery

1. Query `*IDN?`, acquisition status, record length/rate, and channel state/coupling/probe/scale/offset.
2. The bundled scripts do not currently provide an automatic signal-discovery/autorange command. Follow the bounded read-measure-adjust loop below, using only commands documented for the identified model and firmware.
3. For a manual read-only check, use `:MEASure:SIMPle:VALue? PKPK`, then `MAX`, `MIN`, `FREQ`, or `PER` for the selected simple-measurement source. Set/read `:MEASure:SIMPle:SOURce?` only when source identity is ambiguous.
4. A `TRIGger:FREQuency?` value can inform a coarse timebase, but verify with a waveform/measurement. If it returns zero, fall back to measured period or sampled waveform; do not conclude the input is disconnected.

`AUToset` is documented by the manual as a state-changing convenience command and is discouraged for signals below 100 Hz. Use it only when explicitly requested; for controlled agent tuning, prefer bounded V/div, offset, timebase, and trigger adjustments followed by readback.

## Measurement Queries

### Simple measurements

Manual-supported, target response not individually checked for each parameter:

```text
:MEASure:SIMPle:SOURce?                 # source, e.g. C1
:MEASure:SIMPle:VALue? PKPK             # one requested metric
:MEASure:SIMPle:VALue? ALL              # all basic measurement values
```

The documented type set includes voltage (`PKPK`, `MAX`, `MIN`, `AMPL`, `MEAN`, `RMS`), timing (`PER`, `FREQ`, `PWID`, `NWID`, `DUTY`, `RISE`, `FALL`), edge counts, areas, and other listed items. `ALL` is documented as querying every basic measurement item. Its result is not guaranteed to be a single scalar.

### Advanced measurements

Manual-supported. Measurement slots are `P1` through `P12`; first query slot type/source before interpreting the value:

```text
:MEASure:ADVanced:P1:TYPE?
:MEASure:ADVanced:P1:SOURce1?
:MEASure:ADVanced:P1:VALue?
:MEASure:ADVanced:P1:STATistics? MEAN
:MEASure:ADVanced:P1:STATistics? ALL
:MEASure:ADVanced:P1:SHIStory? 5
```

`STATistics?` accepts `ALL`, `CURRent`, `MEAN`, `MAXimum`, `MINimum`, `STDev`, or `COUNt`. `SHIStory? [count]` returns `Count=n,value...`; it is bounded measurement-statistics history, not necessarily a wall-clock timeline. The manual says history behavior depends on a finite maximum-statistics count; with no limit it returns current measurement data.

These argument-bearing queries must include their arguments exactly as documented. Send the complete command, for example `:MEASure:SIMPle:VALue? ALL`, through the raw TCP session; do not silently drop the argument. The current bundled waveform CLI does not expose these measurement queries as command-line options.

## Controlled Tuning Rules

- For a periodic signal, target roughly 3-5 visible periods; choose timebase from measured period and verify the readback.
- Keep the signal comfortably within the vertical range. Use measured min/max and channel scale to avoid clipping, then center using offset and re-read.
- Estimate a trigger level between stable low/high levels; verify that the selected channel and edge slope match the signal.
- Require sample rate to cover the signal's relevant bandwidth with margin. A 4-5x fundamental-frequency heuristic is not sufficient for fast edges or harmonics; use edge bandwidth/rise time when known.
- Every setting write changes acquisition context. Apply only authorized writes before arming a new capture, wait for `*OPC?` as appropriate, and obtain a fresh capture before analysis.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` in this repository.

- Device ID / `*OPC?`: printed pp. 13-14.
- Acquisition points, frame count, sample rate: printed pp. 21-23.
- Acquisition mode, interpolation, memory management, memory depth, sample rate, acquisition type: printed pp. 17-23.
- System remote/local, LAN, NSTorage, date/time, touch, self-calibration: printed pp. 257-266.
- Channel coupling, probe, V/div, switch: printed pp. 25-29.
- Simple/advanced measurement, statistics, history: printed pp. 164-183.
- Trigger frequency and status: printed pp. 243-244.
- Timebase: printed pp. 239-242.
- The manual lists SDS800X HD support from firmware 1.1.3.1; target hardware tested here is firmware 4.8.12.1.1.6.5.
