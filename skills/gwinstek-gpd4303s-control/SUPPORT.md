# Parser Support Record

- Parser status: `documented` overall; response parsing is `hardware-verified`
- Hardware verification: `true` for read-only responses only
- Verified model/firmware/interface: GW Instek GPD-4303S, serial `EP924162`,
  firmware `V2.08`, `/dev/ttyUSB0` at 9600 8N1, captured 2026-11-19
- Retested after capture: yes. A second read-only session on 2026-11-19
  (`verify_all`, 11:38:50Z) re-queried the same unit; its evidence is archived
  locally under `artifacts/verification/evidence/20261119T113850Z/`
  (git-ignored, local reference only).
- Manual source: *GPD-X303S Series User Manual*, GW Instek part no.
  `82PD-433S0MC1`, REMOTE CONTROL chapter, PDF pp. 43-52; local copy
  `ref/gwinstek/GPD-X303S_User_Manual_82PD-433S0MC1.pdf`
- Supported data kinds: `identity`, `scalar-value` (setpoints and read-back),
  `status-record` (`STATUS?`), `command-list` (`HELP?`), `error-message`

## What was verified

| Claim | Level | Evidence |
|---|---|---|
| `*IDN?` framing and field order `GW INSTEK,<model>,SN:<serial>,V<m>.<n>` | `hardware-verified` | `assets/fixtures/idn.txt` (real response, `V2.08`) |
| `VSET<X>?` / `ISET<X>?` respond `24.000V` / `1.000A` style NR2 plus a V or A unit | `hardware-verified` on CH1-CH4 | `assets/fixtures/captures/006-VSET3.raw`-`009-ISET4.raw` (CH3/CH4); `vset1.txt`, `vset2.txt`, `iset1.txt`, `iset2.txt` record the CH1/CH2 responses from the same 2026-11-19 session |
| `VOUT<X>?` / `IOUT<X>?` respond with the same numeric-plus-unit format | `hardware-verified` on CH1-CH4 | `assets/fixtures/captures/002-VOUT1.raw`, `003-IOUT1.raw`, `004-VOUT2.raw`, `005-IOUT2.raw`, `010-VOUT3.raw`-`013-IOUT4.raw` (plus `vout1-on.txt`, `iout1-on.txt` from the prior session) |
| `STATUS?` returns eight binary characters | `hardware-verified` | `assets/fixtures/status-output-off.txt` and two prior captures |
| `STATUS?` bit meanings | `documented` | manual p. 50 |
| `STATUS?` character transmission order | `hardware-verified` for this unit; the order itself is not in the manual | decode reports both orders. The `lsb-first` default agrees with four independent observations of `00110010`: `baud_9600_matches_link`, `output_off_matches_vout_zero`, `beep_off_matches_beep0`, and `panel_ser_indep_led_on_matches_series_decode`. The panel confirmation is the operator's 2026-11-19 visual check that the `SER/INDEP` LED was on (series tracking). The artifact stays `UNVERIFIED` because the manual never states the order |
| `STATUS?` tracking decode matches the front panel (`SER/INDEP` LED on = series, 0-60 V) | `hardware-verified` (panel observation, this unit) | operator visual check of the front panel on 2026-11-19, recorded as `panel_ser_indep_led_on_matches_series_decode` |
| `HELP?` returns an 18-line CR-separated list ending in CR LF | `hardware-verified` (transcript-reconstructed raw) | `assets/fixtures/captures/help-transcribed.raw` (SHA-256 `cc99fc5c…`, indexed in `captures.jsonl` with `capture_method: console-transcript`) |
| `Invalid Character.` is the reply to an unknown command | `hardware-verified` | `assets/fixtures/invalid-character.txt` |
| `OUT<Boolean>`, `VSET/ISET` writes, `TRACK`, `SAV`/`RCL`, `BAUD`, `LOCAL`, `REMOTE` | `documented` | manual pp. 46-52; never sent |
| The other five error messages | `documented` | manual pp. 46-47; never observed |

## What is deliberately not claimed

- No output, setpoint, tracking, memory, baud, or remote/local command was sent,
  so no side effect of those commands is verified on this firmware.
- No calibration: read-back is ±(0.03 % of reading + 10 mV) /
  ±(0.3 % of reading + 10 mA) with 1 mV / 1 mA meter resolution (manual
  pp. 55-56).
- No panel confirmation beyond this unit and date: on 2026-11-19 the operator
  saw the `SER/INDEP` LED on for GPD-4303S `EP924162` (series tracking, 0-60 V),
  matching the `lsb-first` decode `tracking_code=11`. On another unit, or after
  anyone changes the mode, do not assume CH1 and CH2 are independent — check the
  panel. In series tracking the two channels form one 0-60 V / 0-3 A supply
  (manual pp. 33-34) with the load across CH1+ and CH2-.

Do not upgrade this record to full `hardware-verified` control without
preserving real responses for the write commands, including the exact
`OUT1`/`OUT0` sequence, the load, and the measured result.
