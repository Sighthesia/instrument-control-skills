# Instrument Control Skills

[English](README.md) · [简体中文](README.zh-CN.md)

指导 AI 使用仪器并分析其返回数据的 Agent Skill 集合：连接与配置、响应 framing
与解析、完整性校验、provenance 以及离线 replay 测试。

## 安装

使用 skills CLI（推荐）：

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

离线 / 手动：把 Skill 目录（例如 `skills/siglent-sds800xhd-control/`）复制或软链接到
某个 agent 的 skills 目录即可（OpenCode 例如 `~/.config/opencode/skills/`）。

## 支持的仪器

| Skill | 仪器 | 传输方式 | 验证等级 |
|---|---|---|---|
| [`siglent-sds800xhd-control`](skills/siglent-sds800xhd-control/SKILL.md) | Siglent SDS800X HD 系列 —— SDS802X HD、SDS804X HD、SDS812X HD、SDS814X HD、SDS822X HD、SDS824X HD（2 或 4 通道；70/100/200 MHz；50 或 100 Mpts） | LAN（raw TCP）、USB（USBTMC/VISA） | 已在 SDS824X HD（固件 `4.8.12.1.1.6.5`）实机验证 |
| [`write-new-instrument-control`](skills/write-new-instrument-control/SKILL.md) | 任意待新增 Skill 的仪器；本身不连接硬件 | — | 基于合成夹具，replay-tested |

Siglent Skill 覆盖发现与连接、信号测量、截图与波形捕获、协议解码、异常/模板（Mask）
测试、计数器/光标/历史读取，以及本地只读波形分析（NumPy）。与通道数、带宽、存储深度
相关的功能，必须在实际连接的型号上重新确认后才能称为“已验证”。

该表格即为 Skill 目录；每个 Skill 的 `SKILL.md` 是其权威契约。

## 贡献指南

新增 Skill 时，在 `skills/<skill-name>/` 下建立一个目录，包含 `SKILL.md`，并按需包含
`references/`、`scripts/`、`assets/`。目录名必须与 frontmatter 中的 `name` 一致，
并加入上方的表格。

- 仪器命令与状态规则保留在设备 Skill 内；保留原始响应；没有真实响应就不得声称某型号
  或固件“已验证”。
- 分离 framing、metadata、payload 提取、归一化和校验。返回 `COMPLETE`、`INCOMPLETE`、
  `INVALID`、`UNVERIFIED` 或 `UNSUPPORTED`；绝不静默补齐、截断、插值或猜测缺失校准。
  以 `write-new-instrument-control` 作为编写指南和模板来源。
- 离线测试不得连接硬件、扫描网络或枚举 VISA 资源；需包含二进制安全的夹具、期望结果
  和反例。
- 证据等级从保守取值：`documented`、`replay-tested`、`hardware-verified`、
  `firmware-scoped`。等级描述的是证据，而非功能数量。
- 不要提交完整的厂商手册。`dist/`、`artifacts/` 和 `__pycache__/` 属于本地内容并已被
  git 忽略：需要时手动打包，提交前更新双语 README。

### 命令

Siglent 控制测试完全离线，且只有在工作目录为 `scripts/` 时才能正确导入，因为模块使用
同目录的裸导入：

```bash
cd skills/siglent-sds800xhd-control/scripts && python3 -m unittest discover -s . -p 'test_*.py'
```

解析器模板测试与五类解析范例（含离线安全检查）：

```bash
python3 -m unittest discover -s skills/write-new-instrument-control/assets/parser-template/tests -p 'test_*.py'
python3 -m unittest discover -s skills/write-new-instrument-control/assets/examples -p 'test_*.py'
```

校验 Skill，必要时手动打包（打包会先校验并自动排除 `__pycache__/`），再确认 CLI 发现：

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py skills/<skill-name>
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py skills/<skill-name> dist   # dist/ 仅存本地
npx skills@latest add . --list   # 应恰好列出两个 Skill
```

`capture_scope.py` 与 `discover_scope.py` 会连接真实硬件（默认 `192.168.10.2:5025`；
`5024` 端口是旧式 shell，切勿用于查询）。绝不发送 `ARM`，也绝不把失败或重试的读取拼成
“完整”文件。
