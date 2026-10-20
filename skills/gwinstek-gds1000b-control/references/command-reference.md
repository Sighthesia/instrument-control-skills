# Command Reference (Fallback Index)

This page is a fallback index of every SCPI/IEEE-488.2 command already recorded
in this Skill. Read it only when the task-specific reference and the scripts do
not answer the question. Its scope is exclusively what this Skill already
records; the authoritative complete command set is the *GDS-1000B Series
Programming Manual*, Version 1.00, March 2015, which is not copied here. Any
command absent from this index must be verified against the manual and labelled
`documented` before use. The safety rules in `SKILL.md` still apply: no routine
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

## Coverage gaps

- **No command enumeration existed before this file.** Everything here is a
  merge of `SKILL.md`, the eight task references, and the script command
  strings; the manual itself was not read to build it, so commands the Skill
  never used or mentioned are absent by design.
- **Partial mnemonics.** The families listed under each advanced table (display
  settings, `:MATH:FFT:WINDow`, `:MATH:DEFine`, `:ACQuire:FILTer*`, cursor unit
  and XY, `:BUS1:*` parameters, `:SEGMents:SAVe`/`:SEGMents:MEASure:*`,
  `:GONogo:*`, `:TEMPlate:*`, `:DATALOG:*`, `:REMOTEDisk:*`) are recorded only as
  mnemonics or families. Their exact syntax, parameter ranges, and defaults must
  be verified against the manual and labelled `documented` before use.
- **Trigger qualifiers.** Delay, pulse-width, runt, rise-fall, video, timeout,
  and bus trigger sub-parameters (manual pp. 122-162) are not enumerated.
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
