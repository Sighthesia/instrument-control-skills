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

## Vertical Channel Control

Every per-channel read in the snapshot table above has a documented setter. Reads are the default; the writes below change the acquisition context, so they belong before `TRMD SINGLE` and never during a stopped-frame read (manual printed pp. 24-30).

| Command | Values | Notes |
|---|---|---|
| `:CHANnel<n>:SCALe` | NR3, V/div | Range depends on model and scales with probe attenuation. |
| `:CHANnel<n>:OFFSet` | NR3, V | Allowed range depends on the vertical scale. |
| `:CHANnel<n>:SWITch` | `ON`, `OFF` | Channel enable. |
| `:CHANnel<n>:COUPling` | `AC`, `DC`, `GND` | `GND` disconnects the input; a flat trace is not a zero-volt signal. |
| `:CHANnel<n>:PROBe` | `DEFault` or `VALue,<ratio>`; ratio `1E-6`..`1E6` | Default 1X. Wrong ratio silently scales every voltage and measurement. |
| `:CHANnel<n>:BWLimit` | `20M`, `200M`, `FULL` | Bandwidth limit changes rise time and noise. |
| `:CHANnel<n>:INVert` | `ON`, `OFF` | Displayed polarity only; trigger slope is unaffected. |
| `:CHANnel<n>:IMPedance` | `ONEMeg`, `FIFTy` | At `FIFTy` (50 Ω) the maximum vertical scale is 1 V/div. |
| `:CHANnel<n>:UNIT` | `V`, `A` | Changes the unit of measurements, cursors, channel scale, and trigger level, not just the label. A current probe workflow needs `A`; a voltage-in-V assumption is then wrong. |
| `:CHANnel<n>:SKEW` | NR3, `-1.00E-07`..`1.00E-07` s | Channel-to-channel deskew. |
| `:CHANnel<n>:LABel` + `:CHANnel<n>:LABel:TEXT` | `ON`/`OFF`; quoted string up to 20 chars | Annotation only; never evidence of the signal. |
| `:CHANnel<n>:VISible` | `ON`, `OFF` | Display visibility, distinct from `SWITch`. |
| `:CHANnel:REFerence` | `OFFSet`, `POSition` | Vertical expansion strategy when the scale changes. |

`UNIT A` is the most dangerous of these: after switching a channel to amperes, every voltage figure in this Skill (including the WORD calibration caveat and the trigger level) is expressed in amperes. Record the unit with each measurement.

## Trigger Mode and Type

`TRMD` / `TRMD?` are the firmware-verified short forms used by every script here. The manual does not list `TRMD` at all; its documented spellings are `:TRIGger:MODE` and `:TRIGger:MODE?` (printed pp. 243-244), and `TRMD SINGLE` and `:TRIGger:MODE SINGle` are the same operation. Record which form was sent, and never send `TRMD` after `Stop`.

| Command | Values | Notes |
|---|---|---|
| `:TRIGger:MODE` / `TRMD` | `SINGle`, `NORMal`, `AUTO`, `FTRIG` | `FTRIG` forces a frame regardless of the trigger condition. This Skill still uses `TRMD SINGLE` as the only approved single-shot start; `FTRIG` and `NORMal` are recorded for completeness, not recommended for captures that depend on the `Ready -> Stop` proof. |
| `:TRIGger:STATus?` / `SAST?` | `Arm`, `Ready`, `Auto`, `Trig'd`, `Stop`, `Roll` | The `Ready -> Stop` rule applies to the value, whichever spelling produced it. |
| `:TRIGger:TYPE` | `EDGE`, `PULSE`, `SLOPe`, `INTerval`, `PATTern`, `RUNT`, `WINDow`, `DROPout`, `VIDeo`, `QUALified`, `NEDGe`, `DELay`, `SHOLd`, `IIC`, `SPI`, `UART`, `LIN`, `CAN`, `FLEXray`, `CANFd`, `IIS`, `M1553`, `SENT`, `A429` | 24 documented types (printed p. 245). Only `EDGE` is verified here. A runt/glitch workflow needs `RUNT` or `PULSE` plus its own parameters; searching cannot be configured without first selecting the type. |
| `:TRIGger:RUN` / `:TRIGger:STOP` | — | Equivalent to the front-panel Run/Stop key. Both are forbidden after `Stop` while reading a frame; nothing in this Skill sends them automatically. |

