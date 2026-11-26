# Save and Screenshot (GDS-2000A)

Manual: *GDS-2000A Series Programming Manual*, Version 1.4, August 2013.
Hardcopy: TOC pp. 74-77; save/recall: TOC pp. 149-153; display output: TOC
p. 74 (body-only, Appendix A). Support level: the hardcopy/save-image state
queries and the raw `:DISPlay:OUTPut?` block are `hardware-verified`; every
write that prints, saves, or changes a file is `documented` and was not
exercised.
Page numbers are table-of-contents or List of Commands markers (pp. 24-34); the
local converted copy has no body page breaks.

## Critical boundary

Two different things are true:

- `:DISPlay:OUTPut?` **does** return the screen image over SCPI: a 16-bit RGB
  run-length encoded image framed as `#<n><len>[count][color]...[count][color]`
  plus a line feed. The verified response was `#538822` + 38,822 payload bytes
  + LF; each `[count]` and `[color]` is 2 bytes.
- **Saved files still cannot be read back.** `:SAVe:IMAGe` writes `Disk:/` or
  `USB:/`; no command returns those file bytes. Retrieving them needs physical
  media, a separate transfer mechanism, or operator action.

The bundled parser does **not** implement the RLE decoder. A raw response may
be saved as bytes but must not be presented as a decoded or verified image.

## Screen-image readback

```text
:DISPlay:OUTPut?
```

Body-only command, documented at TOC p. 74 but absent from the manual's List of
Commands. Return format: header + data + LF.

- Header `#<n><len>` uses the IEEE 488.2 definite-length convention; `len` is
  the image payload byte count.
- Payload is 16-bit RGB run-length data: pairs of `[count][color]`.
- The verified block declared 38,822 bytes and arrived with one trailing LF
  (38,830 raw bytes including the 7-byte header and LF).
- The session helper `screenshot --out screen.bin` saves the raw bytes and
  reports `status: UNVERIFIED`, `reason: image decoding is not implemented`.
  It refuses to overwrite an existing local file unless `--overwrite` is
  explicit.

Do not confuse this with a PNG/BMP file. The raw block is not a standard image
file.

## Hardcopy state (queried, not started)

```text
:HARDcopy:MODe {PRINT|SAVE|?}
:HARDcopy:PRINTINKSaver {OFF|ON|?}
:HARDcopy:SAVEINKSaver {OFF|ON|?}
:HARDcopy:SAVEFORMat {PNG|BMP|?}
:HARDcopy:ASSIGN {IMAGe|WAVEform|SETUp|ALL|?}
:HARDcopy:START
```

Manual TOC pp. 74-77. The verified unit reported:

- `:HARDcopy:MODe?` -> `SAVE`
- `:HARDcopy:PRINTINKSaver?` -> `ON`
- `:HARDcopy:SAVEINKSaver?` -> `OFF`
- `:HARDcopy:SAVEFORMat?` -> `BMP`
- `:HARDcopy:ASSIGN?` -> `IMAGE`

`:HARDcopy:START` is a write equivalent to pressing the front-panel Hardcopy
key. It was **not sent**. `MODe SAVE` directs output to storage; `PRINT` sends
to a configured printer. `ASSIGN` selects what is captured. `START` performs
the operation. The helper does not implement a hardcopy write workflow.

## Image save

```text
:SAVe:IMAGe "Disk:/pic1.PNG"
:SAVe:IMAGe "USB:/pic1.BMP"
:SAVe:IMAGe:FILEFormat {PNG|BMP|?}
:SAVe:IMAGe:INKSaver {OFF|ON|?}
```

Manual TOC pp. 150-151.

