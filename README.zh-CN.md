# Siglent SDS800X HD SCPI Skill

[English](README.md) · [简体中文](README.zh-CN.md)

一个 AgentSkill（附带确定性 Python 辅助脚本），通过单一原始 SCPI TCP 会话驱动
鼎阳（Siglent）SDS800X HD 系列示波器：单次捕获、波形下载、测量、截图、协议解码、
异常搜索，以及有界的本地波形分析。

## 支持的示波器

- SDS800X HD 系列（同一平台与命令集）：**SDS802X HD**、**SDS804X HD**、
  **SDS812X HD**、**SDS814X HD**、**SDS822X HD**、**SDS824X HD** —— 2 或 4 通道，
  70/100/200 MHz，50 或 100 Mpts。
- 本文档中的行为均在 **SDS824X HD**（固件 `4.8.12.1.1.6.5`）上实测验证。与通道数、
  带宽、存储深度相关的功能，必须在实际连接的型号上重新确认后才能称为“已验证”。

## 支持的操作

- **发现与连接** —— 只读的 USB（USBTMC/VISA）与 LAN `*IDN?` 发现、身份校验、
  存储/传输路径选择。
- **信号发现与测量** —— 查找信号、自动量程、查看触发与采集状态、
  测量电压/时序/抖动。
- **截图与波形捕获** —— 单次捕获、截图、分段的 BYTE/WORD 波形下载。
- **协议解码** —— UART/I2C/SPI/CAN/LIN 及其他支持的串行总线。
- **异常搜索与模板（Mask）测试** —— 窄脉冲（runt）、毛刺、时序违规、模板失败。
- **计数器、光标与历史** —— 频率/周期统计、光标差值、历史时间戳。
- **本地只读波形分析**（NumPy）—— 针对已完成捕获的 `inspect`、`summarize`、
  `events`、`window`、`ringing`。

## 安装

### 使用 skills CLI（推荐）

```bash
npx skills@latest add Sighthesia/SDS800XHD_SCPI_Skill
```

### 离线 / 手动

已提交的 `dist/siglent-sds800xhd-control.skill` 是 skill 目录的 zip 包。
将其解压到某个 agent 的 skills 目录即可（OpenCode 例如
`~/.config/opencode/skills/`）。

## 工作流

- **渐进式参考加载** —— 从
  [`siglent-sds800xhd-control/SKILL.md`](siglent-sds800xhd-control/SKILL.md)
  的目标表开始，只加载与当前目标匹配的那一页 `references/`，而不是一次读完所有页面。
- **单次捕获** —— 只连接一次，先快照配置，用 `TRMD SINGLE` 启动（绝不用 `ARM`），
  轮询 `SAST?` 直到 `Ready`，激励被测件，再轮询直到 `Stop`，随后冻结命令集。
  全长度传输使用 `capture_scope.py` 的分段路径（`WAV:SOURce` -> 位宽/字节序 ->
  `WAV:INTerval` -> `WAV:STARt`/`WAV:POINt` -> `WAV:DATA?`），并且只有在所有分段
  全部通过校验后才合并为一个 `waveform.bin`。
- **不可变（immutable）停止帧** —— 先读取每个通道的 `WF? DAT2`，保存原始载荷，
  之后再选择性地发出 `WF? DESC`。期间不写任何状态。
- **已配置的重复捕获（configured_capture）** —— 明确标注为 `configured_capture`；
  可在新捕获前使用 `WFSU`，但绝不在 `Stop` 之后使用。对跟随触发的突发，可选启用
  左对齐触发策略（`--left-aligned-trigger`）。
- **分析流水线** —— capture -> `inspect` -> `summarize` -> `events`
  （可带时间范围）-> `ringing` -> `window`。原始 `waveform.bin` 始终是权威证据；
  摘要/预览只是有损辅助。

## 仓库结构

- `siglent-sds800xhd-control/` —— skill 源码。
  - `SKILL.md` —— 行为契约与安全规则。
  - `scripts/` —— 标准库 Python 辅助脚本及离线单元测试。
  - `references/` —— 渐进式加载页面（中文）；由 `SKILL.md` 的目标表决定读取哪一页。
- `dist/siglent-sds800xhd-control.skill` —— 已提交的 zip 交付物。
  skill 目录内任何改动后都需重新打包；它本身不会自动跟踪源码。
- `.specs/` —— 带日期的逐功能契约（约束 + 验收清单）。
- `docs/ref/*.pdf` —— 厂商手册（未跟踪）；`references/` 按页码引用。
- `docs/superpowers/specs/` —— 设计意图文档。
- `artifacts/` —— 原始捕获（未跟踪）。

## 开发

测试完全离线（合成夹具，无需示波器），且只有在工作目录为 `scripts/` 时才能正确导入，
因为模块使用同目录的裸导入：

```bash
cd siglent-sds800xhd-control/scripts && python3 -m unittest discover -s . -p 'test_*.py'
```

- 44 个测试，约 0.2 s。运行单个模块/类/用例：
  `python3 -m unittest test_waveform_analysis` 或
  `python3 -m unittest test_scope_protocol.TestX.test_y`。
- 校验 skill（frontmatter、结构、引用）：
  `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py siglent-sds800xhd-control`
- 校验通过后重新打包（会先校验；自动排除 `__pycache__`）：
  `python3 ~/.agents/skills/skill-creator/scripts/package_skill.py siglent-sds800xhd-control dist`
  然后用 `unzip -t dist/siglent-sds800xhd-control.skill` 检查。
- `capture_scope.py` 与 `discover_scope.py` 会连接真实硬件（默认
  `192.168.10.2:5025`；`5024` 端口是旧式 shell，切勿用于查询）。

## 安全不变量

以下为关键约束；离线测试覆盖了其中一部分。

- 绝不发送 `ARM`。单次启动使用 `TRMD SINGLE`，有效捕获必须观察到
  `Ready -> Stop` 状态转换。
- 不可变停止帧读取不得发送 `STOP`/`TRMD`/`RUN`/`ARM`/`WFSU`、配置写入或 TCP 重连。
  在发出任何 `WF? DESC` 之前，先读取每个通道的 `WF? DAT2`。
- 明确区分 `immutable_capture` 与 `configured_capture`；绝不隐式恢复仪器状态。
- IEEE 488.2 二进制块：找到 `#`，读取长度位数字，再读取确切长度的载荷；
  绝不按行切分载荷，也绝不把失败的重试拼成“完整”文件。
- 记录 BYTE 与 WORD 的来源信息。除非提供与该次捕获 SHA 绑定的校准文件，
  WORD 电压一律保持 `OBSERVED_UNVERIFIED`。

## 依赖

- `scope_protocol.py`、`capture_scope.py`、`discover_scope.py` 仅需 Python 3 + 标准库。
- `numpy>=2.0,<3.0`（`siglent-sds800xhd-control/requirements-analysis.txt`）
  仅用于 `waveform_analysis.py` / `analyze_waveform.py`。
- `pyvisa` 为可选依赖，仅 `discover_scope.py --usb` 使用。
- 有意不引入 SciPy。
