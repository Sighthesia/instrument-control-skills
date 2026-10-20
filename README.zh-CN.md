# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一些供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性。

## Skills

| 仪器类型 | Skill | 仪器系列 | 能力 | 验证情况 |
|---|---|---|---|---|
| 示波器 | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 —— SDS802X HD、SDS804X HD、SDS812X HD、SDS814X HD、SDS822X HD、SDS824X HD（2 或 4 通道；70/100/200 MHz；50 或 100 Mpts） | 发现与连接、信号测量、截图与波形捕获、协议解码、异常/模板（Mask）测试、计数器/光标/历史读取、本地波形分析（NumPy）；LAN（raw TCP）与 USB（USBTMC/VISA） | ✅已验证（SDS824X HD，固件 `4.8.12.1.1.6.5`；与通道数、带宽、存储深度相关的功能须在所连型号上重新确认） |
| 台式万用表 | [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Keithley Model 2000（6½ 位万用表） | 基于 SCPI 手册的直流/交流电压与电流、二线/四线电阻、频率/周期、热电偶温度、二极管与通断测量；读数命令选择、响应校验，以及带前置条件的触发/缓冲/限值/扫描参考 | 基于 2000-900-01 Rev. J / August 2010 手册标记为 `documented`；未声称实机验证 |
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

### 编写规范覆盖的内容

新建设备 Skill 前应先阅读以下文档；它们对通信与数据处理具有约束力：

| 领域 | 参考文档 | 规则 |
|---|---|---|
| 编写阶段 | `authoring-workflow.md` | 仪器边界、证据表、`read_frame → parse_metadata → extract_payload → normalize → validate` 划分、先测试后上机、保守发布 |
| 仪器类型 | `instrument-types-and-examples.md` | 按数据断言与响应格式选择示例；五种教学格式及其主要检查 |
| 响应分帧 | `response-framing.md` | 行式文本、CSV、IEEE 488.2 定长块、长度前缀二进制、分段/分包记录；失败映射与分配上限 |
| 元数据与载荷 | `metadata-payload-validation.md` | 元数据与载荷分离、按证据执行长度/分段/校验和/坐标轴检查、仅归一化有证据支持的语义 |
| 完整性状态 | `status-and-reports.md` | `COMPLETE`/`INCOMPLETE`/`INVALID`/`UNVERIFIED`/`UNSUPPORTED`；单项检查 `pass`/`fail`/`not_checked`；报告结构与分析门控 |
| 数据专项检查 | `waveform-checks.md`、`scalar-checks.md`、`axes-and-sequences.md` | 点数/字节数、分段覆盖、坐标轴与单位、读数数量与仪器状态、顺序与重复记录 |
| 证据与溯源 | `evidence-and-provenance.md` | 型号、固件、接口、命令、原始响应、SHA-256、解析器版本、手册引用、校准绑定 |
| 离线测试 | `replay-testing.md` | 正向与负向夹具、期望结果、测试中不得使用 socket 或 VISA |

### 研究参考与标准依据

指南依据公开规范与成熟的开源仪器库编写；不复制其实现代码，也不把其中任何
项目作为运行时依赖。

- **IEEE 488.2** 二进制块分帧（`#<长度位数><长度><载荷>`）是示波器波形传输及
  其他定长响应的参考。
- **厂商编程手册**（例如 SCPI 手册）是命令、字段和单位断言的唯一可接受来源；
  按修订版与页码引用，绝不复制进仓库。
- **PyVISA**（[读写数值](https://pyvisa.readthedocs.io/en/stable/introduction/rvalues.html)）
  说明了每次传输必须显式决定的事项：数据类型、字节序、头部、终止符与期望点数。
- **PyVISA-sim**（[模拟仪器](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html)）
  为查询/响应会话、消息结束规则和原始字节回放测试提供参考。
- **PyMeasure**（[适配器](https://pymeasure.readthedocs.io/en/latest/api/adapters.html)、
  [高级通信](https://pymeasure.readthedocs.io/en/latest/dev/adding_instruments/advanced_communication.html)）
  支持把传输层置于仪器语义之下，把分帧/校验和置于字节层之上。
- **QCoDeS 社区驱动**（[Qcodes_contrib_drivers](https://github.com/QCoDeS/Qcodes_contrib_drivers)）
  体现驱动、示例与测试分离，支持责任归贡献者的做法。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
