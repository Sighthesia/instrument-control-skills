# Command Reference (Fallback Index)

这是一份**兜底索引**：只有当按目标加载的任务参考文档和脚本仍无法回答某个命令问题时才加载它；日常应按 `SKILL.md` 的“Progressive Query Reference”优先读取对应任务页，不要一开始就全表通读。
正文各表只记录本 Skill 内（`SKILL.md`、`references/*.md`、`scripts/*.py`）**已经用过或讨论过**的命令；手册里的其余命令集中列在文末「附录：手册命令清单」中（命令名与 PDF 页码取自手册，参数未抄录）。权威来源仍是厂商编程手册 `SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`（仓库内 `ref/`）。
表中没有出现的任何命令，必须先对照手册核实并标注为 `documented` 后才能使用；`SKILL.md` 的安全规则（禁止 `ARM`、`Ready -> Stop`、Stop 后冻结命令集、二进制完整性）始终优先于本表。
“Source”列给出记录该命令的文件；括号内页码只在原文明确给出时才有；原文未给出页码的条目在 Notes 中注明“手册未给出独立页码”或“需对手册核实”，使用前应回到手册核对。

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | 返回厂商、型号、序列号、固件；任何型号相关命令之前必须先执行并保存结果。手册印刷 pp. 13-14；discovery 发送 `*IDN?\n`。 | signal-discovery-and-measurement.md (manual pp. 13-14)<br>connection-and-storage.md<br>SKILL.md<br>scripts/discover_scope.py<br>scripts/scope_protocol.py |
| `*OPC?` | query | — | 挂起操作完成时返回 `1`；不能证明发生过触发。等待设置写入生效时可作为同步点。手册印刷 pp. 13-14。 | signal-discovery-and-measurement.md (manual pp. 13-14) |
| `SYSTem:ERRor?` / `SYST:ERR?` | query | — | **手册未记录，但在固件 `4.8.12.1.1.6.5` 上实测可用**，返回 `0,"No error"` 或 `-113,"Undefined header;<原文>"`、`-224,"Illegal parameter value"`、`-350,"Queue overflow"`。**每次写入后的唯一静默失败探测器**；它不是万能的（采集上下文类写入被丢弃时不报错，见“写入失败模式”），但拒绝类失败全靠它。详见该节的读法与陷阱。 | `firmware-scoped` 实测（手册 pp. 13-14 未列） |
| `*RST` | — | no parameter | 手册 pp. 13-14 只列出该命令，未描述复位后各项设置的具体状态。**破坏性写**：会恢复出厂设置，本 Skill 不发送。 | signal-discovery-and-measurement.md (manual pp. 13-14) |
| `*OPC` | `*OPC?` | `*OPC?` 返回 `1` | 可作同步点，但**不能证明发生过触发**。 | signal-discovery-and-measurement.md (manual pp. 13-14) |

## Write-Failure Modes (read this before diagnosing any setting that "did not take")

Evidence label: `firmware-scoped` — SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP `5025`, four channels enabled. Every row below was reproduced with a fresh single TCP session and a write-then-read-back.

**The default outcome of a rejected or inapplicable write is silence.** `SYST:ERR?` answers `0,"No error"` while the value stays unchanged. A read-back that differs from what was just requested is therefore the *primary* evidence, and the error queue is only a secondary one.

| Symptom you observe | Actual cause | Detector | Correct action |
|---|---|---|---|
| A setting "does not take", no error at all, scope is `Stop` | **Acquisition-context writes are dropped while stopped.** Confirmed `NO-OP` with no error for `:ACQuire:SRATe`, `:ACQuire:MDEPth`, `:ACQuire:MMANagement`. | Write → read back → compare. `SYST:ERR?` stays clean. | Return to run state (`TRMD AUTO`, or `:TRIGger:RUN`) **before** writing acquisition context. Do not conclude the scope is frozen. |
| Same, but the setting is `TDIV`/`TIM:SCAL` | Not a Stop problem: **conservation law**. `TDIV_max = ACQ:POIN? / (SARA * 10)`. In `FSRate` mode the sample rate is fixed, so a large `TDIV` is silently clamped and no error is queued. | Compare requested `TDIV` with `ACQ:POIN?/(SARA*10)`. Read `TDIV?` back. | Lower `SRATe` first, *then* raise `TIM:SCAL`. Verified 4/4: 25Mpts@500MSa/s clamps to 5 ms/div; 25Mpts@20MSa/s reaches 100 ms/div. |
| `-113,"Undefined header"` for a command that exists | **A second and later command inside one TCP write is discarded.** Only the first command of a single `sendall` batch reliably executes; `\n`-separated batches silently lose everything after line 1, and `;` compounds lose the tail too. `TRSE` is the reproducible victim (it is accepted alone or as line 1, rejected as line 2+). The rejected text is echoed in the error string. Other comma-free setters (`C1:OFST`, `:TRIGger:EDGE:SOURce`) happened to survive, so **do not treat "it worked last time" as proof the batching is safe**. | Send one command per `write()`, then read `SYST:ERR?`. | Never pipeline commands. `scripts/scope_protocol.py` already writes one command per `sendall`; if you hand-roll a socket, you lose that protection. |
| `-224,"Illegal parameter value"` | Short form takes a **different value spelling** than the long form. Concrete case: `:TRIGger:EDGE:SLOPe RISing` is valid but `C4:TRSL RIS` is `-224`; the short form requires `POSitive`/`NEGative`. | `SYST:ERR?` does report this one. | Prefer the documented long form `:TRIGger:EDGE:SLOPe`; it is also the only form whose value readback is quoted in the manual. |
| The trigger source changed even though you only set slope or level | Writing `C<n>:TRSL` or `C<n>:TRLV` **also switches the trigger source to that channel** (observed: source was `C3`, `C4:TRLV 2.5` made it `C4`). The readback then looks correct while an unrelated channel quietly became the trigger. | Read `:TRIGger:EDGE:SOURce?`, not just `TRSE?`. | Set the source explicitly with `:TRIGger:EDGE:SOURce C<n>` *after* any per-channel level write, and verify the source last. |
| `SYST:ERR?` itself times out and the whole session then desynchronises | **An undefined-header *query* answers nothing at all.** `TRSL?`, `MMAN?`, `ZOOM?` produce no reply line but do queue `-113`. Every later `readline()` is then short by one response, so subsequent "timeouts" are off-by-one response skew, not a dead instrument. | A query that returns nothing; later queries returning the previous query's answer. | Never invent a query spelling. If one times out, assume the reply stream is skewed: open a new session (a new connection is fine; the instrument is healthy) and re-read a known-good query such as `*IDN?`. |

### Reading the error queue

- `SYST:ERR?` returns one entry per call, oldest first, and `0,"No error"` when empty. **Drain in a loop until it returns `0`**; a single call will report a stale backlog left by an earlier experiment and make you chase a phantom.
- The queue **overflows** (`-350,"Queue overflow"`) after a burst of rejects, so drain before a diagnostic write, not after a long batch.
- An error entry can survive on the unit for several seconds after the offending write; if a fresh session immediately reports a `-113` whose text matches *your previous* experiment, it is backlog, not a new failure.
- The echoed command text in `-113,"Undefined header;<text>"` is the authoritative record of what the instrument tried to parse. Use it to distinguish "command spelling wrong" from "command lost in a batch".


## System / communication

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SYSTem:COMMunicate:LAN:TYPE?` | query | — | 只读确认 LAN 配置类型。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:TYPE` | set | `STATIC` | 有副作用：仅在明确授权、确认网络规划并能处理连接中断时使用；写入后先回读，再重新发现新地址。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:IPADdress?` | query | — | 只读确认当前 IP。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:IPADdress` | set | 字符串，示例如 `"192.168.1.150"` | 引号/字段写法以目标固件为准；会改变可达地址。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:SMASk?` | query | — | 只读确认子网掩码。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:SMASk` | set | 字符串，示例如 `"255.255.255.0"` | 与 `IPADdress` 同批写入并回读。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:GATeway?` | query | — | 只读确认网关。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:GATeway` | set | 字符串，示例如 `"192.168.1.1"` | 与 `IPADdress` 同批写入并回读。 | connection-and-storage.md |
| `:SYSTem:COMMunicate:LAN:MAC?` | query | — | 只读确认 MAC 地址。 | connection-and-storage.md |
| `:SYSTem:NSTorage` | set | `<path>,<user>,<pwd>,...`（完整字段由固件决定）；示意 `"//192.168.1.100/ScopeShare","scope-user","<password>",0,0,1,0,0` | 设置网络存储参数；密码查询以 `***` 返回；不要把密码写入日志/仓库/JSON；字段含义与 SMB/NFS 兼容性由固件决定，不能跨固件硬编码。 | connection-and-storage.md |
| `:SYSTem:NSTorage:CONNect` | event | — | 短命令形式以设备手册为准；连接前先填好 `NSTorage` 参数。 | connection-and-storage.md |
| `:SYSTem:NSTorage:STATus?` | query | — | 确认返回 `ON` 或手册规定的已连接状态；先用小截图/小 CSV 验证挂载路径。 | connection-and-storage.md |
| `:SYSTem:NSTorage:DISConnect` | event | — | 断开网络存储；与 `CONNect` 成对使用。手册印刷 p. 263。 | connection-and-storage.md (manual p. 263) |
| `:SYSTem:REMote?` | query | 返回 `ON`、`OFF` | 查询远程控制状态；`ON` 表示触摸屏、前面板按键和外设均被禁用，界面显示 “Remote”。手册印刷 p. 264。 | connection-and-storage.md (manual p. 264) |
| `:SYSTem:REMote` / `SYST:REM` | set | `ON`、`OFF` | **状态改变**：`ON` 锁定面板与触摸屏，`OFF` 返回本地。仅在用户明确要求时发送，不作为会话收尾清理；raw TCP 会话不会自动进入此状态。手册印刷 p. 264；证据等级 `documented`，未在目标固件实测。 | connection-and-storage.md (manual p. 264) |
| `:SYSTem:DATE?` / `:SYSTem:TIME?` | query | 返回 `YYYYMMDD` / `HHMMSS` | 与 `:HISTORy:TIME?`（只有时分秒）配对才能把历史帧对应到墙钟时间。手册印刷 pp. 232, 238。 | counter-cursor-and-history.md (manual pp. 232, 238) |

## Identity / status / acquisition state

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `TRMD?` | query | — | 返回当前触发/采集模式；快照与采集前记录都用它。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `TRMD` | set | `SINGLE`（新采集）、`AUTO`（显式恢复运行，例如 `scope_restore_run_mode`） | `TRMD SINGLE` 是唯一接受的单次启动操作；Stop 后禁止 `TRMD`；不得自动恢复 `TRMD AUTO`。 | SKILL.md<br>connection-and-storage.md<br>programming-guide.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `SAST?` | query | — | 采集状态：`Ready` -> `Stop` 是有效采集的唯一证据；Stop 前未见过 Ready 不算新采集；轮询超时不得自动重试。快照中记录为 `acquisition_state`。 | SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `STOP` | event | — | Stop 后禁止发送；在不可变读取期间发送会破坏帧证据。`scope_protocol` 将其列入 `FORBIDDEN_AFTER_STOP`。 | SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `RUN` | event | — | Stop 后禁止发送。 | SKILL.md<br>scripts/scope_protocol.py |
| `ARM` | event | — | **禁止发送**。固件 `4.8.12.1.1.6.5` 上 `ARM` 被明确拒绝；`scope_arm_single` 只发送 `TRMD SINGLE`。 | SKILL.md<br>programming-guide.md<br>scripts/scope_protocol.py |
| `:TRIGger:STATus?` / `SAST?` | query | — | 返回 `Arm`、`Ready`、`Auto`、`Trig'd`、`Stop` 或 `Roll`。**`Roll` 不是 `Ready`**：Roll 模式永远不会进入 `Ready`，`Ready -> Stop` 规则无法满足，脚本会立即报错而不是超时。手册印刷 p. 244。 | signal-discovery-and-measurement.md (manual p. 244)<br>scripts/scope_protocol.py |
| `:TRIGger:FREQuency?` | query | — | 硬件频率计数器（Hz）；`0` 表示无有效计数结果，不等于无信号。默认 3 位有效数字，用 `:FORMat:DATA` 提高到 7 位。手册印刷 p. 243。 | signal-discovery-and-measurement.md (manual p. 243) |
| `:TRIGger:MODE` / `TRMD` | set/query | `SINGle`、`NORMal`、`AUTO`、`FTRIG` | `TRMD` 是固件实测短形式，**手册未列出该拼写**；手册形式为 `:TRIGger:MODE`（印刷 pp. 243-244）。`FTRIG` 无视触发条件强制一帧，会破坏 `Ready -> Stop` 证据链，本 Skill 不使用。Stop 后禁止发送。 | signal-discovery-and-measurement.md (manual pp. 243-244)<br>SKILL.md<br>scripts/scope_protocol.py |
| `:TRIGger:TYPE` | set/query | `EDGE`、`PULSE`、`SLOPe`、`INTerval`、`PATTern`、`RUNT`、`WINDow`、`DROPout`、`VIDeo`、`QUALified`、`NEDGe`、`DELay`、`SHOLd`、`IIC`、`SPI`、`UART`、`LIN`、`CAN`、`FLEXray`、`CANFd`、`IIS`、`M1553`、`SENT`、`A429`（24 种） | 只有 `EDGE` 在本 Skill 中验证过；毛刺/欠幅排查必须先选 `RUNT` 或 `PULSE` 再设其参数，否则搜索无从配置。串行/视频类型参数在印刷 pp. 267-410，取决于选件与数字通道。手册印刷 p. 245。 | signal-discovery-and-measurement.md (manual p. 245) |
| `:TRIGger:RUN` | event | — | 等价于前面板 Run，保持当前触发模式。Stop 后禁止（会破坏帧证据）。手册印刷 p. 244。 | signal-discovery-and-measurement.md (manual p. 244) |

## Acquisition / horizontal timebase

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:ACQuire:NUMACq?` | query | — | 已采集帧数；水平/垂直变更等影响采集的操作会使其复位；不是通用平均完成标志。手册印刷 pp. 21-23。 | signal-discovery-and-measurement.md (manual pp. 21-23) |
| `:ACQuire:POINts?` / `ACQ:POIN?` | query | — | 屏幕上当前波形的采样点数（手册印刷 p. 21）。现代传输中与 WAVEDESC 波形点数分别报告；载荷完整性按描述符校验，屏幕／波形范围对应关系单独记录，不能仅因二者不同就断言短读。 | signal-discovery-and-measurement.md (manual pp. 21-23)<br>scripts/scope_protocol.py |
| `:ACQuire:SRATe?` / `SARA?` | query | — | 当前采样率（Sa/s）。**没有离散档位表**：手册只说“超过可设定值会自动匹配”，因此不能预先枚举，必须在设备上读取。手册印刷 pp. 21-23。 | signal-discovery-and-measurement.md (manual pp. 21-23)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `:ACQuire:SRATe` / `ACQ:SRAT` / `ACQ:SRATe` | set | `<rate>`，浮点 NR3，**不带单位后缀**（如 `2.00E+07`）；手册示例为 `5.00E9` | **两个条件同时成立才生效**：`MMANagement FSRate`、`SAST?` 不在 `Stop`。写入后必须回读，实测值可能与请求值不同；改变采集上下文，只能在 `TRMD SINGLE` 之前写。**写入短形式 `SARA <值>` 被拒 `-113 Undefined header`**（`SARA` 只能查询）；**带单位后缀的值也被拒**，`ACQuire:SRATe 20MSa/s` 返回 `-131,"Invalid suffix"`，只能用裸 NR3。手册印刷 p. 22。`firmware-scoped` 实测（4.8.12.1.1.6.5）。 | signal-discovery-and-measurement.md (manual pp. 22-23)<br>scripts/scope_protocol.py |
| `MMAN?` | — | — | **不存在**。`MMAN?`（无论 `ACQ:MMAN?`、`ACQuire:MMAN?`）都会回 `-113 Undefined header`，而且**不回包**，详见“写入失败模式”一节的查询型误用。 | 固件实测 `firmware-scoped` |
| `:ACQuire:MMANagement?` / `ACQ:MMAN?` | query | 返回 `AUTO`、`FSRate`、`FMDepth` | 存储管理方式；决定采样率与存储深度哪一个由用户控制。写采样率或深度前应先确认此模式。手册印刷 p. 18。 | signal-discovery-and-measurement.md (manual p. 18) |
| `:ACQuire:MMANagement` / `ACQ:MMAN` | set | `AUTO`、`FSRate`、`FMDepth` | `AUTO` 保持最大采样率并按时基推两者；`FSRate` 固定采样率、深度随时基；`FMDepth` 固定深度、采样率随时基。改变采集上下文，写入后回读。**`SAST?` 为 `Stop` 时写入静默 NO-OP 且不报错**，必须回到运行态再写。手册印刷 p. 18。`firmware-scoped` 实测。 | signal-discovery-and-measurement.md (manual p. 18)<br>scripts/scope_protocol.py |
| `:ACQuire:MODE` | set/query | `YT`、`XY`、`ROLL` | 采集模式。`ROLL` 为滚动流式显示：**`SAST?` 只报 `Roll` 不报 `Ready`**，因此不能用于本 Skill 的 `Ready -> Stop` 单次采集；只在 50 ms/div 及更慢时可用，水平延迟无效，运行中不支持 Zoom，并限制存储深度。详见 `signal-discovery-and-measurement.md` 的 Roll Mode 一节。手册印刷 pp. 18-19 + 用户手册印刷 p. 44。 | signal-discovery-and-measurement.md (manual pp. 18-19)<br>scripts/scope_protocol.py |
| `:ACQuire:AMODe` | set/query | `FAST`、`SLOW` | 快采/慢采，影响波形捕获率。手册印刷 p. 17。 | signal-discovery-and-measurement.md (manual p. 17) |
| `:ACQuire:TYPE` | set/query | `NORMal`、`PEAK`、`AVERage[,<times>]`、`ERES[,<bits>]`；`<times>` = 4..8192 的 2 次幂，`<bits>` = 0.5..4.0 步进 0.5 | 采集方式；**分段采集开启时平均/ERES 不可用**；平均与 ERES 会限制存储深度。手册印刷 p. 23。 | signal-discovery-and-measurement.md (manual p. 23) |
| `:ACQuire:INTerpolation` | set/query | `ON`（Sinc）、`OFF`（线性） | 内插方式。手册印刷 pp. 17-18。 | signal-discovery-and-measurement.md (manual pp. 17-18) |
| `:ACQuire:SEQuence` | set/query | `ON`、`OFF` | 分段采集开关；随后用 `:WAVeform:SEQuence?` 读取帧。手册印刷 p. 22。 | signal-discovery-and-measurement.md (manual p. 22) |
| `:ACQuire:SEQuence:COUNt` | set/query | 整型 NR1；手册写“最大分段数可能受**存储深度**限制”，未提时基 | 分段数；具体范围因机型/时基而异，回读确认。手册印刷 p. 22。 | signal-discovery-and-measurement.md (manual p. 22) |
| `:ACQuire:RESolution` | set/query | `8Bits`、`10Bits`（手册标注为 SDS2000X Plus） | ADC 分辨率；SDS800X HD 是否支持需按机型确认，不得假设。手册印刷 p. 21。 | signal-discovery-and-measurement.md (manual p. 21) |
| `:ACQuire:CSWeep` | event | — | 清除扫描并重新开始采集，等价于前面板 Clear Sweeps。手册印刷 p. 17。 | signal-discovery-and-measurement.md (manual p. 17) |

| `:ACQuire:MDEPth?` / `ACQ:MDEP?` | query | — | 当前存储深度。SDS800X HD 手册档位为：单通道 `{10k,100k,1M,10M,100M}`、双通道 `{10k,100k,1M,10M,50M}`、四通道 `{10k,100k,1M,10M,25M}`。手册印刷 pp. 19-20。 | signal-discovery-and-measurement.md (manual pp. 19-20)<br>scripts/scope_protocol.py |
| `ACQ:MDEP` / `ACQuire:MDEPth` | set | 手册全档位见上；`configure_memory_depth` 目前只接受 `100M`、`50M`、`25M` 三个便捷值（默认按通道数 1/2/3/4 取 100M/50M/25M/25M） | 必须在 `TRMD SINGLE` 之前写入；写入后回读校验；不可变读取期间禁止。**`SAST?` 为 `Stop` 时静默 NO-OP 且不报错**（`firmware-scoped` 实测：Stop 下 `ACQuire:MDEPth 10M` 从 25M 请求读完仍是 25M，`SYST:ERR?` 为 `0,"No error"`）。脚本未实现的更小档位（10k/100k/1M/10M）需直接发送命令并自行回读。 | signal-discovery-and-measurement.md<br>scripts/scope_protocol.py |
| `:TIMebase:SCALe?` / `TIM:SCAL?` / `TDIV?` | query | — | 主时基（s/div）；左对齐触发策略先读取它计算 `Delay`，写入后再回读校验。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `:TIMebase:DELay?` / `TIM:DEL?` / `TRDL?` | query | — | 水平延迟（s）；`TRDL?` 为旧式字段，延迟符号约定不要与新式 `TIMebase:DELay?` 混用。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `TIM:DEL` | set | 秒，`(5 - margin_div) * Timebase`（`margin_div` 取值 (0, 5]） | 触发跟随窗口策略的显式可选项；只在 `TRMD SINGLE` 之前写，写完回读；与 `--existing-stopped` 不兼容。 | signal-discovery-and-measurement.md<br>SKILL.md<br>scripts/scope_protocol.py |
| `:TIMebase:REFerence:POSition?` / `TIM:REF:POS?` | query | 0..100（百分比） | 延迟固定展开时的水平参考位置；写入后回读。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py |
| `TIM:REF:POS` | set | 整数 0..100 | 可选写入；`capture_scope.py --reference-position` 暴露；仅在采集前使用。 | signal-discovery-and-measurement.md<br>SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `TDIV` / `:TIMebase:SCALe` | set | 受守恒律钳制：`TDIV_max = ACQ:POIN? / (SARA * 10)` | 时基写入；Stop 后禁止（列入 `FORBIDDEN_AFTER_STOP`），会改变采集上下文。**超限写入被静默钳到可取值，且 `SYST:ERR?` 仍返回 `0,"No error"`**——`firmware-scoped` 实测 4/4 命中公式：25Mpoints@500MSa/s → 最大 `5.00E-03S`；25Mpoints@20MSa/s → 最大 `1.00E-01S`；1Mpoints@1MSa/s → 最大 `1.00E-01S`。改时基前先降采样率，否则“写不进 100 ms/div”是守恒律而不是故障。公式见 `signal-discovery-and-measurement.md`。 | scripts/scope_protocol.py<br>`firmware-scoped` 实测 |

## Trigger

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `TRSE` | set | `EDGE,SR,C1,HT,OFF`（handover 记录的唯一形式） | **不要在 Stop 之后使用，也不要把它当作可验证的配置。**`HT` 在整个 495 页编程手册中无定义；按手册自己的可选缩写规则，`HT` 前缀可指 `HOLDoff`、`HLDTime`、`HLDEVent`、`HSTart` 或假想的 `HTIMe`，把它读作“上升沿”是假设。实测 `:TRIGger:EDGE:SLOPe?` 读回 `RISing` 可用于确认斜率。必须在 `TRMD SINGLE` 之前；Stop 后禁止。**另外：`TRSE` 只有在单次 TCP 写入的首条命令位置才可靠生效；作为第 2 条及以后会被丢弃并回 `-113`**（`firmware-scoped` 实测 3/3，前导命令换成 `C1:VDIV`／`*CLS`／4 通道块结果一致）。优先改用 `:TRIGger:EDGE:SOURce`。 | programming-guide.md<br>scripts/scope_protocol.py<br>`firmware-scoped` 实测 |
| `C1:TRSL` | set | **`POS`**（合法）、`NEG`（合法）；**`RIS` / `RISing` 非法** | 短形式，手册无此拼写；手册形式为 `:TRIGger:EDGE:SLOPe {RISing\|FALLing\|ALTernate}`（印刷 p. 250，可查询读回）。**参数值与长形式不同名**：长形式用 `RISing`/`FALLing`，短形式只收 `POSitive`/`NEGative`；`C4:TRSL RIS` 回 `-224 Illegal parameter value`（`firmware-scoped` 实测），所以从长形式“猜”短形式参数会静默失败。注意手册形式不带通道号。**写入 `C<n>:TRSL` 或 `C<n>:TRLV` 会把触发源切到该通道**（`firmware-scoped` 实测），因此不能把它当纯参数写入。必须在 `TRMD SINGLE` 之前；Stop 后禁止。 | programming-guide.md<br>scripts/scope_protocol.py<br>`firmware-scoped` 实测 |
| `C1:TRLV` | set | 电压值，示例 `2.5`（V）或 `2.5V`（带单位均可） | 短形式，手册无此拼写；手册形式为 `:TRIGger:EDGE:LEVel <NR3>`（印刷 p. 249，可查询读回，范围 `[-4.1*垂直档位-垂直偏移, 4.1*垂直档位-垂直偏移]`）。手册形式不带通道号。同样会把触发源切到该通道。必须在 `TRMD SINGLE` 之前；Stop 后禁止。 | programming-guide.md<br>scripts/scope_protocol.py |
| `TRSL` / `TRLV`（无通道前缀） | — | — | **不存在**，回 `-113 Undefined header`：触发斜率/电平的短形式必须带通道前缀（`C<n>:TRSL`、`C<n>:TRLV`）。 | `firmware-scoped` 实测 |
| `:TRIGger:TYPE` / `:TRIGger:EDGE:*` 可读回组合 | set/query | 见下 | 替代 handover 短形式块。固件 `4.8.12.1.1.6.5` 实测全部可读回：`:TRIGger:TYPE?`→`EDGE`、`:TRIGger:EDGE:SOURce?`→`C2`、`:TRIGger:EDGE:SLOPe?`→`RISing`、`:TRIGger:EDGE:LEVel?`→`1.50E+00`、`:TRIGger:EDGE:COUPling?`→`DC`、`:TRIGger:EDGE:HOLDoff?`→`OFF`、`:TRIGger:EDGE:NREJect?`→`OFF`、`:TRIGger:EDGE:IMPedance?`→`ONEMeg`。手册印刷 pp. 249-251。 | programming-guide.md (manual pp. 249-251)<br>scripts/scope_protocol.py |
| `:TRIGger:EDGE:SLOPe?` | query | — | 边沿触发斜率，返回 `RISing`/`FALLing`/`ALTernate`。**这是整个手册中唯一明确给出上升/下降语义的地方**；需要 slope 证据时必须查它，不得从 `HT` 之类的短形式推断。手册印刷 p. 250。 | programming-guide.md (manual p. 250) |
| `:TRIGger:EDGE:SOURce?` | query | — | 边沿触发源，返回 `{C<n>\|D<d>\|EX\|EX5\|LINE}`。允许外部触发与市电，因此 `C2` 这一读回是正向证据而不是默认值。手册印刷 pp. 250-251。 | programming-guide.md (manual pp. 250-251) |
| `:TRIGger:EDGE:LEVel?` | query | — | 边沿触发阈值（V），返回 NR3。手册印刷 p. 249。 | signal-discovery-and-measurement.md (manual p. 249) |

## Channel / vertical

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CHANnel<n>:SCALe?` | query | `n` = 1..4；长形式 | 每通道 V/div；`C<n>:VDIV?` 为脚本使用的短形式。换短形式时 `C<n>:VDIV` 可直接写。手册印刷 pp. 28-29。 | signal-discovery-and-measurement.md (manual pp. 28-29) |
| `:CHANnel<n>:SCALe` | set | NR3，V/div；范围与探头衰减成正比，按机型不同 | 改变采集上下文；Stop 后禁止。手册印刷 pp. 28-29。 | signal-discovery-and-measurement.md (manual pp. 28-29) |
| `:CHANnel<n>:OFFSet?` | query | `n` = 1..4 | 每通道直流偏移；短形式 `C<n>:OFST?`。手册印刷 p. 27。 | signal-discovery-and-measurement.md (manual p. 27) |
| `:CHANnel<n>:OFFSet` | set | NR3，V；允许范围随垂直档位变化 | 改变采集上下文；Stop 后禁止。手册印刷 p. 27。 | signal-discovery-and-measurement.md (manual p. 27) |
| `:CHANnel<n>:SWITch?` | query | `n` = 1..4 | 通道开关状态。手册印刷 p. 29。 | signal-discovery-and-measurement.md (manual p. 29) |
| `:CHANnel<n>:SWITch` | set | `ON`、`OFF` | 通道使能；改变采集上下文。手册印刷 p. 29。 | signal-discovery-and-measurement.md (manual p. 29) |
| `:CHANnel<n>:COUPling?` | query | `n` = 1..4 | AC/DC/GND 耦合。手册印刷 p. 25。 | signal-discovery-and-measurement.md (manual p. 25) |
| `:CHANnel<n>:COUPling` | set | `AC`、`DC`、`GND` | `GND` 断开输入，平线不等于 0 V。手册印刷 p. 25。 | signal-discovery-and-measurement.md (manual p. 25) |
| `:CHANnel<n>:PROBe?` | query | `n` = 1..4 | 探头衰减系数。手册印刷 p. 28。 | signal-discovery-and-measurement.md (manual p. 28) |
| `:CHANnel<n>:PROBe` | set | `DEFault`（1X）或 `VALue,<ratio>`，ratio 1E-6..1E6 | 衰减系数写错会静默缩放所有电压与测量值。手册印刷 p. 28。 | signal-discovery-and-measurement.md (manual p. 28) |
| `:CHANnel<n>:BWLimit` | set/query | `20M`、`200M`、`FULL` | 带宽限制改变上升时间与噪声。手册印刷 p. 24。 | signal-discovery-and-measurement.md (manual p. 24) |
| `:CHANnel<n>:INVert` | set/query | `ON`、`OFF` | 只改变显示极性，不改变触发斜率。手册印刷 p. 26。 | signal-discovery-and-measurement.md (manual p. 26) |
| `:CHANnel<n>:IMPedance` | set/query | `ONEMeg`（1 MΩ）、`FIFTy`（50 Ω） | 50 Ω 时垂直档位最大 1 V/div。手册印刷 pp. 25-26。 | signal-discovery-and-measurement.md (manual pp. 25-26) |
| `:CHANnel<n>:UNIT` | set/query | `V`、`A` | **改变测量、光标、通道档位与触发电平的单位**，不只是标签；切到 `A` 后本 Skill 中所有“电压”表述都按安培解释。手册印刷 p. 30。 | signal-discovery-and-measurement.md (manual p. 30) |
| `:CHANnel<n>:SKEW` | set/query | NR3，-1.00E-07..1.00E-07 s | 通道间时滞补偿。手册印刷 p. 29。 | signal-discovery-and-measurement.md (manual p. 29) |
| `:CHANnel<n>:LABel` | set/query | `ON`、`OFF` | 标签显示开关。手册印刷 p. 26。 | signal-discovery-and-measurement.md (manual p. 26) |
| `:CHANnel<n>:LABel:TEXT` | set/query | 带引号 ASCII，长度 ≤ 20 | 标签文本；仅为注释，不构成证据。手册印刷 p. 27。 | signal-discovery-and-measurement.md (manual p. 27) |
| `:CHANnel<n>:VISible` | set/query | `ON`、`OFF` | 波形显示状态，与 `SWITch` 不同。手册印刷 p. 30。 | signal-discovery-and-measurement.md (manual p. 30) |
| `:CHANnel:REFerence` | set/query | `OFFSet`、`POSition` | 垂直扩展策略：改档位时固定偏移还是固定网格位置。手册印刷 p. 24。 | signal-discovery-and-measurement.md (manual p. 24) |
| `C<n>:VDIV?` | query | `n` = 1..4 | 短形式 V/div 回读；旧式读取时与 `OFST?` 一起记录到配置快照。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `C<n>:VDIV` | set | 示例 `C1:VDIV 2`、`C2:VDIV 2`、`C3:VDIV 5`、`C4:VDIV 2` | 写入会改变垂直刻度并改变采集上下文；Stop 后禁止。 | SKILL.md<br>scripts/scope_protocol.py |
| `C<n>:OFST?` | query | `n` = 1..4 | 短形式偏移回读。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `C<n>:OFST` | set | 示例 `C1:OFST 0` … `C4:OFST 0`（V） | 写入会改变垂直偏移并改变采集上下文；Stop 后禁止。 | SKILL.md<br>scripts/scope_protocol.py |
| `VDIV` / `OFST`（无通道前缀） | set | — | 在 `FORBIDDEN_AFTER_STOP` 中按前缀禁止；属于垂直配置写入（本表不另立行）。 | scripts/scope_protocol.py |

