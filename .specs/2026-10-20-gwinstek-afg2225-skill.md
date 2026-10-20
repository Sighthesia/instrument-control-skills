# Spec Contract: GW Instek AFG-2225 Instrument Skill

- **Created**: 2026-10-20 00:00
- **Status**: Completed
- **Target Files/Modules**: `skills/gwinstek-afg2225-control/`, `README.md`, `README.zh-CN.md`

## 1. Core Objective

根据 AFG-2225 Series User Manual（GW Instek part no. 82RF-22250M01）编写一个可独立使用的 GW Instek AFG-2225 双通道任意函数发生器控制 Skill，覆盖 USB CDC 串口 SCPI 会话、身份/状态/错误处理、基本波形、调制/扫描/突发、计数器、相位/耦合，以及经过校验的任意波形上传（ASCII 或显式字节序 IEEE 块），并明确文档证据与实机验证的区别。

## 2. Hard Constraints & Negative Rules

- [x] 不复制整本厂商手册；只保留必要摘要、章节/页码引用和官方来源信息。
- [x] 所有未连接真实仪器的能力只能标记为 `documented`，不得声称 `hardware-verified`。
- [x] 保留原始响应后再解码；解析必须区分 framing、metadata、payload、normalization 和 validation；不得静默填充、截断、插值或猜测数据。
- [x] 仪器特定 SCPI 命令、状态规则和安全规则必须放在本 Skill 内。
- [x] 离线测试不得连接真实硬件；测试使用合成或固定响应夹具。
- [x] 修改完成后运行 Skill 校验、CLI 发现检查、相关离线测试。

## 3. Acceptance Criteria

- [x] 新增 `skills/gwinstek-afg2225-control/SKILL.md`，包含合法 frontmatter、触发描述、设备边界、支持级别、证据引用和使用流程。
- [x] Skill 覆盖 USB CDC 连接、`*IDN?`、版本查询、状态/错误队列、APPLy 与低电平波形、调制/扫描/突发、ARB 上传。
- [x] 新增 references，记录手册版本、关键章节/页码、命令家族和已知限制。
- [x] 新增标准库 Python 离线解析/校验辅助代码，分离 framing、metadata、payload、normalization、validation；处理 identity、numeric、error-queue、CSV/DAC、IEEE 块；保留原始字节。
- [x] 新增离线测试夹具，验证有效/无效身份、数值、错误队列、CSV、缩放、IEEE 块、会话 dry-run。
- [x] 更新 `README.md` 与 `README.zh-CN.md`，相同顺序登记 Skill。
- [x] 运行 `quick_validate.py`、`npx skills@latest add . --list`、相关 Python 测试。

## 4. Edge Cases

- identity 缺少字段 -> `INCOMPLETE`；错误模型 -> `INVALID`。
- 数值 NaN/Inf/坏单位 -> `INVALID`；单位无法解析 -> `INCOMPLETE`。
- 错误队列空 -> `COMPLETE`；溢出 -> `INCOMPLETE`；其他消息 auto 模式 -> `UNSUPPORTED`。
- CSV 浮点/非整数 -> `INVALID`；超范围 -> validate 失败；超 4096 -> `INVALID`。
- 缩放不钳位；IEEE 块不定长/截断/长度不匹配 -> 拒绝。
- 二进制 ARB 无字节序 -> 拒绝；dry-run 打印精确字节。

## 5. Execution & Verification Log

- [x] Initial scaffolding
- [x] Implementation
- [x] Automated offline tests: 82 passed; hardware verification not performed
- [x] README synchronization
- [x] Final acceptance audit

## 6. Review-Fix Addendum

- [x] Manual example byte-count defect preserved.
- [x] Binary byte order labelled unverified.
- [x] USB CDC identity labelled external evidence.
- [x] Enforce a terminator and reject trailing bytes in every response parser.
- [x] Normalize documented numeric suffixes to canonical base units while preserving raw values.
- [x] Validate ARB start address and `start + points <= 4096`.
- [x] Set `OUTP:LOAD` before APPLy/ARB and select `FUNC USER` after an ARB upload.
- [x] Correct amplitude, pulse-width, FUNC, load, voltage-unit, and modulation range tables.
- [x] Remove unsupported `*RST` error-queue and continuous-acquisition claims.