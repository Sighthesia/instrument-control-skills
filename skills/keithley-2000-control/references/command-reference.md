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
| `:SENSe:<function>:AVERage:STATe` | set | `ON` / `OFF` | Digital averaging filter on/off. Not supported for frequency, period, continuity, diode. | measurement-configuration.md p.51, 177-178<br>hardware-verification.md |
| `:SENSe:<function>:AVERage:STATe?` | query | — | Verified state readback; helper reports `enabled` from it. | hardware-verification.md<br>scripts/keithley2000_session.py |
| `:SENSe:<function>:AVERage:TCONtrol` | set | `MOVing` / `REPeat` | Filter mode; verified both accepted. Helper also accepts `moving`/`repeat` spelling. | measurement-configuration.md p.51, 177-178<br>hardware-verification.md |
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
| `:SENSe:TEMPerature:TCouple:TYPE` | set | `J`, `K`, or `T` | Thermocouple type; verified default readback `J`. Record it with any temperature reading. | basic-measurements.md p.40, 180-181<br>measurement-configuration.md |
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
