# Anomaly Search and Mask Testing

For long motor captures, use the local analyzer's time-bounded workflow before exporting any edge list to an AI context: `events --start-time/--end-time` locates a bounded set of switching edges, `ringing` screens one selected edge window, and `window` returns the corresponding raw samples. These local tools retain the complete-capture SHA-256 and report when a selected window may truncate the ring-down.

Load this reference when the symptom is intermittent runt/glitch/pulse-width/interval/slope behavior or a compliance/mask failure. These features require setup before reading results; do not enable or reconfigure them while preserving an immutable stopped frame.

## Search Configuration

The queries below report results only for whatever configuration was last active. Search is off by default, so `COUNT?` returning `0` usually means "not configured", not "no anomaly".

```text
:SEARch {ON|OFF}
:SEARch:MODE {EDGE|SLOPe|PULSE|INTerval|RUNT}
:SEARch:COUNT?
:SEARch:EVENt?
```

Per-mode parameters follow the selected mode: `:SEARch:EDGE:*`, `:SEARch:SLOPe:*`, `:SEARch:PULSE:*`, `:SEARch:INTerval:*`, `:SEARch:RUNT:*` (source, slope/polarity, threshold, and upper/lower limits, printed pp. 209-227). Set the mode first, then its parameters, then enable search. Enabling search requires a fresh acquisition before `COUNT?` reflects the configured search.

## Mask Test Results

Mask testing needs a mask and an enabled test before a count is meaningful. `:MTESt:COUNt?` alone cannot pass or fail anything.

```text
:MTESt:MASK:LOAD {INTernal,<num>|EXTernal,<path>}
:MTESt:TYPE {ALL_IN|ALL_OUT|ANY_IN|ANY_OUT}
:MTESt {ON|OFF}
:MTESt?
:MTESt:COUNt?
```

`ALL_IN` passes only when every waveform point is inside the mask; a single point outside fails it. `ALL_OUT`, `ANY_IN`, and `ANY_OUT` invert that logic, so a PASS/FAIL figure is meaningless without the recorded type. Response shape is `FAIL,<n>,PASS,<n>,TOTAL,<n>`; `TOTAL=0` means no evaluated samples, not pass. Mask creation and loading change the mask in use or pull one from an internal slot/external file, so treat them as authorized writes and never overwrite operator masks.

## Writing Search and Mask Configuration

搜索（`:SEARch`，34 条，手册印刷 pp. 207-227）和掩码（`:MTESt`，12 条，pp. 190-195）都已进入 `scope_command_catalog.py`，配置由 `scripts/configure_scope.py` 校验并写入：先对整份计划做预检（解析、索引、取值域、权限），任何一步不合法就整体拒绝、退出码 2、不发送任何字节；通过后每条命令单独一次写入，写后清空 `SYST:ERR?` 并回读比对（手册为该命令记录了查询时）。

两类设置都归 `display` 风险类，需要重复给 `--allow display`；`apply` 默认只试运行，真正落笔必须再加 `--write`。真实写入前会读一次采集状态，处于 Stop 时默认拒绝（退出码 2），除非显式给 `--allow-after-stop` —— 搜索和掩码的价值在“边采集边判定”，通常应让仪器处于触发运行状态再配置。

搜索按模式配置，模式决定后续参数族；模式、源、极性/斜率、阈值、上下限的顺序不要颠倒：

| 模式 | 参数族（目录拼写） | 手册印刷页 |
|---|---|---|
| `EDGE` | `:SEARch:EDGE:SOURce`、`:SLOPe`（`RISing`/`FALLing`/`ALTernate`）、`:LEVel` | pp. 209-210 |
| `SLOPe` | `:SEARch:SLOPe:SOURce`（手册限 `C<n>`）、`:SLOPe`、`:HLEVel`/`:LLEVel`、`:LIMit`、`:TUPPer`/`:TLOWer` | pp. 211-214 |
| `PULSE` | `:SEARch:PULSe:SOURce`、`:POLarity`、`:LEVel`、`:LIMit`、`:TUPPer`/`:TLOWer` | pp. 216-219 |
| `INTerval` | `:SEARch:INTerval:SOURce`、`:SLOPe`、`:LEVel`、`:LIMit`、`:TUPPer`/`:TLOWer` | pp. 220-223 |
| `RUNT` | `:SEARch:RUNT:SOURce`（仅 `C<n>`）、`:POLarity`、`:HLEVel`/`:LLEVel`、`:LIMit`、`:TUPPer`/`:TLOWer` | pp. 224-227 |

`LIMit` 取 `LESSthan`、`GREATerthan`、`INNer`、`OUTer`，决定上下限是单边门限还是双边窗口；解释 `COUNT?` 前必须先确认模式与 `LIMit`。`:SEARch:COPY`（`FROMtrigger`、`TOTRigger`、`CANCel`，p. 208）让触发设置与搜索设置同步，**没有回读**，在引擎里只能落到 `unverified`；`TOTRigger` 会改写触发配置，目录虽把它归为 `display`，这个操作应按采集上下文类授权对待。

掩码：先有模板，再开测试，最后计数才有意义。

