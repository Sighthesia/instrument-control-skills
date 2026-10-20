# Spec Contract: GW Instek GDS-1000B Instrument Skill

- **Created**: 2026-10-20 00:00
- **Status**: Completed
- **Target Files/Modules**: `skills/gwinstek-gds1000b-control/`, `README.md`, `README.zh-CN.md`

## 1. Core Objective

根据 `ref/编程指令手册.pdf`（*GDS-1000B Series Programming Manual*，Version
1.00，March 2015）编写一个可独立使用的 GW Instek GDS-1000B 系列数字存储示波器
控制 Skill，覆盖 USB CDC / 型号相关以太网 SCPI 会话、通道/时基/触发配置、单次
采集与存储深度波形下载、测量、保存/截图和离线响应校验，并严格区分文档证据与
实机验证。

用户已确认：无实机可用，全部能力只能标记为 `documented`；波形电压换算因手册
示例自相矛盾而只能标记 `UNVERIFIED`；截图只能落盘到仪器，不得宣称 SCPI 回读。

## 2. Hard Constraints & Negative Rules (Non-negotiables)

- [x] **C-01**: 不复制厂商手册；只保留命令摘要、章节/页码引用和官方版本信息。
- [x] **C-02**: 没有真实仪器响应时，所有能力只能标记 `documented`，不得声称
  `hardware-verified` 或 `firmware-scoped`。
- [x] **C-03**: 保留原始响应字节后再解码；解析分离 framing、metadata、payload、
  normalization、validation；不得静默补齐、截断、钳位、插值或猜测。
- [x] **C-04**: 仪器命令、状态规则、安全规则全部位于 GDS-1000B Skill 内，不修改
  通用 authoring Skill 或其他设备的协议。
- [x] **C-05**: 离线测试不得打开串口或 socket；测试使用合成夹具。
- [x] **C-06**: 不创建 `dist/`、`artifacts/` 或 `__pycache__/`；测试后清理缓存。
- [x] **C-07**: 库代码与测试仅使用标准库；pyserial 只在实时传输路径惰性导入。
- [x] **C-08**: 不自动执行 `*RST`、`*SAV`、`*RCL`、校准、固件更新或覆盖文件。
- [x] **C-09**: 不声称支持 SCPI 图像/文件回读；截图流程明确为仪器端落盘。

## 3. Atomized Acceptance Criteria (Checklist)

- [x] **AC-01**: 新增 `skills/gwinstek-gds1000b-control/SKILL.md`，frontmatter
  `name` 与目录一致，描述覆盖 GDS-1000B、USB CDC/型号相关以太网、采集/波形、
  测量、保存/截图与 `documented` 支持状态。
- [x] **AC-02**: SKILL.md 包含用途与手册引用、不可协商的安全规则、证据与支持
  级别、设备边界、按需加载的参考表、标准会话流程、采集/波形流程、测量流程、
  保存/截图流程、离线解析与 CLI、完整性状态、验证命令、已知限制。
- [x] **AC-03**: `references/bench-setup.md` 覆盖六个型号/通道/带宽、探头与
  300 Vrms CAT I / CAT II、1 MΩ//16 pF（GDS-1202B 14 pF）、接地、USB 与 LAN、
  30 分钟预热、面板锁、禁止浮地。
- [x] **AC-04**: `references/remote-session.md` 覆盖 USB CDC、以太网服务器默认
  关闭/端口 1024-65535/仅四通道、LF、`*IDN?`、`*LRN?`、通用命令、`*SAV/*RCL`、
  `*RST`、`*CLS`、`*OPC?`、`*ESR?/*STB?`、`:SYSTem:LOCK`、错误队列与查询配对。
- [x] **AC-05**: `references/capture-and-waveform.md` 覆盖 RUN/STOP/SINGle/FORCe、
  触发状态、采集状态、记录长度 1e3-1e7、`HEADer`、存储查询、IEEE 块、大端有符号
  16 位、AD 因子 25、电压公式缺陷、`HEADer OFF`、资源上限与 CSV。
- [x] **AC-06**: `references/vertical-timebase-trigger.md` 覆盖通道、时基、触发
  命令与范围、CH3/4 与 EXT 的型号约束、触发模式/类型、状态查询与快照字段。
- [x] **AC-07**: `references/measurements.md` 覆盖 36 个单项测量、单位、源选择、
  `Chan Off`、八槽统计、采集上下文与状态处理。
- [x] **AC-08**: `references/save-and-screenshot.md` 覆盖图像保存、hardcopy、
  波形/设置保存与调回、路径与 8 字符限制、格式、无文件回读、禁止覆盖。
- [x] **AC-09**: `references/advanced-features.md` 覆盖数学/光标/显示、总线解码/
  搜索/分段/DVM/Go-NoGo/数据记录/远程磁盘、可选许可与型号前置条件，并明确核心
  脚本未实现这些功能。
- [x] **AC-10**: `references/response-and-evidence.md` 覆盖解析阶段、状态、身份/
  测量/错误/波形形状、原始证据、校准缺陷与已知限制。
