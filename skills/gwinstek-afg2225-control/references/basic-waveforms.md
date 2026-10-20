# Basic Waveforms and Output (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 200-215. Support level:
`documented`.

## APPLy commands

`SOURce[1|2]:APPLy:*` sets trigger to immediate, disables burst/modulation/
sweep, and turns the output **on**. Nested optional parameters. Defaults:
1 kHz, 100 mVpp (50 Ω), 0 V offset (manual pp. 200-205).

| Command | Frequency range | Manual page |
|---|---|---|
| `SOURce[1|2]:APPLy:SINusoid [freq[,amp[,offset]]]` | 1 µHz-25 MHz | 202 |
| `SOURce[1|2]:APPLy:SQUare` | 1 µHz-25 MHz | 202 |
| `SOURce[1|2]:APPLy:RAMP` | 1 µHz-1 MHz | 203 |
| `SOURce[1|2]:APPLy:PULSe` | 500 µHz-25 MHz | 203 |
| `SOURce[1|2]:APPLy:NOISe` | frequency not applicable; use `DEF` | 204 |
| `SOURce[1|2]:APPLy:USER` | 1 µHz-60 MHz | 204 |
| `SOURce[1|2]:APPLy?` | returns function/frequency/amplitude/offset | 205 |

APPLy amplitude is `1 mVpp-10 Vpp` into 50 Ω; offset is `-4.99 V..4.99 V`
(manual pp. 202-204). The square APPLy command forces 50 % duty and the ramp
APPLy command forces 50 % symmetry; use the low-level commands to change them.

## Low-level output commands

| Command | Range / notes | Page |
|---|---|---|
| `SOURce[1|2]:FUNCtion` | SIN/SQU/RAMP/PULS/NOIS/USER | 206 |
| `SOURce[1|2]:FREQuency` | 1 µHz-25 MHz (sine/square); 1 µHz-1 MHz (ramp); pulse 500 µHz-25 MHz | 207 |
| `SOURce[1|2]:AMPlitude` | 1 mVpp-10 Vpp (50 Ω); 2 mVpp-20 Vpp (high-Z); 1-5 Vpp (50 Ω) at 20-25 MHz; **2-10 Vpp (high-Z) at 20-25 MHz** | 209, 293 |
| `SOURce[1|2]:DCOffset` | ±5 Vpk ac+dc (50 Ω); ±10 Vpk (high-Z); ±2.5 Vpk (50 Ω) at 20-25 MHz; `|Voffset| < Vmax - Vpp/2` | 210 |
| `SOURce[1|2]:SQUare:DCYCle` | 1-99 % (≤100 kHz), 10-90 % (≤1 MHz), 50 % (25 MHz) | 211 |
| `SOURce[1|2]:RAMP:SYMMetry` | 0-100 % | 212 |
| `OUTPut[1|2]` | ON/OFF | 213 |
| `OUTPut[1|2]:LOAD` | `DEFault` (50 Ω) / `INFinity` (>10 kΩ); reference only; not usable while ARB/MOD/SWEEP/BURST is active | 143, 213 |
| `SOURce[1|2]:VOLTage:UNIT` | `VPP` / `VRMS` / `DBM` (dBm unavailable in high-Z); sets the **default unit for all subsequent amplitude commands** | 214-215 |

## Load impedance and amplitude math

- `OUTPut[1|2]:LOAD` **only sets a reference termination**; the manual is explicit
  that it "is to be used as a reference only. If the actual load impedance is
  different to that specified, then the actual amplitude and offset will vary
  accordingly" (manual p. 143). A `LOAD INF` setting feeding a real 50 Ω load
  produces half the expected amplitude.
- **The load function "can only be used if the ARB, MOD, SWEEP or BURST
  functions are not active"** (manual p. 143). Since APPLy turns off burst,
  modulation, and sweep, sending `OUTPut:LOAD` before an APPLy is safe, but
  sending it while any of those modes is active may be rejected or ignored.
- Amplitude and offset **double** when the reference load changes from 50 Ω to
  high-Z (manual pp. 209-210).
- dBm is unavailable in high-Z mode; the units "will default to Vpp" (manual
  p. 214). A dBm value that was set earlier is silently reinterpreted as Vpp
  after switching to high-Z, so re-read `VOLTage:UNIT?` after any load change.
- Constraint: `|Voffset| < Vmax - Vpp/2` (manual p. 210).
- `OUTPut` state defaults to off. The manual describes `FUNC` as selecting and
  outputting a waveform, but the output on/off state is controlled by
  `OUTPut`. Do not assume a low-level command enabled the output: query
  `OUTP<n>?` and send `OUTPut ON` explicitly unless APPLy was used. APPLy is
  documented to turn the output on.

## Amplitude units and how they change every number

`SOURce[1|2]:VOLTage:UNIT` is a setter, not a label, and it is **global**:
"the units set with the VOLTage:UNIT command will be used as the default unit
for all amplitude units unless a different unit is specifically used"
(manual pp. 214-215).

```text
SOURce[1|2]:VOLTage:UNIT {VPP|VRMS|DBM}
SOURce[1|2]:VOLTage:UNIT?
```

Consequences:

- A bare `SOUR1:AMPL 3.54` means 3.54 of whatever unit is current. The same
  string is 3.54 Vpp or 3.54 Vrms (about 10 Vpp) depending on an earlier
  setting, so a readback without `VOLTage:UNIT?` cannot be interpreted.
- A per-command suffix (`3.54VRMS`, `10VPP`) overrides the default for that one
  command. The bundled helper always appends `VPP`, which makes APPLy
  deterministic but hides the instrument's current default.
- dBm requires a known reference load; it is refusable in high-Z.
- `FUNC` itself can rewrite the amplitude when it changes shape: the manual's
  example is a 5 Vrms square wave becoming a 3.536 Vrms sine after a shape
  change (manual p. 206). An `AMPL?` readback after `FUNC` therefore reports
  the instrument's value, not the value that was requested.

Record `VOLTage:UNIT?` and `OUTPut:LOAD?` with every amplitude.

## ARB amplitude semantics

`DATA:DAC` integers ±511 map to the **peak** amplitude of the configured Vpp, not
to full scale: "for a waveform with an amplitude of 5 Vpp (0 offset), the value
511 is the equivalent of 2.5 Volts… If the integer values do not span the full
output range, the peak amplitude will be limited" (manual p. 261). A waveform
written with ±300 codes therefore does not lose Vpp resolution — it produces
the configured Vpp with fewer quantisation steps; the ±511 span is a resolution
limit, not an amplitude limit.


## Pulse commands

| Command | Range | Page |
|---|---|---|
| `SOURce[1|2]:PULSe:PERiod` | 40 ns-2000 s | 216 |
| `SOURce[1|2]:PULSe:WIDTh` | 20 ns-1999.9 s; width > 1.6 × edge time, width < period − 1.6 × edge time | 217 |

## Mode compatibility

- APPLy disables burst/modulation/sweep and sets trigger immediate.
- Low-level commands allow those features to remain active; verify mode
  conflicts before combining.
- Only one modulation type active at a time (see modulation reference).

## Community caveat (unverified)

`avian2/gwinstek-tools` reports that `SOURCE1:OUTPUT ON` worked where the
manual's `OUTP1 ON` did not, and that positive DC offset with ARB can
invert the signal. Treat as unverified community observations, not commands
the Skill guarantees. Do not apply the DC-offset workaround automatically.