# Connection and Storage Guidance

本文档适用于 SDS800X HD 系列，目标是建立“先发现、再确认、后配置、最后传输”的基础通信流程。手册来源为仓库内的 `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf` 和 `docs/ref/SDS800X-HD_usermanual_CN01A.pdf`；页码以 PDF 阅读器页码/印刷页码为准，具体固件仍应以目标设备实测为准。

## 1. 先明确端口角色

| 端口/协议 | 角色 | 适合用途 | 本项目策略 |
|---|---|---|---|
| 后置 USB 2.0 Device | 示波器作为 USBTMC 仪器设备 | VISA/SCPI 控制与查询 | 用 PyVISA 枚举，`*IDN?` 确认 |
| 前置 USB Host | 示波器作为 USB 主机 | 外接 U 盘、鼠标、键盘等 | 不能作为电脑端的 USB Device |
| LAN VXI-11 | VISA 仪器会话 | 支持 VXI-11 的 VISA 发现/连接 | 可选，需本机 VISA 后端与设备实测 |
| LAN raw socket | TCP SCPI 服务 | `IP:5025`，低依赖、可保留二进制字节 | 本项目采集主路径 |
| LAN Telnet/legacy shell | 旧式交互通道 | 诊断或手册指定场景 | 不作为本项目 SCPI 查询通道；不要把 `5024` 当作普通 SCPI 端口 |

手册的 VISA 示例使用 USB VID `0xF4EC`，并展示了 USBTMC 资源地址；该 VID 可作为筛选线索，但不能代替 `*IDN?`。USB 设备枚举还依赖操作系统驱动和 VISA backend。

## 2. 自动发现流程

### 2.1 USBTMC/VISA

安装 PyVISA 及可用的 VISA backend 后运行：

```text
python3 scripts/discover_scope.py --usb
```

工具调用 `ResourceManager.list_resources("USB?*INSTR")`，逐个打开资源并发送 `*IDN?`。只有 manufacturer 包含 `Siglent` 且 model 包含 `SDS` 的结果才会进入默认 `results`；用 `--all` 可保留其他成功响应用于诊断。

可能遇到的结果：

- `PyVISA is not installed`：这是依赖缺失，不等于“没有 USB 示波器”。
- VISA backend 找不到：安装 NI-VISA、Keysight VISA 或平台可用的兼容 backend，并确认 USBTMC 驱动已加载。
- 资源打开失败：保留在对应 transport 的 `errors` 中，其他设备仍继续探测。
- 多台设备：全部返回，不自动选择第一台；调用方应按序列号、型号或用户选择建立后续会话。

### 2.2 LAN raw socket

已知网段时，使用有上限的并发探测：

```text
python3 scripts/discover_scope.py --lan 192.168.1.0/24 --timeout 0.4 --max-hosts 254
```

已知地址时，避免扫描：

```text
python3 scripts/discover_scope.py --ip 192.168.1.150
```

每个地址只做以下动作：连接 TCP `5025`、发送 `*IDN?\n`、读取文本响应、关闭连接。工具会容忍旧通道可能出现的 banner/空行，但不会把 banner 当作身份结果。`--max-hosts` 默认是 `256`，网段过大时直接拒绝，避免无界扫描。

LAN 发现依赖路由、防火墙和示波器 LAN 配置；端口开放不代表设备一定是 Siglent。成功结果必须再次检查 `target: true`，并在真正控制前保存完整 IDN。

### 2.3 VISA LAN/VXI-11

手册说明 LAN 支持 VXI-11、Sockets 和 Telnet。若本机 VISA backend 支持 VXI-11，可以用资源管理器列出 `TCPIP?*INSTR`，或对已知地址使用类似：

下面的 PyVISA API 形态参考 PyVISA 官方通信文档：https://github.com/pyvisa/pyvisa/blob/main/docs/source/introduction/communication.md 。资源字符串和 VXI-11 是否可用仍以本机 VISA 实现为准。

