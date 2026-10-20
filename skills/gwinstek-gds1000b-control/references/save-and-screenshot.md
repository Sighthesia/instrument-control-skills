# Save and Screenshot (GDS-1000B)

Manual: *GDS-1000B Series Programming Manual*, Version 1.00, March 2015,
pp. 78-80 (hardcopy), pp. 164-168 (save/recall). Support level: `documented`.

## Critical boundary

**Two different things are true, and the earlier version of this page conflated them.**

- `:DISPlay:OUTPut?` **does** return the screen image over SCPI: a 16-bit RGB
  run-length encoded image framed as `#<n><len>[count][color]...[count][color]<LF>`,
  where each `[count]`/`[color]` pair is 2 bytes (manual p. 77). So remote image
  readback exists.
- **Saved files still cannot be read back.** `:SAVe:IMAGe` writes `Disk:/` or
  `USB:/`; no command returns those file bytes. Retrieving them still needs
  physical media, a separate transfer mechanism, or operator action.

The bundled parser does **not** implement the RLE decoder for
`:DISPlay:OUTPut?`. Until it does, a raw response may be saved as bytes but
must not be presented as a decoded or verified image.


## Image save

```text
:SAVe:IMAGe:FILEFormat {PNG|BMP}
:SAVe:IMAGe:INKSaver {ON|OFF}
:SAVe:IMAGe "Disk:/pic1.PNG"
:SAVe:IMAGe "USB:/pic1.BMP"
```

Manual pp. 165-166.

- Filename is limited to **8 characters** (the extension is additional in the
  manual's examples).
- Path must start with `Disk:/` or `USB:/`.
- Format must match the extension: `.PNG` -> `PNG`, `.BMP` -> `BMP`.
- `INKSaver ON` reduces ink for printing; it does not change resolution.
- The command writes to the instrument's storage. It does not stream the image
  back over SCPI.
- Never overwrite an existing operator file. Choose a new name, or confirm the
  overwrite with the operator first.

`scripts/gds1000b_session.py save-image --path "Disk:/pic1.PNG"` validates the
prefix, filename length, and extension, then sends the three commands.

## Hardcopy

```text
:HARDcopy:MODe {PRINT|SAVE}
:HARDcopy:ASSIGN {IMAGe|WAVEform|SETUp|ALL}
:HARDcopy:SAVEFORMat {PNG|BMP}
:HARDcopy:PRINTINKSaver {ON|OFF}
:HARDcopy:SAVEINKSaver {ON|OFF}
:HARDcopy:START
```

Manual pp. 78-80.

- `MODe SAVE` directs output to storage; `PRINT` sends to a configured printer.
- `ASSIGN` selects what is captured.
- `START` performs the operation.
- The helper sets `MODe SAVE`, `ASSIGN IMAGe`, `SAVEFORMat`, and `START`.
  It does not choose the destination filename; use `:SAVe:IMAGe` when an exact
  path is required.

## Waveform save

```text
:SAVe:WAVEform {CH1|CH2|CH3|CH4|MATH|REF1..REF4}, {REF1..REF4|W1..W20}
:SAVe:WAVEform {CH1|CH2|CH3|CH4|MATH|REF1..REF4|ALL}, "<path>"
:SAVe:WAVEform:FILEFormat {LSF|DCSV|FCSV}
:RECAll:WAVEform {W<n>|"<path>"}, REF<X>
```

Manual pp. 167-168.

- Reference memory (REF1-REF4) and W1-W20 slots are finite; saving overwrites
  the selected destination.
- `ALL` saves every displayed waveform; the file path becomes a folder in some
  examples.
- File formats: LSF (instrument binary), DCSV (detail CSV), FCSV (fast CSV).
  Detail CSV cannot be recalled to the scope.
- Saving to `Disk:/` or `USB:/` follows the same filename limits as images.
- `RECAll:WAVEform` replaces the selected reference waveform.

## Setup save and recall

```text
:SAVe:SETUp {S1..S20|"<path>.SET"}
:RECAll:SETUp {S1..S20|"<path>.SET"}
*SAV {1..20}
*RCL {1..20}
```

Manual pp. 33-39, 164-167.

- `S1..S20` and `*SAV`/`*RCL` use the 20 internal setup slots.
- The file form uses `.SET` on `Disk:/` or `USB:/`.
- Recall replaces the live setup; it can change channel, timebase, trigger, and
  display state. Confirm before recalling on an active bench.

## Path and file rules

- Accept only `Disk:/` or `USB:/` prefixes for image paths.
- Filename stem <= 8 characters; use `.PNG` or `.BMP` for images.
- Do not assume a directory exists; create it on the instrument first.
- Do not assume USB media is present. A failed write is an operator-visible
  failure, not a silent fallback.
- Do not overwrite files automatically. The local helper refuses an existing
  local output file unless `--overwrite` is explicit; it cannot enforce the same
  rule on the instrument's storage, so choose unique names.

## Recommended screenshot workflow

1. Confirm the display shows the intended signal, cursors, and measurements.
2. Choose `Disk:/` or `USB:/` and a unique filename <= 8 characters.
3. Set `:SAVe:IMAGe:FILEFormat` to match the extension.
4. Optionally set `INKSaver`.
5. Send `:SAVe:IMAGe "<path>"`.
6. Drain `:SYSTem:ERRor?`.
7. Report the exact path. Do not claim the image was downloaded.
8. Retrieve the file through the operator's chosen file-transfer method.

## Verification limits

- `:DISPlay:OUTPut?` is the only image readback path, and it returns the
  run-length encoded screen, not a PNG and not a saved file. No bundled parser
  decodes it, so its pixel content remains `UNVERIFIED`.
- A successful `:SAVe:IMAGe` means the instrument accepted the request; it does
  not prove the file exists, is readable, or contains the expected screen. The
  documented failure modes are `-250` mass storage error, `-252` missing media,
  `-254` media full, `-256` file name not found, `-257` file name error, and
  `-258` media protected (manual p. 252), so drain `:SYSTem:ERRor?` instead of
  assuming success.
- File naming and storage behavior are firmware-dependent and `documented`
  only.
