# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

SCPI 仪器控制、响应解析与证据分级的 Agent 技能。

## 技能

| Skill | 仪器类型 | 实机验证 |
|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | 示波器 | ✅ SDS824X HD |
| [`keithley-2000-control`](skills/keithley-2000-control/SKILL.md) | 台式万用表 | ✅ Model 2000 |
| [`gwinstek-gdm8352-control`](skills/gwinstek-gdm8352-control/SKILL.md) | 台式万用表 | ✅ GDM-8352 |
| [`gwinstek-afg2225-control`](skills/gwinstek-afg2225-control/SKILL.md) | 函数发生器 | — |
| [`gwinstek-gpd4303s-control`](skills/gwinstek-gpd4303s-control/SKILL.md) | 直流电源 | ✅ GPD-4303S |
| [`gwinstek-gds1000b-control`](skills/gwinstek-gds1000b-control/SKILL.md) | 示波器 | — |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 编写指南 | — |

## 能力

| Skill                          | 手册覆盖                             | 辅助能力                                                 |
| ------------------------------ | ------------------------------------ | -------------------------------------------------------- |
| `siglent-sds800xhd-control`    | 部分：7 类任务；仅有回退命令索引     | `waveform_analysis`、`waveform_scan` 等 11 个脚本        |
| `keithley-2000-control`        | 部分：11/11 面板功能；无块/缓冲解析  | `keithley2000_session`：试运行、原始捕获、串口锁         |
| `gwinstek-gdm8352-control`     | 仅可读子集：122 条索引中 22 条       | `gdm8352_session`：试运行、白名单、sha256 fixtures       |
| `gwinstek-afg2225-control`     | 部分：9 个构建/解析函数；13 个单位表 | `afg2225_protocol`：ARB/IEEE 块编解码、错误队列          |
| `gwinstek-gpd4303s-control`    | 仅可读子集：18 条形式中 8 条         | `gpd4303s_protocol`/`_session`：`STATUS?` 位解码、试运行 |
| `gwinstek-gds1000b-control`    | 部分：41 条测量命令；波形下载        | `gds1000b_protocol`：IEEE 块编解码、离线波形校验         |
| `write-new-instrument-control` | —（无设备命令）                      | 解析器模板、响应分帧示例、完整性状态                     |

## 提示或已知问题

- GPD-4303S 的验证机台处于串联跟踪时，CH1/CH2 可能接成一路供电，而非两个独立通道。
- 与通道数、带宽、存储深度相关的行为须在所连型号上重新确认。
- 实机验证仅覆盖直流电压与直流电流，其余功能仍为 `documented`。
- `hardware-verified` 仅覆盖只读查询，写命令、量程/功能切换、跟踪与记忆类命令均为 `documented`。
- GDM-8352：存在一次静默的 `SYST:BEEP:STAT 0`（事后查询确认，Skill 仍拒绝发送）。
- 部分 Skill 仅 `documented`，未做任何实机验证。
- 不得把 `hardware-verified` 扩展到所记录的型号、固件、接口与功能之外。

## 验证

**设备 Skill 只有在真实仪器上实际运行过才算已验证。**

各 Skill 的 `SKILL.md` / `SUPPORT.md` 是权威记录。

## 安装

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献

为新型号仪器添加 Skill 时，从[编写指南][authoring-guide]入手。
该指南本身不连接真实硬件；编写依据见 [`docs/references.md`](docs/references.md)。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。

[authoring-guide]: skills/write-new-instrument-control/SKILL.md
