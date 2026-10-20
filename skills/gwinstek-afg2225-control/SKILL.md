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
- Only one modulation type is active at a time; enabling one disables the
  others.
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
- Amplitude is meaningless without `VOLTage:UNIT?` and `OUTPut:LOAD?`: the unit
  is a global default, and the load is only a reference (manual pp. 143,
  214-215).
- `OUTPut:LOAD` cannot be used while ARB, modulation, sweep, or burst is active
  (manual p. 143). Do not send it as blind prelude to every command.
- The counter is off by default; a `COUNter:VALue?` read without
  `COUNter:STATe ON` is not a measurement.

## Evidence and scope

- **Support level**: `documented` only. No real AFG-2225 response is bundled;
  do not claim `hardware-verified` or `firmware-scoped`.
- **Manual**: *AFG-2225 Series User Manual*, GW Instek part no.
  `82RF-22250M01`, local copy `ref/编程手册.pdf`; the remote-interface chapter
  is PDF pp. 180-199, the command reference pp. 193-272, and the status/error
  model pp. 273-292.
- **External evidence**: the USB CDC VID/PID `0x2184:0x001c` and the
  `/dev/ttyACM0` behavior come from the Linux kernel and community drivers,
  not from the manual. Treat them as transport evidence, not as command
  evidence.
- **Known evidence gaps**: serial defaults, binary ARB byte order, firmware
  behavior of `OUTP1 ON` versus `SOURCE1:OUTPUT ON`, and real-device
  acceptance of the documented command sequences.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

These labels describe evidence, not feature count. This Skill is intentionally
`documented`.

## Device boundary

- **Instrument**: GW Instek AFG-2225, 2-channel, 25 MHz sine/square,
  1 MHz ramp, 500 µHz-25 MHz pulse, 1 µHz resolution, 120 MSa/s ARB,
  60 MHz repetition, 4096-point ARB, 10-bit amplitude.
- **Interface**: USB device port only (Type-B slave); no LAN/GPIB/RS-232.
- **Language**: IEEE 488.2 (1992, fully) and SCPI (1994, partially).
- **Primary data kinds**: `instrument-response` (identity/numeric/queue) and
  `waveform` (arbitrary DAC command).
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
| Cross-check a command across subsystems, or answer a command question no task reference covers | [command-reference.md](references/command-reference.md) |

The command index is a fallback, not a starting point: open it only when the
task reference and the scripts cannot answer the command question. It lists only
commands this Skill already records; anything absent must be verified against the
user manual and labelled `documented` before use, and the safety rules above still
apply.

## Standard remote session

1. Open the already-configured USB CDC COM port (no manual default baud).
2. Send `*IDN?`; preserve raw bytes; validate vendor/model/serial/firmware.
3. Query `SYSTem:VERSion?` when firmware evidence is needed.
4. Clear only authorized status; `*CLS` clears status and error queue.
5. Drain `SYSTem:ERRor?` until `0 No error`/`No error`.
6. Configure waveform/output settings.
7. Turn output on only when authorized; verify `OUTP?` (or use APPLy, which
   is documented to turn it on).
8. Verify readback where a query exists.
9. Drain the error queue again.

Query pairing: one session, one query, one response. Do not send a second
query while an earlier response is unread.

Terminators: LF, CR, or LF/CR. Remote mode locks all panel keys except F5.

## Output workflow

| Need | Preferred sequence | Important side effects |
|---|---|---|
| Quick known waveform | `SOUR<n>:APPL:<shape> [freq[,amp[,offset]]]` | Sets trigger immediate, disables burst/modulation/sweep, and turns output **on**. |
| Precise control without mode reset | `FUNC` -> `FREQ`/`AMPL`/`DCO` -> `OUTP ON` | Output state is controlled by `OUTP`; verify `OUTP?` rather than assuming a low-level command enabled it. |
| Arbitrary waveform | `FUNC USER` -> `FREQ` -> `DATA:DAC` | Rate = frequency × points; verify `OUTP?` before connecting a load. |
| Modulation / sweep / burst | Configure carrier and mode parameters, then enable the mode | Enabling one mode can disable conflicting modes. |

`APPLy` defaults are 1 kHz, 100 mVpp (50 Ω), and 0 V offset. Low-level control
uses `FUNC`, `FREQ`, `AMPL`, `DCO`, `SQU:DCYC`, `RAMP:SYMM`, `PULS:*`, `OUTP`,
`OUTP:LOAD`, and `VOLT:UNIT` (manual pp. 200-215).

## ARB workflow

1. Validate CSV/DAC codes (`load_arb_csv`, `validate_arb_samples`).
2. Scale normalized data if needed (`scale_normalized`, half-away-from-zero,
   no clamping).
3. Build ASCII command (default safe path) or explicit binary block with
   `--byte-order`. Check start address `0..4095` and `start + points <= 4096`.
4. Select `SOURce[1|2]:FUNCtion USER` (manual p. 260 order).
5. Set frequency (rate = Hz × points) and amplitude/offset as needed.
6. Send `DATA:DAC VOLATILE,<start>,...` to volatile memory.
7. Verify readback and `OUTP?` before connecting a load; this helper does not
   auto-enable the output, but the manual's wording for `FUNC USER` is not
   explicit about the output state.

## Offline parser and builders

Use `scripts/afg2225_protocol.py` (transport-independent, stdlib only):

```text
python3 scripts/afg2225_protocol.py identity assets/fixtures/identity.txt
python3 scripts/afg2225_protocol.py numeric assets/fixtures/frequency.txt --quantity frequency --unit Hz
python3 scripts/afg2225_protocol.py error-queue assets/fixtures/error-none.txt
python3 scripts/afg2225_protocol.py arb --csv assets/fixtures/arb-valid.csv --format ascii
```

Stages: `read_frame` -> `parse_metadata` -> `extract_payload` -> `normalize` ->
`validate`; the high-level `parse_identity`, `parse_numeric`, and
`parse_error_queue` are thin compositions of those stages. ARB stages:
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

- `COMPLETE`: framing, required fields, unit/quantity, and applicable range
  checks pass for the stated structural claim.
- `INCOMPLETE`: a required byte, terminator, field, unit, point, or sequence
  is missing.
- `INVALID`: framing, numeric, unit, start-address, or type constraints
  contradict the raw bytes.
- `UNVERIFIED`: parsing succeeded but hardware acceptance, byte order,
  calibration, freshness, or firmware behavior is not proven.
- `UNSUPPORTED`: the response shape or feature is not implemented.

Never silently pad, truncate, clamp, interpolate, or guess. A parsed value is
not proof of hardware acceptance or calibrated output.

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