## Measurement

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MEASure:SIMPle:SOURce?` | query | — | 简单测量源，例如返回 `C1`；仅在源身份不明确时读取。手册印刷 pp. 182-183。 | signal-discovery-and-measurement.md (manual pp. 182-183) |
| `:MEASure` | set/query | `ON`、`OFF` | 测量功能总开关；未开启时各测量项不刷新。手册印刷 p. 180。 | signal-discovery-and-measurement.md (manual p. 180) |
| `:MEASure:MODE` | set/query | `SIMPle`、`ADVanced` | 简单/高级测量模式切换；不设模式就配置测量项是常见错误。手册印刷 p. 180。 | signal-discovery-and-measurement.md (manual p. 180) |
| `:MEASure:ADVanced:P<n>` | set/query | `ON`、`OFF` | 槽位使能；未使能时 `VALue?` 无意义。手册印刷 pp. 194-195。 | signal-discovery-and-measurement.md (manual pp. 194-195) |
| `:MEASure:ADVanced:P<n>:TYPE` | set | 高级测量参数（`PKPK`…以及 `PHA`、`SKEW`、`FRR`、`FRF`、`FFR`、`FFF`、`LRR`、`LRF`、`LFR`、`LFF`、`PSLOPE`、`NSLOPE`、`TSR`、`TSF`、`THR`、`THF`、`DTIMe1`..`DTIMe4` 等 70+ 项） | 决定槽位测什么；不写 `TYPE` 槽位就是空的。手册印刷 p. 196。 | signal-discovery-and-measurement.md (manual p. 196) |
| `:MEASure:SIMPle:ITEM` | set | `<parameter>,{ON\|OFF}`；`<parameter>` 为 52 项之一（`PKPK`、`MAX`、`MIN`、`AMPL`、`TOP`、`BASE`、`LEVELX`、`CMEAN`、`MEAN`、`STDEV`、`VSTD`、`RMS`、`CRMS`、`MEDIAN`、`CMEDIAN`、`OVSN`、`FPRE`、`OVSP`、`RPRE`、`ULOWer`、`PER`、`FREQ`、`TMAX`、`TMIN`、`PWID`、`NWID`、`DUTY`、`NDUTY`、`WID`、`NBWID`、`DELAY`、`TIMEL`、`RISE`、`FALL`、`RISE20T80`、`FALL80T20`、`CCJ`、`PAREA`、`NAREA`、`AREA`、`ABSAREA`、`CYCLES`、`REDGES`、`FEDGES`、`EDGES`、`PPULSES`、`NPULSES`、`PACArea`、`NACArea`、`ACArea`、`ABSACArea`） | **必须先开启测量项**，否则 `VALue?` 取不到该结果；示例 `:MEASure:SIMPle:ITEM MAX,ON`。手册印刷 pp. 181-182。 | signal-discovery-and-measurement.md (manual pp. 181-182) |
| `:MEASure:SIMPle:VALue?` | query | 必带参数：`PKPK`、`MAX`、`MIN`、`AMPL`、`MEAN`、`RMS`、`PER`、`FREQ`、`PWID`、`NWID`、`DUTY`、`RISE`、`FALL`（以及原文列出的计数/面积类项目）或 `ALL` | 不能静默丢弃参数；`ALL` 查询全部基本测量项，**不保证**为单一标量，必须用保存完整响应的 reader。手册印刷 pp. 164-183。 | signal-discovery-and-measurement.md (manual pp. 164-183) |
| `:MEASure:ADVanced:P<n>:SOURce1` / `:MEASure:ADVanced:P<n>:SOURce2` | set/query | 源：`C<n>`、`Z<n>`（仅 Zoom 开启时有效）、`F<x>`、`M<m>`、`D<d>`（0-15）、`REF<r>`（A-D） | 槽位源；A/B 两个源都要设对。手册印刷 pp. 164-166。 | signal-discovery-and-measurement.md (manual pp. 164-166) |
| `:MEASure:ADVanced:P<n>:VALue?` | query | `n` = 1..12 | 槽位测量值。手册印刷 p. 200。 | signal-discovery-and-measurement.md (manual p. 200) |
| `:MEASure:ADVanced:P<n>:STATistics?` | query | `ALL`、`CURRent`、`MEAN`、`MAXimum`、`MINimum`、`STDev`、`COUNt` | 参数必填；示例 `P1:STATistics? MEAN`。手册印刷 p. 200。 | signal-discovery-and-measurement.md (manual p. 200) |
| `:MEASure:ADVanced:P<n>:SHIStory?` | query | 可选计数，示例 `5` | 返回 `Count=n,value...`；是有界的测量统计历史，不必然是墙钟时间线。手册印刷 p. 201。 | signal-discovery-and-measurement.md (manual p. 201) |
| `AUToset` | event | — | 手册记录的状态改变便利命令；低于 100 Hz 的信号不推荐；仅在明确要求时使用，受控调参应改用有界 V/div、offset、时基与触发电平并回读。 | signal-discovery-and-measurement.md |
| `:FORMat:DATA` | set/query | `SINGle`（7 位有效数字）、`DOUBle`（14 位）、`CUSTom,<digit>`（`<digit>` 为 1..64 的整数） | **默认只有 3 位有效数字**；在做统计、读取 7 位频率计数器或小纹波之前必须提高精度。手册印刷 p. 15。 | signal-discovery-and-measurement.md (manual p. 15)<br>counter-cursor-and-history.md |

## Waveform transfer (modern WAV)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `WAV:SOURce` / `:WAVeform:SOURce` | set | `C1`、`C2`、`C3`、`C4` | 改变传输视图；在 `Stop` 后属于显式 `configured_capture` 路径，不可变模式禁用。手册印刷 pp. 383-394。 | screenshot-and-waveform.md (manual pp. 383-394)<br>SKILL.md<br>programming-guide.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:PREamble?` / `:WAVeform:PREamble?` | query | — | 返回二进制块（346 字节小端 WAVEDESC），不是 ASCII；解析偏移见 `programming-guide.md`（含 `wave_array_1`、`wave_array_count`、`read_frames`、`sum_frame` 等）。手册印刷 pp. 383-394。 | screenshot-and-waveform.md (manual pp. 383-394)<br>connection-and-storage.md<br>programming-guide.md<br>SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:MAXPoint?` | query | — | 单次传输最大点数；用于选择分段步长。手册 5.23（PDF pp. 411-422）。 | programming-guide.md (manual 5.23, PDF pp. 411-422)<br>connection-and-storage.md<br>scripts/capture_scope.py |
| `WAV:WIDTh` / `:WAVeform:WIDTh` | set | `WORD`（原文示例；脚本 `--wav-width` 另有 `BYTE`） | 前导码 nominal bits > 8 时必须用 `WORD`；`BYTE` 只用于明确标注为有损的历史对比；写入改变传输视图，不可变模式禁用。手册印刷 pp. 383-394。 | SKILL.md<br>programming-guide.md<br>screenshot-and-waveform.md (manual pp. 383-394)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:WIDT?` | query | — | 宽度回读，脚本与请求值比对。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:BYTeorder` / `:WAVeform:BYTeorder` | set | `LSB`（WORD 传输） | 写完必须读回 `WAV:BYT?` 确认；WORD 电压标定仍未验证。 | SKILL.md<br>programming-guide.md<br>screenshot-and-waveform.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:BYT?` | query | — | 字节序回读（期望 `LSB`）。 | SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:INTerval` / `:WAVeform:INTerval` | set | `1`（抽点间隔 1，不抽点） | 读回 `WAV:INT?` 必须为 1；写入改变传输视图。 | SKILL.md<br>programming-guide.md<br>screenshot-and-waveform.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:INT?` | query | — | 抽点参数回读。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:STARt` / `:WAVeform:STARt` | set | 从 0 起始的点索引 `<zero-based-point>` | 只控制切片起点，不改变记录长度；每段写后回读 `WAV:STAR?` 校验。手册 5.23（PDF pp. 411-422）。 | SKILL.md<br>programming-guide.md (manual 5.23, PDF pp. 411-422)<br>screenshot-and-waveform.md<br>connection-and-storage.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:STAR?` | query | — | 起点回读，必须等于请求值。 | scripts/scope_protocol.py |
| `WAV:POINt` / `:WAVeform:POINt` | set | 点数 `<count>` | 与 `STARt` 共同定义切片；请求值必须与实际 `WAV:DATA?` 载荷点数一致。`WAV:POIN?` 只作辅助证据，不能替代载荷长度校验。手册 5.23（PDF pp. 411-422）。 | SKILL.md<br>programming-guide.md (manual 5.23, PDF pp. 411-422)<br>screenshot-and-waveform.md<br>connection-and-storage.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WAV:POIN?` | query | — | 点数回读仅作辅助证据；已验证固件可回显请求值而实际载荷静默截断到 250000 点。必须以 `len(payload) / bytes_per_point` 校验实际点数，不一致即失败；250000 是实测固件行为，不是通用上限。 | scripts/scope_protocol.py<br>scripts/capture_scope.py<br>screenshot-and-waveform.md |
| `WAV:DATA?` / `:WAVeform:DATA?` | query | — | IEEE 488.2 二进制块；BYTE 期望 `count` 字节、WORD 期望 `count * 2` 字节；保留前缀/头/载荷/SHA-256；短载荷即 `INCOMPLETE`/`INVALID`。手册 5.23（PDF pp. 411-422）。 | SKILL.md<br>programming-guide.md (manual 5.23, PDF pp. 411-422)<br>connection-and-storage.md<br>screenshot-and-waveform.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `:WAVeform:SEQuence?` | query | — | 分段采集启用后才有意义；返回 `<value1>,<value2>`，未启用分段时目标返回 `4294967295,1`，**不得**当作有效帧号；按 `PREamble?` 的 `read_frames`/`sum_frame` 计算分片读取次数。手册印刷 pp. 383-394。 | screenshot-and-waveform.md (manual pp. 383-394) |
| `CHDR` | set | `OFF` | 关闭命令头开启状态命令；在采集准备序列中先于通道/触发设置。 | programming-guide.md<br>scripts/scope_protocol.py |
| `WFSU?` | query | — | 波形设置回读（`waveform_setup`），快照与旧式读取都记录；Stop 后查询允许。 | scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `WFSU` | set | `SP,1,NP,0,FP,0`（handover 记录的唯一形式） | **会替换/刷新已停止帧**；Stop 后的不可变读取中禁止；仅在 `configured_capture` 且 `--wfsu` 显式给出时使用，并逐条记录。 | SKILL.md<br>programming-guide.md<br>connection-and-storage.md<br>scripts/scope_protocol.py<br>scripts/test_scope_protocol.py |

## Waveform transfer (legacy stopped frame)

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `C<n>:WF? DAT2` | query | `n` = 1..4 | 旧式 8 位载荷（`1000` 字节 = `1000` 点）；不可变读取必须先对**所有**请求通道发 `WF? DAT2` 并保存，之后才允许 `WF? DESC`；缺任一通道的 DAT2 时脚本会拒绝 DESC。 | SKILL.md<br>programming-guide.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `C<n>:WF? DESC` | query | `n` = 1..4 | 描述符（WAVEDESC）；只能作为 DAT2 全部完成后的独立诊断步骤；不可作为新的触发证据。 | SKILL.md<br>programming-guide.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |

## Screenshot / print

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:PRINt?` | query | `PNG`；或 `BMP[,NORMal\|INVerted]` | 返回图像字节流，不是 ASCII 标量；**固件 `4.8.12.1.1.6.5` 实测为裸 PNG，无 IEEE 488.2 头**，以 `LF` 结尾，`query_block()`/`read_ieee_block()` 会合法地失败。须按 `IEND` + `LF` 有界读取并保留 SHA-256，禁止 `readline()`；`scripts/screenshot_capture.py` 实现了该读取器（只校验容器：签名、IHDR 合法位深/颜色组合、块顺序、CRC、`IEND`+`LF`；不解码图像，`image_decode_status` 恒为 `UNVERIFIED`；离线测试，未实机验证）。`PRINt?` **无法隐藏屏上菜单**，需要无菜单截图时用 `:SAVe:IMAGe ... ,MOFf`。手册印刷 p. 15；示例 pp. 494-495。 | screenshot-and-waveform.md (manual p. 15, pp. 494-495)<br>connection-and-storage.md |
| `:SAVe:IMAGe` | set | `<path>,<type>,<invert>[,<menu>]`；`<type>` = `BMP`/`JPG`/`PNG`，`<invert>` = `ON`/`OFF`，`<menu>` = `MOFf`/`MON` | 存到内部（`local/...`）、网络存储（`net_storage/...`）或 U 盘（`U-disk0/...`）；**唯一能隐藏顶部/右侧菜单的截图路径**。写文件，需授权且不得覆盖既有文件。手册印刷 p. 203。 | screenshot-and-waveform.md (manual p. 203) |
| `:DISPlay:PERSistence` | set/query | SDS800X HD：`OFF`、`INFinite`、`1S`、`5S`、`10S`、`30S` | 余辉显示时间；捕获间歇故障与截图取证的基础显示能力。手册印刷 p. 133。 | screenshot-and-waveform.md (manual p. 133) |

## Counter

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:COUNter` | set/query | `ON`、`OFF` | 计数器使能；默认关闭，未使能时 `CURRent?` 返回 0，看起来像测量结果。手册印刷 p. 31。 | counter-cursor-and-history.md (manual p. 31) |
| `:COUNter?` | query | — | 计数器开关状态。手册印刷 p. 31。 | counter-cursor-and-history.md (manual p. 31) |
| `:COUNter:MODE` | set/query | `FREQuency`、`PERiod`、`TOTalizer` | 当前值含义取决于模式；只测模拟通道输入。手册印刷 pp. 31-32。 | counter-cursor-and-history.md (manual pp. 31-32) |
| `:COUNter:LEVel` | set/query | 触发电平，NR3 | 计数器的触发/门限电平。手册印刷 p. 31。 | counter-cursor-and-history.md (manual p. 31) |
| `:COUNter:SOURce` | set/query | 通道 | 计数器源通道。手册印刷 p. 33。 | counter-cursor-and-history.md (manual p. 33) |
| `:COUNter:CURRent?` | query | — | 当前值；目标实测为 `0.00E+00`（未启用/默认态）。手册印刷 p. 31。 | counter-cursor-and-history.md (manual p. 31) |
| `:COUNter:STATistics` | set/query | `ON`、`OFF` | 统计开关；默认 `OFF`，仅频率/周期模式有文档统计。手册印刷 p. 33。 | counter-cursor-and-history.md (manual p. 33) |
| `:COUNter:STATistics:RESet` | event | — | 清零统计；不重置就没法把新旧数据分开。手册印刷 p. 33。 | counter-cursor-and-history.md (manual p. 33) |
| `:COUNter:STATistics:VALue?` | query | — | 格式 `<current>,<mean>,<min>,<max>,<stdev>,<count>`；统计关闭时返回 `OFF`。手册印刷 pp. 33-34。 | counter-cursor-and-history.md (manual pp. 33-34) |
| `:COUNter:TOTalizer:GATE` | set/query | `ON`、`OFF` | 总计数模式的门控开关；不开门控时总数无意义。手册印刷 p. 34。 | counter-cursor-and-history.md (manual p. 34) |
| `:COUNter:TOTalizer:GATE:TYPE` | set/query | 手册枚举 | 门控类型。手册印刷 p. 36。 | counter-cursor-and-history.md (manual p. 36) |
| `:COUNter:TOTalizer:GATE:LEVel` | set/query | 电平 NR3 | 门控电平。手册印刷 p. 35。 | counter-cursor-and-history.md (manual p. 35) |
| `:COUNter:TOTalizer:GATE:SLOPe` | set/query | `RISe`、`FALL` | 门控斜率。手册印刷 p. 35。 | counter-cursor-and-history.md (manual p. 35) |
| `:COUNter:TOTalizer:SLOPe` | set/query | `RISe`、`FALL` | 计数斜率。手册印刷 pp. 36-37。 | counter-cursor-and-history.md (manual pp. 36-37) |
| `:COUNter:TOTalizer:RESet` | event | — | 总计数清零。手册印刷 p. 36。 | counter-cursor-and-history.md (manual p. 36) |

## Cursor

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:CURSor` | set/query | `ON`、`OFF` | 光标使能；未使能时查询位置会超时。手册印刷 pp. 38-39。 | counter-cursor-and-history.md (manual pp. 38-39) |
| `:CURSor:MODE` | set/query | `TRACk`、`MANual,{X\|Y\|XY}`、`MEASure` | 手动模式需带 `X`/`Y`/`XY` 子选择。手册印刷 p. 41。 | counter-cursor-and-history.md (manual p. 41) |
| `:CURSor:SOURce1` | set/query | 通道或参考源 | 第一个光标源。手册印刷 pp. 41-42。 | counter-cursor-and-history.md (manual pp. 41-42) |
| `:CURSor:SOURce2` | set/query | 通道或参考源 | 第二个光标源。手册印刷 p. 42。 | counter-cursor-and-history.md (manual p. 42) |
| `:CURSor:X1` | set/query | 时间位置 | 第一个 X 光标位置。手册印刷 p. 43。 | counter-cursor-and-history.md (manual p. 43) |
| `:CURSor:X2` | set/query | 时间位置 | 第二个 X 光标位置。手册印刷 p. 43。 | counter-cursor-and-history.md (manual p. 43) |
| `:CURSor:Y1` | set/query | 电压/电流位置 | 第一个 Y 光标位置。手册印刷 p. 44。 | counter-cursor-and-history.md (manual p. 44) |
| `:CURSor:Y2` | set/query | 电压/电流位置 | 第二个 Y 光标位置。手册印刷 p. 44。 | counter-cursor-and-history.md (manual p. 44) |
| `:CURSor:MODE?` | query | 返回 `TRACk`、`MANual`、`MEASure`；手动模式另有 `X`/`Y`/`XY` 选择 | 光标未启用时查询可能超时，不等于命令不支持。手册印刷 p. 41。 | counter-cursor-and-history.md (manual p. 41) |
| `:CURSor:X1?` | query | — | 第一个 X 光标位置。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:X2?` | query | — | 第二个 X 光标位置。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:XDELta?` | query | — | 返回 `X2-X1`（s）。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:IXDelta?` | query | — | 返回 `1/(X2-X1)`（Hz）。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:Y1?` | query | — | 第一个 Y 光标位置。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:Y2?` | query | — | 第二个 Y 光标位置。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |
| `:CURSor:YDELta?` | query | — | 返回 `Y2-Y1`（通道垂直单位）。手册印刷 pp. 38-45。 | counter-cursor-and-history.md (manual pp. 38-45) |

## History

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:HISTORy` | set/query | `ON`、`OFF` | 历史波形使能；未使能时 `TIME?` 超时属条件查询，不等于不支持。手册印刷 p. 161。 | counter-cursor-and-history.md (manual p. 161) |
| `:HISTORy:FRAMe` | set/query | 整型帧号；上限与存储深度相关（每帧点数越多，可存帧越少） | 选帧；会改变仪器视图，不可变读取期间禁止。手册印刷 p. 161。 | counter-cursor-and-history.md (manual p. 161) |
| `:HISTORy:INTERval` | set/query | 时间间隔 | 历史采集间隔。手册印刷 p. 162。 | counter-cursor-and-history.md (manual p. 162) |
| `:HISTORy:LIST?` | query | — | 历史帧列表。手册印刷 p. 162。 | counter-cursor-and-history.md (manual p. 162) |
| `:HISTORy:PLAY` | event | 手册枚举 | 历史回放；属于视图状态改变。手册印刷 p. 163。 | counter-cursor-and-history.md (manual p. 163) |
| `:HISTORy:TIME?` | query | — | 返回当前选中历史帧的 `HH:MM:SS.ffffff`，不含日期；需配合 `:SYSTem:DATE?`/`:SYSTem:TIME?` 才能定位墙钟时间；无有效历史帧时可能超时，不等于不支持；历史帧选择/回放会改变仪器视图，不可变读取期间禁止。手册印刷 p. 163。 | anomaly-search-and-mask-testing.md (manual p. 163)<br>counter-cursor-and-history.md (manual p. 163) |

## Protocol decode

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:DECode:BUS<n>:PROTocol?` | query | `n` = 1、2；返回 `IIC`、`SPI`、`UART`、`CAN`、`LIN`、`FLEXray`、`CANFd`、`IIS`、`M1553`、`SENT`、`MANchester`、`ARINC429`/`A429`、`USB20` | 可用性取决于型号/选件；原文写作用于 bus 1（`BUS1`）。手册印刷 pp. 71-72。 | protocol-decode.md (manual pp. 71-72) |
| `:DECode:LIST?` | query | 返回 `OFF`、`D1` 或 `D2` | 当前列表显示选择。手册印刷 pp. 68-70。 | protocol-decode.md (manual pp. 68-70) |
| `:DECode:LIST:LINE?` | query | 整数 1-7 | UI 显示行数，不是解码帧总数。手册印刷 pp. 68-70。 | protocol-decode.md (manual pp. 68-70) |
| `:DECode:LIST<n>:RESult?` | query | `n` = 1、2 | 列表/总线 1 或 2 的完整 ASCII 解码表（逗号分隔字段、换行分隔记录、含表头）；事件分析首选；**必须用保留全部行的 reader**（禁止只读首行的 `readline()`，否则只得表头且缓冲区残留导致后续响应错位）；先解析表头，不假设固定列。`scripts/read_decode_list.py` 已实现只读抓取。手册印刷 pp. 68-70。 | protocol-decode.md (manual pp. 68-70) |
| `:DECode:BUS<n>:RESult?` | query | `n` = 1、2 | 可见总线摘要（逗号分隔字段、分号分隔帧），事件多时可能不完整；**多行 ASCII**，同样必须保留全部行；仅作屏幕摘要核对。手册印刷 pp. 71-72。 | protocol-decode.md (manual pp. 71-72) |

**常见错误（`firmware-scoped`，SDS824X HD 4.8.12.1.1.6.5，SCPI TCP 5025）**：不要猜测 `DEC1?`、`DEC1:STAT/TYPE/SPI?`、`DEC:SPI?`、`DEC:A:*`、`D1:*` 等发明节点——这些不是本机合法查询；未定义查询 **0 字节返回并入队 `-113,"Undefined header;..."`**，`readline()` 会超时，复用同一连接还会造成响应错位。手册给出的短形式（如 `DEC:LIST1:RES?`）仍属合法命令树；规则是“不发明 header/node”。`DEC?`/`DECODE?` 可能返回全局 `ON/OFF`（本机观察值），但**不**返回总线/列表/解码明细。查询无返回时在**新连接**上 `SYST:ERR?` 排空直到 `0,"No error"`；`RESult?` 多行读取首字节用正常超时、首字节后用 idle 超时（启发式），并显式报告 `complete/truncated` 风险，勿静默截断。`scripts/read_decode_list.py` 仅发送文档化只读查询集（含 `*IDN?` 识别），不接受任意写命令。

**解码查询指导（通用）**：只使用手册/已验证读回确认的解码命令；不要发明 header/node。未定义查询在部分固件上可能 0 字节返回并入队错误，单行 `readline()` 会挂起并造成响应错位——无返回时在**新连接**上 `SYST:ERR?` 排空直到 `0,"No error"`。全局解码开关不能替代总线/协议选择或 `LIST/BUS RESult?`。若已配置解码器，**先读 `:DECode:LIST<n>:RESult?` 再做 host 侧重建**；host 侧重建无法证明仪器的帧边界、采样点、阈值/源、时钟/边沿、位序与帧格式。`RESult?` 为多行 ASCII：首字节用正常超时、首字节后用 idle 超时（启发式），保留全部行并显式报告完整性/截断风险。`scripts/read_decode_list.py` 仅发送固定只读查询集（含 `*IDN?`）。

**解码器配置读回（通用）**：本 Skill 记录 `LIST/RES`、`BUS/RES`、协议/列表选择等结果/状态查询，但**未**完整映射协议专用配置读回（源、阈值、速率、时钟/边沿、位序、帧格式等，手册印刷 pp. 73-148）。未确认的配置一律标 `UNVERIFIED`：以编程手册为准逐项验证候选查询的读回与 `SYST:ERR?`；不得仅凭解码字节或 host 侧波形重建反推配置。

## Search / anomaly

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:SEARch` | set/query | `ON`、`OFF` | **搜索使能**；默认关闭，未使能时 `COUNT?` 返回 0 通常表示“未配置”，不是“无异常”。手册印刷 p. 207。 | anomaly-search-and-mask-testing.md (manual p. 207) |
| `:SEARch?` | query | — | 搜索使能状态。手册印刷 p. 207。 | anomaly-search-and-mask-testing.md (manual p. 207) |
| `:SEARch:MODE` | set/query | `EDGE`、`SLOPe`、`PULSE`、`INTerval`、`RUNT` | 必须先设模式再设该模式参数；只读 `COUNT?` 永远只反映上一次面板设置。手册印刷 p. 207。 | anomaly-search-and-mask-testing.md (manual p. 207) |
| `:SEARch:MODE?` | query | 返回 `EDGE`、`SLOPe`、`PULSE`、`INTerval` 或 `RUNT` | 必须先确认当前模式与源/极性/阈值/限制再解释计数。手册印刷 p. 207。 | anomaly-search-and-mask-testing.md (manual p. 207) |
| `:SEARch:EDGE:*` / `:SEARch:SLOPe:*` / `:SEARch:PULSE:*` / `:SEARch:INTerval:*` / `:SEARch:RUNT:*` | set/query | 源、斜率/极性、阈值、上下限（按模式不同） | 各模式参数族，手册印刷 pp. 209-234；本 Skill 未逐条记录，使用前回查手册。`RUNT:TLOWer`/`TUPPer` 是欠幅排查的关键。 | anomaly-search-and-mask-testing.md (manual pp. 209-234) |
| `:SEARch:COUNT?` | query | — | 当前屏幕内的搜索事件数，不是全历史累计；目标实测返回 `0`。手册印刷 p. 208。 | anomaly-search-and-mask-testing.md (manual p. 208) |
| `:SEARch:EVENt?` | query | — | 停止采集时当前定位到的事件帧索引；目标实测返回 `0`。手册印刷 p. 208。 | anomaly-search-and-mask-testing.md (manual p. 208) |

