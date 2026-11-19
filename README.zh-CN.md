# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一些供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性。

## 技能列表

| Skill | 仪器 | 接口 |
|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 | `LAN (TCP 5025)`、`USB-TMC` |
| [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | Keithley Model 2000 | `RS-232` |
| [`gwinstek-gdm8352-control`](skills/gwinstek-gdm8352-control/SKILL.md) | GW Instek GDM-8352 | `USB CDC-ACM` |
| [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | GW Instek AFG-2225 | `USB CDC` |
| [`gwinstek-gpd4303s-control`](skills/gwinstek-gpd4303s-control/SKILL.md) | GW Instek GPD-4303S | `FTDI serial` |
| [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | GW Instek GDS-1000B 系列 | `USB CDC`、`LAN`（四通道型号） |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 任意仪器（编写指南） | — |

## 能力概览

- **`siglent-sds800xhd-control`** —— 测量、截图、波形捕获、协议解码、模板测试、
  离线分析。
- **`keithley-2000-control`** —— 交直流电压/电流、电阻、频率、温度、二极管与通断
  测量及响应校验。
- **`gwinstek-gdm8352-control`** —— 只读身份与交直流电压/电流查询、双显示帧解析、
  仅查询白名单。
- **`gwinstek-afg2225-control`** —— 标准与任意波形、调制、扫描、突发、计数器与
  ARB 上传校验。
- **`gwinstek-gpd4303s-control`** —— 只读电源监控：身份、`STATUS?` 解码、设定值
  与输出回读，不含使负载上电的命令。
- **`gwinstek-gds1000b-control`** —— 采集、触发、波形下载与校验、测量、保存与
  截图。
- **`write-new-instrument-control`** —— 新仪器 Skill 的编写指南与解析器模板；
  不连接硬件。

## 实机验证情况

| Skill | 型号 | 固件 | 接口 | 台架日期 |
|---|---|---|---|---|
| `siglent-sds800xhd-control` | SDS824X HD | `4.8.12.1.1.6.5` | LAN TCP 5025 | 未记录 |
| `keithley-2000-control` | Model 2000 | `A17` / `A02` | RS-232 9600 8N1 | 2026-10-20 |
| `gwinstek-gdm8352-control` | GDM-8352 | `1.00` | USB CDC-ACM `2184:003b` | 2026-11-19 |
| `gwinstek-gpd4303s-control` | GPD-4303S | `V2.08` | FTDI serial 9600 8N1 | 2026-11-19 |

## 台架备注

- SDS824X HD：与通道数、带宽、存储深度相关的行为须在所连型号上重新确认。
- Keithley Model 2000：仅直流电压与直流电流经 RS-232 实机验证（序列号
  `0944865`）；其余功能仍为 `documented`。
- GDM-8352：七条只读查询已实机验证并当日复测（序列号 `GEP848232`）；全部写命令与
  其他测量功能仍为 `documented`。
- GPD-4303S：CH1-CH4 只读查询已实机验证并当日复测（序列号 `EP924162`）；全部输出、
  设定值、跟踪、记忆命令仍为 `documented`。受验机台当时为串联跟踪（`SER/INDEP`
  灯亮，与 `STATUS?` 解码一致），CH1/CH2 合成单路 0-60 V，而非两个独立通道。
- AFG-2225 与 GDS-1000B 均为 `documented`，未做任何实机验证。
- 不得把 `hardware-verified` 扩展到所记录的型号、固件、接口与功能之外。

## 证据等级

`documented` < `hardware-verified` = `firmware-scoped`：标签描述的是特定型号、固件与
接口上的证据，而不是功能数量。

**设备 Skill 是否算已验证，以在真实仪器上实际运行为准。**
各 Skill 的 `SKILL.md` / `SUPPORT.md` 是权威记录。

## 安装

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

如果你有想要添加的仪器通信方法，也可将其加入。为新型号仪器添加 Skill 时，
从本仓库自带的编写指南
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md)
入手：界定仪器边界、从编程手册收集可引用的证据、划分响应格式、把解析拆分为
多个阶段。

指南本身不连接真实硬件。编写规则与分析方法的具体依据见
[`docs/references.md`](docs/references.md)。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
