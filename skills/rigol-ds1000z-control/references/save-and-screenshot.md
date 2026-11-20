# Screenshot Capture and Storage Commands (DS1000Z)

Load this reference when you need a screen image from the instrument, or when
someone asks why `:DISPlay:DATA?` produced a broken BMP — and load it before
touching anything in the store/reference/pass-fail families, because those change
instrument state.

Command syntax and page numbers come from the *MSO1000Z/DS1000Z Programming
Guide*, PGA19108-1110, Software Version 00.04.03.SP2 (PDF physical pages). Values
marked `hardware-verified` were observed on `RIGOL TECHNOLOGIES,DS1074Z,
DS1ZA171004155,00.04.02.SP4`; raw streams are in `artifacts/rigol-ds1000z/raw/`.
Everything else is `documented` and untested on that firmware.

## `:DISPlay:DATA?` — documented syntax (PDF p. 79)

```text
:DISPlay:DATA? [<color>,<invert>,<format>]
```

| Parameter | Type | Range | Default |
|---|---|---|---|
| `<color>` | Bool | `{ON\|OFF}`; `ON` = colour, `OFF` = intensity-graded | `ON` |
| `<invert>` | Bool | `{{1\|ON}\|{0\|OFF}}` | `0\|OFF` |
| `<format>` | Discrete | `{BMP24\|BMP8\|PNG\|JPEG\|TIFF}` | `BMP24` |

With all arguments omitted the instrument is documented to use the current
`:STORage:IMAGe:COLor` and `:STORage:IMAGe:INVERT` settings and `BMP24`
(PDF p. 79). The manual describes the reply as a TMC header plus image data —
`800 × 480 × 3 + 54 = 1152054` bytes for BMP24 — and instructs the caller to
strip the TMC header **and remove the trailing `\n` (0x0A)** (PDF p. 79, note 4).

## What this firmware actually does (`hardware-verified`)

- **Only 0 to 2 arguments are accepted.** Bare, `ON`, `OFF`, `ON,OFF`, and
  `ON,ON` all returned an image (each with a distinct payload hash: colour/mono
  and inverted variants). Any third argument is rejected with `command error`
  plus `-220,"Parameter error"`: `ON,OFF,BMP`, `OFF,ON,BMP`, `OFF,OFF,PNG`,
  `OFF,OFF,JPEG`, `OFF,OFF,0` all failed. **Image format is fixed BMP on this
  firmware**, whatever the manual's `<format>` parameter and
  `:STORage:IMAGe:TYPE` say — the storage setting governs front-panel file
  saves, not this query.
- **The stream carries three bytes past the declared length.** Declared
  `1152054`, total `1152068`: header `#9` + `1152054` + the complete BMP + the
  extra bytes `;0\n`. The manual only warns about the final `\n`, so trimming
  "to the end minus one newline" leaves `;0` appended and `file(1)` rejects the
  file. Trim to the declared length exactly.
- Payload structure: `BM`, `bfSize` = 1152054, pixel data offset 54, 800 × 480
  × 24 bit. Validate those four numbers before writing the file.
- **Latency is 2.2-6.2 s per capture.** Set the read timeout well above that and
  never re-send the query after a slow read; a second query while the first is
  still streaming makes the session unusable. The manual warns that the receive
  buffer must be large enough and that the terminator must be removed
  (PDF p. 79).

Capture sequence:

```text
:DISPlay:DATA?            one write, read the long block, keep the raw bytes
-> declared length from #9 + 9 digits
-> verify BM / 1152054 / offset 54 / 800x480x24
-> write declared-length prefix to .bmp
-> report declared length, observed length, both SHA-256 values, argument set
```

The scripts write the raw response to `<out>.raw` and the trimmed image to
`--out`, never overwrite an existing path without `--overwrite`, and refuse
to "repair" a length mismatch: a mismatch is reported, not padded.

## Display settings that change the image

These are `documented`, cheap to read, and change what the screenshot shows — so
record them with the image:

| Command | Range / default | Page |
|---|---|---|
| `:DISPlay:TYPE <type>` / `?` | `{VECTors\|DOTS}`, default `VECTors`; echoes `VECT`/`DOTS` | 80 |
| `:DISPlay:GRID <grid>` / `?` | `{FULL\|HALF\|NONE}`, default `FULL`; evidence unit answered `FULL` | 82 |
| `:DISPlay:GRADing:TIME <time>` / `?` | Persistence time | 81 |
| `:DISPlay:WBRightness <time>` / `?` | Waveform brightness | 81 |
| `:DISPlay:GBRightness <brightness>` / `?` | Grid brightness, integer 0 to 100, default 50 | 82 |
| `:DISPlay:CLEar` | Clear the display; the waveform reappears immediately in RUN | 78 |

`:DISPlay:BRIGhtness?` is **not** a valid header on `00.04.02.SP4` (returns
`command error`); the documented name is `GBRightness` (PDF p. 82). This is one
of several places where an invented abbreviation fails while the documented long
form works.

## Storage-related families: present in the manual, not implemented here

**This Skill sends none of these.** They change instrument state, consume
instrument memory, or overwrite what the operator stored. Listing them here is
for cross-checking a header, not an invitation to use them.

### Storage of image files (`:STORage`, PDF pp. 158-159)

