---
name: gwinstek-afg2225-control
description: Control and document waveform-generation workflows for a GW Instek AFG-2225 dual-channel arbitrary function generator over its USB CDC serial SCPI interface. Use for identity/session setup, APPLy and low-level sine/square/ramp/pulse/noise/ARB output, frequency/amplitude/offset/load handling, AM/FM/FSK/PM/SUM modulation, sweep, burst, counter reads, and validated arbitrary-waveform uploads from CSV or DAC codes.
---

# GW Instek AFG-2225 Control

Use this Skill for the GW Instek AFG-2225 (2-channel, 25 MHz) arbitrary
function generator over its USB CDC serial SCPI interface. The implementation
is based on the official *AFG-2225 Series User Manual* (GW Instek part no.
82RF-22250M01), available from the
[GW Instek AFG-2225 product page](https://www.gwinstek.com/en-global/products/detail/AFG-2225);
the local evidence copy is `ref/编程手册.pdf`. It is `documented` only until a
real instrument response is captured with model, firmware, interface, and
test date.

## Non-negotiable safety rules

- Do not assume the output is safe to enable. Confirm load impedance,
  amplitude, offset, and connected circuit before `OUTPut ON` or any APPLy
  command (APPLy turns the output on).
- Observe `|Voffset| < Vmax - Vpp/2`. Amplitude and offset double when load
  changes from 50 Ω to high-Z.
- dBm units are unavailable in high-Z mode.
- Square duty limits: 1-99 % (≤100 kHz), 10-90 % (≤1 MHz), 50 % (25 MHz).
- Ramp symmetry 0-100 %.
- Pulse width/period limits: period 40 ns-2000 s, width 20 ns-1999.9 s.
- Only one modulation type should be active at a time.
- Do not send `*RST` as routine cleanup; it resets to factory defaults and
  does not delete saved states. Use `*CLS` only when clearing status/error
  state is authorized.
- Do not run `*SAV`/recall/delete/calibration automatically.
- ARB binary uploads require an explicit `--byte-order little|big`; byte order
  is unverified and must not be guessed.
- Do not apply the community DC-offset workaround automatically; it is an
  unverified observation.
- A numerical response is not proof of a valid waveform. Preserve raw bytes
  and configuration context.

## Device boundary

- **Instrument**: GW Instek AFG-2225, 2-channel, 25 MHz sine/square,
  1 MHz ramp, 500 µHz-25 MHz pulse, 1 µHz resolution, 120 MSa/s ARB,
  60 MHz repetition, 4096-point ARB, 10-bit amplitude.
- **Interface**: USB device port only (Type-B slave); no LAN/GPIB/RS-232.
- **Language**: IEEE 488.2 (1992, fully) and SCPI (1994, partially).
- **Primary data kinds**: `instrument-response` and `arbitrary-waveform`.
- **Support level**: `documented`; no hardware response is bundled.
- **Not automatic**: calibration, firmware update, panel save/recall/delete,
  and non-volatile ARB save.

## Task-specific reference table

| Goal | Reference |
|---|---|
| Bench setup, output/trigger/MOD/counter connectors, load and power | [bench-setup.md](references/bench-setup.md) |
| USB CDC setup, terminators, `*IDN?`, status/error, remote/local | [remote-session.md](references/remote-session.md) |
| APPLy vs low-level, load/amplitude/offset, duty/symmetry/pulse | [basic-waveforms.md](references/basic-waveforms.md) |
| AM/FM/FSK/PM/SUM, sweep, burst, counter, phase, coupling | [modulation-sweep-burst.md](references/modulation-sweep-burst.md) |
| ARB memory, DATA:DAC, CSV, validation, quantization | [arbitrary-waveform.md](references/arbitrary-waveform.md) |
| Parser stages, statuses, provenance, limitations | [response-and-evidence.md](references/response-and-evidence.md) |

## Standard remote session

1. Open the already-configured USB CDC COM port (no manual default baud).
2. Send `*IDN?`; preserve raw bytes; validate vendor/model/serial/firmware.
3. Query `SYSTem:VERSion?` when firmware evidence is needed.
4. Clear only authorized status; `*CLS` clears status and error queue.
5. Drain `SYSTem:ERRor?` until `0 No error`/`No error`.
6. Configure waveform/output settings.
7. Turn output on explicitly (or use APPLy).
8. Verify readback where a query exists.
9. Drain the error queue again.

Query pairing: one session, one query, one response. Do not send a second
query while an earlier response is unread.

Terminators: LF, CR, or LF/CR. Remote mode locks all panel keys except F5.

## Output workflow

- **APPLy** (`SOURce[1|2]:APPLy:*`): sets trigger immediate, disables
  burst/modulation/sweep, turns output on. Nested optional parameters.
  Defaults: 1 kHz, 100 mVpp (50 Ω), 0 V offset.
- **Low-level** (`FUNC`, `FREQ`, `AMPL`, `DCO`, `SQU:DCYC`, `RAMP:SYMM`,
  `PULS:*`, `OUTP`, `OUTP:LOAD`, `VOLT:UNIT`): precise control without
  changing mode state. Output must be enabled explicitly.

## ARB workflow

1. Validate CSV/DAC codes (`load_arb_csv`, `validate_arb_samples`).
2. Scale normalized data if needed (`scale_normalized`, half-away-from-zero,
   no clamping).
3. Build ASCII command (default safe path) or explicit binary block with
   `--byte-order`.
4. Check start address `0..4095` and `start + points <= 4096`.
5. Send `DATA:DAC VOLATILE,<start>,...`.
6. Select `SOURce[1|2]:FUNCtion USER`.
7. Set frequency (rate = Hz × points).
8. Verify readback where available; the output remains off unless explicitly
   enabled.

## Offline parser and builders

Use `scripts/afg2225_protocol.py` (transport-independent, stdlib only):

```text
python3 scripts/afg2225_protocol.py identity assets/fixtures/identity.txt
python3 scripts/afg2225_protocol.py numeric assets/fixtures/frequency.txt --quantity frequency --unit Hz
python3 scripts/afg2225_protocol.py error-queue assets/fixtures/error-none.txt
python3 scripts/afg2225_protocol.py arb --csv assets/fixtures/arb-valid.csv --format ascii
```

Stages: `read_frame`, `parse_identity`/`parse_numeric`/`parse_error_queue`,
`load_arb_csv`, `scale_normalized`, `validate_arb_samples`,
`encode_ieee_block`/`decode_ieee_block`, `build_data_dac_ascii`,
`build_data_dac_binary`, `build_arb_artifact`.

`parse_numeric` requires a terminator, rejects trailing bytes, and converts
documented suffixes (for example `kHz`, `ms`) to a canonical base unit while
retaining `raw_value` and `raw_unit`. A unit that conflicts with the declared
quantity is `INVALID`, never silently reinterpreted.

Optional live transport: `scripts/afg2225_session.py` (lazy pyserial import,
`--dry-run` prints exact bytes).

## Integrity statuses

`COMPLETE`, `INCOMPLETE`, `INVALID`, `UNVERIFIED`, `UNSUPPORTED`. Never
silently pad, truncate, clamp, interpolate, or guess.

## Verification commands

```bash
python3 -m unittest discover -s skills/gwinstek-afg2225-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/gwinstek-afg2225-control
npx skills@latest add . --list
```

## Known limitations / manual defects

- No hardware verification; all capabilities `documented`.
- USB CDC only; no LAN/GPIB/RS-232.
- Binary ARB byte order unverified (ASCII default).
- Manual example `DATA:DAC VOLATILE, #216 Binary Data` claims 5 values /
  16 bytes, but 5 × 2 = 10 bytes (documented defect).
- `115200 8N1` is an assumption, not a manual default.
- No automatic reset/save/delete/calibration.
- Community observations (unverified): `SOURCE1:OUTPUT ON` vs `OUTP1 ON`;
  positive DC offset with ARB can invert signal.
- Linux device ID `0x2184:0x001c` is external evidence, not manual text.