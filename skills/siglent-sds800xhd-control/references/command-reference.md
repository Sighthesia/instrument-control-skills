# Command Reference (Fallback Index)

这是一份**兜底索引**：只有当按目标加载的任务参考文档和脚本仍无法回答某个命令问题时才加载它；日常应按 `SKILL.md` 的“Progressive Query Reference”优先读取对应任务页，不要一开始就全表通读。
本文范围仅限本 Skill 内（`SKILL.md`、`references/*.md`、`scripts/*.py`）**已经记录过**的命令，不复制厂商手册，也不补全手册内容；权威完整命令集是厂商编程手册 `SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`（仓库内 `ref/`）。
表中没有出现的任何命令，必须先对照手册核实并标注为 `documented` 后才能使用；`SKILL.md` 的安全规则（禁止 `ARM`、`Ready -> Stop`、Stop 后冻结命令集、二进制完整性）始终优先于本表。
“Source”列给出记录该命令的文件；括号内页码只在原文明确给出时才有；原文未给出页码的条目在 Notes 中注明“手册未给出独立页码”或“需对手册核实”，使用前应回到手册核对。

## IEEE 488.2 common commands

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `*IDN?` | query | — | 返回厂商、型号、序列号、固件；任何型号相关命令之前必须先执行并保存结果。手册印刷 pp. 13-14；discovery 发送 `*IDN?\n`。 | signal-discovery-and-measurement.md (manual pp. 13-14)<br>connection-and-storage.md<br>SKILL.md<br>scripts/discover_scope.py<br>scripts/scope_protocol.py |
| `*OPC?` | query | — | 挂起操作完成时返回 `1`；不能证明发生过触发。等待设置写入生效时可作为同步点。手册印刷 pp. 13-14。 | signal-discovery-and-measurement.md (manual pp. 13-14) |

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
| `:ACQuire:POINts?` / `ACQ:POIN?` | query | — | 当前记录点数（`scope_record_points`）；用于与描述符点数比对判断 `COMPLETE`/`INCOMPLETE`。手册印刷 pp. 21-23。 | signal-discovery-and-measurement.md (manual pp. 21-23)<br>scripts/scope_protocol.py |
| `:ACQuire:SRATe?` | query | — | 当前采样率（Sa/s）。**没有离散档位表**：手册只说“超过可设定值会自动匹配”，因此不能预先枚举，必须在设备上读取。手册印刷 pp. 21-23。 | signal-discovery-and-measurement.md (manual pp. 21-23)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `:ACQuire:SRATe` / `ACQ:SRAT` | set | `<rate>`，浮点 NR3，如 `5.00E9`；手册未给离散档位表，只说明“超过可设定值会自动匹配” | **仅在 `:ACQuire:MMANagement FSRate` 固定采样率模式下有效**；写入后必须回读，实测值可能与请求值不同；改变采集上下文，只能在 `TRMD SINGLE` 之前写。Roll 模式下是否可写未见手册说明，属 `UNVERIFIED`。手册印刷 p. 22。证据等级 `documented`。 | signal-discovery-and-measurement.md (manual pp. 22-23) |
| `:ACQuire:MMANagement?` | query | 返回 `AUTO`、`FSRate`、`FMDepth` | 存储管理方式；决定采样率与存储深度哪一个由用户控制。写采样率或深度前应先确认此模式。手册印刷 p. 18。 | signal-discovery-and-measurement.md (manual p. 18) |
| `:ACQuire:MMANagement` / `ACQ:MMAN` | set | `AUTO`、`FSRate`、`FMDepth` | `AUTO` 保持最大采样率并按时基推两者；`FSRate` 固定采样率、深度随时基；`FMDepth` 固定深度、采样率随时基。改变采集上下文，写入后回读。手册印刷 p. 18。 | signal-discovery-and-measurement.md (manual p. 18) |
| `:ACQuire:MODE` | set/query | `YT`、`XY`、`ROLL` | 采集模式。`ROLL` 为滚动流式显示：**`SAST?` 只报 `Roll` 不报 `Ready`**，因此不能用于本 Skill 的 `Ready -> Stop` 单次采集；只在 50 ms/div 及更慢时可用，水平延迟无效，运行中不支持 Zoom，并限制存储深度。详见 `signal-discovery-and-measurement.md` 的 Roll Mode 一节。手册印刷 pp. 18-19 + 用户手册印刷 p. 44。 | signal-discovery-and-measurement.md (manual pp. 18-19)<br>scripts/scope_protocol.py |
| `:ACQuire:AMODe` | set/query | `FAST`、`SLOW` | 快采/慢采，影响波形捕获率。手册印刷 p. 17。 | signal-discovery-and-measurement.md (manual p. 17) |
| `:ACQuire:TYPE` | set/query | `NORMal`、`PEAK`、`AVERage[,<times>]`、`ERES[,<bits>]`；`<times>` = 4..8192 的 2 次幂，`<bits>` = 0.5..4.0 步进 0.5 | 采集方式；**分段采集开启时平均/ERES 不可用**；平均与 ERES 会限制存储深度。手册印刷 p. 23。 | signal-discovery-and-measurement.md (manual p. 23) |
| `:ACQuire:INTerpolation` | set/query | `ON`（Sinc）、`OFF`（线性） | 内插方式。手册印刷 pp. 17-18。 | signal-discovery-and-measurement.md (manual pp. 17-18) |
| `:ACQuire:SEQuence` | set/query | `ON`、`OFF` | 分段采集开关；随后用 `:WAVeform:SEQuence?` 读取帧。手册印刷 p. 22。 | signal-discovery-and-measurement.md (manual p. 22) |
| `:ACQuire:SEQuence:COUNt` | set/query | 整型 NR1；手册写“最大分段数可能受**存储深度**限制”，未提时基 | 分段数；具体范围因机型/时基而异，回读确认。手册印刷 p. 22。 | signal-discovery-and-measurement.md (manual p. 22) |
| `:ACQuire:RESolution` | set/query | `8Bits`、`10Bits`（手册标注为 SDS2000X Plus） | ADC 分辨率；SDS800X HD 是否支持需按机型确认，不得假设。手册印刷 p. 21。 | signal-discovery-and-measurement.md (manual p. 21) |
| `:ACQuire:CSWeep` | event | — | 清除扫描并重新开始采集，等价于前面板 Clear Sweeps。手册印刷 p. 17。 | signal-discovery-and-measurement.md (manual p. 17) |

