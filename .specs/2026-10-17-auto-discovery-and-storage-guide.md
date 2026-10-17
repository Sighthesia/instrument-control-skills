# Spec Contract: Scope Auto-Discovery and Storage Guidance

- **Created**: 2026-10-17
- **Status**: Completed
- **Target Files/Modules**: `siglent-sds800xhd-control/references/connection-and-storage.md`, `siglent-sds800xhd-control/scripts/discover_scope.py`, `siglent-sds800xhd-control/SKILL.md`, `siglent-sds800xhd-control/scripts/test_discover_scope.py`

## 1. Core Objective
将 SDS800X HD 的 USB/LAN 自动发现、身份握手、基础连接配置，以及示波器文件/波形传输方案整理为可执行的工程指导，并提供不改变既有采集安全约束的最小 Python 示例。

## 2. Hard Constraints & Negative Rules (Non-negotiables)
- [x] **C-01**: 不把 USB Device 端口描述为 USB Mass Storage/U 盘，也不提供未经手册支持的 MSC 切换命令。
- [x] **C-02**: Raw SCPI LAN 连接默认使用 TCP `5025`；不得把 legacy `5024` 当作普通 SCPI 查询端口。
- [x] **C-03**: 自动发现必须使用 `*IDN?` 做厂商/型号确认；单次探测失败不得中断整个扫描。
- [x] **C-04**: 发现工具不自动修改 IP、触发采集、改变示波器状态或挂载网络共享；所有写操作必须由调用者显式执行。
- [x] **C-05**: 二进制响应必须按 IEEE 488.2 definite-length block 读取，不能用按行读取替代。
- [x] **C-06**: 不把未经目标固件验证的 VISA/VXI-11 广播、SMB/NFS 参数或路径语法写成必然可用；文档必须标出验证边界。

## 3. Atomized Acceptance Criteria (Checklist)
- [x] **AC-01**: 指导文档说明 USBTMC/VISA、LAN raw socket、VXI-11 的角色、前置 USB Host 与后置 USB Device 的区别。
- [x] **AC-02**: 指导文档给出 USB 自动发现、LAN 已知网段探测和已知 IP 连接的可执行流程，并包含超时、权限、空结果和多设备处理。
- [x] **AC-03**: 指导文档说明 `*IDN?` 校验、连接后只读快照，以及连接配置命令的授权边界。
- [x] **AC-04**: 指导文档比较网络存储挂载与电脑端直传两条数据路径，明确何时使用各自方案及安全注意事项。
- [x] **AC-05**: 提供 `discover_scope.py`，支持 USB VISA（可选依赖）、LAN raw 探测、指定地址连接，并输出 JSON 结果。
- [x] **AC-06**: 工具不会默认执行危险/有副作用命令；LAN 探测按 `*IDN?\n` 握手并关闭连接。
- [x] **AC-07**: 为发现工具添加离线测试，覆盖 IDN 匹配、无效响应、超时/连接失败和 JSON 输出核心逻辑。
- [x] **AC-08**: `SKILL.md` 的渐进式参考表和资源列表包含新指导与工具，并保留现有 capture workflow 约束。
- [x] **AC-09**: 运行离线测试、`git diff --check`，并更新本合同的验证状态。

## 4. Edge Cases & Boundary Conditions
- USB VISA 不可用、未安装 PyVISA 或没有 VISA backend 时，工具应给出可读错误而不是假装 USB 为空。
- 同一网络中有多个 Siglent 设备时必须返回全部候选，不隐式选择第一台。
- LAN 设备可能返回启动 banner、空行或非 ASCII 数据；握手只接受可解析的 `*IDN?` 文本。
- 用户提供的网段可能过大；默认限制探测地址数，避免无界扫描。
- 设备型号匹配应允许 `SDS800X HD` 系列变体，但厂商标识不匹配时不能标记为目标示波器。
- 网络共享凭据不得写入日志、JSON 或命令行示例中的真实值。
- `:SYSTem:NSTorage` 和 `:SAVE` 命令的具体参数/路径必须以目标固件手册为准，文档不宣称跨固件通用。

## 5. Execution & Verification Log
- [x] Initial scaffolding
- [x] Implementation
- [x] Automated tests / manual verification: `python3 -m unittest discover -s . -p 'test_*.py'` (39 passed), `py_compile`, `git diff --check`, and local `--usb` dependency-path check.
