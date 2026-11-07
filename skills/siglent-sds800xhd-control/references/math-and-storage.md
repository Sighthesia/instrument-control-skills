# Math and Storage

本参考页覆盖 `scripts/scope_command_catalog.py` 中的 `:FUNCtion`、`:SAVe`、`:RECall`、`:REF`、`:MEMory`。所有条目均转录自编程手册（`documented`），**不代表已在仪器上硬件验证**。写入是否生效只能以仪器读回为准。

## 使用配置引擎

推荐用 `scripts/configure_scope.py` 管理这些命令：

```bash
python3 scripts/configure_scope.py list --root :FUNCtion
python3 scripts/configure_scope.py list --root :SAVE
python3 scripts/configure_scope.py list --root :RECall
python3 scripts/configure_scope.py list --root :REF
python3 scripts/configure_scope.py list --root :MEMory
```

风险类：
- `display`：大多数数学运算、内存波形显示、参考波形显示设置、标签等
- `file_write`：`:SAVE:*`、`:RECall:REFerence`、`:MEMory<m>:IMPort`（导入外部文件）等写入存储的操作
- `destructive`：`:RECall:SERase`（删除内部存储的用户文件）、`:RECall:FDEFault`（恢复出厂设置）、`:SAVE:DEFault`（将当前设置存为默认）、`:MTESt:RESet`（见掩模测试页）

真实写入必须用 `--write`，并按风险给足 `--allow`。若处于 `Stop` 态需 `--allow-after-stop`。

## :FUNCtion（数学运算）

目录覆盖 `:FUNCtion` 共 43 条（手册印刷 pp. 138-159）。常用操作：

| 命令（目录拼写） | 功能 | 备注 |
|---|---|---|
| `:FUNCtion<x>` | 数学通道使能 | `x` 通常 1..4，视机型而定 |
| `:FUNCtion<x>:OPERation` | 算子：`ADD`、`SUBTract`、`MULTiply`、`DIVision`、`FFT`、`INTegrate`、`DIFF`、`SQRT`、`ERES`、`AVERage`、`ABSolute`、`SIGN`、`IDENtity`、`NEGation`、`EXP`、`TEN`、`LN`、`LOG`、`INTErpolate`、`MAXHold`、`MINHold`、`FILTer` | 选算子后再设置源/参数 |
| `:FUNCtion<x>:SOURce1`、`:SOURce2` | 运算源（`C<n>`、`Z<n>`、`F<x>`、`M<m>`） | 有回读，按实际源选择 |
| `:FUNCtion<x>:FFT:MODE`、`:FFT:POINts`、`:FFT:WINDOW` 等 | FFT 配置 | FFT 参数较多，按目录域校验 |
| `:FUNCtion<x>:INVert` | 反相 | `ON`/`OFF` |
| `:FUNCtion<x>:LABel:TEXT` | 标签（需引号） | `string` 类型，写入需加引号 |

示例：

```bash
python3 scripts/configure_scope.py apply --write --allow display \
  --set ":FUNCtion1 ON" \
  --set ":FUNCtion1:OPERation ADD" \
  --set ":FUNCtion1:SOURce1 C1" \
  --set ":FUNCtion1:SOURce2 C2"
```

```bash
python3 scripts/configure_scope.py apply --write --allow display \
  --set ':FUNCtion1:LABel:TEXT "Math1"'
```

## :SAVe（存储文件）

目录覆盖 `:SAVE` 共 7 条（手册印刷 pp. 201-205）。这些都是文件写入，**风险为 `file_write`**，需 `--allow file_write`。

| 命令（目录拼写） | 功能 | 备注 |
|---|---|---|
| `:SAVE:IMAGe` | 截图（`BMP`/`JPG`/`PNG`，可选反色、是否带菜单） | 多参数，目录标记 `compound`，需要回读难以完全验证，常为 `unverified` |
| `:SAVE:CSV` | 波形数据导出 CSV | 指定源等参数 |
| `:SAVE:BINary` | 二进制波形 |  |
| `:SAVE:MATLab` | MATLAB 格式导出 |  |
| `:SAVE:REFerence` | 保存参考波形到文件 |  |
| `:SAVE:SETup` | 保存设置文件（`*.xml`） |  |
| `:SAVE:DEFault` | 保存为默认设置（`CUSTom`/`FACTory`） | `destructive`，目录中标记为 `destructive` |

路径存储类型：`local/`（内部）、`U-disk0/`（U盘）、`net_storage/`（网络存储器）。**保存到内部时路径须包含 `local`**，未指定路径类型时可能默认到 U 盘。文件扩展名需与所选格式一致。