| `:ACQuire:MDEPth?` / `ACQ:MDEP?` | query | — | 当前存储深度。SDS800X HD 手册档位为：单通道 `{10k,100k,1M,10M,100M}`、双通道 `{10k,100k,1M,10M,50M}`、四通道 `{10k,100k,1M,10M,25M}`。手册印刷 pp. 19-20。 | signal-discovery-and-measurement.md (manual pp. 19-20)<br>scripts/scope_protocol.py |
| `ACQ:MDEP` | set | 手册全档位见上；`configure_memory_depth` 目前只接受 `100M`、`50M`、`25M` 三个便捷值（默认按通道数 1/2/3/4 取 100M/50M/25M/25M） | 必须在 `TRMD SINGLE` 之前写入；写入后回读校验；不可变读取期间禁止。脚本未实现的更小档位（10k/100k/1M/10M）需直接发送命令并自行回读。 | signal-discovery-and-measurement.md<br>scripts/scope_protocol.py |
| `:TIMebase:SCALe?` / `TIM:SCAL?` / `TDIV?` | query | — | 主时基（s/div）；左对齐触发策略先读取它计算 `Delay`，写入后再回读校验。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `:TIMebase:DELay?` / `TIM:DEL?` / `TRDL?` | query | — | 水平延迟（s）；`TRDL?` 为旧式字段，延迟符号约定不要与新式 `TIMebase:DELay?` 混用。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `TIM:DEL` | set | 秒，`(5 - margin_div) * Timebase`（`margin_div` 取值 (0, 5]） | 触发跟随窗口策略的显式可选项；只在 `TRMD SINGLE` 之前写，写完回读；与 `--existing-stopped` 不兼容。 | signal-discovery-and-measurement.md<br>SKILL.md<br>scripts/scope_protocol.py |
| `:TIMebase:REFerence:POSition?` / `TIM:REF:POS?` | query | 0..100（百分比） | 延迟固定展开时的水平参考位置；写入后回读。手册印刷 pp. 239-242。 | signal-discovery-and-measurement.md (manual pp. 239-242)<br>scripts/scope_protocol.py |
| `TIM:REF:POS` | set | 整数 0..100 | 可选写入；`capture_scope.py --reference-position` 暴露；仅在采集前使用。 | signal-discovery-and-measurement.md<br>SKILL.md<br>scripts/scope_protocol.py<br>scripts/capture_scope.py |
| `TDIV` | set | — | 时基写入；Stop 后禁止（列入 `FORBIDDEN_AFTER_STOP`），会改变采集上下文。 | scripts/scope_protocol.py |

