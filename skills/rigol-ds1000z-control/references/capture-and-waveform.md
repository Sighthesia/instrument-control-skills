# Capture, Memory Depth, and Waveform Download (DS1000Z)

Load this reference before running, stopping, or downloading an acquisition: it
covers the run-state commands, the memory-depth write that only works while
running, the three `:WAVeform` reading modes, the IEEE block framing, and the
preamble fields.

Syntax and page numbers come from the *MSO1000Z/DS1000Z Programming Guide*,
PGA19108-1110, Software Version 00.04.03.SP2 (PDF physical pages). Values marked
`hardware-verified` were observed on `RIGOL TECHNOLOGIES,DS1074Z,
DS1ZA171004155,00.04.02.SP4` over raw TCP 5555; raw captures and timings are in
`artifacts/rigol-ds1000z/`. Everything else is `documented` and untested on that
firmware.

## Run control (PDF pp. 18-19)

| Command | Syntax | Behaviour | Page |
|---|---|---|---|
| `:RUN` | `:RUN` | Start acquisition; returns nothing | 18 |
| `:STOP` | `:STOP` | Stop acquisition; returns nothing; required before RAW/MAXimum reads | 18 |
| `:SINGle` | `:SINGle` | Wait for one trigger, display it, then stop (= `:TRIGger:SWEep SINGle`) | 19 |
| `:TFORce` | `:TFORce` | Force a trigger; only valid in `NORMal` and `SINGle` sweep | 19 |
| `:CLEar` | `:CLEar` | Clear the display; in RUN state the waveform reappears immediately | 18 |
| `:AUToscale` | `:AUToscale` | Auto-set vertical, horizontal, and trigger from the signal | 18 |

- `:RUN`, `:STOP`, `:SINGle`, and `:AUToscale` "are invalid" while the waveform
  record function is enabled or playing back (PDF p. 18-19). This Skill does not
  use the record function, so that condition is `documented` only.
- Writes return **no** response. On the evidence unit, ~0.3-0.4 s had to elapse
  before the next command on the same socket behaved (`hardware-verified`).
- `:SINGle` leaves the instrument stopped: `:TRIGger:STATus?` answered `STOP`
  after `:SINGle`, and `TD` after a subsequent `:RUN` (`hardware-verified`).
- **`:AUToscale` needs operator authorization.** It indiscriminately rewrites
  vertical scale, timebase, and trigger settings, so it destroys the
  configuration whose context the rest of this Skill requires. `:AUToscale` is
  also documented to disable pass/fail mode first (PDF p. 18). The scripts never
  send it and `--allow-writes` does not enable it; only a human at the bench may
  authorize it, and the configuration must be re-read afterwards.

## Trigger status (`:TRIGger:STATus?`, PDF p. 175)

| Reply | Meaning (`documented`) |
|---|---|
| `TD` | Triggered; a trigger occurred and the record is available |
| `WAIT` | Waiting for the trigger condition |
| `RUN` | Running (the instrument does not document which sub-state this is) |
| `AUTO` | Auto sweep; the frame is **not** a triggered frame |
| `STOP` | Acquisition stopped |

Observed on the evidence unit: `TD` while running, `STOP` after `:SINGle` or
`:STOP` (`hardware-verified`). Immediately after `:RUN` the query can answer with
nothing at all — 0 bytes, no terminator, re-tested as `TD` seconds later — so an
empty status reply means "ask again", not "no trigger" or a framing failure
(`hardware-verified`). `WAIT`, `RUN`, and `AUTO` are documented but were
not seen, so a script must treat them as "not ready" rather than assume a
meaning. Practical rule: poll until `TD` or `STOP`; never treat `AUTO` as proof
of a trigger; in `:TRIGger:SWEep AUTO` a completed record proves only that the
instrument acquired, not that it triggered (`documented`, PDF p. 175).

## Acquisition settings (`:ACQuire`, PDF pp. 20-23)