| 操作 | 命令 | 文档参数域 | 风险类 / 可证明性 | 手册印刷页 |
|---|---|---|---|---|
| 由波形生成模板 | `:MTESt:MASK:CREate` | `<XMARgin>,<YMARgin>`，如 `0.8,0.08` | `display`；无回读 → `unverified` | p. 193 |
| 载入模板 | `:MTESt:MASK:LOAD` | `INTernal,<1..4>` 或 `EXTernal,"<path>.msk/.smsk"` | `display`；无回读 → `unverified` | p. 193 |
| 判定类型 | `:MTESt:TYPE` | `ALL_IN`、`ALL_OUT`、`ANY_IN`、`ANY_OUT` | `display`；有回读 | p. 195 |
| 测试开关 | `:MTESt` / `:MTESt:OPERate` | `ON`、`OFF` | `display`；有回读 | pp. 190, 194 |
| 失败即停 | `:MTESt:FUNCtion:SOF` | `ON`、`OFF` | `display`；有回读；开启后会**停止采集** | p. 192 |
| 失败存帧 | `:MTESt:FUNCtion:FTH` | `ON`、`OFF` | `display`；有回读；失败帧写入历史波形 | p. 191 |
| 失败截图 | `:MTESt:FUNCtion:COF` | `ON`、`OFF` | `display`；有回读；开启后**在 `SIGLENT/` 下写截图文件** | p. 191 |
| 蜂鸣器 / 信息显示 | `:MTESt:FUNCtion:BUZZer` / `:MTESt:IDISplay` | `ON`、`OFF` | `display`；有回读 | pp. 190, 192 |
| 模板源 | `:MTESt:SOURce` | `C<n>`、`Z<n>` | `display`；有回读 | p. 194 |
| 重置测试 | `:MTESt:RESet` | 无参数 | **`destructive`**；无回读 | p. 194 |

掩码文件路径（`local/`、`U-disk0/`、`net_storage/`）属于文件写操作的范畴：`:MTESt:MASK:LOAD` 自身只**读**文件，所以目录给的是 `display`；本版手册和目录里没有 `:MTESt:MASK:SAVE` 一类命令，模板只能由波形边距生成或从已有 `.msk/.smsk` 载入，不要在计划里安排一步不存在的“保存模板”。` :MTESt:SOURce <C<n>|Z<n>>`（p. 194）已纳入目录，风险 `display`，有回读。

```text
# 试运行：RUNT 欠幅搜索，下限 20 ns
python3 scripts/configure_scope.py apply --allow display --set ":SEARch:MODE RUNT" --set ":SEARch:RUNT:SOURce C1" --set ":SEARch:RUNT:POLarity POSitive" --set ":SEARch:RUNT:TLOWer 20e-9" --set ":SEARch ON"

# 真实写入（先让仪器运行；之后重新采集，COUNT? 才反映新配置）
python3 scripts/configure_scope.py apply --write --allow display --set ":SEARch:MODE RUNT" --set ":SEARch:RUNT:SOURce C1" --set ":SEARch ON"

# 模板测试：生成模板 -> 选类型 -> 开操作 -> 开测试
python3 scripts/configure_scope.py apply --write --allow display --set ":MTESt:MASK:CREate 0.8,0.08" --set ":MTESt:TYPE ALL_IN" --set ":MTESt:OPERate ON" --set ":MTESt ON"

# 载入已存在的外部模板
python3 scripts/configure_scope.py apply --write --allow display --set ':MTESt:MASK:LOAD EXTernal,"U-disk0/SIGLENT/compliance.msk"'

# 重置模板测试
python3 scripts/configure_scope.py apply --write --allow destructive --set ":MTESt:RESet"
```

证明方式：搜索与掩码的使能、模式、源、阈值、类型、功能开关都有手册查询，写入可判 `verified`；`MASK:CREATe`、`MASK:LOAD`、`:MTESt:RESet`、`:SEARch:COPY` 没有回读，只能判 `unverified`。功能证据仍是重新采集后的 `:SEARch:COUNT?` 和 `:MTESt?`（`FAIL,<n>,PASS,<n>,TOTAL,<n>`），配置回读替代不了它们。

## History

Manual-supported, target query is conditional:

```text
:HISTORy:TIME?
```

Returns `HH:MM:SS.ffffff` for the currently selected history frame. This does not contain a calendar date; pair it with `:SYSTem:DATE?`/`:SYSTem:TIME?` when wall-clock time matters. A timeout can mean there is no valid selected history frame or the feature is inactive; do not automatically classify the command as unsupported. History frame selection/playback changes instrument view and must not be used during an immutable read. 历史功能的配置入口见 `counter-cursor-and-history.md` 的 History 一节。

## Interpretation Rules

- Zero search events only means none were found under the currently active search setup and current screen context.
- A nonzero count identifies candidates, not proof of circuit root cause. Retrieve the event waveform/segment and compare it with trigger and threshold conditions.
- Mask results need a nonzero `TOTAL` and a known mask/test configuration before PASS/FAIL is meaningful.
- Preserve the acquisition setup and command log alongside the result so event counts can be reproduced.

## Evidence and Manual Pages

Source: `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Search enable, mode, count, event, copy and mode-specific configuration: printed pp. 207-227.
- Mask test switch, function switches, mask create/load, operate, reset, type, source: printed pp. 190-195.
- History frame timestamp: printed p. 163.
- Catalog coverage: `:SEARch` 34 条 pp. 207-227、`:MTESt` 12 条 pp. 190-195（`python3 scripts/configure_scope.py list --root :SEARch|:MTESt`）；条目是 `documented`，不是 `hardware-verified`。