```bash
# 截图（示例，按实际路径调整）
python3 scripts/configure_scope.py apply --write --allow file_write \
  --set ':SAVE:IMAGe "U-disk0/SIGLENT/test.png",PNG,OFF,MOFf'

# 保存设置
python3 scripts/configure_scope.py apply --write --allow file_write \
  --set ':SAVE:SETup EXTernal,"U-disk0/SIGLENT/config.xml"'

# 将当前设置存为自定义默认（谨慎使用）
python3 scripts/configure_scope.py apply --write --allow destructive \
  --set ":SAVE:DEFault CUSTom"
```

## :RECall（调出设置/参考波形）

目录覆盖 `:RECall` 共 4 条（手册印刷 pp. 196-197）。

| 命令（目录拼写） | 功能 | 风险 | 备注 |
|---|---|---|---|
| `:RECall:SETup` | 从文件调出设置 | `file_write`（按目录分类） | 路径同保存，需授权 |
| `:RECall:REFerence` | 从文件调出参考波形 | `file_write` | 多参数，可能无完整回读 |
| `:RECall:SERase` | 删除内部存储的用户文件（参考波形、设置、模板、自定义默认、复制到AWG产生的波形等） | `destructive` | **不可逆**，务必确认 |
| `:RECall:FDEFault` | 调用出厂设置 | `destructive` | **不可逆**，务必确认 |

```bash
python3 scripts/configure_scope.py apply --write --allow file_write \
  --set ':RECall:SETup EXTernal,"U-disk0/SIGLENT/config.xml"'

python3 scripts/configure_scope.py apply --write --allow destructive \
  --set ":RECall:FDEFault"
```

## :REF（参考波形）

目录覆盖 `:REF` 共 6 条（手册印刷 pp. 198-200），参考波形通常有 A-D（目录用 `<r>` 表示 `A|B|C|D`）。

| 命令（目录拼写） | 功能 | 备注 |
|---|---|---|
| `:REF<r>:DATA` | 操作：`LOAD`、`UNLoad`、`SAVE,<source>` | 保存时需指定源（`C<n>`、`F<x>`、`D<d>`），无回读 |
| `:REF<r>:LABel`、`:REF<r>:LABel:TEXT` | 标签显示与文本 | 文本需引号 |
| `:REF<r>:DATA:SCALe`、`:REF<r>:DATA:POSition` | 参考波形显示比例/位置 | 具体项以 `list --root :REF` 为准 |

示例：

```bash
python3 scripts/configure_scope.py apply --write --allow display \
  --set ":REFA:DATA LOAD"

# 将通道 1 保存到参考波形 A
python3 scripts/configure_scope.py apply --write --allow display \
  --set ":REFA:DATA SAVE,C1"
```

## :MEMory（内存波形）

目录覆盖 `:MEMory` 共 9 条（手册印刷 pp. 186-189），内存波形编号用 `<m>` 表示。

| 命令（目录拼写） | 功能 | 风险 | 备注 |
|---|---|---|---|
| `:MEMory<m>:SWITch` | 显示开关 | `display` |  |
| `:MEMory<m>:HORizontal:*`、`:MEMory<m>:VERTical:*` | 水平/垂直设置 | `display` |  |
| `:MEMory<m>:LABel`、`:MEMory<m>:LABel:TEXT` | 标签 | `display` | 文本需引号 |
| `:MEMory<m>:IMPort` | 从源导入波形 | `file_write`（目录分类） | 源可为通道/函数/其他内存波形或带引号路径（`.bin`） |

```bash
python3 scripts/configure_scope.py apply --write --allow display \
  --set ":MEMory2:SWITch ON" \
  --set ":MEMory2:IMPort C2"
```

## 注意事项

- 路径参数必须用引号（如 `":SAVE:IMAGe \"U-disk0/test.png\",PNG,OFF,MOFf"`）。
- `:SAVE:IMAGe`、`:SAVE:CSV`、`:RECall:REFerence` 等多参数命令引擎标记为 `compound`，只校验形状，**回读未必完全匹配**，常落到 `unverified`，不代表写入失败。
- 写入存储（截图、数据、设置）需 `--allow file_write`；擦除内部文件或恢复出厂/保存默认需 `--allow destructive`。
- 未列入目录的存储相关子命令需 `--allow-unlisted --manual-page N`。
- 所有配置仍需尊重 `Stop/Run` 状态：若仪器停止，默认禁止写入，必要时加 `--allow-after-stop`。
- 证据等级均为 `documented`（手册印刷页），以仪器回读为最终判定。
