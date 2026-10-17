# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

一组供 AI 使用的仪器操作与数据分析技能：连接和配置仪器、解析仪器返回的
数据、校验数据完整性，并在本地离线回放。

## 安装

使用 skills CLI（推荐）：

```bash
npx skills@latest add Sighthesia/instrument-control-skills
```

离线 / 手动安装：把 `skills/` 下的某个 Skill 目录复制或软链接到 agent 的
skills 目录（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

每个 Skill 是 `skills/<skill-name>/` 下的一个目录。目录名必须与 frontmatter
中的 `name` 一致。每个 Skill 的 `SKILL.md` 是该 Skill 的权威契约。

- 离线测试不得连接硬件、扫描网络或枚举 VISA 资源。
- 连接真实硬件的脚本只在被直接运行时才会连接硬件；离线测试不得导入或调用它们。
- 不要提交完整的厂商手册。

提交时保持 `README.md` 与 `README.zh-CN.md` 同步。