## Trigger

| Command | Type | Parameters / range | Notes | Source |
|---|---|---|---|---|
| `TRSE` | set | `EDGE,SR,C1,HT,OFF`（handover 记录的唯一形式） | 设置边沿触发源/类型；必须在 `TRMD SINGLE` 之前；Stop 后禁止。 | programming-guide.md<br>scripts/scope_protocol.py |
| `C1:TRSL` | set | `POS` | 边沿斜率；必须在 `TRMD SINGLE` 之前；Stop 后禁止。 | programming-guide.md<br>scripts/scope_protocol.py |
| `C1:TRLV` | set | 电压值，示例 `2.5`（V） | 边沿触发电平；必须在 `TRMD SINGLE` 之前；Stop 后禁止。 | programming-guide.md<br>scripts/scope_protocol.py |
| `:TRIGger:EDGE:LEVel?` | query | — | 边沿触发阈值（V），只读快照用。手册未给出独立页码。 | signal-discovery-and-measurement.md |

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
| `:PRINt?` | query | `PNG`；或 `BMP[,NORMal\|INVerted]` | 返回图像字节流，不是 ASCII 标量；**固件 `4.8.12.1.1.6.5` 实测为裸 PNG，无 IEEE 488.2 头**，以 `LF` 结尾，`query_block()`/`read_ieee_block()` 会合法地失败。须按 `IEND` + `LF` 有界读取并保留 SHA-256，禁止 `readline()`；当前 `scripts/` 无此 reader 实现。`PRINt?` **无法隐藏屏上菜单**，需要无菜单截图时用 `:SAVe:IMAGe ... ,MOFf`。手册印刷 p. 15；示例 pp. 494-495。 | screenshot-and-waveform.md (manual p. 15, pp. 494-495)<br>connection-and-storage.md |
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
| `:DECode:LIST<n>:RESult?` | query | `n` = 1、2 | 列表/总线 1 或 2 的完整 ASCII 解码表（逗号分隔字段、换行分隔记录、含表头）；事件分析首选；必须用保留全部行的 reader；先解析表头，不假设固定列。手册印刷 pp. 68-70。 | protocol-decode.md (manual pp. 68-70) |
| `:DECode:BUS<n>:RESult?` | query | `n` = 1、2 | 可见总线摘要（逗号分隔字段、分号分隔帧），事件多时可能不完整；仅作屏幕摘要核对。手册印刷 pp. 71-72。 | protocol-decode.md (manual pp. 71-72) |

