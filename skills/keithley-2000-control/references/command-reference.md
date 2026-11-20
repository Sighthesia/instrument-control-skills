# Command Reference (Fallback Index)

This is a fallback index of every SCPI/IEEE-488.2 command already recorded
inside this Skill (`SKILL.md`, `references/*.md`, `scripts/*.py`). Read the
task-specific reference or script first; open this file only when neither
answers the question. The scope is exactly what this Skill records — the
authoritative complete command set is the *Model 2000 Multimeter User's Manual*,
`2000-900-01 Rev. J / August 2010`, which is not copied here. Any command,
parameter, range, or page absent from the tables must be verified against the
manual and labelled `documented` before use. Every row is `documented` unless
stated otherwise; DC voltage and DC current over RS-232 are additionally
`hardware-verified` / `firmware-scoped` on serial `0944865`, firmware `A17`/`A02`.
The safety rules in `SKILL.md` still apply unchanged: `INPUT HI`/`INPUT LO` for
non-current functions, front `AMPS` + `INPUT LO` for current, `1000 V peak`
differential, `500 V peak` common-mode, `3 A, 250 V` fuse, no `*OPC?` during
`:INITiate:CONTinuous ON`, and no routine `*RST`.

**Source column convention:** `file` = the document that records the command;
`p.<n>` = the PDF physical page already cited in that document. Where a
reference deliberately records a command's existence without a manual page, the
page cell is left out rather than guessed. `scripts/…` marks a command whose only
recorded source is a bundled script (the session helper or its tests), not a
reference document; those commands were not necessarily exercised on hardware.

Function placeholders in the command column (`<function>`) expand to the
recorded tokens in the sense-section table; they are not free-form wildcards.
Non-code rows (e.g. "Buffer clear") are capabilities the Skill names without a
command spelling; they are listed so their absence is visible, not to be sent.

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | Returns vendor, model, serial, digital/display firmware; does not prove SCPI is selected (SKILL.md p.81-84). `"A17  /A02  "` observed as trailing firmware pair. | SKILL.md p.81-84<br>scpi-remote-workflow.md<br>hardware-verification.md |
| `*OPT?` | query | — | Option-card evidence; `0,0` = no scanner option reported. Gate scans on this result. | SKILL.md<br>hardware-verification.md |
| `*OPC?` | query | — | Only mentioned as a lock hazard. Do not use while `:INITiate:CONTinuous ON` is active (can lock the instrument). No sequencing was hardware-verified. | SKILL.md p.125, 136, 201<br>conditional-acquisition.md<br>hardware-verification.md |
| `*CLS` | event | — | Clears event/status registers **and** the error queue; send only when authorized. Never as routine cleanup. | SKILL.md p.98-107<br>scpi-remote-workflow.md p.117<br>scripts/keithley2000_session.py (refused without `--allow-state-change`) |
| `*RST` | event | — | Resets measurement state but **not** the error queue; differs from `:SYSTem:PRESet`. Do not send merely as cleanup; may cancel a pending operation-complete query. | SKILL.md<br>scpi-remote-workflow.md<br>scripts/keithley2000_session.py (refused without `--allow-state-change`) |
| `*TRG` | event | — | Recorded only as a guarded state-changing write in the session helper; no reference document describes it. Not exercised. | scripts/keithley2000_session.py |