- Filename is limited to **8 characters** (the extension is additional in the
  manual's examples).
- Path must start with `Disk:/` or `USB:/`.
- Use a matching extension: `.PNG` with `PNG`, `.BMP` with `BMP`.
- `INKSaver ON` reduces ink for printing/saving; it does not change resolution.
- The command writes to the instrument's storage. It does not stream the image
  back over SCPI.
- Never overwrite an existing operator file. Choose a new name, or confirm the
  overwrite with the operator first.
- Drain `:SYSTem:ERRor?` after the write. A successful command means the
  instrument accepted the request; it does not prove the file exists or is
  readable.
- The verified run queried only the format/ink-saver state (`BMP` and
  `OFF` respectively); it did not write an image.

## Waveform save

```text
:SAVe:WAVEform {CH1..CH4|MATH|REF1..REF4}, {REF1..REF4|W1..W20}
:SAVe:WAVEform {CH1..CH4|MATH|REF1..REF4|ALL}, "<path>"
:SAVe:WAVEform:FILEFormat {LSF|DCSV|FCSV|LMDCSV|LMFCSV|?}
:RECAll:WAVEform {W1..W20|"<path>.LSF"}, REF1..REF4
```

Manual TOC pp. 152-153.

- Reference memory (REF1-REF4) and W1-W20 slots are finite; saving overwrites
  the selected destination.
- `ALL` saves every displayed waveform; the file path becomes a folder in the
  manual's example.
- File formats: LSF (instrument binary), DCSV (detail CSV), FCSV (fast CSV),
  LMDCSV (LM detail CSV), LMFCSV (LM fast CSV).
- **Only LSF can be recalled** by the scope using `:RECAll:WAVEform`; CSV files
  cannot be recalled.
- Saving to `Disk:/` or `USB:/` follows the same filename limits as images.
- `:RECAll:WAVEform` replaces the selected reference waveform.
- The verified run did not save or recall a waveform.

## Setup save and recall

```text
:SAVe:SETUp {S1..S20|"<path>.SET"}
:RECAll:SETUp {S1..S20|"<path>.SET"}
*SAV {1..20}
*RCL {1..20}
```

Manual TOC pp. 37-40, 149-151.

- `S1..S20` and `*SAV`/`*RCL` use the 20 internal setup slots.
- The file form uses `.SET` on `Disk:/` or `USB:/`.
- Recall replaces the live setup; it can change channel, timebase, trigger,
  and display state. Confirm before recalling on an active bench.
- Do not use `*RST` as a cleanup step; it discards the operator's setup.

## Path and file rules

- Accept only `Disk:/` or `USB:/` prefixes for instrument paths.
- Filename stem <= 8 characters; use `.PNG` or `.BMP` for images, `.SET` for
  setups, and the documented waveform extension.
- Do not assume a directory exists; create it on the instrument first.
- Do not assume USB media is present. A failed write is an operator-visible
  failure, not a silent fallback.
- Do not overwrite files automatically. The local helper refuses an existing
  local output file unless `--overwrite` is explicit; it cannot enforce the
  same rule on the instrument's storage, so choose unique names.
- Report the exact path written. Do not claim the file was downloaded.

## Recommended screenshot workflow

1. Confirm the display shows the intended signal, cursors, and measurements.
2. Choose `Disk:/` or `USB:/` and a unique filename <= 8 characters.
3. Set `:SAVe:IMAGe:FILEFormat` to the matching format.
4. Optionally set `:SAVe:IMAGe:INKSaver`.
5. Send `:SAVe:IMAGe "<path>"`.
6. Drain `:SYSTem:ERRor?`.
7. Report the exact path. Do not claim the image was downloaded.
8. Retrieve the file through the operator's chosen file-transfer method.

For a remote raw image without touching instrument storage, use
`:DISPlay:OUTPut?` and save the raw block; label it `UNVERIFIED` until a
decoder is implemented and checked.

## Verification limits

- The RLE decoder is not implemented; pixel content is `UNVERIFIED`.
- `:HARDcopy:START` and all `:SAVe:*` writes are `documented` only. No file
  existence, content, format, or overwrite behavior was exercised.
- The manual's documented mass-storage errors (`-250`, `-252`, `-254`, `-256`,
  `-257`, `-258`) are the reason to drain the queue instead of assuming
  success. They are documented, not observed in this run.
- File naming and storage behavior are firmware-dependent and `documented`
  only.
