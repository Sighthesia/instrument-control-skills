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
| [`rigol-ds1000z-control`](skills/rigol-ds1000z-control/SKILL.md) | 示波器 | ✅ DS1074Z |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 编写指南 | — |

## 能力

| Skill                          | 手册覆盖                             | 辅助能力                                                 |
| ------------------------------ | ------------------------------------ | -------------------------------------------------------- |
| `siglent-sds800xhd-control`    | 手册索引 873 行，参数已转录 | `waveform_analysis`、`waveform_scan` 等 11 个脚本        |
| `keithley-2000-control`        | 11/11 面板功能；287 行索引，参数已转录 | `keithley2000_session`：试运行、原始捕获、串口锁         |
| `gwinstek-gdm8352-control`     | 仅可读子集；写操作拒绝；索引 173 行 | `gdm8352_session`：试运行、白名单、sha256 fixtures       |
| `gwinstek-afg2225-control`     | 部分：ARB/IEEE 块构建与解析；13 个单位表 | `afg2225_protocol`：ARB/IEEE 块编解码、错误队列          |
| `gwinstek-gpd4303s-control`    | 仅可读子集；写操作拒绝；索引 48 行 | `gpd4303s_protocol`/`_session`：`STATUS?` 位解码、试运行 |
| `gwinstek-gds1000b-control`    | 部分：测量与波形下载；索引 450 行 | `gds1000b_protocol`：IEEE 块编解码、离线波形校验         |
| `rigol-ds1000z-control`        | 手册索引 500 行，参数已转录 | `ds1000z_protocol`/`_session`：IEEE 块、前导→电压、BMP 裁剪、游标读数、锁步 TCP |
| `write-new-instrument-control` | —（无设备命令）                      | 解析器模板、响应分帧示例、完整性状态                     |

索引行数均由 `grep -c '^|'` 在各技能已提交的 `references/command-reference.md` 上复算，
不要直接照抄本表。

## 提示或已知问题

- GPD-4303S：处于串联跟踪时，CH1/CH2 可能接成一路供电，而非两个独立通道。
- 示波器：与通道数、带宽、存储深度相关的行为须在所连型号上重新确认。
- 部分 Skill 仅 `documented`，未做任何实机验证。

## 验证

**证据属于具体断言，不属于整个 Skill。** 上表 ✅ 表示该 Skill 存有该仪器的抓包，
不等于其中每条命令、每个解析器、每个单位都在那台仪器上验证过。请读该 Skill
`SUPPORT.md`（若存在）或 `SKILL.md` 里的逐条证据表；只有引用了原始回包的断言才能标
`hardware-verified`。没有 `SUPPORT.md` 的 Skill 会在 `SKILL.md` 中说明。

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