| Command | Range / default | Page |
|---|---|---|
| `:STORage:IMAGe:TYPE <type>` / `?` | `{PNG\|BMP8\|BMP24\|JPEG\|TIFF}`, default `PNG` | 158 |
| `:STORage:IMAGe:INVERT <bool>` / `?` | `{{1\|ON}\|{0\|OFF}}`, default `0` | 158 |
| `:STORage:IMAGe:COLor <bool>` / `?` | `{ON\|OFF}`, default `ON` | 159 |

The whole `:STORage` subsystem contains only these three parameter commands
(PDF p. 158): there is **no** command to write a file to USB or to write the
screen to a named file. Any `:STORage:*` write only changes how the front panel
would save, so it is pointless here and disabled by policy.

### Setup export/import (`:SYSTem:SETup`, PDF p. 163)

```text
:SYSTem:SETup <setup_stream>     # import (restores the instrument to that state)
:SYSTem:SETup?                   # export a TMC block, example header #9000002077
```

- The `<setup_stream>` must be the exact bytes previously returned by
  `:SYSTem:SETup?`; it cannot be constructed (PDF p. 163).
- **On `00.04.02.SP4`, `:SYSTem:SETup?` returns `command error`**
  (`hardware-verified`). So the documented save/restore path does not exist on
  the evidence unit: there is no verified way to round-trip a setup on this
  firmware.
- In any case, `:SYSTem:SETup <stream>` is a state-restoring write: it can revert
  the operator's channel, trigger, and timebase configuration silently. It is
  never part of a measurement script.

### Reference waveforms (`:REFerence<n>:SAVe`, PDF p. 145)

```text
:REFerence<n>:SAVe        <n> = {1|2|3|4|5|6|7|8|9|10}
```

Stores the current reference channel's waveform in internal memory
(PDF p. 145). Related commands: `:REFerence<n>:ENABle`, `:SOURce`, `:VSCale`,
`:VOFFset`, `:RESet`, `:CURRent`, `:COLor`, and `:REFerence:DISPlay`
(PDF pp. 142-145). `SAVe` and `RESet` destroy what is in that reference slot, so
they are operator-only writes.

### Pass/fail masks (`:MASK`, PDF pp. 123-127)

`:MASK:ENABle`, `:SOURce`, `:OPERate`, `:MDISplay`, `:SOOutput`, `:OUTPut`,
`:X`, `:Y`, `:CREatE`, `:PASSed?`, `:FAILed?`, `:TOTal?`, `:RESet`
(PDF pp. 123-127). Enabling pass/fail also switches off `:AUToscale`-like
behaviour in the other direction: the manual states that sending `:AUToscale`
disables pass/fail first (PDF p. 18). Not implemented; the mask statistics are
meaningful only while the operator watches the instrument.

### What does not exist in this manual

`grep` over the programming guide finds **no `*SAV`, no `*RCL`, no `:SAVE`, and
no `:RECAll` subsystem** for this family. Setup and file storage live under
`:SYSTem:SETup` (PDF p. 163), `:STORage:*` (PDF p. 158), and
`:REFerence<n>:SAVe` (PDF p. 145). Aliases that exist on other Rigol families do
not exist here, and `scripts/ds1000z_session.py` rejects `*RST`, `*SAV`, `*RCL`,
`:SAVE`, `:RECAll`, and every writing `:LAN:` command unconditionally.

## Never overwrite instrument-side content

- Do not send `:REFerence<n>:SAVe`, `:REFerence<n>:RESet`, `:SYSTem:SETup
  <stream>`, `:MASK:CREatE`, `:MASK:RESet`, `:CALibrate:STARt`, or
  `:SYSTem:OPTion:*` as part of a capture workflow. Each one replaces operator
  data or instrument configuration that cannot be recovered through this Skill.
- Do not overwrite local output files either. The session helper refuses an
  existing path unless `--overwrite` is given explicitly, and always reports the
  exact path plus SHA-256 so a caller can prove what was written.
- A screenshot is evidence only with its context: the argument set, the capture
  time, `*IDN?`, `:TRIGger:STATus?`, the per-channel display/scale/offset, and
  the SHA-256 of both the raw stream and the trimmed image.

## Statuses for this workflow

- `COMPLETE`: `#9` header, declared length 1152054, `BM`/`bfSize`/offset/geometry
  all agree, and the file was written from exactly the declared bytes.
- `INCOMPLETE`: short read, missing terminator, or fewer bytes than declared.
- `INVALID`: header is not `#9`, declared length does not match the BMP header,
  or the geometry is not 800 × 480 × 24.
- `UNVERIFIED`: the image parsed but the on-screen state was not recorded, or a
  third argument was assumed to work.
- `UNSUPPORTED`: non-BMP formats on this firmware, `:SYSTem:SETup` export,
  reference-waveform storage, and pass/fail control.

## CLI

```text
python3 scripts/ds1000z_session.py --host 10.99.0.194 screenshot --out screen.raw [--arguments ON,OFF] [--overwrite]
python3 scripts/ds1000z_protocol.py screenshot assets/fixtures/screenshot-compact.bin --out screen.bmp [--overwrite]
```

`screenshot --out` writes the trimmed BMP to the given path and the exact raw
response (including the trailing `;0\n`) to `<out>.raw`. `--arguments` sends the
documented argument set verbatim; passing three arguments reproduces the
documented-but-rejected case, which is reported as an error from the queue rather
than a silent failure. Expect a multi-second read and do not run the query twice.
