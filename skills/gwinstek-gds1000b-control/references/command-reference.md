# Command Reference (Fallback Index)

This page is a fallback index of every SCPI/IEEE-488.2 command already recorded
in this Skill. Read it only when the task-specific reference and the scripts do
not answer the question. Its scope is exclusively what this Skill already
records; the authoritative complete command set is the *GDS-1000B Series
Programming Manual*, Version 1.00, March 2015, which is not copied here. Any
command absent from this index must be verified against the manual and labelled
`documented` before use. The manual's own command list (manual pp. 18-30) was
enumerated on 2026-11-20: it holds 343 command forms and all of them are now in
this file, the ones that no Skill document had recorded appearing in
[Manual commands that this index did not previously
list](#manual-commands-that-this-index-did-not-previously-list). The safety
rules in `SKILL.md` still apply: no routine
`*RST`, `*SAV`, `*RCL`, `:SAVE`, `:RECAll`, or panel-lock changes, and no
overwrite of operator files on `Disk:/` or `USB:/`.

Naming follows the sources exactly, including short/long forms (`:SINGle`,
`:ACQuire:RECOrdlength`, `:MEASure:METHod`, `:SEARCH:STATE`). `X` or `<X>` is a
channel or slot index; `n`/`N` is a channel number. `—` means the Skill records
no parameter list, range, or value for that command; it does not mean the
command takes no parameter.

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | Returns `GW,GDS-<model>,P<serial>,V<version>`; gate channel count, EXT, and Ethernet on the model before anything else. | remote-session.md (manual pp. 33-34)<br>response-and-evidence.md (manual pp. 33-34)<br>SKILL.md |
| `*LRN?` | query | — | Long settings string; preserve verbatim, not every field is parsed. | remote-session.md (manual pp. 33-39) |
| `*RST` | event | — | Resets to documented defaults and destroys the operator setup; never routine cleanup. | remote-session.md (manual pp. 33-39)<br>bench-setup.md |
| `*CLS` | event | — | Clears status and the error queue; only when clearing status is authorized. | remote-session.md (manual pp. 33-39)<br>SKILL.md |
| `*ESE` | set | `<n>` (event status enable register) | Changes what sets the event status bits. | remote-session.md (manual pp. 33-39) |
| `*ESE?` | query | — | Reads the event status enable mask. | remote-session.md (manual pp. 33-39) |
| `*ESR?` | query | — | Event status register; the register is cleared when read. | remote-session.md (manual pp. 33-39)<br>remote-session.md "Status and errors" |
| `*OPC` | event | — | Signals operation complete via the status mechanism. | remote-session.md (manual pp. 33-39) |
| `*OPC?` | query | — | Returns `1` when the pending operation is done. | remote-session.md (manual pp. 33-39) |
| `*SRE` | set | `<n>` (service request enable register) | Changes SRQ behavior. | remote-session.md (manual pp. 33-39) |
| `*SRE?` | query | — | Reads the service request enable mask. | remote-session.md (manual pp. 33-39) |
| `*STB?` | query | — | Status byte; not a substitute for the error queue. | remote-session.md (manual pp. 33-39)<br>remote-session.md "Status and errors" |
| `*SAV` | set | `<1..20>` (setup slot) | Overwrites that setup slot; authorization required. | remote-session.md (manual pp. 33-39)<br>save-and-screenshot.md (manual pp. 33-39, 164-167) |
| `*RCL` | set | `<1..20>` (setup slot) | Replaces the live setup (channel, timebase, trigger, display); authorization required. | remote-session.md (manual pp. 33-39)<br>save-and-screenshot.md (manual pp. 33-39, 164-167) |

## System, status, and error

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SYSTem:LOCK` | set | `{OFF\|ON}` | Locks the front panel; blocks local intervention. Use only on operator request. | remote-session.md (manual p. 163)<br>bench-setup.md |
| `:SYSTem:LOCK?` | query | — | Reads the panel-lock state; release it when the remote session ends unless the operator wants it left locked. | remote-session.md (manual p. 163)<br>bench-setup.md |
| `:SYSTem:ERRor?` | query | — | `+0, "No error."` = empty; `-350, "Queue overflow"` = `INCOMPLETE`; any other record is preserved and `UNVERIFIED`. Drain repeatedly (bounded, the helper uses 20). | remote-session.md (manual pp. 250-253)<br>response-and-evidence.md (manual pp. 250-253)<br>SKILL.md<br>gds1000b_session.py |

## Acquisition (run/stop/single, memory, record length)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:RUN` | event | — | Start continuous acquisition. | capture-and-waveform.md (manual pp. 117-118)<br>gds1000b_session.py |
| `:STOP` | event | — | Stop acquisition; required before `:ACQuire<X>:MEMory?` so the record cannot change during download. | capture-and-waveform.md (manual pp. 117-118)<br>SKILL.md<br>gds1000b_session.py |
| `:SINGle` | event | — | Arm a single acquisition; preferred over `:RUN` for a deterministic download. | capture-and-waveform.md (manual pp. 117-118)<br>SKILL.md<br>gds1000b_session.py |
| `:FORCe` | event | — | Forces a trigger event; a deliberate override, never a timeout workaround. | capture-and-waveform.md (manual pp. 117-118)<br>SKILL.md<br>gds1000b_session.py |
| `:ACQuire<X>:STATe?` | query | — | `0` = raw data not ready, `1` = ready (manual p. 45); reset to zero on the STOP to RUN transition. Poll until `1` before downloading. | capture-and-waveform.md (manual p. 45)<br>SKILL.md<br>gds1000b_session.py |
| `:ACQuire<X>:MEMory?` | query | — | Returns ASCII header, `Waveform Data;` marker, then an IEEE 488.2 definite-length block. Never query while running. Voltages `UNVERIFIED`. | capture-and-waveform.md (manual pp. 41-46)<br>SKILL.md<br>response-and-evidence.md<br>gds1000b_session.py<br>gds1000b_protocol.py |
| `:ACQuire:RECOrdlength` | set | `{1e3\|1e4\|1e5\|1e6\|1e7}` = 1 000 … 10 000 000 points | At two bytes per point the largest record is about 20 MB; parser limits `MAX_POINTS = 10_000_000`, `MAX_PAYLOAD_BYTES = 20_000_000`. | capture-and-waveform.md (manual p. 45) |
| `:ACQuire:RECOrdlength?` | query | — | Read it back and record it with the waveform context. | capture-and-waveform.md (manual p. 45)<br>vertical-timebase-trigger.md<br>gds1000b_session.py |
| `:ACQuire:MODe` | set/query | `{SAMPle\|PDETect\|AVERage}` | 采样模式（手册 p. 41）。`PDETect` 改变“一个点”的含义；`AVERage` 需配 `:ACQuire:AVERage`。会改变所有幅值/有效值结果，必须随波形记录。 | capture-and-waveform.md (manual pp. 40-41)<br>gds1000b_session.py |
| `:ACQuire:AVERage` | set/query | `{2\|4\|8\|16\|32\|64\|128\|256}` | 平均次数（手册 p. 40）。缺失时平均模式停留在面板遗留值。 | capture-and-waveform.md (manual p. 40) |
| `:ACQuire:INTERpolation` | set/query | `{ET\|SINC}` | 内插方式（手册 p. 45）；本机型不支持 `ET`。`SINC` 会让上升时间/过冲变成插值结果。 | capture-and-waveform.md (manual p. 45) |
| `:HEADer` | set | `{ON\|OFF}` | Default ON (manual p. 46). `OFF` returns only the block: no scale, unit, source, or timebase metadata, so the result is `UNVERIFIED`. | capture-and-waveform.md (manual p. 46)<br>response-and-evidence.md (manual p. 46)<br>SKILL.md<br>gds1000b_session.py |
| `:HEADer?` | query | — | Reads the header switch state in the session snapshot. | gds1000b_session.py |

## `:ACQuire` waveform memory

The waveform memory is exposed through the acquisition commands above
(`:ACQuire<X>:MEMory?`, `:ACQuire<X>:STATe?`, `:ACQuire:RECOrdlength`,
`:HEADer`). Block and decoding rules that apply to every `:MEMory?` response:

| Item | Rule | Source |
|---|---|---|
| Block framing | `#<n><length><payload>`; `<length>` is payload bytes, not points. | capture-and-waveform.md (manual p. 41) |
| Sample encoding | Two bytes per point, signed 16-bit two's complement, `-32768..32767`; the manual example is big-endian (`00 1C` = 28). | capture-and-waveform.md (manual p. 41) |
| Rejected shapes | Indefinite `#0` blocks unsupported; odd payload length `INVALID`; declared length beyond received bytes `INCOMPLETE`; extra bytes `INVALID` except one terminator. | capture-and-waveform.md |
| Documented header fields | `Memory Length`, `Trigger Address`, `Trigger Level`, `Source`, `Vertical Units`, `Probe Type`, `Probe Ratio`, `Vertical Scale`, `Vertical Position`, `Horizontal Units`, `Horizontal Scale`, `Horizontal Position`, `Horizontal Mode`, `Sampling Period`, `Firmware`, `Time`, `Format`, `IntpDistance`. | capture-and-waveform.md (manual pp. 41-43) |
| Voltage conversion | `voltage = (code / 25) * Vertical Scale`; no probe-ratio multiplication, no offset; `calibration.status` always `UNVERIFIED`. | capture-and-waveform.md (manual pp. 42-43)<br>response-and-evidence.md (manual pp. 42-43) |

## Vertical / channel

`X` is 1-2 on 2-channel models and 1-4 on 4-channel models; CH3/CH4 on a
2-channel instrument is an error, so check `*IDN?` first.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CHANnel<X>:SCALe` | set/query | `<NRf>`; 2 mV/div .. 10 V/div at x1 | Range assumes a x1 probe; set `PROBe:RATio` to match the physical probe. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:POSition` | set/query | `<NRf>` | Vertical offset. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:COUPling` | set/query | `{AC\|DC\|GND}` | `GND` disconnects the input; a flat trace is not a zero-volt signal. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:PROBe:RATio` | set/query | `<NRf>` | Must match the actual probe; scale readback and measurements depend on it. | vertical-timebase-trigger.md (manual pp. 48-53)<br>bench-setup.md |
| `:CHANnel<X>:PROBe:TYPe` | set/query | `{VOLTage\|CURRent}` | Decides whether voltage/current and area measurements are V/A or V·s/A·s. | vertical-timebase-trigger.md (manual pp. 48-53)<br>measurements.md<br>SKILL.md |
| `:CHANnel<X>:BWLimit` | set/query | `{FULL\|20E6}` | `20E6` inserts a 20 MHz limit; changes rise time and noise. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:DISPlay` | set/query | `{ON\|OFF}` | Only displayed/active channels produce measurement values. Read before arming. | vertical-timebase-trigger.md (manual pp. 48-53)<br>SKILL.md<br>gds1000b_session.py |
| `:CHANnel<X>:INVert` | set | `{ON\|OFF}` | Changes displayed polarity, not trigger-source polarity. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:DESKew` | set | `<NRf>`; -50 ns .. 50 ns | Channel-to-channel deskew. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:EXPand` | set | `{GND\|CENTer}` | Vertical expansion reference. | vertical-timebase-trigger.md (manual pp. 48-53) |
| `:CHANnel<X>:IMPedance?` | query | — | Read-only fixed 1 MΩ; there is no selectable 50 Ω input. | vertical-timebase-trigger.md (manual pp. 48-53) |

## Horizontal / timebase

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:TIMebase:SCALe` | set/query | `<NRf>`; 5 ns/div .. 100 s/div | The sample interval follows timebase and record length; read `Sampling Period` from the header instead of deriving it. | vertical-timebase-trigger.md (manual pp. 119-121)<br>capture-and-waveform.md<br>gds1000b_session.py |
| `:TIMebase:POSition` | set/query | `<NRf>` | Horizontal position. | vertical-timebase-trigger.md (manual pp. 119-121)<br>gds1000b_session.py |
| `:TIMebase:MODe` | set/query | `{MAIN\|WINDOW\|XY}` | `WINDOW`/`XY` change what the main timebase and memory mean; record with any waveform. | vertical-timebase-trigger.md (manual pp. 119-121)<br>gds1000b_session.py |
| `:TIMebase:EXPand` | set | `{CENTer\|TRIGger}` | Anchors horizontal expansion on center or trigger point. | vertical-timebase-trigger.md (manual pp. 119-121) |
| `:TIMebase:WINDow:SCALe` | set | `<NRf>` | Only meaningful in window mode. | vertical-timebase-trigger.md (manual pp. 119-121) |
| `:TIMebase:WINDow:POSition` | set | `<NRf>` | Only meaningful in window mode. | vertical-timebase-trigger.md (manual pp. 119-121) |

## Trigger

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:TRIGger:SOURce` | set/query | `{CH1\|CH2\|CH3\|CH4\|EXT\|LINe}` | CH1/CH2 on all models; CH3/CH4 only on 4-channel models; `EXT` only on 2-channel models; `LINe` = AC line. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:TYPe` | set/query | `{EDGE\|DELay\|PULSEWidth\|VIDeo\|RUNT\|RISEFall\|BUS\|TIMEOut}` | `BUS` decode/trigger is optional/licensed. Configure a subtype only after the type is selected. | vertical-timebase-trigger.md (manual pp. 122-162)<br>advanced-features.md (manual pp. 139-162) |
| `:TRIGger:LEVel` | set/query | `{TTL\|ECL\|SETTO50\|<NRf>}` | `TTL`/`ECL`/`SETTO50` are presets; `<NRf>` is an explicit level. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:HLEVel` | set | `<NRf>` | High level for rise/fall and pulse-runt triggers. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:LLEVel` | set | `<NRf>` | Low level for rise/fall and pulse-runt triggers. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:MODe` | set/query | `{AUTO\|NORMAL}` | `AUTO` sweeps without a trigger; `NORMAL` waits, so a timeout is a configuration result, not a transport bug. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:COUPle` | set/query | `{AC\|DC\|HF\|LF}` | Changes the trigger signal path; can hide DC or HF content. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:NREJ` | set | `{OFF\|ON}` | Noise rejection; changes timing sensitivity. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:HOLDoff` | set | `<NRf>` | Prevents retriggering during a burst or frame. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:EDGe:SLOP` | set | `{RISE\|FALL\|EITHER}` | Edge slope; the effective source is the general `:TRIGger:SOURce`. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:FREQuency?` | query | — | Measured trigger frequency; a measurement, not a configuration readback. | vertical-timebase-trigger.md (manual pp. 122-162) |
| `:TRIGger:STATe?` | query | — | `*ARMED`, `*AUTO`, `*READY`, `*SAVE`, `*TRIGGER`; don't treat `*SAVE` as readiness and don't assume `*TRIGGER` means the memory record is complete. | vertical-timebase-trigger.md (manual pp. 137-138)<br>capture-and-waveform.md (manual pp. 137-138)<br>SKILL.md<br>gds1000b_session.py |
| `:TRIGger:BUS:B1:*` | set/query | `—` (family only) | Bus trigger family; same optional-license caveat as bus decode. | advanced-features.md (manual pp. 139-162) |

Delay, pulse-width, runt, rise-fall, video, and timeout trigger qualifiers
(delay time, pulse width, runt levels, video standard/line/field) are documented
on manual pp. 122-162 but are not enumerated by this Skill.

## Measurement — individual items

`:MEASure:SOURce1` and `:MEASure:SOURce2` select the sources; relay pairs
(`FRRDelay`, `FRFDelay`, …) use both, so select both before reading. Every
individual item returns `<NR3>` or `Chan Off` (`Chan Off` = `INCOMPLETE`, never
zero). Units are not appended to the response.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MEASure:SOURce<X>` | set/query | `{CH1\|CH2\|CH3\|CH4\|MATH}`; `<X>` = 1 or 2 | CH3/CH4 need a 4-channel model. `MATH` correctness depends on `:MATH:*`, which this Skill does not validate. | measurements.md (manual p. 82)<br>SKILL.md<br>gds1000b_session.py |
| `:MEASure:METHod` | set/query | `{AUTO\|HISTogram\|MINMax}` | Chooses how High/Low reference levels are derived; record non-default values. | measurements.md (manual pp. 82-84) |
| `:MEASure:GATing` | set/query | `{OFF\|SCREEN\|CURSOR}` | Restricts the measurement window; results from different gating are not comparable. | measurements.md (manual pp. 82-84) |
| `:MEASure:FREQuency?` | query | — | Hz. | measurements.md (manual p. 86)<br>gds1000b_protocol.py<br>assets/fixtures/README.md (manual p. 86)<br>gds1000b_session.py |
| `:MEASure:PERiod?` | query | — | s. | measurements.md (manual pp. 81-105)<br>gds1000b_protocol.py |
| `:MEASure:RISe?` | query | — | s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FALL?` | query | — | s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PWIDth?` | query | — | Positive width, s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:NWIDth?` | query | — | Negative width, s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PDUTy?` | query | — | Positive duty, %. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:AMPlitude?` | query | — | V or A, depending on `:CHANnel<X>:PROBe:TYPe`. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:MEAN?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:CMEan?` | query | — | Cycle mean, V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:HIGH?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:LOW?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:MAX?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:MIN?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PK2PK?` | query | — | V or A; also used in the SKILL.md measurement example. | measurements.md<br>gds1000b_protocol.py<br>SKILL.md |
| `:MEASure:RMS?` | query | — | V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:CRMS?` | query | — | Cycle RMS, V or A. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:AREa?` | query | — | V·s or A·s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:CARea?` | query | — | Cycle area, V·s or A·s. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:ROVShoot?` | query | — | Rise overshoot, %. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:RPReshoot?` | query | — | Rise preshoot, %. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FOVShoot?` | query | — | Fall overshoot, %. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FPReshoot?` | query | — | Fall preshoot, %. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PPULSE?` | query | — | Positive pulse count; unitless `<NR3>`. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:NPULSE?` | query | — | Negative pulse count; unitless. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PEDGE?` | query | — | Positive edge count; unitless. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:NEDGE?` | query | — | Negative edge count; unitless. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FRRDelay?` | query | — | s; relay pair on source1/source2. Also the `delay` quantity key in the scripts. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FRFDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FFRDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:FFFDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:LRRDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:LRFDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:LFRDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:LFFDelay?` | query | — | s; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |
| `:MEASure:PHAse?` | query | — | deg; relay pair on source1/source2. | measurements.md<br>gds1000b_protocol.py |

## Measurement — eight-slot (`:MEASUrement:MEAS<X>:*`)

`<X>` selects one of eight slots. The slot type is set independently; `VALue?`
and the statistics queries are only meaningful when the slot is enabled and its
source is valid.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MEASUrement:MEAS<X>:SOURCE<X>` | set | `{CH1\|CH2\|CH3\|CH4\|MATH}` | CH3/CH4 need a 4-channel model. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:MEAS<X>:TYPe` | set/query | `PK2pk`、`MAXimum`、`MINImum`、`AMPlitude`、`HIGH`、`LOW`、`MEAN`、`CMEan`、`RMS`、`CRMs`、`AREa`、`CARea`、`ROVShoot`、`FOVShoot`、`RPReshoot`、`FPReshoot`、`FREQuency`、`PERIod`、`RISe`、`FALL`、`PWIdth`、`NWIdth`、`PDUTy`、`PPULSE`、`NPULSE`、`PEDGE`、`NEDGE`、`FRRDelay`、`FRFDelay`、`FFRDelay`、`FFFDelay`、`LRRDelay`、`LRFDelay`、`LFRDelay`、`LFFDelay`、`PHAse` | **必写设置**，不是只读标签；不设类型槽位就没有有效值。手册 p. 107。 | measurements.md (manual p. 107) |
| `:MEASUrement:MEAS<X>:STATE` | set/query | `{OFF\|ON}`（查询返回 `0`/`1`） | 返回 `0` 表示槽位关闭，此时 `VALue?` 结果不得当作测量值。手册 p. 108。 | measurements.md (manual p. 108) |
| `:MEASUrement:REFLevel:PERCent:HIGH` / `:LOW` / `:MID` / `:MID2` | set/query | `<NRf>`，0-100 % | 参考电平百分比；上升/下降时间、占空比、脉宽、相位都由它决定，不记录则数值不可复现。手册 pp. 83-84。 | measurements.md (manual pp. 83-84) |
| `:MEASUrement:MEAS<X>:VALue?` | query | — | Current value of the slot. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:MEAS<X>:MAXimum?` | query | — | Accumulated maximum, not one acquisition; a single `VALue?` without the segment index is ambiguous in segmented mode. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:MEAS<X>:MEAN?` | query | — | Accumulated mean. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:MEAS<X>:MINImum?` | query | — | Accumulated minimum. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:MEAS<X>:STDdev?` | query | — | Accumulated standard deviation. | measurements.md (manual pp. 106-113)<br>SKILL.md |
| `:MEASUrement:STATIstics:MODe` | set/query | `{OFF\|ON}` | Displaying statistics does not necessarily reset them. | measurements.md (manual pp. 106-113) |
| `:MEASUrement:STATIstics:WEIghting` | set/query | `<NR1>`; 2..1000 samples | Sample count used for the statistics. | measurements.md (manual pp. 106-113) |
| `:MEASUrement:STATIstics` | event | `RESET` | Clears accumulated values; do not reset operator statistics without authorization. | measurements.md (manual pp. 106-113) |

## Hardcopy and image save

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:HARDcopy:MODe` | set | `{PRINT\|SAVE}` | `SAVE` directs output to storage, `PRINT` to a configured printer. The helper sets `SAVE`. | save-and-screenshot.md (manual pp. 78-80)<br>SKILL.md<br>gds1000b_session.py |
| `:HARDcopy:ASSIGN` | set | `{IMAGe\|WAVEform\|SETUp\|ALL}` | Selects what is captured. The helper sets `IMAGe`. | save-and-screenshot.md (manual pp. 78-80)<br>SKILL.md<br>gds1000b_session.py |
| `:HARDcopy:SAVEFORMat` | set | `{PNG\|BMP}` | Format of the saved hardcopy; the helper derives it from the requested extension. | save-and-screenshot.md (manual pp. 78-80)<br>SKILL.md<br>gds1000b_session.py |
| `:HARDcopy:PRINTINKSaver` | set | `{ON\|OFF}` | Ink saving for printer output. | save-and-screenshot.md (manual pp. 78-80) |
| `:HARDcopy:SAVEINKSaver` | set | `{ON\|OFF}` | Ink saving for stored output. | save-and-screenshot.md (manual pp. 78-80) |
| `:HARDcopy:START` | event | — | Performs the configured hardcopy; does not choose a destination filename. | save-and-screenshot.md (manual pp. 78-80)<br>SKILL.md<br>gds1000b_session.py |
| `:DISPlay:OUTPut?` | query | — | 返回 16 位 RGB 行程编码（RLE）的屏幕图像，格式 `#<n><len>[count][color]...[count][color]<LF>`，每对 2 字节（手册 p. 77）。**这是唯一的图像回读路径**；本 Skill 未实现 RLE 解码，只能按原始字节保存并标为 `UNVERIFIED`。 | save-and-screenshot.md (manual p. 77) |
| `:DISPlay:WAVEform` | set/query | `{VECTor\|DOT}` | 矢量/点显示方式（手册 p. 77）；影响截图观感，不影响数据。 | save-and-screenshot.md (manual p. 77) |
| `:SAVe:IMAGe` | set | `"Disk:/<name>.PNG"` or `"USB:/<name>.BMP"` | Writes a file on instrument storage; `:DISPlay:OUTPut?` is the only way to read the screen image back over SCPI. Filename stem ≤ 8 characters; path must start with `Disk:/` or `USB:/`; never overwrite operator files. Documented file errors are `-250`/`-252`/`-254`/`-256`/`-257`/`-258` (manual p. 252), so drain the error queue instead of assuming success. | save-and-screenshot.md (manual pp. 165-166, 252)<br>SKILL.md<br>gds1000b_session.py |
| `:SAVe:IMAGe:FILEFormat` | set | `{PNG\|BMP}` | Must match the file extension (`.PNG`→`PNG`, `.BMP`→`BMP`). | save-and-screenshot.md (manual pp. 165-166)<br>SKILL.md<br>gds1000b_session.py |
| `:SAVe:IMAGe:INKSaver` | set | `{ON\|OFF}` | Reduces ink for printing; does not change resolution. | save-and-screenshot.md (manual pp. 165-166)<br>gds1000b_session.py |

## Save/recall and setup files

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SAVe:WAVEform` | set | `{CH1\|CH2\|CH3\|CH4\|MATH\|REF1..REF4}, {REF1..REF4\|W1..W20}` or `{CH1\|CH2\|CH3\|CH4\|MATH\|REF1..REF4\|ALL}, "<path>"` | Saving overwrites the selected destination. `ALL` saves every displayed waveform; the path can become a folder in some manual examples. Same filename limits as images. | save-and-screenshot.md (manual pp. 167-168)<br>SKILL.md |
| `:SAVe:WAVEform:FILEFormat` | set | `{LSF\|DCSV\|FCSV}` | LSF = instrument binary, DCSV = detail CSV (cannot be recalled to the scope), FCSV = fast CSV. | save-and-screenshot.md (manual pp. 167-168) |
| `:RECAll:WAVEform` | set | `{W<n>\|"<path>"}, REF<X>` | Replaces the selected reference waveform; authorization required. | save-and-screenshot.md (manual pp. 167-168)<br>SKILL.md |
| `:SAVe:SETUp` | set | `{S1..S20\|"<path>.SET"}` | File form requires `.SET` on `Disk:/` or `USB:/`. | save-and-screenshot.md (manual pp. 164-167)<br>SKILL.md |
| `:RECAll:SETUp` | set | `{S1..S20\|"<path>.SET"}` | Replaces the live setup (channel, timebase, trigger, display); confirm on an active bench. | save-and-screenshot.md (manual pp. 164-167)<br>SKILL.md |

## Ethernet

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:ETHERnet:DHCP` | set/query | `—` | Applies only to GDS-1074B/GDS-1104B (manual p. 169); check `*IDN?` before use. The socket server is off by default on 4-channel models and must be enabled on the instrument; port 1024-65535; raw TCP with LF termination. | SKILL.md (manual p. 169)<br>remote-session.md (manual p. 169)<br>bench-setup.md (manual p. 169)<br>gds1000b_protocol.py |

## Advanced: math, cursors, display, decode, search, segments

These families are documented for orientation only. The core scripts do not
implement them, and several are optional, licensed, or model-dependent; confirm
the installed option and the displayed menu before sending commands. Commands
whose syntax this Skill records in full are tabulated; the rest are listed per
family immediately below the table, unverified beyond the mnemonic.

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MATH:DISP` | set/query | `{OFF\|ON}` | Math trace display. | advanced-features.md (manual pp. 54-62) |
| `:MATH:TYPe` | set/query | `{DUAL\|ADVanced\|FFT}` | Record the operation with the data. | advanced-features.md (manual pp. 54-62) |
| `:MATH:DUAL:SOURce<X>` | set | `{CH1..CH4}` | Sources must be active; CH3/CH4 need a 4-channel model. | advanced-features.md (manual pp. 54-62) |
| `:MATH:DUAL:OPERator` | set | `{PLUS\|MINus\|MULTiply\|DIVide}` | Division by zero changes the result's meaning. | advanced-features.md (manual pp. 54-62) |
| `:MATH:FFT:MAG` | set | `{DB\|LINEar}` | Magnitude unit; windowing changes the result's meaning. | advanced-features.md (manual pp. 54-62) |
| `:CURSor:MODe` | set/query | `{OFF\|ON}` | Cursor readings depend on mode, source, and position; not a replacement for measurement. | advanced-features.md (manual pp. 63-73) |
| `:CURSor:SOURce` | set | `{CH1..CH4\|MATH\|REF1..REF4}` | CH3/CH4 need a 4-channel model. | advanced-features.md (manual pp. 63-73) |
| `:BUS1:STATE` | set/query | `{ON\|OFF}` | Bus decode is optional/licensed. | advanced-features.md (manual pp. 171-184) |
| `:BUS1:TYPe` | set | `{I2C\|UART\|SPI\|CAN\|LIN}` | Must match the physical bus. | advanced-features.md (manual pp. 171-184) |
| `:LISTer:DATA?` | query | — | Decode results; length and format depend on bus and buffer, so preserve the raw response. | advanced-features.md (manual pp. 171-184) |
| `:SEARCH:STATE` | set/query | `{ON\|OFF}` | Search scans the acquired record without re-acquiring. | advanced-features.md (manual pp. 188-220) |
| `:SEARCH:TOTAL?` | query | — | Number of search events found. | advanced-features.md (manual pp. 188-220) |
| `:SEGMents:STATE` | set/query | `{ON\|OFF}` | Segmented acquisition stores many triggered records. | advanced-features.md (manual pp. 227-235) |
| `:SEGMents:CURRent?` | query | — | Record the segment index with any per-segment value. | advanced-features.md (manual pp. 227-235) |
| `:SEGMents:TOTalnum?` | query | — | Segment count. | advanced-features.md (manual pp. 227-235) |
| `:SEGMents:TIMe?` | query | — | Segment time information; record with the count and current index. | advanced-features.md (manual pp. 227-235) |

Mnemonics recorded without parameters or ranges (set-only unless shown as a
query). Verify each against the manual and label it `documented` before use:

- `:MATH:DUAL:POSition <NRf>`, `:MATH:DUAL:SCALe <NRf>`,
  `:MATH:FFT:SOURce {CH1..CH4}`, `:MATH:FFT:WINDow`,
  `:MATH:FFT:POSition <NRf>`, `:MATH:FFT:SCALe <NRf>`, `:MATH:DEFine` —
  advanced-features.md (manual pp. 54-62).
- `:ACQuire:FILTer*` — digital filter family; applies only with the Digital
  Filter app installed (advanced-features.md, manual pp. 43-44).
- `:CURSor:HUNI` / `:CURSor:HUSE`, `:CURSor:VUNI` / `:CURSor:VUSE`,
  `:CURSor:H1Position`, `:CURSor:H2Position`, `:CURSor:V1Position`,
  `:CURSor:V2Position`, and `:CURSor:XY:*` (rectangular, polar, product, ratio)
  — advanced-features.md (manual pp. 63-73).
- `:CURSor:HDELta?`, `:CURSor:VDELta?` — cursor delta queries
  (advanced-features.md, manual pp. 63-73).
- Display commands (persistence, intensity, grid; pp. 74-77) are described but
  not named by this Skill — advanced-features.md (manual pp. 74-77).
- `:BUS1:INPut`, `:BUS1:I2C:SCLK:SOURce`, `:BUS1:I2C:SDA:SOURce`,
  `:BUS1:UART:BITRate`, `:BUS1:UART:DATABits`, `:BUS1:UART:PARIty`,
  `:BUS1:SPI:SCLK:SOURce`, `:BUS1:SPI:MOSI:SOURce`, plus the `:BUS1:CAN:*` and
  `:BUS1:LIN:*` families — threshold, bit rate, polarity, and source channel
  must match the physical bus (advanced-features.md, manual pp. 171-184).
- `:SEARCH:TRIGger:TYPe`, `:SEARCH:TRIGger:SOURce`, `:SEARCH:TRIGger:EDGE:SLOP`,
  `:SEARCH:TRIGger:LEVel`, `:SEARCH:FFTPeak:METHod` — advanced-features.md
  (manual pp. 188-220).
- `:MARK:CREATE`, `:MARK:DELEte` — annotate record positions; not measurement
  evidence (advanced-features.md, manual pp. 185-187).
- `:SEGMents:SAVe`, `:SEGMents:MEASure:*` — advanced-features.md (manual
  pp. 227-235).

## Advanced: DVM, Go-NoGo, templates, datalog, remote disk

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:DVM:STATE` | set/query | `{ON\|OFF}` | DVM is a separate measurement path with its own mode. | advanced-features.md (manual pp. 236-237) |
| `:DVM:SOURce` | set | `{CH1..CH4}` | CH3/CH4 need a 4-channel model. | advanced-features.md (manual pp. 236-237) |
| `:DVM:VALue?` | query | — | Not equal to `:MEASure:MEAN?` or a cursor reading. | advanced-features.md (manual pp. 236-237) |
| `:GONogo:NGCount?` | query | — | Number of violations; store with the template used. | advanced-features.md (manual pp. 238-243) |
| `:GONogo:VIOLation?` | query | — | Violation state; depends on the stored template and tolerance. | advanced-features.md (manual pp. 238-243) |
| `:DATALOG:STATE` | set/query | `{ON\|OFF}` | The Skill never starts a log. | advanced-features.md (manual pp. 244-246) |
| `:DATALOG:INTerval` | set | `<NRf>` | Interval × duration bounds the file size. | advanced-features.md (manual pp. 244-246) |
| `:DATALOG:DURation` | set | `<NRf>` | Interval × duration bounds the file size. | advanced-features.md (manual pp. 244-246) |

Mnemonics recorded without parameters or ranges:

- `:DVM:MODe` — record the mode with every DVM value (advanced-features.md,
  manual pp. 236-237).
- `:GONogo:EXECute`, `:GONogo:CLEar`, `:GONogo:FUNCtion`, `:GONogo:NGDefine`,
  `:GONogo:SOURce` — a pass/fail result depends on the template and tolerance,
  which must be stored with the result (advanced-features.md, manual
  pp. 238-243).
- `:TEMPlate:MODe`, `:TEMPlate:MAXimum`, `:TEMPlate:MINimum`,
  `:TEMPlate:TOLerance` — template saves write files or memory and follow the
  same no-overwrite rule (advanced-features.md, manual pp. 238-243).
- `:DATALOG:SOURce`, `:DATALOG:SAVe` — confirm storage and filename first;
  never overwrite (advanced-features.md, manual pp. 244-246).
- `:REMOTEDisk:IPADDress`, `:REMOTEDisk:PATHName`, `:REMOTEDisk:USERName`,
  `:REMOTEDisk:PASSWord`, `:REMOTEDisk:MOUNT`, `:REMOTEDisk:AUTOMount` —
  mounts a network share on the instrument; a mount does not imply SCPI file
  readback (advanced-features.md, manual pp. 247-249).

## Manual commands that this index did not previously list

Every row below is transcribed from the *GDS-1000B Series Programming Manual*
(Version 1.00, March 2015): `Command` is the manual's own spelling, `Type`
comes from the manual's Set/Query markers, `Parameters / range` quotes the
manual's Syntax and Parameter text, and `Source` is the PDF page of that
command's detail block. All rows are `documented` only — none was sent to an
instrument. Where a command has both a set and a query form they are recorded
in one row, the same convention the tables above use.

### Acquisition (manual pp. 40-46)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:ACQuire:FILTer:SOURce` | set/query | CH1 ~ CH4 Source channel | Syntax `:ACQuire:FILTer:SOURce {CH1\|CH2\|CH3\|CH4\|?}`; not exercised. | 43 |
| `:ACQuire:FILTer` | set/query | ON Filter on. OFF Filter off. | Syntax `:ACQuire:FILTer {ON\|OFF\|?}`; not exercised. | 44 |
| `:ACQuire:FILTer:FREQuency` | set/query | DEFault Sets the filter frequency to the default. <NRf> Manually sets the filter frequency. (1Hz ~ 500MHz) | Syntax `:ACQuire:FILTer:FREQuency {DEFault\|<NRf>\|?}`; not exercised. | 44 |
| `:ACQuire:FILTer:TRACking` | set/query | OFF Tracking off | Syntax `:ACQuire:FILTer:TRACking {ON\|OFF\|?}`; not exercised. | 44 |

### Autoscale (manual pp. 47-47)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:AUTORSET:MODe` | set/query | FITScreen Fit Screen mode ACPriority AC priority mode | Syntax `:AUTORSET:MODe {FITScreen \| ACPriority \| ?}`; not exercised. | 47 |

### Math (manual pp. 54-62)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MATH:DUAL:POSition` | set/query | <NRf> Vertical position Depends on the vertical scale (Unit/Div) <NR3> Returns the vertical position. | Syntax `:MATH:DUAL:POSition {<NRf> \| ? }`; not exercised. | 56 |
| `:MATH:DUAL:SCALe` | set/query | <NRf> Vertical scale <NR3> Returns the scale. | Syntax `:MATH:DUAL:SCALe {<NRf> \| ?}`; not exercised. | 56 |
| `:MATH:FFT:SOURce` | set/query | CH1~4 Channel 1 to 4 REF1~4 Reference waveform 1 to 4 Returns the FFT source. | Syntax `:MATH:FFT:SOURce { CH1 \| CH2 \| CH3 \| CH4 \| REF1 \| REF2 \| REF3 \| REF4 \| ? }`; not exercised. | 57 |
| `:MATH:FFT:WINDow` | set/query | — | Syntax `:MATH:FFT:WINDow {RECTangular\|HAMming\|HANning\|BLAckman\|?}`; not exercised. | 57 |
| `:MATH:FFT:POSition` | set/query | <NRf> Vertical position: -12e+0 to +12e+0 (12 units/division to +12 units/division.) <NR3> Returns the vertical position. | Syntax `MATH:FFT:POSition { <NRf> \| ? }`; not exercised. | 58 |
| `:MATH:FFT:SCALe` | set/query | <NRf> Vertical scale: Linear: 2e-3 to 1e+3 (2mV~1kV) dB: 1e+0 to 2e+1 (1~20dB) <NR3> Returns vertical scale. | Syntax `:MATH:FFT:SCALe {<NRf> \| ?}`; not exercised. | 58 |
| `:MATH:FFT:HORizontal:SCALe` | set/query | <NRf> Zoom scale: 1 to 20 times <NRf> Horizontal position: 0Hz ~ 999.9kHz <NR3> Returns zoom scale. <NR3> Returns the vertical position. | Syntax `:MATH:FFT:HORizonatal:SCALe {<NRf> \| ?} MATH:FFT:HORizontal:POSition { <NRf> \| ? }`; not exercised. | 59 |
| `MATH:FFT:HORizontal:POSition` | set/query | — | Syntax `MATH:FFT:HORizontal:POSition`; not exercised. | 59 |
| `:MATH:DEFine` | set/query | — | Syntax `:MATH:DEFine {<string>\| ?}`; not exercised. | 59 |
| `MATHVAR?` | query | <string> VAR1 <NR3>; VAR2 <NR3> | Syntax `MATHVAR?`; not exercised. | 60 |
| `MATHVAR:VAR<X>` | set/query | — | Syntax `MATHVAR:VAR<X>`; not exercised. | 61 |
| `:MATH:ADVanced:POSition` | set/query | <NRf> Vertical position: -12e+0 to +12e+0 (12 units/division to +12 units/division.) <NR3> Returns the vertical position. | Syntax `MATH:ADVanced:POSition { <NRf> \| ? }`; not exercised. | 61 |
| `:MATH:ADVanced:SCALe` | set/query | — | Syntax `:MATH:ADVanced:SCALe {<NRf> \| ?}`; not exercised. | 61 |

### Cursor (manual pp. 63-73)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CURSor:HUNI` | set/query | SEConds Sets the cursor units to time in seconds. HERtz Sets the cursor units to frequency. DEGrees Sets the cursor units to degrees. PERcent Sets the cursor units to percent. Returns… | Syntax `:CURSor:HUNI {SEConds \| HERtz \| DEGrees \| PERcent \| ?}`; not exercised. | 65 |
| `:CURSor:HUSE` | set | CURRent Uses the current horizontal position | Syntax `:CURSor:HUSE {CURRent}`; not exercised. | 65 |
| `:CURSor:VUNI` | set/query | BASE Sets the vertical cursor units the same as the scope units (V or A). PERcent Sets the displayed units to percent. Returns the unit type. | Syntax `:CURSor:VUNI {BASE \| PERcent \| ?}`; not exercised. | 66 |
| `:CURSor:VUSE` | set | CURRent Uses the current vertical position | Syntax `:CURSor:VUSE {CURRent}`; not exercised. | 66 |
| `:CURSor:DDT` | query | — | Syntax `:CURSor:DDT{?}`; not exercised. | 66 |
| `:CURSor:H1Position` | set/query | <NRf> Horizontal position Returns the cursor position. | Syntax `:CURSor:H1Position {<NRf>\| ?}`; not exercised. | 67 |
| `:CURSor:H2Position` | set/query | <NRf> Horizontal position Returns the cursor position. | Syntax `:CURSor:H2Position {<NRf> \| ?}`; not exercised. | 67 |
| `:CURSor:HDELta` | query | — | Syntax `:CURSor:HDELta{?} Return Parameter <NR3> Returns the distance between two horizontal cursors.`; not exercised. | 68 |
| `:CURSor:V1Position` | set/query | <NRf> Vertical position. Depends on the vertical scale. <NR3> Returns the cursor position. | Syntax `:CURSor:V1Position {<NRf>\| ?}`; not exercised. | 68 |
| `:CURSor:V2Position` | set/query | <NRf> Vertical position. Depends on the vertical scale. <NR3> Returns the cursor position. | Syntax `:CURSor:V2Position {<NRf> \| ?}`; not exercised. | 68 |
| `:CURSor:VDELta` | query | — | Syntax `:CURSor:VDELta{?} Return Parameter <NR3> Returns the difference between two vertical cursors.`; not exercised. | 69 |
| `:CURSor:XY:RECTangular:X:POSition<X>` | set/query | <X> Cursor 1, 2 <NRf> Horizontal position co-ordinates <NR3> Returns the cursor position. | Syntax `:CURSor:XY:RECTangular:X:POSition<X> {<NRf>\|?}`; not exercised. | 69 |
| `:CURSor:XY:RECTangular:X:DELta` | query | — | Syntax `:CURSor:XY:RECTangular:X:DELta{?} Return Parameter <NR3> Returns the delta value of cursor 1 and 2 as <NR3>.`; not exercised. | 69 |
| `:CURSor:XY:RECTangular:Y:POSition<X>` | set/query | <X> Cursor 1, 2 <NRf> Vertical position co-ordinates <NR3> Returns the cursor position. | Syntax `:CURSor:XY:RECTangular:Y:POSition<X> {<NRf>\|?}`; not exercised. | 70 |
| `:CURSor:XY:RECTangular:Y:DELta` | query | — | Syntax `:CURSor:XY:RECTangular:Y:DELta{?} Return Parameter <NR3> Returns the delta value of cursor 1 and 2 as <NR3>.`; not exercised. | 70 |
| `:CURSor:XY:POLar:RADIUS:POSition<X>` | query | — | Syntax `:CURSor:XY:POLar:RADIUS:POSition<X>`; not exercised. | 70 |
| `:CURSor:XY:POLar:RADIUS:DELta` | query | — | Syntax `:CURSor:XY:POLar:RADIUS:DELta{?} Return Parameter <NR3> Returns the radius delta.`; not exercised. | 71 |
| `:CURSor:XY:POLar:THETA:POSition<X>` | query | <X> 1, 2 (Cursor 1, Cursor 2) <NR3> Returns the polar angle. | Syntax `:CURSor:XY:POLar:THETA:POSition<X>{?}`; not exercised. | 71 |
| `:CURSor:XY:POLar:THETA:DELta` | query | — | Syntax `:CURSor:XY:POLar:THETA:DELta`; not exercised. | 71 |
| `:CURSor:XY:PRODuct:POSition<X>` | query | <X> 1, 2 (Cursor 1, Cursor 2) <NR3> Returns the product value of the Cursor1 or Cursor2. | Syntax `:CURSor:XY:PRODuct:POSition<X>{?}`; not exercised. | 72 |
| `:CURSor:XY:PRODuct:DELta` | query | <NR3> Returns the product delta. | Syntax `:CURSor:XY:PRODuct:DELta{?}`; not exercised. | 72 |
| `:CURSor:XY:RATio:POSition<X>` | query | — | Syntax `:CURSor:XY:RATio:POSition<X>`; not exercised. | 72 |
| `:CURSor:XY:RATio:DELta` | query | <NR3> Returns the ratio delta. | Syntax `:CURSor:XY:RATio:DELta{?}`; not exercised. | 73 |

### Display (manual pp. 74-77)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:DISPlay:INTensity:WAVEform` | set/query | `<NRf>` 0 to 100 (%); query returns `<NR3>` | Syntax `:DISPlay:INTensity:WAVEform {<NRf> \| ?}`; waveform intensity, not a measurement; not exercised. | 74 |
| `:DISPlay:INTensity:GRATicule` | set/query | <NRf> 1.0E+0 to 1.0E+2 (10% to 100%) Parameter <NR3> Returns the graticule intensity. | Syntax `:DISPlay:INTensity:GRATicule {<NRf> \| ?}`; not exercised. | 74 |
| `:DISPlay:INTensity:BACKLight` | set/query | <NRf> 1.0E+0 to 1.0E+2 (10% to 100%) Parameter <NR3> Returns the backlight intensity. | Syntax `:DISPlay:INTensity:BACKLight {<NRf> \| ?}`; not exercised. | 75 |
| `:DISPlay:INTensity:BACKLight:AUTODim:ENAble` | set/query | — | Syntax `:DISPlay:INTensity:BACKLight:AUTODim:ENAble`; not exercised. | 75 |
| `DISplay:INTENSITy:BACKLight:AUTODim:TIMe` | set/query | — | Syntax `DISplay:INTENSITy:BACKLight:AUTODim:TIMe`; not exercised. | 75 |
| `:DISPlay:PERSistence` | set/query | <NRf> 1.6E-2 ~ 4.0E+0. (16mS to 4S) Range(1.6E-2, 30E-3, 60E-3, 120E-2, 240E- 3, 500E-3, 750E-3, 1, 1.5,2, 4 INFInite Infinite persistence OFF No persistence Parameter <NR3> Returns the… | Syntax `:DISPlay:PERSistence { INFInite \| OFF \| <NRf> \| ? }`; not exercised. | 76 |
| `:DISPlay:GRATicule` | set/query | FULL CROSs FRAMe GRID Returns the graticule type. | Syntax `:DISPlay:GRATicule {FULL \| GRID\|CROSs \| FRAMe \| ?}`; not exercised. | 76 |

### Measure (manual pp. 81-105)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MEASUrement:REFLevel:PERCent:LOW` | set/query | <NRf> 0 - 100% Returns the low reference level. | Syntax `:MEASUrement:REFLevel:PERCent:LOW {<NRf> \| ?}`; not exercised. | 84 |
| `:MEASUrement:REFLevel:PERCent:MID` | set/query | <NRf> 0 - 100% Returns the mid reference level. | Syntax `:MEASUrement:REFLevel:PERCent:MID {<NRf> \| ?}`; not exercised. | 84 |
| `:MEASUrement:REFLevel:PERCent:MID2` | set/query | <NRf> 0 - 100% Returns the mid reference level of the second source. | Syntax `:MEASUrement:REFLevel:PERCent:MID2 {<NRf> \| ?}`; not exercised. | 84 |

### Reference (manual pp. 114-116)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:REF<X>:TIMebase:POSition` | set/query | — | Syntax `:REF<X>:TIMebase:POSition { <NRf> \| ?}`; not exercised. | 114 |
| `:REF<X>:TIMebase:SCALe` | set/query | <X> Reference waveform 1, 2, 3, 4. <NRf> Horizontal scale <NR3> Returns the reference waveform scale. | Syntax `:REF<X>:TIMebase:SCALe { <NRf> \| ?}`; not exercised. | 115 |
| `:REF<X>:OFFSet` | set/query | <X> Reference waveform 1, 2, 3, 4. <NRf> Vertical offset | Syntax `:REF<X>:OFFSet { <NRf> \| ?}`; not exercised. | 115 |
| `:REF<x>:SCALe` | set/query | <X> Reference waveform 1, 2, 3, 4. <NRf> Vertical scale <NR3> Returns the reference waveform vertical scale. | Syntax `:REF<X>:SCALe { <NRf> \| ? }`; not exercised. | 116 |

### Trigger (manual pp. 122-162)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:TRIGger:DELay:SLOP` | set/query | RISe Rising slope FALL Falling slope EITher Either rising or falling slope | Syntax `:TRIGger:DELay:SLOP {RISe \| FALL \| EITher \| ? }`; not exercised. | 128 |
| `:TRIGger:DELay:TYPe` | set/query | TIMe Sets the delay type to time. EVENt Sets the delay type to event. Returns the trigger delay type. | Syntax `:TRIGger:DELay:TYPE {TIMe \| EVENt \| ?}`; not exercised. | 129 |
| `:TRIGger:DELay:TIMe` | set/query | <NRf> Delay time (1.00E-8~1.00E+1) <NR3> Returns the delay time. | Syntax `:TRIGger:DELay:TIMe {<NRf> \| ?}`; not exercised. | 129 |
| `:TRIGger:DELay:EVENt` | set/query | — | Syntax `:TRIGger:DELay:EVENt`; not exercised. | 129 |
| `:TRIGger:DELay:LEVel` | set/query | <NRf> Delay trigger level <NR3> Returns the delay trigger. | Syntax `:TRIGger:DELay:LEVel {<NRf> \| ?}`; not exercised. | 130 |
| `:TRIGger:PULSEWidth:POLarity` | set/query | POSitive Positive polarity NEGative Negative polarity Returns the pulse width polarity. | Syntax `:TRIGger:PULSEWidth:POLarity {POSitive \| NEGative \| ?}`; not exercised. | 130 |
| `:TRIGger:RUNT:POLarity` | set/query | POSitive Positive polarity NEGative Negative polarity EITher Positive or negative polarity Returns the pulse runt trigger polarity. | Syntax `:TRIGger:RUNT:POLarity { POSitive \| NEGative \| EITher \| ? }`; not exercised. | 131 |
| `:TRIGger:RUNT:WHEn` | set/query | MOREthan > LESSthan < Equal = UNEQual ≠ Returns the pulse runt trigger condition. | Syntax `:TRIGger:RUNT:WHEn {MOREthan\| LESSthan \| EQual \| UNEQual \| ? }`; not exercised. | 131 |
| `:TRIGger:RUNT:TIMe` | set/query | <NRf> Pulse runt time (4nS to 10S) Parameter <NR3> Returns the runt time in seconds | Syntax `:TRIGger:RUNT:TIMe {<NRf> \| ? }`; not exercised. | 132 |
| `:TRIGger:RISEFall:SLOP` | set/query | RISe Rising slope FALL Falling slope EITher Either rising or falling slope Returns the rise & fall slope. | Syntax `:TRIGger:RISEFall:SLOP {RISe \| FALL \| EITher \| ?}`; not exercised. | 132 |
| `:TRIGger:RISEFall:WHEn` | set/query | — | Syntax `:TRIGger:RISEFall:WHEn {MOREthan \| LESSthan \| EQual \| UNEQual \| ? }`; not exercised. | 132 |
| `:TRIGger:RISEFall:TIMe` | set/query | <NRf> Rise and Fall time (4nS to 10S) Parameter <NR3> Returns the rise and fall time in seconds | Syntax `:TRIGger:RISEFall:TIMe {<NRf> \| ? }`; not exercised. | 133 |
| `:TRIGger:VIDeo:TYPe` | set/query | — | Syntax `:TRIGger:VIDeo:TYPE {NTSC \| PAL \| SECam \| EDTV480P \| EDTV576P \| HDTV720P \| HDTV1080I \| HDTV1080P \| ? }`; not exercised. | 133 |
| `:TRIGger:VIDeo:FIELd` | set/query | FIELD1 Trigger on field 1 FIELD2 Trigger on field 2 ALLFields Trigger on all fields ALLLines Trigger on all lines Returns the video trigger field. | Syntax `:TRIGger:VIDeo:FIELd { FIELD1 \| FIELD2 \| ALLFields \| ALLLines \| ? }`; not exercised. | 134 |
| `:TRIGger:VIDeo:LINe` | set/query | <NR1> Video line <NR3> Returns the video trigger line. | Syntax `:TRIGger:VIDeo:LINe {<NR1> \| ?}`; not exercised. | 135 |
| `:TRIGger:VIDeo:POLarity` | set/query | POSitive Positive polarity NEGative Negative polarity Returns the video trigger polarity. | Syntax `:TRIGger:VIDeo:POLarity { POSitive \| NEGative \| ? }`; not exercised. | 135 |
| `:TRIGger:PULSe:WHEn` | set/query | — | Syntax `:TRIGger:PULSe:WHEn { MOREthan \| LESSthan \| EQual \| UNEQual \| ? }`; not exercised. | 135 |
| `:TRIGger:PULSe:TIMe` | set/query | <NRf> Pulse width time (4ns~10s) <NR3> Returns the pulse width time in seconds. | Syntax `:TRIGger:PULSe:TIMe {<NRf> \| ?}`; not exercised. | 136 |
| `:TRIGger:TIMEOut:WHEn` | set/query | HIGH Signal is high. LOW Signal is low. EITher Signal is high or low. | Syntax `:TRIGger:TIMEOut:WHEn {HIGH\|LOW\|EITher\|?}`; not exercised. | 136 |
| `:TRIGger:TIMEOut:TIMER` | set/query | <NRf> Timeout time. (4nS to 10S). Returns the timeout time as <NR3>. | Syntax `:TRIGger:TIMEOut:TIMER {<NRf> \| ? }`; not exercised. | 137 |
| `:TRIGger:ALTernate` | set/query | OFF Alternate off ON Alternate on Returns the Alternate trigger status (ON, OFF). | Syntax `:TRIGger:ALTernate {OFF \| ON \|?}`; not exercised. | 137 |
| `:TRIGger:EXTERnal:PROBe:TYPe` | set/query | VOLTage Voltage CURRent Current Returns the probe type. | Syntax `:TRIGger:EXTERnal:PROBe:TYPe { VOLTage \| CURRent \|? }`; not exercised. | 138 |
| `:TRIGger:EXTERnal:PROBe:RATio` | set/query | <NRf> External probe attenuation factor. <NR3> Returns the probe attenuation factor. | Syntax `:TRIGger:EXTERnal:PROBe:RATio {<NRf> \| ?}`; not exercised. | 139 |
| `:TRIGger:BUS:TYPe` | query | 12C I2C mode SPI SPI mode UART UART mode CAN CAN mode LIN LIN mode | Syntax `:TRIGger:BUS:TYPe?`; not exercised. | 139 |
| `:TRIGger:BUS:THReshold:CH<x>` | set/query | — | Syntax `:TRIGger:BUS:THReshold:CH<X> {<NR3> \| ?} <X> CH1 ~ CH4 <NR3> Threshold level Return Parameter <NR3> Returns the threshold level`; not exercised. | 140 |
| `:TRIGger:BUS:B1:I2C:CONDition` | set/query | STARt Set Start as the I2C trigger condition. STOP Set Stop as the I2C trigger condition. REPEATstart Set Repeat of Start as the I2C trigger condition. ACKMISS Set Missing… | Syntax `:TRIGger:BUS:B1:I2C:CONDition {STARt \| STOP \| REPEATstart \| ACKMISS \| ADDRess \| DATA \| ADDRANDDATA \| ? }`; not exercised. | 140 |
| `:TRIGger:BUS:B1:I2C:ADDRess:MODe` | set/query | ADDR7 7 bit addressing ADDR10 10 bit addressing Parameter 0 7 bit addressing 1 10 bit addressing | Syntax `:TRIGger:BUS:B1:I2C:ADDRess:MODe {ADDR7 \| ADDR10 \| ? }`; not exercised. | 141 |
| `:TRIGger:BUS:B1:I2C:ADDRess:TYPe` | set/query | GENeralcall Set a general call address (0000 000 0). STARtbyte Set a start byte address. (0000 000 1) HSmode Set a high-speed mode address. (0000 1xx x) EEPROM Set an EEPROM address.… | Syntax `:TRIGger:BUS:B1:I2C:ADDRess:TYPe {GENeralcall \| STARtbyte \| HSmode \| EEPROM \| CBUS \| ?}`; not exercised. | 142 |
| `:TRIGger:BUS:B1:I2C:ADDRess:VALue` | set/query | — | Syntax `:TRIGger:BUS:B1:I2C:ADDRess:VALue {<string> \| ? }`; not exercised. | 142 |
| `:TRIGger:BUS:B1:I2C:ADDRess:DIRection` | set/query | READ Set read as the data direction. WRITE Set write as the data direction. NOCARE Set either as the data direction. Parameter Returns the direction (READ, WRITE, NOCARE). | Syntax `:TRIGger:BUS:B1:I2C:ADDRess:DIRection { READ \| WRITE \| NOCARE \| ? }`; not exercised. | 143 |
| `:TRIGger:BUS:B1:I2C:DATa:SIZe` | set/query | <NR1> Number of data bytes (1 to 5). <NR1> Returns the number of bytes. | Syntax `:TRIGger:BUS:B1:I2C:DATa:SIZe {<NR1> \| ? }`; not exercised. | 144 |
| `:TRIGger:BUS:B1:I2C:DATa:VALue` | set/query | — | Syntax `:TRIGger:BUS:B1:I2C:DATa:VALue {<string> \| ? }`; not exercised. | 144 |
| `:TRIGger:BUS:B1:UART:CONDition` | set/query | — | Syntax `:TRIGger:BUS:B1:UART:CONDition { RXSTArt \| RXDATA \| RXENDPacket \| TXSTArt \| TXDATA \| TXENDPacket \| TXPARItyerr \| RXPARItyerr \| ? }`; not exercised. | 145 |
| `:TRIGger:BUS:B1:UART:RX:DATa:SIZe` | set/query | <NR1> Number of bytes (1 to 10). <NR1> Returns the number of bytes. | Syntax `:TRIGger:BUS:B1:UART:RX:DATa:SIZe {<NR1> \| ?}`; not exercised. | 146 |
| `:TRIGger:BUS:B1:UART:RX:DATa:VALue` | set/query | <sting> The number of characters in the string depends on the data size setting. The string must be enclosed in double quotes, "string". x = don’t care 1 = binary 1 0 = binary 0… | Syntax `:TRIGger:BUS:B1:UART:RX:DATa:VALue {<string> \| ? }`; not exercised. | 147 |
| `:TRIGger:BUS:B1:UART:TX:DATa:SIZe` | set/query | — | Syntax `:TRIGger:BUS:B1:UART:TX:DATa:SIZe`; not exercised. | 147 |
| `:TRIGger:BUS:B1:UART:TX:DATa:VALue` | set/query | <sting> The number of characters in the string depends on the data size setting. The string must be enclosed in double quotes, "string". x = don’t care 1 = binary 1 0 = binary 0… | Syntax `:TRIGger:BUS:B1:UART:TX:DATa:VALue {<string> \| ? }`; not exercised. | 148 |
| `:TRIGger:BUS:B1:SPI:CONDition` | set/query | SS Set to trigger on the Slave Selection condition. MISO Set to trigger on the Master-In Slave-Out condition. MOSI Set to trigger on the Master-Out Slave-In condition. MISOMOSI Set to… | Syntax `:TRIGger:BUS:B1:SPI:CONDition {SS \| MISO \| MOSI \| MISOMOSI \| ? }`; not exercised. | 149 |
| `:TRIGger:BUS:B1:SPI:DATa:SIZe` | set/query | — | Syntax `:TRIGger:BUS:B1:SPI:DATa:SIZe`; not exercised. | 149 |
| `:TRIGger:BUS:B1:SPI:DATa:MISO:VALue` | set/query | <sting> The number of characters in the string depends on the data size setting. The string must be enclosed in double quotes, "string". x = don’t care 1 = binary 1 0 = binary 0… | Syntax `:TRIGger:BUS:B1:SPI:DATa:MISO:VALue {<string> \|?}`; not exercised. | 150 |
| `:TRIGger:BUS:B1:SPI:DATa:MOSI:VALue` | set/query | <sting> The number of characters in the string depends on the data size setting. The string must be enclosed in double quotes, "string". x = don’t care 1 = binary 1 0 = binary 0… | Syntax `:TRIGger:BUS:B1:SPI:DATa:MOSI:VALue {<string> \|?}`; not exercised. | 151 |
| `:TRIGger:BUS:B1:CAN:CONDition` | set/query | SOF Triggers on a start of frame FRAMEtype Triggers on the type of frame Identifier Triggers on a matching identifier DATA Triggers on matching data IDANDDATA Triggers on matching… | Syntax `:TRIGger:BUS:B1:CAN:CONDition {SOF\|FRAMEtype\|IDentifier\|DATA\|IDANDDATA\|EOF\| ACKMISS\|STUFFERR\|?}`; not exercised. | 152 |
| `:TRIGger:BUS:B1:CAN:FRAMEtype` | set/query | — | Syntax `:TRIGger:BUS:B1:CAN:FRAMEtype`; not exercised. | 152 |
| `:TRIGger:BUS:B1:CAN:IDentifier:MODe` | set/query | STANDard Standard addressing mode EXTended Extended addressing mode | Syntax `:TRIGger:BUS:B1:CAN:IDentifier:MODe {STANDard\|EXTended\|?}`; not exercised. | 153 |
| `:TRIGger:BUS:B1:CAN:IDentifier:VALue` | set/query | — | Syntax `:TRIGger:BUS:B1:CAN:IDentifier:VALue`; not exercised. | 153 |
| `:TRIGger:BUS:B1:CAN:IDentifier:DIRection` | set/query | READ Sets read as the data direction WRITE Sets write as the data direction NOCARE Sets either as the data direction | Syntax `:TRIGger:BUS:B1:CAN:IDentifier:DIRection {READ\|WRITE\|NOCARE\|?}`; not exercised. | 154 |
| `:TRIGger:BUS:B1:CAN:DATa:QUALifier` | set/query | LESSthan Triggers when the data is less than the qualifier value. MOREthan Triggers when the data is greater than the qualifier value. EQual Triggers when the data is equal to the… | Syntax `:TRIGger:BUS:B1:CAN:DATa:QUALifier {LESSthan\|MOREthan\|EQual\|UNEQual\|LESSEQual\|M OREEQual\|?}`; not exercised. | 155 |
| `:TRIGger:BUS:B1:CAN:DATa:SIZe` | set/query | <NR1> 1~8 (bytes) | Syntax `:TRIGger:BUS:B1:CAN:DATa:SIZe {<NR1>\|?}`; not exercised. | 156 |
| `:TRIGger:BUS:B1:CAN:DATa:VALue` | set/query | — | Syntax `:TRIGger:BUS:B1:CAN:DATa:VALue {<string>\|?}`; not exercised. | 156 |
| `:TRIGger:BUS:B1:LIN:CONDition` | set/query | — | Syntax `:TRIGger:BUS:B1:LIN:CONDition {SYNCField\|IDentifier\|DATA\|IDANDDATA\|WAKEup\| SLEEP\|ERRor\|?}`; not exercised. | 157 |
| `:TRIGger:BUS:B1:LIN:DATa:QUALifier` | set/query | — | Syntax `:TRIGger:BUS:B1:LIN:DATa:QUALifier {LESSthan\|MOREthan\|EQual\|UNEQual\|LESSEQual\|M OREEQual\|?}`; not exercised. | 158 |
| `:TRIGger:BUS:B1:LIN:DATa:SIZe` | set/query | <NR1> 1~8 (bytes) | Syntax `:TRIGger:BUS:B1:LIN:DATa:SIZe {<NR1>\|?}`; not exercised. | 159 |
| `:TRIGger:BUS:B1:LIN:DATa:VALue` | set/query | <string> The size of the string depends on the data size setting. The string must be enclosed in double quotes, “string”. String contents: x = don’t care 1 = binary 1 0 = binary | Syntax `:TRIGger:BUS:B1:LIN:DATa:VALue {<string>\|?}`; not exercised. | 160 |
| `:TRIGger:BUS:B1:LIN:ERRTYPE` | set/query | SYNC Sets the LIN error type to SYNC. PARIty Sets the LIN error type to parity. CHecksum Sets the LIN error type to checksum. | Syntax `:TRIGger:BUS:B1:LIN:ERRTYPE {SYNC\|PARIty\|CHecksum\|?}`; not exercised. | 161 |
| `:TRIGger:BUS:B1:LIN:IDentifier:VALue` | set/query | — | Syntax `:TRIGger:BUS:B1:LIN:IDentifier:VALue {<string>\|?}`; not exercised. | 161 |

### Bus decode (manual pp. 170-184)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:BUS1:INPut` | set/query | ANAlog Sets the source to the analog inputs Example1 :BUS1:INPut? >ANALOG Set | Syntax `:BUS1:INPut {ANAlog \| ?}`; not exercised. | 172 |
| `:BUS1:I2C:ADDRess:RWINClude` | set/query | OFF The R/W bit is not included. ON The R/W bit is included. 0 The R/W bit is not included. 1 The R/W bit is included. | Syntax `:BUS1:I2C:ADDRess:RWINClude { OFF \| ON \| ? }`; not exercised. | 172 |
| `:BUS1:I2C:SCLK:SOURce` | set/query | CH1 to CH4 Analog channels 1 ~ 4. | Syntax `:BUS1:I2C:SCLK:SOURce { CH1 \| CH2 \| CH3 \| CH4 \|?}`; not exercised. | 173 |
| `:BUS1:I2C:SDA:SOURce` | set/query | CH1 to CH4 Analog channels 1 ~ 4. | Syntax `:BUS1:I2C:SDA:SOURce { CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 173 |
| `:BUS1:UART:BITRate` | set/query | — | Syntax `:BUS1:UART:BITRate {<NR1>\| ? }`; not exercised. | 173 |
| `:BUS1:UART:DATABits` | set/query | 5 5 data bits in the UART frame. 6 6 data bits in the UART frame. 7 7 data bits in the UART frame. 8 8 data bits in the UART frame. | Syntax `:BUS1:UART:DATABits { 5 \| 6 \| 7 \| 8 \| 9 \| ? }`; not exercised. | 174 |
| `:BUS1:UART:PARIty` | set/query | <NR1> 0: None 1: Odd parity 2: Even parity | Syntax `:BUS1:UART:PARIty { <NR1> \| ? }`; not exercised. | 175 |
| `:BUS1:UART:PACKEt` | set/query | <NR1> 0: Off 1: On | Syntax `:BUS1:UART:PACKEt {<NR1> \| ? }`; not exercised. | 175 |
| `:BUS1:UART:EOFPAcket` | set/query | — | Syntax `:BUS1:UART:EOFPAcket <NR1>`; not exercised. | 175 |
| `:BUS1:UART:TX:SOURce` | set/query | OFF Off, no Tx source CH1 to CH4 Analog channels CH1 to CH4 | Syntax `:BUS1:UART:TX:SOURce { OFF \| CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 176 |
| `:BUS1:UART:RX:SOURce` | set/query | OFF Off, no Rx source CH1 to CH4 Analog channels CH1 to CH4 | Syntax `:BUS1:UART:RX:SOURce { OFF \| CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 176 |
| `:BUS1:SPI:SCLK:POLARity` | set/query | FALL Sets the polarity to falling edge. RISE Sets the polarity to rising edge. | Syntax `:BUS1:SPI:SCLK:POLARity { FALL \| RISE \| ? }`; not exercised. | 177 |
| `:BUS1:SPI:SS:POLARity` | set/query | LOW Active low polarity HIGH Active high polarity | Syntax `:BUS1:SPI:SS:POLARity { LOW \| HIGH \| ? }`; not exercised. | 177 |
| `:BUS1:SPI:WORDSize` | set/query | <NR1> Bits per word (4~32) | Syntax `:BUS1:SPI:WORDSize {<NR1> \| ? }`; not exercised. | 177 |
| `:BUS1:SPI:BITORder` | set/query | <NR1> 0: MSB bit first 1: LSB bit first | Syntax `:BUS1:SPI:BITORder {<NR1> \| ? }`; not exercised. | 178 |
| `:BUS1:SPI:SCLK:SOURce` | set/query | CH1 to CH4 Analog channels CH1 to CH4 | Syntax `:BUS1:SPI:SCLK:SOURce { CH1 \| CH2 \| CH3 \| CH4 \|?}`; not exercised. | 178 |
| `:BUS1:SPI:SS:SOURce` | set/query | CH1 to CH4 Analog channels CH1 to CH4 | Syntax `:BUS1:SPI:SS:SOURce { CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 178 |
| `:BUS1:SPI:MOSI:SOURce` | set/query | CH1 to CH4 Analog channels CH1 to CH4 OFF No MOSI source. | Syntax `:BUS1:SPI:MOSI:SOURce { OFF \| CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 179 |
| `:BUS1:SPI:MISO:SOURce` | set/query | CH1 to CH4 Analog channels CH1 to CH4 OFF No MISO source. | Syntax `:BUS1:SPI:MISO:SOURce { OFF \| CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 179 |
| `:BUS1:DISplay:FORMAt` | set/query | BINary Binary format HEXadecimal Hexadecimal format | Syntax `:BUS1:DISplay:FORMAt { BINary \| HEXadecimal \| ASCII \| ? }`; not exercised. | 179 |
| `:BUS1:CAN:SOURce` | set/query | CH1 ~ CH4 Analog channel source | Syntax `:BUS1:CAN:SOURce { CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 180 |
| `:BUS1:CAN:PROBe` | set/query | CANH CAN-High CANL CAN-Low TX Transmit RX Receive | Syntax `:BUS1:CAN:PROBe {CANH \| CANL \| TX \| RX \| ? }`; not exercised. | 180 |
| `:BUS1:CAN:SAMPLEpoint` | query | — | Syntax `:BUS1:CAN:SAMPLEpoint? Return Parameter Returns the sample point of the CAN bus as a percentage of the bit time.`; not exercised. | 181 |
| `:BUS1:CAN:BITRate` | set/query | — | Syntax `:BUS1:CAN:BITRate {RATE10K\|RATE20K\|RATE50K\|RATE125K\|RATE250K\| RATE500K\|RATE800K\|RATE1M \| ?}`; not exercised. | 181 |
| `:BUS1:LIN:BITRate` | set/query | <NR1> 1200, 2400, 4800, 9600, 10417, 19200 | Syntax `:BUS1:LIN:BITRate {<NR1> \| ?}`; not exercised. | 182 |
| `:BUS1:LIN:IDFORmat` | set/query | NOPARity Don’t include parity bits with Id. PARIty Include parity bits with Id. | Syntax `:BUS1:LIN:IDFORmat {NOPARity\|PARIty\|?}`; not exercised. | 182 |
| `:BUS1:LIN:POLARity` | set/query | NORMal Normal LIN polarity INVerted Inverted LIN polarity | Syntax `:BUS1:LIN:POLARity {NORMal\|INVerted\|?}`; not exercised. | 183 |
| `:BUS1:LIN:SAMPLEpoint` | query | — | Syntax `:BUS1:LIN:SAMPLEpoint? Return Parameter Returns the sample point of the LIN bus as a percentage.`; not exercised. | 183 |
| `:BUS1:LIN:SOURce` | set/query | CH1 ~ CH4 Analog channel source | Syntax `:BUS1:LIN:SOURce {CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 183 |
| `:BUS1:LIN:STANDard` | set/query | V1X Lin standard version 1.x V2X Lin standard version 2.x BOTH Both standards | Syntax `:BUS1:LIN:STANDard {V1X\|V2X\|BOTH\|?}`; not exercised. | 184 |

### Mark (manual pp. 185-186)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MARK:CREATE` | set | CURRent Creates a mark at the current position ALL Creates a mark for all the events. | Syntax `:MARK:CREATE { CURRent \| ALL }`; not exercised. | 185 |
| `:MARK:DELEte` | set | CURRent Deletes the current mark ALL Deletes all the marks | Syntax `:MARK:DELEte { CURRent \| ALL }`; not exercised. | 186 |

### Search (manual pp. 187-220)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:VALue` | set/query | `<string>` pattern such as `"1x1x0101"` | Syntax `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:VALue {<string> \| ? }`; not exercised. | 204 |
| `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:VALue` | set/query | `<string>` pattern | Syntax `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:VALue {<string> \| ? }`; not exercised. | 206 |
| `:SEARCH:TRIGger:BUS:B1:SPI:DATa:MISO:VALue` | set/query | `<string>` pattern | Syntax `:SEARCH:TRIGger:BUS:B1:SPI:DATa:MISO:VALue {<string> \| ? }`; not exercised. | 207 |
| `:SEARCH:TRIGger:BUS:B1:SPI:DATa:MOSI:VALue` | set/query | `<string>` pattern | Syntax `:SEARCH:TRIGger:BUS:B1:SPI:DATa:MOSI:VALue {<string> \| ? }`; not exercised. | 208 |
| `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:MODe` | set/query | `{STANDard\|EXTended}` | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:MODe {STANDard\|EXTended\|?}`; not exercised. | 210 |
| `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:DIRection` | set/query | `{READ\|WRITE\|NOCARE}` | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:DIRection {READ\|WRITE\|NOCARE\|?}`; not exercised. | 211 |
| `:SEARCH:TRIGger:TYPe` | set/query | — | Syntax `:SEARCH:TRIGger:TYPe { EDGe \| PULSEWidth \| RUNT \| RISEFall \| FFTPeak \| BUS \| ? }`; not exercised. | 189 |
| `:SEARCH:TRIGger:SOURce` | set/query | CH1 to CH4 Channel 1 to Channel 4 | Syntax `:SEARCH:TRIGger:SOURce {CH1 \| CH2 \| CH3 \| CH4 \|?}`; not exercised. | 190 |
| `:SEARCH:TRIGger:EDGE:SLOP` | set/query | RISe Rising slope FALL Falling slope EITher Either rising or falling slope Returns the trigger slope. | Syntax `:SEARCH:TRIGger:EDGe:SLOP { RISe \| FALL \| EITher \|?}`; not exercised. | 190 |
| `:SEARCH:TRIGger:LEVel` | set/query | <NRf> Trigger level value TTL Sets the search trigger level to TTL. ECL Sets the search trigger level to ECL. SETTO50 Sets the search trigger level to the User level (50% by default).… | Syntax `:SEARCH:TRIGger:LEVel {TTL \| ECL\| SETTO50 \| <NRf> \| ?}`; not exercised. | 191 |
| `:SEARCH:TRIGger:HLEVel` | set/query | <NRf> High level value. <NR3> Returns the high level search trigger. | Syntax `:SEARCH:TRIGger:HLEVel { <NRf> \| ?}`; not exercised. | 191 |
| `:SEARCH:TRIGger:LLEVel` | set/query | <NRf> Low level value. <NR3> Returns the low level. | Syntax `:SEARCH:TRIGger:LLEVel { <NRf> \| ?}`; not exercised. | 192 |
| `:SEARCH:TRIGger:PULSEWidth:POLarity` | set/query | POSitive Positive polarity NEGative Negative polarity Returns the pulse width polarity. | Syntax `:SEARCH:TRIGger:PULSEWidth:POLarity {POSitive \| NEGative \| ?}`; not exercised. | 192 |
| `:SEARCH:TRIGger:RUNT:POLarity` | set/query | POSitive Positive polarity NEGative Negative polarity EITher Positive or negative polarity Returns the pulse runt search trigger polarity. | Syntax `:SEARCH:TRIGger:RUNT:POLarity {POSitive \| NEGative \| EITher \| ?}`; not exercised. | 193 |
| `:SEARCH:TRIGger:RISEFall:SLOP` | set/query | RISe Rising slope FALL Falling slope EITher Either rising or falling slope Returns the rise & fall slope. | Syntax `:SEARCH:TRIGger:RISEFall:SLOP { RISe \| FALL \| EITher \| ? }`; not exercised. | 193 |
| `:SEARCH:TRIGger:PULSe:WHEn` | set/query | MOREthan > LESSthan < EQual = UNEQual ≠ Returns the pulse width search trigger conditions. | Syntax `:SEARCH:TRIGger:PULSe:WHEn {MOREthan \| LESSthan \| EQual \| UNEQual \| ?}`; not exercised. | 194 |
| `:SEARCH:TRIGger:PULSe:TIMe` | set/query | <NRf> Pulse width time (4ns~10s) <NR3> Returns the pulse width time in seconds. | Syntax `:SEARCH:TRIGger:PULSe:TIMe {<NRf> \| ?}`; not exercised. | 194 |
| `:SEARCH:TRIGger:RUNT:WHEn` | set/query | MOREthan > LESSthan < EQual = UNEQual ≠ Returns the pulse runt search trigger conditions. | Syntax `:SEARCH:TRIGger:RUNT:WHEn {MOREthan \| LESSthan \| EQual \| UNEQual \| ? }`; not exercised. | 195 |
| `:SEARCH:TRIGger:RUNT:TIMe` | set/query | <NRf> Pulse runt time (4nS to 10S) Parameter <NR3> Returns the runt time in seconds. | Syntax `:SEARCH:TRIGger:RUNT:TIMe {<NRf> \| ? }`; not exercised. | 195 |
| `:SEARCH:TRIGger:RISEFall:WHEn` | set/query | MOREthan > LESSthan < Equal = UNEQual ≠ Returns the rise and fall search trigger condition. | Syntax `:SEARCH:TRIGger:RISEFall:WHEn {MOREthan \| LESSthan \| EQual \| UNEQual \|? }`; not exercised. | 196 |
| `:SEARCH:TRIGger:RISEFall:TIMe` | set/query | <NRf> Rise and Fall time (4nS to 10S) Parameter <NR3> Returns the rise and fall time in seconds. | Syntax `:SEARCH:TRIGger:RISEFall:TIMe {<NRf> \| ? }`; not exercised. | 196 |
| `:SEARCH:TRIGger:BUS:TYPe` | query | 12C I2C mode SPI SPI mode UART UART mode CAN CAN mode LIN LIN mode | Syntax `:SEARCH:TRIGger:BUS:TYPe?`; not exercised. | 197 |
| `:SEARCH:TRIGger:BUS:B1:I2C:CONDition` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:CONDition {STARt \| STOP \| REPEATstart \| ACKMISS \| ADDRess \| DATA \| ADDRANDDATA \| ? }`; not exercised. | 197 |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:MODe` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:MODe`; not exercised. | 198 |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:TYPe` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:TYPe`; not exercised. | 199 |
| `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:VALue` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:ADDRess:VALue`; not exercised. | 199 |
| `:SEARCH:TRIGger:BUS:B1:I2C:DATa:SIZe` | set/query | <NR1> Number of data bytes (1 to 5). <NR1> Returns the number of bytes. | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:DATa:SIZe {<NR1> \| ? }`; not exercised. | 201 |
| `:SEARCH:TRIGger:BUS:B1:I2C:DATa:VALue` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:I2C:DATa:VALue {<string> \| ? }`; not exercised. | 201 |
| `:SEARCH:TRIGger:BUS:B1:UART:CONDition` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:UART:CONDition`; not exercised. | 202 |
| `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:SIZe` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:UART:RX:DATa:SIZe`; not exercised. | 203 |
| `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:SIZe` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:UART:TX:DATa:SIZe`; not exercised. | 204 |
| `:SEARCH:TRIGger:BUS:B1:SPI:CONDition` | set/query | SS Set to trigger on the Slave Selection condition. MISO Set to trigger on the Master-In Slave-Out condition. MOSI Set to trigger on the Master-Out Slave-In condition. MISOMOSI Set to… | Syntax `:SEARCH:TRIGger:BUS:B1:SPI:CONDition {SS \| MISO \| MOSI \| MISOMOSI \| ? }`; not exercised. | 206 |
| `:SEARCH:TRIGger:BUS:B1:SPI:DATa:SIZe` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:SPI:DATa:SIZe`; not exercised. | 206 |
| `:SEARCH:TRIGger:BUS:B1:CAN:CONDition` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:CONDition`; not exercised. | 208 |
| `:SEARCH:TRIGger:BUS:B1:CAN:FRAMEtype` | set/query | — | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:FRAMEtype {DATA\|REMote\|ERRor\|OVERLoad\|?}`; not exercised. | 209 |
| `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:VALue` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:IDentifier:VALue`; not exercised. | 210 |
| `:SEARCH:TRIGger:BUS:B1:CAN:DATa:QUALifier` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:DATa:QUALifier`; not exercised. | 212 |
| `:SEARCH:TRIGger:BUS:B1:CAN:DATa:SIZe` | set/query | <NR1> 1~8 (bytes) | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:DATa:SIZe {<NR1>\|?}`; not exercised. | 213 |
| `:SEARCH:TRIGger:BUS:B1:CAN:DATa:VALue` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:CAN:DATa:VALue`; not exercised. | 213 |
| `:SEARCH:TRIGger:BUS:B1:LIN:CONDition` | set/query | SYNCField Sets the LIN search trigger condition to the sync field. IDentifier Sets the LIN search trigger condition to identifier field. DATA Sets the LIN search trigger condition to the… | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:CONDition {SYNCField\|IDentifier\|DATA\|IDANDDATA\|WAKEup\|SL EEP\|ERRor\|?}`; not exercised. | 214 |
| `:SEARCH:TRIGger:BUS:B1:LIN:DATa:QUALifier` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:DATa:QUALifier`; not exercised. | 215 |
| `:SEARCH:TRIGger:BUS:B1:LIN:DATa:SIZe` | set/query | <NR1> 1~8 (bytes) | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:DATa:SIZe {<NR1>\|?}`; not exercised. | 216 |
| `:SEARCH:TRIGger:BUS:B1:LIN:DATa:VALue` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:DATa:VALue`; not exercised. | 216 |
| `:SEARCH:TRIGger:BUS:B1:LIN:ERRTYPE` | set/query | SYNC Sets the LIN error type to SYNC. PARIty Sets the LIN error type to parity. CHecksum Sets the LIN error type to checksum. | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:ERRTYPE {SYNC\|PARIty\|CHecksum\|?}`; not exercised. | 217 |
| `:SEARCH:TRIGger:BUS:B1:LIN:IDentifier:VALue` | set | — | Syntax `:SEARCH:TRIGger:BUS:B1:LIN:IDentifier:VALue`; not exercised. | 217 |
| `:SEARCH:FFTPeak:METHod` | set/query | — | Syntax `:SEARCH:FFTPeak:METHod`; not exercised. | 218 |
| `:SEARCH:FFTPeak:METHod:MPEak` | set/query | <NR1> Active peak number. <NR3> Frequency of the active peak. | Syntax `:SEARCH:FFTPeak:METHod:MPEak {<NR1> \| ?}`; not exercised. | 219 |
| `:SEARCH:FFTPeak:SINFo` | set/query | — | Syntax `:SEARCH:FFTPeak:SINFo {MARK \| PEAK \| ?}`; not exercised. | 219 |

### Label (manual pp. 221-226)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CHANnel<X>:LABel:DISPlay` | set/query | <X> Channel 1, 2, 3, 4 OFF Turns the file label off for the selected channel. ON Turns the file label on for the selected channel. Returns the status of the file label for the selected… | Syntax `:CHANnel<X>:LABel:DISPlay { OFF \| ON \| ? }`; not exercised. | 222 |
| `:REF<X>:LABel` | set/query | — | Syntax `:REF<X>:LABel {<string> \| ?}`; not exercised. | 222 |
| `:REF<X>:LABel:DISPlay` | set/query | <X> Reference waveform 1, 2, 3, 4 OFF Turns the file label off for the selected reference waveform. ON Turns the file label on for the selected reference waveform. Returns the status of… | Syntax `:REF<X>:LABel:DISPlay { OFF \| ON \| ? }`; not exercised. | 223 |
| `:BUS1:LABel` | set/query | <string> The string must be no more than 8 characters and only contain alphanumeric characters in addition to period, dash and underscore characters. The string must be enclosed in… | Syntax `:BUS1:LABel {<string> \| ?}`; not exercised. | 224 |
| `:BUS1:LABel:DISPlay` | set/query | — | Syntax `:BUS1:LABel:DISPlay { OFF \| ON \| ? }`; not exercised. | 224 |
| `:SET<X>:LABel` | set/query | <X> Setup number 1 to 20 <string> The string must be no more than 8 characters and only contain alphanumeric characters in addition to period, dash and underscore characters. The string… | Syntax `:SET<X>:LABel {<string> \| ?}`; not exercised. | 225 |

### Segment (manual pp. 227-235)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SEGMents:DISPALL` | set/query | OFF Turns the display all function off. ON Turns the display all function on. Example1 :SEGMents:DISPALL ON Turns the display all function on. Set | Syntax `:SEGMents:DISPALL {OFF\|ON\|?}`; not exercised. | 229 |
| `:SEGMents:MEASure:MODe` | set/query | — | Syntax `:SEGMents:MEASure:MODe {OFF\|PLOT\|TABle\|?}`; not exercised. | 229 |
| `:SEGMents:MEASure:PLOT:SOURce` | set/query | — | Syntax `:SEGMents:MEASure:PLOT:SOURce {<NR1> \| ? }`; not exercised. | 230 |
| `:SEGMents:MEASure:PLOT:DIVide` | set/query | — | Syntax `:SEGMents:MEASure:PLOT:DIVide {<NR1> \| ? }`; not exercised. | 230 |
| `:SEGMents:MEASure:PLOT:SELect` | set | — | Syntax `:SEGMents:MEASure:PLOT:SELect`; not exercised. | 231 |
| `:SEGMents:MEASure:PLOT:RESults` | set | <NR1> 1~8 (Automatic measurement item 1~8) Example1 :SEGMents:MEASure:PLOT:SOURce 1 Sets the source as auto measurement item 1. Set | Syntax `:SEGMents:MEASure:PLOT:RESults`; not exercised. | 231 |
| `:SEGMents:MEASure:TABle:SOURce` | set/query | — | Syntax `:SEGMents:MEASure:TABle:SOURce {CH1 \| CH2 \| CH3\| CH4 \| ? }`; not exercised. | 232 |
| `:SEGMents:MEASure:TABle:SELect` | set/query | — | Syntax `:SEGMents:MEASure:TABle:SELect {<NR1> \| ? }`; not exercised. | 232 |
| `:SEGMents:MEASure:TABle:LIST` | set | CH1~CH4 Channel 1 to 4 Example1 :SEGMents:MEASure:TABle:SOURce CH1 Sets the source to CH1. Set | Syntax `:SEGMents:MEASure:TABle:LIST`; not exercised. | 233 |
| `:SEGMents:MEASure:TABle:SAVe` | set | — | Syntax `:SEGMents:MEASure:TABle:SAVe`; not exercised. | 233 |
| `:SEGMents:SAVe` | set | — | Syntax `:SEGMents:SAVe`; not exercised. | 233 |
| `:SEGMents:SAVe:SOURce` | set/query | CH1~CH4 Channel 1 to 4. | Syntax `:SEGMents:SAVe:SOURce {CH1 \| CH2 \| CH3 \| CH4 \| ? }`; not exercised. | 234 |
| `:SEGMents:SAVe:SELect:STARt` | set/query | SETTOMIN Sets the starting segment to min segment. SETTOMAX Sets the starting segment to the max segment. <NR1> Sets the starting segment to 1~29000. | Syntax `:SEGMents:SAVe:SELect:STARt {SETTOMIN \| SETTOMAX \| <NR1> \| ? }`; not exercised. | 234 |
| `:SEGMents:SAVe:SELect:END` | set | — | Syntax `:SEGMents:SAVe:SELect:END`; not exercised. | 235 |

### DVM (manual pp. 236-237)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:DVM:MODe` | set/query | ACRMS Sets the mode to AC RMS DC Sets the mode to DC DCRMS Sets the mode to DC RMS DUTY Sets the mode to AC Duty FREQuency Sets the mode to AC frequency | Syntax `:DVM:MODe {ACRMS\|DC\|DCRMS\|DUTY\| FREQuency\|?}`; not exercised. | 237 |

### Go-NoGo (manual pp. 238-243)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:GONogo:FUNCtion` | set | — | Syntax `:GONogo:FUNCtion`; not exercised. | 239 |
| `:GONogo:NGDefine` | set/query | EXITs Sets the NoGo condition to when the Parameter input signal exceeds the limit boundary. ENTers Sets the NoGo condition to when the input signal stays within the limit boundary. | Syntax `:GONogo:NGDefine {EXITs\|ENTers\|?}`; not exercised. | 239 |
| `:GONogo:SOURce` | set/query | CH1~CH4 Parameter | Syntax `:GONogo:SOURce {CH1\|CH2\|CH3\|CH4\|?}`; not exercised. | 240 |
| `:GONogo:SCRipt` | set | ON Turns Go/NoGo APP on. Parameter OFF Turns the Go/NoGo APP off. | Syntax `:GONogo:SCRipt {OFF \| ON \| ?}`; not exercised. | 240 |
| `:TEMPlate:MODe` | set/query | MAXimum Maximum template Parameter MINimum Minimum template AUTO Auto template | Syntax `:TEMPlate:MODe {MAXimum\|MINimum\|AUTO\|?}`; not exercised. | 241 |
| `:TEMPlate:MAXimum` | set/query | REF1 Reference one Parameter W1~W20 Waveform memory 1 to | Syntax `:TEMPlate:MAXimum {REF1\|W1~W20\|?}`; not exercised. | 241 |
| `:TEMPlate:MINimum` | set/query | REF2 Reference two Parameter W1~W20 Waveform memory 1 to | Syntax `:TEMPlate:MINimum {REF2\|W1~W20\|?}`; not exercised. | 241 |
| `:TEMPlate:POSition:MAXimum` | set/query | <NR2> Desired template position (-12.0 ~ +12.0 divisions) Returns the position in the following format: “<NR2>Div” | Syntax `:TEMPlate:POSition:MAXimum {<NR2>\|?}`; not exercised. | 242 |
| `:TEMPlate:POSition:MINimum` | set/query | <NR2> Desired template position (-12.0 ~ +12.0 divisions) Returns the position in the following format: “<NR2>Div” | Syntax `:TEMPlate:POSition:MINimum {<NR2>\|?}`; not exercised. | 242 |
| `:TEMPlate:SAVe:MAXimum` | set | — | Syntax `:TEMPlate:SAVe:MAXimum`; not exercised. | 242 |
| `:TEMPlate:SAVe:MINimum` | set | — | Syntax `:TEMPlate:SAVe:MINimum Set`; not exercised. | 243 |
| `:TEMPlate:TOLerance` | set/query | <NR2> The auto tolerance range (0.4% ~ 40%) Parameter | Syntax `:TEMPlate:TOLerance {<NR2>\|?}`; not exercised. | 243 |
| `:TEMPlate:SAVe:AUTo` | set | — | Syntax `:TEMPlate:SAVe:AUTo`; not exercised. | 243 |

### Data logging (manual pp. 244-246)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:DATALOG:SAVe` | set/query | — | Syntax `:DATALOG:SAVe {IMAGe\|WAVEform\|?}`; not exercised. | 245 |

### Remote disk (manual pp. 247-249)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:REMOTEDisk:USERName` | set/query | — | Syntax `:REMOTEDisk:USERName {<string> \| ? }`; not exercised. | 247 |
| `:REMOTEDisk:PASSWord` | set/query | <string> Username password enclosed in double quotes eg., “Password”. | Syntax `:REMOTEDisk:PASSWord {<string> \| ? }`; not exercised. | 248 |
| `:REMOTEDisk:MOUNT` | set/query | OFF Unmount remote disk ON Mount remote disk | Syntax `:REMOTEDisk:MOUNT { OFF \| ON \| ? }`; not exercised. | 248 |
| `:REMOTEDisk:AUTOMount` | set/query | OFF Don’t mount the remote disk at start up. ON Automatically mount the remote disk on start up. | Syntax `:REMOTEDisk:AUTOMount { OFF \| ON \| ? }`; not exercised. | 249 |

## Manual defects

- PDF p. 237 prints a heading `:DVD:MODe` whose body is the `:DVM:MODe`
  command (`:DVM:MODe {ACRMS|DC|DCRMS|DUTY|FREQuency|?}`). `:DVD:` does not
  exist; only `:DVM:MODe` is indexed. Treat the `:DVD:` heading as a manual
  typo and do not send it.

## Coverage gaps

- **Two provenance tiers.** The sections above this point were a merge of
  `SKILL.md`, the eight task references, and the script command strings, so they
  can carry values the Skill itself verified. The section *Manual commands that
  this index did not previously list* was transcribed from the manual's command
  details only; its `Parameters / range` cell quotes the manual and is not
  cross-checked against any Skill document or script.
- **Transcription, not verification.** Three hundred and forty-three command
  forms are enumerated, but the added rows were read out of the manual's text,
  so a syntax line can still be a printing error (for example the `12C`/`I2C`
  duplication on manual p. 197 is quoted as printed). Treat every added row as
  `documented` and nothing more.
- **Parameter detail depth.** The added rows quote the Syntax and Parameter
  lines; where a command depends on defaults, coupled settings, or front-panel
  state that the manual describes in prose (trigger holdoff behaviour, segment
  measurement slots, template tolerances), only the enumerable part is recorded.
  The prose still has to be read before use.
- **Slot index semantics.** `:MEASUrement:MEAS<X>:TYPe` values and the
  `SOURCE<X>` index pairing are taken verbatim from `measurements.md`; how the
  manual numbers slots versus sources (pp. 106-113) is not independently
  confirmed.
- **Setter-only entries.** Where a source shows only a setter, the row is typed
  `set` (or `event`); this table does not claim a query form exists for it.
- **Waveform voltage calibration** remains `UNVERIFIED`: `(code / 25) *
  Vertical Scale` is documented but the manual's own example is internally
  inconsistent (pp. 42-43). No command in this Skill establishes a transfer
  function.
- **USB CDC serial defaults** are undocumented; `115200 8N1` is an assumption of
  `scripts/gds1000b_session.py`, and no command to configure or read the USB
  framing is recorded.
- **Ethernet.** Only `:ETHERnet:DHCP` is recorded. Its parameters and ranges are
  not stated in this Skill; the socket-server enable path is a front-panel action
  with no recorded SCPI command. Availability is limited to GDS-1054B/GDS-1074B/
  GDS-1104B, and the DHCP command only to GDS-1074B/GDS-1104B.
- **Model gating.** Channel-count (2 vs 4) and EXT availability are enforced only
  by human/`*IDN?` checks; no recorded command reports EXT support.
- **Optional licensed features.** Bus decode, bus trigger, digital filter, and
  some advanced features are conditional on installed options; no recorded
  command confirms option installation.
- **`*LRN?` response fields** are not parsed by this Skill, so the setup string
  is opaque evidence and cannot be used to reconstruct individual settings.
- **No hardware verification** exists for any command in this table; every entry
  is `documented` only, and acceptance of each sequence by real firmware is
  unproven.
