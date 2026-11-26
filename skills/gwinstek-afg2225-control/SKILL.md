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
the local evidence copy is `ref/编程手册.pdf`. It is `hardware-verified` only for
the captured subset listed under [Evidence and scope](#evidence-and-scope);
every command family not listed there remains `documented`.

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
- Channel commands must carry the source/output prefix: `SOUR1:FREQ?`,
  `SOUR1:APPL?`, `OUTP1?`. The verified firmware does not answer bare
  `FREQ?`, `VOLT?`, `APPL?`, or `FUNC?`; they leave the response queue empty and
  can desynchronise the next query.
- There is **no SCPI beeper command**. The manual's System Commands list has
  none, and the verified V2.05 did not answer `SYSTem:BEEPer?`, `SYST:BUZZ?`, or
  `:BUZZER?` (it queued `-113 Undefined header` or `-102 Syntax error`). The
  beeper is a panel setting only: UTIL -> F3 System -> F3 Beep -> F2 OFF.

## Evidence and scope

- **Verified instrument**: GW Instek AFG-2225, serial `GEP902745`, firmware
  `V2.05`, USB CDC-ACM `2184:001c` at `/dev/ttyACM0`, 115200 8N1, captured
  **2026-11-26**. The same link also answered at 9600 baud, so the host baud
  rate is not a device setting. Raw bytes are in `assets/captures/` with a
  hash index in `assets/captures/captures.jsonl`; the full exchange is in
  `artifacts/hw-verify/afg2225-20261126/` (git-ignored, local reference only).
- **`hardware-verified` subset** (exactly these observations): `*IDN?`
  (`GW INSTEK,AFG-2225,SN:GEP902745,V2.05\r\n`); the two-line error-queue
  format and its empty-queue form; read-only queries for function, frequency,
  amplitude (`SOUR<n>:AMPLITUDE?` long form only), offset, output state, load,
  phase, duty cycle, counter state/value, and `SOUR<n>:APPL?`; and
  single-parameter write/readback/restore of `SOUR1:FREQ`,
  `SOUR1:AMPLITUDE`, and `SOUR1:DCO` with the output OFF before and after;
  and one output-on loopback on 2026-11-26 (AFG-2225 CH1 into a GDS-2104A
  CH1 at 1 MOhm): `SOUR1:FUNC SIN`, `SOUR1:FREQ 1000`, `SOUR1:AMPLITUDE 1`,
  `SOUR1:DCO 0`, `OUTP1 ON` produced `1.000E+03 Hz`, `2.060E+00 Vpp`, and
  `7.27E-01 V RMS` on the scope, consistent with the 50 Ohm reference
  doubling into 1 MOhm. `OUTP1 OFF` then returned `0` and the original
  `SIN 0.5 Hz / 3 Vpp / 0 V` setup was restored. Evidence:
  `artifacts/hw-verify/loopback-20261126/loopback-result.json`
  (git-ignored). This proves the command path and one amplitude point, not
  amplitude accuracy, flatness, or calibration.
- **`documented` only**: APPLy writes (they turn the output on as a side effect
  and were not sent), ARB `DATA:DAC` upload, binary ARB byte order, modulation,
  sweep, burst, counter enable/measurement, phase/coupling writes,
  save/recall/delete, and calibration. No such write was exercised.
- **Manual**: *AFG-2225 Series User Manual*, GW Instek part no.
  `82RF-22250M01`, local copy `ref/编程手册.pdf`; the remote-interface chapter
  is PDF pp. 180-199, the command reference pp. 193-272, and the status/error
  model pp. 273-292.
- **External evidence**: the USB CDC VID/PID `0x2184:0x001c` was also reported
  by the Linux kernel; the manual does not list VID/PID or `/dev/ttyACM0`.
  Treat those as transport evidence, not command evidence.
- **Known evidence gaps**: binary ARB byte order, modulation/sweep/burst
  writes, amplitude flatness and accuracy/calibration (only one 1 kHz loopback
  point exists), and the manual's undocumented serial defaults.

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence. |
| `hardware-verified` | A real instrument response was captured and checked. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |

These labels describe evidence, not feature count. This Skill is
`hardware-verified` for the captured subset above and `documented` for every
other command family; do not extend one capture to another firmware or unit.

## Device boundary

- **Instrument**: GW Instek AFG-2225, 2-channel, 25 MHz sine/square,
  1 MHz ramp, 500 µHz-25 MHz pulse, 1 µHz resolution, 120 MSa/s ARB,
  60 MHz repetition, 4096-point ARB, 10-bit amplitude.
- **Interface**: USB device port only (Type-B slave); no LAN/GPIB/RS-232.
- **Language**: IEEE 488.2 (1992, fully) and SCPI (1994, partially).
- **Primary data kinds**: `instrument-response` (identity/numeric/queue) and
  `waveform` (arbitrary DAC command).
- **Support level**: `hardware-verified` for the captured read-only and
  single-parameter write/readback subset only; `documented` elsewhere.
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
5. Drain `SYSTem:ERRor?` until the observed empty form `\r\nNo error.`
   (`0 No error` is the manual's single-line form). Each non-empty reply is
   two lines: a CRLF-terminated code such as `-102\r\n` followed by an
   unterminated message such as `Syntax error.`.
6. Configure waveform/output settings.
7. Turn output on only when authorized; verify `OUTP?` (or use APPLy, which
   is documented to turn it on).
8. Verify readback where a query exists. Use `SOUR<n>:AMPLITUDE?`, not the
   rejected short form `SOUR<n>:AMPL?`.
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
`OUTP:LOAD`, and `VOLT:UNIT` (manual pp. 200-215). Read the amplitude back with
the long form `SOUR<n>:AMPLITUDE?`; the verified V2.05 rejects `SOUR<n>:AMPL?`
(no response, `-113 Undefined header`).

## ARB workflow

No ARB upload was exercised in the 2026-11-26 verification. Steps 4-7 below
remain `documented`; binary byte order is `UNVERIFIED`.

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
python3 scripts/afg2225_protocol.py identity assets/captures/idn.txt
python3 scripts/afg2225_protocol.py numeric assets/captures/freq.txt --quantity frequency --unit Hz
python3 scripts/afg2225_protocol.py error-queue assets/captures/error-empty.txt
python3 scripts/afg2225_protocol.py arb --csv assets/fixtures/arb-valid.csv --format ascii
```

Stages: `read_frame` -> `parse_metadata` -> `extract_payload` -> `normalize` ->
`validate`; the high-level `parse_identity`, `parse_numeric`, and
`parse_error_queue` are thin compositions of those stages. `parse_error_queue`
uses `read_error_queue_frame`, which accepts both the manual's single-line form
and the observed two-line code/message form. ARB stages:
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

- `COMPLETE`: every applicable **structural and count** check passes for the stated claim (framing, required fields, point/row counts, terminator); it never means the data is correct, covers what the caller wanted, or is within calibration.
- `INCOMPLETE`: a required byte, terminator, field, point, segment, or status element is missing.
- `INVALID`: framing, counts, or type constraints contradict the observed bytes.
- `UNVERIFIED`: parsing found no contradiction, but the available evidence cannot prove completeness, units, calibration, or acquisition state.
- `UNSUPPORTED`: this Skill does not implement that response shape or feature.

A structural status never stands in for a different claim: **bytes complete**,
**scale usable**, **same frame**, and **the number is a physical level** are four
separate conclusions. Where an artifact reports one of them, it names it.

Never silently pad, truncate, clamp, interpolate, or guess. A parsed value is
not proof of hardware acceptance or calibrated output.

## Verification commands

```bash
python3 -m unittest discover -s skills/gwinstek-afg2225-control/scripts -p 'test_*.py'
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/gwinstek-afg2225-control
npx skills@latest add . --list
```

## Known limitations / manual defects

- Hardware evidence covers one unit (serial `GEP902745`, firmware `V2.05`, USB
  CDC-ACM) on 2026-11-26; every other unit and firmware needs its own capture.
- The error queue is two lines on the wire (`-102\r\nSyntax error.`), not the
  manual's single-line `-138 Suffix not allowed`; the message line has no
  terminator. Empty queue is `\r\nNo error.`.
- `SOUR<n>:APPL?` returns a quoted composite string on the wire
  (`"SIN +5.0000000000000E-01,+3.000E+00,+0.00E+00"`); the manual example omits
  the quotes.
- `SOUR<n>:AMPL?` / `AMPL? MAX` / `AMPL? MIN` do not answer on V2.05 and queue
  `-113 Undefined header`; use the long form `SOUR<n>:AMPLITUDE?`.
- No SCPI beeper command exists in the manual or firmware; use the panel
  UTIL -> F3 System -> F3 Beep -> F2 OFF.
- USB CDC only; no LAN/GPIB/RS-232.
- Binary ARB byte order unverified (ASCII default).
- Manual example `DATA:DAC VOLATILE, #216 Binary Data` claims 5 values /
  16 bytes, but 5 × 2 = 10 bytes (documented defect).
- `115200 8N1` is the helper default, not a manual requirement; the verified
  link also answered at 9600 baud.
- No automatic reset/save/delete/calibration.
- Community observations (unverified): `SOURCE1:OUTPUT ON` vs `OUTP1 ON`;
  positive DC offset with ARB can invert signal.
- Linux device ID `0x2184:0x001c` is external evidence, not manual text.