- [x] **AC-11**: `scripts/gds1000b_protocol.py` 为纯标准库、传输无关实现，包含
  `MAX_POINTS=10_000_000`、`MAX_PAYLOAD_BYTES=20_000_000`、`AD_FACTOR=25`、
  `ProtocolError.status`、`Frame`、`IEEEBlock`、`read_frame`、`parse_metadata`、
  `extract_payload`、`normalize`、`validate`、高层解析函数、IEEE 块编解码、
  `iter_samples`、`sample_value`、`waveform_to_csv` 和 CLI。
- [x] **AC-12**: 波形解析校验 `Memory Length == points`、块长度偶数、无尾随字节、
  超大声明拒绝；无头块返回 `UNVERIFIED` 且无 scale/units；截断/错配 fail closed。
- [x] **AC-13**: `scripts/gds1000b_session.py` 支持串口与 TCP、`--dry-run`、
  `idn`/`snapshot`/`errors`/`run`/`stop`/`single`/`force`/`capture`/`waveform`/
  `measure`/`save-image`/`hardcopy`/`query`；TCP 必须显式 host/port；实时路径惰性
  导入 pyserial/socket。
- [x] **AC-14**: 新增合成夹具与 `expected-*.json`，覆盖有效/错型号/缺固件身份、
  数值与 `Chan Off` 测量、三种错误队列、有效/截断/长度错配/无头/坏头波形。
- [x] **AC-15**: 新增离线测试覆盖帧终止符/空/缺终止符/尾随、身份、测量、错误
  队列、IEEE 块、波形、采样换算、CSV、会话 dry-run、传输选择、采集顺序、文件
  覆盖保护与截图无回读。
- [x] **AC-16**: 新增 `SUPPORT.md` 与 `manifest.json`，记录 `documented`、无实机
  验证、夹具来源、已知限制和波形夹具哈希。
- [x] **AC-17**: 更新 `README.md` 与 `README.zh-CN.md`，在 AFG-2225 行后以相同
  顺序登记 GDS-1000B Skill。
- [x] **AC-18**: 运行离线测试、`quick_validate.py` 与 `npx skills@latest add . --list`，
  记录结果并修复失败项。

## 4. Edge Cases & Boundary Conditions

- 响应可能为空、缺终止符、带多余尾随字节、使用 CR/LF/CRLF/LFCR，或包含非 ASCII
  字节；这些情况必须分类而不是清洗。
- `Chan Off`、`NaN`、`Inf`、带单位后缀的测量值都不是正常数值。
- 错误队列溢出、未知错误码和排版引号必须保留原始 code/message。
- 波形块可能在长度字段、payload、尾部或 `Memory Length` 处不一致；必须 fail
  closed，不得按“最接近”长度读取。
- `:HEADer OFF` 时没有 scale/units；点数和原始码仍可用，但电压必须为空/未验证。
- 10 Mpt 记录约 20 MB；内联样本上限 1 000 000 点，超出必须改用 CSV 流式输出。
- 四通道型号才有以太网、CH3/CH4；两通道型号才有 EXT；型号判断不能只靠命令。
- USB CDC 串口默认参数未在手册声明；`115200 8N1` 必须标记为假设。
- 截图/保存只写仪器端文件；本 Skill 不提供也不声称任何回读通道。
- 可选许可功能（总线解码、数字滤波）在未确认安装时必须是 `UNSUPPORTED` 或
  条件性支持，不能当作默认可用的测量路径。

## 5. Execution & Verification Log

- [x] Initial scaffolding and manual page mapping
- [x] Protocol parser, CLI, fixtures, and expected results
- [x] Optional session helper and dry-run planning
- [x] Reference documents and SKILL.md
- [x] README/zh-CN synchronization
- [x] Offline tests: 149 passed with `PYTHONDONTWRITEBYTECODE=1`
- [x] `quick_validate.py`: passed
- [x] `npx skills@latest add . --list`: GDS-1000B Skill discovered
- [x] No `dist/`, `artifacts/`, or `__pycache__/` created; caches cleaned
- [x] Hardware verification: not performed and not claimed

## 6. Review-Fix Addendum

- [x] Corrected the CSV digest to cover the header row, so `csv_sha256` matches
  the file bytes.
- [x] Corrected oversized-block fixtures in tests to use a valid 9-digit
  length field, and rebuilt the inline-sample-limit test with a real block.
- [x] Fixed a dry-run `str`/`bytes` mismatch in the capture memory query.
- [x] Fixed the session block reader to skip documented whitespace between the
  `Waveform Data;` marker and `#`.
- [x] Corrected `:TRIGger:SOURce` usage (no `:TRIGger:EDGe:SOURce` command) and
  the `:SAVe:SETUp` / `:SAVe:WAVEform` syntax in the references.
- [x] Aligned the TCP CLI with the brief: `--host` plus numeric `--port`, with
  no default port.

## 7. Open Questions

- USB CDC framing defaults are not stated by the manual; the assumed
  `115200 8N1` cannot be promoted without a capture.
- Waveform voltage calibration cannot be resolved from the manual alone; the
  example's scale contradiction requires bench characterization.
- Optional-license availability varies by instrument and cannot be inferred
  from `*IDN?`.
- Screenshot retrieval depends on the operator's file-transfer method and is
  outside SCPI.