## Mask test

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `:MTESt` | set/query | `ON`、`OFF` | 掩码测试使能；未使能时计数器无意义。手册印刷 p. 222。 | anomaly-search-and-mask-testing.md (manual p. 222) |
| `:MTESt?` | query | — | 掩码测试查询；响应形如 `FAIL,<n>,PASS,<n>,TOTAL,<n>`；必须检查使能状态、源、掩码/测试类型与总数。手册印刷 p. 218。 | anomaly-search-and-mask-testing.md (manual p. 218) |
| `:MTESt:MASK:LOAD` | set | `INTernal,<num>` 或 `EXTernal,<path>` | 加载内部或外部掩码；写文件/内部槽位，属于授权写操作。手册印刷 p. 221。 | anomaly-search-and-mask-testing.md (manual p. 221) |
| `:MTESt:TYPE` | set/query | `ALL_IN`、`ALL_OUT`、`ANY_IN`、`ANY_OUT` | `ALL_IN` 要求**所有**点都在模板内才 PASS，1 个点越界即 FAIL；不记录类型则 PASS/FAIL 不可解释。手册印刷 p. 223。 | anomaly-search-and-mask-testing.md (manual p. 223) |
| `:MTESt:COUNt?` | query | — | 计数；`TOTAL=0` 表示未评估样本/帧，不等于通过；计数器单独不足以判定 PASS/FAIL。手册印刷 p. 218。 | anomaly-search-and-mask-testing.md (manual p. 218) |

## 手册自身缺陷（记录，不复制）

- **`DITMe` 与 `DTIMe`**：手册「新增命令」列表（印刷 p.29 附近）把 DeltaTime 的测量项写成
  `:MEASure:DITMe<n>:EDGE1/EDGE2/SLOPe1/SLOPe2/THReshold1…`，而命令章节与目录用的是
  `:MEASure:DTIMe<n>:…`（如 PDF p.176-177）。本索引只录 `DTIMe` 拼写；`DITMe` 是手册笔误，
  不要当成第二条命令发送。若在固件上确认 `DITMe` 也可接受，再作为 `measured-only` 单列。
- **`12C` 与 `I2C`**：部分表格把 I2C 印成 `12C`（数字 1 与 2），属排版缺陷，不是第二种协议。

## Coverage gaps

本文件之前，Skill 内没有任何完整命令枚举；现有文档只覆盖发现/连接、采集与传输、测量、解码、搜索/掩码、计数器/光标/历史、截图与 PDF 相关路径。以下子系统手册有覆盖但本 Skill **未记录**具体命令，使用时必须回查 `SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` 并据此标注 `documented`：

- **IEEE 488.2 其余命令**：手册本身只列出 `*IDN`、`*OPC`、`*RST` 三条（印刷 pp. 13-14）；`*CLS`、`*ESE`、`*ESR?`、`*SRE`、`*STB?`、`*TRG`、`*TST?`、`*SAV`/`*RCL` **不在该手册中**，是否支持需按固件实测，不得假设。
- **错误队列与状态寄存器**：手册未记录任何查询。**`SYSTem:ERRor?` 已在固件 `4.8.12.1.1.6.5` 上实测可用**（见“Write-Failure Modes”一节），因此写入后的探测不再属于未知项；但 `*ESR?`/`*STB?`/`*SRE`/`*CLS` 等仍不得假设支持。手册 pp. 13-14。
- **系统设置**：`SYSTem` 已记录 LAN、`NSTorage`（含 `DISConnect`）、`REMote`、`DATE?`/`TIME?`；`BUZZer`、`CLOCk`、`VNCPort`、`EDUMode`、`LANGuage`、`MENU`、`PON`、`SSAVer`、`TOUCh` 未记录（手册印刷 pp. 257-266）；`REBoot`、`SHUTdown`、`SELFCal` 属破坏性/耗时操作，刻意不提供。
- **通道/垂直写入**：已记录 `SCALe`、`OFFSet`、`SWITch`、`COUPling`、`PROBe`、`BWLimit`、`INVert`、`IMPedance`、`UNIT`、`SKEW`、`LABel`、`LABel:TEXT`、`VISible`、`CHANnel:REFerence`（手册印刷 pp. 24-30）。
- **数字通道与选件**：MSO 数字通道（`:DIGital:*`，选件）、`:WGEN:*`（外部 SAG1021I 发生器选件，不是本机内置）、`:METEr:*`（仅手持 SHS 系列）均不属于本机基础能力，刻意不收录。
- **时基/采集写入**：已记录 `ACQ:MDEP`、`ACQ:SRAT`、`ACQ:MMAN`、`ACQ:MODE`、`ACQ:TYPE`、`ACQ:SEQuence`、`TIM:DEL`、`TIM:REF:POS`、`TDIV`；`ACQ:AMODe`、`ACQ:INTerpolation`、`ACQ:CSWeep` 已列但未实现为脚本参数；数字通道、平均/ERES 与记录深度的交互只按手册记录，未实测。
- **采样率可取值集合**：两份手册都没有离散档位表，只有“超过可设定值自动匹配”的说明。Roll 模式下的采样率由 50 ms/div 下限与（未公开的）深度限制共同约束，只能现场读 `:ACQuire:MDEPth?`/`:ACQuire:POINts?`/`:ACQuire:SRATe?` 获取，不得用公式代替实测。
- **触发系统**：已记录 `TRIGger:MODE`（含 `FTRIG`）、`TRIGger:TYPE` 的 24 种类型、`TRIGger:STATus?`、`TRIGger:RUN/STOP` 与边沿触发序列；各类型的具体参数（脉宽、欠幅上下限、释抑、耦合、噪声抑制、串行协议阈值/速率）未逐条记录，手册印刷 pp. 245-410。
- **测量**：简单测量已记录 `MEASure` 总开关、`MEASure:MODE`、`SIMPle:ITEM` 的 52 项参数与 `VALue?`；高级测量已记录槽位使能、`TYPE` 写入、双源、值、统计、历史；阈值上下文 `THReshold:SOURce/TYPE/PERCent/ABSolute` 已记录（手册印刷 pp. 183-185）；统计复位与 `MAXCount`、`ASTRategy`、门控（`GATE`）未记录。
- **波形传输**：只记录了现代 WAV 与旧式 `C<n>:WF? DAT2/DESC`；`WAV:SOURce` 的数字通道/数学等扩展源、历史帧/存储媒介选择（`MEMory`/`SAVE` 类）未记录。
- **文件与保存**：已记录 `SAVe:IMAGe`（含菜单开关）；`:SAVe:WAVEform`、`:SAVe:SETup`、`:RECall:*`、`:MEMory:*`、`:REF:*` 未记录，属写文件操作，需按需授权。
- **协议解码**：只记录 5 条总线/列表查询；`DECode`/`DECode:BUS<n>` 使能、`BUS<n>:PROTocol` 写入，以及手册印刷 pp. 73-148 的协议专用设置（I2C/SPI/UART/CAN/LIN 等的源、阈值、位速、帧格式）未记录。
- **搜索与掩码**：已记录搜索使能/模式/计数/事件/模式参数族，掩码使能/加载/类型/计数；事件导航（上一/下一事件 `COPY`）、掩码生成/编辑与模板来源未记录。
- **计数器/光标/历史**：已记录计数器使能/模式/源/电平/统计/总计数的门控，光标使能与单组位置/差值，历史使能/选帧/间隔/列表/回放；多光标族（`MANual`/`MEASure`/`TRACk`/`XY`，印刷 pp. 46-67）未逐条记录。
- **数学与显示**：`:FUNCtion<x>:*`（ADD/SUBT/FFT/ERES/AVERage/MAXHold/MINHold/FILTer 等，印刷 pp. 138-188）与 `:DISPlay:*`（除 `PERSistence` 外）未记录。
- **网络与远程控制周边**：VXI-11/Web 控制、凭据与安全设置、固件升级等命令未记录。

## Appendix: every command in the manual (TOC/heading derived)

This appendix exists so the index misses no command the vendor manual documents.
It was generated from the manual's own command headings
(`SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`, 495 pages): command spelling and
PDF page come from the manual, and the parameter and note columns are
transcribed from the cited PDF page. Where the manual makes a range depend on
the model, the SDS800X HD row of its table is quoted. Rows are `documented`
only — transcribing a page is not a hardware verification — and the curated
tables above remain the place to look for behaviour, caveats and evidence
labels.

