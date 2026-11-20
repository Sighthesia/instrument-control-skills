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
PDF page come from the manual, the parameter column does not. Rows are
`documented` only — nothing here was exercised on hardware, and the curated
tables above remain the place to look for behaviour, caveats and evidence labels.

`780` commands below have no curated row above. The query column names the
`?` form the SCPI convention implies; confirm it against the manual page before
relying on it.

| Syntax | Query | Parameters / range | Note | PDF page |
|---|---|---|---|---|
| `:COUNter:STATistics:VALue` | `:COUNter:STATistics:VALue?` | see p.62 | documented; TOC/body-heading derived, parameters not transcribed | 62 |
| `:CURSor:IXDelta` | `:CURSor:IXDelta?` | see p.68 | documented; TOC/body-heading derived, parameters not transcribed | 68 |
| `:CURSor:MANual:X2` | `:CURSor:MANual:X2?` | see p.74 | documented; TOC/body-heading derived, parameters not transcribed | 74 |
| `:CURSor:MANual:X2:COLor` | `:CURSor:MANual:X2:COLor?` | see p.74 | documented; TOC/body-heading derived, parameters not transcribed | 74 |
| `:CURSor:MANual:X2:DFOLlow` | `:CURSor:MANual:X2:DFOLlow?` | see p.75 | documented; TOC/body-heading derived, parameters not transcribed | 75 |
| `:CURSor:MANual:X2:DTCursor` | `:CURSor:MANual:X2:DTCursor?` | see p.75 | documented; TOC/body-heading derived, parameters not transcribed | 75 |
| `:CURSor:MANual:X2:DVALue` | `:CURSor:MANual:X2:DVALue?` | see p.76 | documented; TOC/body-heading derived, parameters not transcribed | 76 |
| `:CURSor:MANual:X2:LABel` | `:CURSor:MANual:X2:LABel?` | see p.77 | documented; TOC/body-heading derived, parameters not transcribed | 77 |
| `:CURSor:MANual:X2:POSition` | `:CURSor:MANual:X2:POSition?` | see p.77 | documented; TOC/body-heading derived, parameters not transcribed | 77 |
| `:CURSor:MANual:X2:SOURce` | `:CURSor:MANual:X2:SOURce?` | see p.78 | documented; TOC/body-heading derived, parameters not transcribed | 78 |
| `:CURSor:MANual:X<n>` | `:CURSor:MANual:X<n>?` | see p.74 | documented; TOC/body-heading derived, parameters not transcribed | 74 |
| `:CURSor:MANual:X<n>:COLor` | `:CURSor:MANual:X<n>:COLor?` | see p.74 | documented; TOC/body-heading derived, parameters not transcribed | 74 |
| `:CURSor:MANual:X<n>:DFOLlow` | `:CURSor:MANual:X<n>:DFOLlow?` | see p.75 | documented; TOC/body-heading derived, parameters not transcribed | 75 |
| `:CURSor:MANual:X<n>:DTCursor` | `:CURSor:MANual:X<n>:DTCursor?` | see p.75 | documented; TOC/body-heading derived, parameters not transcribed | 75 |
| `:CURSor:MANual:X<n>:DVALue` | `:CURSor:MANual:X<n>:DVALue?` | see p.76 | documented; TOC/body-heading derived, parameters not transcribed | 76 |
| `:CURSor:MANual:X<n>:LABel` | `:CURSor:MANual:X<n>:LABel?` | see p.76 | documented; TOC/body-heading derived, parameters not transcribed | 76 |
| `:CURSor:MANual:X<n>:POSition` | `:CURSor:MANual:X<n>:POSition?` | see p.77 | documented; TOC/body-heading derived, parameters not transcribed | 77 |
| `:CURSor:MANual:X<n>:SOURce` | `:CURSor:MANual:X<n>:SOURce?` | see p.77 | documented; TOC/body-heading derived, parameters not transcribed | 77 |
| `:CURSor:MANual:Y2` | `:CURSor:MANual:Y2?` | see p.78 | documented; TOC/body-heading derived, parameters not transcribed | 78 |
| `:CURSor:MANual:Y2:COLor` | `:CURSor:MANual:Y2:COLor?` | see p.79 | documented; TOC/body-heading derived, parameters not transcribed | 79 |
| `:CURSor:MANual:Y2:DFOLlow` | `:CURSor:MANual:Y2:DFOLlow?` | see p.79 | documented; TOC/body-heading derived, parameters not transcribed | 79 |
| `:CURSor:MANual:Y2:DTCursor` | `:CURSor:MANual:Y2:DTCursor?` | see p.80 | documented; TOC/body-heading derived, parameters not transcribed | 80 |
| `:CURSor:MANual:Y2:DVALue` | `:CURSor:MANual:Y2:DVALue?` | see p.80 | documented; TOC/body-heading derived, parameters not transcribed | 80 |
| `:CURSor:MANual:Y2:LABel` | `:CURSor:MANual:Y2:LABel?` | see p.81 | documented; TOC/body-heading derived, parameters not transcribed | 81 |
| `:CURSor:MANual:Y2:POSition` | `:CURSor:MANual:Y2:POSition?` | see p.81 | documented; TOC/body-heading derived, parameters not transcribed | 81 |
| `:CURSor:MANual:Y2:SOURce` | `:CURSor:MANual:Y2:SOURce?` | see p.82 | documented; TOC/body-heading derived, parameters not transcribed | 82 |
| `:CURSor:MANual:Y<n>` | `:CURSor:MANual:Y<n>?` | see p.78 | documented; TOC/body-heading derived, parameters not transcribed | 78 |
| `:CURSor:MANual:Y<n>:COLor` | `:CURSor:MANual:Y<n>:COLor?` | see p.78 | documented; TOC/body-heading derived, parameters not transcribed | 78 |
| `:CURSor:MANual:Y<n>:DFOLlow` | `:CURSor:MANual:Y<n>:DFOLlow?` | see p.79 | documented; TOC/body-heading derived, parameters not transcribed | 79 |
| `:CURSor:MANual:Y<n>:DTCursor` | `:CURSor:MANual:Y<n>:DTCursor?` | see p.79 | documented; TOC/body-heading derived, parameters not transcribed | 79 |
| `:CURSor:MANual:Y<n>:DVALue` | `:CURSor:MANual:Y<n>:DVALue?` | see p.80 | documented; TOC/body-heading derived, parameters not transcribed | 80 |
| `:CURSor:MANual:Y<n>:LABel` | `:CURSor:MANual:Y<n>:LABel?` | see p.80 | documented; TOC/body-heading derived, parameters not transcribed | 80 |
| `:CURSor:MANual:Y<n>:POSition` | `:CURSor:MANual:Y<n>:POSition?` | see p.81 | documented; TOC/body-heading derived, parameters not transcribed | 81 |
| `:CURSor:MANual:Y<n>:SOURce` | `:CURSor:MANual:Y<n>:SOURce?` | see p.81 | documented; TOC/body-heading derived, parameters not transcribed | 81 |
| `:CURSor:MEASure2` | `:CURSor:MEASure2?` | see p.82 | documented; TOC/body-heading derived, parameters not transcribed | 82 |
| `:CURSor:MEASure2:COLor` | `:CURSor:MEASure2:COLor?` | see p.83 | documented; TOC/body-heading derived, parameters not transcribed | 83 |
| `:CURSor:MEASure2:LABel` | `:CURSor:MEASure2:LABel?` | see p.83 | documented; TOC/body-heading derived, parameters not transcribed | 83 |
| `:CURSor:MEASure2:MITem` | `:CURSor:MEASure2:MITem?` | see p.84 | documented; TOC/body-heading derived, parameters not transcribed | 84 |
| `:CURSor:MEASure<n>` | `:CURSor:MEASure<n>?` | see p.82 | documented; TOC/body-heading derived, parameters not transcribed | 82 |
| `:CURSor:MEASure<n>:COLor` | `:CURSor:MEASure<n>:COLor?` | see p.82 | documented; TOC/body-heading derived, parameters not transcribed | 82 |
| `:CURSor:MEASure<n>:LABel` | `:CURSor:MEASure<n>:LABel?` | see p.83 | documented; TOC/body-heading derived, parameters not transcribed | 83 |
| `:CURSor:MEASure<n>:MITem` | `:CURSor:MEASure<n>:MITem?` | see p.84 | documented; TOC/body-heading derived, parameters not transcribed | 84 |
| `:CURSor:MITem` | `:CURSor:MITem?` | see p.68 | documented; TOC/body-heading derived, parameters not transcribed | 68 |
| `:CURSor:TAGStyle` | `:CURSor:TAGStyle?` | see p.66 | documented; TOC/body-heading derived, parameters not transcribed | 66 |
| `:CURSor:TRAC2:DTCursor` | `:CURSor:TRAC2:DTCursor?` | see p.86 | documented; TOC/body-heading derived, parameters not transcribed | 86 |
| `:CURSor:TRACk2` | `:CURSor:TRACk2?` | see p.84 | documented; TOC/body-heading derived, parameters not transcribed | 84 |
| `:CURSor:TRACk2:COLor` | `:CURSor:TRACk2:COLor?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk2:DFOLlow` | `:CURSor:TRACk2:DFOLlow?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk2:DVALue` | `:CURSor:TRACk2:DVALue?` | see p.86 | documented; TOC/body-heading derived, parameters not transcribed | 86 |
| `:CURSor:TRACk2:LABel` | `:CURSor:TRACk2:LABel?` | see p.87 | documented; TOC/body-heading derived, parameters not transcribed | 87 |
| `:CURSor:TRACk2:POSition` | `:CURSor:TRACk2:POSition?` | see p.88 | documented; TOC/body-heading derived, parameters not transcribed | 88 |
| `:CURSor:TRACk2:SOURce` | `:CURSor:TRACk2:SOURce?` | see p.88 | documented; TOC/body-heading derived, parameters not transcribed | 88 |
| `:CURSor:TRACk<n>` | `:CURSor:TRACk<n>?` | see p.76 | documented; TOC/body-heading derived, parameters not transcribed | 76 |
| `:CURSor:TRACk<n>:COLor` | `:CURSor:TRACk<n>:COLor?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk<n>:DFOLlow` | `:CURSor:TRACk<n>:DFOLlow?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk<n>:DTCursor` | `:CURSor:TRACk<n>:DTCursor?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk<n>:DVALue` | `:CURSor:TRACk<n>:DVALue?` | see p.86 | documented; TOC/body-heading derived, parameters not transcribed | 86 |
| `:CURSor:TRACk<n>:LABel` | `:CURSor:TRACk<n>:LABel?` | see p.87 | documented; TOC/body-heading derived, parameters not transcribed | 87 |
| `:CURSor:TRACk<n>:POSition` | `:CURSor:TRACk<n>:POSition?` | see p.87 | documented; TOC/body-heading derived, parameters not transcribed | 87 |
| `:CURSor:TRACk<n>:SOURce` | `:CURSor:TRACk<n>:SOURce?` | see p.85 | documented; TOC/body-heading derived, parameters not transcribed | 85 |
| `:CURSor:TRACk<n>:VALue` | `:CURSor:TRACk<n>:VALue?` | see p.88 | documented; TOC/body-heading derived, parameters not transcribed | 88 |
| `:CURSor:XDELta` | `:CURSor:XDELta?` | see p.68 | documented; TOC/body-heading derived, parameters not transcribed | 68 |
| `:CURSor:XREFerence` | `:CURSor:XREFerence?` | see p.67 | documented; TOC/body-heading derived, parameters not transcribed | 67 |
| `:CURSor:XY:X2` | `:CURSor:XY:X2?` | see p.89 | documented; TOC/body-heading derived, parameters not transcribed | 89 |
| `:CURSor:XY:X2:COLor` | `:CURSor:XY:X2:COLor?` | see p.89 | documented; TOC/body-heading derived, parameters not transcribed | 89 |
| `:CURSor:XY:X2:DFOLlow` | `:CURSor:XY:X2:DFOLlow?` | see p.90 | documented; TOC/body-heading derived, parameters not transcribed | 90 |
| `:CURSor:XY:X2:DTCursor` | `:CURSor:XY:X2:DTCursor?` | see p.90 | documented; TOC/body-heading derived, parameters not transcribed | 90 |
| `:CURSor:XY:X2:DVALue` | `:CURSor:XY:X2:DVALue?` | see p.91 | documented; TOC/body-heading derived, parameters not transcribed | 91 |
| `:CURSor:XY:X2:LABel` | `:CURSor:XY:X2:LABel?` | see p.92 | documented; TOC/body-heading derived, parameters not transcribed | 92 |
| `:CURSor:XY:X2:POSition` | `:CURSor:XY:X2:POSition?` | see p.92 | documented; TOC/body-heading derived, parameters not transcribed | 92 |
| `:CURSor:XY:X<n>` | `:CURSor:XY:X<n>?` | see p.89 | documented; TOC/body-heading derived, parameters not transcribed | 89 |
| `:CURSor:XY:X<n>:COLor` | `:CURSor:XY:X<n>:COLor?` | see p.89 | documented; TOC/body-heading derived, parameters not transcribed | 89 |
| `:CURSor:XY:X<n>:DFOLlow` | `:CURSor:XY:X<n>:DFOLlow?` | see p.90 | documented; TOC/body-heading derived, parameters not transcribed | 90 |
| `:CURSor:XY:X<n>:DTCursor` | `:CURSor:XY:X<n>:DTCursor?` | see p.90 | documented; TOC/body-heading derived, parameters not transcribed | 90 |
| `:CURSor:XY:X<n>:DVALue` | `:CURSor:XY:X<n>:DVALue?` | see p.91 | documented; TOC/body-heading derived, parameters not transcribed | 91 |
| `:CURSor:XY:X<n>:LABel` | `:CURSor:XY:X<n>:LABel?` | see p.91 | documented; TOC/body-heading derived, parameters not transcribed | 91 |
| `:CURSor:XY:X<n>:POSition` | `:CURSor:XY:X<n>:POSition?` | see p.92 | documented; TOC/body-heading derived, parameters not transcribed | 92 |
| `:CURSor:XY:Y2` | `:CURSor:XY:Y2?` | see p.93 | documented; TOC/body-heading derived, parameters not transcribed | 93 |
| `:CURSor:XY:Y2:COLor` | `:CURSor:XY:Y2:COLor?` | see p.93 | documented; TOC/body-heading derived, parameters not transcribed | 93 |
| `:CURSor:XY:Y2:DFOLlow` | `:CURSor:XY:Y2:DFOLlow?` | see p.94 | documented; TOC/body-heading derived, parameters not transcribed | 94 |
| `:CURSor:XY:Y2:DTCursor` | `:CURSor:XY:Y2:DTCursor?` | see p.94 | documented; TOC/body-heading derived, parameters not transcribed | 94 |
| `:CURSor:XY:Y2:DVALue` | `:CURSor:XY:Y2:DVALue?` | see p.95 | documented; TOC/body-heading derived, parameters not transcribed | 95 |
| `:CURSor:XY:Y2:LABel` | `:CURSor:XY:Y2:LABel?` | see p.95 | documented; TOC/body-heading derived, parameters not transcribed | 95 |
| `:CURSor:XY:Y2:POSition` | `:CURSor:XY:Y2:POSition?` | see p.96 | documented; TOC/body-heading derived, parameters not transcribed | 96 |
| `:CURSor:XY:Y<n>` | `:CURSor:XY:Y<n>?` | see p.92 | documented; TOC/body-heading derived, parameters not transcribed | 92 |
| `:CURSor:XY:Y<n>:COLor` | `:CURSor:XY:Y<n>:COLor?` | see p.93 | documented; TOC/body-heading derived, parameters not transcribed | 93 |
| `:CURSor:XY:Y<n>:DFOLlow` | `:CURSor:XY:Y<n>:DFOLlow?` | see p.93 | documented; TOC/body-heading derived, parameters not transcribed | 93 |
| `:CURSor:XY:Y<n>:DTCursor` | `:CURSor:XY:Y<n>:DTCursor?` | see p.93 | documented; TOC/body-heading derived, parameters not transcribed | 93 |
| `:CURSor:XY:Y<n>:DVALue` | `:CURSor:XY:Y<n>:DVALue?` | see p.94 | documented; TOC/body-heading derived, parameters not transcribed | 94 |
| `:CURSor:XY:Y<n>:LABel` | `:CURSor:XY:Y<n>:LABel?` | see p.95 | documented; TOC/body-heading derived, parameters not transcribed | 95 |
| `:CURSor:XY:Y<n>:POSition` | `:CURSor:XY:Y<n>:POSition?` | see p.95 | documented; TOC/body-heading derived, parameters not transcribed | 95 |
| `:CURSor:YDELta` | `:CURSor:YDELta?` | see p.72 | documented; TOC/body-heading derived, parameters not transcribed | 72 |
| `:CURSor:YREFerence` | `:CURSor:YREFerence?` | see p.67 | documented; TOC/body-heading derived, parameters not transcribed | 67 |
| `:DECode:BUS1` | `:DECode:BUS1?` | see p.98 | documented; TOC/body-heading derived, parameters not transcribed | 98 |
| `:DECode:BUS1:CAN:BAUD` | `:DECode:BUS1:CAN:BAUD?` | see p.119 | documented; TOC/body-heading derived, parameters not transcribed | 119 |
| `:DECode:BUS1:CAN:SOURce` | `:DECode:BUS1:CAN:SOURce?` | see p.119 | documented; TOC/body-heading derived, parameters not transcribed | 119 |
| `:DECode:BUS1:CAN:THReshold` | `:DECode:BUS1:CAN:THReshold?` | see p.120 | documented; TOC/body-heading derived, parameters not transcribed | 120 |
| `:DECode:BUS1:CANFd:BAUDData` | `:DECode:BUS1:CANFd:BAUDData?` | see p.125 | documented; TOC/body-heading derived, parameters not transcribed | 125 |
| `:DECode:BUS1:CANFd:BAUDNominal` | `:DECode:BUS1:CANFd:BAUDNominal?` | see p.125 | documented; TOC/body-heading derived, parameters not transcribed | 125 |
| `:DECode:BUS1:CANFd:SOURce` | `:DECode:BUS1:CANFd:SOURce?` | see p.126 | documented; TOC/body-heading derived, parameters not transcribed | 126 |
| `:DECode:BUS1:CANFd:THReshold` | `:DECode:BUS1:CANFd:THReshold?` | see p.127 | documented; TOC/body-heading derived, parameters not transcribed | 127 |
| `:DECode:BUS1:COPY` | `:DECode:BUS1:COPY?` | see p.99 | documented; TOC/body-heading derived, parameters not transcribed | 99 |
| `:DECode:BUS1:FLEXray:BAUD` | `:DECode:BUS1:FLEXray:BAUD?` | see p.123 | documented; TOC/body-heading derived, parameters not transcribed | 123 |
| `:DECode:BUS1:FLEXray:SOURce` | `:DECode:BUS1:FLEXray:SOURce?` | see p.123 | documented; TOC/body-heading derived, parameters not transcribed | 123 |
| `:DECode:BUS1:FLEXray:THReshold` | `:DECode:BUS1:FLEXray:THReshold?` | see p.124 | documented; TOC/body-heading derived, parameters not transcribed | 124 |
| `:DECode:BUS1:FORMat` | `:DECode:BUS1:FORMat?` | see p.99 | documented; TOC/body-heading derived, parameters not transcribed | 99 |
| `:DECode:BUS1:IIC:RWBit` | `:DECode:BUS1:IIC:RWBit?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS1:IIC:SCLSource` | `:DECode:BUS1:IIC:SCLSource?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS1:IIC:SCLThreshold` | `:DECode:BUS1:IIC:SCLThreshold?` | see p.102 | documented; TOC/body-heading derived, parameters not transcribed | 102 |
| `:DECode:BUS1:IIC:SDASource` | `:DECode:BUS1:IIC:SDASource?` | see p.103 | documented; TOC/body-heading derived, parameters not transcribed | 103 |
| `:DECode:BUS1:IIC:SDAThreshold` | `:DECode:BUS1:IIC:SDAThreshold?` | see p.103 | documented; TOC/body-heading derived, parameters not transcribed | 103 |
| `:DECode:BUS1:IIS:ANNotate` | `:DECode:BUS1:IIS:ANNotate?` | see p.128 | documented; TOC/body-heading derived, parameters not transcribed | 128 |
| `:DECode:BUS1:IIS:AVARiant` | `:DECode:BUS1:IIS:AVARiant?` | see p.128 | documented; TOC/body-heading derived, parameters not transcribed | 128 |
| `:DECode:BUS1:IIS:BCLKSource` | `:DECode:BUS1:IIS:BCLKSource?` | see p.129 | documented; TOC/body-heading derived, parameters not transcribed | 129 |
| `:DECode:BUS1:IIS:BCLKThreshold` | `:DECode:BUS1:IIS:BCLKThreshold?` | see p.130 | documented; TOC/body-heading derived, parameters not transcribed | 130 |
| `:DECode:BUS1:IIS:BITorder` | `:DECode:BUS1:IIS:BITorder?` | see p.130 | documented; TOC/body-heading derived, parameters not transcribed | 130 |
| `:DECode:BUS1:IIS:DLENgth` | `:DECode:BUS1:IIS:DLENgth?` | see p.130 | documented; TOC/body-heading derived, parameters not transcribed | 130 |
| `:DECode:BUS1:IIS:DSource` | `:DECode:BUS1:IIS:DSource?` | see p.131 | documented; TOC/body-heading derived, parameters not transcribed | 131 |
| `:DECode:BUS1:IIS:DTHReshold` | `:DECode:BUS1:IIS:DTHReshold?` | see p.132 | documented; TOC/body-heading derived, parameters not transcribed | 132 |
| `:DECode:BUS1:IIS:LATChedge` | `:DECode:BUS1:IIS:LATChedge?` | see p.132 | documented; TOC/body-heading derived, parameters not transcribed | 132 |
| `:DECode:BUS1:IIS:LCH` | `:DECode:BUS1:IIS:LCH?` | see p.133 | documented; TOC/body-heading derived, parameters not transcribed | 133 |
| `:DECode:BUS1:IIS:SBIT` | `:DECode:BUS1:IIS:SBIT?` | see p.133 | documented; TOC/body-heading derived, parameters not transcribed | 133 |
| `:DECode:BUS1:IIS:WSSource` | `:DECode:BUS1:IIS:WSSource?` | see p.134 | documented; TOC/body-heading derived, parameters not transcribed | 134 |
| `:DECode:BUS1:IIS:WSTHreshold` | `:DECode:BUS1:IIS:WSTHreshold?` | see p.134 | documented; TOC/body-heading derived, parameters not transcribed | 134 |
| `:DECode:BUS1:LIN:BAUD` | `:DECode:BUS1:LIN:BAUD?` | see p.121 | documented; TOC/body-heading derived, parameters not transcribed | 121 |
| `:DECode:BUS1:LIN:SOURce` | `:DECode:BUS1:LIN:SOURce?` | see p.121 | documented; TOC/body-heading derived, parameters not transcribed | 121 |
| `:DECode:BUS1:LIN:THReshold` | `:DECode:BUS1:LIN:THReshold?` | see p.122 | documented; TOC/body-heading derived, parameters not transcribed | 122 |
| `:DECode:BUS1:M1553:LTHReshold` | `:DECode:BUS1:M1553:LTHReshold?` | see p.135 | documented; TOC/body-heading derived, parameters not transcribed | 135 |
| `:DECode:BUS1:M1553:SOURce` | `:DECode:BUS1:M1553:SOURce?` | see p.136 | documented; TOC/body-heading derived, parameters not transcribed | 136 |
| `:DECode:BUS1:M1553:UTHReshold` | `:DECode:BUS1:M1553:UTHReshold?` | see p.136 | documented; TOC/body-heading derived, parameters not transcribed | 136 |
| `:DECode:BUS1:MANChester:BAUD` | `:DECode:BUS1:MANChester:BAUD?` | see p.143 | documented; TOC/body-heading derived, parameters not transcribed | 143 |
| `:DECode:BUS1:MANChester:BITorder` | `:DECode:BUS1:MANChester:BITorder?` | see p.148 | documented; TOC/body-heading derived, parameters not transcribed | 148 |
| `:DECode:BUS1:MANChester:DISPlay` | `:DECode:BUS1:MANChester:DISPlay?` | see p.147 | documented; TOC/body-heading derived, parameters not transcribed | 147 |
| `:DECode:BUS1:MANChester:DSIZe` | `:DECode:BUS1:MANChester:DSIZe?` | see p.147 | documented; TOC/body-heading derived, parameters not transcribed | 147 |
| `:DECode:BUS1:MANChester:HSIZe` | `:DECode:BUS1:MANChester:HSIZe?` | see p.146 | documented; TOC/body-heading derived, parameters not transcribed | 146 |
| `:DECode:BUS1:MANChester:IBITs` | `:DECode:BUS1:MANChester:IBITs?` | see p.144 | documented; TOC/body-heading derived, parameters not transcribed | 144 |
| `:DECode:BUS1:MANChester:IDLE` | `:DECode:BUS1:MANChester:IDLE?` | see p.144 | documented; TOC/body-heading derived, parameters not transcribed | 144 |
| `:DECode:BUS1:MANChester:POLarity` | `:DECode:BUS1:MANChester:POLarity?` | see p.143 | documented; TOC/body-heading derived, parameters not transcribed | 143 |
| `:DECode:BUS1:MANChester:SOURce` | `:DECode:BUS1:MANChester:SOURce?` | see p.142 | documented; TOC/body-heading derived, parameters not transcribed | 142 |
| `:DECode:BUS1:MANChester:SSIZe` | `:DECode:BUS1:MANChester:SSIZe?` | see p.145 | documented; TOC/body-heading derived, parameters not transcribed | 145 |
| `:DECode:BUS1:MANChester:STARt` | `:DECode:BUS1:MANChester:STARt?` | see p.145 | documented; TOC/body-heading derived, parameters not transcribed | 145 |
| `:DECode:BUS1:MANChester:THReshold` | `:DECode:BUS1:MANChester:THReshold?` | see p.143 | documented; TOC/body-heading derived, parameters not transcribed | 143 |
| `:DECode:BUS1:MANChester:TSIZe` | `:DECode:BUS1:MANChester:TSIZe?` | see p.146 | documented; TOC/body-heading derived, parameters not transcribed | 146 |
| `:DECode:BUS1:MANChester:WSIZe` | `:DECode:BUS1:MANChester:WSIZe?` | see p.147 | documented; TOC/body-heading derived, parameters not transcribed | 147 |
| `:DECode:BUS1:PROTocol` | `:DECode:BUS1:PROTocol?` | see p.100 | documented; TOC/body-heading derived, parameters not transcribed | 100 |
| `:DECode:BUS1:SENT:CLOCk` | `:DECode:BUS1:SENT:CLOCk?` | see p.138 | documented; TOC/body-heading derived, parameters not transcribed | 138 |
| `:DECode:BUS1:SENT:CRC` | `:DECode:BUS1:SENT:CRC?` | see p.140 | documented; TOC/body-heading derived, parameters not transcribed | 140 |
| `:DECode:BUS1:SENT:FORMat` | `:DECode:BUS1:SENT:FORMat?` | see p.138 | documented; TOC/body-heading derived, parameters not transcribed | 138 |
| `:DECode:BUS1:SENT:IDLE` | `:DECode:BUS1:SENT:IDLE?` | see p.139 | documented; TOC/body-heading derived, parameters not transcribed | 139 |
| `:DECode:BUS1:SENT:LENGth` | `:DECode:BUS1:SENT:LENGth?` | see p.140 | documented; TOC/body-heading derived, parameters not transcribed | 140 |
| `:DECode:BUS1:SENT:PPULse` | `:DECode:BUS1:SENT:PPULse?` | see p.141 | documented; TOC/body-heading derived, parameters not transcribed | 141 |
| `:DECode:BUS1:SENT:SOURce` | `:DECode:BUS1:SENT:SOURce?` | see p.137 | documented; TOC/body-heading derived, parameters not transcribed | 137 |
| `:DECode:BUS1:SENT:THReshold` | `:DECode:BUS1:SENT:THReshold?` | see p.138 | documented; TOC/body-heading derived, parameters not transcribed | 138 |
| `:DECode:BUS1:SENT:TOLerance` | `:DECode:BUS1:SENT:TOLerance?` | see p.139 | documented; TOC/body-heading derived, parameters not transcribed | 139 |
| `:DECode:BUS1:SPI:BITorder` | `:DECode:BUS1:SPI:BITorder?` | see p.104 | documented; TOC/body-heading derived, parameters not transcribed | 104 |
| `:DECode:BUS1:SPI:CLKSource` | `:DECode:BUS1:SPI:CLKSource?` | see p.104 | documented; TOC/body-heading derived, parameters not transcribed | 104 |
| `:DECode:BUS1:SPI:CLKThreshold` | `:DECode:BUS1:SPI:CLKThreshold?` | see p.105 | documented; TOC/body-heading derived, parameters not transcribed | 105 |
| `:DECode:BUS1:SPI:CSSource` | `:DECode:BUS1:SPI:CSSource?` | see p.106 | documented; TOC/body-heading derived, parameters not transcribed | 106 |
| `:DECode:BUS1:SPI:CSTYpe` | `:DECode:BUS1:SPI:CSTYpe?` | see p.107 | documented; TOC/body-heading derived, parameters not transcribed | 107 |
| `:DECode:BUS1:SPI:CSThreshold` | `:DECode:BUS1:SPI:CSThreshold?` | see p.106 | documented; TOC/body-heading derived, parameters not transcribed | 106 |
| `:DECode:BUS1:SPI:DLENgth` | `:DECode:BUS1:SPI:DLENgth?` | see p.107 | documented; TOC/body-heading derived, parameters not transcribed | 107 |
| `:DECode:BUS1:SPI:LATChedge` | `:DECode:BUS1:SPI:LATChedge?` | see p.108 | documented; TOC/body-heading derived, parameters not transcribed | 108 |
| `:DECode:BUS1:SPI:MISOSource` | `:DECode:BUS1:SPI:MISOSource?` | see p.108 | documented; TOC/body-heading derived, parameters not transcribed | 108 |
| `:DECode:BUS1:SPI:MISOThreshold` | `:DECode:BUS1:SPI:MISOThreshold?` | see p.109 | documented; TOC/body-heading derived, parameters not transcribed | 109 |
| `:DECode:BUS1:SPI:MOSISource` | `:DECode:BUS1:SPI:MOSISource?` | see p.110 | documented; TOC/body-heading derived, parameters not transcribed | 110 |
| `:DECode:BUS1:SPI:MOSIThreshold` | `:DECode:BUS1:SPI:MOSIThreshold?` | see p.110 | documented; TOC/body-heading derived, parameters not transcribed | 110 |
| `:DECode:BUS1:SPI:NCSSource` | `:DECode:BUS1:SPI:NCSSource?` | see p.111 | documented; TOC/body-heading derived, parameters not transcribed | 111 |
| `:DECode:BUS1:SPI:NCSThreshold` | `:DECode:BUS1:SPI:NCSThreshold?` | see p.112 | documented; TOC/body-heading derived, parameters not transcribed | 112 |
| `:DECode:BUS1:UART:BAUD` | `:DECode:BUS1:UART:BAUD?` | see p.113 | documented; TOC/body-heading derived, parameters not transcribed | 113 |
| `:DECode:BUS1:UART:BITorder` | `:DECode:BUS1:UART:BITorder?` | see p.113 | documented; TOC/body-heading derived, parameters not transcribed | 113 |
| `:DECode:BUS1:UART:DLENgth` | `:DECode:BUS1:UART:DLENgth?` | see p.114 | documented; TOC/body-heading derived, parameters not transcribed | 114 |
| `:DECode:BUS1:UART:IDLE` | `:DECode:BUS1:UART:IDLE?` | see p.114 | documented; TOC/body-heading derived, parameters not transcribed | 114 |
| `:DECode:BUS1:UART:PARity` | `:DECode:BUS1:UART:PARity?` | see p.115 | documented; TOC/body-heading derived, parameters not transcribed | 115 |
| `:DECode:BUS1:UART:RXSource` | `:DECode:BUS1:UART:RXSource?` | see p.115 | documented; TOC/body-heading derived, parameters not transcribed | 115 |
| `:DECode:BUS1:UART:RXTHreshold` | `:DECode:BUS1:UART:RXTHreshold?` | see p.116 | documented; TOC/body-heading derived, parameters not transcribed | 116 |
| `:DECode:BUS1:UART:STOP` | `:DECode:BUS1:UART:STOP?` | see p.117 | documented; TOC/body-heading derived, parameters not transcribed | 117 |
| `:DECode:BUS1:UART:TXSource` | `:DECode:BUS1:UART:TXSource?` | see p.117 | documented; TOC/body-heading derived, parameters not transcribed | 117 |
| `:DECode:BUS1:UART:TXTHreshold` | `:DECode:BUS1:UART:TXTHreshold?` | see p.118 | documented; TOC/body-heading derived, parameters not transcribed | 118 |
| `:DECode:BUS<n>` | `:DECode:BUS<n>?` | see p.98 | documented; TOC/body-heading derived, parameters not transcribed | 98 |
| `:DECode:BUS<n>:CAN` | `:DECode:BUS<n>:CAN?` | see p.119 | documented; TOC/body-heading derived, parameters not transcribed | 119 |
| `:DECode:BUS<n>:CAN:BAUD` | `:DECode:BUS<n>:CAN:BAUD?` | see p.119 | documented; TOC/body-heading derived, parameters not transcribed | 119 |
| `:DECode:BUS<n>:CAN:SOURce` | `:DECode:BUS<n>:CAN:SOURce?` | see p.119 | documented; TOC/body-heading derived, parameters not transcribed | 119 |
| `:DECode:BUS<n>:CAN:THReshold` | `:DECode:BUS<n>:CAN:THReshold?` | see p.120 | documented; TOC/body-heading derived, parameters not transcribed | 120 |
| `:DECode:BUS<n>:CANFd` | `:DECode:BUS<n>:CANFd?` | see p.125 | documented; TOC/body-heading derived, parameters not transcribed | 125 |
| `:DECode:BUS<n>:CANFd:BAUDData` | `:DECode:BUS<n>:CANFd:BAUDData?` | see p.125 | documented; TOC/body-heading derived, parameters not transcribed | 125 |
| `:DECode:BUS<n>:CANFd:BAUDNominal` | `:DECode:BUS<n>:CANFd:BAUDNominal?` | see p.125 | documented; TOC/body-heading derived, parameters not transcribed | 125 |
| `:DECode:BUS<n>:CANFd:SOURce` | `:DECode:BUS<n>:CANFd:SOURce?` | see p.126 | documented; TOC/body-heading derived, parameters not transcribed | 126 |
| `:DECode:BUS<n>:CANFd:THReshold` | `:DECode:BUS<n>:CANFd:THReshold?` | see p.126 | documented; TOC/body-heading derived, parameters not transcribed | 126 |
| `:DECode:BUS<n>:COPY` | `:DECode:BUS<n>:COPY?` | see p.99 | documented; TOC/body-heading derived, parameters not transcribed | 99 |
| `:DECode:BUS<n>:FLEXray` | `:DECode:BUS<n>:FLEXray?` | see p.123 | documented; TOC/body-heading derived, parameters not transcribed | 123 |
| `:DECode:BUS<n>:FLEXray:BAUD` | `:DECode:BUS<n>:FLEXray:BAUD?` | see p.123 | documented; TOC/body-heading derived, parameters not transcribed | 123 |
| `:DECode:BUS<n>:FLEXray:SOURce` | `:DECode:BUS<n>:FLEXray:SOURce?` | see p.123 | documented; TOC/body-heading derived, parameters not transcribed | 123 |
| `:DECode:BUS<n>:FLEXray:THReshold` | `:DECode:BUS<n>:FLEXray:THReshold?` | see p.124 | documented; TOC/body-heading derived, parameters not transcribed | 124 |
| `:DECode:BUS<n>:FORMat` | `:DECode:BUS<n>:FORMat?` | see p.99 | documented; TOC/body-heading derived, parameters not transcribed | 99 |
| `:DECode:BUS<n>:IIC` | `:DECode:BUS<n>:IIC?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS<n>:IIC:RWBit` | `:DECode:BUS<n>:IIC:RWBit?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS<n>:IIC:SCLSource` | `:DECode:BUS<n>:IIC:SCLSource?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS<n>:IIC:SCLThreshold` | `:DECode:BUS<n>:IIC:SCLThreshold?` | see p.102 | documented; TOC/body-heading derived, parameters not transcribed | 102 |
| `:DECode:BUS<n>:IIC:SDASource` | `:DECode:BUS<n>:IIC:SDASource?` | see p.101 | documented; TOC/body-heading derived, parameters not transcribed | 101 |
| `:DECode:BUS<n>:IIC:SDAThreshold` | `:DECode:BUS<n>:IIC:SDAThreshold?` | see p.103 | documented; TOC/body-heading derived, parameters not transcribed | 103 |
| `:DECode:BUS<n>:IIS` | `:DECode:BUS<n>:IIS?` | see p.128 | documented; TOC/body-heading derived, parameters not transcribed | 128 |
| `:DECode:BUS<n>:IIS:ANNotate` | `:DECode:BUS<n>:IIS:ANNotate?` | see p.128 | documented; TOC/body-heading derived, parameters not transcribed | 128 |
| `:DECode:BUS<n>:IIS:AVARiant` | `:DECode:BUS<n>:IIS:AVARiant?` | see p.128 | documented; TOC/body-heading derived, parameters not transcribed | 128 |
| `:DECode:BUS<n>:IIS:BCLKSource` | `:DECode:BUS<n>:IIS:BCLKSource?` | see p.129 | documented; TOC/body-heading derived, parameters not transcribed | 129 |
| `:DECode:BUS<n>:IIS:BCLKThreshold` | `:DECode:BUS<n>:IIS:BCLKThreshold?` | see p.129 | documented; TOC/body-heading derived, parameters not transcribed | 129 |
| `:DECode:BUS<n>:IIS:BITorder` | `:DECode:BUS<n>:IIS:BITorder?` | see p.130 | documented; TOC/body-heading derived, parameters not transcribed | 130 |
| `:DECode:BUS<n>:IIS:DLENgth` | `:DECode:BUS<n>:IIS:DLENgth?` | see p.130 | documented; TOC/body-heading derived, parameters not transcribed | 130 |
| `:DECode:BUS<n>:IIS:DSource` | `:DECode:BUS<n>:IIS:DSource?` | see p.131 | documented; TOC/body-heading derived, parameters not transcribed | 131 |
| `:DECode:BUS<n>:IIS:DTHReshold` | `:DECode:BUS<n>:IIS:DTHReshold?` | see p.131 | documented; TOC/body-heading derived, parameters not transcribed | 131 |
| `:DECode:BUS<n>:IIS:LATChedge` | `:DECode:BUS<n>:IIS:LATChedge?` | see p.132 | documented; TOC/body-heading derived, parameters not transcribed | 132 |
| `:DECode:BUS<n>:IIS:LCH` | `:DECode:BUS<n>:IIS:LCH?` | see p.132 | documented; TOC/body-heading derived, parameters not transcribed | 132 |
| `:DECode:BUS<n>:IIS:SBIT` | `:DECode:BUS<n>:IIS:SBIT?` | see p.133 | documented; TOC/body-heading derived, parameters not transcribed | 133 |
| `:DECode:BUS<n>:IIS:WSSource` | `:DECode:BUS<n>:IIS:WSSource?` | see p.133 | documented; TOC/body-heading derived, parameters not transcribed | 133 |
| `:DECode:BUS<n>:IIS:WSTHreshold` | `:DECode:BUS<n>:IIS:WSTHreshold?` | see p.134 | documented; TOC/body-heading derived, parameters not transcribed | 134 |
| `:DECode:BUS<n>:LIN` | `:DECode:BUS<n>:LIN?` | see p.121 | documented; TOC/body-heading derived, parameters not transcribed | 121 |
| `:DECode:BUS<n>:LIN:BAUD` | `:DECode:BUS<n>:LIN:BAUD?` | see p.121 | documented; TOC/body-heading derived, parameters not transcribed | 121 |
| `:DECode:BUS<n>:LIN:SOURce` | `:DECode:BUS<n>:LIN:SOURce?` | see p.121 | documented; TOC/body-heading derived, parameters not transcribed | 121 |
| `:DECode:BUS<n>:LIN:THReshold` | `:DECode:BUS<n>:LIN:THReshold?` | see p.122 | documented; TOC/body-heading derived, parameters not transcribed | 122 |
| `:DECode:BUS<n>:M1553` | `:DECode:BUS<n>:M1553?` | see p.135 | documented; TOC/body-heading derived, parameters not transcribed | 135 |
| `:DECode:BUS<n>:M1553:LTHReshold` | `:DECode:BUS<n>:M1553:LTHReshold?` | see p.135 | documented; TOC/body-heading derived, parameters not transcribed | 135 |
| `:DECode:BUS<n>:M1553:SOURce` | `:DECode:BUS<n>:M1553:SOURce?` | see p.135 | documented; TOC/body-heading derived, parameters not transcribed | 135 |
| `:DECode:BUS<n>:M1553:UTHReshold` | `:DECode:BUS<n>:M1553:UTHReshold?` | see p.135 | documented; TOC/body-heading derived, parameters not transcribed | 135 |
| `:DECode:BUS<n>:MANChester` | `:DECode:BUS<n>:MANChester?` | see p.142 | documented; TOC/body-heading derived, parameters not transcribed | 142 |
| `:DECode:BUS<n>:MANChester:BAUD` | `:DECode:BUS<n>:MANChester:BAUD?` | see p.143 | documented; TOC/body-heading derived, parameters not transcribed | 143 |
| `:DECode:BUS<n>:MANChester:BITorder` | `:DECode:BUS<n>:MANChester:BITorder?` | see p.148 | documented; TOC/body-heading derived, parameters not transcribed | 148 |
| `:DECode:BUS<n>:MANChester:DISPlay` | `:DECode:BUS<n>:MANChester:DISPlay?` | see p.147 | documented; TOC/body-heading derived, parameters not transcribed | 147 |
| `:DECode:BUS<n>:MANChester:DSIZe` | `:DECode:BUS<n>:MANChester:DSIZe?` | see p.147 | documented; TOC/body-heading derived, parameters not transcribed | 147 |
| `:DECode:BUS<n>:MANChester:HSIZe` | `:DECode:BUS<n>:MANChester:HSIZe?` | see p.145 | documented; TOC/body-heading derived, parameters not transcribed | 145 |
| `:DECode:BUS<n>:MANChester:IBITs` | `:DECode:BUS<n>:MANChester:IBITs?` | see p.144 | documented; TOC/body-heading derived, parameters not transcribed | 144 |
| `:DECode:BUS<n>:MANChester:IDLE` | `:DECode:BUS<n>:MANChester:IDLE?` | see p.144 | documented; TOC/body-heading derived, parameters not transcribed | 144 |
| `:DECode:BUS<n>:MANChester:POLarity` | `:DECode:BUS<n>:MANChester:POLarity?` | see p.143 | documented; TOC/body-heading derived, parameters not transcribed | 143 |
| `:DECode:BUS<n>:MANChester:SOURce` | `:DECode:BUS<n>:MANChester:SOURce?` | see p.142 | documented; TOC/body-heading derived, parameters not transcribed | 142 |
| `:DECode:BUS<n>:MANChester:SSIZe` | `:DECode:BUS<n>:MANChester:SSIZe?` | see p.145 | documented; TOC/body-heading derived, parameters not transcribed | 145 |
| `:DECode:BUS<n>:MANChester:STARt` | `:DECode:BUS<n>:MANChester:STARt?` | see p.145 | documented; TOC/body-heading derived, parameters not transcribed | 145 |
| `:DECode:BUS<n>:MANChester:THReshold` | `:DECode:BUS<n>:MANChester:THReshold?` | see p.142 | documented; TOC/body-heading derived, parameters not transcribed | 142 |
| `:DECode:BUS<n>:MANChester:TSIZe` | `:DECode:BUS<n>:MANChester:TSIZe?` | see p.146 | documented; TOC/body-heading derived, parameters not transcribed | 146 |
| `:DECode:BUS<n>:MANChester:WSIZe` | `:DECode:BUS<n>:MANChester:WSIZe?` | see p.146 | documented; TOC/body-heading derived, parameters not transcribed | 146 |
| `:DECode:BUS<n>:PROTocol` | `:DECode:BUS<n>:PROTocol?` | see p.99 | documented; TOC/body-heading derived, parameters not transcribed | 99 |
| `:DECode:BUS<n>:RESult` | `:DECode:BUS<n>:RESult?` | see p.100 | documented; TOC/body-heading derived, parameters not transcribed | 100 |
| `:DECode:BUS<n>:SENT` | `:DECode:BUS<n>:SENT?` | see p.137 | documented; TOC/body-heading derived, parameters not transcribed | 137 |
| `:DECode:BUS<n>:SENT:CLOCk` | `:DECode:BUS<n>:SENT:CLOCk?` | see p.138 | documented; TOC/body-heading derived, parameters not transcribed | 138 |
| `:DECode:BUS<n>:SENT:CRC` | `:DECode:BUS<n>:SENT:CRC?` | see p.140 | documented; TOC/body-heading derived, parameters not transcribed | 140 |
| `:DECode:BUS<n>:SENT:FORMat` | `:DECode:BUS<n>:SENT:FORMat?` | see p.138 | documented; TOC/body-heading derived, parameters not transcribed | 138 |
| `:DECode:BUS<n>:SENT:IDLE` | `:DECode:BUS<n>:SENT:IDLE?` | see p.139 | documented; TOC/body-heading derived, parameters not transcribed | 139 |
| `:DECode:BUS<n>:SENT:LENGth` | `:DECode:BUS<n>:SENT:LENGth?` | see p.140 | documented; TOC/body-heading derived, parameters not transcribed | 140 |
| `:DECode:BUS<n>:SENT:PPULse` | `:DECode:BUS<n>:SENT:PPULse?` | see p.141 | documented; TOC/body-heading derived, parameters not transcribed | 141 |
| `:DECode:BUS<n>:SENT:SOURce` | `:DECode:BUS<n>:SENT:SOURce?` | see p.137 | documented; TOC/body-heading derived, parameters not transcribed | 137 |
| `:DECode:BUS<n>:SENT:THReshold` | `:DECode:BUS<n>:SENT:THReshold?` | see p.137 | documented; TOC/body-heading derived, parameters not transcribed | 137 |
| `:DECode:BUS<n>:SENT:TOLerance` | `:DECode:BUS<n>:SENT:TOLerance?` | see p.139 | documented; TOC/body-heading derived, parameters not transcribed | 139 |
| `:DECode:BUS<n>:SPI` | `:DECode:BUS<n>:SPI?` | see p.104 | documented; TOC/body-heading derived, parameters not transcribed | 104 |
| `:DECode:BUS<n>:SPI:BITorder` | `:DECode:BUS<n>:SPI:BITorder?` | see p.104 | documented; TOC/body-heading derived, parameters not transcribed | 104 |
| `:DECode:BUS<n>:SPI:CLKSource` | `:DECode:BUS<n>:SPI:CLKSource?` | see p.104 | documented; TOC/body-heading derived, parameters not transcribed | 104 |
| `:DECode:BUS<n>:SPI:CLKThreshold` | `:DECode:BUS<n>:SPI:CLKThreshold?` | see p.105 | documented; TOC/body-heading derived, parameters not transcribed | 105 |
| `:DECode:BUS<n>:SPI:CSSource` | `:DECode:BUS<n>:SPI:CSSource?` | see p.105 | documented; TOC/body-heading derived, parameters not transcribed | 105 |
| `:DECode:BUS<n>:SPI:CSTYpe` | `:DECode:BUS<n>:SPI:CSTYpe?` | see p.107 | documented; TOC/body-heading derived, parameters not transcribed | 107 |
| `:DECode:BUS<n>:SPI:CSThreshold` | `:DECode:BUS<n>:SPI:CSThreshold?` | see p.106 | documented; TOC/body-heading derived, parameters not transcribed | 106 |
| `:DECode:BUS<n>:SPI:DLENgth` | `:DECode:BUS<n>:SPI:DLENgth?` | see p.107 | documented; TOC/body-heading derived, parameters not transcribed | 107 |
| `:DECode:BUS<n>:SPI:LATChedge` | `:DECode:BUS<n>:SPI:LATChedge?` | see p.108 | documented; TOC/body-heading derived, parameters not transcribed | 108 |
| `:DECode:BUS<n>:SPI:MISOSource` | `:DECode:BUS<n>:SPI:MISOSource?` | see p.108 | documented; TOC/body-heading derived, parameters not transcribed | 108 |
| `:DECode:BUS<n>:SPI:MISOThreshold` | `:DECode:BUS<n>:SPI:MISOThreshold?` | see p.109 | documented; TOC/body-heading derived, parameters not transcribed | 109 |
| `:DECode:BUS<n>:SPI:MOSISource` | `:DECode:BUS<n>:SPI:MOSISource?` | see p.109 | documented; TOC/body-heading derived, parameters not transcribed | 109 |
| `:DECode:BUS<n>:SPI:MOSIThreshold` | `:DECode:BUS<n>:SPI:MOSIThreshold?` | see p.110 | documented; TOC/body-heading derived, parameters not transcribed | 110 |
| `:DECode:BUS<n>:SPI:NCSSource` | `:DECode:BUS<n>:SPI:NCSSource?` | see p.111 | documented; TOC/body-heading derived, parameters not transcribed | 111 |
| `:DECode:BUS<n>:SPI:NCSThreshold` | `:DECode:BUS<n>:SPI:NCSThreshold?` | see p.111 | documented; TOC/body-heading derived, parameters not transcribed | 111 |
| `:DECode:BUS<n>:UART` | `:DECode:BUS<n>:UART?` | see p.113 | documented; TOC/body-heading derived, parameters not transcribed | 113 |
| `:DECode:BUS<n>:UART:BAUD` | `:DECode:BUS<n>:UART:BAUD?` | see p.113 | documented; TOC/body-heading derived, parameters not transcribed | 113 |
| `:DECode:BUS<n>:UART:BITorder` | `:DECode:BUS<n>:UART:BITorder?` | see p.113 | documented; TOC/body-heading derived, parameters not transcribed | 113 |
| `:DECode:BUS<n>:UART:DLENgth` | `:DECode:BUS<n>:UART:DLENgth?` | see p.114 | documented; TOC/body-heading derived, parameters not transcribed | 114 |
| `:DECode:BUS<n>:UART:IDLE` | `:DECode:BUS<n>:UART:IDLE?` | see p.114 | documented; TOC/body-heading derived, parameters not transcribed | 114 |
| `:DECode:BUS<n>:UART:PARity` | `:DECode:BUS<n>:UART:PARity?` | see p.115 | documented; TOC/body-heading derived, parameters not transcribed | 115 |
| `:DECode:BUS<n>:UART:RXSource` | `:DECode:BUS<n>:UART:RXSource?` | see p.115 | documented; TOC/body-heading derived, parameters not transcribed | 115 |
| `:DECode:BUS<n>:UART:RXTHreshold` | `:DECode:BUS<n>:UART:RXTHreshold?` | see p.116 | documented; TOC/body-heading derived, parameters not transcribed | 116 |
| `:DECode:BUS<n>:UART:STOP` | `:DECode:BUS<n>:UART:STOP?` | see p.116 | documented; TOC/body-heading derived, parameters not transcribed | 116 |
| `:DECode:BUS<n>:UART:TXSource` | `:DECode:BUS<n>:UART:TXSource?` | see p.117 | documented; TOC/body-heading derived, parameters not transcribed | 117 |
| `:DECode:BUS<n>:UART:TXTHreshold` | `:DECode:BUS<n>:UART:TXTHreshold?` | see p.117 | documented; TOC/body-heading derived, parameters not transcribed | 117 |
| `:DECode:LIST` | `:DECode:LIST?` | see p.96 | documented; TOC/body-heading derived, parameters not transcribed | 96 |
| `:DECode:LIST:LINE` | `:DECode:LIST:LINE?` | see p.97 | documented; TOC/body-heading derived, parameters not transcribed | 97 |
| `:DECode:LIST:SCRoll` | `:DECode:LIST:SCRoll?` | see p.97 | documented; TOC/body-heading derived, parameters not transcribed | 97 |
| `:DECode:LIST<n>:RESult` | `:DECode:LIST<n>:RESult?` | see p.98 | documented; TOC/body-heading derived, parameters not transcribed | 98 |
| `:DIGital:ACTive` | `:DIGital:ACTive?` | see p.149 | documented; TOC/body-heading derived, parameters not transcribed | 149 |
| `:DIGital:BUS1:DEFault` | `:DIGital:BUS1:DEFault?` | see p.150 | documented; TOC/body-heading derived, parameters not transcribed | 150 |
| `:DIGital:BUS1:DISPlay` | `:DIGital:BUS1:DISPlay?` | see p.150 | documented; TOC/body-heading derived, parameters not transcribed | 150 |
| `:DIGital:BUS1:FORMat` | `:DIGital:BUS1:FORMat?` | see p.151 | documented; TOC/body-heading derived, parameters not transcribed | 151 |
| `:DIGital:BUS1:MAP` | `:DIGital:BUS1:MAP?` | see p.151 | documented; TOC/body-heading derived, parameters not transcribed | 151 |
| `:DIGital:BUS<n>:DEFault` | `:DIGital:BUS<n>:DEFault?` | see p.150 | documented; TOC/body-heading derived, parameters not transcribed | 150 |
| `:DIGital:BUS<n>:DISPlay` | `:DIGital:BUS<n>:DISPlay?` | see p.150 | documented; TOC/body-heading derived, parameters not transcribed | 150 |
| `:DIGital:BUS<n>:FORMat` | `:DIGital:BUS<n>:FORMat?` | see p.150 | documented; TOC/body-heading derived, parameters not transcribed | 150 |
| `:DIGital:BUS<n>:MAP` | `:DIGital:BUS<n>:MAP?` | see p.151 | documented; TOC/body-heading derived, parameters not transcribed | 151 |
| `:DIGital:D5` | `:DIGital:D5?` | see p.152 | documented; TOC/body-heading derived, parameters not transcribed | 152 |
| `:DIGital:D<d>` | `:DIGital:D<d>?` | see p.152 | documented; TOC/body-heading derived, parameters not transcribed | 152 |
| `:DIGital:HEIGht` | `:DIGital:HEIGht?` | see p.152 | documented; TOC/body-heading derived, parameters not transcribed | 152 |
| `:DIGital:LABel15` | `:DIGital:LABel15?` | see p.153 | documented; TOC/body-heading derived, parameters not transcribed | 153 |
| `:DIGital:LABel<d>` | `:DIGital:LABel<d>?` | see p.153 | documented; TOC/body-heading derived, parameters not transcribed | 153 |
| `:DIGital:POINts` | `:DIGital:POINts?` | see p.153 | documented; TOC/body-heading derived, parameters not transcribed | 153 |
| `:DIGital:POSition` | `:DIGital:POSition?` | see p.153 | documented; TOC/body-heading derived, parameters not transcribed | 153 |
| `:DIGital:SKEW` | `:DIGital:SKEW?` | see p.154 | documented; TOC/body-heading derived, parameters not transcribed | 154 |
| `:DIGital:SRATe` | `:DIGital:SRATe?` | see p.154 | documented; TOC/body-heading derived, parameters not transcribed | 154 |
| `:DIGital:THReshold1` | `:DIGital:THReshold1?` | see p.155 | documented; TOC/body-heading derived, parameters not transcribed | 155 |
| `:DIGital:THReshold<n>` | `:DIGital:THReshold<n>?` | see p.155 | documented; TOC/body-heading derived, parameters not transcribed | 155 |
| `:DISPlay:AXIS` | `:DISPlay:AXIS?` | see p.156 | documented; TOC/body-heading derived, parameters not transcribed | 156 |
| `:DISPlay:AXIS:MODE` | `:DISPlay:AXIS:MODE?` | see p.156 | documented; TOC/body-heading derived, parameters not transcribed | 156 |
| `:DISPlay:AXIS:POSition` | `:DISPlay:AXIS:POSition?` | see p.157 | documented; TOC/body-heading derived, parameters not transcribed | 157 |
| `:DISPlay:BACKlight` | `:DISPlay:BACKlight?` | see p.157 | documented; TOC/body-heading derived, parameters not transcribed | 157 |
| `:DISPlay:CLEar` | `:DISPlay:CLEar?` | see p.157 | documented; TOC/body-heading derived, parameters not transcribed | 157 |
| `:DISPlay:COLor` | `:DISPlay:COLor?` | see p.158 | documented; TOC/body-heading derived, parameters not transcribed | 158 |
| `:DISPlay:GRATicule` | `:DISPlay:GRATicule?` | see p.158 | documented; TOC/body-heading derived, parameters not transcribed | 158 |
| `:DISPlay:GRIDstyle` | `:DISPlay:GRIDstyle?` | see p.159 | documented; TOC/body-heading derived, parameters not transcribed | 159 |
| `:DISPlay:HIDemenu` | `:DISPlay:HIDemenu?` | see p.159 | documented; TOC/body-heading derived, parameters not transcribed | 159 |
| `:DISPlay:INTensity` | `:DISPlay:INTensity?` | see p.159 | documented; TOC/body-heading derived, parameters not transcribed | 159 |
| `:DISPlay:MENU` | `:DISPlay:MENU?` | see p.160 | documented; TOC/body-heading derived, parameters not transcribed | 160 |
| `:DISPlay:MENU:HIDE` | `:DISPlay:MENU:HIDE?` | see p.160 | documented; TOC/body-heading derived, parameters not transcribed | 160 |
| `:DISPlay:TRANsparence` | `:DISPlay:TRANsparence?` | see p.162 | documented; TOC/body-heading derived, parameters not transcribed | 162 |
| `:DISPlay:TYPE` | `:DISPlay:TYPE?` | see p.162 | documented; TOC/body-heading derived, parameters not transcribed | 162 |
| `:DVM:ALARm` | `:DVM:ALARm?` | see p.163 | documented; TOC/body-heading derived, parameters not transcribed | 163 |
| `:DVM:ARANge` | `:DVM:ARANge?` | see p.164 | documented; TOC/body-heading derived, parameters not transcribed | 164 |
| `:DVM:CURRent` | `:DVM:CURRent?` | see p.164 | documented; TOC/body-heading derived, parameters not transcribed | 164 |
| `:DVM:HOLD` | `:DVM:HOLD?` | see p.164 | documented; TOC/body-heading derived, parameters not transcribed | 164 |
| `:DVM:MODE` | `:DVM:MODE?` | see p.165 | documented; TOC/body-heading derived, parameters not transcribed | 165 |
| `:DVM:SOURce` | `:DVM:SOURce?` | see p.165 | documented; TOC/body-heading derived, parameters not transcribed | 165 |
| `:FUNCtion:FFTDisplay` | `:FUNCtion:FFTDisplay?` | see p.166 | documented; TOC/body-heading derived, parameters not transcribed | 166 |
| `:FUNCtion:GVALue` | `:FUNCtion:GVALue?` | see p.166 | documented; TOC/body-heading derived, parameters not transcribed | 166 |
| `:FUNCtion1:DIFF:DX` | `:FUNCtion1:DIFF:DX?` | see p.168 | documented; TOC/body-heading derived, parameters not transcribed | 168 |
| `:FUNCtion1:ERES:BITS` | `:FUNCtion1:ERES:BITS?` | see p.168 | documented; TOC/body-heading derived, parameters not transcribed | 168 |
| `:FUNCtion1:FFT:AUToset` | `:FUNCtion1:FFT:AUToset?` | see p.169 | documented; TOC/body-heading derived, parameters not transcribed | 169 |
| `:FUNCtion1:FFT:HCENter` | `:FUNCtion1:FFT:HCENter?` | see p.169 | documented; TOC/body-heading derived, parameters not transcribed | 169 |
| `:FUNCtion1:FFT:LOAD` | `:FUNCtion1:FFT:LOAD?` | see p.171 | documented; TOC/body-heading derived, parameters not transcribed | 171 |
| `:FUNCtion1:FFT:MODE` | `:FUNCtion1:FFT:MODE?` | see p.171 | documented; TOC/body-heading derived, parameters not transcribed | 171 |
| `:FUNCtion1:FFT:POINts` | `:FUNCtion1:FFT:POINts?` | see p.172 | documented; TOC/body-heading derived, parameters not transcribed | 172 |
| `:FUNCtion1:FFT:RLEVel` | `:FUNCtion1:FFT:RLEVel?` | see p.173 | documented; TOC/body-heading derived, parameters not transcribed | 173 |
| `:FUNCtion1:FFT:SCALe` | `:FUNCtion1:FFT:SCALe?` | see p.174 | documented; TOC/body-heading derived, parameters not transcribed | 174 |
| `:FUNCtion1:FFT:SEARch` | `:FUNCtion1:FFT:SEARch?` | see p.174 | documented; TOC/body-heading derived, parameters not transcribed | 174 |
| `:FUNCtion1:FFT:SEARch:EXCursion` | `:FUNCtion1:FFT:SEARch:EXCursion?` | see p.175 | documented; TOC/body-heading derived, parameters not transcribed | 175 |
| `:FUNCtion1:FFT:SEARch:MARKer1` | `:FUNCtion1:FFT:SEARch:MARKer1?` | see p.175 | documented; TOC/body-heading derived, parameters not transcribed | 175 |
| `:FUNCtion1:FFT:SEARch:MARKer2:SHOW` | `:FUNCtion1:FFT:SEARch:MARKer2:SHOW?` | see p.176 | documented; TOC/body-heading derived, parameters not transcribed | 176 |
| `:FUNCtion1:FFT:SEARch:MON` | `:FUNCtion1:FFT:SEARch:MON?` | see p.176 | documented; TOC/body-heading derived, parameters not transcribed | 176 |
| `:FUNCtion1:FFT:SEARch:PORDer` | `:FUNCtion1:FFT:SEARch:PORDer?` | see p.176 | documented; TOC/body-heading derived, parameters not transcribed | 176 |
| `:FUNCtion1:FFT:SEARch:TABLe` | `:FUNCtion1:FFT:SEARch:TABLe?` | see p.178 | documented; TOC/body-heading derived, parameters not transcribed | 178 |
| `:FUNCtion1:FFT:SEARch:TABLe:DELTa` | `:FUNCtion1:FFT:SEARch:TABLe:DELTa?` | see p.178 | documented; TOC/body-heading derived, parameters not transcribed | 178 |
| `:FUNCtion1:FFT:SEARch:TABLe:FREQuency` | `:FUNCtion1:FFT:SEARch:TABLe:FREQuency?` | see p.179 | documented; TOC/body-heading derived, parameters not transcribed | 179 |
| `:FUNCtion1:FFT:SEARch:THReshold` | `:FUNCtion1:FFT:SEARch:THReshold?` | see p.179 | documented; TOC/body-heading derived, parameters not transcribed | 179 |
| `:FUNCtion1:FFT:SPAN` | `:FUNCtion1:FFT:SPAN?` | see p.170 | documented; TOC/body-heading derived, parameters not transcribed | 170 |
| `:FUNCtion1:FFT:UNIT` | `:FUNCtion1:FFT:UNIT?` | see p.179 | documented; TOC/body-heading derived, parameters not transcribed | 179 |
| `:FUNCtion1:FFT:WINDow` | `:FUNCtion1:FFT:WINDow?` | see p.180 | documented; TOC/body-heading derived, parameters not transcribed | 180 |
| `:FUNCtion1:FILTer:HFRequency` | `:FUNCtion1:FILTer:HFRequency?` | see p.181 | documented; TOC/body-heading derived, parameters not transcribed | 181 |
| `:FUNCtion1:FILTer:LFRequency` | `:FUNCtion1:FILTer:LFRequency?` | see p.181 | documented; TOC/body-heading derived, parameters not transcribed | 181 |
| `:FUNCtion1:FILTer:TYPE` | `:FUNCtion1:FILTer:TYPE?` | see p.181 | documented; TOC/body-heading derived, parameters not transcribed | 181 |
| `:FUNCtion1:INTErpolate:COEF` | `:FUNCtion1:INTErpolate:COEF?` | see p.183 | documented; TOC/body-heading derived, parameters not transcribed | 183 |
| `:FUNCtion1:INTegrate:GATE` | `:FUNCtion1:INTegrate:GATE?` | see p.182 | documented; TOC/body-heading derived, parameters not transcribed | 182 |
| `:FUNCtion1:INTegrate:OFFSet` | `:FUNCtion1:INTegrate:OFFSet?` | see p.183 | documented; TOC/body-heading derived, parameters not transcribed | 183 |
| `:FUNCtion1:INVert` | `:FUNCtion1:INVert?` | see p.184 | documented; TOC/body-heading derived, parameters not transcribed | 184 |
| `:FUNCtion1:LABel` | `:FUNCtion1:LABel?` | see p.184 | documented; TOC/body-heading derived, parameters not transcribed | 184 |
| `:FUNCtion1:LABel:TEXT` | `:FUNCtion1:LABel:TEXT?` | see p.184 | documented; TOC/body-heading derived, parameters not transcribed | 184 |
| `:FUNCtion1:MAXHold:SWeeps` | `:FUNCtion1:MAXHold:SWeeps?` | see p.185 | documented; TOC/body-heading derived, parameters not transcribed | 185 |
| `:FUNCtion1:MINHold:SWeeps` | `:FUNCtion1:MINHold:SWeeps?` | see p.185 | documented; TOC/body-heading derived, parameters not transcribed | 185 |
| `:FUNCtion1:OPERation` | `:FUNCtion1:OPERation?` | see p.186 | documented; TOC/body-heading derived, parameters not transcribed | 186 |
| `:FUNCtion1:POSition` | `:FUNCtion1:POSition?` | see p.186 | documented; TOC/body-heading derived, parameters not transcribed | 186 |
| `:FUNCtion1:SCALe` | `:FUNCtion1:SCALe?` | see p.187 | documented; TOC/body-heading derived, parameters not transcribed | 187 |
| `:FUNCtion1:SOURce1` | `:FUNCtion1:SOURce1?` | see p.187 | documented; TOC/body-heading derived, parameters not transcribed | 187 |
| `:FUNCtion1:SOURce2` | `:FUNCtion1:SOURce2?` | see p.188 | documented; TOC/body-heading derived, parameters not transcribed | 188 |
| `:FUNCtion2:AVERage:NUM` | `:FUNCtion2:AVERage:NUM?` | see p.168 | documented; TOC/body-heading derived, parameters not transcribed | 168 |
| `:FUNCtion2:FFT:RESET` | `:FUNCtion2:FFT:RESET?` | see p.172 | documented; TOC/body-heading derived, parameters not transcribed | 172 |
| `:HISTORy:LIST` | `:HISTORy:LIST?` | see p.190 | documented; TOC/body-heading derived, parameters not transcribed | 190 |
| `:HISTORy:TIME` | `:HISTORy:TIME?` | see p.191 | documented; TOC/body-heading derived, parameters not transcribed | 191 |
| `:MEASure:ADVanced:CLEar` | `:MEASure:ADVanced:CLEar?` | see p.192 | documented; TOC/body-heading derived, parameters not transcribed | 192 |
| `:MEASure:ADVanced:LINenumber` | `:MEASure:ADVanced:LINenumber?` | see p.192 | documented; TOC/body-heading derived, parameters not transcribed | 192 |
| `:MEASure:ADVanced:P1` | `:MEASure:ADVanced:P1?` | see p.193 | documented; TOC/body-heading derived, parameters not transcribed | 193 |
| `:MEASure:ADVanced:P1:SHIStory` | `:MEASure:ADVanced:P1:SHIStory?` | see p.195 | documented; TOC/body-heading derived, parameters not transcribed | 195 |
| `:MEASure:ADVanced:P1:SOURce1` | `:MEASure:ADVanced:P1:SOURce1?` | see p.194 | documented; TOC/body-heading derived, parameters not transcribed | 194 |
| `:MEASure:ADVanced:P1:SOURce2` | `:MEASure:ADVanced:P1:SOURce2?` | see p.194 | documented; TOC/body-heading derived, parameters not transcribed | 194 |
| `:MEASure:ADVanced:P1:TYPE` | `:MEASure:ADVanced:P1:TYPE?` | see p.199 | documented; TOC/body-heading derived, parameters not transcribed | 199 |
| `:MEASure:ADVanced:P<n>:SHIStory` | `:MEASure:ADVanced:P<n>:SHIStory?` | see p.195 | documented; TOC/body-heading derived, parameters not transcribed | 195 |
| `:MEASure:ADVanced:P<n>:STATistics` | `:MEASure:ADVanced:P<n>:STATistics?` | see p.194 | documented; TOC/body-heading derived, parameters not transcribed | 194 |
| `:MEASure:ADVanced:P<n>:VALue` | `:MEASure:ADVanced:P<n>:VALue?` | see p.200 | documented; TOC/body-heading derived, parameters not transcribed | 200 |
| `:MEASure:ADVanced:STATistics` | `:MEASure:ADVanced:STATistics?` | see p.200 | documented; TOC/body-heading derived, parameters not transcribed | 200 |
| `:MEASure:ADVanced:STATistics:AIMLimit` | `:MEASure:ADVanced:STATistics:AIMLimit?` | see p.200 | documented; TOC/body-heading derived, parameters not transcribed | 200 |
| `:MEASure:ADVanced:STATistics:HISTOGram` | `:MEASure:ADVanced:STATistics:HISTOGram?` | see p.201 | documented; TOC/body-heading derived, parameters not transcribed | 201 |
| `:MEASure:ADVanced:STATistics:MAXCount` | `:MEASure:ADVanced:STATistics:MAXCount?` | see p.201 | documented; TOC/body-heading derived, parameters not transcribed | 201 |
| `:MEASure:ADVanced:STATistics:RESet` | `:MEASure:ADVanced:STATistics:RESet?` | see p.202 | documented; TOC/body-heading derived, parameters not transcribed | 202 |
| `:MEASure:ADVanced:STYLe` | `:MEASure:ADVanced:STYLe?` | see p.202 | documented; TOC/body-heading derived, parameters not transcribed | 202 |
| `:MEASure:ASTRategy` | `:MEASure:ASTRategy?` | see p.202 | documented; TOC/body-heading derived, parameters not transcribed | 202 |
| `:MEASure:ASTRategy:BASE` | `:MEASure:ASTRategy:BASE?` | see p.203 | documented; TOC/body-heading derived, parameters not transcribed | 203 |
| `:MEASure:ASTRategy:TOP` | `:MEASure:ASTRategy:TOP?` | see p.203 | documented; TOC/body-heading derived, parameters not transcribed | 203 |
| `:MEASure:DTIMe1:EDGE1` | `:MEASure:DTIMe1:EDGE1?` | see p.204 | documented; TOC/body-heading derived, parameters not transcribed | 204 |
| `:MEASure:DTIMe1:EDGE2` | `:MEASure:DTIMe1:EDGE2?` | see p.205 | documented; TOC/body-heading derived, parameters not transcribed | 205 |
| `:MEASure:DTIMe1:SLOPe1` | `:MEASure:DTIMe1:SLOPe1?` | see p.205 | documented; TOC/body-heading derived, parameters not transcribed | 205 |
| `:MEASure:DTIMe1:SLOPe2` | `:MEASure:DTIMe1:SLOPe2?` | see p.205 | documented; TOC/body-heading derived, parameters not transcribed | 205 |
| `:MEASure:DTIMe1:THReshold1` | `:MEASure:DTIMe1:THReshold1?` | see p.206 | documented; TOC/body-heading derived, parameters not transcribed | 206 |
| `:MEASure:DTIMe1:THReshold2` | `:MEASure:DTIMe1:THReshold2?` | see p.206 | documented; TOC/body-heading derived, parameters not transcribed | 206 |
| `:MEASure:DTIMe<n>:EDGE1` | `:MEASure:DTIMe<n>:EDGE1?` | see p.204 | documented; TOC/body-heading derived, parameters not transcribed | 204 |
| `:MEASure:DTIMe<n>:EDGE2` | `:MEASure:DTIMe<n>:EDGE2?` | see p.204 | documented; TOC/body-heading derived, parameters not transcribed | 204 |
| `:MEASure:DTIMe<n>:SLOPe1` | `:MEASure:DTIMe<n>:SLOPe1?` | see p.205 | documented; TOC/body-heading derived, parameters not transcribed | 205 |
| `:MEASure:DTIMe<n>:SLOPe2` | `:MEASure:DTIMe<n>:SLOPe2?` | see p.205 | documented; TOC/body-heading derived, parameters not transcribed | 205 |
| `:MEASure:DTIMe<n>:THReshold1` | `:MEASure:DTIMe<n>:THReshold1?` | see p.206 | documented; TOC/body-heading derived, parameters not transcribed | 206 |
| `:MEASure:DTIMe<n>:THReshold2` | `:MEASure:DTIMe<n>:THReshold2?` | see p.206 | documented; TOC/body-heading derived, parameters not transcribed | 206 |
| `:MEASure:GATE` | `:MEASure:GATE?` | see p.207 | documented; TOC/body-heading derived, parameters not transcribed | 207 |
| `:MEASure:GATE:GA` | `:MEASure:GATE:GA?` | see p.207 | documented; TOC/body-heading derived, parameters not transcribed | 207 |
| `:MEASure:GATE:GB` | `:MEASure:GATE:GB?` | see p.207 | documented; TOC/body-heading derived, parameters not transcribed | 207 |
| `:MEASure:RDISplay` | `:MEASure:RDISplay?` | see p.209 | documented; TOC/body-heading derived, parameters not transcribed | 209 |
| `:MEASure:SIMPle:CLEar` | `:MEASure:SIMPle:CLEar?` | see p.209 | documented; TOC/body-heading derived, parameters not transcribed | 209 |
| `:MEASure:SIMPle:SOURce` | `:MEASure:SIMPle:SOURce?` | see p.210 | documented; TOC/body-heading derived, parameters not transcribed | 210 |
| `:MEASure:SIMPle:VALue` | `:MEASure:SIMPle:VALue?` | see p.210 | documented; TOC/body-heading derived, parameters not transcribed | 210 |
| `:MEASure:THReshold:ABSolute` | `:MEASure:THReshold:ABSolute?` | see p.212 | documented; TOC/body-heading derived, parameters not transcribed | 212 |
| `:MEASure:THReshold:PERCent` | `:MEASure:THReshold:PERCent?` | see p.213 | documented; TOC/body-heading derived, parameters not transcribed | 213 |
| `:MEASure:THReshold:SOURce` | `:MEASure:THReshold:SOURce?` | see p.211 | documented; TOC/body-heading derived, parameters not transcribed | 211 |
| `:MEASure:THReshold:TYPE` | `:MEASure:THReshold:TYPE?` | see p.212 | documented; TOC/body-heading derived, parameters not transcribed | 212 |
| `:MEMory2:HORizontal:POSition` | `:MEMory2:HORizontal:POSition?` | see p.214 | documented; TOC/body-heading derived, parameters not transcribed | 214 |
| `:MEMory2:HORizontal:SCALe` | `:MEMory2:HORizontal:SCALe?` | see p.214 | documented; TOC/body-heading derived, parameters not transcribed | 214 |
| `:MEMory2:HORizontal:SYNC` | `:MEMory2:HORizontal:SYNC?` | see p.215 | documented; TOC/body-heading derived, parameters not transcribed | 215 |
| `:MEMory2:LABel` | `:MEMory2:LABel?` | see p.216 | documented; TOC/body-heading derived, parameters not transcribed | 216 |
| `:MEMory2:LABel:TEXT` | `:MEMory2:LABel:TEXT?` | see p.216 | documented; TOC/body-heading derived, parameters not transcribed | 216 |
| `:MEMory2:SWITch` | `:MEMory2:SWITch?` | see p.216 | documented; TOC/body-heading derived, parameters not transcribed | 216 |
| `:MEMory2:VERTical:POSition` | `:MEMory2:VERTical:POSition?` | see p.217 | documented; TOC/body-heading derived, parameters not transcribed | 217 |
| `:MEMory2:VERTical:SCALe` | `:MEMory2:VERTical:SCALe?` | see p.217 | documented; TOC/body-heading derived, parameters not transcribed | 217 |
| `:MTES:MASK:LOAD` | `:MTES:MASK:LOAD?` | see p.221 | documented; TOC/body-heading derived, parameters not transcribed | 221 |
| `:MTESt:COUNt` | `:MTESt:COUNt?` | see p.218 | documented; TOC/body-heading derived, parameters not transcribed | 218 |
| `:MTESt:FUNCtion:BUZZer` | `:MTESt:FUNCtion:BUZZer?` | see p.218 | documented; TOC/body-heading derived, parameters not transcribed | 218 |
| `:MTESt:FUNCtion:COF` | `:MTESt:FUNCtion:COF?` | see p.219 | documented; TOC/body-heading derived, parameters not transcribed | 219 |
| `:MTESt:FUNCtion:FTH` | `:MTESt:FUNCtion:FTH?` | see p.219 | documented; TOC/body-heading derived, parameters not transcribed | 219 |
| `:MTESt:FUNCtion:SOF` | `:MTESt:FUNCtion:SOF?` | see p.220 | documented; TOC/body-heading derived, parameters not transcribed | 220 |
| `:MTESt:IDISplay` | `:MTESt:IDISplay?` | see p.220 | documented; TOC/body-heading derived, parameters not transcribed | 220 |
| `:MTESt:MASK:CREate` | `:MTESt:MASK:CREate?` | see p.221 | documented; TOC/body-heading derived, parameters not transcribed | 221 |
| `:MTESt:OPERate` | `:MTESt:OPERate?` | see p.222 | documented; TOC/body-heading derived, parameters not transcribed | 222 |
| `:MTESt:RESet` | `:MTESt:RESet?` | see p.222 | documented; TOC/body-heading derived, parameters not transcribed | 222 |
| `:MTESt:SOURce` | `:MTESt:SOURce?` | see p.222 | documented; TOC/body-heading derived, parameters not transcribed | 222 |
| `:RECall:FDEFault` | `:RECall:FDEFault?` | see p.224 | documented; TOC/body-heading derived, parameters not transcribed | 224 |
| `:RECall:REFerence` | `:RECall:REFerence?` | see p.224 | documented; TOC/body-heading derived, parameters not transcribed | 224 |
| `:RECall:SERase` | `:RECall:SERase?` | see p.225 | documented; TOC/body-heading derived, parameters not transcribed | 225 |
| `:RECall:SETup` | `:RECall:SETup?` | see p.225 | documented; TOC/body-heading derived, parameters not transcribed | 225 |
| `:REFA:DATA` | `:REFA:DATA?` | see p.227 | documented; TOC/body-heading derived, parameters not transcribed | 227 |
| `:REFA:DATA:POSition` | `:REFA:DATA:POSition?` | see p.228 | documented; TOC/body-heading derived, parameters not transcribed | 228 |
| `:REFA:DATA:SCALe` | `:REFA:DATA:SCALe?` | see p.228 | documented; TOC/body-heading derived, parameters not transcribed | 228 |
| `:REFA:DATA:SOUR` | `:REFA:DATA:SOUR?` | see p.227 | documented; TOC/body-heading derived, parameters not transcribed | 227 |
| `:REFA:LAB` | `:REFA:LAB?` | see p.226 | documented; TOC/body-heading derived, parameters not transcribed | 226 |
| `:REFA:LABel` | `:REFA:LABel?` | see p.226 | documented; TOC/body-heading derived, parameters not transcribed | 226 |
| `:REFA:LABel:TEXT` | `:REFA:LABel:TEXT?` | see p.226 | documented; TOC/body-heading derived, parameters not transcribed | 226 |
| `:SAVE:BINary` | `:SAVE:BINary?` | see p.229 | documented; TOC/body-heading derived, parameters not transcribed | 229 |
| `:SAVE:CSV` | `:SAVE:CSV?` | see p.230 | documented; TOC/body-heading derived, parameters not transcribed | 230 |
| `:SAVE:DEFault` | `:SAVE:DEFault?` | see p.231 | documented; TOC/body-heading derived, parameters not transcribed | 231 |
| `:SAVE:MATLab` | `:SAVE:MATLab?` | see p.232 | documented; TOC/body-heading derived, parameters not transcribed | 232 |
| `:SAVE:REFerence` | `:SAVE:REFerence?` | see p.233 | documented; TOC/body-heading derived, parameters not transcribed | 233 |
| `:SAVE:SET` | `:SAVE:SET?` | see p.234 | documented; TOC/body-heading derived, parameters not transcribed | 234 |
| `:SEAR:MODE` | `:SEAR:MODE?` | see p.235 | documented; TOC/body-heading derived, parameters not transcribed | 235 |
| `:SEARch:COPY` | `:SEARch:COPY?` | see p.236 | documented; TOC/body-heading derived, parameters not transcribed | 236 |
| `:SEARch:COUNT` | `:SEARch:COUNT?` | see p.236 | documented; TOC/body-heading derived, parameters not transcribed | 236 |
| `:SEARch:EDGE` | `:SEARch:EDGE?` | see p.237 | documented; TOC/body-heading derived, parameters not transcribed | 237 |
| `:SEARch:EDGE:LEVel` | `:SEARch:EDGE:LEVel?` | see p.238 | documented; TOC/body-heading derived, parameters not transcribed | 238 |
| `:SEARch:EDGE:SLOPe` | `:SEARch:EDGE:SLOPe?` | see p.237 | documented; TOC/body-heading derived, parameters not transcribed | 237 |
| `:SEARch:EDGE:SOURce` | `:SEARch:EDGE:SOURce?` | see p.237 | documented; TOC/body-heading derived, parameters not transcribed | 237 |
| `:SEARch:EVENt` | `:SEARch:EVENt?` | see p.236 | documented; TOC/body-heading derived, parameters not transcribed | 236 |
| `:SEARch:INTerval` | `:SEARch:INTerval?` | see p.248 | documented; TOC/body-heading derived, parameters not transcribed | 248 |
| `:SEARch:INTerval:LEVel` | `:SEARch:INTerval:LEVel?` | see p.249 | documented; TOC/body-heading derived, parameters not transcribed | 249 |
| `:SEARch:INTerval:LIMit` | `:SEARch:INTerval:LIMit?` | see p.249 | documented; TOC/body-heading derived, parameters not transcribed | 249 |
| `:SEARch:INTerval:SLOPe` | `:SEARch:INTerval:SLOPe?` | see p.248 | documented; TOC/body-heading derived, parameters not transcribed | 248 |
| `:SEARch:INTerval:SOURce` | `:SEARch:INTerval:SOURce?` | see p.248 | documented; TOC/body-heading derived, parameters not transcribed | 248 |
| `:SEARch:INTerval:TLOWer` | `:SEARch:INTerval:TLOWer?` | see p.250 | documented; TOC/body-heading derived, parameters not transcribed | 250 |
| `:SEARch:INTerval:TUPPer` | `:SEARch:INTerval:TUPPer?` | see p.250 | documented; TOC/body-heading derived, parameters not transcribed | 250 |
| `:SEARch:PULSe` | `:SEARch:PULSe?` | see p.244 | documented; TOC/body-heading derived, parameters not transcribed | 244 |
| `:SEARch:PULSe:LEVel` | `:SEARch:PULSe:LEVel?` | see p.245 | documented; TOC/body-heading derived, parameters not transcribed | 245 |
| `:SEARch:PULSe:LIMit` | `:SEARch:PULSe:LIMit?` | see p.245 | documented; TOC/body-heading derived, parameters not transcribed | 245 |
| `:SEARch:PULSe:POLarity` | `:SEARch:PULSe:POLarity?` | see p.244 | documented; TOC/body-heading derived, parameters not transcribed | 244 |
| `:SEARch:PULSe:SOURce` | `:SEARch:PULSe:SOURce?` | see p.244 | documented; TOC/body-heading derived, parameters not transcribed | 244 |
| `:SEARch:PULSe:TLOWer` | `:SEARch:PULSe:TLOWer?` | see p.246 | documented; TOC/body-heading derived, parameters not transcribed | 246 |
| `:SEARch:PULSe:TUPPer` | `:SEARch:PULSe:TUPPer?` | see p.246 | documented; TOC/body-heading derived, parameters not transcribed | 246 |
| `:SEARch:PULse:POLarity` | `:SEARch:PULse:POLarity?` | see p.244 | documented; TOC/body-heading derived, parameters not transcribed | 244 |
| `:SEARch:PULse:SOURce` | `:SEARch:PULse:SOURce?` | see p.244 | documented; TOC/body-heading derived, parameters not transcribed | 244 |
| `:SEARch:RUNT` | `:SEARch:RUNT?` | see p.252 | documented; TOC/body-heading derived, parameters not transcribed | 252 |
| `:SEARch:RUNT:HLEVel` | `:SEARch:RUNT:HLEVel?` | see p.252 | documented; TOC/body-heading derived, parameters not transcribed | 252 |
| `:SEARch:RUNT:LIMit` | `:SEARch:RUNT:LIMit?` | see p.254 | documented; TOC/body-heading derived, parameters not transcribed | 254 |
| `:SEARch:RUNT:LLEVel` | `:SEARch:RUNT:LLEVel?` | see p.253 | documented; TOC/body-heading derived, parameters not transcribed | 253 |
| `:SEARch:RUNT:POLarity` | `:SEARch:RUNT:POLarity?` | see p.252 | documented; TOC/body-heading derived, parameters not transcribed | 252 |
| `:SEARch:RUNT:SOURce` | `:SEARch:RUNT:SOURce?` | see p.252 | documented; TOC/body-heading derived, parameters not transcribed | 252 |
| `:SEARch:RUNT:TLOWer` | `:SEARch:RUNT:TLOWer?` | see p.254 | documented; TOC/body-heading derived, parameters not transcribed | 254 |
| `:SEARch:RUNT:TUPPer` | `:SEARch:RUNT:TUPPer?` | see p.254 | documented; TOC/body-heading derived, parameters not transcribed | 254 |
| `:SEARch:SLOPe` | `:SEARch:SLOPe?` | see p.239 | documented; TOC/body-heading derived, parameters not transcribed | 239 |
| `:SEARch:SLOPe:HLEVel` | `:SEARch:SLOPe:HLEVel?` | see p.239 | documented; TOC/body-heading derived, parameters not transcribed | 239 |
| `:SEARch:SLOPe:LIMit` | `:SEARch:SLOPe:LIMit?` | see p.241 | documented; TOC/body-heading derived, parameters not transcribed | 241 |
| `:SEARch:SLOPe:LLEVel` | `:SEARch:SLOPe:LLEVel?` | see p.240 | documented; TOC/body-heading derived, parameters not transcribed | 240 |
| `:SEARch:SLOPe:SLOPe` | `:SEARch:SLOPe:SLOPe?` | see p.239 | documented; TOC/body-heading derived, parameters not transcribed | 239 |
| `:SEARch:SLOPe:SOURce` | `:SEARch:SLOPe:SOURce?` | see p.239 | documented; TOC/body-heading derived, parameters not transcribed | 239 |
| `:SEARch:SLOPe:TLOWer` | `:SEARch:SLOPe:TLOWer?` | see p.241 | documented; TOC/body-heading derived, parameters not transcribed | 241 |
| `:SEARch:SLOPe:TUPPer` | `:SEARch:SLOPe:TUPPer?` | see p.241 | documented; TOC/body-heading derived, parameters not transcribed | 241 |
| `:SYSTem:BUZZer` | `:SYSTem:BUZZer?` | see p.257 | documented; TOC/body-heading derived, parameters not transcribed | 257 |
| `:SYSTem:CLOCk` | `:SYSTem:CLOCk?` | see p.257 | documented; TOC/body-heading derived, parameters not transcribed | 257 |
| `:SYSTem:COMMunicate:LAN:MAC` | `:SYSTem:COMMunicate:LAN:MAC?` | see p.259 | documented; TOC/body-heading derived, parameters not transcribed | 259 |
| `:SYSTem:COMMunicate:VNCPort` | `:SYSTem:COMMunicate:VNCPort?` | see p.260 | documented; TOC/body-heading derived, parameters not transcribed | 260 |
| `:SYSTem:DATE` | `:SYSTem:DATE?` | see p.260 | documented; TOC/body-heading derived, parameters not transcribed | 260 |
| `:SYSTem:EDUMode` | `:SYSTem:EDUMode?` | see p.261 | documented; TOC/body-heading derived, parameters not transcribed | 261 |
| `:SYSTem:LANGuage` | `:SYSTem:LANGuage?` | see p.261 | documented; TOC/body-heading derived, parameters not transcribed | 261 |
| `:SYSTem:MENU` | `:SYSTem:MENU?` | see p.262 | documented; TOC/body-heading derived, parameters not transcribed | 262 |
| `:SYSTem:NSTorage:STATus` | `:SYSTem:NSTorage:STATus?` | see p.263 | documented; TOC/body-heading derived, parameters not transcribed | 263 |
| `:SYSTem:PON` | `:SYSTem:PON?` | see p.264 | documented; TOC/body-heading derived, parameters not transcribed | 264 |
| `:SYSTem:REBoot` | `:SYSTem:REBoot?` | see p.264 | documented; TOC/body-heading derived, parameters not transcribed | 264 |
| `:SYSTem:SELFCal` | `:SYSTem:SELFCal?` | see p.265 | documented; TOC/body-heading derived, parameters not transcribed | 265 |
| `:SYSTem:SHUTdown` | `:SYSTem:SHUTdown?` | see p.265 | documented; TOC/body-heading derived, parameters not transcribed | 265 |
| `:SYSTem:SSAVer` | `:SYSTem:SSAVer?` | see p.265 | documented; TOC/body-heading derived, parameters not transcribed | 265 |
| `:SYSTem:TIME` | `:SYSTem:TIME?` | see p.266 | documented; TOC/body-heading derived, parameters not transcribed | 266 |
| `:SYSTem:TOUCh` | `:SYSTem:TOUCh?` | see p.266 | documented; TOC/body-heading derived, parameters not transcribed | 266 |
| `:TIMebase:DELay` | `:TIMebase:DELay?` | see p.267 | documented; TOC/body-heading derived, parameters not transcribed | 267 |
| `:TIMebase:REFerence` | `:TIMebase:REFerence?` | see p.267 | documented; TOC/body-heading derived, parameters not transcribed | 267 |
| `:TIMebase:REFerence:POSition` | `:TIMebase:REFerence:POSition?` | see p.268 | documented; TOC/body-heading derived, parameters not transcribed | 268 |
| `:TIMebase:WINDow` | `:TIMebase:WINDow?` | see p.269 | documented; TOC/body-heading derived, parameters not transcribed | 269 |
| `:TIMebase:WINDow:DELay` | `:TIMebase:WINDow:DELay?` | see p.269 | documented; TOC/body-heading derived, parameters not transcribed | 269 |
| `:TIMebase:WINDow:SCALe` | `:TIMebase:WINDow:SCALe?` | see p.269 | documented; TOC/body-heading derived, parameters not transcribed | 269 |
| `:TRIG:SPI:NCSS` | `:TRIG:SPI:NCSS?` | see p.370 | documented; TOC/body-heading derived, parameters not transcribed | 370 |
| `:TRIG:STAT` | `:TRIG:STAT?` | see p.272 | documented; TOC/body-heading derived, parameters not transcribed | 272 |
| `:TRIGger:CAN` | `:TRIGger:CAN?` | see p.380 | documented; TOC/body-heading derived, parameters not transcribed | 380 |
| `:TRIGger:CAN:BAUD` | `:TRIGger:CAN:BAUD?` | see p.380 | documented; TOC/body-heading derived, parameters not transcribed | 380 |
| `:TRIGger:CAN:CONDition` | `:TRIGger:CAN:CONDition?` | see p.380 | documented; TOC/body-heading derived, parameters not transcribed | 380 |
| `:TRIGger:CAN:DAT2` | `:TRIGger:CAN:DAT2?` | see p.381 | documented; TOC/body-heading derived, parameters not transcribed | 381 |
| `:TRIGger:CAN:DATA` | `:TRIGger:CAN:DATA?` | see p.381 | documented; TOC/body-heading derived, parameters not transcribed | 381 |
| `:TRIGger:CAN:ID` | `:TRIGger:CAN:ID?` | see p.382 | documented; TOC/body-heading derived, parameters not transcribed | 382 |
| `:TRIGger:CAN:IDLENgth` | `:TRIGger:CAN:IDLENgth?` | see p.382 | documented; TOC/body-heading derived, parameters not transcribed | 382 |
| `:TRIGger:CAN:IDLength` | `:TRIGger:CAN:IDLength?` | see p.382 | documented; TOC/body-heading derived, parameters not transcribed | 382 |
| `:TRIGger:CAN:SOURce` | `:TRIGger:CAN:SOURce?` | see p.383 | documented; TOC/body-heading derived, parameters not transcribed | 383 |
| `:TRIGger:CAN:THReshold` | `:TRIGger:CAN:THReshold?` | see p.383 | documented; TOC/body-heading derived, parameters not transcribed | 383 |
| `:TRIGger:CANFd:BAUDData` | `:TRIGger:CANFd:BAUDData?` | see p.396 | documented; TOC/body-heading derived, parameters not transcribed | 396 |
| `:TRIGger:CANFd:BAUDNominal` | `:TRIGger:CANFd:BAUDNominal?` | see p.396 | documented; TOC/body-heading derived, parameters not transcribed | 396 |
| `:TRIGger:CANFd:CONDition` | `:TRIGger:CANFd:CONDition?` | see p.397 | documented; TOC/body-heading derived, parameters not transcribed | 397 |
| `:TRIGger:CANFd:DAT2` | `:TRIGger:CANFd:DAT2?` | see p.397 | documented; TOC/body-heading derived, parameters not transcribed | 397 |
| `:TRIGger:CANFd:DATA` | `:TRIGger:CANFd:DATA?` | see p.397 | documented; TOC/body-heading derived, parameters not transcribed | 397 |
| `:TRIGger:CANFd:FTYPe` | `:TRIGger:CANFd:FTYPe?` | see p.398 | documented; TOC/body-heading derived, parameters not transcribed | 398 |
| `:TRIGger:CANFd:ID` | `:TRIGger:CANFd:ID?` | see p.398 | documented; TOC/body-heading derived, parameters not transcribed | 398 |
| `:TRIGger:CANFd:IDLength` | `:TRIGger:CANFd:IDLength?` | see p.399 | documented; TOC/body-heading derived, parameters not transcribed | 399 |
| `:TRIGger:CANFd:SOURce` | `:TRIGger:CANFd:SOURce?` | see p.399 | documented; TOC/body-heading derived, parameters not transcribed | 399 |
| `:TRIGger:CANFd:THReshold` | `:TRIGger:CANFd:THReshold?` | see p.400 | documented; TOC/body-heading derived, parameters not transcribed | 400 |
| `:TRIGger:DELay` | `:TRIGger:DELay?` | see p.340 | documented; TOC/body-heading derived, parameters not transcribed | 340 |
| `:TRIGger:DELay:INPut` | `:TRIGger:DELay:INPut?` | see p.340 | documented; TOC/body-heading derived, parameters not transcribed | 340 |
| `:TRIGger:DELay:LEVel` | `:TRIGger:DELay:LEVel?` | see p.341 | documented; TOC/body-heading derived, parameters not transcribed | 341 |
| `:TRIGger:DELay:LEVel2` | `:TRIGger:DELay:LEVel2?` | see p.342 | documented; TOC/body-heading derived, parameters not transcribed | 342 |
| `:TRIGger:DELay:LIMit` | `:TRIGger:DELay:LIMit?` | see p.343 | documented; TOC/body-heading derived, parameters not transcribed | 343 |
| `:TRIGger:DELay:SLOPe` | `:TRIGger:DELay:SLOPe?` | see p.341 | documented; TOC/body-heading derived, parameters not transcribed | 341 |
| `:TRIGger:DELay:SLOPe2` | `:TRIGger:DELay:SLOPe2?` | see p.341 | documented; TOC/body-heading derived, parameters not transcribed | 341 |
| `:TRIGger:DELay:SOURce` | `:TRIGger:DELay:SOURce?` | see p.340 | documented; TOC/body-heading derived, parameters not transcribed | 340 |
| `:TRIGger:DELay:SOURce2` | `:TRIGger:DELay:SOURce2?` | see p.340 | documented; TOC/body-heading derived, parameters not transcribed | 340 |
| `:TRIGger:DELay:TLOWer` | `:TRIGger:DELay:TLOWer?` | see p.343 | documented; TOC/body-heading derived, parameters not transcribed | 343 |
| `:TRIGger:DELay:TUPPer` | `:TRIGger:DELay:TUPPer?` | see p.343 | documented; TOC/body-heading derived, parameters not transcribed | 343 |
| `:TRIGger:DROPout` | `:TRIGger:DROPout?` | see p.315 | documented; TOC/body-heading derived, parameters not transcribed | 315 |
| `:TRIGger:DROPout:COUPling` | `:TRIGger:DROPout:COUPling?` | see p.315 | documented; TOC/body-heading derived, parameters not transcribed | 315 |
| `:TRIGger:DROPout:HLDEVent` | `:TRIGger:DROPout:HLDEVent?` | see p.315 | documented; TOC/body-heading derived, parameters not transcribed | 315 |
| `:TRIGger:DROPout:HLDTime` | `:TRIGger:DROPout:HLDTime?` | see p.316 | documented; TOC/body-heading derived, parameters not transcribed | 316 |
| `:TRIGger:DROPout:HOLDoff` | `:TRIGger:DROPout:HOLDoff?` | see p.316 | documented; TOC/body-heading derived, parameters not transcribed | 316 |
| `:TRIGger:DROPout:HSTart` | `:TRIGger:DROPout:HSTart?` | see p.317 | documented; TOC/body-heading derived, parameters not transcribed | 317 |
| `:TRIGger:DROPout:LEVel` | `:TRIGger:DROPout:LEVel?` | see p.317 | documented; TOC/body-heading derived, parameters not transcribed | 317 |
| `:TRIGger:DROPout:NREJect` | `:TRIGger:DROPout:NREJect?` | see p.318 | documented; TOC/body-heading derived, parameters not transcribed | 318 |
| `:TRIGger:DROPout:SLOPe` | `:TRIGger:DROPout:SLOPe?` | see p.318 | documented; TOC/body-heading derived, parameters not transcribed | 318 |
| `:TRIGger:DROPout:SOURce` | `:TRIGger:DROPout:SOURce?` | see p.319 | documented; TOC/body-heading derived, parameters not transcribed | 319 |
| `:TRIGger:DROPout:TIME` | `:TRIGger:DROPout:TIME?` | see p.319 | documented; TOC/body-heading derived, parameters not transcribed | 319 |
| `:TRIGger:DROPout:TYPE` | `:TRIGger:DROPout:TYPE?` | see p.320 | documented; TOC/body-heading derived, parameters not transcribed | 320 |
| `:TRIGger:EDGE` | `:TRIGger:EDGE?` | see p.274 | documented; TOC/body-heading derived, parameters not transcribed | 274 |
| `:TRIGger:EDGE:COUPling` | `:TRIGger:EDGE:COUPling?` | see p.274 | documented; TOC/body-heading derived, parameters not transcribed | 274 |
| `:TRIGger:EDGE:HLDEVent` | `:TRIGger:EDGE:HLDEVent?` | see p.274 | documented; TOC/body-heading derived, parameters not transcribed | 274 |
| `:TRIGger:EDGE:HLDTime` | `:TRIGger:EDGE:HLDTime?` | see p.275 | documented; TOC/body-heading derived, parameters not transcribed | 275 |
| `:TRIGger:EDGE:HOLDoff` | `:TRIGger:EDGE:HOLDoff?` | see p.275 | documented; TOC/body-heading derived, parameters not transcribed | 275 |
| `:TRIGger:EDGE:HSTart` | `:TRIGger:EDGE:HSTart?` | see p.276 | documented; TOC/body-heading derived, parameters not transcribed | 276 |
| `:TRIGger:EDGE:IMPedance` | `:TRIGger:EDGE:IMPedance?` | see p.276 | documented; TOC/body-heading derived, parameters not transcribed | 276 |
| `:TRIGger:EDGE:LEVel` | `:TRIGger:EDGE:LEVel?` | see p.277 | documented; TOC/body-heading derived, parameters not transcribed | 277 |
| `:TRIGger:EDGE:NREJect` | `:TRIGger:EDGE:NREJect?` | see p.278 | documented; TOC/body-heading derived, parameters not transcribed | 278 |
| `:TRIGger:FLEXray:BAUD` | `:TRIGger:FLEXray:BAUD?` | see p.392 | documented; TOC/body-heading derived, parameters not transcribed | 392 |
| `:TRIGger:FLEXray:CONDition` | `:TRIGger:FLEXray:CONDition?` | see p.392 | documented; TOC/body-heading derived, parameters not transcribed | 392 |
| `:TRIGger:FLEXray:FRAMe:COMPare` | `:TRIGger:FLEXray:FRAMe:COMPare?` | see p.393 | documented; TOC/body-heading derived, parameters not transcribed | 393 |
| `:TRIGger:FLEXray:FRAMe:CYCLe` | `:TRIGger:FLEXray:FRAMe:CYCLe?` | see p.393 | documented; TOC/body-heading derived, parameters not transcribed | 393 |
| `:TRIGger:FLEXray:FRAMe:ID` | `:TRIGger:FLEXray:FRAMe:ID?` | see p.393 | documented; TOC/body-heading derived, parameters not transcribed | 393 |
| `:TRIGger:FLEXray:FRAMe:REPetition` | `:TRIGger:FLEXray:FRAMe:REPetition?` | see p.394 | documented; TOC/body-heading derived, parameters not transcribed | 394 |
| `:TRIGger:FLEXray:SOURce` | `:TRIGger:FLEXray:SOURce?` | see p.394 | documented; TOC/body-heading derived, parameters not transcribed | 394 |
| `:TRIGger:FLEXray:Source` | `:TRIGger:FLEXray:Source?` | see p.394 | documented; TOC/body-heading derived, parameters not transcribed | 394 |
| `:TRIGger:FLEXray:THReshold` | `:TRIGger:FLEXray:THReshold?` | see p.395 | documented; TOC/body-heading derived, parameters not transcribed | 395 |
| `:TRIGger:FREQuency` | `:TRIGger:FREQuency?` | see p.271 | documented; TOC/body-heading derived, parameters not transcribed | 271 |
| `:TRIGger:IIC` | `:TRIGger:IIC?` | see p.357 | documented; TOC/body-heading derived, parameters not transcribed | 357 |
| `:TRIGger:IIC:ADDRess` | `:TRIGger:IIC:ADDRess?` | see p.357 | documented; TOC/body-heading derived, parameters not transcribed | 357 |
| `:TRIGger:IIC:ALENgth` | `:TRIGger:IIC:ALENgth?` | see p.357 | documented; TOC/body-heading derived, parameters not transcribed | 357 |
| `:TRIGger:IIC:CONDition` | `:TRIGger:IIC:CONDition?` | see p.358 | documented; TOC/body-heading derived, parameters not transcribed | 358 |
| `:TRIGger:IIC:DAT2` | `:TRIGger:IIC:DAT2?` | see p.358 | documented; TOC/body-heading derived, parameters not transcribed | 358 |
| `:TRIGger:IIC:DATA` | `:TRIGger:IIC:DATA?` | see p.358 | documented; TOC/body-heading derived, parameters not transcribed | 358 |
| `:TRIGger:IIC:DLENgth` | `:TRIGger:IIC:DLENgth?` | see p.359 | documented; TOC/body-heading derived, parameters not transcribed | 359 |
| `:TRIGger:IIC:LIMit` | `:TRIGger:IIC:LIMit?` | see p.359 | documented; TOC/body-heading derived, parameters not transcribed | 359 |
| `:TRIGger:IIC:RWBit` | `:TRIGger:IIC:RWBit?` | see p.360 | documented; TOC/body-heading derived, parameters not transcribed | 360 |
| `:TRIGger:IIC:SCLSource` | `:TRIGger:IIC:SCLSource?` | see p.360 | documented; TOC/body-heading derived, parameters not transcribed | 360 |
| `:TRIGger:IIC:SCLThreshold` | `:TRIGger:IIC:SCLThreshold?` | see p.361 | documented; TOC/body-heading derived, parameters not transcribed | 361 |
| `:TRIGger:IIC:SDASource` | `:TRIGger:IIC:SDASource?` | see p.361 | documented; TOC/body-heading derived, parameters not transcribed | 361 |
| `:TRIGger:IIC:SDAThreshold` | `:TRIGger:IIC:SDAThreshold?` | see p.362 | documented; TOC/body-heading derived, parameters not transcribed | 362 |
| `:TRIGger:IIS:AVARiant` | `:TRIGger:IIS:AVARiant?` | see p.401 | documented; TOC/body-heading derived, parameters not transcribed | 401 |
| `:TRIGger:IIS:BCLKSource` | `:TRIGger:IIS:BCLKSource?` | see p.401 | documented; TOC/body-heading derived, parameters not transcribed | 401 |
| `:TRIGger:IIS:BCLKThreshold` | `:TRIGger:IIS:BCLKThreshold?` | see p.402 | documented; TOC/body-heading derived, parameters not transcribed | 402 |
| `:TRIGger:IIS:BITorder` | `:TRIGger:IIS:BITorder?` | see p.402 | documented; TOC/body-heading derived, parameters not transcribed | 402 |
| `:TRIGger:IIS:CHANnel` | `:TRIGger:IIS:CHANnel?` | see p.403 | documented; TOC/body-heading derived, parameters not transcribed | 403 |
| `:TRIGger:IIS:COMPare` | `:TRIGger:IIS:COMPare?` | see p.403 | documented; TOC/body-heading derived, parameters not transcribed | 403 |
| `:TRIGger:IIS:CONDition` | `:TRIGger:IIS:CONDition?` | see p.403 | documented; TOC/body-heading derived, parameters not transcribed | 403 |
| `:TRIGger:IIS:DLENgth` | `:TRIGger:IIS:DLENgth?` | see p.404 | documented; TOC/body-heading derived, parameters not transcribed | 404 |
| `:TRIGger:IIS:DSource` | `:TRIGger:IIS:DSource?` | see p.404 | documented; TOC/body-heading derived, parameters not transcribed | 404 |
| `:TRIGger:IIS:DTHReshold` | `:TRIGger:IIS:DTHReshold?` | see p.405 | documented; TOC/body-heading derived, parameters not transcribed | 405 |
| `:TRIGger:IIS:LATChedge` | `:TRIGger:IIS:LATChedge?` | see p.406 | documented; TOC/body-heading derived, parameters not transcribed | 406 |
| `:TRIGger:IIS:LATChegde` | `:TRIGger:IIS:LATChegde?` | see p.406 | documented; TOC/body-heading derived, parameters not transcribed | 406 |
| `:TRIGger:IIS:LCH` | `:TRIGger:IIS:LCH?` | see p.406 | documented; TOC/body-heading derived, parameters not transcribed | 406 |
| `:TRIGger:IIS:VALue` | `:TRIGger:IIS:VALue?` | see p.407 | documented; TOC/body-heading derived, parameters not transcribed | 407 |
| `:TRIGger:IIS:WSSource` | `:TRIGger:IIS:WSSource?` | see p.407 | documented; TOC/body-heading derived, parameters not transcribed | 407 |
| `:TRIGger:IIS:WSTHreshold` | `:TRIGger:IIS:WSTHreshold?` | see p.408 | documented; TOC/body-heading derived, parameters not transcribed | 408 |
| `:TRIGger:INTerval` | `:TRIGger:INTerval?` | see p.308 | documented; TOC/body-heading derived, parameters not transcribed | 308 |
| `:TRIGger:INTerval:COUPling` | `:TRIGger:INTerval:COUPling?` | see p.308 | documented; TOC/body-heading derived, parameters not transcribed | 308 |
| `:TRIGger:INTerval:HLDEVent` | `:TRIGger:INTerval:HLDEVent?` | see p.308 | documented; TOC/body-heading derived, parameters not transcribed | 308 |
| `:TRIGger:INTerval:HLDTime` | `:TRIGger:INTerval:HLDTime?` | see p.309 | documented; TOC/body-heading derived, parameters not transcribed | 309 |
| `:TRIGger:INTerval:HOLDoff` | `:TRIGger:INTerval:HOLDoff?` | see p.309 | documented; TOC/body-heading derived, parameters not transcribed | 309 |
| `:TRIGger:INTerval:HSTart` | `:TRIGger:INTerval:HSTart?` | see p.310 | documented; TOC/body-heading derived, parameters not transcribed | 310 |
| `:TRIGger:INTerval:LEVel` | `:TRIGger:INTerval:LEVel?` | see p.310 | documented; TOC/body-heading derived, parameters not transcribed | 310 |
| `:TRIGger:INTerval:LIMit` | `:TRIGger:INTerval:LIMit?` | see p.311 | documented; TOC/body-heading derived, parameters not transcribed | 311 |
| `:TRIGger:INTerval:NREJect` | `:TRIGger:INTerval:NREJect?` | see p.312 | documented; TOC/body-heading derived, parameters not transcribed | 312 |
| `:TRIGger:INTerval:SLOPe` | `:TRIGger:INTerval:SLOPe?` | see p.312 | documented; TOC/body-heading derived, parameters not transcribed | 312 |
| `:TRIGger:INTerval:SOURce` | `:TRIGger:INTerval:SOURce?` | see p.312 | documented; TOC/body-heading derived, parameters not transcribed | 312 |
| `:TRIGger:INTerval:TLOWer` | `:TRIGger:INTerval:TLOWer?` | see p.313 | documented; TOC/body-heading derived, parameters not transcribed | 313 |
| `:TRIGger:INTerval:TUPPer` | `:TRIGger:INTerval:TUPPer?` | see p.311 | documented; TOC/body-heading derived, parameters not transcribed | 311 |
| `:TRIGger:LIN` | `:TRIGger:LIN?` | see p.385 | documented; TOC/body-heading derived, parameters not transcribed | 385 |
| `:TRIGger:LIN:BAUD` | `:TRIGger:LIN:BAUD?` | see p.385 | documented; TOC/body-heading derived, parameters not transcribed | 385 |
| `:TRIGger:LIN:CONDition` | `:TRIGger:LIN:CONDition?` | see p.385 | documented; TOC/body-heading derived, parameters not transcribed | 385 |
| `:TRIGger:LIN:DAT2` | `:TRIGger:LIN:DAT2?` | see p.386 | documented; TOC/body-heading derived, parameters not transcribed | 386 |
| `:TRIGger:LIN:DATA` | `:TRIGger:LIN:DATA?` | see p.386 | documented; TOC/body-heading derived, parameters not transcribed | 386 |
| `:TRIGger:LIN:ERRor:CHECksum` | `:TRIGger:LIN:ERRor:CHECksum?` | see p.387 | documented; TOC/body-heading derived, parameters not transcribed | 387 |
| `:TRIGger:LIN:ERRor:DLENgth` | `:TRIGger:LIN:ERRor:DLENgth?` | see p.387 | documented; TOC/body-heading derived, parameters not transcribed | 387 |
| `:TRIGger:LIN:ERRor:ID` | `:TRIGger:LIN:ERRor:ID?` | see p.388 | documented; TOC/body-heading derived, parameters not transcribed | 388 |
| `:TRIGger:LIN:ERRor:PARity` | `:TRIGger:LIN:ERRor:PARity?` | see p.388 | documented; TOC/body-heading derived, parameters not transcribed | 388 |
| `:TRIGger:LIN:ERRor:SYNC` | `:TRIGger:LIN:ERRor:SYNC?` | see p.389 | documented; TOC/body-heading derived, parameters not transcribed | 389 |
| `:TRIGger:LIN:ID` | `:TRIGger:LIN:ID?` | see p.389 | documented; TOC/body-heading derived, parameters not transcribed | 389 |
| `:TRIGger:LIN:SOURce` | `:TRIGger:LIN:SOURce?` | see p.390 | documented; TOC/body-heading derived, parameters not transcribed | 390 |
| `:TRIGger:LIN:STANdard` | `:TRIGger:LIN:STANdard?` | see p.390 | documented; TOC/body-heading derived, parameters not transcribed | 390 |
| `:TRIGger:LIN:Source` | `:TRIGger:LIN:Source?` | see p.390 | documented; TOC/body-heading derived, parameters not transcribed | 390 |
| `:TRIGger:LIN:THReshold` | `:TRIGger:LIN:THReshold?` | see p.390 | documented; TOC/body-heading derived, parameters not transcribed | 390 |
| `:TRIGger:NEDGe` | `:TRIGger:NEDGe?` | see p.345 | documented; TOC/body-heading derived, parameters not transcribed | 345 |
| `:TRIGger:NEDGe:EDGE` | `:TRIGger:NEDGe:EDGE?` | see p.346 | documented; TOC/body-heading derived, parameters not transcribed | 346 |
| `:TRIGger:NEDGe:HLDEVent` | `:TRIGger:NEDGe:HLDEVent?` | see p.348 | documented; TOC/body-heading derived, parameters not transcribed | 348 |
| `:TRIGger:NEDGe:HLDEvent` | `:TRIGger:NEDGe:HLDEvent?` | see p.349 | documented; TOC/body-heading derived, parameters not transcribed | 349 |
| `:TRIGger:NEDGe:HLDTime` | `:TRIGger:NEDGe:HLDTime?` | see p.348 | documented; TOC/body-heading derived, parameters not transcribed | 348 |
| `:TRIGger:NEDGe:HOLDoff` | `:TRIGger:NEDGe:HOLDoff?` | see p.347 | documented; TOC/body-heading derived, parameters not transcribed | 347 |
| `:TRIGger:NEDGe:HSTart` | `:TRIGger:NEDGe:HSTart?` | see p.348 | documented; TOC/body-heading derived, parameters not transcribed | 348 |
| `:TRIGger:NEDGe:IDLE` | `:TRIGger:NEDGe:IDLE?` | see p.346 | documented; TOC/body-heading derived, parameters not transcribed | 346 |
| `:TRIGger:NEDGe:LEVel` | `:TRIGger:NEDGe:LEVel?` | see p.347 | documented; TOC/body-heading derived, parameters not transcribed | 347 |
| `:TRIGger:NEDGe:NREJect` | `:TRIGger:NEDGe:NREJect?` | see p.349 | documented; TOC/body-heading derived, parameters not transcribed | 349 |
| `:TRIGger:NEDGe:SLOPe` | `:TRIGger:NEDGe:SLOPe?` | see p.345 | documented; TOC/body-heading derived, parameters not transcribed | 345 |
| `:TRIGger:NEDGe:SOURce` | `:TRIGger:NEDGe:SOURce?` | see p.345 | documented; TOC/body-heading derived, parameters not transcribed | 345 |
| `:TRIGger:PATTern` | `:TRIGger:PATTern?` | see p.329 | documented; TOC/body-heading derived, parameters not transcribed | 329 |
| `:TRIGger:PATTern:HLDEVent` | `:TRIGger:PATTern:HLDEVent?` | see p.329 | documented; TOC/body-heading derived, parameters not transcribed | 329 |
| `:TRIGger:PATTern:HLDTime` | `:TRIGger:PATTern:HLDTime?` | see p.329 | documented; TOC/body-heading derived, parameters not transcribed | 329 |
| `:TRIGger:PATTern:HOLDoff` | `:TRIGger:PATTern:HOLDoff?` | see p.330 | documented; TOC/body-heading derived, parameters not transcribed | 330 |
| `:TRIGger:PATTern:HSTart` | `:TRIGger:PATTern:HSTart?` | see p.330 | documented; TOC/body-heading derived, parameters not transcribed | 330 |
| `:TRIGger:PATTern:INPut` | `:TRIGger:PATTern:INPut?` | see p.331 | documented; TOC/body-heading derived, parameters not transcribed | 331 |
| `:TRIGger:PATTern:LEVel` | `:TRIGger:PATTern:LEVel?` | see p.331 | documented; TOC/body-heading derived, parameters not transcribed | 331 |
| `:TRIGger:PATTern:LIMit` | `:TRIGger:PATTern:LIMit?` | see p.332 | documented; TOC/body-heading derived, parameters not transcribed | 332 |
| `:TRIGger:PATTern:LOGic` | `:TRIGger:PATTern:LOGic?` | see p.333 | documented; TOC/body-heading derived, parameters not transcribed | 333 |
| `:TRIGger:PATTern:TLOWer` | `:TRIGger:PATTern:TLOWer?` | see p.333 | documented; TOC/body-heading derived, parameters not transcribed | 333 |
| `:TRIGger:PATTern:TUPPer` | `:TRIGger:PATTern:TUPPer?` | see p.333 | documented; TOC/body-heading derived, parameters not transcribed | 333 |
| `:TRIGger:PULSe` | `:TRIGger:PULSe?` | see p.288 | documented; TOC/body-heading derived, parameters not transcribed | 288 |
| `:TRIGger:PULSe:COUPling` | `:TRIGger:PULSe:COUPling?` | see p.288 | documented; TOC/body-heading derived, parameters not transcribed | 288 |
| `:TRIGger:PULSe:HLDEVent` | `:TRIGger:PULSe:HLDEVent?` | see p.288 | documented; TOC/body-heading derived, parameters not transcribed | 288 |
| `:TRIGger:PULSe:HLDTime` | `:TRIGger:PULSe:HLDTime?` | see p.289 | documented; TOC/body-heading derived, parameters not transcribed | 289 |
| `:TRIGger:PULSe:HOLDoff` | `:TRIGger:PULSe:HOLDoff?` | see p.289 | documented; TOC/body-heading derived, parameters not transcribed | 289 |
| `:TRIGger:PULSe:HSTart` | `:TRIGger:PULSe:HSTart?` | see p.290 | documented; TOC/body-heading derived, parameters not transcribed | 290 |
| `:TRIGger:PULSe:LEVel` | `:TRIGger:PULSe:LEVel?` | see p.290 | documented; TOC/body-heading derived, parameters not transcribed | 290 |
| `:TRIGger:PULSe:LIMit` | `:TRIGger:PULSe:LIMit?` | see p.291 | documented; TOC/body-heading derived, parameters not transcribed | 291 |
| `:TRIGger:PULSe:NREJect` | `:TRIGger:PULSe:NREJect?` | see p.292 | documented; TOC/body-heading derived, parameters not transcribed | 292 |
| `:TRIGger:PULSe:POLarity` | `:TRIGger:PULSe:POLarity?` | see p.292 | documented; TOC/body-heading derived, parameters not transcribed | 292 |
| `:TRIGger:PULSe:SOURce` | `:TRIGger:PULSe:SOURce?` | see p.292 | documented; TOC/body-heading derived, parameters not transcribed | 292 |
| `:TRIGger:PULSe:TLOWer` | `:TRIGger:PULSe:TLOWer?` | see p.293 | documented; TOC/body-heading derived, parameters not transcribed | 293 |
| `:TRIGger:PULSe:TUPPer` | `:TRIGger:PULSe:TUPPer?` | see p.291 | documented; TOC/body-heading derived, parameters not transcribed | 291 |
| `:TRIGger:QUALified` | `:TRIGger:QUALified?` | see p.335 | documented; TOC/body-heading derived, parameters not transcribed | 335 |
| `:TRIGger:QUALified:ELEVel` | `:TRIGger:QUALified:ELEVel?` | see p.335 | documented; TOC/body-heading derived, parameters not transcribed | 335 |
| `:TRIGger:QUALified:ELVel` | `:TRIGger:QUALified:ELVel?` | see p.335 | documented; TOC/body-heading derived, parameters not transcribed | 335 |
| `:TRIGger:QUALified:ESLope` | `:TRIGger:QUALified:ESLope?` | see p.335 | documented; TOC/body-heading derived, parameters not transcribed | 335 |
| `:TRIGger:QUALified:ESource` | `:TRIGger:QUALified:ESource?` | see p.336 | documented; TOC/body-heading derived, parameters not transcribed | 336 |
| `:TRIGger:QUALified:LIMit` | `:TRIGger:QUALified:LIMit?` | see p.336 | documented; TOC/body-heading derived, parameters not transcribed | 336 |
| `:TRIGger:QUALified:QLEVel` | `:TRIGger:QUALified:QLEVel?` | see p.337 | documented; TOC/body-heading derived, parameters not transcribed | 337 |
| `:TRIGger:QUALified:QSource` | `:TRIGger:QUALified:QSource?` | see p.337 | documented; TOC/body-heading derived, parameters not transcribed | 337 |
| `:TRIGger:QUALified:TLOWer` | `:TRIGger:QUALified:TLOWer?` | see p.338 | documented; TOC/body-heading derived, parameters not transcribed | 338 |
| `:TRIGger:QUALified:TUPPer` | `:TRIGger:QUALified:TUPPer?` | see p.337 | documented; TOC/body-heading derived, parameters not transcribed | 337 |
| `:TRIGger:QUALified:TYPE` | `:TRIGger:QUALified:TYPE?` | see p.339 | documented; TOC/body-heading derived, parameters not transcribed | 339 |
| `:TRIGger:RUNT` | `:TRIGger:RUNT?` | see p.321 | documented; TOC/body-heading derived, parameters not transcribed | 321 |
| `:TRIGger:RUNT:COUPling` | `:TRIGger:RUNT:COUPling?` | see p.321 | documented; TOC/body-heading derived, parameters not transcribed | 321 |
| `:TRIGger:RUNT:HLDEVent` | `:TRIGger:RUNT:HLDEVent?` | see p.321 | documented; TOC/body-heading derived, parameters not transcribed | 321 |
| `:TRIGger:RUNT:HLDTime` | `:TRIGger:RUNT:HLDTime?` | see p.322 | documented; TOC/body-heading derived, parameters not transcribed | 322 |
| `:TRIGger:RUNT:HLEVel` | `:TRIGger:RUNT:HLEVel?` | see p.322 | documented; TOC/body-heading derived, parameters not transcribed | 322 |
| `:TRIGger:RUNT:HOLDoff` | `:TRIGger:RUNT:HOLDoff?` | see p.323 | documented; TOC/body-heading derived, parameters not transcribed | 323 |
| `:TRIGger:RUNT:HSTart` | `:TRIGger:RUNT:HSTart?` | see p.323 | documented; TOC/body-heading derived, parameters not transcribed | 323 |
| `:TRIGger:RUNT:LIMit` | `:TRIGger:RUNT:LIMit?` | see p.324 | documented; TOC/body-heading derived, parameters not transcribed | 324 |
| `:TRIGger:RUNT:LLEVel` | `:TRIGger:RUNT:LLEVel?` | see p.325 | documented; TOC/body-heading derived, parameters not transcribed | 325 |
| `:TRIGger:RUNT:NREJect` | `:TRIGger:RUNT:NREJect?` | see p.325 | documented; TOC/body-heading derived, parameters not transcribed | 325 |
| `:TRIGger:RUNT:POLarity` | `:TRIGger:RUNT:POLarity?` | see p.326 | documented; TOC/body-heading derived, parameters not transcribed | 326 |
| `:TRIGger:RUNT:SOURce` | `:TRIGger:RUNT:SOURce?` | see p.326 | documented; TOC/body-heading derived, parameters not transcribed | 326 |
| `:TRIGger:RUNT:TLOWer` | `:TRIGger:RUNT:TLOWer?` | see p.327 | documented; TOC/body-heading derived, parameters not transcribed | 327 |
| `:TRIGger:RUNT:TUPPer` | `:TRIGger:RUNT:TUPPer?` | see p.324 | documented; TOC/body-heading derived, parameters not transcribed | 324 |
| `:TRIGger:RUNt:HLDTime` | `:TRIGger:RUNt:HLDTime?` | see p.322 | documented; TOC/body-heading derived, parameters not transcribed | 322 |
| `:TRIGger:SENT:SOURce` | `:TRIGger:SENT:SOURce?` | see p.409 | documented; TOC/body-heading derived, parameters not transcribed | 409 |
| `:TRIGger:SENT:THReshold` | `:TRIGger:SENT:THReshold?` | see p.409 | documented; TOC/body-heading derived, parameters not transcribed | 409 |
| `:TRIGger:SHOL:TUPPer` | `:TRIGger:SHOL:TUPPer?` | see p.355 | documented; TOC/body-heading derived, parameters not transcribed | 355 |
| `:TRIGger:SHOLd` | `:TRIGger:SHOLd?` | see p.351 | documented; TOC/body-heading derived, parameters not transcribed | 351 |
| `:TRIGger:SHOLd:CSource` | `:TRIGger:SHOLd:CSource?` | see p.351 | documented; TOC/body-heading derived, parameters not transcribed | 351 |
| `:TRIGger:SHOLd:CTHReshold` | `:TRIGger:SHOLd:CTHReshold?` | see p.352 | documented; TOC/body-heading derived, parameters not transcribed | 352 |
| `:TRIGger:SHOLd:DSource` | `:TRIGger:SHOLd:DSource?` | see p.353 | documented; TOC/body-heading derived, parameters not transcribed | 353 |
| `:TRIGger:SHOLd:DTHReshold` | `:TRIGger:SHOLd:DTHReshold?` | see p.353 | documented; TOC/body-heading derived, parameters not transcribed | 353 |
| `:TRIGger:SHOLd:LEVel` | `:TRIGger:SHOLd:LEVel?` | see p.354 | documented; TOC/body-heading derived, parameters not transcribed | 354 |
| `:TRIGger:SHOLd:LIMit` | `:TRIGger:SHOLd:LIMit?` | see p.354 | documented; TOC/body-heading derived, parameters not transcribed | 354 |
| `:TRIGger:SHOLd:SLOPe` | `:TRIGger:SHOLd:SLOPe?` | see p.352 | documented; TOC/body-heading derived, parameters not transcribed | 352 |
| `:TRIGger:SHOLd:TLOWer` | `:TRIGger:SHOLd:TLOWer?` | see p.355 | documented; TOC/body-heading derived, parameters not transcribed | 355 |
| `:TRIGger:SHOLd:TUPPer` | `:TRIGger:SHOLd:TUPPer?` | see p.355 | documented; TOC/body-heading derived, parameters not transcribed | 355 |
| `:TRIGger:SHOLd:TYPE` | `:TRIGger:SHOLd:TYPE?` | see p.351 | documented; TOC/body-heading derived, parameters not transcribed | 351 |
| `:TRIGger:SLOPe` | `:TRIGger:SLOPe?` | see p.280 | documented; TOC/body-heading derived, parameters not transcribed | 280 |
| `:TRIGger:SLOPe:COUPling` | `:TRIGger:SLOPe:COUPling?` | see p.280 | documented; TOC/body-heading derived, parameters not transcribed | 280 |
| `:TRIGger:SLOPe:HLDEVent` | `:TRIGger:SLOPe:HLDEVent?` | see p.280 | documented; TOC/body-heading derived, parameters not transcribed | 280 |
| `:TRIGger:SLOPe:HLDTime` | `:TRIGger:SLOPe:HLDTime?` | see p.281 | documented; TOC/body-heading derived, parameters not transcribed | 281 |
| `:TRIGger:SLOPe:HLEVel` | `:TRIGger:SLOPe:HLEVel?` | see p.281 | documented; TOC/body-heading derived, parameters not transcribed | 281 |
| `:TRIGger:SLOPe:HOLDoff` | `:TRIGger:SLOPe:HOLDoff?` | see p.282 | documented; TOC/body-heading derived, parameters not transcribed | 282 |
| `:TRIGger:SLOPe:HSTart` | `:TRIGger:SLOPe:HSTart?` | see p.282 | documented; TOC/body-heading derived, parameters not transcribed | 282 |
| `:TRIGger:SLOPe:LIMit` | `:TRIGger:SLOPe:LIMit?` | see p.283 | documented; TOC/body-heading derived, parameters not transcribed | 283 |
| `:TRIGger:SLOPe:LLEVel` | `:TRIGger:SLOPe:LLEVel?` | see p.284 | documented; TOC/body-heading derived, parameters not transcribed | 284 |
| `:TRIGger:SLOPe:NREJect` | `:TRIGger:SLOPe:NREJect?` | see p.284 | documented; TOC/body-heading derived, parameters not transcribed | 284 |
| `:TRIGger:SLOPe:SLOPe` | `:TRIGger:SLOPe:SLOPe?` | see p.285 | documented; TOC/body-heading derived, parameters not transcribed | 285 |
| `:TRIGger:SLOPe:SOURce` | `:TRIGger:SLOPe:SOURce?` | see p.285 | documented; TOC/body-heading derived, parameters not transcribed | 285 |
| `:TRIGger:SLOPe:TLOWer` | `:TRIGger:SLOPe:TLOWer?` | see p.286 | documented; TOC/body-heading derived, parameters not transcribed | 286 |
| `:TRIGger:SLOPe:TUPPer` | `:TRIGger:SLOPe:TUPPer?` | see p.283 | documented; TOC/body-heading derived, parameters not transcribed | 283 |
| `:TRIGger:SPI` | `:TRIGger:SPI?` | see p.363 | documented; TOC/body-heading derived, parameters not transcribed | 363 |
| `:TRIGger:SPI:BITorder` | `:TRIGger:SPI:BITorder?` | see p.363 | documented; TOC/body-heading derived, parameters not transcribed | 363 |
| `:TRIGger:SPI:CLKSource` | `:TRIGger:SPI:CLKSource?` | see p.363 | documented; TOC/body-heading derived, parameters not transcribed | 363 |
| `:TRIGger:SPI:CLKThreshold` | `:TRIGger:SPI:CLKThreshold?` | see p.364 | documented; TOC/body-heading derived, parameters not transcribed | 364 |
| `:TRIGger:SPI:CSSource` | `:TRIGger:SPI:CSSource?` | see p.364 | documented; TOC/body-heading derived, parameters not transcribed | 364 |
| `:TRIGger:SPI:CSTYpe` | `:TRIGger:SPI:CSTYpe?` | see p.366 | documented; TOC/body-heading derived, parameters not transcribed | 366 |
| `:TRIGger:SPI:CSThreshold` | `:TRIGger:SPI:CSThreshold?` | see p.365 | documented; TOC/body-heading derived, parameters not transcribed | 365 |
| `:TRIGger:SPI:DATA` | `:TRIGger:SPI:DATA?` | see p.366 | documented; TOC/body-heading derived, parameters not transcribed | 366 |
| `:TRIGger:SPI:DLENgth` | `:TRIGger:SPI:DLENgth?` | see p.367 | documented; TOC/body-heading derived, parameters not transcribed | 367 |
| `:TRIGger:SPI:LATC` | `:TRIGger:SPI:LATC?` | see p.367 | documented; TOC/body-heading derived, parameters not transcribed | 367 |
| `:TRIGger:SPI:LATChedge` | `:TRIGger:SPI:LATChedge?` | see p.367 | documented; TOC/body-heading derived, parameters not transcribed | 367 |
| `:TRIGger:SPI:MISOSource` | `:TRIGger:SPI:MISOSource?` | see p.367 | documented; TOC/body-heading derived, parameters not transcribed | 367 |
| `:TRIGger:SPI:MISOThreshold` | `:TRIGger:SPI:MISOThreshold?` | see p.368 | documented; TOC/body-heading derived, parameters not transcribed | 368 |
| `:TRIGger:SPI:MOSISource` | `:TRIGger:SPI:MOSISource?` | see p.369 | documented; TOC/body-heading derived, parameters not transcribed | 369 |
| `:TRIGger:SPI:MOSIThreshold` | `:TRIGger:SPI:MOSIThreshold?` | see p.369 | documented; TOC/body-heading derived, parameters not transcribed | 369 |
| `:TRIGger:SPI:NCSSource` | `:TRIGger:SPI:NCSSource?` | see p.370 | documented; TOC/body-heading derived, parameters not transcribed | 370 |
| `:TRIGger:SPI:NCSThreshold` | `:TRIGger:SPI:NCSThreshold?` | see p.370 | documented; TOC/body-heading derived, parameters not transcribed | 370 |
| `:TRIGger:SPI:TTYPe` | `:TRIGger:SPI:TTYPe?` | see p.371 | documented; TOC/body-heading derived, parameters not transcribed | 371 |
| `:TRIGger:STATus` | `:TRIGger:STATus?` | see p.272 | documented; TOC/body-heading derived, parameters not transcribed | 272 |
| `:TRIGger:STOP` | `:TRIGger:STOP?` | see p.272 | documented; TOC/body-heading derived, parameters not transcribed | 272 |
| `:TRIGger:UART` | `:TRIGger:UART?` | see p.372 | documented; TOC/body-heading derived, parameters not transcribed | 372 |
| `:TRIGger:UART:BAUD` | `:TRIGger:UART:BAUD?` | see p.372 | documented; TOC/body-heading derived, parameters not transcribed | 372 |
| `:TRIGger:UART:BITorder` | `:TRIGger:UART:BITorder?` | see p.372 | documented; TOC/body-heading derived, parameters not transcribed | 372 |
| `:TRIGger:UART:CONDition` | `:TRIGger:UART:CONDition?` | see p.373 | documented; TOC/body-heading derived, parameters not transcribed | 373 |
| `:TRIGger:UART:DATA` | `:TRIGger:UART:DATA?` | see p.373 | documented; TOC/body-heading derived, parameters not transcribed | 373 |
| `:TRIGger:UART:DLENgth` | `:TRIGger:UART:DLENgth?` | see p.374 | documented; TOC/body-heading derived, parameters not transcribed | 374 |
| `:TRIGger:UART:IDLE` | `:TRIGger:UART:IDLE?` | see p.374 | documented; TOC/body-heading derived, parameters not transcribed | 374 |
| `:TRIGger:UART:LIMit` | `:TRIGger:UART:LIMit?` | see p.375 | documented; TOC/body-heading derived, parameters not transcribed | 375 |
| `:TRIGger:UART:PARity` | `:TRIGger:UART:PARity?` | see p.375 | documented; TOC/body-heading derived, parameters not transcribed | 375 |
| `:TRIGger:UART:RXSource` | `:TRIGger:UART:RXSource?` | see p.376 | documented; TOC/body-heading derived, parameters not transcribed | 376 |
| `:TRIGger:UART:RXTHreshold` | `:TRIGger:UART:RXTHreshold?` | see p.376 | documented; TOC/body-heading derived, parameters not transcribed | 376 |
| `:TRIGger:UART:STOP` | `:TRIGger:UART:STOP?` | see p.377 | documented; TOC/body-heading derived, parameters not transcribed | 377 |
| `:TRIGger:UART:TTYPe` | `:TRIGger:UART:TTYPe?` | see p.377 | documented; TOC/body-heading derived, parameters not transcribed | 377 |
| `:TRIGger:UART:TXSource` | `:TRIGger:UART:TXSource?` | see p.378 | documented; TOC/body-heading derived, parameters not transcribed | 378 |
| `:TRIGger:UART:TXTHreshold` | `:TRIGger:UART:TXTHreshold?` | see p.378 | documented; TOC/body-heading derived, parameters not transcribed | 378 |
| `:TRIGger:VIDeo` | `:TRIGger:VIDeo?` | see p.295 | documented; TOC/body-heading derived, parameters not transcribed | 295 |
| `:TRIGger:VIDeo:FCNT` | `:TRIGger:VIDeo:FCNT?` | see p.295 | documented; TOC/body-heading derived, parameters not transcribed | 295 |
| `:TRIGger:VIDeo:FIELd` | `:TRIGger:VIDeo:FIELd?` | see p.295 | documented; TOC/body-heading derived, parameters not transcribed | 295 |
| `:TRIGger:VIDeo:FRATe` | `:TRIGger:VIDeo:FRATe?` | see p.296 | documented; TOC/body-heading derived, parameters not transcribed | 296 |
| `:TRIGger:VIDeo:INTerlace` | `:TRIGger:VIDeo:INTerlace?` | see p.296 | documented; TOC/body-heading derived, parameters not transcribed | 296 |
| `:TRIGger:VIDeo:LCNT` | `:TRIGger:VIDeo:LCNT?` | see p.296 | documented; TOC/body-heading derived, parameters not transcribed | 296 |
| `:TRIGger:VIDeo:LEVel` | `:TRIGger:VIDeo:LEVel?` | see p.297 | documented; TOC/body-heading derived, parameters not transcribed | 297 |
| `:TRIGger:VIDeo:LINE` | `:TRIGger:VIDeo:LINE?` | see p.298 | documented; TOC/body-heading derived, parameters not transcribed | 298 |
| `:TRIGger:VIDeo:SOURce` | `:TRIGger:VIDeo:SOURce?` | see p.298 | documented; TOC/body-heading derived, parameters not transcribed | 298 |
| `:TRIGger:VIDeo:STANdard` | `:TRIGger:VIDeo:STANdard?` | see p.299 | documented; TOC/body-heading derived, parameters not transcribed | 299 |
| `:TRIGger:VIDeo:SYNC` | `:TRIGger:VIDeo:SYNC?` | see p.295 | documented; TOC/body-heading derived, parameters not transcribed | 295 |
| `:TRIGger:WIND:HLDTime` | `:TRIGger:WIND:HLDTime?` | see p.303 | documented; TOC/body-heading derived, parameters not transcribed | 303 |
| `:TRIGger:WIND:HOLDoff` | `:TRIGger:WIND:HOLDoff?` | see p.304 | documented; TOC/body-heading derived, parameters not transcribed | 304 |
| `:TRIGger:WINDow` | `:TRIGger:WINDow?` | see p.301 | documented; TOC/body-heading derived, parameters not transcribed | 301 |
| `:TRIGger:WINDow:CLEVel` | `:TRIGger:WINDow:CLEVel?` | see p.301 | documented; TOC/body-heading derived, parameters not transcribed | 301 |
| `:TRIGger:WINDow:COUPling` | `:TRIGger:WINDow:COUPling?` | see p.301 | documented; TOC/body-heading derived, parameters not transcribed | 301 |
| `:TRIGger:WINDow:DLEVel` | `:TRIGger:WINDow:DLEVel?` | see p.302 | documented; TOC/body-heading derived, parameters not transcribed | 302 |
| `:TRIGger:WINDow:HLDEVent` | `:TRIGger:WINDow:HLDEVent?` | see p.303 | documented; TOC/body-heading derived, parameters not transcribed | 303 |
| `:TRIGger:WINDow:HLDTime` | `:TRIGger:WINDow:HLDTime?` | see p.303 | documented; TOC/body-heading derived, parameters not transcribed | 303 |
| `:TRIGger:WINDow:HLEVel` | `:TRIGger:WINDow:HLEVel?` | see p.304 | documented; TOC/body-heading derived, parameters not transcribed | 304 |
| `:TRIGger:WINDow:HOLDoff` | `:TRIGger:WINDow:HOLDoff?` | see p.304 | documented; TOC/body-heading derived, parameters not transcribed | 304 |
| `:TRIGger:WINDow:HSTart` | `:TRIGger:WINDow:HSTart?` | see p.305 | documented; TOC/body-heading derived, parameters not transcribed | 305 |
| `:TRIGger:WINDow:LLEVel` | `:TRIGger:WINDow:LLEVel?` | see p.305 | documented; TOC/body-heading derived, parameters not transcribed | 305 |
| `:TRIGger:WINDow:NREJect` | `:TRIGger:WINDow:NREJect?` | see p.306 | documented; TOC/body-heading derived, parameters not transcribed | 306 |
| `:TRIGger:WINDow:SOURce` | `:TRIGger:WINDow:SOURce?` | see p.307 | documented; TOC/body-heading derived, parameters not transcribed | 307 |
| `:TRIGger:WINDow:TYPE` | `:TRIGger:WINDow:TYPE?` | see p.307 | documented; TOC/body-heading derived, parameters not transcribed | 307 |
| `:WAVeform:DATA` | `:WAVeform:DATA?` | see p.418 | documented; TOC/body-heading derived, parameters not transcribed | 418 |
| `:WAVeform:MAXPoint` | `:WAVeform:MAXPoint?` | see p.413 | documented; TOC/body-heading derived, parameters not transcribed | 413 |
| `:WAVeform:PRE` | `:WAVeform:PRE?` | see p.418 | documented; TOC/body-heading derived, parameters not transcribed | 418 |
| `:WAVeform:PREamble` | `:WAVeform:PREamble?` | see p.412 | documented; TOC/body-heading derived, parameters not transcribed | 412 |
| `:WAVeform:SEQuence` | `:WAVeform:SEQuence?` | see p.422 | documented; TOC/body-heading derived, parameters not transcribed | 422 |
