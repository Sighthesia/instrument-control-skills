# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

指导 AI 使用仪器并分析其返回数据的 Agent Skill 集合：连接与配置、响应 framing
与解析、完整性校验、provenance 以及离线 replay 测试。

## 安装

使用 skills CLI（推荐）：

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

离线 / 手动：已提交的 `dist/siglent-sds800xhd-control.skill` 和
`dist/write-new-instrument-control.skill` 分别是对应 Skill 目录的 zip 包。
将需要的 archive 解压到某个 agent 的 skills 目录即可（OpenCode 例如
`~/.config/opencode/skills/`）。

## 支持的仪器

| Skill | 仪器 | 传输方式 | 验证等级 |
|---|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 —— SDS802X HD、SDS804X HD、SDS812X HD、SDS814X HD、SDS822X HD、SDS824X HD（2 或 4 通道；70/100/200 MHz；50 或 100 Mpts） | LAN（raw TCP）、USB（USBTMC/VISA） | 已在 SDS824X HD（固件 `4.8.12.1.1.6.5`）实机验证 |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 任意待新增 Skill 的仪器；本身不连接硬件 | — | 基于合成夹具，replay-tested |

Siglent Skill 覆盖发现与连接、信号测量、截图与波形捕获、协议解码、异常/模板（Mask）
测试、计数器/光标/历史读取，以及本地只读波形分析（NumPy）。与通道数、带宽、存储深度
相关的功能，必须在实际连接的型号上重新确认后才能称为“已验证”。

`registry.yaml` 是 Skill、能力与验证等级的机器可读目录；每个 Skill 的 `SKILL.md`
是其权威契约。

## 贡献指南

Skill 目录结构、控制/解析规则、证据等级、手册与版权政策、离线测试要求以及提交前
验证清单，见 [CONTRIBUTING.md](CONTRIBUTING.md)。