```python
import pyvisa

rm = pyvisa.ResourceManager()
resources = rm.list_resources("TCPIP?*INSTR")
for name in resources:
    with rm.open_resource(name) as scope:
        scope.timeout = 1000
        print(name, scope.query("*IDN?").strip())
```

VXI-11 广播/发现是否可用取决于 VISA 实现、子网和设备固件；不能将 `list_resources` 为空解释为 LAN 没有示波器。对 raw socket 采集，直接使用现有 `scope_protocol.py` 的单一 TCP `5025` 会话。

## 3. 连接后的最小配置

发现成功后，配置分成“只读确认”和“显式写入”两类。

### 3.1 推荐的只读确认

先发送：

```text
*IDN?
:SYSTem:COMMunicate:LAN:TYPE?
:SYSTem:COMMunicate:LAN:IPADdress?
:SYSTem:COMMunicate:LAN:SMASk?
:SYSTem:COMMunicate:LAN:GATeway?
:SYSTem:COMMunicate:LAN:MAC?
```

然后按当前工作流保存示波器状态快照。现有 `capture_scope.py` 会在采集前记录 IDN、触发模式、采样率、存储深度、时基、触发延迟、波形传输设置和通道垂直参数。

### 3.2 静态 IP 配置是有副作用的

只有用户明确授权、确认网络规划并准备处理连接中断时，才考虑：

```text
:SYSTem:COMMunicate:LAN:TYPE STATIC
:SYSTem:COMMunicate:LAN:IPADdress "192.168.1.150"
:SYSTem:COMMunicate:LAN:SMASk "255.255.255.0"
:SYSTem:COMMunicate:LAN:GATeway "192.168.1.1"
```

实际写法以目标固件对引号、重启/应用动作和字段顺序的要求为准。配置后先读取回读值，再重新发现新地址；基础发现工具不会自动执行这些命令。

## 4. 远程/本地控制状态（REMOTE / LOCAL）

手册 `:SYSTem:REMote` 有明确命令（印刷 p. 264），不是只能靠面板按键：

```text
:SYSTem:REMote ON       # 进入远程：触摸屏、前面板按键和其他外设全部禁用，
                        # 界面显示 “Remote”
:SYSTem:REMote OFF      # 返回本地控制
:SYSTem:REMote?         # 查询，返回 ON / OFF
```

短形式 `SYST:REM ON` / `SYST:REM OFF` / `SYST:REM?`。

要点：

- 这是**状态改变**命令，只在用户明确要求“锁定/恢复面板”时才发送，不要作为会话收尾的自动清理。
- 进入远程前先确认没有人在面板上操作；进入后所有面板输入失效，只能靠 SCPI 或 `:SYSTem:REMote OFF` 恢复。
- 该命令与“连接方式”无关：raw TCP `5025` 会话**不会**自动让示波器进入面板锁定，是否锁定由这条命令显式控制。因此不能用“面板能按”来判断 SCPI 会话是否正常。
- 与部分 GW Instek 型号另有的独立面板锁命令语义不同；SDS800X HD 手册只记录 `:SYSTem:REMote` 这一条面板锁定路径。
- 证据等级：`documented`（手册印刷 p. 264），尚未在目标固件 `4.8.12.1.1.6.5` 上实测；实际是否会重新枚举会话或断开连接需实测确认。

## 5. USB 不能直接变成 U 盘

后置 USB Device 在手册中定义为 USBTMC 通信控制端口，前置 USB Host 才是连接外部存储设备的端口。因此本项目不提供 USB MSC 挂载、盘符映射或 `:SYSTem:USB:MODe MSC` 之类的操作；没有足够手册依据证明该模式存在。

这意味着电脑端不能通过 USB 文件系统直接浏览示波器内部存储。应在下面两条方案中选择一条，并把文件最终落到电脑端：

## 6. 文件和波形传输方案

### 6.1 方案 A：示波器挂载电脑网络存储

手册的 `:SYSTem:NSTorage` 命令用于设置网络存储参数，参数形式包含路径、用户名、密码以及远端路径/用户等字段；密码查询会以 `***` 返回。推荐流程：

