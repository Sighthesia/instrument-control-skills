# Spec Contract: Keithley 2000 Instrument Skill

- **Created**: 2026-10-18 00:00
- **Status**: Completed
- **Target Files/Modules**: `skills/keithley-2000-control/`, `README.md`, `README.zh-CN.md`

## 1. Core Objective

根据 `ref/2000-900_J-Aug2010_User.pdf`（Model 2000 Multimeter User’s Manual，2000-900-01 Rev. J，August 2010）编写一个可独立使用的 Keithley 2000 台式万用表控制 Skill，覆盖常用台式万用表测量方法、SCPI 远程控制、响应解析、状态/错误检查和安全边界，并明确文档证据与实机验证的区别。

用户已确认首版聚焦常用测量及 SCPI 单次/连续读数和校验；触发、缓冲、限值、扫描作为带前置条件的进阶参考。

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: 不复制整本厂商手册；只保留必要的手册摘要、章节/页码引用和官方来源信息。
- [x] **C-02**: 所有未连接真实 Keithley 2000 得到的能力只能标记为 `documented`，不得声称 `hardware-verified`。
- [x] **C-03**: 保留原始响应后再解码；解析必须区分 framing、metadata、payload、normalization 和 validation；不得静默填充、截断、插值或猜测数据。
- [x] **C-04**: 仪器特定 SCPI 命令、状态规则和安全规则必须放在 Keithley 2000 Skill 内，不修改通用 authoring Skill 的设备协议。
- [x] **C-05**: 离线测试不得连接真实硬件；测试必须使用合成或固定响应夹具。
- [x] **C-06**: 修改完成后运行 Skill 校验、仓库规定的 CLI 发现检查、相关离线测试，并按仓库要求使用英文 Conventional Commit 提交。

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: 新增 `skills/keithley-2000-control/SKILL.md`，包含合法 frontmatter、触发描述、设备边界、支持级别、证据引用和使用流程。
- [x] **AC-02**: Skill 覆盖连接/会话初始化、`*IDN?` 探测、清状态、错误队列读取、命令终止符/查询配对和安全复位边界。
- [x] **AC-03**: Skill 覆盖 DC/AC 电压、电阻、频率/周期、温度、二极管/通断、直流/交流电流等手册支持的基础测量方法；对端子、最大输入和连接前置条件给出安全提示，包括电流仅用前面板 AMPS/INPUT LO、未知电路不自动切换。
- [x] **AC-04**: Skill 覆盖函数选择、自动/固定量程、分辨率/数字数、积分/NPLC、带宽、平均滤波、相对值和触发/延时等影响读数的设置。
- [x] **AC-05**: Skill 覆盖单次读数、连续采集、`READ?`/`FETCH?`/`MEASURE?`/`:SENSe:DATA?` 的适用边界，以及结果的单位、函数、配置、时间和证据元数据；注意 `*IDN?` 不证明所选命令语言。
- [x] **AC-06**: Skill 覆盖触发模型、外部触发、读取保持、缓冲区读写/统计、限值测试和（有扫描卡时）扫描流程；未声明硬件条件的功能必须标记条件性支持或 `UNSUPPORTED`。
- [x] **AC-07**: 新增参考资料，记录手册版本、关键章节/页码、命令家族和已知限制；不将手册全文打包进 Skill。
- [x] **AC-08**: 新增标准库 Python 的离线解析/校验辅助代码，分离 framing、metadata、payload、normalization、validation；处理 ASCII 标量、`+9.9E37` 溢出和错误队列响应，对 CSV/多值/二进制明确报告 `UNSUPPORTED`，并保留原始字节。
- [x] **AC-09**: 新增离线测试夹具，验证有效读数、单位/上下文缺失、非法数值、过载/错误响应、空响应或截断响应的状态分类。
- [x] **AC-10**: 更新 `README.md` 与 `README.zh-CN.md`，以相同顺序登记 Keithley 2000 Skill、能力和 `documented` 证据状态。
- [x] **AC-11**: 运行 `quick_validate.py`、`npx skills@latest add . --list`、相关 Python 测试和必要的打包验证；记录结果并修复失败项。
- [x] **AC-12**: 完成验收审计，逐项更新本 Spec 的复选框，说明未完成项或验证限制，并创建英文 Conventional Commit。

## 4. Edge Cases & Boundary Conditions

- 读数可能带有 `OVLD`、错误字符串、空行、非有限值或额外尾随字节；不得把这些当作正常数值。
- 查询必须与响应一一配对；不得在已有未读取响应时继续发送会产生歧义的查询。
- 自动量程、NPLC、滤波、平均和触发设置会改变读数的速度、噪声和语义；结果必须带配置上下文。
- 交流测量、低电平电压、热电势、屏蔽和高能量电路存在手册规定的误差/安全注意事项；Skill 只能提示，不得替代操作规程或校准证明。
- 电流输入保险丝、端子和最大输入限制必须在测量流程前确认；未知外部电路状态时不得自动切换到电流测量。
- 温度测量需要探头/热电偶类型与参考结设置；缺失时应报告 `INCOMPLETE` 或 `UNVERIFIED`。
- 扫描卡、外部触发和 GPIB/RS-232 接口是条件性能力；没有对应硬件/接口证据时不能宣称可用。

## 5. Execution & Verification Log

- [x] Initial scaffolding
- [x] Implementation
- [x] Automated offline tests: 24 passed; hardware verification not performed
- [x] README synchronization
- [x] Final acceptance audit and commit: `79fd741 feat: add Keithley 2000 multimeter skill`
