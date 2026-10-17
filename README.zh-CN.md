# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

指导 AI 使用仪器并分析其返回数据的 Agent Skill 集合：连接与配置、响应 framing
与解析、完整性校验、provenance 以及离线 replay 测试。

## 安装

使用 skills CLI（推荐）：

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

离线 / 手动：把 `skills/` 下的任一 Skill 目录复制或软链接到某个 agent 的 skills
目录即可（OpenCode 例如 `~/.config/opencode/skills/`）。

## 贡献指南

新增 Skill 时，在 `skills/<skill-name>/` 下建立一个目录，包含 `SKILL.md`，并按需
包含 `references/`、`scripts/`、`assets/`。目录名必须与 frontmatter 中的 `name`
一致。每个 Skill 的 `SKILL.md` 是其权威契约。

- 仪器命令与状态规则保留在设备 Skill 内；保留原始响应；没有真实响应就不得声称
  某型号或固件"已验证"。
- 分离 framing、metadata、payload 提取、归一化和校验。返回 `COMPLETE`、
  `INCOMPLETE`、`INVALID`、`UNVERIFIED` 或 `UNSUPPORTED`；绝不静默补齐、截断、
  插值或猜测缺失校准。复用本仓库内置的解析器模板与编写指南。
- 离线测试不得连接硬件、扫描网络或枚举 VISA 资源；需包含二进制安全的夹具、
  期望结果和反例。
- 证据等级从保守取值：`documented`、`replay-tested`、`hardware-verified`、
  `firmware-scoped`。等级描述的是证据，而非功能数量。
- 不要提交完整的厂商手册。`dist/`、`artifacts/` 和 `__pycache__/` 属于本地内容
  并已被 git 忽略：需要时手动打包，提交前保持双语 README 同步。

### 命令

测试完全离线。模块使用同目录的裸导入，因此需把工作目录设置为测试模块所在的
目录再运行：

```bash
cd skills/<skill-name>/scripts && python3 -m unittest discover -s . -p 'test_*.py'
python3 -m unittest discover -s skills/<skill-name>/assets/<component>/tests -p 'test_*.py'
```

校验 Skill，必要时手动打包（打包会先校验并自动排除 `__pycache__/`），再确认
CLI 发现：

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py skills/<skill-name> dist   # dist/ 仅存本地
npx skills@latest add . --list   # 应恰好列出 skills/ 下的全部 Skill
```

连接真实硬件的脚本只在被直接运行时才会连接；切勿把它们接入测试，也绝不把失败
或重试的读取拼成"完整"文件。