| Command | Parameter | Range / default | Unit | Page |
|---|---|---|---|---|
| `:ACQuire:TYPE <type>` / `?` | Discrete | `{NORMal\|AVERages\|PEAK\|HRESolution}`, default `NORMal`; echoes `NORM`, `AVER`, `PEAK`, `HRES` | — | 22 |
| `:ACQuire:MDEPth <mdep>` / `?` | Discrete | Single channel `{AUTO\|12000\|120000\|1200000\|12000000\|24000000}`; two channels `{AUTO\|6000\|60000\|600000\|6000000\|12000000}`; three/four `{AUTO\|3000\|30000\|300000\|3000000\|6000000}`; default `AUTO` | pts | 21 |
| `:ACQuire:SRATe?` | — | Query only; NR3 | Sa/s | 23 |
| `:ACQuire:AVERages <count>` / `?` | Integer | `2^n`, n = 1..10 (2 to 1024), default 2 | — | 20 |

- `24000000` (single channel), `12000000` (two), and `6000000` (three/four) are
  documented as optional memory depths (PDF p. 21), consistent with `*OPT?`
  failing on this firmware.
- The documented relation is `memory depth = sample rate × waveform length`, and
  `waveform length = 12 × horizontal timebase` (PDF pp. 21, 23). Read
  `:ACQuire:SRATe?` instead of deriving it.
- **`:ACQuire:MDEPth` is only writable while the acquisition is running**
  (`hardware-verified`): with `:TRIGger:STATus?` = `TD`, `12000`, `120000`, and
  `1200000` were accepted immediately and read back unchanged; with the
  acquisition stopped the same writes returned `-200,"Execution error"` and the
  value stayed `AUTO`.
- **Suffixed depths are rejected** (`hardware-verified`): `12K`, `120K`, `1.2M`,
  `24M`, and `DEFAULT` return `-220,"Parameter error"` in either run state. Bare
  `AUTO` is always accepted. This matches the manual's general rule that setting
  commands take numbers with default units and "cannot recognize the units sent
  with the parameters" (PDF p. 17, note 3).
- `:ACQuire:TYPE` accepts `NORM`, `PEAK`, `AVER`, `HRES` while running and does
  not restrict the memory-depth write (`hardware-verified` for acceptance only;
  no waveform was downloaded in `AVER` or `HRES`).
- Order that works (`hardware-verified`): `:RUN` → `:ACQuire:MDEPth <bare
  number>` → wait for the acquisition → `:STOP` → `:WAVeform:MODE RAW` →
  `:WAVeform:STARt` / `:WAVeform:STOP` → `:WAVeform:DATA?`.

Evidence-unit state: `:ACQuire:TYPE?` = `NORM`, `:ACQuire:MDEPth?` = `AUTO`
(screen showed 240 kpts), `:ACQuire:SRATe?` = `1.000000e+09`
(`hardware-verified`).

## Reading modes and windows (`:WAVeform`, PDF pp. 233-241)

| Command | Parameter | Range / default | Page |
|---|---|---|---|
| `:WAVeform:SOURce <source>` / `?` | Discrete | `{CHANnel1..CHANnel4\|D0..D15\|MATH}`, default `CHANnel1` | 233 |
| `:WAVeform:MODE <mode>` / `?` | Discrete | `{NORMal\|MAXimum\|RAW}`, default `NORMal`; echoes `NORM`, `MAX`, `RAW` | 234 |
| `:WAVeform:FORMat <format>` / `?` | Discrete | `{WORD\|BYTE\|ASCii}`, default `BYTE` | 234 |
| `:WAVeform:STARt <sta>` / `?` | Integer | NORM: 1 to 1200; MAX: 1 to the effective on-screen points; RAW: 1 to the current memory depth; default 1 | 240 |
| `:WAVeform:STOP <stop>` / `?` | Integer | Same ranges as `STARt`; default 1200 | 241 |
| `:WAVeform:DATA?` | — | Returns a TMC `#9` block (BYTE/WORD) or comma-separated volts (ASCii) | 235 |

- `MODE NORMal` reads the screen record (1200 points typical). `MODE MAXimum`
  reads the on-screen record while running and the internal memory when stopped.
  `MODE RAW` reads the internal memory and **requires the stop state**: the
  manual states the internal memory "can only be read when the oscilloscope is
  in the stop state" (PDF p. 234). On hardware, `:WAVeform:STOP 100000` while
  running was rejected with `-220,"Parameter error"` and the window silently
  stayed at 1000; after `:STOP` the same write was accepted
  (`hardware-verified`).
- With `MATH` selected only `NORMal` is valid (PDF pp. 233-234).
- The window is `STARt`/`STOP`, and `:WAVeform:POINts?` = `STOP - STARt + 1`
  (`hardware-verified`). `:WAVeform:POINts?` **is not in the Programming Guide**;
  it answered on `00.04.02.SP4` but must be labelled `UNVERIFIED` against any
  manual.