`780` commands below have no curated row above. The query column names the
`?` form the SCPI convention implies; confirm it against the manual page before
relying on it. `—` in the parameter column means the cited page lists no input
parameter (query-only or event command, or a section heading whose parameters
live in its subcommands); "manual lists no range" means the page gives the type
but no range, and nothing was filled in from outside the manual.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:DECode` | `:DECode?` | `<state>` = `{ON\|OFF}` | documented; 解码功能总开关（手册 p.96）。先把本开关打开，子命令才有意义；查询返回开关状态。 | 96 |
| `:DIGital` | `:DIGital?` | `<state>` = `{ON\|OFF}` | documented; 数字通道总开关（手册 p.149）。依赖 MSO/Plus 的数字通道硬件。 | 149 |
| `:DVM` | `:DVM?` | `<state>` = `{ON\|OFF}` | documented; 数字电压表（DVM）开关（手册 p.163）；DVM 读数只在开启后有效。 | 163 |
| `:FUNCtion<x>` | `:FUNCtion<x>?` | `<x>` 数学函数序号 NR1；`<state>` = `{ON\|OFF}` | documented; 数学函数总开关（手册 p.167）。关掉后该函数的 `:FUNCtion<x>:*` 读数不可当有效值。 | 167 |
| `:COUNter:STATistics:VALue` | `:COUNter:STATistics:VALue?` | — | documented; 只读查询当前计数器的统计信息（仅频率/周期模式有效）；手册该页无输入参数（手册 p.62） | 62 |
| `:CURSor:IXDelta` | `:CURSor:IXDelta?` | — | documented; 只读查询光标 1/(X2-X1) 的当前值；手册该页无输入参数（手册 p.68） | 68 |
| `:CURSor:MANual:X<n>` | `:CURSor:MANual:X<n>?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}` | documented; 指定手动 X 光标的开关（手册 p.74） | 74 |
| `:CURSor:MANual:X<n>:COLor` | `:CURSor:MANual:X<n>:COLor?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<color>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `DELTa` = follows the reference cursor, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定手动 X 光标的颜色（手册 p.74） | 74 |
| `:CURSor:MANual:X<n>:DFOLlow` | `:CURSor:MANual:X<n>:DFOLlow?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}`; only settable when the reference cursor source is not `NONE` | documented; 手动 X 光标与参考光标固定相对位置的开关（手册 p.75） | 75 |
| `:CURSor:MANual:X<n>:DTCursor` | `:CURSor:MANual:X<n>:DTCursor?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<source>` = `{MX<m>\|TRACK<t>\|NONE}`; `<m>` = manual X cursor index 1 to 8, `<t>` = track cursor index 1 to 8, `NONE` = no reference cursor | documented; 指定手动 X 光标的参考光标（手册 p.75） | 75 |
| `:CURSor:MANual:X<n>:DVALue` | `:CURSor:MANual:X<n>:DVALue?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), position relative to the reference cursor | documented; 指定手动 X 光标相对参考光标的位置（手册 p.76） | 76 |
| `:CURSor:MANual:X<n>:LABel` | `:CURSor:MANual:X<n>:LABel?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<state>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = empty label, `DELTa` = follows the reference cursor label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定手动 X 光标的标签（手册 p.76） | 76 |
| `:CURSor:MANual:X<n>:POSition` | `:CURSor:MANual:X<n>:POSition?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), [-horizontal divisions/2 * current timebase + horizontal delay, horizontal divisions/2 * current timebase + horizontal delay] | documented; 指定手动 X 光标的位置（手册 p.77） | 77 |
| `:CURSor:MANual:X<n>:SOURce` | `:CURSor:MANual:X<n>:SOURce?` | `<n>` = manual X cursor index, Integer (NR1), 1 to 8; `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>\|DIGital\|ZDIGital\|HISTOGram}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform, `HISTOGram` = waveform histogram | documented; 指定手动 X 光标的信源（手册 p.77） | 77 |
| `:CURSor:MANual:Y<n>` | `:CURSor:MANual:Y<n>?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}` | documented; 指定手动 Y 光标的开关（手册 p.78） | 78 |
| `:CURSor:MANual:Y<n>:COLor` | `:CURSor:MANual:Y<n>:COLor?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<color>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `DELTa` = follows the reference cursor, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定手动 Y 光标的颜色（手册 p.78） | 78 |
| `:CURSor:MANual:Y<n>:DFOLlow` | `:CURSor:MANual:Y<n>:DFOLlow?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}`; only settable when the reference cursor source is not `NONE` | documented; 手动 Y 光标与参考光标固定相对位置的开关（手册 p.79） | 79 |
| `:CURSor:MANual:Y<n>:DTCursor` | `:CURSor:MANual:Y<n>:DTCursor?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<source>` = `{MY<m>\|NONE}`; `<m>` = manual Y cursor index, `NONE` = no reference cursor | documented; 指定手动 Y 光标的参考光标（手册 p.79） | 79 |
| `:CURSor:MANual:Y<n>:DVALue` | `:CURSor:MANual:Y<n>:DVALue?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), position relative to the reference cursor | documented; 指定手动 Y 光标相对参考光标的位置（手册 p.80） | 80 |
| `:CURSor:MANual:Y<n>:LABel` | `:CURSor:MANual:Y<n>:LABel?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<state>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = empty label, `DELTa` = follows the reference cursor label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定手动 Y 光标的标签（手册 p.80） | 80 |
| `:CURSor:MANual:Y<n>:POSition` | `:CURSor:MANual:Y<n>:POSition?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), [-vertical divisions/2 * vertical scale + vertical offset, vertical divisions/2 * vertical scale + vertical offset] | documented; 指定手动 Y 光标的位置（手册 p.81） | 81 |
| `:CURSor:MANual:Y<n>:SOURce` | `:CURSor:MANual:Y<n>:SOURce?` | `<n>` = manual Y cursor index, Integer (NR1), 1 to 8; `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>\|HISTOGram}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform, `HISTOGram` = waveform histogram | documented; 指定手动 Y 光标的信源（手册 p.81） | 81 |
| `:CURSor:MEASure<n>` | `:CURSor:MEASure<n>?` | `<n>` = measurement cursor index, Integer (NR1), 1 to 4; `<state>` = `{ON\|OFF}` | documented; 指定测量光标 MEA 的开关（手册 p.82） | 82 |
| `:CURSor:MEASure<n>:COLor` | `:CURSor:MEASure<n>:COLor?` | `<n>` = measurement cursor index, Integer (NR1), 1 to 4; `<color>` = `{DEFault\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定测量光标 MEA 的颜色（手册 p.82） | 82 |
| `:CURSor:MEASure<n>:LABel` | `:CURSor:MEASure<n>:LABel?` | `<n>` = Integer (NR1) (manual prints the 1-to-8 track-cursor range here); `<state>` = `{DEFault\|CUSTom[,<string>]}`; `DEFault` = empty label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定测量光标 MEA 的标签（手册 p.83） | 83 |
| `:CURSor:MEASure<n>:MITem` | `:CURSor:MEASure<n>:MITem?` | `<n>` = measurement cursor index, Integer (NR1), 1 to 4; `<type>` = measurement item, same mnemonics as Table 5-1; `<source1>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|D<d>\|ZD<d>}`; `<source2>` = `{C<n>}`, required when the advanced item is a channel delay; `<m>` = memory waveform 1 to 4, `<d>` = digital channel 0 to 15, `Z<n>` is only valid while Zoom is on | documented; 指定测量光标 MEA 的测量项（手册 p.84） | 84 |
| `:CURSor:MITem` | `:CURSor:MITem?` | `<type>` = measurement item, same mnemonics as Table 5-1; `<source1>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|D<d>\|ZD<d>\|REF<r>}`; `<source2>` = `{C<n>}`, required when the advanced item is a channel delay; `<m>` = memory waveform 1 to 4, `<r>` = `{A\|B\|C\|D}` reference waveform, `<d>` = digital channel 0 to 15, `Z<n>` is only valid while Zoom is on | documented; 光标模式为测量光标时的测量项（手册 p.68） | 68 |
| `:CURSor:TAGStyle` | `:CURSor:TAGStyle?` | `<type>` = `{FIXed\|FOLLowing}` (fixed / following cursor style) | documented; 光标样式（手册 p.66） | 66 |
| `:CURSor:TRAC2:DTCursor` | `:CURSor:TRAC2:DTCursor?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<source>` = `{MX<m>\|TRACK<t>\|NONE}`; `<m>`/`<t>` = manual X / track cursor index 1 to 8, `NONE` = no reference cursor | documented; 指定追踪光标 TX 的参考光标（手册 p.86） | 86 |
| `:CURSor:TRACk<n>` | `:CURSor:TRACk<n>?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}` | documented; 指定追踪光标 TX 的开关（手册 p.76） | 76 |
| `:CURSor:TRACk<n>:COLor` | `:CURSor:TRACk<n>:COLor?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<color>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `DELTa` = follows the reference cursor, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定追踪光标 TX 的颜色（手册 p.85） | 85 |
| `:CURSor:TRACk<n>:DFOLlow` | `:CURSor:TRACk<n>:DFOLlow?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}`; only settable when the reference cursor source is not `NONE` | documented; 追踪光标 TX 与参考光标固定相对位置的开关（手册 p.85） | 85 |
| `:CURSor:TRACk<n>:DTCursor` | `:CURSor:TRACk<n>:DTCursor?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<source>` = `{MX<m>\|TRACK<t>\|NONE}`; `<m>`/`<t>` = manual X / track cursor index 1 to 8, `NONE` = no reference cursor | documented; 指定追踪光标 TX 的参考光标（手册 p.85） | 85 |
| `:CURSor:TRACk<n>:DVALue` | `:CURSor:TRACk<n>:DVALue?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), position relative to the reference cursor | documented; 指定追踪光标 TX 相对参考光标的位置（手册 p.86） | 86 |
| `:CURSor:TRACk<n>:LABel` | `:CURSor:TRACk<n>:LABel?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<state>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = empty label, `DELTa` = follows the reference cursor label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定追踪光标 TX 的标签（手册 p.87） | 87 |
| `:CURSor:TRACk<n>:POSition` | `:CURSor:TRACk<n>:POSition?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<value>` = Real (NR3), [-horizontal divisions/2 * current timebase + horizontal delay, horizontal divisions/2 * current timebase + horizontal delay] | documented; 指定追踪光标 TX 的水平位置（手册 p.87） | 87 |
| `:CURSor:TRACk<n>:SOURce` | `:CURSor:TRACk<n>:SOURce?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8; `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform | documented; 指定追踪光标 TX 的信源（手册 p.85） | 85 |
| `:CURSor:TRACk<n>:VALue` | `:CURSor:TRACk<n>:VALue?` | `<n>` = track cursor TX index, Integer (NR1), 1 to 8 | documented; 只读查询追踪光标 TX 的垂直方向位置（手册 p.88） | 88 |
| `:CURSor:XDELta` | `:CURSor:XDELta?` | — | documented; 只读查询光标 X2 与 X1 当前位置的水平差；手册该页无输入参数（手册 p.68） | 68 |
| `:CURSor:XREFerence` | `:CURSor:XREFerence?` | `<type>` = `{DELay\|POSition}`; `DELay` keeps the X cursor value when the timebase changes, `POSition` keeps its on-screen grid position | documented; X 光标参考的类型（手册 p.67） | 67 |
| `:CURSor:XY:X<n>` | `:CURSor:XY:X<n>?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<state>` = `{ON\|OFF}`; XY mode must be on, turning XY off turns these cursors off | documented; 指定 XY 模式 X 光标的开关（手册 p.89） | 89 |
| `:CURSor:XY:X<n>:COLor` | `:CURSor:XY:X<n>:COLor?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<color>` = `{DEFault\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定 XY 模式 X 光标的颜色（手册 p.89） | 89 |
| `:CURSor:XY:X<n>:DFOLlow` | `:CURSor:XY:X<n>:DFOLlow?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<state>` = `{ON\|OFF}`; only settable when the reference cursor source is not `NONE` | documented; XY 模式 X 光标与参考光标固定相对位置的开关（手册 p.90） | 90 |
| `:CURSor:XY:X<n>:DTCursor` | `:CURSor:XY:X<n>:DTCursor?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<source>` = `{XY_X<m>\|NONE}`; `<m>` = XY mode X cursor index 1 to 2, `NONE` = no reference cursor | documented; 指定 XY 模式 X 光标的参考光标（手册 p.90） | 90 |
| `:CURSor:XY:X<n>:DVALue` | `:CURSor:XY:X<n>:DVALue?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<value>` = Real (NR3), position relative to the reference cursor | documented; 指定 XY 模式 X 光标相对参考光标的位置（手册 p.91） | 91 |
| `:CURSor:XY:X<n>:LABel` | `:CURSor:XY:X<n>:LABel?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<state>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = empty label, `DELTa` = follows the reference cursor label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定 XY 模式 X 光标的标签（手册 p.91） | 91 |
| `:CURSor:XY:X<n>:POSition` | `:CURSor:XY:X<n>:POSition?` | `<n>` = XY mode X cursor index, Integer (NR1), 1 to 2; `<value>` = Real (NR3); manual lists no range on this page | documented; 指定 XY 模式 X 光标的位置（手册 p.92） | 92 |
| `:CURSor:XY:Y<n>` | `:CURSor:XY:Y<n>?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<state>` = `{ON\|OFF}`; XY mode must be on, turning XY off turns these cursors off | documented; 指定 XY 模式 Y 光标的开关（手册 p.92） | 92 |
| `:CURSor:XY:Y<n>:COLor` | `:CURSor:XY:Y<n>:COLor?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<color>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = colour of the cursor source, `DELTa` = follows the reference cursor, `CUSTom` needs `<string>` = quoted hexadecimal RGB code | documented; 指定 XY 模式 Y 光标的颜色（手册 p.93） | 93 |
| `:CURSor:XY:Y<n>:DFOLlow` | `:CURSor:XY:Y<n>:DFOLlow?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<state>` = `{ON\|OFF}`; only settable when the reference cursor source is not `NONE` | documented; XY 模式 Y 光标与参考光标固定相对位置的开关（手册 p.93） | 93 |
| `:CURSor:XY:Y<n>:DTCursor` | `:CURSor:XY:Y<n>:DTCursor?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<source>` = `{XY_Y<m>\|NONE}`; `<m>` = XY mode Y cursor index 1 to 2, `NONE` = no reference cursor | documented; 指定 XY 模式 Y 光标的参考光标（手册 p.93） | 93 |
| `:CURSor:XY:Y<n>:DVALue` | `:CURSor:XY:Y<n>:DVALue?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<value>` = Real (NR3), position relative to the reference cursor | documented; 指定 XY 模式 Y 光标相对参考光标的位置（手册 p.94） | 94 |
| `:CURSor:XY:Y<n>:LABel` | `:CURSor:XY:Y<n>:LABel?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<state>` = `{DEFault\|DELTa\|CUSTom[,<string>]}`; `DEFault` = empty label, `DELTa` = follows the reference cursor label, `CUSTom` needs `<string>` = quoted ASCII text, up to 20 characters | documented; 指定 XY 模式 Y 光标的标签（手册 p.95） | 95 |
| `:CURSor:XY:Y<n>:POSition` | `:CURSor:XY:Y<n>:POSition?` | `<n>` = XY mode cursor index, Integer (NR1), 1 to 2; `<value>` = Real (NR3); manual lists no range on this page | documented; 指定 XY 模式 Y 光标的位置（手册 p.95） | 95 |
| `:CURSor:YDELta` | `:CURSor:YDELta?` | — | documented; 只读查询光标 Y2 与 Y1 当前位置的垂直差；手册该页无输入参数（手册 p.72） | 72 |
| `:CURSor:YREFerence` | `:CURSor:YREFerence?` | `<type>` = `{OFFSet\|POSition}`; `OFFSet` keeps the Y cursor value when the vertical scale changes, `POSition` keeps its on-screen grid position | documented; Y 光标参考的类型（手册 p.67） | 67 |
| `:DECode:BUS1:M1553:LTHReshold` | `:DECode:BUS1:M1553:LTHReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:DECode:BUS<n>:M1553:UTHReshold`) | documented; M1553 总线解码的阈值低电平（手册 p.135） | 135 |
| `:DECode:BUS1:M1553:SOURce` | `:DECode:BUS1:M1553:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; M1553 总线解码的信源（手册 p.136） | 136 |
| `:DECode:BUS1:M1553:UTHReshold` | `:DECode:BUS1:M1553:UTHReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The high level must not be below the low level (`:DECode:BUS<n>:M1553:LTHReshold`) | documented; M1553 总线解码的阈值高电平（手册 p.136） | 136 |
| `:DECode:BUS<n>` | `:DECode:BUS<n>?` | `<n>` = `{1\|2}`, bus index; `<state>` = `{ON\|OFF}` | documented; 解码总线的显示状态（手册 p.98） | 98 |
| `:DECode:BUS<n>:CAN` | `:DECode:BUS<n>:CAN?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.119） | 119 |
| `:DECode:BUS<n>:CAN:BAUD` | `:DECode:BUS<n>:CAN:BAUD?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{5kbps\|10kbps\|20kbps\|50kbps\|100kbps\|125kbps\|250kbps\|500kbps\|800kbps\|1Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 5000 to 1000000 | documented; CAN 总线解码的波特率（手册 p.119） | 119 |
| `:DECode:BUS<n>:CAN:SOURce` | `:DECode:BUS<n>:CAN:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; CAN 总线解码的信源（手册 p.119） | 119 |
| `:DECode:BUS<n>:CAN:THReshold` | `:DECode:BUS<n>:CAN:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; CAN 总线解码的阈值（手册 p.120） | 120 |
| `:DECode:BUS<n>:CANFd` | `:DECode:BUS<n>:CANFd?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.125） | 125 |
| `:DECode:BUS<n>:CANFd:BAUDData` | `:DECode:BUS<n>:CANFd:BAUDData?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{500kbps\|1Mbps\|2Mbps\|5Mbps\|8Mbps\|10Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 100000 to 10000000 | documented; CAN FD 总线解码的数据波特率（手册 p.125） | 125 |
| `:DECode:BUS<n>:CANFd:BAUDNominal` | `:DECode:BUS<n>:CANFd:BAUDNominal?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{10kbps\|25kbps\|50kbps\|100kbps\|250kbps\|1Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 10000 to 1000000 | documented; CAN FD 总线解码的标准波特率（手册 p.125） | 125 |
| `:DECode:BUS<n>:CANFd:SOURce` | `:DECode:BUS<n>:CANFd:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; CAN FD 总线解码的信源（手册 p.126） | 126 |
| `:DECode:BUS<n>:CANFd:THReshold` | `:DECode:BUS<n>:CANFd:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; CAN FD 总线解码的阈值（手册 p.126） | 126 |
| `:DECode:BUS<n>:COPY` | `:DECode:BUS<n>:COPY?` | `<n>` = `{1\|2}`, bus index; `<operation>` = `{FROMtrigger\|TOTRigger}`; copy the trigger settings into the decode settings / the decode settings into the trigger settings | documented; 解码设置与触发设置同步（手册 p.99） | 99 |
| `:DECode:BUS<n>:FLEXray` | `:DECode:BUS<n>:FLEXray?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.123） | 123 |
| `:DECode:BUS<n>:FLEXray:BAUD` | `:DECode:BUS<n>:FLEXray:BAUD?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{2500kbps\|5Mbps\|10Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 1000000 to 20000000 | documented; FlexRay 总线解码的波特率（手册 p.123） | 123 |
| `:DECode:BUS<n>:FLEXray:SOURce` | `:DECode:BUS<n>:FLEXray:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; FlexRay 总线解码的信源（手册 p.123） | 123 |
| `:DECode:BUS<n>:FLEXray:THReshold` | `:DECode:BUS<n>:FLEXray:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; FlexRay 总线解码的阈值（手册 p.124） | 124 |
| `:DECode:BUS<n>:FORMat` | `:DECode:BUS<n>:FORMat?` | `<n>` = `{1\|2}`, bus index; `<format>` = `{BINary\|DECimal\|HEX\|ASCii}` | documented; 解码总线的数据格式（手册 p.99） | 99 |
| `:DECode:BUS<n>:IIC` | `:DECode:BUS<n>:IIC?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.101） | 101 |
| `:DECode:BUS<n>:IIC:RWBit` | `:DECode:BUS<n>:IIC:RWBit?` | `<n>` = `{1\|2}`, bus index; `<state>` = `{ON\|OFF}` | documented; IIC 总线解码结果是否包含读写位（手册 p.101） | 101 |
| `:DECode:BUS<n>:IIC:SCLSource` | `:DECode:BUS<n>:IIC:SCLSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIC 总线解码的 SCL（串行时钟线）信源（手册 p.101） | 101 |
| `:DECode:BUS<n>:IIC:SCLThreshold` | `:DECode:BUS<n>:IIC:SCLThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIC 总线解码的 SCL（串行时钟线）阈值（手册 p.102） | 102 |
| `:DECode:BUS<n>:IIC:SDASource` | `:DECode:BUS<n>:IIC:SDASource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIC 总线解码的 SDA（串行数据线）信源（手册 p.101） | 101 |
| `:DECode:BUS<n>:IIC:SDAThreshold` | `:DECode:BUS<n>:IIC:SDAThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIC 总线解码的 SDA（串行数据线）阈值（手册 p.103） | 103 |
| `:DECode:BUS<n>:IIS` | `:DECode:BUS<n>:IIS?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.128） | 128 |
| `:DECode:BUS<n>:IIS:ANNotate` | `:DECode:BUS<n>:IIS:ANNotate?` | `<n>` = `{1\|2}`, bus index; `<type>` = `{ALL\|LEFT\|RIGHt}` | documented; IIS 总线解码的注释通道（手册 p.128） | 128 |
| `:DECode:BUS<n>:IIS:AVARiant` | `:DECode:BUS<n>:IIS:AVARiant?` | `<n>` = `{1\|2}`, bus index; `<type>` = `{I2S\|LJ\|RJ}` (Audio-I2S / Audio-LJ / Audio-RJ) | documented; IIS 总线解码的音频格式（手册 p.128） | 128 |
| `:DECode:BUS<n>:IIS:BCLKSource` | `:DECode:BUS<n>:IIS:BCLKSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线解码的时钟（BCLK）源（手册 p.129） | 129 |
| `:DECode:BUS<n>:IIS:BCLKThreshold` | `:DECode:BUS<n>:IIS:BCLKThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线解码的时钟（BCLK）源阈值（手册 p.129） | 129 |
| `:DECode:BUS<n>:IIS:BITorder` | `:DECode:BUS<n>:IIS:BITorder?` | `<n>` = `{1\|2}`, bus index; `<order>` = `{LSB\|MSB}` (least / most significant bit first) | documented; IIS 总线解码的比特流格式（手册 p.130） | 130 |
| `:DECode:BUS<n>:IIS:DLENgth` | `:DECode:BUS<n>:IIS:DLENgth?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 1 to 32 | documented; IIS 总线解码的数据位数（手册 p.130） | 130 |
| `:DECode:BUS<n>:IIS:DSource` | `:DECode:BUS<n>:IIS:DSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线解码的数据源（手册 p.131） | 131 |
| `:DECode:BUS<n>:IIS:DTHReshold` | `:DECode:BUS<n>:IIS:DTHReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线解码的数据源阈值（手册 p.131） | 131 |
| `:DECode:BUS<n>:IIS:LATChedge` | `:DECode:BUS<n>:IIS:LATChedge?` | `<n>` = `{1\|2}`, bus index; `<slope>` = `{RISing\|FALLing}`; data is latched on the selected clock edge | documented; IIS 总线解码的时钟采样边沿（手册 p.132） | 132 |
| `:DECode:BUS<n>:IIS:LCH` | `:DECode:BUS<n>:IIS:LCH?` | `<n>` = `{1\|2}`, bus index; `<left>` = `{LOW\|HIGH}`; `LOW` selects the left channel while WS is low, `HIGH` selects it while WS is high | documented; IIS 总线解码的左声道极性（手册 p.132） | 132 |
| `:DECode:BUS<n>:IIS:SBIT` | `:DECode:BUS<n>:IIS:SBIT?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 1 to 31 | documented; IIS 总线解码的起始位（手册 p.133） | 133 |
| `:DECode:BUS<n>:IIS:WSSource` | `:DECode:BUS<n>:IIS:WSSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线解码的帧时钟（WS）源（手册 p.133） | 133 |
| `:DECode:BUS<n>:IIS:WSTHreshold` | `:DECode:BUS<n>:IIS:WSTHreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线解码的帧时钟（WS）阈值（手册 p.134） | 134 |
| `:DECode:BUS<n>:LIN` | `:DECode:BUS<n>:LIN?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.121） | 121 |
| `:DECode:BUS<n>:LIN:BAUD` | `:DECode:BUS<n>:LIN:BAUD?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{600bps\|1200bps\|2400bps\|4800bps\|9600bps\|19200bps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 300 to 20000000 | documented; LIN 总线解码的波特率（手册 p.121） | 121 |
| `:DECode:BUS<n>:LIN:SOURce` | `:DECode:BUS<n>:LIN:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; LIN 总线解码的信源（手册 p.121） | 121 |
| `:DECode:BUS<n>:LIN:THReshold` | `:DECode:BUS<n>:LIN:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; LIN 总线解码的阈值（手册 p.122） | 122 |
| `:DECode:BUS<n>:M1553` | `:DECode:BUS<n>:M1553?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.135） | 135 |
| `:DECode:BUS<n>:M1553:LTHReshold` | `:DECode:BUS<n>:M1553:LTHReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:DECode:BUS<n>:M1553:UTHReshold`) | documented; M1553 总线解码的阈值低电平（手册 p.135） | 135 |
| `:DECode:BUS<n>:M1553:SOURce` | `:DECode:BUS<n>:M1553:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; M1553 总线解码的信源（手册 p.135） | 135 |
| `:DECode:BUS<n>:M1553:UTHReshold` | `:DECode:BUS<n>:M1553:UTHReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The high level must not be below the low level (`:DECode:BUS<n>:M1553:LTHReshold`) | documented; M1553 总线解码的阈值高电平（手册 p.135） | 135 |
| `:DECode:BUS<n>:MANChester` | `:DECode:BUS<n>:MANChester?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.142） | 142 |
| `:DECode:BUS<n>:MANChester:BAUD` | `:DECode:BUS<n>:MANChester:BAUD?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 500 to 5000000 | documented; MANChester 总线解码的波特率（手册 p.143） | 143 |
| `:DECode:BUS<n>:MANChester:BITorder` | `:DECode:BUS<n>:MANChester:BITorder?` | `<n>` = `{1\|2}`, bus index; `<order>` = `{LSB\|MSB}` (least / most significant bit first) | documented; MANChester 总线解码的比特流格式（手册 p.148） | 148 |
| `:DECode:BUS<n>:MANChester:DISPlay` | `:DECode:BUS<n>:MANChester:DISPlay?` | `<n>` = `{1\|2}`, bus index; `<format>` = `{WORD\|BIT}` | documented; MANChester 总线解码的显示格式（手册 p.147） | 147 |
| `:DECode:BUS<n>:MANChester:DSIZe` | `:DECode:BUS<n>:MANChester:DSIZe?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 1 to 255 | documented; MANChester 总线解码的数据字长度（手册 p.147） | 147 |
| `:DECode:BUS<n>:MANChester:HSIZe` | `:DECode:BUS<n>:MANChester:HSIZe?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 0 to 32 | documented; MANChester 总线解码的头部字段长度（手册 p.145） | 145 |
| `:DECode:BUS<n>:MANChester:IBITs` | `:DECode:BUS<n>:MANChester:IBITs?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 2 to 32 | documented; MANChester 总线解码的帧间隔（手册 p.144） | 144 |
| `:DECode:BUS<n>:MANChester:IDLE` | `:DECode:BUS<n>:MANChester:IDLE?` | `<n>` = `{1\|2}`, bus index; `<idle>` = `{LOW\|HIGH}` (manual repeats `LOW` for both entries) | documented; MANChester 总线解码的空闲状态（手册 p.144） | 144 |
| `:DECode:BUS<n>:MANChester:POLarity` | `:DECode:BUS<n>:MANChester:POLarity?` | `<n>` = `{1\|2}`, bus index; `<polar>` = `{RISing\|FALLing}`; `RISing` treats a rising edge as logic 1, `FALLing` a falling edge | documented; MANChester 总线解码的极性（手册 p.143） | 143 |
| `:DECode:BUS<n>:MANChester:SOURce` | `:DECode:BUS<n>:MANChester:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; MANChester 总线解码的信源（手册 p.142） | 142 |
| `:DECode:BUS<n>:MANChester:SSIZe` | `:DECode:BUS<n>:MANChester:SSIZe?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 0 to 32 | documented; MANChester 总线解码的同步字段长度（手册 p.145） | 145 |
| `:DECode:BUS<n>:MANChester:STARt` | `:DECode:BUS<n>:MANChester:STARt?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 1 to 32 | documented; MANChester 总线解码的起始沿（手册 p.145） | 145 |
| `:DECode:BUS<n>:MANChester:THReshold` | `:DECode:BUS<n>:MANChester:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; MANChester 总线解码的阈值（手册 p.142） | 142 |
| `:DECode:BUS<n>:MANChester:TSIZe` | `:DECode:BUS<n>:MANChester:TSIZe?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 0 to 32 | documented; MANChester 总线解码的尾部字段长度（手册 p.146） | 146 |
| `:DECode:BUS<n>:MANChester:WSIZe` | `:DECode:BUS<n>:MANChester:WSIZe?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 2 to 8 | documented; MANChester 总线解码的字大小（手册 p.146） | 146 |
| `:DECode:BUS<n>:PROTocol` | `:DECode:BUS<n>:PROTocol?` | `<n>` = `{1\|2}`, bus index; `<protocol>` = `{IIC\|SPI\|UART\|CAN\|LIN\|FLEXray\|CANFd\|IIS\|M1553\|SENT\|MANchester\|ARINC429\|USB20}` (the return format prints `A429` for `ARINC429`) | documented; 解码总线的协议（手册 p.99） | 99 |
| `:DECode:BUS<n>:RESult` | `:DECode:BUS<n>:RESult?` | `<n>` = `{1\|2}`, bus index | documented; 只读查询解码总线的结果，返回 ASCII 文本（字段逗号分隔、帧分号分隔，首行为头部描述）；完整结果用 `:DECode:LIST<n>:RESult`（手册 p.100） | 100 |
| `:DECode:BUS<n>:SENT` | `:DECode:BUS<n>:SENT?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.137） | 137 |
| `:DECode:BUS<n>:SENT:CLOCk` | `:DECode:BUS<n>:SENT:CLOCk?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3), 500E-09 to 300E-06 | documented; SENT 总线解码的时钟周期（手册 p.138） | 138 |
| `:DECode:BUS<n>:SENT:CRC` | `:DECode:BUS<n>:SENT:CRC?` | `<n>` = `{1\|2}`, bus index; `<state>` = `{OFF\|ON}` (`ON` = 2010 CRC format, `OFF` = 2008 CRC format) | documented; SENT 总线解码的 CRC 校验格式（手册 p.140） | 140 |
| `:DECode:BUS<n>:SENT:FORMat` | `:DECode:BUS<n>:SENT:FORMat?` | `<n>` = `{1\|2}`, bus index; `<format>` = `{NIBBles\|FSIGnal\|SSERial\|ESERial}` | documented; SENT 总线解码的消息格式（手册 p.138） | 138 |
| `:DECode:BUS<n>:SENT:IDLE` | `:DECode:BUS<n>:SENT:IDLE?` | `<n>` = `{1\|2}`, bus index; `<idle>` = `{LOW\|HIGH}` (manual repeats `LOW` for both entries) | documented; SENT 总线解码的空闲状态（手册 p.139） | 139 |
| `:DECode:BUS<n>:SENT:LENGth` | `:DECode:BUS<n>:SENT:LENGth?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 3 to 8 | documented; SENT 总线解码的半字节数（手册 p.140） | 140 |
| `:DECode:BUS<n>:SENT:PPULse` | `:DECode:BUS<n>:SENT:PPULse?` | `<state>` = `{OFF\|ON}`; manual lists no bus index for this command | documented; SENT 总线解码的可变暂停位状态（手册 p.141） | 141 |
| `:DECode:BUS<n>:SENT:SOURce` | `:DECode:BUS<n>:SENT:SOURce?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SENT 总线解码的信源（手册 p.137） | 137 |
| `:DECode:BUS<n>:SENT:THReshold` | `:DECode:BUS<n>:SENT:THReshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SENT 总线解码的阈值（手册 p.137） | 137 |
| `:DECode:BUS<n>:SENT:TOLerance` | `:DECode:BUS<n>:SENT:TOLerance?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1) percent, 1 to 25 | documented; SENT 总线解码时钟周期的容差（手册 p.139） | 139 |
| `:DECode:BUS<n>:SPI` | `:DECode:BUS<n>:SPI?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.104） | 104 |
| `:DECode:BUS<n>:SPI:BITorder` | `:DECode:BUS<n>:SPI:BITorder?` | `<n>` = `{1\|2}`, bus index; `<order>` = `{LSB\|MSB}` (least / most significant bit first) | documented; SPI 总线解码的比特流格式（手册 p.104） | 104 |
| `:DECode:BUS<n>:SPI:CLKSource` | `:DECode:BUS<n>:SPI:CLKSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线解码的 CLK（时钟）信源（手册 p.104） | 104 |
| `:DECode:BUS<n>:SPI:CLKThreshold` | `:DECode:BUS<n>:SPI:CLKThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线解码的 CLK（时钟）阈值（手册 p.105） | 105 |
| `:DECode:BUS<n>:SPI:CSSource` | `:DECode:BUS<n>:SPI:CSSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线解码的 CS（片选）信源（手册 p.105） | 105 |
| `:DECode:BUS<n>:SPI:CSTYpe` | `:DECode:BUS<n>:SPI:CSTYpe?` | `<n>` = `{1\|2}`, bus index; `<type>` = `{NCS\|CS\|TIMeout[,<time>]}`; `NCS` frames on chip select low, `CS` on chip select high, `TIMeout` needs no CS source but `<time>` = Real (NR3), 1.00E-07 to 5.00E-03 (minimum clock-idle time) | documented; SPI 总线解码的片选类型（手册 p.107） | 107 |
| `:DECode:BUS<n>:SPI:CSThreshold` | `:DECode:BUS<n>:SPI:CSThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线解码的 CS（片选）阈值（手册 p.106） | 106 |
| `:DECode:BUS<n>:SPI:DLENgth` | `:DECode:BUS<n>:SPI:DLENgth?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 4 to 32 | documented; SPI 总线解码的数据位宽（手册 p.107） | 107 |
| `:DECode:BUS<n>:SPI:LATChedge` | `:DECode:BUS<n>:SPI:LATChedge?` | `<n>` = `{1\|2}`, bus index; `<slope>` = `{RISing\|FALLing}` | documented; SPI 总线解码的 CLK（时钟）采样边沿（手册 p.108） | 108 |
| `:DECode:BUS<n>:SPI:MISOSource` | `:DECode:BUS<n>:SPI:MISOSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>\|DIS}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1, `DIS` = disabled | documented; SPI 总线解码的 MISO 信源（手册 p.108） | 108 |
| `:DECode:BUS<n>:SPI:MISOThreshold` | `:DECode:BUS<n>:SPI:MISOThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线解码的 MISO 阈值（手册 p.109） | 109 |
| `:DECode:BUS<n>:SPI:MOSISource` | `:DECode:BUS<n>:SPI:MOSISource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>\|DIS}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1, `DIS` = disabled | documented; SPI 总线解码的 MOSI 信源（手册 p.109） | 109 |
| `:DECode:BUS<n>:SPI:MOSIThreshold` | `:DECode:BUS<n>:SPI:MOSIThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线解码的 MOSI 阈值（手册 p.110） | 110 |
| `:DECode:BUS<n>:SPI:NCSSource` | `:DECode:BUS<n>:SPI:NCSSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线解码的 NCS 信源（手册 p.111） | 111 |
| `:DECode:BUS<n>:SPI:NCSThreshold` | `:DECode:BUS<n>:SPI:NCSThreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线解码的 NCS 阈值（手册 p.111） | 111 |
| `:DECode:BUS<n>:UART` | `:DECode:BUS<n>:UART?` | — | documented; 章节标题，本节无独立参数；该协议的设置都在其子命令中（手册 p.113） | 113 |
| `:DECode:BUS<n>:UART:BAUD` | `:DECode:BUS<n>:UART:BAUD?` | `<n>` = `{1\|2}`, bus index; `<baud>` = `{600bps\|1200bps\|2400bps\|4800bps\|9600bps\|19200bps\|38400bps\|57600bps\|115200bps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 300 to 20000000 | documented; UART 总线解码的波特率（手册 p.113） | 113 |
| `:DECode:BUS<n>:UART:BITorder` | `:DECode:BUS<n>:UART:BITorder?` | `<n>` = `{1\|2}`, bus index; `<order>` = `{LSB\|MSB}` (least / most significant bit first) | documented; UART 总线解码的比特流格式（手册 p.113） | 113 |
| `:DECode:BUS<n>:UART:DLENgth` | `:DECode:BUS<n>:UART:DLENgth?` | `<n>` = `{1\|2}`, bus index; `<value>` = Integer (NR1), 5 to 8 | documented; UART 总线解码的数据长度（手册 p.114） | 114 |
| `:DECode:BUS<n>:UART:IDLE` | `:DECode:BUS<n>:UART:IDLE?` | `<n>` = `{1\|2}`, bus index; `<idle>` = `{LOW\|HIGH}` | documented; UART 总线解码的空闲电平（手册 p.114） | 114 |
| `:DECode:BUS<n>:UART:PARity` | `:DECode:BUS<n>:UART:PARity?` | `<n>` = `{1\|2}`, bus index; `<parity>` = `{NONE\|ODD\|EVEN\|MARK\|SPACe}` (none / odd / even / mark = 1 / space = 0) | documented; UART 总线解码的奇偶校验（手册 p.115） | 115 |
| `:DECode:BUS<n>:UART:RXSource` | `:DECode:BUS<n>:UART:RXSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>\|DIS}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1, `DIS` = disabled | documented; UART 总线解码的 RX 信源（手册 p.115） | 115 |
| `:DECode:BUS<n>:UART:RXTHreshold` | `:DECode:BUS<n>:UART:RXTHreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; UART 总线解码的 RX 阈值（手册 p.116） | 116 |
| `:DECode:BUS<n>:UART:STOP` | `:DECode:BUS<n>:UART:STOP?` | `<n>` = `{1\|2}`, bus index; `<bit>` = `{1\|1.5\|2}` | documented; UART 总线解码的停止位数（手册 p.116） | 116 |
| `:DECode:BUS<n>:UART:TXSource` | `:DECode:BUS<n>:UART:TXSource?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{C<n>\|D<d>\|DIS}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1, `DIS` = disabled | documented; UART 总线解码的 TX 信源（手册 p.117） | 117 |
| `:DECode:BUS<n>:UART:TXTHreshold` | `:DECode:BUS<n>:UART:TXTHreshold?` | `<n>` = `{1\|2}`, bus index; `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; UART 总线解码的 TX 阈值（手册 p.117） | 117 |
| `:DECode:LIST` | `:DECode:LIST?` | `<state>` = `{OFF\|D1\|D2}` (`OFF` hides the list, `D1`/`D2` shows the list of bus 1 / bus 2) | documented; 解码列表状态（手册 p.96） | 96 |
| `:DECode:LIST:LINE` | `:DECode:LIST:LINE?` | `<value>` = Integer (NR1), 1 to 7 | documented; 解码列表显示的行数（手册 p.97） | 97 |
| `:DECode:LIST:SCRoll` | `:DECode:LIST:SCRoll?` | `<value>` = Integer (NR1); manual lists no range on this page | documented; 解码列表选定行（手册 p.97） | 97 |
| `:DECode:LIST<n>:RESult` | `:DECode:LIST<n>:RESult?` | `<n>` = `{1\|2}`, list index of the corresponding bus | documented; 只读查询指定解码列表的结果（手册 p.98） | 98 |
| `:DIGital:ACTive` | `:DIGital:ACTive?` | `<digital>` = `{D<d>}`; `<d>` = channel index, Integer (NR1) | documented; 当前激活的数字通道（手册 p.149） | 149 |
| `:DIGital:BUS<n>:DEFault` | `:DIGital:BUS<n>:DEFault?` | `<n>` = `{1\|2}`, bus index | documented; 重置数字通道总线的比特位顺序（手册 p.150） | 150 |
| `:DIGital:BUS<n>:DISPlay` | `:DIGital:BUS<n>:DISPlay?` | `<n>` = `{1\|2}`, bus index; `<state>` = `{ON\|OFF}` | documented; 数字通道总线的显示状态（手册 p.150） | 150 |
| `:DIGital:BUS<n>:FORMat` | `:DIGital:BUS<n>:FORMat?` | `<n>` = `{1\|2}`, bus index; `<format>` = `{BINary\|DECimal\|UDECimal\|HEX}` | documented; 数字通道总线的显示格式（手册 p.150） | 150 |
| `:DIGital:BUS<n>:MAP` | `:DIGital:BUS<n>:MAP?` | `<n>` = `{1\|2}`, bus index; `<source>` = `{D<d>}`, one entry per bit, `<d>` = channel index Integer (NR1); the number of values sets the bus width | documented; 数字总线的位宽与各位对应的通道（手册 p.151） | 151 |
| `:DIGital:D<d>` | `:DIGital:D<d>?` | `<d>` = channel index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; 指定数字通道的开关（手册 p.152） | 152 |
| `:DIGital:HEIGht` | `:DIGital:HEIGht?` | `<value>` = Real (NR3), 4.00E+00 to 8.00E+00 | documented; 数字通道的显示高度（手册 p.152） | 152 |
| `:DIGital:LABel<d>` | `:DIGital:LABel<d>?` | `<d>` = channel index, Integer (NR1); `<qstring>` = quoted ASCII text, up to 8 characters | documented; 指定数字通道的标签字符（手册 p.153） | 153 |
| `:DIGital:POINts` | `:DIGital:POINts?` | — | documented; 只读查询数字通道当前的采样点数；手册该页无输入参数（手册 p.153） | 153 |
| `:DIGital:POSition` | `:DIGital:POSition?` | `<value>` = Real (NR3), vertical position in divisions; the range changes with the number of enabled digital channels | documented; 数字通道的显示位置（手册 p.153） | 153 |
| `:DIGital:SKEW` | `:DIGital:SKEW?` | `<value>` = Real (NR3), -1.00E-07 to 1.00E-07 | documented; 数字通道的时滞（手册 p.154） | 154 |
| `:DIGital:SRATe` | `:DIGital:SRATe?` | — | documented; 只读查询数字通道当前的采样率；手册该页无输入参数（手册 p.154） | 154 |
| `:DIGital:THReshold<n>` | `:DIGital:THReshold<n>?` | `<n>` = `{1\|2}` (channel group 1 = D0-D7, group 2 = D8-D15); `<type>` = `{TTL\|CMOS\|LVCMOS33\|LVCMOS25\|CUSTom[,<value>]}`; `<value>` = Real (NR3), range depends on model - SDS800X HD: [-8E-1, 8E-1] | documented; 数字通道组的阈值（手册 p.155） | 155 |
| `:DISPlay:AXIS` | `:DISPlay:AXIS?` | `<state>` = `{ON\|OFF}` | documented; 轴标签显示状态（手册 p.156） | 156 |
| `:DISPlay:AXIS:MODE` | `:DISPlay:AXIS:MODE?` | `<mode>` = `{FIXed\|MOVing}`; `FIXed` keeps the axis position fixed while the coordinates follow the waveform, `MOVing` moves the axis with the waveform | documented; 轴标签显示模式（手册 p.156） | 156 |
| `:DISPlay:AXIS:POSition` | `:DISPlay:AXIS:POSition?` | `<pos>` = `{LEFT\|MIDDle\|RIGHt}` (vertical axis at the left / middle / right of the screen) | documented; 轴标签垂直轴的显示位置（手册 p.157） | 157 |
| `:DISPlay:BACKlight` | `:DISPlay:BACKlight?` | `<value>` = Integer (NR1) percent, 0 to 100 | documented; 屏幕亮度（手册 p.157） | 157 |
| `:DISPlay:CLEar` | `:DISPlay:CLEar?` | — | documented; 事件命令（无参数），清除当前屏幕内显示的波形（手册 p.157） | 157 |
| `:DISPlay:COLor` | `:DISPlay:COLor?` | `<state>` = `{ON\|OFF}` | documented; 色温状态（手册 p.158） | 158 |
| `:DISPlay:GRATicule` | `:DISPlay:GRATicule?` | `<value>` = Integer (NR1) percent, 0 to 100 | documented; 网格亮度（手册 p.158） | 158 |
| `:DISPlay:GRIDstyle` | `:DISPlay:GRIDstyle?` | `<mode>` = `{FULL\|LIGHt\|NONE}`; `FULL` = 8 x 10 grid, `LIGHt` splits the screen into four, `NONE` = no grid | documented; 网格的显示模式（手册 p.159） | 159 |
| `:DISPlay:HIDemenu` | `:DISPlay:HIDemenu?` | — | documented; 事件命令（无参数），隐藏右侧菜单（手册 p.159） | 159 |
| `:DISPlay:INTensity` | `:DISPlay:INTensity?` | `<value>` = Integer (NR1) percent, 0 to 100 | documented; 波形亮度（手册 p.159） | 159 |
| `:DISPlay:MENU` | `:DISPlay:MENU?` | `<mode>` = `{EMBedded\|FLOating}` (embedded / floating menu) | documented; 菜单的显示样式（手册 p.160） | 160 |
| `:DISPlay:MENU:HIDE` | `:DISPlay:MENU:HIDE?` | `<time>` = `{OFF\|3S\|5S\|10S\|30S\|60S}`; `OFF` disables auto-hide | documented; 隐藏菜单的时间（手册 p.160） | 160 |
| `:DISPlay:TRANsparence` | `:DISPlay:TRANsparence?` | `<value>` = Integer (NR1) percent, 0 to 100 | documented; 信息显示框的透明度（仅 SHS800X/SHS1000X）（手册 p.162） | 162 |
| `:DISPlay:TYPE` | `:DISPlay:TYPE?` | `<type>` = `{VECTor\|DOT}`; `VECTor` connects the samples, `DOT` shows the raw samples | documented; 波形的显示类型（手册 p.162） | 162 |
| `:DVM:ALARm` | `:DVM:ALARm?` | `<state>` = `{ON\|OFF}` | documented; DVM 超量程报警开关（手册 p.163） | 163 |
| `:DVM:ARANge` | `:DVM:ARANge?` | `<state>` = `{ON\|OFF}` | documented; DVM 自动量程开关（手册 p.164） | 164 |
| `:DVM:CURRent` | `:DVM:CURRent?` | — | documented; 只读查询 DVM 当前模式下的测量值（默认 3 位有效数字）；手册该页无输入参数（手册 p.164） | 164 |
| `:DVM:HOLD` | `:DVM:HOLD?` | `<state>` = `{ON\|OFF}` | documented; DVM 保持开关（保持显示值，后台仍持续测量）（手册 p.164） | 164 |
| `:DVM:MODE` | `:DVM:MODE?` | `<mode>` = `{DCavg\|DCRMs\|ACRMs\|PKPK\|AMPLitude}` (DC average / DC RMS / AC RMS / peak-to-peak / amplitude) | documented; DVM 测量模式（手册 p.165） | 165 |
| `:DVM:SOURce` | `:DVM:SOURce?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; DVM 测量的信源（手册 p.165） | 165 |
| `:FUNCtion:FFTDisplay` | `:FUNCtion:FFTDisplay?` | `<mode>` = `{SPLit\|FULL\|EXCLusive}`; `SPLit` = time domain on top, frequency domain below, `FULL` = both on one screen, `EXCLusive` = spectrum analyser view | documented; FFT 显示模式（手册 p.166） | 166 |
| `:FUNCtion:GVALue` | `:FUNCtion:GVALue?` | `<valueA/B>` = Real (NR3), [-horizontal divisions/2 * current timebase + horizontal delay, horizontal divisions/2 * current timebase + horizontal delay]; A above B clamps to B and vice versa | documented; 数学函数积分门限阈值（手册 p.166） | 166 |
| `:FUNCtion1:DIFF:DX` | `:FUNCtion1:DIFF:DX?` | `<x>` = math function index, Integer (NR1); `<dx>` = step, Integer (NR1) | documented; 数学函数导数的步长（手册 p.168） | 168 |
| `:FUNCtion1:ERES:BITS` | `:FUNCtion1:ERES:BITS?` | `<x>` = math function index, Integer (NR1); `<bits>` = `{0.5\|1.0\|1.5\|2.0\|2.5\|3.0}` | documented; 数学函数增强分辨率的增强位数（手册 p.168） | 168 |
| `:FUNCtion1:FFT:AUToset` | `:FUNCtion1:FFT:AUToset?` | `<x>` = math function index, Integer (NR1); `<mode>` = `{SPAN\|PEAK\|NORMal}` (full span / peak centred / centre at the fundamental with span = half the FFT sample rate) | documented; 自动设置 FFT 波形的水平与垂直参数（手册 p.169） | 169 |
| `:FUNCtion1:FFT:HCENter` | `:FUNCtion1:FFT:HCENter?` | `<x>` = math function index, Integer (NR1); `<center>` = Real (NR3); the range depends on the FFT sample rate | documented; FFT 的中心频率（手册 p.169） | 169 |
| `:FUNCtion1:FFT:LOAD` | `:FUNCtion1:FFT:LOAD?` | `<x>` = math function index, Integer (NR1); `<load>` = Integer (NR1), 1 to 1000000 | documented; FFT 的外部负载（手册 p.171） | 171 |
| `:FUNCtion1:FFT:MODE` | `:FUNCtion1:FFT:MODE?` | `<x>` = math function index, Integer (NR1); `<mode>` = `{NORMal\|MAXHold\|AVERage[,<num>]}`; `AVERage` needs `<num>` = Integer (NR1), 4 to 1024 | documented; FFT 的采集模式（手册 p.171） | 171 |
| `:FUNCtion1:FFT:POINts` | `:FUNCtion1:FFT:POINts?` | `<x>` = math function index, Integer (NR1); `<point>` = `{1k\|2k\|4k\|8k\|16k\|32k\|64k\|128k\|256k\|512k\|1M\|2M}` on SDS800X HD (larger sets are listed for other models) | documented; FFT 最大点数（手册 p.172） | 172 |
| `:FUNCtion1:FFT:RLEVel` | `:FUNCtion1:FFT:RLEVel?` | `<x>` = math function index, Integer (NR1); `<level>` = Real (NR3); the range depends on the probe factor and the FFT unit (dBVrms / Vrms / dBm), see the manual's table on p.173 | documented; FFT 的参考电平（手册 p.173） | 173 |
| `:FUNCtion1:FFT:SCALe` | `:FUNCtion1:FFT:SCALe?` | `<x>` = math function index, Integer (NR1); `<scale>` = Real (NR3), `dBVrms` 1.00E-01 to 2.00E+01, `Vrms` 1.00E-03 to 1.00E+01, `dBm` 1.00E-01 to 2.00E+01 | documented; FFT 的垂直档位（手册 p.174） | 174 |
| `:FUNCtion<x>:FFT:HSCale` | `:FUNCtion<x>:FFT:HSCale?` | query only; returns `<scale>` NR3 (Hz/div) | documented; FFT horizontal scale, manual writes the instance as `<x>` (body examples use `FUNC2:FFT:HSC?`) | 170 |
| `:FUNCtion<x>:FFT:SEARch:RESult` | `:FUNCtion<x>:FFT:SEARch:RESult?` | query only; returns `<type>,<no>,<freq>,<ampl>` with `<type>` = `{Markers\|Peaks}` | documented; FFT search result list, one entry per query — preserve the raw text, it is not a single number | 177 |

| `:FUNCtion1:FFT:SEARch` | `:FUNCtion1:FFT:SEARch?` | `<x>` = math function index, Integer (NR1); `<type>` = `{OFF\|PEAK\|MARKer}` | documented; FFT 的搜索工具类型（手册 p.174） | 174 |
| `:FUNCtion1:FFT:SEARch:EXCursion` | `:FUNCtion1:FFT:SEARch:EXCursion?` | `<x>` = math function index, Integer (NR1); `<value>` = Real (NR3), range depends on the FFT unit; with `dBVrms` it is 0 to 1.60E+02 | documented; FFT 搜索工具的峰值偏移（手册 p.175） | 175 |
| `:FUNCtion1:FFT:SEARch:MARKer1` | `:FUNCtion1:FFT:SEARch:MARKer1?` | `<x>` = math function index, Integer (NR1); `<n>` = marker index, Integer (NR1), 1 to 8; `<freq>` = `{NPeak\|NAMPlitude\|<value>}` (`NPeak` = next peak, `NAMPlitude` = next amplitude, `<value>` = frequency Real NR3) | documented; 设置 FFT 指定标记的频率（手册 p.175） | 175 |
| `:FUNCtion1:FFT:SEARch:MARKer2:SHOW` | `:FUNCtion1:FFT:SEARch:MARKer2:SHOW?` | `<x>` = math function index, Integer (NR1); `<n>` = marker index, Integer (NR1), 1 to 8; `<state>` = `{ON\|OFF}` | documented; FFT 指定标记的开关（手册 p.176） | 176 |
| `:FUNCtion1:FFT:SEARch:MON` | `:FUNCtion1:FFT:SEARch:MON?` | `<x>` = math function index, Integer (NR1); `<type>` = `{PEAK\|HARMonics}` (mark peaks / mark harmonics) | documented; FFT 标记的方式（手册 p.176） | 176 |
| `:FUNCtion1:FFT:SEARch:PORDer` | `:FUNCtion1:FFT:SEARch:PORDer?` | `<x>` = math function index, Integer (NR1); `<type>` = `{AMPLitude\|FREQuency}` | documented; FFT 峰值的排序方式（手册 p.176） | 176 |
| `:FUNCtion1:FFT:SEARch:TABLe` | `:FUNCtion1:FFT:SEARch:TABLe?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; FFT 搜索表格的开关（手册 p.178） | 178 |
| `:FUNCtion1:FFT:SEARch:TABLe:DELTa` | `:FUNCtion1:FFT:SEARch:TABLe:DELTa?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; FFT 搜索表格中增量的显示状态（手册 p.178） | 178 |
| `:FUNCtion1:FFT:SEARch:TABLe:FREQuency` | `:FUNCtion1:FFT:SEARch:TABLe:FREQuency?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; FFT 搜索表格中频率的显示状态（手册 p.179） | 179 |
| `:FUNCtion1:FFT:SEARch:THReshold` | `:FUNCtion1:FFT:SEARch:THReshold?` | `<x>` = math function index, Integer (NR1); `<value>` = Real (NR3), range depends on the FFT unit; with `dBVrms` it is -1.60E+02 to 8.00E+01 | documented; FFT 搜索工具的峰值阈值（手册 p.179） | 179 |
| `:FUNCtion1:FFT:SPAN` | `:FUNCtion1:FFT:SPAN?` | `<x>` = math function index, Integer (NR1); `<span>` = Real (NR3); manual lists no range on this page | documented; FFT 的频率范围（手册 p.170） | 170 |
| `:FUNCtion1:FFT:UNIT` | `:FUNCtion1:FFT:UNIT?` | `<x>` = math function index, Integer (NR1); `<unit>` = `{DBVrms\|Vrms\|DBm}` | documented; FFT 的单位（手册 p.179） | 179 |
| `:FUNCtion1:FFT:WINDow` | `:FUNCtion1:FFT:WINDow?` | `<x>` = math function index, Integer (NR1); `<window>` = `{RECTangle\|BLACkman\|HANNing\|HAMMing\|FLATtop}` | documented; FFT 的窗口类型（手册 p.180） | 180 |
| `:FUNCtion1:FILTer:HFRequency` | `:FUNCtion1:FILTer:HFRequency?` | `<x>` = math function index, Integer (NR1); `<value>` = Real (NR3); manual lists no range on this page | documented; 滤波算子（带通/带阻）的上限截止频率（手册 p.181） | 181 |
| `:FUNCtion1:FILTer:LFRequency` | `:FUNCtion1:FILTer:LFRequency?` | `<x>` = math function index, Integer (NR1); `<value>` = Real (NR3); manual lists no range on this page | documented; 滤波算子（带通/带阻）的下限截止频率（手册 p.181） | 181 |
| `:FUNCtion1:FILTer:TYPE` | `:FUNCtion1:FILTer:TYPE?` | `<x>` = math function index, Integer (NR1); `<type>` = `{LPASs\|HPASs\|BPASs\|BREJect}` (low-pass / high-pass / band-pass / band-reject) | documented; 滤波算子的滤波类型（手册 p.181） | 181 |
| `:FUNCtion1:INTErpolate:COEF` | `:FUNCtion1:INTErpolate:COEF?` | `<x>` = math function index, Integer (NR1); `<coef>` = `{2\|5\|10\|20}` | documented; 数学函数插值的插值系数（手册 p.183） | 183 |
| `:FUNCtion1:INTegrate:GATE` | `:FUNCtion1:INTegrate:GATE?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; 数学函数积分门限开关（手册 p.182） | 182 |
| `:FUNCtion1:INTegrate:OFFSet` | `:FUNCtion1:INTegrate:OFFSet?` | `<x>` = math function index, Integer (NR1); `<offset>` = Real (NR3), [-100 * pixel, 100 * pixel] | documented; 积分算子的偏移（手册 p.183） | 183 |
| `:FUNCtion1:INVert` | `:FUNCtion1:INVert?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; 数学函数反相开关（手册 p.184） | 184 |
| `:FUNCtion1:LABel` | `:FUNCtion1:LABel?` | `<x>` = math function index, Integer (NR1); `<state>` = `{ON\|OFF}` | documented; 数学函数标签开关（手册 p.184） | 184 |
| `:FUNCtion1:LABel:TEXT` | `:FUNCtion1:LABel:TEXT?` | `<n>` = math function index, Integer (NR1); `<qstring>` = quoted ASCII text, up to 20 characters | documented; 指定数学函数的标签字符（手册 p.184） | 184 |
| `:FUNCtion1:MAXHold:SWeeps` | `:FUNCtion1:MAXHold:SWeeps?` | `<x>` = math function index, Integer (NR1); `<value>` = Integer (NR1), 0 to 2147483646; 0 means unlimited | documented; 数学函数最大保持的扫描限制（手册 p.185） | 185 |
| `:FUNCtion1:MINHold:SWeeps` | `:FUNCtion1:MINHold:SWeeps?` | `<x>` = math function index, Integer (NR1); `<value>` = Integer (NR1), 1 to 2147483646 (the page also states 0 means unlimited) | documented; 数学函数最小保持的扫描限制（手册 p.185） | 185 |
| `:FUNCtion1:OPERation` | `:FUNCtion1:OPERation?` | `<x>` = math function index, Integer (NR1); `<operation>` = `{ADD\|SUBTract\|MULTiply\|DIVision\|INTegrate\|DIFF\|FFT\|SQRT\|ERES\|AVERage\|ABSolute\|SIGN\|IDENtity\|NEGation\|EXP\|TEN\|LN\|LOG\|INTErpolate\|MAXHold\|MINHold\|FILTer}` | documented; 数学函数的算子（手册 p.186） | 186 |
| `:FUNCtion1:POSition` | `:FUNCtion1:POSition?` | `<x>` = math function index, Integer (NR1); `<offset>` = Real (NR3), [-1E+5, 1E+5]; the range depends on the operator type | documented; 数学函数的垂直位移（手册 p.186） | 186 |
| `:FUNCtion1:SCALe` | `:FUNCtion1:SCALe?` | `<x>` = math function index, Integer (NR1); `<scale>` = Real (NR3), [5E-4, 1E+4]; the range depends on the function source, and for integral/derivative operators on the timebase | documented; 数学函数的垂直档位（手册 p.187） | 187 |
| `:FUNCtion1:SOURce1` | `:FUNCtion1:SOURce1?` | `<x>` = math function index, Integer (NR1); `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform. `Z<n>` is only valid while Zoom is on, and a function cannot use itself as a source | documented; 指定数学函数的信源 A（手册 p.187） | 187 |
| `:FUNCtion1:SOURce2` | `:FUNCtion1:SOURce2?` | `<x>` = math function index, Integer (NR1); `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform. `Z<n>` is only valid while Zoom is on, and a function cannot use itself as a source | documented; 指定数学函数的信源 B（手册 p.188） | 188 |
| `:FUNCtion2:AVERage:NUM` | `:FUNCtion2:AVERage:NUM?` | `<x>` = math function index, Integer (NR1); `<num>` = `{4\|16\|32\|64\|128\|256\|512\|1024}` on SDS800X HD (larger sets are listed for other models) | documented; 平均算子的平均次数（手册 p.168） | 168 |
| `:FUNCtion2:FFT:RESET` | `:FUNCtion2:FFT:RESET?` | `<x>` = math function index, Integer (NR1); no other parameter | documented; FFT 采集模式为平均时，让 FFT 重新开始计数（手册 p.172） | 172 |
| `:HISTORy:LIST` | `:HISTORy:LIST?` | `<state>` = `{OFF\|ON[,<type>]}`, `<type>` = `{TIME\|DELTa}` (list by sample time / by sample interval) | documented; 历史波形列表的开关（手册 p.190） | 190 |
| `:HISTORy:TIME` | `:HISTORy:TIME?` | — | documented; 只读查询当前历史帧的时间戳（时:分:秒）；手册该页无输入参数（手册 p.191） | 191 |
| `:MEASure:ADVanced:CLEar` | `:MEASure:ADVanced:CLEar?` | — | documented; 事件命令（无参数），清除所有高级测量项（手册 p.192） | 192 |
| `:MEASure:ADVanced:LINenumber` | `:MEASure:ADVanced:LINenumber?` | `<value>` = total number of displayed measurements, Integer (NR1), 1 to 12 | documented; 高级测量 M2 模式下显示的测量项总数（手册 p.192） | 192 |
| `:MEASure:ADVanced:P1:SOURce1` | `:MEASure:ADVanced:P1:SOURce1?` | `<n>` = measurement index, Integer (NR1), 1 to 12; `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>\|D<d>\|ZD<d>\|REF<r>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform, `<d>` = digital channel (0 to 15), `<r>` = `{A\|B\|C\|D}` | documented; 指定高级测量项的信源 A（手册 p.194） | 194 |
| `:MEASure:ADVanced:P1:SOURce2` | `:MEASure:ADVanced:P1:SOURce2?` | `<n>` = measurement index, Integer (NR1), 1 to 12; `<source>` = `{C<n>\|F<x>}` (`<n>` = analog/zoom channel, `<x>` = math function); required for delay measurements | documented; 指定高级测量项的信源 B（手册 p.194） | 194 |
| `:MEASure:ADVanced:P<n>:SHIStory` | `:MEASure:ADVanced:P<n>:SHIStory?` | `<count>` = Integer (NR1), bounded by the maximum statistics count; omit it to return all history | documented; 查询指定高级测量项的历史统计数据（仅在最大统计次数有限时有效）（手册 p.195） | 195 |
| `:MEASure:ADVanced:P<n>:STATistics` | `:MEASure:ADVanced:P<n>:STATistics?` | — | documented; 只读查询指定高级测量项的统计信息；手册该页无输入参数（手册 p.194） | 194 |
| `:MEASure:ADVanced:P<n>:VALue` | `:MEASure:ADVanced:P<n>:VALue?` | `<n>` = measurement index, Integer (NR1), 1 to 12 | documented; 只读查询当前指定高级测量项的值（手册 p.200） | 200 |
| `:MEASure:ADVanced:STATistics` | `:MEASure:ADVanced:STATistics?` | `<state>` = `{ON\|OFF}` | documented; 高级测量统计开关（手册 p.200） | 200 |
| `:MEASure:ADVanced:STATistics:AIMLimit` | `:MEASure:ADVanced:STATistics:AIMLimit?` | `<value>` = AIM count, Integer (NR1); the range depends on the model | documented; 高级测量统计的 AIM 次数（手册 p.200） | 200 |
| `:MEASure:ADVanced:STATistics:HISTOGram` | `:MEASure:ADVanced:STATistics:HISTOGram?` | `<state>` = `{ON\|OFF}` | documented; 高级测量统计直方图开关（手册 p.201） | 201 |
| `:MEASure:ADVanced:STATistics:MAXCount` | `:MEASure:ADVanced:STATistics:MAXCount?` | `<value>` = Integer (NR1), 0 to 1024; 0 means unlimited | documented; 高级测量的最大统计次数（手册 p.201） | 201 |
| `:MEASure:ADVanced:STATistics:RESet` | `:MEASure:ADVanced:STATistics:RESet?` | — | documented; 事件命令（无参数），重置高级测量的统计结果（手册 p.202） | 202 |
| `:MEASure:ADVanced:STYLe` | `:MEASure:ADVanced:STYLe?` | `<type>` = `{M1\|M2}`; `M1` shows statistics vertically (with histogram), `M2` horizontally (no histogram) | documented; 高级测量的显示模式（手册 p.202） | 202 |
| `:MEASure:ASTRategy` | `:MEASure:ASTRategy?` | `<type>` = `{AUTO\|MANual}`; `AUTO` picks the amplitude strategy from the signal, `MANual` uses the top/base strategy set by `:MEASure:ASTRategy:TOP` / `:BASE` | documented; 测量的幅值计算策略（手册 p.202） | 202 |
| `:MEASure:ASTRategy:BASE` | `:MEASure:ASTRategy:BASE?` | `<type>` = `{HISTogram\|MIN}`; `HISTogram` takes the most probable value below half the peak-to-peak value, `MIN` takes the waveform minimum | documented; 手动幅值策略下的底端值计算策略（手册 p.203） | 203 |
| `:MEASure:ASTRategy:TOP` | `:MEASure:ASTRategy:TOP?` | `<type>` = `{HISTogram\|MAX}`; `HISTogram` takes the most probable value above half the peak-to-peak value, `MAX` takes the waveform maximum | documented; 手动幅值策略下的顶端值计算策略（手册 p.203） | 203 |
| `:MEASure:DTIMe1:EDGE1` | `:MEASure:DTIMe1:EDGE1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<value>` = start edge, Integer (NR1), bounded by the maximum AIM count, -1 selects the last edge | documented; 指定 △Time 的开始沿（手册 p.204） | 204 |
| `:MEASure:DTIMe1:EDGE2` | `:MEASure:DTIMe1:EDGE2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<value>` = stop edge, Integer (NR1), bounded by the maximum AIM count, -1 selects the last edge | documented; 指定 △Time 的结束沿（手册 p.205） | 205 |
| `:MEASure:DTIMe1:SLOPe1` | `:MEASure:DTIMe1:SLOPe1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<slope_type>` = `{RISing\|FALLing}` | documented; 指定 △Time 开始沿的类型（手册 p.205） | 205 |
| `:MEASure:DTIMe1:SLOPe2` | `:MEASure:DTIMe1:SLOPe2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<slope_type>` = `{RISing\|FALLing}` | documented; 指定 △Time 开始沿的类型（手册 p.205） | 205 |
| `:MEASure:DTIMe1:THReshold1` | `:MEASure:DTIMe1:THReshold1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<type>` = `{UPPer\|MIDDle\|LOWer}` | documented; 指定 △Time 的开始沿阈值（手册 p.206） | 206 |
| `:MEASure:DTIMe1:THReshold2` | `:MEASure:DTIMe1:THReshold2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<type>` = `{UPPer\|MIDDle\|LOWer}` | documented; 指定 △Time 的结束沿阈值（手册 p.206） | 206 |
| `:MEASure:DTIMe<n>:EDGE1` | `:MEASure:DTIMe<n>:EDGE1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<value>` = start edge, Integer (NR1), bounded by the maximum AIM count, -1 selects the last edge | documented; 指定 △Time 的开始沿（手册 p.204） | 204 |
| `:MEASure:DTIMe<n>:EDGE2` | `:MEASure:DTIMe<n>:EDGE2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<value>` = stop edge, Integer (NR1), bounded by the maximum AIM count, -1 selects the last edge | documented; 指定 △Time 的结束沿（手册 p.204） | 204 |
| `:MEASure:DTIMe<n>:SLOPe1` | `:MEASure:DTIMe<n>:SLOPe1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<slope_type>` = `{RISing\|FALLing}` | documented; 指定 △Time 开始沿的类型（手册 p.205） | 205 |
| `:MEASure:DTIMe<n>:SLOPe2` | `:MEASure:DTIMe<n>:SLOPe2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<slope_type>` = `{RISing\|FALLing}` | documented; 指定 △Time 结束沿的类型（手册 p.205） | 205 |
| `:MEASure:DTIMe<n>:THReshold1` | `:MEASure:DTIMe<n>:THReshold1?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<type>` = `{UPPer\|MIDDle\|LOWer}` | documented; 指定 △Time 的开始沿阈值（手册 p.206） | 206 |
| `:MEASure:DTIMe<n>:THReshold2` | `:MEASure:DTIMe<n>:THReshold2?` | `<n>` = DeltaTime index, Integer (NR1), 1 to 4; `<type>` = `{UPPer\|MIDDle\|LOWer}` | documented; 指定 △Time 的结束沿阈值（手册 p.206） | 206 |
| `:MEASure:GATE` | `:MEASure:GATE?` | `<state>` = `{ON\|OFF}` | documented; 测量门限开关（手册 p.207） | 207 |
| `:MEASure:GATE:GA` | `:MEASure:GATE:GA?` | `<value>` = Real (NR3), [-horizontal divisions/2 * current timebase + horizontal delay, horizontal divisions/2 * current timebase + horizontal delay]; a value above B is clamped to B | documented; 测量门限 A 的位置（手册 p.207） | 207 |
| `:MEASure:GATE:GB` | `:MEASure:GATE:GB?` | `<value>` = Real (NR3), [-horizontal divisions/2 * current timebase + horizontal delay, horizontal divisions/2 * current timebase + horizontal delay]; a value below A is clamped to A | documented; 测量门限 B 的位置（手册 p.207） | 207 |
| `:MEASure:RDISplay` | `:MEASure:RDISplay?` | `<type>` = `{EMBedded\|FLOating}`; `EMBedded` squeezes the waveform area, `FLOating` overlays it | documented; 测量结果的显示样式（手册 p.209） | 209 |
| `:MEASure:SIMPle:CLEar` | `:MEASure:SIMPle:CLEar?` | — | documented; 事件命令（无参数），清除所有基本测量项（手册 p.209） | 209 |
| `:MEASure:SIMPle:SOURce` | `:MEASure:SIMPle:SOURce?` | `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>\|D<d>\|ZD<d>\|REF<r>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform, `<d>` = digital channel, `<r>` = `{A\|B\|C\|D}` reference waveform | documented; 基本测量的源（手册 p.210） | 210 |
| `:MEASure:SIMPle:VALue` | `:MEASure:SIMPle:VALue?` | `<type>` = {PKPK\|MAX\|MIN\|AMPL\|TOP\|BASE\|LEVELX\|CMEAN\|MEAN\|STDEV\|VSTD\|RMS\|CRMS\|MEDIAN\|CMEDIAN\|OVSN\|FPRE\|OVSP\|RPRE\|ULOWer\|PER\|FREQ\|TMAX\|TMIN\|PWID\|NWID\|DUTY\|NDUTY\|WID\|NBWID\|DELAY\|TIMEL\|RISE\|FALL\|RISE20T80\|FALL80T20\|CCJ\|PAREA\|NAREA\|AREA\|ABSAREA\|CYCLES\|REDGES\|FEDGES\|EDGES\|PPULSES\|NPULSES\|PACArea\|NACArea\|ACArea\|ABSACArea\|ALL}; `ALL` returns every simple measurement; values are Real (NR3) | documented; 查询基本测量中指定测量项的值（手册 p.210） | 210 |
| `:MEASure:THReshold:ABSolute` | `:MEASure:THReshold:ABSolute?` | `<high>,<mid>,<low>` = Real (NR3); the range depends on the vertical scale and offset of the current threshold source | documented; 阈值类型为绝对值时的测量阈值（手册 p.212） | 212 |
| `:MEASure:THReshold:PERCent` | `:MEASure:THReshold:PERCent?` | `<high>,<mid>,<low>` = Integer (NR1) percent; `<high>` 3 to 99, `<mid>` 2 to 98, `<low>` 1 to 97 | documented; 阈值类型为百分比时的测量阈值（手册 p.213） | 213 |
| `:MEASure:THReshold:SOURce` | `:MEASure:THReshold:SOURce?` | `<source>` = `{C<n>\|Z<n>\|F<x>\|ZF<x>\|M<m>\|ZM<m>\|REF<r>}`; `<n>` = analog/zoom channel, `<x>` = math function, `<m>` = memory waveform, `<r>` = `{A\|B\|C\|D}`. `Z<n>`/`ZF<x>`/`ZM<m>` are only valid while Zoom is on | documented; 测量阈值的源（手册 p.211） | 211 |
| `:MEASure:THReshold:TYPE` | `:MEASure:THReshold:TYPE?` | `<type>` = `{PERCent\|ABSolute}`; `PERCent` uses waveform percentages (low/high 1%-99%, low must not exceed mid or high), `ABSolute` uses the vertical range (depends on scale, offset and probe factor) | documented; 测量阈值的类型（手册 p.212） | 212 |
| `:MEMory2:HORizontal:POSition` | `:MEMory2:HORizontal:POSition?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<val>` = Real (NR3), horizontal position | documented; 内存波形的水平位置（偏移）（手册 p.214） | 214 |
| `:MEMory2:HORizontal:SCALe` | `:MEMory2:HORizontal:SCALe?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<value>` = Real (NR3), horizontal scale | documented; 内存波形的水平档位（手册 p.214） | 214 |
| `:MEMory2:HORizontal:SYNC` | `:MEMory2:HORizontal:SYNC?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<state>` = `{ON\|OFF}` | documented; 内存波形与窗口同步开关（手册 p.215） | 215 |
| `:MEMory2:LABel` | `:MEMory2:LABel?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<state>` = `{ON\|OFF}` | documented; 内存波形标签开关（手册 p.216） | 216 |
| `:MEMory2:LABel:TEXT` | `:MEMory2:LABel:TEXT?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<qstring>` = quoted ASCII text, up to 20 characters | documented; 内存波形的标签字符（手册 p.216） | 216 |
| `:MEMory2:SWITch` | `:MEMory2:SWITch?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<state>` = `{ON\|OFF}` | documented; 内存波形显示开关（手册 p.216） | 216 |
| `:MEMory<m>:IMPort` | — | `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|<path>}`, path is a quoted `.bin` | documented; imports a source waveform into memory waveform `<m>`; the query form returns the last source and is not documented as writable | 215 |

| `:MEMory2:VERTical:POSition` | `:MEMory2:VERTical:POSition?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<offset>` = Real (NR3), vertical position | documented; 内存波形的垂直位置（偏移）（手册 p.217） | 217 |
| `:MEMory2:VERTical:SCALe` | `:MEMory2:VERTical:SCALe?` | `<m>` = memory waveform index, Integer (NR1) (this row spells it as the literal `2`); `<scale>` = Real (NR3), vertical scale | documented; 内存波形的垂直档位（手册 p.217） | 217 |
| `:MTES:MASK:LOAD` | `:MTES:MASK:LOAD?` | `<location>` = `{INTernal,<num>\|EXTernal,<path>}`; `<num>` = `{1\|2\|3\|4}` (early internal templates), `<path>` = quoted path to a `.msk`/`.smsk` file | documented; `MTESt:MASK:LOAD` 的短形式；加载内部或外部存储的模板（手册 p.221） | 221 |
| `:MTESt:COUNt` | `:MTESt:COUNt?` | — | documented; 只读查询模板测试的结果；手册该页无输入参数（手册 p.218） | 218 |
| `:MTESt:FUNCtion:BUZZer` | `:MTESt:FUNCtion:BUZZer?` | `<state>` = `{ON\|OFF}` | documented; 模板测试蜂鸣器开关（检测到故障帧时发声）（手册 p.218） | 218 |
| `:MTESt:FUNCtion:COF` | `:MTESt:FUNCtion:COF?` | `<state>` = `{ON\|OFF}` | documented; 模板测试失败截图开关（默认保存路径 `SIGLENT/`）（手册 p.219） | 219 |
| `:MTESt:FUNCtion:FTH` | `:MTESt:FUNCtion:FTH?` | `<state>` = `{ON\|OFF}` | documented; 模板测试存储失败帧开关（失败帧可在历史波形中查看）（手册 p.219） | 219 |
| `:MTESt:FUNCtion:SOF` | `:MTESt:FUNCtion:SOF?` | `<state>` = `{ON\|OFF}` | documented; 模板测试失败即停开关（手册 p.220） | 220 |
| `:MTESt:IDISplay` | `:MTESt:IDISplay?` | `<state>` = `{ON\|OFF}` | documented; 模板测试显示信息开关（手册 p.220） | 220 |
| `:MTESt:MASK:CREate` | `:MTESt:MASK:CREate?` | `<XMARgin>` = Real (NR2), `<YMARgin>` = Real (NR2) | documented; 以波形为中心按给定水平 X、垂直 Y 数值创建模板（手册 p.221） | 221 |
| `:MTESt:OPERate` | `:MTESt:OPERate?` | `<state>` = `{ON\|OFF}` | documented; 模板测试操作开关（手册 p.222） | 222 |
| `:MTESt:RESet` | `:MTESt:RESet?` | — | documented; 事件命令（无参数），重置模板测试（手册 p.222） | 222 |
| `:MTESt:SOURce` | `:MTESt:SOURce?` | `<source>` = `{C<n>\|Z<n>}`; `<n>` = analog/zoom channel; `Z<n>` is only valid while Zoom is on | documented; 模板测试的源（手册 p.222） | 222 |
| `:RECall:FDEFault` | `:RECall:FDEFault?` | — | documented; 事件命令（无参数），调用出厂设置（手册 p.224） | 224 |
| `:RECall:REFerence` | `:RECall:REFerence?` | `<location>` = `{REF<r>}` (`<r>` = `{A\|B\|C\|D}`), `<path>` = quoted path to a `.ref` file (`local/...`, `net_storage/...`, `U-disk0/...` or `U-disk1/...`); without a path type it loads from U-disk0 | documented; 从内部或外部存储器调出参考波形文件到指定参考波形（手册 p.224） | 224 |
| `:RECall:SERase` | `:RECall:SERase?` | — | documented; 事件命令（无参数），删除内部存储的参考波形/设置/模板/自定义默认设置等文件（手册 p.225） | 225 |
| `:RECall:SETup` | `:RECall:SETup?` | `<state>` = `{INTernal,<num>\|EXTernal,<path>}`; `<num>` = Integer (NR1), `<path>` = quoted path to a `.xml` file; without a path type it loads from U-disk0 | documented; 从内部或外部存储器调出配置文件（手册 p.225） | 225 |
| `:REFA:DATA` | `:REFA:DATA?` | `<r>` = `{A\|B\|C\|D}`; `<operation>` = `{LOAD\|UNLoad\|SAVE,<source>}` (`LOAD` shows the stored REF waveform, `UNLoad` hides it, `SAVE` stores `<source>`); `<source>` = `{C<n>\|F<x>\|D<d>}` | documented; 参考波形的调用及保存（手册 p.227） | 227 |
| `:REFA:DATA:POSition` | `:REFA:DATA:POSition?` | `<r>` = `{A\|B\|C\|D}`; `<value>` = Real (NR3), auto-clamped to the settable value, range same as the reference source. Only valid when the reference waveform is stored and displayed | documented; 参考波形的垂直偏移（手册 p.228） | 228 |
| `:REFA:DATA:SCALe` | `:REFA:DATA:SCALe?` | `<r>` = `{A\|B\|C\|D}`; `<value>` = Real (NR3), auto-clamped to the settable value, range same as the reference source. Only valid when the reference waveform is stored and displayed | documented; 参考波形的垂直档位（手册 p.228） | 228 |
| `:REFA:DATA:SOUR` | `:REFA:DATA:SOUR?` | — | documented; 只读查询当前参考波形的信源，返回 `{C<n>\|F<x>\|D<d>}`；手册该页无输入参数（手册 p.227） | 227 |
| `:REFA:LAB` | `:REFA:LAB?` | `<r>` = `{A\|B\|C\|D}`; `<state>` = `{ON\|OFF}` | documented; `REF<r>:LABel` 的短形式；参考波形标签开关（手册 p.226） | 226 |
| `:REFA:LABel` | `:REFA:LABel?` | `<r>` = `{A\|B\|C\|D}`; `<state>` = `{ON\|OFF}` | documented; 参考波形标签开关（手册 p.226） | 226 |
| `:REFA:LABel:TEXT` | `:REFA:LABel:TEXT?` | `<r>` = `{A\|B\|C\|D}`; `<qstring>` = quoted ASCII text, up to 20 characters | documented; 参考波形的标签字符（手册 p.226） | 226 |
| `:SAVE:BINary` | `:SAVE:BINary?` | `<path>` = quoted ASCII path, e.g. `"local/SIGLENT/test.bin"`, `"net_storage/test.bin"` or `"U-disk0/test.bin"`; internal saves must contain `local`, an external save without a path type goes to U-disk0; `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|D0_D15\|DIGital\|ZD0_ZD15\|ZDIGital}`; `D0_D15`/`DIGital` store the digital channels per bit / as a bus, the `Z*` forms are their zoomed versions | documented; 把指定通道波形以 `.bin` 保存到内部或外部存储器（手册 p.229） | 229 |
| `:SAVE:CSV` | `:SAVE:CSV?` | `<path>` = quoted ASCII path to a `.csv` file (`local/...`, `net_storage/...`, `U-disk0/...`); `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|D0_D15\|DIGital\|ZD0_ZD15\|ZDIGital}`; `D0_D15`/`DIGital` store the digital channels per bit / as a bus, the `Z*` forms are their zoomed versions; `<state>` = `{OFF\|ON}` (`ON` also writes the vertical/horizontal settings into the file) | documented; 把指定通道波形以 `.csv` 保存到内部或外部存储器（手册 p.230） | 230 |
| `:SAVE:DEFault` | `:SAVE:DEFault?` | `<set>` = `{CUSTom\|FACTory}` (current user settings / factory settings) | documented; 保存用户自定义设置或出厂设置作为默认设置（手册 p.231） | 231 |
| `:SAVE:MATLab` | `:SAVE:MATLab?` | `<path>` = quoted ASCII path, e.g. `"local/SIGLENT/test.mat"`, `"net_storage/test.mat"` or `"U-disk0/test.mat"`; internal saves must contain `local`, an external save without a path type goes to U-disk0; `<source>` = `{C<n>\|Z<n>\|F<x>\|M<m>\|D0_D15\|DIGital\|ZD0_ZD15\|ZDIGital}`; `D0_D15`/`DIGital` store the digital channels per bit / as a bus, the `Z*` forms are their zoomed versions | documented; 把指定通道波形以 `.mat` 保存到内部或外部存储器（手册 p.232） | 232 |
| `:SAVE:REFerence` | `:SAVE:REFerence?` | `<path>` = quoted ASCII path to a `.ref` file (`local/...`, `net_storage/...`, `U-disk0/...`); `<source>` = `{C<n>\|F<x>\|D<d>}` | documented; 把指定通道波形以 `.ref` 保存到内部或外部存储器作参考波形（手册 p.233） | 233 |
| `:SAVE:SET` | `:SAVE:SET?` | `<setup_num>` = `{INTernal,<num>\|EXTernal,<path>}`; `<num>` = Integer (NR1) save slot, `<path>` = quoted path to a `.xml` file; an external save without a path type goes to U-disk0 | documented; `SAVe:SETup` 的短形式；把当前设置保存为内部或外部文件（手册 p.234） | 234 |
| `:SEAR:MODE` | `:SEAR:MODE?` | `<mode>` = `{EDGE\|SLOPe\|PULSE\|INTerval\|RUNT}` (edge / slope / pulse width / interval / runt search) | documented; `SEARch:MODE` 的短形式（手册该节查询拼写）；当前搜索模式（手册 p.235） | 235 |
| `:SEARch:COPY` | `:SEARch:COPY?` | `<operation>` = `{FROMtrigger\|TOTRigger\|CANCel}`; copy the trigger settings into the search settings / the search settings into the trigger settings / undo the last copy | documented; 搜索设置与触发设置同步（手册 p.236） | 236 |
| `:SEARch:COUNT` | `:SEARch:COUNT?` | — | documented; 只读查询当前屏幕内搜索事件总数，返回整型 NR1；手册该页无输入参数（手册 p.236） | 236 |
| `:SEARch:EDGE` | `:SEARch:EDGE?` | — | documented; 章节标题，本节无独立参数；边沿搜索的参数都在其子命令中（手册 p.237） | 237 |
| `:SEARch:EDGE:LEVel` | `:SEARch:EDGE:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 边沿搜索的搜索电平（手册 p.238） | 238 |
| `:SEARch:EDGE:SLOPe` | `:SEARch:EDGE:SLOPe?` | `<slope_type>` = `{RISing\|FALLing\|ALTernate}`（上升 / 下降 / 任意边沿） | documented; 边沿搜索的斜率。**手册 p.237 的「命令格式」行误印为 `:SEARch:EDGE:SOURce <slope_type>`**，按手册笔误处理，不要照抄该拼写。 | 237 |
| `:SEARch:EDGE:SOURce` | `:SEARch:EDGE:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 边沿搜索的信源（手册 p.237） | 237 |
| `:SEARch:EVENt` | `:SEARch:EVENt?` | — | documented; 只读查询采集停止时定位的事件帧号，返回整型 NR1；手册该页无输入参数（手册 p.236） | 236 |
| `:SEARch:INTerval` | `:SEARch:INTerval?` | — | documented; 章节标题，本节无独立参数；间隔搜索的参数都在其子命令中（手册 p.248） | 248 |
| `:SEARch:INTerval:LEVel` | `:SEARch:INTerval:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 间隔搜索的搜索电平（手册 p.249） | 249 |
| `:SEARch:INTerval:LIMit` | `:SEARch:INTerval:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 间隔搜索的限制条件类型（手册 p.249） | 249 |
| `:SEARch:INTerval:SLOPe` | `:SEARch:INTerval:SLOPe?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 间隔搜索的斜率（手册 p.248） | 248 |
| `:SEARch:INTerval:SOURce` | `:SEARch:INTerval:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 间隔搜索的信源（手册 p.248） | 248 |
| `:SEARch:INTerval:TLOWer` | `:SEARch:INTerval:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 间隔搜索限制条件的下限值（手册 p.250） | 250 |
| `:SEARch:INTerval:TUPPer` | `:SEARch:INTerval:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 间隔搜索限制条件的上限值（手册 p.250） | 250 |
| `:SEARch:PULSe` | `:SEARch:PULSe?` | — | documented; 章节标题，本节无独立参数；脉宽搜索的参数都在其子命令中（手册 p.244） | 244 |
| `:SEARch:PULSe:LEVel` | `:SEARch:PULSe:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 脉宽搜索的搜索电平（手册 p.245） | 245 |
| `:SEARch:PULSe:LIMit` | `:SEARch:PULSe:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 脉宽搜索的限制条件类型（手册 p.245） | 245 |
| `:SEARch:PULSe:POLarity` | `:SEARch:PULSe:POLarity?` | `<polarity_type>` = `{POSitive\|NEGative}` (positive / negative pulse) | documented; 脉宽搜索的极性（手册 p.244） | 244 |
| `:SEARch:PULSe:SOURce` | `:SEARch:PULSe:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 脉宽搜索的信源（手册 p.244） | 244 |
| `:SEARch:PULSe:TLOWer` | `:SEARch:PULSe:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 脉宽搜索限制条件的下限值（手册 p.246） | 246 |
| `:SEARch:PULSe:TUPPer` | `:SEARch:PULSe:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 脉宽搜索限制条件的上限值（手册 p.246） | 246 |
| `:SEARch:PULse:POLarity` | `:SEARch:PULse:POLarity?` | `<polarity_type>` = `{POSitive\|NEGative}` (positive / negative pulse) | documented; 脉宽搜索的极性（手册 p.244） | 244 |
| `:SEARch:PULse:SOURce` | `:SEARch:PULse:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 脉宽搜索的信源（手册 p.244） | 244 |
| `:SEARch:RUNT` | `:SEARch:RUNT?` | — | documented; 章节标题，本节无独立参数；欠幅搜索的参数都在其子命令中（手册 p.252） | 252 |
| `:SEARch:RUNT:HLEVel` | `:SEARch:RUNT:HLEVel?` | `<high_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The high level must not be below the low level (`:SEARch:RUNT:LLEVel`) | documented; 欠幅搜索的高电平（手册 p.252） | 252 |
| `:SEARch:RUNT:LIMit` | `:SEARch:RUNT:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 欠幅搜索的限制条件类型（手册 p.254） | 254 |
| `:SEARch:RUNT:LLEVel` | `:SEARch:RUNT:LLEVel?` | `<low_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:SEARch:RUNT:HLEVel`) | documented; 欠幅搜索的低电平（手册 p.253） | 253 |
| `:SEARch:RUNT:POLarity` | `:SEARch:RUNT:POLarity?` | `<polarity_type>` = `{POSitive\|NEGative}` (positive / negative pulse) | documented; 欠幅搜索的极性（手册 p.252） | 252 |
| `:SEARch:RUNT:SOURce` | `:SEARch:RUNT:SOURce?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; 欠幅搜索的信源（手册 p.252） | 252 |
| `:SEARch:RUNT:TLOWer` | `:SEARch:RUNT:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 欠幅搜索限制条件的下限值（手册该节描述误写成“幅度搜索”）（手册 p.254） | 254 |
| `:SEARch:RUNT:TUPPer` | `:SEARch:RUNT:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 欠幅搜索限制条件的上限值（手册 p.254） | 254 |
| `:SEARch:SLOPe` | `:SEARch:SLOPe?` | — | documented; 章节标题，本节无独立参数；斜率搜索的参数都在其子命令中（手册 p.239） | 239 |
| `:SEARch:SLOPe:HLEVel` | `:SEARch:SLOPe:HLEVel?` | `<high_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The high level must not be below the low level (`:SEARch:SLOPe:LLEVel`) | documented; 斜率搜索的高电平（手册 p.239） | 239 |
| `:SEARch:SLOPe:LIMit` | `:SEARch:SLOPe:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 斜率搜索的限制条件类型（手册 p.241） | 241 |
| `:SEARch:SLOPe:LLEVel` | `:SEARch:SLOPe:LLEVel?` | `<low_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:SEARch:SLOPe:HLEVel`) | documented; 斜率搜索的低电平（手册 p.240） | 240 |
| `:SEARch:SLOPe:SLOPe` | `:SEARch:SLOPe:SLOPe?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 斜率搜索的斜率（手册 p.239） | 239 |
| `:SEARch:SLOPe:SOURce` | `:SEARch:SLOPe:SOURce?` | `<source>` = `C<n>` (`<n>` = analog channel NR1); no digital source | documented; 斜率搜索的信源（手册 p.239） | 239 |
| `:SEARch:SLOPe:TLOWer` | `:SEARch:SLOPe:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 斜率搜索限制条件的下限值（手册 p.241） | 241 |
| `:SEARch:SLOPe:TUPPer` | `:SEARch:SLOPe:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 斜率搜索限制条件的上限值（手册 p.241） | 241 |
| `:SYSTem:BUZZer` | `:SYSTem:BUZZer?` | `<state>` = `{ON\|OFF}` | documented; 蜂鸣器开关（手册 p.257） | 257 |
| `:SYSTem:CLOCk` | `:SYSTem:CLOCk?` | `<source>` = `{EXT\|IN_ON\|IN_OFF}`; `EXT` selects the external clock (internal 10 MHz output off), `IN_ON` internal clock with 10 MHz output on, `IN_OFF` internal clock with output off | documented; 时钟源与内部 10 MHz 时钟输出状态（手册 p.257） | 257 |
| `:SYSTem:COMMunicate:LAN:MAC` | `:SYSTem:COMMunicate:LAN:MAC?` | — | documented; 只读查询 MAC 地址；手册该页无输入参数（手册 p.259） | 259 |
| `:SYSTem:COMMunicate:VNCPort` | `:SYSTem:COMMunicate:VNCPort?` | `<value>` = Integer (NR1) port number, 5900 to 5999 | documented; VNC 端口号（手册 p.260） | 260 |
| `:SYSTem:DATE` | `:SYSTem:DATE?` | `<date>` = Integer (NR1), 8 significant digits, YYYYMMDD from most to least significant | documented; 系统日期（手册 p.260） | 260 |
| `:SYSTem:EDUMode` | `:SYSTem:EDUMode?` | `<func>` = `{AUTOSet\|MEASure\|CURSor}`, `<lock>` = `{ON\|OFF}` (`ON` enables the selected function, `OFF` disables it) | documented; 教育模式开关（教育模式下可禁用 Auto Setup、Measure、Cursors）（手册 p.261） | 261 |
| `:SYSTem:LANGuage` | `:SYSTem:LANGuage?` | `<language>` = `{SCHinese\|TCHinese\|ENGLish\|FRENch\|JAPanese\|KORean\|DEUTsch\|ESPan\|RUSSian\|ITALiana\|PORTuguese}` | documented; 显示语言（手册 p.261） | 261 |
| `:SYSTem:MENU` | `:SYSTem:MENU?` | `<state>` = `{ON\|OFF}` | documented; 菜单开关（仅适用于带 Menu 键的机型）（手册 p.262） | 262 |
| `:SYSTem:NSTorage:STATus` | `:SYSTem:NSTorage:STATus?` | `<state>` = `{ON\|OFF}` | documented; 网络存储器的连接状态（只读查询）（手册 p.263） | 263 |
| `:SYSTem:PON` | `:SYSTem:PON?` | `<state>` = `{ON\|OFF}` | documented; 上电自动开机开关（手册 p.264） | 264 |
| `:SYSTem:REBoot` | `:SYSTem:REBoot?` | — | documented; 事件命令（无参数），重启示波器（手册 p.264） | 264 |
| `:SYSTem:SELFCal` | `:SYSTem:SELFCal?` | — | documented; 设置或查询自校正状态；手册该页未列输入参数与取值范围（手册 p.265） | 265 |
| `:SYSTem:SHUTdown` | `:SYSTem:SHUTdown?` | — | documented; 事件命令（无参数），示波器关机（手册 p.265） | 265 |
| `:SYSTem:SSAVer` | `:SYSTem:SSAVer?` | `<time>` = `{OFF\|1MIN\|5MIN\|10MIN\|30MIN\|60MIN}` | documented; 屏幕保护（预设时间到达后关闭显示输出）（手册 p.265） | 265 |
| `:SYSTem:TIME` | `:SYSTem:TIME?` | `<time>` = Integer (NR1), 6 significant digits, HHMMSS from most to least significant (24 h clock) | documented; 当前时间（24 小时制）（手册 p.266） | 266 |
| `:SYSTem:TOUCh` | `:SYSTem:TOUCh?` | `<state>` = `{ON\|OFF}` | documented; 触摸屏开关（手册 p.266） | 266 |
| `:TIMebase:DELay` | `:TIMebase:DELay?` | `<delay_value>` = Real (NR3); no range listed | documented; 设置或查询水平触发延时（手册 p.267） | 267 |
| `:TIMebase:REFerence` | `:TIMebase:REFerence?` | `<type>` = `{DELay\|POSition}`; `DELay` keeps the delay value when the timebase changes and lets `:TIMebase:REFerence:POSition` set the reference point, `POSition` keeps the delay at a fixed on-screen grid position | documented; 水平扩展参考策略（手册 p.267） | 267 |
| `:TIMebase:REFerence:POSition` | `:TIMebase:REFerence:POSition?` | `<value>` = Integer (NR1) percent, 0 to 100 | documented; 延时固定策略下的水平参考中心位置，百分比（手册 p.268） | 268 |
| `:TIMebase:WINDow` | `:TIMebase:WINDow?` | `<state>` = `{ON\|OFF}` | documented; Zoom 窗口开关（手册 p.269） | 269 |
| `:TIMebase:WINDow:DELay` | `:TIMebase:WINDow:DELay?` | `<delay_value>` = Real (NR3); must lie inside the main window range, an out-of-range value clamps to the nearest settable one | documented; Zoom 窗口水平延时（手册 p.269） | 269 |
| `:TIMebase:WINDow:SCALe` | `:TIMebase:WINDow:SCALe?` | `<scale_value>` = Real (NR3); cannot exceed the main-window timebase, otherwise it auto-matches the main window | documented; Zoom 窗口时基（手册 p.269） | 269 |
| `:TRIG:SPI:NCSS` | `:TRIG:SPI:NCSS?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 手册该节标题为 `:TRIGger:SPI:NCSSource`，本行为其短形式；设置或查询 SPI 触发 NCS 信源（手册 p.370） | 370 |
| `:TRIG:STAT` | `:TRIG:STAT?` | — | documented; 短形式查询触发状态，返回 `{Arm\|Ready\|Auto\|Trig'd\|Stop\|Roll}`；手册该页只给返回格式，无输入参数（手册 p.272） | 272 |
| `:TRIGger:CAN` | `:TRIGger:CAN?` | — | documented; 章节标题，本节无独立参数；CAN 触发的参数都在其子命令中（手册 p.380） | 380 |
| `:TRIGger:CAN:BAUD` | `:TRIGger:CAN:BAUD?` | `<baud>` = `{5kbps\|10kbps\|20kbps\|50kbps\|100kbps\|125kbps\|250kbps\|500kbps\|800kbps\|1Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 5000 to 1000000 | documented; CAN 触发的波特率（手册 p.380） | 380 |
| `:TRIGger:CAN:CONDition` | `:TRIGger:CAN:CONDition?` | `<condition>` = `{STARt\|REMote\|ID\|ID_AND_DATA\|ERRor}` | documented; CAN 触发条件：帧起始、远程帧、ID、ID+数据、错误帧（手册 p.380） | 380 |
| `:TRIGger:CAN:DAT2` | `:TRIGger:CAN:DAT2?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; CAN 触发的数据字节 2（手册 p.381） | 381 |
| `:TRIGger:CAN:DATA` | `:TRIGger:CAN:DATA?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; CAN 触发的数据字节 1（手册 p.381） | 381 |
| `:TRIGger:CAN:ID` | `:TRIGger:CAN:ID?` | `<id>` = Integer (NR1); 29-bit ID: 0 to 536870912 (536870912 = any, `0xXXXXXXXX`), 11-bit ID: 0 to 2048 (2048 = any, `0xXXXX`) | documented; CAN 触发的 ID（手册 p.382） | 382 |
| `:TRIGger:CAN:IDLENgth` | `:TRIGger:CAN:IDLENgth?` | `<id_length>` = `{11BITS\|29BITS}` | documented; 手册标题拼作 `:TRIGger:CAN:IDLength`，本行为其目录拼写；CAN 触发的 ID 长度（手册 p.382） | 382 |
| `:TRIGger:CAN:IDLength` | `:TRIGger:CAN:IDLength?` | `<id_length>` = `{11BITS\|29BITS}` | documented; CAN 触发的 ID 长度（手册 p.382） | 382 |
| `:TRIGger:CAN:SOURce` | `:TRIGger:CAN:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel index NR1, `<d>` = digital channel index NR1 | documented; CAN 触发的信源（手册 p.383） | 383 |
| `:TRIGger:CAN:THReshold` | `:TRIGger:CAN:THReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; CAN 触发的阈值（手册 p.383） | 383 |
| `:TRIGger:CANFd:BAUDData` | `:TRIGger:CANFd:BAUDData?` | `<baud>` = `{500kbps\|1Mbps\|2Mbps\|5Mbps\|8Mbps\|10Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 100000 to 10000000 | documented; CAN FD 触发的数据波特率（手册 p.396） | 396 |
| `:TRIGger:CANFd:BAUDNominal` | `:TRIGger:CANFd:BAUDNominal?` | `<baud>` = `{10kbps\|25kbps\|50kbps\|100kbps\|250kbps\|1Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 10000 to 1000000 | documented; CAN FD 触发的标准波特率（手册 p.396） | 396 |
| `:TRIGger:CANFd:CONDition` | `:TRIGger:CANFd:CONDition?` | `<condition>` = `{STARt\|REMote\|ID\|ID_AND_DATA\|ERRor}` | documented; CAN FD 触发条件；手册该页未展开各枚举的含义（手册 p.397） | 397 |
| `:TRIGger:CANFd:DAT2` | `:TRIGger:CANFd:DAT2?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; CAN FD 触发的数据字节 2（手册 p.397） | 397 |
| `:TRIGger:CANFd:DATA` | `:TRIGger:CANFd:DATA?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; CAN FD 触发的数据字节 1（手册 p.397） | 397 |
| `:TRIGger:CANFd:FTYPe` | `:TRIGger:CANFd:FTYPe?` | `<frame_type>` = `{BOTH\|CAN\|CANFd}` | documented; CAN FD 触发的帧类型（手册 p.398） | 398 |
| `:TRIGger:CANFd:ID` | `:TRIGger:CANFd:ID?` | `<id>` = Integer (NR1); manual lists no range on this page | documented; 触发条件为远程帧、ID 或 ID+数据时的 CAN FD 触发 ID（手册 p.398） | 398 |
| `:TRIGger:CANFd:IDLength` | `:TRIGger:CANFd:IDLength?` | `<length>` = `{11BITS\|29BITS}` | documented; CAN FD 触发的 ID 长度（手册 p.399） | 399 |
| `:TRIGger:CANFd:SOURce` | `:TRIGger:CANFd:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel index NR1, `<d>` = digital channel index NR1 | documented; CAN FD 触发的信源（手册 p.399） | 399 |
| `:TRIGger:CANFd:THReshold` | `:TRIGger:CANFd:THReshold?` | `<threshold>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; CAN FD 触发的阈值（手册 p.400） | 400 |
| `:TRIGger:DELay` | `:TRIGger:DELay?` | — | documented; 章节标题，本节无独立参数；延时触发的参数都在其子命令中（手册 p.340） | 340 |
| `:TRIGger:DELay:INPut` | `:TRIGger:DELay:INPut?` | `<state>` = `{X\|L\|H}`, one entry per source, mapped in the order C1-C<n>, D0-D15; `X` = don't care, `H` = high, `L` = low | documented; 手册本节标题为 `:TRIGger:DELay:SOURce`、命令格式却写作 `:TRIGger:DELay:INPut`；设置/查询延时触发信源 A 各通道的逻辑电平（手册 p.340） | 340 |
| `:TRIGger:DELay:LEVel` | `:TRIGger:DELay:LEVel?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1), `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 延时触发信源 A 的触发电平（手册 p.341） | 341 |
| `:TRIGger:DELay:LEVel2` | `:TRIGger:DELay:LEVel2?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 延时触发信源 B 的触发电平（手册 p.342） | 342 |
| `:TRIGger:DELay:LIMit` | `:TRIGger:DELay:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 延时触发的限制条件类型（手册 p.343） | 343 |
| `:TRIGger:DELay:SLOPe` | `:TRIGger:DELay:SLOPe?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 延时触发信源 A 的斜率类型（手册 p.341） | 341 |
| `:TRIGger:DELay:SLOPe2` | `:TRIGger:DELay:SLOPe2?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 延时触发信源 B 的斜率类型（手册 p.341） | 341 |
| `:TRIGger:DELay:SOURce` | `:TRIGger:DELay:SOURce?` | `<state>` = `{X\|L\|H}`, one entry per source, mapped in the order C1-C<n>, D0-D15; `X` = don't care, `H` = high, `L` = low | documented; 延时触发信源 A 的状态（手册 p.340） | 340 |
| `:TRIGger:DELay:SOURce2` | `:TRIGger:DELay:SOURce2?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 延时触发信源 B 的信源（手册 p.340） | 340 |
| `:TRIGger:DELay:TLOWer` | `:TRIGger:DELay:TLOWer?` | `<value>` = Real (NR3); no range listed. Must not exceed the upper limit (`:TRIGger:DELay:TUPPer`); not usable when the limit type is `<=` | documented; 延时触发限制条件的下限值（手册 p.343） | 343 |
| `:TRIGger:DELay:TUPPer` | `:TRIGger:DELay:TUPPer?` | `<value>` = Real (NR3); no range listed. Must not be below the lower limit (`:TRIGger:DELay:TLOWer`); not usable when the limit type is `>=` | documented; 延时触发限制条件的上限值（手册 p.343） | 343 |
| `:TRIGger:DROPout` | `:TRIGger:DROPout?` | — | documented; 章节标题，本节无独立参数；超时触发的参数都在其子命令中（手册 p.315） | 315 |
| `:TRIGger:DROPout:COUPling` | `:TRIGger:DROPout:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 超时触发的耦合方式（手册 p.315） | 315 |
| `:TRIGger:DROPout:HLDEVent` | `:TRIGger:DROPout:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 超时触发的触发释抑事件数（手册 p.315） | 315 |
| `:TRIGger:DROPout:HLDTime` | `:TRIGger:DROPout:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 超时触发的触发释抑时间（手册 p.316） | 316 |
| `:TRIGger:DROPout:HOLDoff` | `:TRIGger:DROPout:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 超时触发的触发释抑类型（手册 p.316） | 316 |
| `:TRIGger:DROPout:HSTart` | `:TRIGger:DROPout:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 超时触发的触发释抑启动条件（手册 p.317） | 317 |
| `:TRIGger:DROPout:LEVel` | `:TRIGger:DROPout:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 超时触发的触发电平（手册 p.317） | 317 |
| `:TRIGger:DROPout:NREJect` | `:TRIGger:DROPout:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 超时触发的噪声抑制开关（手册 p.318） | 318 |
| `:TRIGger:DROPout:SLOPe` | `:TRIGger:DROPout:SLOPe?` | `<state>` = `{RISing\|FALLing}` | documented; 超时触发的斜率类型（手册 p.318） | 318 |
| `:TRIGger:DROPout:SOURce` | `:TRIGger:DROPout:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 超时触发的触发源（手册 p.319） | 319 |
| `:TRIGger:DROPout:TIME` | `:TRIGger:DROPout:TIME?` | `<time>` = Real (NR3); range depends on model - SDS800X HD: [2.00E-09, 4.20E+00] s | documented; 超时触发的超时时间（手册 p.319） | 319 |
| `:TRIGger:DROPout:TYPE` | `:TRIGger:DROPout:TYPE?` | `<type>` = `{EDGE\|STATe}` (edge / state) | documented; 超时触发的超时类型（手册 p.320） | 320 |
| `:TRIGger:EDGE` | `:TRIGger:EDGE?` | — | documented; 章节标题，本节无独立参数；边沿触发的参数都在其子命令中（手册 p.274） | 274 |
| `:TRIGger:EDGE:COUPling` | `:TRIGger:EDGE:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 边沿触发的耦合方式（手册 p.274） | 274 |
| `:TRIGger:EDGE:HLDEVent` | `:TRIGger:EDGE:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 边沿触发的触发释抑事件数（手册 p.274） | 274 |
| `:TRIGger:EDGE:HLDTime` | `:TRIGger:EDGE:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 边沿触发的触发释抑时间（手册 p.275） | 275 |
| `:TRIGger:EDGE:HOLDoff` | `:TRIGger:EDGE:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 边沿触发的触发释抑类型（手册 p.275） | 275 |
| `:TRIGger:EDGE:HSTart` | `:TRIGger:EDGE:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 边沿触发的触发释抑启动条件（手册 p.276） | 276 |
| `:TRIGger:EDGE:IMPedance` | `:TRIGger:EDGE:IMPedance?` | `<ohm>` = `{ONEMeg\|FIFTy}` (1 MOhm / 50 Ohm); only valid when the trigger source is `EXT` or `EXT/5` | documented; 边沿触发的触发源阻抗（手册 p.276） | 276 |
| `:TRIGger:EDGE:LEVel` | `:TRIGger:EDGE:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 边沿触发的触发电平（手册 p.277） | 277 |
| `:TRIGger:EDGE:NREJect` | `:TRIGger:EDGE:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 边沿触发的噪声抑制开关（手册 p.278） | 278 |
| `:TRIGger:FLEXray:BAUD` | `:TRIGger:FLEXray:BAUD?` | `<baud>` = `{2500kbps\|5Mbps\|10Mbps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 1000000 to 20000000 | documented; FlexRay 总线触发的波特率（手册 p.392） | 392 |
| `:TRIGger:FLEXray:CONDition` | `:TRIGger:FLEXray:CONDition?` | `<condition>` = `{TSS\|FRAMe\|SYMBol\|ERRor}` (transmission start sequence / frame / symbol / error) | documented; FlexRay 总线触发的触发条件（手册 p.392） | 392 |
| `:TRIGger:FLEXray:FRAMe:COMPare` | `:TRIGger:FLEXray:FRAMe:COMPare?` | `<type>` = `{ANY\|EQUal\|GREaterthan\|LESSthan}` | documented; FlexRay 触发的帧比较类型（手册 p.393） | 393 |
| `:TRIGger:FLEXray:FRAMe:CYCLe` | `:TRIGger:FLEXray:FRAMe:CYCLe?` | `<cycle>` = Integer (NR1), 0 to 63 | documented; FlexRay 触发的周期数量（手册 p.393） | 393 |
| `:TRIGger:FLEXray:FRAMe:ID` | `:TRIGger:FLEXray:FRAMe:ID?` | `<id>` = Integer (NR1), 0 to 2048; 2048 stands for any value (`0xXXX`) | documented; FlexRay 触发的 ID（手册 p.393） | 393 |
| `:TRIGger:FLEXray:FRAMe:REPetition` | `:TRIGger:FLEXray:FRAMe:REPetition?` | `<times>` = `{1\|2\|4\|8\|16\|32\|64}` | documented; FlexRay 触发的重复系数（手册 p.394） | 394 |
| `:TRIGger:FLEXray:SOURce` | `:TRIGger:FLEXray:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; FlexRay 总线触发的信源（手册 p.394） | 394 |
| `:TRIGger:FLEXray:Source` | `:TRIGger:FLEXray:Source?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 手册该页的命令格式拼作 `Source`、描述与示例用 `SOURce`；FlexRay 总线触发的信源（手册 p.394） | 394 |
| `:TRIGger:FLEXray:THReshold` | `:TRIGger:FLEXray:THReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; FlexRay 总线触发的阈值（手册 p.395） | 395 |
| `:TRIGger:FREQuency` | `:TRIGger:FREQuency?` | — | documented; 查询硬件频率计：频率有效时以 Hz 返回，默认 3 位有效数字、最多 7 位，精度由 `:FORMat:DATA` 设定；手册该页只给返回格式，无输入参数（手册 p.271） | 271 |
| `:TRIGger:IIC` | `:TRIGger:IIC?` | — | documented; 章节标题，本节无独立参数；IIC 总线触发的参数都在其子命令中（手册 p.357） | 357 |
| `:TRIGger:IIC:ADDRess` | `:TRIGger:IIC:ADDRess?` | `<addr>` = Integer (NR1), 0 to 1024; 1024 stands for any value (`0xXX`) | documented; IIC 总线触发的地址（手册 p.357） | 357 |
| `:TRIGger:IIC:ALENgth` | `:TRIGger:IIC:ALENgth?` | `<length>` = `{7BIT\|10BIT}` | documented; IIC 总线触发的地址长度（手册 p.357） | 357 |
| `:TRIGger:IIC:CONDition` | `:TRIGger:IIC:CONDition?` | `<condition>` = `{STARt\|STOP\|RESTart\|NACK\|EEPRom\|7ADDRess\|10ADDRess\|DLENgth}` | documented; IIC 总线触发的触发条件（手册 p.358） | 358 |
| `:TRIGger:IIC:DAT2` | `:TRIGger:IIC:DAT2?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; IIC 总线触发的数据字节 2（手册 p.358） | 358 |
| `:TRIGger:IIC:DATA` | `:TRIGger:IIC:DATA?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; IIC 总线触发的数据字节 1（手册 p.358） | 358 |
| `:TRIGger:IIC:DLENgth` | `:TRIGger:IIC:DLENgth?` | `<length>` = Integer (NR1), 1 to 12 | documented; IIC 总线触发的数据长度（手册 p.359） | 359 |
| `:TRIGger:IIC:LIMit` | `:TRIGger:IIC:LIMit?` | `<limit_type>` = `{EQUal\|GREaterthan\|LESSthan}`; only when the trigger condition is `EEPRom` | documented; IIC 触发条件为 EEPROM 时的限制条件类型（手册 p.359） | 359 |
| `:TRIGger:IIC:RWBit` | `:TRIGger:IIC:RWBit?` | `<type>` = `{WRITe\|READ\|ANY}`; only when the trigger condition is 7/10 address & data | documented; IIC 触发条件为 7/10 位地址+数据时的读写位（手册 p.360） | 360 |
| `:TRIGger:IIC:SCLSource` | `:TRIGger:IIC:SCLSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIC 总线触发的 SCL 信源（手册 p.360） | 360 |
| `:TRIGger:IIC:SCLThreshold` | `:TRIGger:IIC:SCLThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIC 总线触发的 SCL 阈值（手册 p.361） | 361 |
| `:TRIGger:IIC:SDASource` | `:TRIGger:IIC:SDASource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIC 总线触发的 SDA 信源（手册 p.361） | 361 |
| `:TRIGger:IIC:SDAThreshold` | `:TRIGger:IIC:SDAThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIC 总线触发的 SDA 阈值（手册 p.362） | 362 |
| `:TRIGger:IIS:AVARiant` | `:TRIGger:IIS:AVARiant?` | `<type>` = `{I2S\|LJ\|RJ}` | documented; IIS 总线触发的音频格式（手册 p.401） | 401 |
| `:TRIGger:IIS:BCLKSource` | `:TRIGger:IIS:BCLKSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线触发的时钟源（BCLK）（手册 p.401） | 401 |
| `:TRIGger:IIS:BCLKThreshold` | `:TRIGger:IIS:BCLKThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线触发的时钟阈值（手册 p.402） | 402 |
| `:TRIGger:IIS:BITorder` | `:TRIGger:IIS:BITorder?` | `<order>` = `{LSM\|MSB}` | documented; IIS 总线触发的比特流格式（手册该页拼作 `LSM`）（手册 p.402） | 402 |
| `:TRIGger:IIS:CHANnel` | `:TRIGger:IIS:CHANnel?` | `<channel>` = `{LEFT\|RIGHT}` | documented; IIS 总线触发的通道（手册 p.403） | 403 |
| `:TRIGger:IIS:COMPare` | `:TRIGger:IIS:COMPare?` | `<type>` = `{EQUal\|GREaterthan\|LESSthan}` | documented; IIS 总线触发的比较类型（手册 p.403） | 403 |
| `:TRIGger:IIS:CONDition` | `:TRIGger:IIS:CONDition?` | `<condition>` = `{DATA\|MUTE\|CLIP\|GLITch\|RISing\|FALLing}` | documented; IIS 总线触发的触发条件（手册 p.403） | 403 |
| `:TRIGger:IIS:DLENgth` | `:TRIGger:IIS:DLENgth?` | `<value>` = Integer (NR1); the valid range depends on the channel bit count and the start bit (e.g. 32-bit channel with start bit 2: 1 to 30) | documented; IIS 总线触发的数据位数（手册 p.404） | 404 |
| `:TRIGger:IIS:DSource` | `:TRIGger:IIS:DSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线触发的数据源（手册 p.404） | 404 |
| `:TRIGger:IIS:DTHReshold` | `:TRIGger:IIS:DTHReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线触发的数据源阈值（手册 p.405） | 405 |
| `:TRIGger:IIS:LATChedge` | `:TRIGger:IIS:LATChedge?` | `<slope>` = `{RISing\|FALLing}`; data is latched on the selected clock edge | documented; IIS 总线触发的时钟采样边沿（手册 p.406） | 406 |
| `:TRIGger:IIS:LATChegde` | `:TRIGger:IIS:LATChegde?` | `<slope>` = `{RISing\|FALLing}`; data is latched on the selected clock edge | documented; 手册标题拼作 `:TRIGger:IIS:LATChedge`，本行为其目录拼写；IIS 触发的时钟采样边沿（手册 p.406） | 406 |
| `:TRIGger:IIS:LCH` | `:TRIGger:IIS:LCH?` | `<level>` = `{LOW\|HIGH}`; `LOW` selects the left channel while WS is low, `HIGH` selects it while WS is high | documented; IIS 总线触发的左声道极性（手册 p.406） | 406 |
| `:TRIGger:IIS:VALue` | `:TRIGger:IIS:VALue?` | `<value>` = Integer (NR1); manual lists no range on this page. Ignored when the data length is 8 and the value is 256 | documented; IIS 总线触发的数据值（手册 p.407） | 407 |
| `:TRIGger:IIS:WSSource` | `:TRIGger:IIS:WSSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; IIS 总线触发的帧时钟（WS）源（手册 p.407） | 407 |
| `:TRIGger:IIS:WSTHreshold` | `:TRIGger:IIS:WSTHreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; IIS 总线触发的帧时钟（WS）阈值（手册 p.408） | 408 |
| `:TRIGger:INTerval` | `:TRIGger:INTerval?` | — | documented; 章节标题，本节无独立参数；间隔触发的参数都在其子命令中（手册 p.308） | 308 |
| `:TRIGger:INTerval:COUPling` | `:TRIGger:INTerval:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 间隔触发的耦合方式（手册 p.308） | 308 |
| `:TRIGger:INTerval:HLDEVent` | `:TRIGger:INTerval:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 间隔触发的触发释抑事件数（手册 p.308） | 308 |
| `:TRIGger:INTerval:HLDTime` | `:TRIGger:INTerval:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 间隔触发的触发释抑时间（手册 p.309） | 309 |
| `:TRIGger:INTerval:HOLDoff` | `:TRIGger:INTerval:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 间隔触发的触发释抑类型（手册 p.309） | 309 |
| `:TRIGger:INTerval:HSTart` | `:TRIGger:INTerval:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 间隔触发的触发释抑启动条件（手册 p.310） | 310 |
| `:TRIGger:INTerval:LEVel` | `:TRIGger:INTerval:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 间隔触发的触发电平（手册 p.310） | 310 |
| `:TRIGger:INTerval:LIMit` | `:TRIGger:INTerval:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 间隔触发的限制条件类型（手册 p.311） | 311 |
| `:TRIGger:INTerval:NREJect` | `:TRIGger:INTerval:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 间隔触发的噪声抑制开关（手册 p.312） | 312 |
| `:TRIGger:INTerval:SLOPe` | `:TRIGger:INTerval:SLOPe?` | `<state>` = `{RISing\|FALLing}` | documented; 间隔触发的斜率类型（手册 p.312） | 312 |
| `:TRIGger:INTerval:SOURce` | `:TRIGger:INTerval:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 间隔触发的触发源（手册 p.312） | 312 |
| `:TRIGger:INTerval:TLOWer` | `:TRIGger:INTerval:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 间隔触发限制条件的下限值（手册 p.313） | 313 |
| `:TRIGger:INTerval:TUPPer` | `:TRIGger:INTerval:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 间隔触发限制条件的上限值（手册 p.311） | 311 |
| `:TRIGger:LIN` | `:TRIGger:LIN?` | — | documented; 章节标题，本节无独立参数；LIN 总线触发的参数都在其子命令中（手册 p.385） | 385 |
| `:TRIGger:LIN:BAUD` | `:TRIGger:LIN:BAUD?` | `<baud>` = `{600bps\|1200bps\|2400bps\|4800bps\|9600bps\|19200bps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 300 to 20000000 | documented; LIN 总线触发的波特率（手册 p.385） | 385 |
| `:TRIGger:LIN:CONDition` | `:TRIGger:LIN:CONDition?` | `<condition>` = `{BReak\|ID\|ID_AND_DATA\|DATA_ERROR}` | documented; LIN 总线触发的触发条件（手册 p.385） | 385 |
| `:TRIGger:LIN:DAT2` | `:TRIGger:LIN:DAT2?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; LIN 总线触发的数据字节 2（手册 p.386） | 386 |
| `:TRIGger:LIN:DATA` | `:TRIGger:LIN:DATA?` | `<data>` = Integer (NR1), 0 to 256; 256 stands for any value (`0xXX`) | documented; LIN 总线触发的数据字节 1（手册 p.386） | 386 |
| `:TRIGger:LIN:ERRor:CHECksum` | `:TRIGger:LIN:ERRor:CHECksum?` | `<state>` = `{0\|1}` (0 = checksum check off, 1 = on) | documented; LIN 触发条件为错误时的校验和检测开关（手册 p.387） | 387 |
| `:TRIGger:LIN:ERRor:DLENgth` | `:TRIGger:LIN:ERRor:DLENgth?` | `<length>` = Integer (NR1), 1 to 8 | documented; LIN 触发条件为错误且开启校验和检测时的错误帧数据长度（手册 p.387） | 387 |
| `:TRIGger:LIN:ERRor:ID` | `:TRIGger:LIN:ERRor:ID?` | `<id>` = Integer (NR1), 0 to 63 | documented; LIN 触发条件为错误时的错误帧 ID（手册 p.388） | 388 |
| `:TRIGger:LIN:ERRor:PARity` | `:TRIGger:LIN:ERRor:PARity?` | `<state>` = `{0\|1}` (0 = header parity check off, 1 = on) | documented; LIN 触发条件为错误时的报头奇偶校验开关（手册 p.388） | 388 |
| `:TRIGger:LIN:ERRor:SYNC` | `:TRIGger:LIN:ERRor:SYNC?` | `<state>` = `{0\|1}` | documented; LIN 触发条件为错误时的同步字节检测开关（手册 p.389） | 389 |
| `:TRIGger:LIN:ID` | `:TRIGger:LIN:ID?` | `<id>` = Integer (NR1), 0 to 64; 64 stands for any value (`0xXX`) | documented; LIN 触发条件为 ID 时的 ID（手册 p.389） | 389 |
| `:TRIGger:LIN:SOURce` | `:TRIGger:LIN:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; LIN 总线触发的信源（手册 p.390） | 390 |
| `:TRIGger:LIN:STANdard` | `:TRIGger:LIN:STANdard?` | `<version>` = `{0\|1}` (0 = Rev1.3, 1 = Rev2.x) | documented; LIN 触发条件为错误且开启数据校验时的协议版本（手册 p.390） | 390 |
| `:TRIGger:LIN:Source` | `:TRIGger:LIN:Source?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 手册该页的命令格式拼作 `Source`、描述与示例用 `SOURce`；LIN 总线触发的信源（手册 p.390） | 390 |
| `:TRIGger:LIN:THReshold` | `:TRIGger:LIN:THReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; LIN 总线触发的阈值（手册 p.390） | 390 |
| `:TRIGger:NEDGe` | `:TRIGger:NEDGe?` | — | documented; 章节标题，本节无独立参数；第 N 边沿触发的参数都在其子命令中（手册 p.345） | 345 |
| `:TRIGger:NEDGe:EDGE` | `:TRIGger:NEDGe:EDGE?` | `<value>` = Integer (NR1), 1 to 65535 | documented; 第 N 边沿触发的边沿数（手册 p.346） | 346 |
| `:TRIGger:NEDGe:HLDEVent` | `:TRIGger:NEDGe:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 第 N 边沿触发的触发释抑事件数（手册 p.348） | 348 |
| `:TRIGger:NEDGe:HLDEvent` | `:TRIGger:NEDGe:HLDEvent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 手册示例把 `:TRIGger:NEDGe:HLDEVent` 写成 `HLDEvent`（手册笔误），本行即该示例拼写；第 N 边沿触发的触发释抑事件数（手册 p.349） | 349 |
| `:TRIGger:NEDGe:HLDTime` | `:TRIGger:NEDGe:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s (manual prints it as `{8.00E-09,3.00E+01}`) | documented; 第 N 边沿触发的触发释抑时间（手册 p.348） | 348 |
| `:TRIGger:NEDGe:HOLDoff` | `:TRIGger:NEDGe:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 第 N 边沿触发的触发释抑类型（手册 p.347） | 347 |
| `:TRIGger:NEDGe:HSTart` | `:TRIGger:NEDGe:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 第 N 边沿触发的触发释抑启动条件（手册 p.348） | 348 |
| `:TRIGger:NEDGe:IDLE` | `:TRIGger:NEDGe:IDLE?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 2.00E+01] s | documented; 第 N 边沿触发的空闲时间（手册 p.346） | 346 |
| `:TRIGger:NEDGe:LEVel` | `:TRIGger:NEDGe:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 第 N 边沿触发的触发电平（手册 p.347） | 347 |
| `:TRIGger:NEDGe:NREJect` | `:TRIGger:NEDGe:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 第 N 边沿触发的噪声抑制开关（手册 p.349） | 349 |
| `:TRIGger:NEDGe:SLOPe` | `:TRIGger:NEDGe:SLOPe?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 第 N 边沿触发的斜率类型（手册 p.345） | 345 |
| `:TRIGger:NEDGe:SOURce` | `:TRIGger:NEDGe:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 第 N 边沿触发的触发源（手册 p.345） | 345 |
| `:TRIGger:PATTern` | `:TRIGger:PATTern?` | — | documented; 章节标题，本节无独立参数；码型触发的参数都在其子命令中（手册 p.329） | 329 |
| `:TRIGger:PATTern:HLDEVent` | `:TRIGger:PATTern:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 码型触发的触发释抑事件数（手册 p.329） | 329 |
| `:TRIGger:PATTern:HLDTime` | `:TRIGger:PATTern:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 码型触发的触发释抑时间（手册 p.329） | 329 |
| `:TRIGger:PATTern:HOLDoff` | `:TRIGger:PATTern:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 码型触发的触发释抑类型（手册 p.330） | 330 |
| `:TRIGger:PATTern:HSTart` | `:TRIGger:PATTern:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 码型触发的触发释抑启动条件（手册 p.330） | 330 |
| `:TRIGger:PATTern:INPut` | `:TRIGger:PATTern:INPut?` | `<logic>` = `{X\|L\|H}`, one entry per source, mapped in the order C1-C<n>, D0-D15; `X` = don't care, `H` = high, `L` = low | documented; 码型触发源的逻辑状态（手册 p.331） | 331 |
| `:TRIGger:PATTern:LEVel` | `:TRIGger:PATTern:LEVel?` | `<source>` = `{C<n>}` (`<n>` = channel index NR1), `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 码型触发源的逻辑电平（手册 p.331） | 331 |
| `:TRIGger:PATTern:LIMit` | `:TRIGger:PATTern:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 码型触发的限制条件类型（手册 p.332） | 332 |
| `:TRIGger:PATTern:LOGic` | `:TRIGger:PATTern:LOGic?` | `<logic_type>` = `{AND\|OR\|NAND\|NOR}` | documented; 码型触发的逻辑关系（手册 p.333） | 333 |
| `:TRIGger:PATTern:TLOWer` | `:TRIGger:PATTern:TLOWer?` | `<value>` = Real (NR3); no range listed. Must not exceed the upper limit (`:TRIGger:PATTern:TUPPer`); not usable when the limit type is `<=` | documented; 码型触发限制条件的下限值（手册 p.333） | 333 |
| `:TRIGger:PATTern:TUPPer` | `:TRIGger:PATTern:TUPPer?` | `<value>` = Real (NR3); no range listed. Must not be below the lower limit (`:TRIGger:PATTern:TLOWer`); not usable when the limit type is `>=` | documented; 码型触发限制条件的上限值（手册 p.333） | 333 |
| `:TRIGger:PULSe` | `:TRIGger:PULSe?` | — | documented; 章节标题，本节无独立参数；脉宽触发的参数都在其子命令中（手册 p.288） | 288 |
| `:TRIGger:PULSe:COUPling` | `:TRIGger:PULSe:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 脉宽触发的耦合方式（手册 p.288） | 288 |
| `:TRIGger:PULSe:HLDEVent` | `:TRIGger:PULSe:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 脉宽触发的触发释抑事件数（手册 p.288） | 288 |
| `:TRIGger:PULSe:HLDTime` | `:TRIGger:PULSe:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 脉宽触发的触发释抑时间（手册 p.289） | 289 |
| `:TRIGger:PULSe:HOLDoff` | `:TRIGger:PULSe:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 脉宽触发的触发释抑类型（手册 p.289） | 289 |
| `:TRIGger:PULSe:HSTart` | `:TRIGger:PULSe:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 脉宽触发的触发释抑启动条件（手册 p.290） | 290 |
| `:TRIGger:PULSe:LEVel` | `:TRIGger:PULSe:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 脉宽触发的触发电平（手册 p.290） | 290 |
| `:TRIGger:PULSe:LIMit` | `:TRIGger:PULSe:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 脉宽触发的限制条件类型（手册 p.291） | 291 |
| `:TRIGger:PULSe:NREJect` | `:TRIGger:PULSe:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 脉宽触发的噪声抑制开关（手册 p.292） | 292 |
| `:TRIGger:PULSe:POLarity` | `:TRIGger:PULSe:POLarity?` | `<polarity_type>` = `{POSitive\|NEGative}` | documented; 脉宽触发的极性（手册 p.292） | 292 |
| `:TRIGger:PULSe:SOURce` | `:TRIGger:PULSe:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 脉宽触发的触发源（手册 p.292） | 292 |
| `:TRIGger:PULSe:TLOWer` | `:TRIGger:PULSe:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 脉宽触发限制条件的下限值（手册 p.293） | 293 |
| `:TRIGger:PULSe:TUPPer` | `:TRIGger:PULSe:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 脉宽触发限制条件的上限值（手册 p.291） | 291 |
| `:TRIGger:QUALified` | `:TRIGger:QUALified?` | — | documented; 章节标题，本节无独立参数；前提边沿触发的参数都在其子命令中（手册 p.335） | 335 |
| `:TRIGger:QUALified:ELEVel` | `:TRIGger:QUALified:ELEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 前提边沿触发的边沿触发电平（手册 p.335） | 335 |
| `:TRIGger:QUALified:ELVel` | `:TRIGger:QUALified:ELVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 手册该节标题拼作 `:TRIGger:QUALified:ELEVel`、命令格式却写作 `:TRIGger:QUALified:ELVel`；前提边沿触发的边沿触发电平（手册 p.335） | 335 |
| `:TRIGger:QUALified:ESLope` | `:TRIGger:QUALified:ESLope?` | `<type>` = `{RISing\|FALLing}` | documented; 前提边沿触发的边沿触发斜率类型（手册 p.335） | 335 |
| `:TRIGger:QUALified:ESource` | `:TRIGger:QUALified:ESource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 前提边沿触发的边沿触发信源（手册 p.336） | 336 |
| `:TRIGger:QUALified:LIMit` | `:TRIGger:QUALified:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 前提边沿触发的限制条件类型（手册 p.336） | 336 |
| `:TRIGger:QUALified:QLEVel` | `:TRIGger:QUALified:QLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 前提边沿触发的前提信号电平（手册 p.337） | 337 |
| `:TRIGger:QUALified:QSource` | `:TRIGger:QUALified:QSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 前提边沿触发的前提信号信源（手册 p.337） | 337 |
| `:TRIGger:QUALified:TLOWer` | `:TRIGger:QUALified:TLOWer?` | `<value>` = Real (NR3); no range listed. Must not exceed the upper limit; not usable when the limit type is `<=`. Only valid when the qualifier type is level+time or edge+time | documented; 前提边沿触发限制条件的下限值（手册 p.338） | 338 |
| `:TRIGger:QUALified:TUPPer` | `:TRIGger:QUALified:TUPPer?` | `<value>` = Real (NR3); no range listed. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 前提边沿触发限制条件的上限值（手册 p.337） | 337 |
| `:TRIGger:QUALified:TYPE` | `:TRIGger:QUALified:TYPE?` | `<type>` = `{STATe\|STATE_DLY\|EDGE\|EDGE_DLY}`; `<option>` = `{LOW\|HIGH}` when the type is `STATe`/`STATE_DLY`, `{RISing\|FALLing}` when it is `EDGE`/`EDGE_DLY` | documented; 前提边沿触发的前提类型（手册 p.339） | 339 |
| `:TRIGger:RUNT` | `:TRIGger:RUNT?` | — | documented; 章节标题，本节无独立参数；欠幅触发的参数都在其子命令中（手册 p.321） | 321 |
| `:TRIGger:RUNT:COUPling` | `:TRIGger:RUNT:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 欠幅触发的耦合方式（手册 p.321） | 321 |
| `:TRIGger:RUNT:HLDEVent` | `:TRIGger:RUNT:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 欠幅触发的触发释抑事件数（手册 p.321） | 321 |
| `:TRIGger:RUNT:HLDTime` | `:TRIGger:RUNT:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s (manual heading misspells it `:TRIGger:RUNt:HLDTime`) | documented; 欠幅触发的触发释抑时间（手册 p.322） | 322 |
| `:TRIGger:RUNT:HLEVel` | `:TRIGger:RUNT:HLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 欠幅触发的触发高电平（手册 p.322） | 322 |
| `:TRIGger:RUNT:HOLDoff` | `:TRIGger:RUNT:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 欠幅触发的触发释抑类型（手册 p.323） | 323 |
| `:TRIGger:RUNT:HSTart` | `:TRIGger:RUNT:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 欠幅触发的触发释抑启动条件（手册 p.323） | 323 |
| `:TRIGger:RUNT:LIMit` | `:TRIGger:RUNT:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 欠幅触发的限制条件类型（手册 p.324） | 324 |
| `:TRIGger:RUNT:LLEVel` | `:TRIGger:RUNT:LLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:TRIGger:RUNT:HLEVel`) | documented; 欠幅触发的触发低电平（手册 p.325） | 325 |
| `:TRIGger:RUNT:NREJect` | `:TRIGger:RUNT:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 欠幅触发的噪声抑制开关（手册 p.325） | 325 |
| `:TRIGger:RUNT:POLarity` | `:TRIGger:RUNT:POLarity?` | `<polarity_type>` = `{POSitive\|NEGative}` | documented; 欠幅触发的极性（手册 p.326） | 326 |
| `:TRIGger:RUNT:SOURce` | `:TRIGger:RUNT:SOURce?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; 欠幅触发的触发源（手册 p.326） | 326 |
| `:TRIGger:RUNT:TLOWer` | `:TRIGger:RUNT:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 欠幅触发限制条件的下限值（手册 p.327） | 327 |
| `:TRIGger:RUNT:TUPPer` | `:TRIGger:RUNT:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 欠幅触发限制条件的上限值（手册 p.324） | 324 |
| `:TRIGger:RUNt:HLDTime` | `:TRIGger:RUNt:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 手册该节标题把 `:TRIGger:RUNT:HLDTime` 印成 `RUNt`，本行即该拼写；欠幅触发的触发释抑时间（手册 p.322） | 322 |
| `:TRIGger:SENT:SOURce` | `:TRIGger:SENT:SOURce?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SENT 总线触发的信源（手册 p.409） | 409 |
| `:TRIGger:SENT:THReshold` | `:TRIGger:SENT:THReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SENT 总线触发的阈值（手册 p.409） | 409 |
| `:TRIGger:SHOL:TUPPer` | `:TRIGger:SHOL:TUPPer?` | `<value>` = Real (NR3); no range listed. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 手册示例把 `:TRIGger:SHOLd:TUPPer` 写成 `SHOL`（手册笔误），本行即该示例拼写；建立/保持触发限制条件的上限值（手册 p.355） | 355 |
| `:TRIGger:SHOLd` | `:TRIGger:SHOLd?` | — | documented; 章节标题，本节无独立参数；建立/保持触发的参数都在其子命令中（手册 p.351） | 351 |
| `:TRIGger:SHOLd:CSource` | `:TRIGger:SHOLd:CSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 建立/保持触发的时钟信源（手册 p.351） | 351 |
| `:TRIGger:SHOLd:CTHReshold` | `:TRIGger:SHOLd:CTHReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 建立/保持触发的时钟阈值（手册 p.352） | 352 |
| `:TRIGger:SHOLd:DSource` | `:TRIGger:SHOLd:DSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; 建立/保持触发的数据信源（手册 p.353） | 353 |
| `:TRIGger:SHOLd:DTHReshold` | `:TRIGger:SHOLd:DTHReshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 建立/保持触发的数据源阈值（手册 p.353） | 353 |
| `:TRIGger:SHOLd:LEVel` | `:TRIGger:SHOLd:LEVel?` | `<level_value>` = `{LOW\|HIGH}` | documented; 建立/保持触发的数据源电平状态（手册 p.354） | 354 |
| `:TRIGger:SHOLd:LIMit` | `:TRIGger:SHOLd:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 建立/保持触发的限制条件类型（手册 p.354） | 354 |
| `:TRIGger:SHOLd:SLOPe` | `:TRIGger:SHOLd:SLOPe?` | `<state>` = `{RISing\|FALLing}` | documented; 建立/保持触发的斜率类型（手册 p.352） | 352 |
| `:TRIGger:SHOLd:TLOWer` | `:TRIGger:SHOLd:TLOWer?` | `<value>` = Real (NR3); no range listed. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 建立/保持触发限制条件的下限值（手册 p.355） | 355 |
| `:TRIGger:SHOLd:TUPPer` | `:TRIGger:SHOLd:TUPPer?` | `<value>` = Real (NR3); no range listed. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 建立/保持触发限制条件的上限值（手册 p.355） | 355 |
| `:TRIGger:SHOLd:TYPE` | `:TRIGger:SHOLd:TYPE?` | `<type>` = `{SETup\|HOLD}` | documented; 建立/保持触发的类型（手册 p.351） | 351 |
| `:TRIGger:SLOPe` | `:TRIGger:SLOPe?` | — | documented; 章节标题，本节无独立参数；斜率触发的参数都在其子命令中（手册 p.280） | 280 |
| `:TRIGger:SLOPe:COUPling` | `:TRIGger:SLOPe:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 斜率触发的耦合方式（手册 p.280） | 280 |
| `:TRIGger:SLOPe:HLDEVent` | `:TRIGger:SLOPe:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 斜率触发的触发释抑事件数（手册 p.280） | 280 |
| `:TRIGger:SLOPe:HLDTime` | `:TRIGger:SLOPe:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 斜率触发的触发释抑时间（手册 p.281） | 281 |
| `:TRIGger:SLOPe:HLEVel` | `:TRIGger:SLOPe:HLEVel?` | `<high_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 斜率触发的触发高电平（手册 p.281） | 281 |
| `:TRIGger:SLOPe:HOLDoff` | `:TRIGger:SLOPe:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 斜率触发的触发释抑类型（手册 p.282） | 282 |
| `:TRIGger:SLOPe:HSTart` | `:TRIGger:SLOPe:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 斜率触发的触发释抑启动条件（手册 p.282） | 282 |
| `:TRIGger:SLOPe:LIMit` | `:TRIGger:SLOPe:LIMit?` | `<type>` = `{LESSthan\|GREATerthan\|INNer\|OUTer}` (`<=`, `>=`, inside the time range, outside the time range) | documented; 斜率触发的限制条件类型（手册 p.283） | 283 |
| `:TRIGger:SLOPe:LLEVel` | `:TRIGger:SLOPe:LLEVel?` | `<low_level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:TRIGger:SLOPe:HLEVel`) | documented; 斜率触发的触发低电平（手册 p.284） | 284 |
| `:TRIGger:SLOPe:NREJect` | `:TRIGger:SLOPe:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 斜率触发的噪声抑制开关（手册 p.284） | 284 |
| `:TRIGger:SLOPe:SLOPe` | `:TRIGger:SLOPe:SLOPe?` | `<slope_type>` = `{RISing\|FALLing}` | documented; 斜率触发的斜率类型（手册 p.285） | 285 |
| `:TRIGger:SLOPe:SOURce` | `:TRIGger:SLOPe:SOURce?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; 斜率触发的触发源（手册 p.285） | 285 |
| `:TRIGger:SLOPe:TLOWer` | `:TRIGger:SLOPe:TLOWer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not exceed the upper limit; not usable when the limit type is `<=` | documented; 斜率触发限制条件的下限值（手册 p.286） | 286 |
| `:TRIGger:SLOPe:TUPPer` | `:TRIGger:SLOPe:TUPPer?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-2.00E-09, 2.00E+01] s. Must not be below the lower limit; not usable when the limit type is `>=` | documented; 斜率触发限制条件的上限值（手册 p.283） | 283 |
| `:TRIGger:SPI` | `:TRIGger:SPI?` | — | documented; 章节标题，本节无独立参数；SPI 总线触发的参数都在其子命令中（手册 p.363） | 363 |
| `:TRIGger:SPI:BITorder` | `:TRIGger:SPI:BITorder?` | `<bit_order>` = `{LSM\|MSB}` (`LSM` = least significant bit first, `MSB` = most significant bit first) | documented; SPI 总线触发的比特流格式（手册 p.363） | 363 |
| `:TRIGger:SPI:CLKSource` | `:TRIGger:SPI:CLKSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线触发的 CLK（时钟）信源（手册 p.363） | 363 |
| `:TRIGger:SPI:CLKThreshold` | `:TRIGger:SPI:CLKThreshold?` | `<clk_threshold>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线触发的 CLK（时钟）阈值（手册 p.364） | 364 |
| `:TRIGger:SPI:CSSource` | `:TRIGger:SPI:CSSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线触发的 CS（片选）信源（手册 p.364） | 364 |
| `:TRIGger:SPI:CSTYpe` | `:TRIGger:SPI:CSTYpe?` | `<type>` = `{NCS\|CS\|TIMeout[,<time>]}`; `NCS` frames on chip select low, `CS` on chip select high (both need a CS source and threshold), `TIMeout` needs no CS source but `<time>` = Real (NR3), 1.00E-07 to 5.00E-03 (minimum clock-idle time) | documented; SPI 总线触发的片选类型（手册 p.366） | 366 |
| `:TRIGger:SPI:CSThreshold` | `:TRIGger:SPI:CSThreshold?` | `<threshold>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线触发的 CS（片选）阈值（手册 p.365） | 365 |
| `:TRIGger:SPI:DATA` | `:TRIGger:SPI:DATA?` | `<data>` = `{0\|1\|X}` per bit; the number of values must match the length set by `:TRIGger:SPI:DLENgth`, bits are assigned from the most significant down | documented; SPI 总线触发的数据码型（手册 p.366） | 366 |
| `:TRIGger:SPI:DLENgth` | `:TRIGger:SPI:DLENgth?` | `<data_length>` = Integer (NR1), 4 to 96 | documented; SPI 总线触发的数据长度（手册 p.367） | 367 |
| `:TRIGger:SPI:LATC` | `:TRIGger:SPI:LATC?` | `<slope>` = `{RISing\|FALLing}` | documented; `LATChedge` 的短形式；手册该节命令格式把长、短拼写混写（命令格式 `:TRIGger:SPI:CLK:LATChedge`、查询 `:TRIGger:SPI:LATC?`）；SPI 触发的时钟采样边沿（手册 p.367） | 367 |
| `:TRIGger:SPI:LATChedge` | `:TRIGger:SPI:LATChedge?` | `<slope>` = `{RISing\|FALLing}` | documented; SPI 总线触发的 CLK（时钟）采样边沿（手册 p.367） | 367 |
| `:TRIGger:SPI:MISOSource` | `:TRIGger:SPI:MISOSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线触发的 MISO 信源（手册 p.367） | 367 |
| `:TRIGger:SPI:MISOThreshold` | `:TRIGger:SPI:MISOThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线触发的 MISO 阈值（手册 p.368） | 368 |
| `:TRIGger:SPI:MOSISource` | `:TRIGger:SPI:MOSISource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线触发的 MOSI 信源（手册 p.369） | 369 |
| `:TRIGger:SPI:MOSIThreshold` | `:TRIGger:SPI:MOSIThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线触发的 MOSI 阈值（手册 p.369） | 369 |
| `:TRIGger:SPI:NCSSource` | `:TRIGger:SPI:NCSSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; SPI 总线触发的 NCS 信源（手册 p.370） | 370 |
| `:TRIGger:SPI:NCSThreshold` | `:TRIGger:SPI:NCSThreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; SPI 总线触发的 NCS 阈值（手册 p.370） | 370 |
| `:TRIGger:SPI:TTYPe` | `:TRIGger:SPI:TTYPe?` | `<trigger_type>` = `{MISO\|MOSI}` | documented; SPI 总线触发的触发源类型（手册 p.371） | 371 |
| `:TRIGger:STATus` | `:TRIGger:STATus?` | — | documented; 只读查询当前触发状态，返回 `{Arm\|Ready\|Auto\|Trig'd\|Stop\|Roll}`；手册该页无输入参数（手册 p.272） | 272 |
| `:TRIGger:STOP` | `:TRIGger:STOP?` | — | documented; 事件命令（无参数），把示波器置为 Stop，等同前面板 Run/Stop 键的 Stop（手册 p.272） | 272 |
| `:TRIGger:UART` | `:TRIGger:UART?` | — | documented; 章节标题，本节无独立参数；UART 总线触发的参数都在其子命令中（手册 p.372） | 372 |
| `:TRIGger:UART:BAUD` | `:TRIGger:UART:BAUD?` | `<baud>` = `{600bps\|1200bps\|2400bps\|4800bps\|9600bps\|19200bps\|38400bps\|57600bps\|115200bps\|CUSTom[,<value>]}`; `<value>` = Integer (NR1), 300 to 20000000 | documented; UART 总线触发的波特率（手册 p.372） | 372 |
| `:TRIGger:UART:BITorder` | `:TRIGger:UART:BITorder?` | `<order>` = `{LSM\|MSB}` (`LSM` = least significant bit first, `MSB` = most significant bit first) | documented; UART 总线触发的比特流格式（手册 p.372） | 372 |
| `:TRIGger:UART:CONDition` | `:TRIGger:UART:CONDition?` | `<condition>` = `{STARt\|STOP\|DATA\|ERRor}` | documented; UART 总线触发的触发条件（手册 p.373） | 373 |
| `:TRIGger:UART:DATA` | `:TRIGger:UART:DATA?` | `<data>` = Integer (NR1); the value count must match the length set by `:TRIGger:UART:DLENgth`, and "any value" is the maximum plus 1 (e.g. 256 for an 8-bit length) | documented; UART 总线触发的数据（手册 p.373） | 373 |
| `:TRIGger:UART:DLENgth` | `:TRIGger:UART:DLENgth?` | `<value>` = Integer (NR1), 5 to 8 | documented; UART 总线触发的数据长度（手册 p.374） | 374 |
| `:TRIGger:UART:IDLE` | `:TRIGger:UART:IDLE?` | `<idle>` = `{LOW\|HIGH}` | documented; UART 总线触发的空闲电平（手册 p.374） | 374 |
| `:TRIGger:UART:LIMit` | `:TRIGger:UART:LIMit?` | `<limit_type>` = `{EQUal\|GREaterthan\|LESSthan}`; only when the trigger condition is `DATA` | documented; UART 触发条件为 DATA 时的限制条件（手册 p.375） | 375 |
| `:TRIGger:UART:PARity` | `:TRIGger:UART:PARity?` | `<parity>` = `{NONE\|ODD\|EVEN\|MARK\|SPACe}` (none / odd / even / mark = 1 / space = 0) | documented; UART 总线触发的奇偶校验（手册 p.375） | 375 |
| `:TRIGger:UART:RXSource` | `:TRIGger:UART:RXSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; UART 总线触发的 RX 信源（手册 p.376） | 376 |
| `:TRIGger:UART:RXTHreshold` | `:TRIGger:UART:RXTHreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; UART 总线触发的 RX 阈值（手册 p.376） | 376 |
| `:TRIGger:UART:STOP` | `:TRIGger:UART:STOP?` | `<bit>` = `{1\|1.5\|2}` | documented; UART 总线触发的停止位数（手册 p.377） | 377 |
| `:TRIGger:UART:TTYPe` | `:TRIGger:UART:TTYPe?` | `<trigger_type>` = `{RX\|TX}` | documented; UART 总线触发的触发源类型（手册 p.377） | 377 |
| `:TRIGger:UART:TXSource` | `:TRIGger:UART:TXSource?` | `<source>` = `{C<n>\|D<d>}`; `<n>` = analog channel NR1, `<d>` = digital channel NR1 | documented; UART 总线触发的 TX 信源（手册 p.378） | 378 |
| `:TRIGger:UART:TXTHreshold` | `:TRIGger:UART:TXTHreshold?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; UART 总线触发的 TX 阈值（手册 p.378） | 378 |
| `:TRIGger:VIDeo` | `:TRIGger:VIDeo?` | — | documented; 章节标题，本节无独立参数；视频触发的参数都在其子命令中（手册 p.295） | 295 |
| `:TRIGger:VIDeo:FCNT` | `:TRIGger:VIDeo:FCNT?` | `<field_cnt>` = `{1\|2\|4\|8}` | documented; 视频触发自定义标准下的场数（手册 p.295） | 295 |
| `:TRIGger:VIDeo:FIELd` | `:TRIGger:VIDeo:FIELd?` | `<field>` = `{1\|2}`; only valid for the NTSC, PAL, 1080i/50 and 1080i/60 standards | documented; 视频触发的同步触发场数（手册 p.295） | 295 |
| `:TRIGger:VIDeo:FRATe` | `:TRIGger:VIDeo:FRATe?` | `<field>` = `{25Hz\|30Hz\|50Hz\|60Hz}` | documented; 视频触发自定义标准下的帧速率（手册 p.296） | 296 |
| `:TRIGger:VIDeo:INTerlace` | `:TRIGger:VIDeo:INTerlace?` | `<field>` = `{1\|2\|4\|8}` | documented; 视频触发自定义标准下的交错比例（手册 p.296） | 296 |
| `:TRIGger:VIDeo:LCNT` | `:TRIGger:VIDeo:LCNT?` | `<line_cnt>` = Integer (NR1), 300 to 2000 | documented; 视频触发自定义标准下的行数（手册 p.296） | 296 |
| `:TRIGger:VIDeo:LEVel` | `:TRIGger:VIDeo:LEVel?` | `<level_value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 视频触发的触发电平（手册 p.297） | 297 |
| `:TRIGger:VIDeo:LINE` | `:TRIGger:VIDeo:LINE?` | `<line>` = Integer (NR1); per-standard limits: NTSC field1 1-263 / field2 1-262, PAL 1-313 / 1-312, 720P50/60 1-750, 1080P50/60 1-1125, 1080i50/60 1-563 / 1-562 | documented; 视频触发非自定义标准下的同步触发行数（手册 p.298） | 298 |
| `:TRIGger:VIDeo:SOURce` | `:TRIGger:VIDeo:SOURce?` | `<source>` = `{C<n>}`; no digital source | documented; 视频触发的触发源（手册 p.298） | 298 |
| `:TRIGger:VIDeo:STANdard` | `:TRIGger:VIDeo:STANdard?` | `<standard>` = `{NTSC\|PAL\|P720L50\|P720L60\|P1080L50\|P1080L60\|I1080L50\|I1080L60\|CUSTom}` | documented; 视频触发的标准类型（手册 p.299） | 299 |
| `:TRIGger:VIDeo:SYNC` | `:TRIGger:VIDeo:SYNC?` | `<sync>` = `{SELect\|ANY}`; `SELect` triggers on the chosen field and line, `ANY` on any line that meets the condition | documented; 视频触发的同步模式（手册 p.295） | 295 |
| `:TRIGger:WIND:HLDTime` | `:TRIGger:WIND:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 手册该节命令格式把查询写作 `:TRIGger:WIND:HLDTime?`（短拼写），本行即该拼写；窗口触发的触发释抑时间（手册 p.303） | 303 |
| `:TRIGger:WIND:HOLDoff` | `:TRIGger:WIND:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 手册该节命令格式写作 `:TRIGger:WIND:HOLDoff`（短拼写），本行即该拼写；窗口触发的触发释抑类型（手册 p.304） | 304 |
| `:TRIGger:WINDow` | `:TRIGger:WINDow?` | — | documented; 章节标题，本节无独立参数；窗口触发的参数都在其子命令中（手册 p.301） | 301 |
| `:TRIGger:WINDow:CLEVel` | `:TRIGger:WINDow:CLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 窗口触发的相对中心电平（手册 p.301） | 301 |
| `:TRIGger:WINDow:COUPling` | `:TRIGger:WINDow:COUPling?` | `<mode>` = `{DC\|AC\|LFREJect\|HFREJect}`; `DC` passes all components, `AC` blocks DC, `LFREJect` is a high-pass and `HFREJect` a low-pass (cut-off frequencies in the datasheet) | documented; 窗口触发的耦合方式（手册 p.301） | 301 |
| `:TRIGger:WINDow:DLEVel` | `:TRIGger:WINDow:DLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset] | documented; 窗口触发的相对电平范围（手册 p.302） | 302 |
| `:TRIGger:WINDow:HLDEVent` | `:TRIGger:WINDow:HLDEVent?` | `<value>` = Integer (NR1), 1 to 100000000 | documented; 窗口触发的触发释抑事件数（手册 p.303） | 303 |
| `:TRIGger:WINDow:HLDTime` | `:TRIGger:WINDow:HLDTime?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [8.00E-09, 3.00E+01] s | documented; 窗口触发的触发释抑时间（手册 p.303） | 303 |
| `:TRIGger:WINDow:HLEVel` | `:TRIGger:WINDow:HLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The high level must not be below the low level (`:TRIGger:WINDow:LLEVel`) | documented; 窗口触发的绝对高电平（手册 p.304） | 304 |
| `:TRIGger:WINDow:HOLDoff` | `:TRIGger:WINDow:HOLDoff?` | `<holdoff_type>` = `{OFF\|EVENts\|TIME}`; `EVENts` = number of trigger events, `TIME` = wait time after a trigger before the trigger circuit re-arms | documented; 窗口触发的触发释抑类型（手册 p.304） | 304 |
| `:TRIGger:WINDow:HSTart` | `:TRIGger:WINDow:HSTart?` | `<start_holdoff>` = `{LAST_TRIG\|ACQ_START}`; `LAST_TRIG` starts counting at the previous trigger, `ACQ_START` at the first sample that meets the trigger condition | documented; 窗口触发的触发释抑启动条件（手册 p.305） | 305 |
| `:TRIGger:WINDow:LLEVel` | `:TRIGger:WINDow:LLEVel?` | `<value>` = Real (NR3); range depends on model - SDS800X HD: [-4.1*vertical scale - vertical offset, 4.1*vertical scale - vertical offset]. The low level must not exceed the high level (`:TRIGger:WINDow:HLEVel`) | documented; 窗口触发的绝对低电平（手册 p.305） | 305 |
| `:TRIGger:WINDow:NREJect` | `:TRIGger:WINDow:NREJect?` | `<state>` = `{OFF\|ON}` | documented; 窗口触发的噪声抑制开关（手册 p.306） | 306 |
| `:TRIGger:WINDow:SOURce` | `:TRIGger:WINDow:SOURce?` | `<source>` = `{C<n>}` (`<n>` = analog channel NR1); no digital source | documented; 窗口触发的触发源（手册 p.307） | 307 |
| `:TRIGger:WINDow:TYPE` | `:TRIGger:WINDow:TYPE?` | `<type>` = `{ABSolute\|RELative}`; `ABSolute` sets the high and low trigger levels independently, `RELative` moves them together or scales their distance | documented; 窗口触发的窗口类型（手册 p.307） | 307 |
| `:WAVeform:DATA` | `:WAVeform:DATA?` | — | documented; 只读查询 `:WAVeform:SOURce` 指定源的波形数据；手册该页无输入参数（手册 p.418） | 418 |
| `:WAVeform:MAXPoint` | `:WAVeform:MAXPoint?` | — | documented; 只读查询单片数据的点数（大记录长度需分片读取）；手册该页无输入参数（手册 p.413） | 413 |
| `:WAVeform:PRE` | `:WAVeform:PRE?` | — | documented; `PREamble` 的短形式，只读查询 `:WAVeform:SOURce` 指定源的波形参数；手册该页无输入参数（手册 p.418） | 418 |
| `:WAVeform:PREamble` | `:WAVeform:PREamble?` | — | documented; 只读查询 `:WAVeform:SOURce` 指定源的波形参数（含分片所需字段）；手册该页无输入参数（手册 p.412） | 412 |
| `:WAVeform:SEQuence` | `:WAVeform:SEQuence?` | `<value1>` = frame number, Integer (NR1); 0 returns all frames. `<value2>` = start frame, Integer (NR1), used to read all frames in slices when the total exceeds the memory limit. Defaults: 1 with segmented acquisition on, the last frame with history on, otherwise 4294967295; the range depends on the current segment count | documented; 分段采集时读取哪一帧波形（手册 p.422） | 422 |
