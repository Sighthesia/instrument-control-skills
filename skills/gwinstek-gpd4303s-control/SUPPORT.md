# Parser Support Record

- Parser status: `documented` overall; response parsing is `hardware-verified`
- Hardware verification: `true` for read-only responses only
- Verified model/firmware/interface: GW Instek GPD-4303S, serial `EP924162`,
  firmware `V2.08`, `/dev/ttyUSB0` at 9600 8N1, captured 2026-11-19
- Retested after capture: no. The instrument was disconnected from the host
  after the capture session, so every fixture is a single non-repeatable capture.
- Manual source: *GPD-X303S Series User Manual*, GW Instek part no.
  `82PD-433S0MC1`, REMOTE CONTROL chapter, PDF pp. 43-52; local copy
  `ref/gwinstek/GPD-X303S_User_Manual_82PD-433S0MC1.pdf`
- Supported data kinds: `identity`, `scalar-value` (setpoints and read-back),
  `status-record` (`STATUS?`), `command-list` (`HELP?`), `error-message`

## What was verified

| Claim | Level | Evidence |
|---|---|---|
| `*IDN?` framing and field order `GW INSTEK,<model>,SN:<serial>,V<m>.<n>` | `hardware-verified` | `assets/fixtures/idn.txt` (real response, `V2.08`) |
| `VSET<X>?` / `ISET<X>?` respond `24.000V` / `1.000A` style NR2 plus a V or A unit | `hardware-verified` on CH1/CH2; `documented` on CH3/CH4 | `assets/fixtures/vset1.txt`, `vset2.txt`, `iset1.txt`, `iset2.txt` (CH1/CH2). `vset3/vset4/iset3/iset4.txt` are transcript-only: no raw bytes preserved |
| `VOUT<X>?` / `IOUT<X>?` respond with the same numeric-plus-unit format | `hardware-verified` on CH1/CH2; `documented` on CH3/CH4 | `assets/fixtures/captures/002-VOUT1.raw`, `003-IOUT1.raw`, `004-VOUT2.raw`, `005-IOUT2.raw` (plus `vout1-on.txt`, `iout1-on.txt` from the prior session). `vout3/vout4/iout3/iout4` are transcript-only |
| `STATUS?` returns eight binary characters | `hardware-verified` | `assets/fixtures/status-output-off.txt` and two prior captures |
| `STATUS?` bit meanings | `documented` | manual p. 50 |
| `STATUS?` character transmission order | `UNVERIFIED` | not in the manual; decode reports both orders |
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
- No CH3/CH4 channel-scoped claim: those queries answered during the session but
  their response bytes were not preserved, so they stay `documented`. Channel
  numbering itself is documented by manual pp. 48-49 and by the `HELP?` hint
  `x:1=CH1,2=CH2 (4303:3=CH3,4=CH4)`.

Do not upgrade this record to full `hardware-verified` control without
preserving real responses for the write commands, including the exact
`OUT1`/`OUT0` sequence, the load, and the measured result.