- **Rejected window writes keep the old window.** The manual gives no error for
  an out-of-range `STOP`; the firmware answers `-220` while running. Always read
  `:WAVeform:STARt?` / `:WAVeform:STOP?` / `:WAVeform:POINts?` back instead of
  trusting the write.
- **Mode switch residue.** Leaving `STOP = 240001` and switching back to `NORM`
  made `:WAVeform:POINts?` and the preamble report 240 001 points with a 2 µs
  x-increment for a 1200-point screen capture (`hardware-verified`): the
  metadata then contradicts the mode. Set both window ends explicitly after every
  mode change and cross-check `points` against the mode.
- Mode to preamble field 2: `NORM` = 0, `MAX` = 1, `RAW` = 2. NORM and RAW were
  exercised; MAXimum was accepted after `:STOP` and reported field 2 = 1 with
  240 000 points (`hardware-verified`).

## Batch limits when reading the internal memory (PDF p. 235)

The maximum number of points per `:WAVeform:DATA?` in the internal memory depends
on the return format (`documented`, PDF p. 235):

| `:WAVeform:FORMat` | Maximum points per read |
|---|---|
| `BYTE` | 250000 |
| `WORD` | 125000 |
| `ASCii` | 15625 |

Read in consecutive windows when the memory depth exceeds that limit, e.g.
`1..125000`, `125001..250000`, `250001..300000`, and concatenate in order (PDF
p. 236). The default depth of 240 000 points on the evidence unit fit a single
BYTE read (240 000 bytes in 638 ms, `hardware-verified`); `1.2M`, `12M`, and
`24M` do not, and this Skill's scripts have no batching path, so a large depth
must be chunked by the caller or left as `UNSUPPORTED`.

## Block framing

`:WAVeform:DATA?` in BYTE or WORD returns the TMC block
`#9` + nine ASCII length digits + payload (PDF p. 237). Observed
(`hardware-verified`):

| Read | Points | Declared length | Total bytes received |
|---|---|---|---|
| NORM 1..1200 | 1200 | 1200 | 1212 (11-byte header + payload + `\n`) |
| RAW 1..4000 | 4000 | 4000 | 4012 |
| RAW 1..240000 | 240000 | 240000 | 240 000 payload bytes in 638 ms |

`ASCii` format returns comma-separated volts with no TMC header (PDF p. 237).
Validate `declared length == STOP - STARt + 1` for BYTE, and
`declared length == 2 × points` for WORD; a mismatch is `INVALID`, not something
to pad.

## Preamble (`:WAVeform:PREamble?`, PDF p. 242)

The query returns ten comma-separated fields
`<format>,<type>,<points>,<count>,<xincrement>,<xorigin>,<xreference>,<yincrement>,<yorigin>,<yreference>`:

| Field | Meaning per PDF p. 242 | Observed (NORM / RAW) |
|---|---|---|
| `<format>` | 0 BYTE, 1 WORD, 2 ASC | 0 / 0 |
| `<type>` | 0 NORMal, 1 MAXimum, 2 RAW | 0 / 2 |
| `<points>` | 1 to 12 000 000 (24 000 000 with the option) | 1200 / 4000 |
| `<count>` | averages in average mode, else 1 | 1 / 1 |
| `<xincrement>` | time between neighbouring points: `TimeScale/100` in NORM, `1/SampleRate` in RAW (PDF p. 238) | 2.000000e-06 / 1.000000e-09 |
| `<xorigin>` | start time of the data | -1.200000e-03 / -1.200000e-03 |
| `<xreference>` | reference time, reported as 0 (PDF p. 239) | 0 / 0 |
| `<yincrement>` | "the waveform increment in the Y direction" (PDF p. 242); `VerticalScale/25` in NORM, in RAW "related to" the internal and current vertical scale (PDF p. 239) | 2.000000e-02 / 2.093750e-02 |
| `<yorigin>` | vertical offset relative to the reference position, `VerticalOffset/YINCrement` in NORM (PDF p. 239) | -76 / -72 |
| `<yreference>` | vertical reference position; 127 in NORM, scale-dependent in RAW (PDF p. 240) | 127 / 121 |

The manual gives no formula for the RAW `yincrement` and no numeric conversion
anywhere in the preamble definition; treat every RAW constant as firmware
output, never as a computed value.

