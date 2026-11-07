# Counter, Cursor, and History

Load this reference only for precision frequency/period statistics, manually marked deltas, or a timestamp associated with an existing history frame. These commands are not needed for ordinary waveform capture.

## Counter

Manual-supported; target `:COUNter:CURRent?` returned `0.00E+00` and statistics returned `OFF` in the observed inactive/default state.

The counter is off by default. Reading `CURRent?` without enabling it returns a zero that looks like a measurement. Enable it first, and treat a zero as "no result" until the enable state and source are recorded.

```text
:COUNter {ON|OFF}                       # counter enable
:COUNter:MODE {FREQuency|PERiod|TOTalizer}
:COUNter:SOURce <channel>
:COUNter:LEVel <level>                  # counter trigger level
:COUNter:CURRent?
:COUNter:STATistics {ON|OFF}
:COUNter:STATistics:RESet
:COUNter:STATistics:VALue?
```

Totalizer mode has its own gate controls, which are required before a totalizer reading means anything:

```text
:COUNter:TOTalizer:GATE {ON|OFF}
:COUNter:TOTalizer:GATE:TYPE ...
:COUNter:TOTalizer:GATE:LEVel <level>
:COUNter:TOTalizer:GATE:SLOPe {RISe|FALL}
:COUNter:TOTalizer:SLOPe {RISe|FALL}
:COUNter:TOTalizer:RESet
```

The counter measures analog-channel input only. `MODE?` reports `FREQuency`, `PERiod`, or `TOTalizer`; `SOURce?` identifies the channel. Current value meaning depends on that mode. Statistics value format in frequency/period mode is:

```text
<current>,<mean>,<min>,<max>,<stdev>,<count>
```

It returns `OFF` if statistics are disabled, and statistics are documented only for frequency and period modes. Enabling/configuring the counter or statistics is state-changing; request authorization, configure source/mode, enable statistics if required, then query. `:FORMat:DATA` controls numeric precision; the counter's stated measurement precision is 7 digits, while default returned significant digits are 3 — set `:FORMat:DATA CUSTom,7` if you need that precision.

## Cursor

Manual-supported. A spot probe on the target timed out when cursor readouts were queried with cursors inactive. Enable/configure cursors only when requested; do not treat an inactive-cursor timeout as evidence that the SCPI command is unsupported.

```text
:CURSor {ON|OFF}
:CURSor:MODE {TRACk|MANual,{X|Y|XY}|MEASure}
:CURSor:SOURce1 <source>
:CURSor:SOURce2 <source>
:CURSor:X1 <value>
:CURSor:X2 <value>
:CURSor:Y1 <value>
:CURSor:Y2 <value>
:CURSor:X1?
:CURSor:X2?
:CURSor:XDELta?
:CURSor:IXDelta?
:CURSor:Y1?
:CURSor:Y2?
:CURSor:YDELta?
```

- Cursors must be enabled and the mode/sources set before positions or deltas mean anything; the target timed out on inactive-cursor queries.
- `MODE?` distinguishes `TRACk`, `MANual`, and `MEASure`; manual mode also has `X`, `Y`, or `XY` selection.
- `XDELta?` returns `X2-X1` in seconds.
- `IXDelta?` returns `1/(X2-X1)` in Hz.
- `YDELta?` returns `Y2-Y1` in the channel's vertical unit.

Multi-cursor families (`:CURSor:MANual:X<n>`, `:CURSor:MANual:Y<n>`, `:CURSor:MEASure<n>`, `:CURSor:TRACk<n>`, `:CURSor:XY:Y<n>`) exist on printed pp. 46-67 and are not reproduced here. Cursor placement/mode commands change display state.

## History

History is a buffer of past acquisitions, not a timestamp log. Enable it, then select and play frames. Reading `:HISTORy:TIME?` without an active selection is a conditional query, not proof the feature is unsupported.

```text
:HISTORy {ON|OFF}
:HISTORy:FRAMe <value>
:HISTORy:FRAMe?
:HISTORy:INTERval <value>
:HISTORy:LIST?
:HISTORy:PLAY ...
:HISTORy:TIME?
```

Frame count depends on memory depth: more points per frame means fewer stored frames. `:HISTORy:TIME?` returns `HH:MM:SS.ffffff` with no calendar date, so pair it with `:SYSTem:DATE?` and `:SYSTem:TIME?` (printed pp. 232, 238) when a wall-clock timestamp matters. Selecting or playing a frame changes the instrument view, so it is forbidden during an immutable read.

### 通过引擎写入历史配置

`:HISTORy` 的 6 条命令（pp. 161-163）都在 `scope_command_catalog.py` 里，风险类全部是 `display`，而且每条都有手册查询，所以 `apply --write` 能把它们判到 `verified`：

| 命令 | 文档参数域 | 语义 | 手册印刷页 |
|---|---|---|---|
| `:HISTORy` | `ON`、`OFF` | 历史存储总开关 | p. 161 |
| `:HISTORy:FRAMe` | 整型帧号 | 选中哪一帧 | p. 161 |
| `:HISTORy:INTERval` | `[1.00E-06, 1]` | **回放**间隔，不是采样间隔 | p. 162 |
| `:HISTORy:LIST` | `OFF`、`ON[,TIME\|DELTa]` | 列表开关；`TIME` 按采样时间、`DELTa` 按采样间隔显示 | p. 162 |
| `:HISTORy:PLAY` | `BACKWards`、`PAUSe`、`FORWards` | 回放方向 / 暂停 | p. 163 |
| `:HISTORy:TIME?` | 只读 | 当前帧时间戳 | p. 163 |

顺序和前提：先 `:HISTORy ON`，然后**让仪器继续采集**才会产生帧；只使能不采集，`FRAMe?`/`TIME?` 读到的仍是旧状态或空状态，这类“0 帧/超时”说明没有可用的历史数据，不是命令不支持。可存帧数与存储深度相关，深存储下帧数会显著减少。

```text
# 只读：当前帧号、时间戳、列表状态
python3 scripts/configure_scope.py show :HISTORy:FRAMe? :HISTORy:TIME? :HISTORy:LIST?

# 开启历史存储（要产生帧仍需继续采集）
python3 scripts/configure_scope.py apply --write --allow display --set ":HISTORy ON"

# 已停采且有帧时浏览：先暂停回放，再选帧、切列表显示方式
python3 scripts/configure_scope.py apply --write --allow display --allow-after-stop --set ":HISTORy:PLAY PAUSe" --set ":HISTORy:FRAMe 10" --set ":HISTORy:LIST ON,DELTa"
```

注意两点：`:HISTORy:LIST ON,DELTa` 的尾参数不做预校验（枚举前缀命令），只有回读能确认实际模式；选帧与回放会改变仪器视图，**不可变读取期间禁止执行**，需要浏览时应在证据已归档的独立会话里做。真实写入遇到 Stop 态默认被拒，`--allow-after-stop` 只加在 `apply` 上，`plan` 不接受该参数。

## Evidence and Manual Pages

Source: `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Counter enable, level, modes, current value, statistics, totalizer gate: printed pp. 31-36.
- Cursor enable, mode, sources, positions, deltas, multi-cursor families: printed pp. 38-67.
- History enable, frame, interval, list, play, timestamp: printed pp. 161-163.
