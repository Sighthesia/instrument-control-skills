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
| `SOURce[1|2]:AMPlitude` | 1 mVpp-10 Vpp (50 Ω); 2 mVpp-20 Vpp (high-Z); 1-5 Vpp (50 Ω) at 20-25 MHz | 209 |
| `SOURce[1|2]:DCOffset` | ±5 Vpk ac+dc (50 Ω); ±10 Vpk (high-Z); ±2.5 Vpk (50 Ω) at 20-25 MHz; `|Voffset| < Vmax - Vpp/2` | 210 |
| `SOURce[1|2]:SQUare:DCYCle` | 1-99 % (≤100 kHz), 10-90 % (≤1 MHz), 50 % (25 MHz) | 211 |
| `SOURce[1|2]:RAMP:SYMMetry` | 0-100 % | 212 |
| `OUTPut[1|2]` | ON/OFF | 213 |
| `OUTPut[1|2]:LOAD` | `DEFault` (50 Ω) / `INFinity` (>10 kΩ) | 213 |
| `SOURce[1|2]:VOLTage:UNIT` | `VPP` / `VRMS` / `DBM` (dBm unavailable in high-Z) | 214 |

## Load impedance and amplitude math

- Amplitude and offset **double** when load changes from 50 Ω to high-Z
  (manual p. 209-210). Set `OUTPut:LOAD` before setting amplitude/offset when
  the reference termination matters.
- dBm is unavailable in high-Z mode (manual p. 214).
- Constraint: `|Voffset| < Vmax - Vpp/2` (manual p. 210).
- `OUTPut` state defaults to off. Low-level `FUNC`/`FREQ`/`AMPL`/`DCO`
  commands do not implicitly turn the output on; send `OUTPut ON` explicitly
  unless APPLy was used. APPLy turns it on.

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