## Codes to volts

```text
volts = (code - yorigin - yreference) * yincrement
```

Status: `hardware-verified` for the arithmetic on this unit, **not calibrated**.
The expression was reproduced from real blocks and cross-checked against
`:MEASure:VPP?` on the same screen (3.04-3.06 V across the recorded sweep); the
zero code corresponds to
`yorigin + yreference` (51 in NORM). The manual prints the same expression only
inside the worked example under `:WAVeform:DATA?` (PDF p. 237); it states no
calibration guarantee, and the preamble section (PDF p. 242) does not define a
conversion at all. Treat reconstructed volts as `UNVERIFIED`: only the shape,
relative levels, and code statistics are supported claims.

Do not mix increments. At 0.5 V/div the same channel gave `yincrement`
`2.000000e-02` in NORM and `2.093750e-02` in RAW (`hardware-verified`); 0.02 =
0.5 V/div ÷ 25 as documented (PDF p. 239), while 0.0209375 is the RAW value and
has no documented derivation. Reusing one for the other mis-scales the trace by
about 4.7 %.

## Two traps that make a block look valid when it is not

- **A block is returned for a channel that is not displayed.** With
  `:WAVeform:SOURce CHAN2` while CH2 was off, the instrument returned 1200 bytes
  of noise with a nonsense y-increment of 7.76 (`hardware-verified`). A
  well-framed block therefore proves nothing about the signal: check
  `:CHANnel<n>:DISPlay?` and record it with the data.
- **Metadata can contradict the mode** (see the `STOP = 240001` residue above).
  Cross-check `points`, `<type>`, and `<xincrement>` before reporting a block as
  usable.

## Workflow

1. Read state: `:TRIGger:STATus?`, `:TIMebase:MAIN:SCALe?`, channel
   display/scale/offset/coupling/probe, `:ACQuire:TYPE?`, `:ACQuire:MDEPth?`,
   `:ACQuire:SRATe?`.
2. For screen data only: `:WAVeform:SOURce CHAN<n>` → `:WAVeform:MODE NORM` →
   `:WAVeform:FORMat BYTE` → `:WAVeform:STARt 1` → `:WAVeform:STOP 1200` →
   `:WAVeform:PREamble?` → `:WAVeform:DATA?`.
3. For deep memory: `:RUN` → `:ACQuire:MDEPth <bare number>` → wait → `:STOP` →
   `:WAVeform:MODE RAW` → window within the batch limit → `:WAVeform:PREamble?`
   → `:WAVeform:DATA?`.
4. Save the raw bytes and their SHA-256 before parsing anything.
5. Report declared versus observed length, point count, mode, both preamble
   increments, the channel context, and the calibration status
   (`UNVERIFIED` for volts).

Script entry points (offline parser and live transport are separate):

```text
python3 scripts/ds1000z_protocol.py waveform assets/fixtures/waveform-norm-ch1.bin --csv-out wave.csv
python3 scripts/ds1000z_protocol.py preamble assets/fixtures/preamble-norm.txt
python3 scripts/ds1000z_protocol.py block assets/fixtures/waveform-norm-block.bin
python3 scripts/ds1000z_session.py --host 10.99.0.194 --allow-writes waveform --out wave.bin --mode NORM --channel 1
```

The `waveform` session subcommand takes `--channel`, `--mode {NORM,MAX,RAW}`,
`--start`, `--stop`, `--out`, `--overwrite`; the `capture` subcommand bundles
identity, measurements, preamble, waveform, and optionally `--with-screenshot`
into one report. No subcommand enables the record function, sends `:AUToscale`,
or batches a large RAW read.

## Integrity statuses for this workflow

- `COMPLETE`: block framing, declared length, point count, window, and mode all
  agree, and the channel context was recorded.
- `INCOMPLETE`: short block, missing `\n`, points fewer than `STOP - STARt + 1`,
  or a memory depth that needs batching that was not done.
- `INVALID`: declared length contradicts the point count, `#` block is malformed,
  or the preamble contradicts the mode.
- `UNVERIFIED`: framing is sound but the volts are reconstructed, the channel was
  not displayed, `:WAVeform:POINts?` was used (undocumented), or MAXimum byte
  semantics were assumed.
- `UNSUPPORTED`: MATH source, digital channels, batched multi-window reads, and
  the `-S` signal source.
