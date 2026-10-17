# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一组供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性。

## 安装

使用 skills CLI（推荐）：

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

为新型号仪器添加 Skill 时，从本仓库自带的编写指南
[`skills/write-new-instrument-control/SKILL.md`](skills/write-new-instrument-control/SKILL.md)
入手。它完整地走一遍编写路径：界定仪器边界、从编程手册收集可引用的证据、
划分响应格式、把解析拆分为多个阶段、产出带完整性报告的数据 artifact，以及
编写离线回放测试。

指南本身不连接真实硬件，基于合成夹具做回放测试。新设备 Skill 的实机验证
需要在真实仪器上单独完成。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
