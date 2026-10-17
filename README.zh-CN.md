# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一组供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性。

## Skills

| 仪器类型 | Skill | 仪器系列 | 能力 | 验证情况 |
|---|---|---|---|---|
| 示波器 | [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 —— SDS802X HD、SDS804X HD、SDS812X HD、SDS814X HD、SDS822X HD、SDS824X HD（2 或 4 通道；70/100/200 MHz；50 或 100 Mpts） | 发现与连接、信号测量、截图与波形捕获、协议解码、异常/模板（Mask）测试、计数器/光标/历史读取、本地波形分析（NumPy）；LAN（raw TCP）与 USB（USBTMC/VISA） | 已在 SDS824X HD 实机验证（固件 `4.8.12.1.1.6.5`）；与通道数、带宽、存储深度相关的功能须在所连型号上重新确认 |
| 任意仪器（编写指南） | [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 可扩展至任意仪器：示波器、万用表、电源、分析仪等 | 编写指南与解析器模板、示例，用于新建仪器 Skill；不连接硬件 | 编写指南，无设备指令需要实机验证 |

使用 skills CLI 安装：

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

为新型号仪器添加 Skill 时，从本仓库自带的编写指南
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md)
入手。它会走一遍编写路径：界定仪器边界、从编程手册收集可引用的证据、划分
响应格式、把解析拆分为多个阶段。

指南本身不连接真实硬件。设备 Skill 是否算已验证，以在真实仪器上实际运行为
准；可以在 Skill 或 README 表格中补充截图、固件版本等证据，但不强制。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