Serial, video, and qualified trigger types (`IIC`, `SPI`, `UART`, `LIN`, `CAN`, `FLEXray`, `CANFd`, `IIS`, `M1553`, `SENT`, `A429`, `VIDeo`, `QUALified`, `PATTern`, `SHOLd`) have their own parameter trees on printed pp. 267-410; they are not reproduced here. Availability depends on model and installed options, and most need digital channels. Configure one only after confirming the option and recording the full parameter readback.

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
| `:ACQuire:MODE` | `YT`, `XY`, `ROLL` | `ROLL` limits usable memory depth and ignores horizontal delay; `XY` changes what the horizontal axis means. See [Roll Mode](#roll-mode). |
| `:ACQuire:AMODe` | `FAST`, `SLOW` | Fast capture improves the odds of catching an anomaly but is not a substitute for a real trigger. |
| `:ACQuire:TYPE` | `NORMal`, `PEAK`, `AVERage,<times>`, `ERES,<bits>` | `PEAK` can show glitches narrower than one sample; averaging and ERES limit depth and are unavailable while segmented acquisition is on. `<times>` is 4..8192 in powers of two; `<bits>` is 0.5..4.0 in 0.5 steps (manual printed p. 23). |
| `:ACQuire:INTerpolation` | `ON` (Sinc), `OFF` (linear) | Changes how samples are joined; do not compare measurements taken under different interpolation. |
| `:ACQuire:SEQuence` | `ON`, `OFF` | Enables segmented acquisition; pair with `:ACQuire:SEQuence:COUNt` and `:WAVeform:SEQuence?`. |
| `:ACQuire:SEQuence:COUNt` | integer; upper bound depends on memory depth | Record it with any segmented capture. |
| `:ACQuire:RESolution` | `8Bits`, `10Bits` (the manual's description mentions SDS2000X Plus; confirm on the connected model instead of assuming it) | ADC resolution. Do not confuse it with the math `ERES` bit setting, which is 0.5-3.0 not 0.5-4.0. |
| `:ACQuire:CSWeep` | — (event) | Clears sweeps and restarts acquisition, like the front-panel Clear Sweeps key. It is a state change, not cleanup. |

## Roll Mode

Roll is a streaming display mode, not a trigger mode, and it is **incompatible with this Skill's `Ready -> Stop` capture flow**. Enter it only for slow observation, and never as part of an automated single-shot capture.

How to enter and leave (manual printed p. 18, user manual printed p. 44):

```text
:ACQuire:MODE ROLL       # enter Roll; equivalent to the front-panel Roll key
:ACQuire:MODE?           # read back; confirm YT/XY/ROLL before trusting a flow
:ACQuire:MODE YT         # leave Roll and return to normal triggered display
```

The front-panel `Roll` key toggles the same state; pressing it again exits. Both paths are documented, but only the SCPI path is usable in a remote session.

Documented behaviour and preconditions:

- The waveform scrolls right to left and is written from the right edge, like a strip chart. It suits events occurring a few times per second.
- **Only available at 50 ms/div and slower.** Below that the mode is not offered.
- **Horizontal position/delay has no effect.** `:TIMebase:DELay` and the whole left-aligned-trigger strategy are meaningless here; the script now refuses to run that strategy outside `YT`.
- **Zoom is not available while Roll is running.**
- Roll **limits the usable memory depth** (programming guide printed p. 20).
- Search-event totals: `YT` and stopped `Roll` cap at 1000 events; running `Roll` has no cap (user manual p. 21 region).

Why the capture flow must not use it:

- `:TRIGger:STATus?` reports `Roll` rather than `Ready`, so a `Ready -> Stop` proof can never be satisfied. `scope_wait_ready()` and `capture_scope.wait_state()` now raise an explicit `Roll mode` error instead of timing out silently.
- `SAST?` returning `Roll` is recorded as `roll_seen`, not as `ready_seen`; a later `Stop` is still rejected as "Stop observed before Ready".
- The manual does not describe how `TRMD SINGLE` interacts with Roll. Treat that combination as unverified and do not depend on it.

To stop a rolling display for inspection, use the front-panel Run/Stop key or `:TRIGger:STOP`; pressing Run/Stop again restarts a rolling acquisition and **clears the display**. Clearing the screen destroys the reference for any earlier screenshot, so capture the screenshot before stopping.

### Sample Rate in Roll Mode

There is no enumerable list. The programming guide describes `:ACQuire:SRATe` only as "NR3; a value above the settable maximum is matched to a settable value" (printed p. 22) and gives no discrete rate table; neither manual has a sample-rate specification appendix for this series. Do not write a fixed table into a script or claim a rate set from arithmetic alone.

What the manuals do bound:

- Roll needs a timebase of 50 ms/div or slower (user manual printed p. 44). A 10-division screen is therefore at least 0.5 s of captured time.
- Roll "limits the memory depth" (programming guide printed p. 20) without stating the limit.
- Maximum depth by active channel count (programming guide printed p. 48): single channel 10k/100k/1M/10M/100M, dual 10k/100k/1M/10M/50M, four-channel 10k/100k/1M/10M/25M.

So rate = depth / window, and the window is at least 0.5 s. The resulting order-of-magnitude ceiling, before Roll's own depth cut, is roughly 200 MSa/s single channel, 100 MSa/s dual, and 50 MSa/s four-channel. Roll's undocumented depth limit only lowers these. Roll is a slow-event mode; a high sample rate here is a sign of a wrong setup, not a goal.

Query the live values instead of predicting them:

```text
:ACQuire:MODE?      # confirm ROLL, YT, or XY
:ACQuire:MDEPth?    # depth actually applied
:ACQuire:POINts?    # points actually captured
:ACQuire:SRATe?     # rate actually in force
```

Record all four together. The relation `points / rate` must agree with the observed capture window; a mismatch means one of the four responses does not describe the same acquisition. These four reads are safe at any time and do not change acquisition context.

Still unknown and deliberately not guessed: the actual Roll depth limit, whether the channel count cuts it further, whether `:ACQuire:SRATe` is accepted while in Roll, and the hardware's real discrete rate divisors. All of this is `documented`; the target firmware has not been exercised in Roll mode.

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
:MEASure <ON|OFF>                       # global measurement enable
:MEASure:MODE {SIMPle|ADVanced}
:MEASure:SIMPle:ITEM <parameter>,<ON|OFF>
:MEASure:SIMPle:SOURce?                 # source, e.g. C1
:MEASure:SIMPle:VALue? PKPK             # one requested metric
:MEASure:SIMPle:VALue? ALL              # all enabled measurement values
```

The item must be enabled with `:MEASure:SIMPle:ITEM <parameter>,ON` before `VALue?` returns it; a reading that depends on an item nobody enabled is not a measurement result. The manual lists 52 parameters (printed pp. 181-182), including `PKPK`, `MAX`, `MIN`, `AMPL`, `TOP`, `BASE`, `LEVELX`, `CMEAN`, `MEAN`, `STDEV`, `VSTD`, `RMS`, `CRMS`, `MEDIAN`, `CMEDIAN`, `OVSN`, `OVSP`, `FPRE`, `RPRE`, `ULOWer`, `PER`, `FREQ`, `TMAX`, `TMIN`, `PWID`, `NWID`, `DUTY`, `NDUTY`, `WID`, `NBWID`, `DELAY`, `TIMEL`, `RISE`, `FALL`, `RISE20T80`, `FALL80T20`, `CCJ`, `PAREA`, `NAREA`, `AREA`, `ABSAREA`, `CYCLES`, `REDGES`, `FEDGES`, `EDGES`, `PPULSES`, `NPULSES`, `PACArea`, `NACArea`, `ACArea`, `ABSACArea`. `ALL` is documented as querying every basic measurement item; its result is not guaranteed to be a single scalar.

### Advanced measurements

Manual-supported. Measurement slots are `P1` through `P12`; first query slot type/source before interpreting the value. The type is a write-only setting: a slot with no type returns nothing useful.

```text
:MEASure:ADVanced:P<n> {ON|OFF}
:MEASure:ADVanced:P<n>:TYPE <parameter>
:MEASure:ADVanced:P<n>:SOURce1 <source>
:MEASure:ADVanced:P<n>:SOURce2 <source>
:MEASure:ADVanced:P<n>:VALue?
:MEASure:ADVanced:P<n>:STATistics? MEAN
:MEASure:ADVanced:P<n>:STATistics? ALL
:MEASure:ADVanced:P<n>:SHIStory? 5```

Sources accept `C<n>`, `Z<n>` (zoom, only while zoom is on), `F<x>` (math), `M<m>` (memory), `D<d>` (digital 0-15), and `REF<r>` where `<r>` is `A`..`D`. That is why a voltage-only assumption breaks on a math or reference source.

`STATistics?` accepts `ALL`, `CURRent`, `MEAN`, `MAXimum`, `MINimum`, `STDev`, or `COUNt`. `SHIStory? [count]` returns `Count=n,value...`; it is bounded measurement-statistics history, not necessarily a wall-clock timeline. The manual says history behavior depends on a finite maximum-statistics count; with no limit it returns current measurement data.

These argument-bearing queries must include their arguments exactly as documented. Send the complete command, for example `:MEASure:SIMPle:VALue? ALL`, through the raw TCP session; do not silently drop the argument. The current bundled waveform CLI does not expose these measurement queries as command-line options.

## Controlled Tuning Rules

- For a periodic signal, target roughly 3-5 visible periods; choose timebase from measured period and verify the readback.
- Keep the signal comfortably within the vertical range. Use measured min/max and channel scale to avoid clipping, then center using offset and re-read.
- Estimate a trigger level between stable low/high levels; verify that the selected channel and edge slope match the signal.
- Require sample rate to cover the signal's relevant bandwidth with margin. A 4-5x fundamental-frequency heuristic is not sufficient for fast edges or harmonics; use edge bandwidth/rise time when known.
- Set `:FORMat:DATA` before trusting a numeric reading. The default is 3 significant digits; a 7-digit frequency counter or a small ripple measurement is meaningless at that precision. Use `:FORMat:DATA DOUBle` (14 digits) or `:FORMat:DATA CUSTom,<1..64>` when the reading is used in statistics.
- Every setting write changes acquisition context. Apply only authorized writes before arming a new capture, wait for `*OPC?` as appropriate, and obtain a fresh capture before analysis.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` in this repository.

- Device ID / `*OPC?`: printed pp. 13-14.
- Numeric precision (`:FORMat:DATA`): printed p. 15.
- Acquisition mode, interpolation, memory management, memory depth, sample rate, acquisition type: printed pp. 17-23.
- Roll mode availability, horizontal-delay/zoom limits, and display behaviour: user manual printed p. 44 (the only place it is described; the programming guide lists `ROLL` as a value only).
- Sample-rate bounds in Roll mode: derived from the 50 ms/div minimum and the per-channel depth table (programming guide printed pp. 20, 22, 48). No discrete rate list exists in either manual.
- Acquisition points, frame count, sample rate: printed pp. 21-23.
- Channel coupling, probe, V/div, switch, bandwidth limit, invert, impedance, unit, skew, label, reference: printed pp. 24-30.
- Simple/advanced measurement, statistics, history: printed pp. 164-183.
- Trigger frequency, mode, status, run/stop: printed pp. 243-244.
- Trigger types and per-type parameters: printed pp. 245-410.
- Timebase: printed pp. 239-242.
- System remote/local, LAN, NSTorage, date/time, touch, self-calibration: printed pp. 257-266.
- The manual lists SDS800X HD support from firmware 1.1.3.1; target hardware tested here is firmware 4.8.12.1.1.6.5.
