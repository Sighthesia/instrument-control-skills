# Parser Support Record

- Parser status: `hardware-verified` for the captured subset; `documented` for
  every other command family.
- Hardware verification: `true`
- Verified model/firmware/interface: GW Instek **GDS-2104A**, serial
  `GEN182193`, firmware `V1.18`, USB CDC-ACM `2184:0014` at `/dev/ttyACM1`,
  115200 8N1, LF terminator, captured **2026-11-26**.
- Raw evidence: `artifacts/hw-verify/gds2000a-20261126/` (git-ignored, local
  reference only). Fixture raw bytes that ship with the Skill are in
  `assets/fixtures/hardware/`; `assets/fixtures/README.md` records each hash and
  source. `assets/fixtures/synthetic/` contains constructed rejection cases and
  is never hardware evidence.
- Manual source: *GDS-2000A Series Programming Manual*, Version 1.4, August
  2013, local converted text
  `ref/GDS-2000A_Programming_Manual_v1.4.extracted.md`. The converted copy has
  no body page breaks; page citations are table-of-contents or **List of
  Commands in Functional Order** markers (pp. 24-34), not inferred body pages.
- Supported data kinds: `identity` (`*IDN?`), `scalar-measurement`
  (`:MEASure:*?`), `status-record` (error queue), `waveform`
  (`:ACQuire<n>:MEMory?`), and raw `screen-image` (`:DISPlay:OUTPut?`), all
  from saved/offline bytes; the optional USB CDC transport is separate.
- Coverage: **51 hardware-verified forms** among the **339** forms in the
  manual's List of Commands, plus **2 body-only forms** in Appendix A
  (`:DISPlay:OUTPut?`, `:GONogo:SCRipt?`). The remaining **288** list forms are
  `documented` only. See
  [references/command-reference.md](references/command-reference.md) for the
  per-row status and the counting method.

## Verified subset

Exactly these observations have real responses or set/readback evidence:

- `*IDN?` -> `GW,GDS-2104A,GEN182193,V1.18`.
- `:SYSTem:ERRor?` -> `+0, "No error."`; preserved `-113, "Undefined header"`
  and `-108, "Parameter not allowed"` records.
- Read-only queries: acquisition mode/record length/header; CH1 bandwidth
  limit, coupling, deskew, display, expand, impedance, invert, position, probe
  ratio/type, and scale; math display/type; hardcopy mode, assign, format, and
  ink-saver states; measurement gating/method; timebase position/scale/mode;
  trigger frequency/type/source/coupling/noise rejection/frequency rejection/
  mode/holdoff/level/edge slope/state; panel lock; save-image format/ink saver;
  search state/total; buzzer; Go-NoGo script state; segment state/total.
- Set/readback/restore: `:CHANnel1:SCALe` (2.0 -> 1.0), `:CHANnel1:COUPling`
  (AC -> DC), `:TIMebase:SCALe` (1.000000e-03 -> 5.000000e-04),
  `:TRIGger:LEVel` (2.600E+00 -> 2.520E+00), and `:BUZZER` (`OFF`).
- `:MEASure:SOURce1` changed to `CH2` and restored to `CH1`;
  `:MEASure:PK2PK?` -> `8.000E-02`; inactive CH2 -> `Ch Off`.
- Loopback with an AFG-2225 on CH1 (1 MOhm, 1x, DC): after
  `:CHANnel1:SCALe 0.5`, `:CHANnel1:POSition 0`, `:TRIGger:LEVel 0`, and
  `:MEASure:SOURce1 CH1`, a 1 kHz / 1 Vpp (50 ohm reference) sine measured
  `1.000E+03 Hz`, `1.000E-03 s`, `2.060E+00 Vpp`, and `7.270E-01 V RMS`; the
  original scale/position/level were then restored and the error queue was
  empty. Record:
  `artifacts/hw-verify/loopback-20261126/loopback-result.json` (git-ignored).
  One frequency and one level is not a calibration or a flatness check.
- `:STOP` -> `SAVE`, `:RUN` -> `AUTO`, `:SINGle` -> `READY` with acquire state
  `0`; continuous acquisition restored with `:STOP` then `:RUN`.
- `:ACQuire1:MEMory?` after `:STOP`: 5,000 points, 10,000 payload bytes,
  declared and observed lengths equal, one trailing LF; structure `COMPLETE`,
  calibration `UNVERIFIED`.
- `:DISPlay:OUTPut?`: `#538822` + 38,822-byte 16-bit RGB RLE image + LF; raw
  bytes preserved, decode not implemented, `UNVERIFIED`.
- Offline suite: 50 tests pass with no network or serial access.

## Unverified subset

- Code-to-volts conversion, waveform calibration, and any physical-level claim.
  The single 1 kHz loopback point above proves the measurement path and the
  50 ohm-to-1 MOhm doubling, not accuracy, flatness, or a calibrated level.
- Measurement window behaviour: `:MEASure:*?` on this firmware reports based on
  the visible acquisition window. With CH1 at 1 V/div and position -2.48 div a
  2 Vpp signal sits outside the screen, and the frequency/period/amplitude
  queries answer `?` even though the DC path is good. Centre the channel and
  widen the range before concluding "no signal".
- Screen-image RLE decoding.
- Actual `:SAVe:*` file writes and `:HARDcopy:START`.
- CH2-CH4, most trigger subtypes, most individual measurement items,
  slotted-measurement configuration, math/FFT configuration, cursors,
  reference waveforms, labels, marks, search configuration, and bus/digital
  decode.
- DVM, DS2-FGN function generator, Go-NoGo/template execution, and data
  logging.
- Ethernet (DS2-LAN), GPIB (DS2-GPIB), and RS-232C.
- Other GDS-2000A models and other firmware revisions.

## Known limitations

- Hardware evidence covers one GDS-2104A, firmware V1.18, USB CDC-ACM, on
  2026-11-26. Do not extend it to another unit, firmware, model, or interface.
- Waveform voltage conversion is unavailable in the manual and always
  `UNVERIFIED`; the parser reports codes and `analysis_allowed =
  code-domain-only`.
- The screen-image RLE decoder is not implemented; the raw block is not a
  verified picture.
- Actual `:SAVe:*` file writes and `:HARDcopy:START` were not sent; file
  existence and content are unverified.
- The 1,000,000-point `:ACQuire1:LMEMory?` capture exists only in local
  evidence and is not shipped.
- CH2-CH4, most trigger subtypes, most individual measurement items,
  slotted-measurement configuration, math/FFT configuration, cursors,
  reference waveforms, bus decode/digital, labels, marks, search configuration,
  DVM, DS2-FGN function generator, Go-NoGo/templates, and data logging were not
  exercised.
- Ethernet (DS2-LAN), GPIB (DS2-GPIB), and RS-232C were not exercised.
- USB CDC serial defaults are not stated by the manual; `115200 8N1` is the
  helper default and the verified host setting, not a device requirement.
- The manual's list omits query `?` and instance suffixes; hardware required
  suffixed query forms such as `:CHANnel1:SCALe?`, `:ACQuire1:MEMory?`, and
  `:MEASure:SOURce1?`. See the command reference's sendable spelling rules.
- Manual/hardware defects: trigger states lack the documented leading `*`;
  `Chan Off` is returned as `Ch Off`; `9.9E+37` is an undocumented no-result
  sentinel; `:TIMebase:EXPand?` returns `-221` on V1.18; the second LF after
  `:TRIGger:FREQuency?` is framing only.

Do not upgrade this record to `firmware-scoped` for another unit without
preserving the actual `*IDN?` identity, model, firmware, interface, test date,
and raw responses.
