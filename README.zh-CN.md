# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一些供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性。

## Skills

| 仪器类型 | Skill | 仪器系列 | 能力 | 验证情况 |
|---|---|---|---|---|
| 示波器 | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 —— SDS802X HD、SDS804X HD、SDS812X HD、SDS814X HD、SDS822X HD、SDS824X HD（2 或 4 通道；70/100/200 MHz；50 或 100 Mpts） | 发现与连接、信号测量、截图与波形捕获、协议解码、异常/模板（Mask）测试、计数器/光标/历史读取、本地波形分析（NumPy）；LAN（raw TCP）与 USB（USBTMC/VISA） | ✅已验证（SDS824X HD，固件 `4.8.12.1.1.6.5`；与通道数、带宽、存储深度相关的功能须在所连型号上重新确认） |
| 台式万用表 | [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Keithley Model 2000（6½ 位万用表） | 基于 SCPI 手册的直流/交流电压与电流、二线/四线电阻、频率/周期、热电偶温度、二极管与通断测量；读数命令选择、响应校验，以及带前置条件的触发/缓冲/限值/扫描参考；离线标量/协议解析器与可选的 RS-232 会话工具（支持干跑与安全护栏） | ✅直流电压与直流电流 + RS-232 已实机验证（序列号 `0944865`，固件 `A17`/`A02`，9600 8N1，2026-10-20）；其余功能与接口仍基于 2000-900-01 Rev. J / August 2010 手册标记为 `documented` |
| 任意函数发生器 | [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | GW Instek AFG-2225（25 MHz，2 通道，120 MSa/s，4k 点 ARB，USB CDC） | 基于 SCPI 手册的身份/会话、基本波形、调制、扫描、突发、计数器，以及经校验的任意波形上传（ASCII 或显式字节序 IEEE 块）；离线响应/ARB 校验 | 基于 AFG-2225 User Manual（GW Instek part no. 82RF-22250M01）标记为 `documented`；USB CDC 身份未实机验证 |
| 示波器 | [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | GW Instek GDS-1000B 系列（GDS-1054B/1072B/1074B/1102B/1104B/1202B；2/4 通道；50-200 MHz；USB CDC；四通道型号支持以太网） | 基于 SCPI 手册的身份/会话、采集/触发/时基/通道配置、波形存储下载与校验、测量、保存/截图；离线解析器 | 基于 GDS-1000B Programming Manual Version 1.00, March 2015 标记为 `documented`；未实机验证 |
| 任意仪器（编写指南） | [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 可扩展至任意仪器：示波器、万用表、电源、分析仪等 | 编写指南与解析器模板、示例，用于新建仪器 Skill；不连接硬件 | 编写指南，无设备指令需要实机验证 |

使用 skills CLI 安装：

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

如果你有想要添加的仪器通信方法，也可将其加入。为新型号仪器添加 Skill 时，
从本仓库自带的编写指南
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md)
入手。它会走一遍编写路径：界定仪器边界、从编程手册收集可引用的证据、划分
响应格式、把解析拆分为多个阶段。

指南本身不连接真实硬件。设备 Skill 是否算已验证，以在真实仪器上实际运行为
准；可以在 Skill 或 README 表格中补充截图、固件版本等证据，但不强制。

### 参考依据

新建设备 Skill 会遵循编写指南中关于响应分帧（行式文本、CSV、IEEE 488.2 块、
长度前缀与分段二进制）、元数据/载荷分离、完整性状态与报告结构、标量/波形/坐标轴
检查、溯源、离线回放测试的规定。

编写指南与波形分析器还参考了公开标准与成熟的开源仪器项目；它们都不是运行时依赖：

- **IEEE 488.2** 块分帧，用于定长波形传输。
- **IEEE Std 181 / IEC 60469** 提供上升时间、脉宽、过冲与振铃等转换/脉冲/畸变
  术语。
- **PyVISA、PyVISA-sim、PyMeasure、QCoDeS** 用于传输选项、回放测试以及传输层与
  语义分离。
- **M4**（VLDB 2014）用于有损预览，**NumPy `memmap`** 用于分块读取，
  **SciPy `find_peaks`/`welch`** 作为未来检测器参考。
- **厂商编程手册** 用于所有命令、字段和单位断言。

阈值交叉、脉宽与 runt 宽度、振铃筛查均为启发式实现，不声称符合任何标准。
完整索引、链接与注意事项见 [`docs/references.md`](docs/references.md)。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