## System, status, and calibration metadata

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SYSTem:ERRor?` | query | — | FIFO of up to 10 entries, `code,message`. Drain until `0,No error`; verified unit quotes it as `0,"No error"`. Positive codes are Keithley-defined, negative SCPI. `±350, Queue Overflow` means earlier messages may be lost. | SKILL.md p.190, 194, 209<br>scpi-remote-workflow.md<br>response-and-evidence.md<br>hardware-verification.md |
| `:STATus:QUEue:NEXT?` | query | — | Alternative error-queue readout; referenced in the session workflow only, no manual page cited. | SKILL.md |
| `:SYSTem:VERSion?` | query | — | SCPI standard revision; verified unit returned `1991.0`. | SKILL.md<br>hardware-verification.md |
| `:SYSTem:FRSWitch?` | query | — | `1` = front inputs, `0` = rear (p.193). Reports the switch position, not which terminals the wiring used. | SKILL.md p.193<br>basic-measurements.md p.193<br>hardware-verification.md |
| `:SYSTem:LFRequency?` | query | — | Line frequency in Hz; verified unit returned `50`. Affects NPLC timing interpretation. | SKILL.md<br>hardware-verification.md |
| `:SYSTem:POSetup?` | query | — | Saved power-on setup name; verified unit returned `SAV0`. | SKILL.md<br>hardware-verification.md |
| `:SYSTem:PRESet` | event | — | Reset to power-on defaults; differs from `*RST`, can invalidate trigger/function state. Refused by the helper without `--allow-state-change`. | SKILL.md<br>scpi-remote-workflow.md<br>scripts/keithley2000_session.py |
| `:SYST:PRES` | event | — | Short form matched by the helper's refusal guard; no separate reference description. | scripts/keithley2000_session.py |
| `:SYSTem:AZERo:STATe` | set/query | `ON` / `OFF` (query returns `1`/`0`) | Autozero control. Enter idle first (`:INITiate:CONTinuous OFF`, then `:ABORt`), record prior state, restore afterwards. Verified unit: `1`; autozero on raised 10 PLC time from 239 ms to 649 ms. | SKILL.md<br>hardware-verification.md |
| `:SYSTem:AZERo:STATe?` | query | — | Read prior autozero state before any change; `1` = on. | SKILL.md<br>hardware-verification.md |
| `:SYST:AZER` | set | — | Short form matched by the helper's refusal guard; no separate reference description. | scripts/keithley2000_session.py |
| `:CAL:PROT:COUN?` | query | — | Calibration count; verified unit returned `6`. Metadata only. | SKILL.md<br>hardware-verification.md |
| `:CAL:PROT:DATE?` | query | — | Last calibration date as `YYYY,MM,DD`; verified `2008,06,20`. | SKILL.md<br>hardware-verification.md |
| `:CAL:PROT:NDUE?` | query | — | Next calibration due date as `YYYY,MM,DD`; verified `2009,06,20` (overdue). Not accuracy evidence. | SKILL.md<br>hardware-verification.md |
| `:CAL:PROT:LOCK?` | query | — | `0` locked, `1` unlocked; verified unit `0`. A calibration write needs an explicit unlock procedure. | SKILL.md<br>hardware-verification.md |
| `:CALibration` | set | — | Every other calibration command is protected; do not send without the calibration manual and operator approval. Helper refuses it without `--allow-state-change`. | SKILL.md<br>scripts/keithley2000_session.py |
| `:CAL:PROT` | set | — | Protected calibration family; same restriction as above. | SKILL.md<br>scripts/keithley2000_session.py |
| `:CAL:PROT:CODE 'KI002000'` | set | `<code>` (string; the recorded example is the factory default unlock code) | Unlock example that the helper refuses without `--allow-state-change`. Not exercised on hardware. | scripts/test_keithley2000_session.py |

## Sense function selection and configuration

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SENSe:FUNCtion` | set | Function token: `VOLTage[:DC]`, `VOLTage:AC`, `CURRent[:DC]`, `CURRent:AC`, `RESistance`, `FRESistance`, `FREQuency`, `PERiod`, `TEMPerature`, `CONTinuity`, `DIODe` | Manual's function names (p.168). Selects a function without resetting that function's other settings, unlike `:CONFigure`. `CURRent` changes the input path to AMPS. | basic-measurements.md p.29-46, 168<br>SKILL.md<br>hardware-verification.md |
| `:FUNCtion` | set | same tokens, quoted (e.g. `"VOLT:DC"`) | Helper writes `:FUNCtion "<token>"` for `config`. | scripts/keithley2000_session.py<br>scripts/test_keithley2000_session.py |
| `:FUNCtion?` | query | — | Returns the active function as a quoted token, e.g. `"VOLT:DC"`. Required because `:SENSe:DATA?` carries no function name. | SKILL.md p.169<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:RANGe[:UPPer]` | set | per-function range limit; verified: `10` on DCV, `3` on DCI (read back `3.1000` top-range full scale) | Applies to voltage, current, resistance and 4-wire resistance only. A fixed range disables autorange. Do not generalize to frequency/period/continuity/diode. | measurement-configuration.md p.50<br>hardware-verification.md |
| `:SENSe:<function>:RANGe?` | query | — | Verified: `100.000000` (DCV autorange resolved), `1010.000000` (DCV full scale), `3.1000`, `1.0000` (DCI), `757.500000` (ACV), `120000000.0` (2-wire), `120000000.000` (4-wire). | hardware-verification.md<br>basic-measurements.md |
| `:SENSe:<function>:RANGe:AUTO` | set | `ON` / `OFF` | Enables/disables autorange; ranges up at 120 % and down at 10 % of nominal (p.50). Avoid when optimum speed is required. | measurement-configuration.md p.50<br>hardware-verification.md |
| `:SENSe:<function>:RANGe:AUTO?` | query | — | Returns `1`/`0`; verified `1` on the open-input walk for every ranged function. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:FREQuency:THReshold:VOLTage:RANGe` | set/query | threshold voltage range; verified readback `10.000000` | Frequency range control. `:SENSe:FREQuency:RANGe` is **not** a Model 2000 command and produces no response (timeout, desynchronised session). | basic-measurements.md p.37-38<br>SKILL.md<br>hardware-verification.md |
| `:SENSe:PERiod:THReshold:VOLTage:RANGe` | set/query | threshold voltage range; verified readback `10.000000` | Period range control; same non-response hazard as above if the voltage/current/resistance syntax is used instead. | basic-measurements.md p.37-38<br>hardware-verification.md |
| `:SENSe:CONTinuity:THReshold` | set | `1 Ω` to `1000 Ω`; default `10 Ω` | Continuity occurs at or below the threshold. Single range. | basic-measurements.md p.45, 182-183<br>measurement-configuration.md |
| `:SENSe:CONTinuity:THReshold?` | query | — | Verified `1.0000000E+01`; helper `config` uses it as the continuity "range". | assets/captures/open-inputs/*.json (verified capture)<br>scripts/keithley2000_session.py |
| `:SENSe:DIODe:CURRent:RANGe[:UPPer]` | set | `0` to `1e-3` (expected diode current; instrument picks the matching range) | Selectable test currents `10 µA`, `100 µA`, `1 mA`. Setting `1e-4` read back `0.00010`. | basic-measurements.md p.46, 182<br>hardware-verification.md |
| `:SENSe:DIODe:CURRent:RANGe?` | query | — | Verified `0.00100` (1 mA default). | basic-measurements.md p.182<br>hardware-verification.md |
| `:SENSe:DIODe:BIAS:VOLTage:RANGe?` | query | — | **Not a Model 2000 command**: verified firmware rejects it with `-113,"Undefined header"`. Listed so it is not retried. | basic-measurements.md |
| `:SENSe:<function>:DIGits` | set | `4` to `7` | Display resolution only; remote string stays at 9 significant digits. Not supported for continuity/diode. | measurement-configuration.md p.52<br>hardware-verification.md |
| `:SENSe:<function>:DIGits?` | query | — | Verified 4-7 read back exactly. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:DIGits?` | query | — | Short form documented in the hardware record for the digits sweep. | hardware-verification.md |
| `:SENSe:<function>:NPLCycles` | set | `0.01` to `10` (helper-enforced); excludes frequency/period/continuity/diode | Integration time. At 50 Hz, 1 PLC ≈ 20 ms; measured 40/41/60/239 ms per `:READ?` at 0.01/0.1/1/10 PLC (10 V range, autozero off). | measurement-configuration.md p.53, 171<br>hardware-verification.md |
| `:SENSe:<function>:NPLCycles?` | query | — | Verified readbacks `0.01`, `0.10`, `1.00`, `10.00`. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:CURRent:DC:NPLC` | set | `1` (verified write) | Abbreviated form used in the verified DCI sequence and read back with `:NPLCycles?`. | hardware-verification.md |
| `:SENSe:VOLTage:DC:NPLC?` | query | — | Short form observed in the verified capture alongside `:NPLCycles?`. | assets/captures/*.json (verified capture) |
| `:SENSe:<function>:AVERage:STATe` | set | `ON` / `OFF` | Digital averaging filter on/off. Not supported for frequency, period, continuity, diode. The manual prose records only "averaging filter", so the command spelling itself comes from the helper, not a cited manual page. | measurement-configuration.md p.51, 177-178 (prose only)<br>scripts/keithley2000_session.py<br>assets/captures/rate-filter-rel-digits/session-characteristics.json |
| `:SENSe:<function>:AVERage:STATe?` | query | — | Verified state readback; helper reports `enabled` from it. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:AVERage:TCONtrol` | set | `MOVing` / `REPeat` | Filter mode; verified both accepted. Helper also accepts `moving`/`repeat` spelling. Spelling source is the helper; the manual cites only the filter behaviour. | measurement-configuration.md p.51, 177-178 (prose only)<br>scripts/keithley2000_session.py<br>assets/captures/rate-filter-rel-digits/session-characteristics.json |
| `:SENSe:<function>:AVERage:TCONtrol?` | query | — | Verified readback used to report `moving`/`repeat`. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:AVERage:COUNt` | set | conversion count; helper enforces `1` to `100`, verified `5` and `10` | Record state, type, and count together; filter effect is not a calibrated noise spec. | measurement-configuration.md p.51<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:AVERage:COUNt?` | query | — | Verified readback of the conversion count. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:REFerence` | set | helper limits: DCV ±1010, ACV ±757.5, DCI/ACI ±3.1, RES/FRES 0 to 120e6, FREQ 0 to 1.5e7, PER 0 to 1, TEMP −200 to 1372 (units of the active function) | REL reference value. Verified `0.05` on DCI made an open input read exactly `-0.050000 A`. Do not use REL to zero ACV offset. | measurement-configuration.md p.32, 52<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:REFerence 0.05` | set | `0.05` (verified write) | Abbreviated write recorded in the rate/REL sweep. | hardware-verification.md |
| `:SENSe:<function>:REFerence?` | query | — | Verified `0.0000000E+00` (off) and the captured reference value. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:REFerence:STATe` | set | `ON` / `OFF` | Enables/disables REL. `ACQuire` requires REL off first, then re-enable as intended. | measurement-configuration.md p.52<br>hardware-verification.md |
| `:SENSe:<function>:REFerence:STATe?` | query | — | Verified `0`/`1` state readback. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:REFerence:STATe OFF` | set | `OFF` (verified write) | Abbreviated form recorded next to the REL sweep. | hardware-verification.md |
| `:SENSe:<function>:REFerence:ACQuire` | event | — | Captures the latest reading as the new REL reference. Verified it captured the raw input, not the relative result. Cannot be combined with an explicit reference in the helper. | measurement-configuration.md p.52<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:REFerence:ACQuire` | event | — | Abbreviated form recorded in the hardware table. | hardware-verification.md |
| `:SENSe:TEMPerature:TCouple:TYPE` | set | `J`, `K`, or `T` | Thermocouple type; verified default readback `J`. The manual prose gives only the `J`/`K`/`T` values, so the command spelling comes from the helper and the capture. | basic-measurements.md p.40, 180-181 (values only)<br>scripts/keithley2000_session.py<br>assets/captures/open-inputs/session-open-inputs.json |
| `:SENSe:TEMPerature:TCouple:TYPE?` | query | — | Verified `J` on the open-input walk. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:TYPE` | set | — | Abbreviated thermocouple-type form cited in the configuration snapshot guidance; no separate argument list recorded. | measurement-configuration.md |
| `:SENSe:TEMPerature:UNIT` | set | — | Name used only as the reason temperature needs an explicit unit; prefer `:UNIT:TEMPerature` (below). | scripts/keithley2000_protocol.py |
| `:SENSe:TEMPerature:UNIT?` | query | — | **Not sent**: the test asserts this is never emitted; use `:UNIT:TEMPerature?`. | scripts/test_keithley2000_session.py |
| `:UNIT:TEMPerature` | set | temperature unit (`C`, `F`, `K` accepted on readback) | Record the temperature unit with each reading. | measurement-configuration.md p.180-182, 205 |
| `:UNIT:TEMPerature?` | query | — | Helper reads it back after a temperature configure; determines the unit attached to the reading. | scripts/keithley2000_session.py |
| `:SYSTem:PRESet` defaults via `:CONFigure` | event | — | Reference only: `:CONFigure:<function>` returns that function's parameters to `*RST` values. | scpi-remote-workflow.md p.134-135 |

## Read, fetch, measure, and data

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CONFigure:<function>` | event | any recorded function token (e.g. `:CONFigure:VOLT:DC`, `:CONFigure:CURRent:DC`, `:CONFigure:FREQ`) | Expands to nothing measurement-related but resets that function's parameters to `*RST` values and disables continuous initiation, math, buffer, and scanning (p.134-135). Leaves continuous initiation **off**, so a following `:READ?` is clean. | scpi-remote-workflow.md p.134-135<br>SKILL.md<br>hardware-verification.md |
| `:CONFigure:VOLT:DC` | event | — | Abbreviated form used by the verified DCV sequence and the helper. | hardware-verification.md<br>scripts/test_keithley2000_session.py |
| `:READ?` | event | — | Expands to `:ABORt; :INITiate; :FETCh?`; waits for the trigger, returns readings, stores them in the buffer. With continuous initiation ON the `:INITiate` queues `-213,"Init ignored"` while `:FETCh?` still returns a free-running value. Sample count >1 with readings already buffered returns `-225`. Responses end with CR on the verified unit. | SKILL.md p.121-122, 125, 136<br>scpi-remote-workflow.md p.136<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:FETCh?` | event | — | Returns the latest post-processed reading without triggering; may repeat a stale value and can miss rapid external triggers. Does not block unless an armed trigger has a pending fetch — then it blocks the queue for every later query. | SKILL.md p.135<br>scpi-remote-workflow.md p.135<br>hardware-verification.md |
| `:MEASure:<function>?` | event | any recorded function token, e.g. `:MEASure:VOLTage:DC?` | Expands to `:ABORt; :CONFigure:<function>; :READ?`; resets math, buffer, scan, and continuous-trigger context (p.137). | scpi-remote-workflow.md p.137<br>SKILL.md<br>hardware-verification.md |
| `:SENSe:DATA?` | query | — | Latest raw or REL-adjusted reading in exponent form; no function name, no math result; always ASCII. Pair with `:FUNCtion?`. | SKILL.md p.169<br>scpi-remote-workflow.md p.169<br>response-and-evidence.md |
| `:DATA:FRESh?` | query | — | Mentioned only as a cross-reference on p.135; the command description is missing from the supplied PDF. Do not rely on it without matching firmware documentation or hardware verification. | SKILL.md p.135<br>scpi-remote-workflow.md p.135 |
| `:FORMat:DATA` | set | `ASCii`, `SREal`, `DREal` | Controls buffer transfer format; binary uses a `#0` header and normal/swapped byte order. RS-232 is ASCII only (`+808 ASCII only with RS-232`, p.212). | scpi-remote-workflow.md p.159-161, 212 |
| `:FORMat:DATA ASCII` | set | `ASCII` (documented default format statement) | The shape the bundled scalar parser accepts. | SKILL.md |
| `:FORMat:ELEMents` | set | element list, e.g. `READ`, `READ,CHAN,UNIT` | Select the elements returned with a reading. Factory default on the verified unit is `READ,,` (bare number, no unit). | SKILL.md<br>hardware-verification.md |
| `:FORMat:ELEMents?` | query | — | Verified `READ,,`; helper/tests parse the comma-split list. | hardware-verification.md<br>scripts/test_keithley2000_protocol.py |
| `:CALCulate:DATA?` | query | — | Always ASCII; use it to read math results, which `:SENSe:DATA?` never returns. | scpi-remote-workflow.md p.169<br>measurement-configuration.md p.169 |

## Trigger and initiation

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:INITiate` | event | — | Arms one acquisition. Ignored with `-213,"Init ignored"` when the instrument is not idle (e.g. after a `BUS`/`EXTernal` arm, or with continuous initiation on). | conditional-acquisition.md p.201-204<br>SKILL.md<br>hardware-verification.md |
| `:INITiate:CONTinuous` | set/query | `ON` / `OFF` (query returns `1`/`0`) | Verified unit arrived free-running (`1`). Must be `OFF` before a `:READ?` can be trusted as newly triggered. Refused by the helper without `--allow-state-change`. Never combine `ON` with `*OPC?`. | SKILL.md p.125, 201<br>hardware-verification.md<br>scripts/keithley2000_session.py |
| `:INITiate:CONTinuous?` | query | — | Check before interpreting any `:READ?`; `1` means the value is a continuous result, not newly triggered. | SKILL.md<br>hardware-verification.md |
| `:INIT:CONT` | set | — | Short form matched by the helper's refusal guard; no separate reference description. | scripts/keithley2000_session.py |
| `:ABORt` | event | — | Terminates the trigger model. Recorded as the first element of `:READ?`. Alone it did **not** clear a blocked output queue left by an armed trigger; use a device clear instead. | SKILL.md<br>conditional-acquisition.md<br>hardware-verification.md |
| `:TRIGger:SOURce` | set/query | `IMMediate`, `TIMer`, `MANual`, `BUS`, `EXTernal` | Configure and query deliberately. Restore `IMMediate` after any timeout recovery. | conditional-acquisition.md p.201-204<br>hardware-verification.md |
| `:TRIGger:SOURce IMM` | set | `IMM` (abbreviated, verified write) | Abbreviated form observed in the verified session and recovery procedure. | hardware-verification.md |
| `:TRIGger:SOURce?` | query | — | Verified `IMM` in the saved capture. | hardware-verification.md |
| `:TRIGger:COUNt` | set/query | `1` to `9999` or `INF` | Number of trigger events; `INF` is continuous scanning-style operation. | conditional-acquisition.md p.201-204 |
| `:TRIGger:DELay` | set/query | `0` to `999999.999 s` | Delay between trigger detection and device action. | conditional-acquisition.md p.201-204 |
| `:TRIGger:TIMer` | set/query | `0.001` to `999999.999 s` | Timer interval when `:TRIGger:SOURce` is `TIMer`. | conditional-acquisition.md p.201-204 |
| `:SAMPle:COUNt` | set/query | `1` to `1024` | Readings per trigger. Must be `1` when continuous initiation is on; `:READ?` with count >1 and existing buffer readings returns `-225`. | conditional-acquisition.md p.201-204<br>SKILL.md |

## Trigger link, hold, and buffer

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| Trigger link VMC output | — | minimum pulse width `10 µs` | **No command recorded.** Described physically (PDF 58-59) without a SCPI form in this Skill; verify Trigger Link wiring and line assignment before connecting instruments. | conditional-acquisition.md p.58-59 |
| `EXT TRIG` input | — | TTL-compatible, falling edge, minimum pulse width `2 µs` | **No command recorded.** Physical input used with `:TRIGger:SOURce EXTernal`; an armed trigger with a pending fetch blocks the output queue. | conditional-acquisition.md p.58-59<br>SKILL.md |
| Reading hold / autosettle | set/query | window `0.01` to `20` percent; consecutive count `2` to `100` | Command name not recorded; only its parameters (PDF 57-58, 170). It changes when a reading is considered settled — record window/count/state. | conditional-acquisition.md p.57-58, 170 |
| `:TRACe` / `:DATA` buffer storage | set/query | capacity `2` to `1024` readings; source `SENSe[1]`, `CALCulate[1]`, `NONE`; control `NEVer`, `NEXT` | Family recorded without per-command suffixes. `:READ?` stores its readings here. Buffer is not persistent across power loss; record source, control, expected and observed counts. | conditional-acquisition.md p.64-66, 199-200<br>SKILL.md p.136 |
| Buffer clear | event | — | Recorded as a capability only; no command spelling or page. Do not invent the suffix. | conditional-acquisition.md p.64-66 |
| Buffer free-space query | query | — | Recorded as a capability only; no command spelling or page. | conditional-acquisition.md p.64-66 |
| Buffer data query | query | — | The buffer dump is not decoded by the bundled parser; report `UNSUPPORTED` until framing and field order are implemented. | conditional-acquisition.md p.64-66<br>scpi-remote-workflow.md p.159-162 |
| Buffer half-full / full status | query | — | Recorded as a status inspection without a command spelling; never pad a sequence to make it look complete. | conditional-acquisition.md p.64-66 |

## Math, limits, and statistics

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CALCulate` | set/query | `MX+B`, percent, dB/dBm, buffer statistics, limit testing | Family recorded generically; math applies after acquisition, while `:SENSe:DATA?` returns no math result. | measurement-configuration.md p.41-45, 151-156 |
| `:CALCulate[1]` | set/query | — | Optional channel form used for buffer statistics and limits (p.153-156). | conditional-acquisition.md p.153-156<br>measurement-configuration.md p.151-156 |
| `:CALCulate:STATe?` | query | — | Verified `0` before and after the DCV sweep when math was off. | assets/captures/*.json (verified capture) |
| `:CALCulate1:STATe` | set | `ON` / `OFF` | Example state write the helper allows (not a forbidden prefix). | scripts/test_keithley2000_session.py |
| `:CALCulate3` limit testing | set/query | upper/lower limits; not supported for continuity | Applied after MX+B/percent math. Record thresholds, math order, enable state, fail/result query, and limit event status. Do not infer which bound failed from one boolean. | conditional-acquisition.md p.67-68, 155-156<br>SKILL.md |
| Buffer statistics queries | query | mean, standard deviation, maximum, minimum | Derived results: preserve contributing readings or declare they were not independently captured. | conditional-acquisition.md p.153-154 |

## Scanner and route

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `ROUTe` | set/query | — | Family name only; gate every scan on `*OPT?` and confirmed card/switch topology. | SKILL.md<br>conditional-acquisition.md p.69-78, 163-167 |
| `:SCAN` | set/query | internal lists `2` to `10` consecutive channels; external lists `2` to `800` channels | Skipping an internal channel is not allowed; external scans need a configured switch system and trigger link. | conditional-acquisition.md p.69-78, 163-167 |
| `:ROUTe:CLOSe` | set | single channel | Do not issue while a scan is active. | conditional-acquisition.md p.69-78 |

## Coverage gaps

- **Fuse condition is not queryable.** No command in this Skill reports AMPS fuse
  continuity; identity, options, and configuration do not imply a good fuse. Mark
  it `UNVERIFIED` without a suitable test.
- **Interface and language switching are front-panel only.** No remote command
  here selects GPIB vs RS-232 or SCPI vs another language, and `*IDN?` does not
  prove SCPI is active. Confirm with the operator or setup record.
- **Scanner availability is unproven.** `*OPT?` returned `0,0` on the verified
  unit; every `:ROUTe`/`:SCAN` row is `documented` only and depends on a card or
  external switch that was never exercised.
- **Trigger, buffer, limit, and scan rows are name-only.** `:TRIGger:*`,
  `:SAMPle:COUNt`, `:TRACe`/`:DATA`, `:CALCulate3`, and `:SCAN` are recorded by
  family and argument limits, not by complete per-command syntax; no page-level
  command description was copied.
- **Recorded-but-undescribed commands.** `:STATus:QUEue:NEXT?`, the Trigger Link
  VMC output, `:DATA:FRESh?`, and the short forms matched only by the helper's
  guard (`:SYST:PRES`, `:SYST:AZER`, `:INIT:CONT`, `*TRG`) lack a verified
  parameter list or were never exercised on hardware.
- **Negative results recorded deliberately.** `:SENSe:FREQuency:RANGe?` and
  `:SENSe:DIODe:BIAS:VOLTage:RANGe?` are **not** Model 2000 commands (no response
  / `-113,"Undefined header"`); `:SENSe:TEMPerature:UNIT?` is not emitted by the
  helper. Do not retry them.
- **Unverified option and sequencing.** `*OPC?` sequencing, `*TRG`, GPIB transfers,
  sample count >1, and binary `SREal`/`DREal` framing remain unverified on real
  hardware; the scalar parser does not decode them.
- **The complete Model 2000 command set far exceeds this table.** Status-register
  trees, full `:CALCulate` sub-trees, format byte-order commands, and other
  documented subsystems are not indexed here; consult the manual
  (`2000-900-01 Rev. J / August 2010`) and label anything found there `documented`.
- **No full command enumeration existed before this file.** This index was
  assembled from `SKILL.md`, the six reference documents, and the bundled scripts;
  it is not a substitute for the manual's command tables.

## Appendix: commands from the manual's command chapter (table derived)

This appendix lists the commands the *Model 2000 User's Manual* (2000-900 J)
documents, so the index misses none of them. Command spelling and the PDF page
come from the manual's command chapter; the parameter and note columns are
transcribed from the cited per-command page (PDF pp. 139-207), because the
summary tables drift their indentation across page breaks and misparent
`[:SENSe[1]]` subtrees. Rows are `documented` only: transcribing a page is not a
hardware verification, and the curated tables above remain the place to look for
behaviour, caveats and evidence labels.

`161` commands below had no curated row. The `?` column names the query
form the SCPI convention implies; confirm the spelling on the cited page first.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:BEEPer[:STATe]` | `:BEEPer[:STATe]?` | <b> = 1 or ON, 0 or OFF | documented; beeper for limit tests | 192 |
| `:CALCulate2:DATA` | `:CALCulate2:DATA?` | — | documented; query only: CALC2 result; the raw reading comes back when CALC2 is off or NONE | 154 |
| `:CALCulate2:IMMediate` | `:CALCulate2:IMMediate?` | — | documented; run CALC2 over the buffered readings; the ? form runs it and returns the result | 154 |
| `:CALCulate2:STATe` | `:CALCulate2:STATe?` | <b> = 0 or off, 1 or on | documented; enable or disable the CALC2 calculation | 153 |
| `:CALCulate3:IMMediate` | `:CALCulate3:IMMediate?` | — | documented; re-process the current input against the new limits; it does not start a conversion | 156 |
| `:CALCulate3:LIMit` | `:CALCulate3:LIMit?` | <n> = -100e6 to 100e6 (LIMIT1 upper/lower value); DEFault upper 1, lower -1 | documented; p.155 is the LIMIT1 path (:UPPer[:DATA] / :LOWer[:DATA]); there is no bare :LIMit command | 155 |
| `:CALCulate3:LIMit[1]:CLEar:AUTO` | `:CALCulate3:LIMit[1]:CLEar:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; auto-clear the limit failure when the instrument enters idle | 156 |
| `:CALCulate3:LIMit[1]:CLEar[:IMMediate]` | `:CALCulate3:LIMit[1]:CLEar[:IMMediate]?` | — | documented; clear the LIMIT1 fail indication | 156 |
| `:CALCulate3:LIMit[1]:FAIL` | `:CALCulate3:LIMit[1]:FAIL?` | — | documented; query only: 1 = pass, 0 = fail; it does not say which limit failed (read the Measurement Event Register) and reading it does not clear the failure | 155 |
| `:CALCulate3:LIMit[1]:STATE` | `:CALCulate3:LIMit[1]:STATE?` | <b> = 0 or off, 1 or on | documented; enable or disable the LIMIT1 test; disabling it clears the fail indication | 155 |
| `[:DATA]` | `[:DATA]?` | <n> = -100e6 to 100e6 (LIMIT1 value; upper DEFault 1, lower DEFault -1) | documented; Table 5-2 (p.139) only: the :CALCulate3:LIMit[1]:UPPer[:DATA] / :LOWer[:DATA] value; no standalone [:DATA] command page | 139 |
| `:DISPlay:ENABle` | `:DISPlay:ENABle?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the display circuitry; when disabled the display freezes and every key except LOCAL is locked out | 157 |
| `:DISPlay[:WINDow[1]]:TEXT:DATA` | `:DISPlay[:WINDow[1]]:TEXT:DATA?` | <a> = up to 12 ASCII characters, enclosed in " " or ' ' | documented; define the displayed message; a space counts as a character and excess characters are an error | 157 |
| `:DISPlay[WINDow[1]]:TEXT:STATe` | `:DISPlay[WINDow[1]]:TEXT:STATe?` | <b> = 0 or OFF, 1 or ON | documented; show or hide the defined text message; leaving remote cancels the message | 158 |
| `:FORMat:BORDer` | `:FORMat:BORDer?` | <name> = NORMal, SWAPped | documented; IEEE754 byte order for the binary formats; ASCII is always normal order and the #0 header is unaffected | 161 |
| `:FORMat[:DATA]` | `:FORMat[:DATA]?` | <type> = ASCii, SREal, DREal | documented; bus data format for buffer transfers; :SENSe:DATA? and :CALCulate:DATA? are always ASCII | 159 |
| `:INITiate[:IMMediate]` | `:INITiate[:IMMediate]?` | — | documented; take the instrument out of idle; it returns to idle after the operations when continuous initiation is off | 201 |
| `:ROUTe:CLOSe:STATe` | `:ROUTe:CLOSe:STATe?` | — | documented; query only: closed channel (or channel pair); a 4-pole pair partner is not reported and :MULTiple:CLOSe closures are not reported | 164 |
| `:ROUTe:MULTiple:CLOSe` | `:ROUTe:MULTiple:CLOSe?` | <list> = (@chanlist), channels 1 to 11 | documented; close several channels; closing channel 11 selects 2-pole mode | 164 |
| `:ROUTe:MULTiple:CLOSe:STATe` | `:ROUTe:MULTiple:CLOSe:STATe?` | — | documented; query only: list of closed channels, the 4-pole pair included | 165 |
| `:ROUTe:MULTiple:OPEN` | `:ROUTe:MULTiple:OPEN?` | <list> = (@chanlist), channels 1 to 11 | documented; open several channels; opening channel 11 selects 4-pole mode | 165 |
| `:ROUTe:OPEN:ALL` | `:ROUTe:OPEN:ALL?` | — | documented; open channels 1 through 10 only (11 is the 2/4-pole relay); it also disables scanning (:LSELect NONE) | 164 |
| `:ROUTe:SCAN:EXTernal` | `:ROUTe:SCAN:EXTernal?` | <list> = (@scanlist), external channels 1 to 800; the list holds 2 to 800 channels | documented; external scan list for an external switch system; enabled by :SCAN:LSELect EXTernal | 166 |
| `:ROUTe:SCAN:LSELect` | `:ROUTe:SCAN:LSELect?` | <name> = INTernal, EXTernal, NONE | documented; select the scan operation; NONE disables all scan operations | 167 |
| `:ROUTe:SCAN[:INTernal]` | `:ROUTe:SCAN[:INTernal]?` | <list> = (@scanlist), channels 1 to 10; the list holds 2 to 10 consecutive channels | documented; define the internal scan list and enable the scan; skipping channels is not allowed | 166 |
| `:SENSe[1]]:CURRent:AC:AVERage:TCONtrol` | `:SENSe[1]]:CURRent:AC:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for ACI; changing the type disables auto filter; p.177 spells the header ':SENSe[1]]' | 177 |
| `:SENSe[1]]:VOLTage[:DC]:REFerence` | `:SENSe[1]]:VOLTage[:DC]:REFerence?` | <n> = -1010 to 1010 (reference for DCV); DEFault 0, MINimum/Maximum per function | documented; REL reference value for DCV; reading = input - reference when :REFerence:STATe is on; p.174 spells the header ':SENSe[1]]' | 174 |
| `[:SENSe[1]]` | `[:SENSe[1]]?` | — | documented; Table 5-6 (p.141) subsystem header; no parameter at this level | 141 |
| `[:SENSe[1]]:CURRen[:DC]:NPLCycles` | `[:SENSe[1]]:CURRen[:DC]:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for DCI; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:CURRent:AC:AVERage:COUNt` | `[:SENSe[1]]:CURRent:AC:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for ACI; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:CURRent:AC:AVERage:STATe` | `[:SENSe[1]]:CURRent:AC:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for ACI | 177 |
| `[:SENSe[1]]:CURRent:AC:DETector:BANDwidth` | `[:SENSe[1]]:CURRent:AC:DETector:BANDwidth?` | <n> = 3 to 300e3 (Hz); 3, 30 and 300 select 3Hz-300kHz, 30Hz-300kHz and 300Hz-300kHz | documented; AC bandwidth for ACI; the NPLC setting is valid only at 300 | 179 |
| `[:SENSe[1]]:CURRent:AC:DIGits` | `[:SENSe[1]]:CURRent:AC:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for ACI; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:CURRent:AC:NPLCycles` | `[:SENSe[1]]:CURRent:AC:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for ACI; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:CURRent:AC:RANGe:AUTO` | `[:SENSe[1]]:CURRent:AC:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for ACI | 173 |
| `[:SENSe[1]]:CURRent:AC:RANGe[:UPPer]` | `[:SENSe[1]]:CURRent:AC:RANGe[:UPPer]?` | <n> = 0 to 3.1 (expected reading in amps); DEFault 3, MINimum 0, MAXimum same as DEFault | documented; manual range selection for ACI by expected reading; a valid write disables autorange | 172 |
| `[:SENSe[1]]:CURRent:AC:REFerence` | `[:SENSe[1]]:CURRent:AC:REFerence?` | <n> = -3.1 to 3.1 (reference for ACI); DEFault 0, MINimum/Maximum per function | documented; REL reference value for ACI; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:CURRent:AC:REFerence:ACQuire` | `[:SENSe[1]]:CURRent:AC:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for ACI; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:CURRent:AC:REFerence:STATe` | `[:SENSe[1]]:CURRent:AC:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for ACI | 175 |
| `[:SENSe[1]]:CURRent:DC:DIGits` | `[:SENSe[1]]:CURRent:DC:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for DCI; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:CURRent[:DC]:AVERage:COUNt` | `[:SENSe[1]]:CURRent[:DC]:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for DCI; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:CURRent[:DC]:AVERage:STATe` | `[:SENSe[1]]:CURRent[:DC]:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for DCI | 177 |
| `[:SENSe[1]]:CURRent[:DC]:AVERage:TCONtrol` | `[:SENSe[1]]:CURRent[:DC]:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for DCI; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:CURRent[:DC]:RANGe:AUTO` | `[:SENSe[1]]:CURRent[:DC]:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for DCI | 173 |
| `[:SENSe[1]]:CURRent[:DC]:RANGe[:UPPer]` | `[:SENSe[1]]:CURRent[:DC]:RANGe[:UPPer]?` | <n> = 0 to 3.1 (expected reading in amps); DEFault 3, MINimum 0, MAXimum same as DEFault | documented; manual range selection for DCI by expected reading; a valid write disables autorange | 172 |
| `[:SENSe[1]]:CURRent[:DC]:REFerence` | `[:SENSe[1]]:CURRent[:DC]:REFerence?` | <n> = -3.1 to 3.1 (reference for DCI); DEFault 0, MINimum/Maximum per function | documented; REL reference value for DCI; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:CURRent[:DC]:REFerence:ACQuire` | `[:SENSe[1]]:CURRent[:DC]:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for DCI; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:CURRent[:DC]:REFerence:STATe` | `[:SENSe[1]]:CURRent[:DC]:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for DCI | 175 |
| `[:SENSe[1]]:DATA` | `[:SENSe[1]]:DATA?` | — | documented; query only: latest raw or REL-adjusted reading in exponent form; the response carries no function name | 169 |
| `[:SENSe[1]]:DIODe:CURRent:RANGe[:UPPer]` | `[:SENSe[1]]:DIODe:CURRent:RANGe[:UPPer]?` | <NRf> = 0 to 1e-3 (expected diode current); the ranges are 10µA, 100µA and 1mA | documented; diode test current range chosen from the expected current | 182 |
| `[:SENSe[1]]:FREQuency:DIGits` | `[:SENSe[1]]:FREQuency:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for FREQuency; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:FREQuency:REFerence` | `[:SENSe[1]]:FREQuency:REFerence?` | <n> = 0 to 1.5e7 (reference for FREQ); DEFault 0, MINimum/Maximum per function | documented; REL reference value for FREQuency; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:FREQuency:REFerence:ACQuire` | `[:SENSe[1]]:FREQuency:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for FREQuency; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:FREQuency:REFerence:STATe` | `[:SENSe[1]]:FREQuency:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for FREQuency | 175 |
| `[:SENSe[1]]:FREQuency:THReshold:VOLTage:RANGe` | `[:SENSe[1]]:FREQuency:THReshold:VOLTage:RANGe?` | <n> = 0 to 1010 (signal level in volts) | documented; expected input level for FREQuency; the instrument then selects the threshold range | 179 |
| `[:SENSe[1]]:FRESistance:AVERage:COUNt` | `[:SENSe[1]]:FRESistance:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for Ω4; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:FRESistance:AVERage:STATe` | `[:SENSe[1]]:FRESistance:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for Ω4 | 177 |
| `[:SENSe[1]]:FRESistance:AVERage:TCONtrol` | `[:SENSe[1]]:FRESistance:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for Ω4; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:FRESistance:DIGits` | `[:SENSe[1]]:FRESistance:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for Ω4; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:FRESistance:NPLCycles` | `[:SENSe[1]]:FRESistance:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for Ω4; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:FRESistance:RANGe:AUTO` | `[:SENSe[1]]:FRESistance:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for Ω4 | 173 |
| `[:SENSe[1]]:FRESistance:RANGe[:UPPer]` | `[:SENSe[1]]:FRESistance:RANGe[:UPPer]?` | <n> = 0 to 120e6 (expected reading in ohms); DEFault 100e6, MINimum 0, MAXimum same as DEFault | documented; manual range selection for Ω4 by expected reading; a valid write disables autorange; p.172 prints the default as '100e6 and Ω' | 172 |
| `[:SENSe[1]]:FRESistance:REFerence` | `[:SENSe[1]]:FRESistance:REFerence?` | <n> = 0 to 120e6 (reference for Ω4); DEFault 0, MINimum/Maximum per function | documented; REL reference value for Ω4; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:FRESistance:REFerence:ACQuire` | `[:SENSe[1]]:FRESistance:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for Ω4; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:FRESistance:REFerence:STATe` | `[:SENSe[1]]:FRESistance:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for Ω4 | 175 |
| `[:SENSe[1]]:FUNCtion` | `[:SENSe[1]]:FUNCtion?` | <name> = 'CURRent:AC', 'CURRent[:DC]', 'VOLTage:AC', 'VOLTage[:DC]', 'RESistance', 'FRESistance', 'PERiod', 'FREQuency', 'TEMPerature', 'DIODe', 'CONTinuity' | documented; select the measurement function; each function keeps its own range, speed, resolution, filter and REL | 168 |
| `[:SENSe[1]]:HOLD:COUNt` | `[:SENSe[1]]:HOLD:COUNt?` | <NRf> = 2 to 100 | documented; number of readings compared to the seed reading during Hold | 170 |
| `[:SENSe[1]]:HOLD:STATe` | `[:SENSe[1]]:HOLD:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable Hold | 170 |
| `[:SENSe[1]]:HOLD:WINDow` | `[:SENSe[1]]:HOLD:WINDow?` | <NRf> = 0.01 to 20 | documented; Hold window as a percent of the seed reading | 170 |
| `[:SENSe[1]]:PERiod:DIGits` | `[:SENSe[1]]:PERiod:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for PERiod; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:PERiod:REFerence` | `[:SENSe[1]]:PERiod:REFerence?` | <n> = 0 to 1 (reference for PER); DEFault 0, MINimum/Maximum per function | documented; REL reference value for PERiod; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:PERiod:REFerence:ACQuire` | `[:SENSe[1]]:PERiod:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for PERiod; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:PERiod:REFerence:STATe` | `[:SENSe[1]]:PERiod:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for PERiod | 175 |
| `[:SENSe[1]]:PERiod:THReshold:VOLTage:RANGe` | `[:SENSe[1]]:PERiod:THReshold:VOLTage:RANGe?` | <n> = 0 to 1010 (signal level in volts) | documented; expected input level for PERiod; the instrument then selects the threshold range | 179 |
| `[:SENSe[1]]:RESistance:AVERage:COUNt` | `[:SENSe[1]]:RESistance:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for Ω2; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:RESistance:AVERage:STATe` | `[:SENSe[1]]:RESistance:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for Ω2 | 177 |
| `[:SENSe[1]]:RESistance:AVERage:TCONtrol` | `[:SENSe[1]]:RESistance:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for Ω2; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:RESistance:DIGits` | `[:SENSe[1]]:RESistance:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for Ω2; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:RESistance:NPLCycles` | `[:SENSe[1]]:RESistance:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for Ω2; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:RESistance:RANGe:AUTO` | `[:SENSe[1]]:RESistance:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for Ω2 | 173 |
| `[:SENSe[1]]:RESistance:RANGe[:UPPer]` | `[:SENSe[1]]:RESistance:RANGe[:UPPer]?` | <n> = 0 to 120e6 (expected reading in ohms); DEFault 100e6, MINimum 0, MAXimum same as DEFault | documented; manual range selection for Ω2 by expected reading; a valid write disables autorange; p.172 prints the default as '100e6 and Ω' | 172 |
| `[:SENSe[1]]:RESistance:REFerence` | `[:SENSe[1]]:RESistance:REFerence?` | <n> = 0 to 120e6 (reference for Ω2); DEFault 0, MINimum/Maximum per function | documented; REL reference value for Ω2; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:RESistance:REFerence:ACQuire` | `[:SENSe[1]]:RESistance:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for Ω2; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:RESistance:REFerence:STATe` | `[:SENSe[1]]:RESistance:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for Ω2 | 175 |
| `[:SENSe[1]]:TEMPerature:AVERage:COUNt` | `[:SENSe[1]]:TEMPerature:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for TEMP; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:TEMPerature:AVERage:STATe` | `[:SENSe[1]]:TEMPerature:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for TEMP | 177 |
| `[:SENSe[1]]:TEMPerature:AVERage:TCONtrol` | `[:SENSe[1]]:TEMPerature:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for TEMP; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:TEMPerature:DIGits` | `[:SENSe[1]]:TEMPerature:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for TEMPerature; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:TEMPerature:NPLCycles` | `[:SENSe[1]]:TEMPerature:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for TEMP; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:TEMPerature:REFerence` | `[:SENSe[1]]:TEMPerature:REFerence?` | <n> = -200 to 1372 (reference for TEMP); DEFault 0, MINimum/Maximum per function | documented; REL reference value for TEMPerature; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:TEMPerature:REFerence:ACQuire` | `[:SENSe[1]]:TEMPerature:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for TEMPerature; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:TEMPerature:REFerence:STATe` | `[:SENSe[1]]:TEMPerature:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for TEMPerature | 175 |
| `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:REAL:OFFSET` | `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:REAL:OFFSET?` | <n> = -0.09999 to 0.09999 (volts); DEFault 0.05463, MINimum -0.09999, MAXimum 0.09999 | documented; offset voltage at 0°C for the real reference junction | 182 |
| `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:RSELect` | `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:RSELect?` | <name> = SIMulated, REAL | documented; reference junction type; REAL is configured with :REAL:TCOefficient and :REAL:OFFSET | 180 |
| `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:SIMulated` | `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]:SIMulated?` | <n> = 0 to 50 (°C), 32 to 122 (°F), 273 to 323 (K); DEFault 23°C/73.4°F/296K, MINimum 0°C/32°F/273K, MAXimum 50°C/122°F/323K | documented; simulated reference-junction temperature in the selected unit | 181 |
| `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]]:REAL:TCoefficient` | `[:SENSe[1]]:TEMPerature:TCouple:RJUNction[1]]:REAL:TCoefficient?` | <n> = -0.09999 to 0.09999 (°C/volt); DEFault +0.01, MINimum -0.09999, MAXimum +0.09999 | documented; temperature coefficient of the real junction; not affected by :UNIT:TEMPerature; p.181 spells the header 'RJUNction[1]]' | 181 |
| `[:SENSe[1]]:TEMPerature:TCouple:TYPE` | `[:SENSe[1]]:TEMPerature:TCouple:TYPE?` | <name> = J, K, T | documented; thermocouple type | 180 |
| `[:SENSe[1]]:VOLTage:AC:AVERage:COUNt` | `[:SENSe[1]]:VOLTage:AC:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for ACV; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:VOLTage:AC:AVERage:STATe` | `[:SENSe[1]]:VOLTage:AC:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for ACV | 177 |
| `[:SENSe[1]]:VOLTage:AC:AVERage:TCONtrol` | `[:SENSe[1]]:VOLTage:AC:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for ACV; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:VOLTage:AC:DETector:BANDwidth` | `[:SENSe[1]]:VOLTage:AC:DETector:BANDwidth?` | <n> = 3 to 300e3 (Hz); 3, 30 and 300 select 3Hz-300kHz, 30Hz-300kHz and 300Hz-300kHz | documented; AC bandwidth for ACV; the NPLC setting is valid only at 300 | 179 |
| `[:SENSe[1]]:VOLTage:AC:DIGits` | `[:SENSe[1]]:VOLTage:AC:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for ACV; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:VOLTage:AC:NPLCycles` | `[:SENSe[1]]:VOLTage:AC:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for ACV; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:VOLTage:AC:RANGe:AUTO` | `[:SENSe[1]]:VOLTage:AC:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for ACV | 173 |
| `[:SENSe[1]]:VOLTage:AC:RANGe[:UPPer]` | `[:SENSe[1]]:VOLTage:AC:RANGe[:UPPer]?` | <n> = 0 to 757.5 (expected reading in AC volts); DEFault 757.5, MINimum 0, MAXimum same as DEFault | documented; manual range selection for ACV by expected reading; a valid write disables autorange | 172 |
| `[:SENSe[1]]:VOLTage:AC:REFerence` | `[:SENSe[1]]:VOLTage:AC:REFerence?` | <n> = -757.5 to 757.5 (reference for ACV); DEFault 0, MINimum/Maximum per function | documented; REL reference value for ACV; reading = input - reference when :REFerence:STATe is on | 174 |
| `[:SENSe[1]]:VOLTage:AC:REFerence:ACQuire` | `[:SENSe[1]]:VOLTage:AC:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for ACV; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:VOLTage:AC:REFerence:STATe` | `[:SENSe[1]]:VOLTage:AC:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for ACV | 175 |
| `[:SENSe[1]]:VOLTage:DC:DIGits` | `[:SENSe[1]]:VOLTage:DC:DIGits?` | <n> = 4 to 7 (3½ to 6½ digits; a real value is rounded to the nearest integer); DEFault 6 for DCI, DCV, Ω2, Ω4, FREQ and PER, 5 for ACI, ACV and TEMP | documented; display resolution for DCV; the bus string keeps its significant digits | 176 |
| `[:SENSe[1]]:VOLTage[:DC]:AVERage:COUNt` | `[:SENSe[1]]:VOLTage[:DC]:AVERage:COUNt?` | <n> = 1 to 100 (readings averaged); DEFault 10, MINimum 1, MAXimum 100 | documented; filter count for DCV; the larger the count, the more filtering | 178 |
| `[:SENSe[1]]:VOLTage[:DC]:AVERage:STATe` | `[:SENSe[1]]:VOLTage[:DC]:AVERage:STATe?` | <b> = 0 or OFF, 1 or ON | documented; enable or disable the digital averaging filter for DCV | 177 |
| `[:SENSe[1]]:VOLTage[:DC]:AVERage:TCONtrol` | `[:SENSe[1]]:VOLTage[:DC]:AVERage:TCONtrol?` | <name> = REPeat, MOVing | documented; averaging filter type for DCV; changing the type disables auto filter | 177 |
| `[:SENSe[1]]:VOLTage[:DC]:NPLCycles` | `[:SENSe[1]]:VOLTage[:DC]:NPLCycles?` | <n> = 0.01 to 10 (power line cycles per integration); DEFault 1, MINimum 0.01, MAXimum 10 | documented; integration time in power-line cycles for DCV; frequency and period have no NPLC | 171 |
| `[:SENSe[1]]:VOLTage[:DC]:RANGe:AUTO` | `[:SENSe[1]]:VOLTage[:DC]:RANGe:AUTO?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable autorange for DCV | 173 |
| `[:SENSe[1]]:VOLTage[:DC]:RANGe[:UPPer]` | `[:SENSe[1]]:VOLTage[:DC]:RANGe[:UPPer]?` | <n> = 0 to 1010 (expected reading in DC volts); DEFault 1000, MINimum 0, MAXimum same as DEFault | documented; manual range selection for DCV by expected reading; a valid write disables autorange | 172 |
| `[:SENSe[1]]:VOLTage[:DC]:REFerence:ACQuire` | `[:SENSe[1]]:VOLTage[:DC]:REFerence:ACQuire?` | — | documented; acquire the present input as the REL reference for DCV; errors if another function is selected or the reading is OFLO/---- | 175 |
| `[:SENSe[1]]:VOLTage[:DC]:REFerence:STATe` | `[:SENSe[1]]:VOLTage[:DC]:REFerence:STATe?` | <b> = 1 or ON, 0 or OFF | documented; enable or disable the REL reference for DCV | 175 |
| `:STATUS:PRESET` | `:STATUS:PRESET?` | — | documented; clear the Questionable, Measurement and Operation event enable registers; other registers are unaffected | 189 |
| `:STATus:MEASurement:CONDition` | `:STATus:MEASurement:CONDition?` | — | documented; query only: real-time condition register as a decimal value | 189 |
| `:STATus:MEASurement:ENABle` | `:STATus:MEASurement:ENABle?` | <NRf> = 0, 1, 2, 4, 16, 32, 64, 128, 256, 512, 1024, 16384 or 65535 (bit weights; 0 clears, 65535 sets all bits) | documented; program the measurement event enable register, the mask for the event register | 187 |
| `:STATus:MEASurement[:EVENt]` | `:STATus:MEASurement[:EVENt]?` | — | documented; query only: decimal event-register value; reading the register clears its bits | 183 |
| `:STATus:OPERation:CONDition` | `:STATus:OPERation:CONDition?` | — | documented; query only: real-time condition register as a decimal value | 189 |
| `:STATus:OPERation:ENABle` | `:STATus:OPERation:ENABle?` | <NRf> = 0, 1, 2, 4, 16, 32, 64, 128, 256, 512, 1024, 16384 or 65535 (bit weights; 0 clears, 65535 sets all bits) | documented; program the operation event enable register, the mask for the event register | 187 |
| `:STATus:OPERation[:EVENt]` | `:STATus:OPERation[:EVENt]?` | — | documented; query only: decimal event-register value; reading the register clears its bits | 183 |
| `:STATus:PRESet` | `:STATus:PRESet?` | — | documented; Table 5-7 (p.147) summary row 'Return status registers to default states'; the command page is p.189 | 147 |
| `:STATus:QUEStionable:CONDition` | `:STATus:QUEStionable:CONDition?` | — | documented; query only: real-time condition register as a decimal value | 189 |
| `:STATus:QUEStionable:ENABle` | `:STATus:QUEStionable:ENABle?` | <NRf> = 0, 1, 2, 4, 16, 32, 64, 128, 256, 512, 1024, 16384 or 65535 (bit weights; 0 clears, 65535 sets all bits) | documented; program the questionable event enable register, the mask for the event register | 187 |
| `:STATus:QUEStionable[:EVENt]` | `:STATus:QUEStionable[:EVENt]?` | — | documented; query only: decimal event-register value; reading the register clears its bits | 183 |
| `:STATus:QUEue:CLEar` | `:STATus:QUEue:CLEar?` | — | documented; clear the error queue | 190 |
| `:STATus:QUEue:DISable` | `:STATus:QUEue:DISable?` | <list> = (numlist) of message numbers | documented; keep the listed messages out of the error queue | 191 |
| `:STATus:QUEue:ENABle` | `:STATus:QUEue:ENABle?` | <list> = (numlist) of message numbers, e.g. (-110), (-110,-140,-222), (-110:-222) or () to disable all | documented; enable the listed messages for the error queue; unlisted messages are disabled | 191 |
| `:STATus:QUEue[:NEXT]` | `:STATus:QUEue[:NEXT]?` | — | documented; query only: read and remove the oldest message; FIFO of 10 with '350, Queue Overflow' on overflow; same as :SYSTem:ERRor? | 190 |
| `:SYSTem:CLEar` | `:SYSTem:CLEar?` | — | documented; clear the error queue | 195 |
| `:SYSTem:ERRor` | `:SYSTem:ERRor?` | — | documented; query only: read and remove the oldest message; FIFO of 10 with '350, Queue Overflow' on overflow; same as :STATus:QUEue[:NEXT]? | 194 |
| `:SYSTem:FRSWitch` | `:SYSTem:FRSWitch?` | — | documented; query only: 1 = front panel inputs, 0 = rear panel inputs | 193 |
| `:SYSTem:KCLick` | `:SYSTem:KCLick?` | <b> = 1 or ON (default), 0 or OFF | documented; keyclick on or off | 192 |
| `:SYSTem:KEY` | `:SYSTem:KEY?` | <NRf> = key-press code (1 SHIFT, 2 DCV, 3 ACV, 4 DCI, 5 ACI, 6 Ω2, 7 Ω4, 8 FREQ, 11 up arrow, 12 AUTO, 13 down arrow, 14 ENTER, 15 right arrow, 16 TEMP, 17 LOCAL, 18 EX TRIG, 19 TRIG, 20 STORE, 21 RECALL, 22 FILTER, 23 REL, 24 left arrow, 26 OPEN, 27 CLOSE, 28 STEP, 29 SCAN, 30 DIGITS, 31 RATE, 32 EXIT; 9, 10 and 25 are unassigned) | documented; simulate a front-panel key press; :KEY? returns the last key code | 196 |
| `:SYSTem:LFRequency` | `:SYSTem:LFRequency?` | — | documented; query only: power-line frequency, sensed at power-up | 198 |
| `:SYSTem:LOCal` | `:SYSTem:LOCal?` | — | documented; take the instrument out of remote and re-enable the front keys; RS-232 only | 198 |
| `:SYSTem:POSetup` | `:SYSTem:POSetup?` | <name> = RST, PRESet, SAV0 | documented; power-on defaults; SAV0 uses the setup saved with *SAV | 193 |
| `:SYSTem:REMote` | `:SYSTem:REMote?` | — | documented; place the instrument in remote; RS-232 only | 198 |
| `:SYSTem:RWLock` | `:SYSTem:RWLock?` | — | documented; local lockout, front-panel keys disabled; RS-232 only, :LOCal restores them | 198 |
| `:SYSTem:VERSion` | `:SYSTem:VERSion?` | — | documented; query only: SCPI standard version, e.g. 1991.0 | 194 |
| `:TRACe:CLEar` | `:TRACe:CLEar?` | — | documented; clear the buffer; otherwise a later store can leave old readings in it | 199 |
| `:TRACe:DATA` | `:TRACe:DATA?` | — | documented; query only: send all buffered readings in the :FORMat format | 200 |
| `:TRACe:FEED` | `:TRACe:FEED?` | <name> = SENSe[1], CALCulate[1], NONE | documented; buffer source: raw readings, math readings, or none | 200 |
| `:TRACe:FEED:CONTrol` | `:TRACe:FEED:CONTrol?` | <name> = NEVer, NEXT | documented; NEVer disables buffer storage; NEXT fills the buffer and stops | 200 |
| `:TRACe:FREE` | `:TRACe:FREE?` | — | documented; query only: two comma-separated values, bytes of memory available and bytes reserved for readings | 199 |
| `:TRACe:POINts` | `:TRACe:POINts?` | <NRf> = 2 to 1024 | documented; buffer size in readings | 199 |
| `:TRIGger:[SEQuence[1]]:TIMer` | `:TRIGger:[SEQuence[1]]:TIMer?` | <n> = 0.001 to 999999.999 (seconds) | documented; measure-layer timer interval, effective only when the control source is TIMer; p.204 spells the header '[SEQuence[1]]' | 204 |
| `:TRIGger[:SEQuence[1]]` | `:TRIGger[:SEQuence[1]]?` | — | documented; Table 5-10 (p.149) path header 'Path to program Trigger Layer'; no parameter | 149 |
| `:TRIGger[:SEQuence[1]]:COUNt` | `:TRIGger[:SEQuence[1]]:COUNt?` | <n> = 1 to 9999, INF; DEFault 1, MINimum 1, MAXimum 9999 | documented; number of trigger-model loops (device actions) | 202 |
| `:TRIGger[:SEQuence[1]]:DELay` | `:TRIGger[:SEQuence[1]]:DELay?` | <n> = 0 to 999999.999 (seconds); DEFault 0, MINimum 0, MAXimum 999999.999 | documented; delay from the trigger event to the device action; :DELay:AUTO enables or disables it | 203 |
| `:TRIGger[:SEQuence[1]]:SIGNal` | `:TRIGger[:SEQuence[1]]:SIGNal?` | — | documented; bypass the programmed control source; an error is reported if the instrument is not waiting for that event | 204 |
| `:TRIGger[:SEQuence[1]]:SOURce` | `:TRIGger[:SEQuence[1]]:SOURce?` | <name> = IMMediate, EXTernal, TIMer, MANual, BUS | documented; event control source; BUS means a GET or *TRG | 203 |
| `:UNIT:VOLTage:AC` | `:UNIT:VOLTage:AC?` | <name> = V, DB, DBM | documented; ACV units; DB and DBM use :DB:REFerence and :DBM:IMPedance | 205 |
| `:UNIT:VOLTage:AC:DB:REFerence` | `:UNIT:VOLTage:AC:DB:REFerence?` | <n> = 1e-7 to 1000 (volts) | documented; dB reference level for ACV, not range dependent; p.206 prints the lower bound as 'le-7' | 206 |
| `:UNIT:VOLTage:AC:DBM:IMPedance` | `:UNIT:VOLTage:AC:DBM:IMPedance?` | <n> = 1 to 9999 (ohms) | documented; dBm reference impedance for ACV; a rational value is rounded to the nearest valid integer | 206 |
| `:UNIT:VOLTage:DC` | `:UNIT:VOLTage:DC?` | <name> = V, DB, DBM | documented; DCV units; DB and DBM use :DB:REFerence and :DBM:IMPedance | 206 |
| `:UNIT:VOLTage[:DC]:DB:REFerence` | `:UNIT:VOLTage[:DC]:DB:REFerence?` | <n> = 1e-7 to 1000 (volts) | documented; dB reference level for DCV, not range dependent | 206 |
| `:UNIT:VOLTage[:DC]:DBM:IMPedance` | `:UNIT:VOLTage[:DC]:DBM:IMPedance?` | <n> = 1 to 9999 (ohms) | documented; dBm reference impedance for DCV; a rational value is rounded to the nearest valid integer | 207 |