协议专用解码设置（协议/源/阈值/速率等）只在手册印刷 pp. 73-148 提及，Skill 未记录具体命令，见“Coverage gaps”。

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
- **错误队列与状态寄存器**：手册未记录任何查询；本 Skill 也不提供。任何“读错误队列”的说法都必须在目标固件上实测确认，不得直接写进流程。
- **系统设置**：`SYSTem` 已记录 LAN、`NSTorage`（含 `DISConnect`）、`REMote`、`DATE?`/`TIME?`；`BUZZer`、`CLOCk`、`VNCPort`、`EDUMode`、`LANGuage`、`MENU`、`PON`、`SSAVer`、`TOUCh` 未记录（手册印刷 pp. 257-266）；`REBoot`、`SHUTdown`、`SELFCal` 属破坏性/耗时操作，刻意不提供。
- **通道/垂直写入**：已记录 `SCALe`、`OFFSet`、`SWITch`、`COUPling`、`PROBe`、`BWLimit`、`INVert`、`IMPedance`、`UNIT`、`SKEW`、`LABel`、`LABel:TEXT`、`VISible`、`CHANnel:REFerence`（手册印刷 pp. 24-30）。
- **数字通道与选件**：MSO 数字通道（`:DIGital:*`，选件）、`:WGEN:*`（外部 SAG1021I 发生器选件，不是本机内置）、`:METEr:*`（仅手持 SHS 系列）均不属于本机基础能力，刻意不收录。
- **时基/采集写入**：已记录 `ACQ:MDEP`、`ACQ:SRAT`、`ACQ:MMAN`、`ACQ:MODE`、`ACQ:TYPE`、`ACQ:SEQuence`、`TIM:DEL`、`TIM:REF:POS`、`TDIV`；`ACQ:AMODe`、`ACQ:INTerpolation`、`ACQ:CSWeep` 已列但未实现为脚本参数；数字通道、平均/ERES 与记录深度的交互只按手册记录，未实测。
- **采样率可取值集合**：两份手册都没有离散档位表，只有“超过可设定值自动匹配”的说明。Roll 模式下的采样率由 50 ms/div 下限与（未公开的）深度限制共同约束，只能现场读 `:ACQuire:MDEPth?`/`:ACQuire:POINts?`/`:ACQuire:SRATe?` 获取，不得用公式代替实测。
- **触发系统**：已记录 `TRIGger:MODE`（含 `FTRIG`）、`TRIGger:TYPE` 的 24 种类型、`TRIGger:STATus?`、`TRIGger:RUN/STOP` 与边沿触发序列；各类型的具体参数（脉宽、欠幅上下限、释抑、耦合、噪声抑制、串行协议阈值/速率）未逐条记录，手册印刷 pp. 245-410。
- **测量**：简单测量已记录 `MEASure` 总开关、`MEASure:MODE`、`SIMPle:ITEM` 的 52 项参数与 `VALue?`；高级测量已记录槽位使能、`TYPE` 写入、双源、值、统计、历史；门限/参考电平设置（`THReshold`）、统计复位与 `MAXCount`、`ASTRategy`、门控（`GATE`）未记录。
- **波形传输**：只记录了现代 WAV 与旧式 `C<n>:WF? DAT2/DESC`；`WAV:SOURce` 的数字通道/数学等扩展源、历史帧/存储媒介选择（`MEMory`/`SAVE` 类）未记录。
- **文件与保存**：已记录 `SAVe:IMAGe`（含菜单开关）；`:SAVe:WAVEform`、`:SAVe:SETup`、`:RECall:*`、`:MEMory:*`、`:REF:*` 未记录，属写文件操作，需按需授权。
- **协议解码**：只记录 5 条总线/列表查询；`DECode`/`DECode:BUS<n>` 使能、`BUS<n>:PROTocol` 写入，以及手册印刷 pp. 73-148 的协议专用设置（I2C/SPI/UART/CAN/LIN 等的源、阈值、位速、帧格式）未记录。
- **搜索与掩码**：已记录搜索使能/模式/计数/事件/模式参数族，掩码使能/加载/类型/计数；事件导航（上一/下一事件 `COPY`）、掩码生成/编辑与模板来源未记录。
- **计数器/光标/历史**：已记录计数器使能/模式/源/电平/统计/总计数的门控，光标使能与单组位置/差值，历史使能/选帧/间隔/列表/回放；多光标族（`MANual`/`MEASure`/`TRACk`/`XY`，印刷 pp. 46-67）未逐条记录。
- **数学与显示**：`:FUNCtion<x>:*`（ADD/SUBT/FFT/ERES/AVERage/MAXHold/MINHold/FILTer 等，印刷 pp. 138-188）与 `:DISPlay:*`（除 `PERSistence` 外）未记录。
- **网络与远程控制周边**：VXI-11/Web 控制、凭据与安全设置、固件升级等命令未记录。