1. 在电脑上建立专用共享目录，并限制到测试网段和最小权限账户。
2. 依据目标固件手册填写 `:SYSTem:NSTorage <path>,<user>,<pwd>,...` 的完整字段。
3. 发送 `:SYSTem:NSTorage:CONNect`（短命令形式以设备手册为准）。
4. 查询 `:SYSTem:NSTorage:STATus?`，确认返回 `ON` 或手册规定的已连接状态。
5. 先用一个小截图或小 CSV 验证实际挂载路径，再批量保存。
6. 完成后用 `:SYSTem:NSTorage:DISConnect` 断开（手册印刷 p. 263），不要长期保留凭据挂载。

示意命令：

```text
:SYSTem:NSTorage "//192.168.1.100/ScopeShare","scope-user","<password>",0,0,1,0,0
:SYSTem:NSTorage:CONNect
:SYSTem:NSTorage:STATus?
:SYSTem:NSTorage:DISConnect
```

`NSTorage` 的完整字段顺序为 `<path>,<user>,<pwd>,<anon>,<auto_con>,<rem_path>,<rem_user>,<rem_pwd>`（手册印刷 pp. 262-263）。含义分别是：`<path>` 服务器挂载路径、`<user>` 用户名、`<pwd>` 密码、`<anon>` 匿名标志（1 = ON）、`<auto_con>` 自动连接标志、`<rem_path>` **记住路径**标志、`<rem_user>` **记住用户名**标志、`<rem_pwd>` **记住密码**标志。后三项是“是否记住”，不是“是否连接”，不要把它们当成连接参数。查询时密码恒返回 `***`。

注意：`NSTorage` 的字段含义和 SMB/NFS 兼容性由固件决定；不要把密码提交到日志、脚本仓库或 JSON。用户原始示例中的 `net_storage/ScopeShare/...` 也应先通过目标设备的文件浏览/保存测试确认，不能跨固件硬编码。

### 6.2 方案 B：直接把二进制数据拉回电脑

这是本项目更推荐的默认路径：示波器只负责返回 SCPI 数据，电脑保存原始响应和解析后的文件。

- 截图：发送 `:PRINt? PNG` 或 `:PRINt? BMP`，使用二进制块读取器保存 payload；不能使用 `readline()`。
- 波形：使用 `WAVeform:PREamble?`、`WAVeform:MAXPoint?`、`WAVeform:STARt`、`WAVeform:POINt`、`WAVeform:DATA?` 分段下载。现有 `capture_scope.py` 会保存每段 payload、前缀、响应、元数据和 SHA-256，并验证点数、字节数及连续范围。
- 分析：先保留 `waveform.bin` 和 manifest，再用 `analyze_waveform.py` 在电脑端做有界分析；不要用 CSV/降采样结果替代原始证据。

最小的 raw socket 结构示例：

```python
from scope_protocol import scope_connect, scope_identify

scope = scope_connect("192.168.1.150", port=5025)
try:
    print(scope_identify(scope))
    # 后续二进制查询必须使用 scope_protocol 的 query_block/read_ieee_block。
finally:
    scope.close()
```

该示例只建立连接和身份确认。不要在没有明确采集授权时追加 `TRMD SINGLE`、`WFSU` 或其他状态修改命令；采集时遵循 `SKILL.md` 的 `Ready -> Stop`、单会话和二进制完整性规则。

## 7. 推荐决策

| 目标 | 推荐 |
|---|---|
| 只想自动找到并识别设备 | `discover_scope.py --usb` 或 `--lan/--ip` |
| 稳定采集大型波形 | raw TCP `5025` + `capture_scope.py` |
| 让示波器保存后文件自动出现在电脑共享目录 | `NSTorage`，先做目标固件小文件验证 |
| 只需把截图/波形交给 AI | 方案 B，直接二进制传输到电脑，再本地分析 |
| 通过 USB 浏览内部文件 | 不支持；USB Device 是 USBTMC，不是 MSC |
