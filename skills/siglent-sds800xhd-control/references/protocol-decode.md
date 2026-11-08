# Protocol Decode

Load this reference only when debugging a serial bus. `scripts/read_decode_list.py` fetches the documented decode queries read-only over raw SCPI TCP port 5025 (it never changes scope state). Decoder *configuration* (enable, protocol selection, source/threshold/bit rate, format, list display) is catalogued and written through `scripts/configure_scope.py` against `scope_command_catalog.py`（`:DECode` 91 条，手册印刷 pp. 68-120）；写入仍需显式授权，见下面 “Decoder Configuration”。

## First Determine Existing Decode State

Manual-supported text queries; target response shape was spot-checked on firmware `4.8.12.1.1.6.5` (SDS824X HD):

| Query | Meaning / caveat |
|---|---|
| `:DECode:BUS1:PROTocol?` | Configured protocol for bus 1. Documented protocols include `IIC`, `SPI`, `UART`, `CAN`, `LIN`, `FLEXray`, `CANFd`, `IIS`, `M1553`, `SENT`, `MANchester`, `ARINC429`/`A429`, and `USB20`; availability may depend on model/options. |
| `:DECode:LIST?` | Current list display selection: `OFF`, `D1`, or `D2`. |
| `:DECode:LIST:LINE?` | Display row setting, integer 1-7; this is a UI row count, not total decoded frame count. |
| `:DECode:LIST<n>:RESult?` | Full ASCII decode-list export for list/bus 1 or 2, comma-separated fields with newline-separated records and a header. **Preferred for event analysis.** |
| `:DECode:BUS<n>:RESult?` | Visible bus summary as ASCII, comma-separated fields and semicolon-separated frames. It can be incomplete when many decoded events are present; use only as a screen-summary check. |

**Use only documented or manual-mapped decode commands for the connected model/firmware. Do not invent command nodes or headers.** Query spelling must come from the programming guide, a documented short form, or a readback you have verified on the instrument. `firmware-scoped` (SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP 5025): guessed forms such as `DEC1?`, `DEC1:STAT?`, `DEC1:TYPE?`, `DEC1:SPI?`, `DEC:SPI?`, `DEC:A:*`, `D1:*` are **not** valid queries for this instrument. An undefined-header *query* returns **0 bytes** and queues `-113,"Undefined header;..."`; a naive `readline()` then waits forever and times out. `DEC?` / `DECODE?` may report global decode on/off (`ON` observed) but **do not** enumerate buses or return decode lists. Manual short forms shown by the programming guide (for example `DEC:LIST1:RES?`) remain valid; the rule is to avoid invented headers/nodes, not to forbid documented short forms. On some firmware, an undefined-header *query* returns no bytes and queues an error, so a line-oriented reader can hang and desynchronize the session; when a query returns no data, open a fresh connection and drain `SYST:ERR?` until `0,"No error"` to confirm the cause (stale backlog can mislead). A global decode enable/state query is not a substitute for bus/protocol selection or `LIST/BUS RESult?`.

On the target, `LIST?=D1`, `BUS1:PROTocol?=SPI`, `BUS2:PROTocol?=IIC`. `LIST1:RESult?` returned a full SPI table (`SPI, Time, MISO, MOSI` header + records); `BUS2/LIST2` returned I2C header/empty summary only — valid responses but not evidence that useful I2C events exist in the current frame. A header-only or empty result is "no decoded evidence", not a passing protocol.

## STOP: Read configured decode results before host-side reconstruction

If a decoder is configured (for example `:DECode:BUS1:PROTocol?` returns a protocol, or `DEC?`/`DECODE?` and `:DECode:LIST?` indicate active decode), read `:DECode:LIST<n>:RESult?` **before** writing any host-side bit/byte reconstruction from raw samples. A hand-rolled edge sampler can disagree with the instrument decoder because it cannot know the decoder's frame boundary, sample point, threshold/source assignment, mode, or bit order from waveform samples alone; it can produce plausible-looking but wrong bytes and send the investigation in the wrong direction. Treat the scope's decode list as primary evidence and host-side analysis as a cross-check, not a replacement.

## Decode Workflow

1. Send `*IDN?` (if not already known), then snapshot bus enabled/list/protocol state (`DEC?`/`:DECode:LIST?`/`:DECode:BUS<n>:PROTocal?` as available).
2. If a decoder is already configured, read `LIST<n>:RESult?` first (full table, multiline). Parse the header rather than assuming fixed fields; protocol and format change columns.
3. If no decode is configured, request permission before changing it. Configure the selected bus and signal source/threshold/bit rate from known DUT details（用 `configure_scope.py apply`，每条命令一次写入并回读）, then read settings back. Decode configuration changes display/instrument state and is not part of immutable waveform retrieval.
4. Compare decoded event times and error/status fields with the raw waveform around the same time range. Treat an empty list, header-only response, truncated transport response, or `truncated_risk` result as “no decoded evidence,” not as a passing protocol.
5. Prefer the full list result over the bus result for root-cause analysis. Keep the bus result only as a short screen-summary check.

## Decoder Configuration

`scope_command_catalog.py` 已经收录整个 `:DECode` 子树（91 条，手册印刷 pp. 68-120），因此协议专用配置不再需要手写 SCPI：`scripts/configure_scope.py` 先按目录校验每一步，再一条命令一次 TCP 写入，每条写后清空错误队列，并按手册记录的回读比对。证据等级 `documented`（手册印刷 p. N），**没有在仪器上实测**；某条写入是否真的生效，只以仪器回读为准。

排步骤时按“先协议、后该协议参数、最后显示”的顺序，因为协议专用参数只在所选协议下有意义：

| 步骤 | 命令（目录拼写） | 文档参数域 | 手册印刷页 |
|---|---|---|---|
| 解码总开关 | `:DECode` | `ON`、`OFF` | p.68 |
| 选协议 | `:DECode:BUS<n>:PROTocol` | `IIC`、`SPI`、`UART`、`CAN`、`LIN`、`FLEXray`、`CANFd`、`IIS`、`M1553`、`SENT`、`MANchester`、`ARINC429`、`USB20` | p.71 |
| 数据显示格式 | `:DECode:BUS<n>:FORMat` | `BINary`、`DECimal`、`HEX`、`ASCii` | p.71 |
| 源与阈值（UART） | `:DECode:BUS<n>:UART:TXSource` / `:RXSource` / `:TXTHreshold` | `C<n>`、`D<d>`、`DIS` / 数值 | pp.87-89 |
| 波特率与位序 | `:DECode:BUS<n>:UART:BAUD` / `:BITorder` | `600bps`…`115200bps`、`CUSTom,<value>` / `LSB`、`MSB` | p.85 |
| 帧结构 | `:DECode:BUS<n>:UART:PARity` / `:STOP` / `:DLENgth` / `:IDLE` | `NONE`…`SPACe` / `1`、`1.5`、`2` / `[5,8]` / `LOW`、`HIGH` | pp.86-87 |
| SPI 时钟与片选 | `:DECode:BUS<n>:SPI:CLKSource` / `:CLKThreshold` / `:LATChedge` / `:CSTYpe` | `C<n>`、`D<d>` / 数值 / `RISing`、`FALLing` / `NCS`、`CS`、`TIMeout` | pp.76-80 |
| 列表显示 | `:DECode:LIST` / `:DECode:LIST:LINE` / `:DECode:LIST:SCRoll` | `OFF`、`D1`、`D2` / `[1,7]` / 整数 | pp.68-69 |
| 结果读回 | `:DECode:LIST<n>:RESult?` / `:DECode:BUS<n>:RESult?` | 只读 | pp.70-72 |

```text
# 只读：先看当前协议与波特率，不写任何东西
python3 scripts/configure_scope.py show :DEC:BUS1:PROT? :DEC:BUS1:UART:BAUD?

# 试运行：只做校验并打印线序计划，不连仪器
python3 scripts/configure_scope.py apply --allow display --set ":DECode ON" --set ":DECode:BUS1:PROTocol UART"

# 真实写入：每条命令写后回读
python3 scripts/configure_scope.py apply --write --allow display --set ":DECode:BUS1:UART:BAUD 9600bps"

# 列表显示：选总线 1、显示 3 行、定位第 3 行
python3 scripts/configure_scope.py apply --write --allow display --set ":DECode:LIST D1" --set ":DECode:LIST:LINE 3" --set ":DECode:LIST:SCRoll 3"
```

回读与解释上的坑：

- `:DECode` 下 91 条目录项除 `:DECode:BUS<n>:COPY` 外都有手册查询，`apply` 会逐条回读，因此这些写入可以判到 `verified`；`:DECode:BUS<n>:COPY`（`FROMtrigger`、`TOTRigger`，p.71）没有回读，只能是 `unverified`，而且 `TOTRigger` 会改写触发配置。
- 写 `ARINC429`，回读是短形式 `A429`（手册返回格式，p.72）。这是正常的；但反过来不行：`--set ":DECode:BUS1:PROTocol A429"` 会在预检阶段被拒（`A429` 不是设置枚举项）。触发侧 `:TRIGger:TYPE` 的枚举反而是 `A429`，两侧拼写不能互换。
- 写 `CUSTom,<value>` 后回读是纯数值（例如 `1000000`）；引擎按 1e-6 相对容差比较，不要按字符串比对判失败。
- 配置回读只证明“参数被接受”，不证明协议在跑。功能证据仍只有 `:DECode:LIST<n>:RESult?` / `:DECode:BUS<n>:RESult?`：空响应或只有表头表示当前帧没有解码事件，既不是配置失败，也不是协议通过。
- 本版手册里 `ARINC429`、`USB20` 只有 `:PROTocol` 枚举，没有协议专用参数子节；型号/选件是否支持某协议仍查 `*IDN?` 与手册机型支持表（p.3）。数字通道 `D<d>` 属选件，不要假设存在。

## Transport and Option Boundaries

- Use the raw TCP session (port 5025) for these text queries. `LIST<n>:RESult?` / `BUS<n>:RESult?` are **multi-line ASCII text** (not IEEE 488.2 definite-length blocks): `LIST` returns a header plus newline-separated records; `BUS` returns semicolon-separated frames and may span multiple lines. A line-oriented `readline()` returns only the first line (often just the header) and leaves the rest in the socket buffer, which **desynchronizes every later read**. Read the *entire* response and report completeness/truncation risk explicitly.
- Practical pattern (observed on SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP 5025): send `*IDN?` first, then send one query and `recv` with a normal **first-byte timeout**; after the first byte arrives, use a short **idle timeout** (e.g. 0.4–0.8 s) to detect the end. Idle timeout is a heuristic, not a length delimiter: keep `end_reason`/`likely_complete` (or equivalent) and treat a response without a final newline or with an unexpected end as incomplete/no complete decoded evidence. `scripts/read_decode_list.py` implements this read-only path and drains `SYST:ERR?` on 0-byte replies.
  ```python
  s.sendall(b":DECode:LIST1:RESult?\n")
  s.settimeout(4.0)   # first-byte timeout
  chunks = []
  while True:
      try:
          d = s.recv(65536)
          if not d:
              end = "closed"; break
          chunks.append(d)
          s.settimeout(0.6)  # idle timeout after first byte
      except socket.timeout:
          end = "idle_timeout" if chunks else "first_byte_timeout"; break
  raw = b"".join(chunks)
  complete = raw.endswith(b"\n") and end in ("idle_timeout", "closed")
  text = raw.decode("utf-8", "replace")  # header + all records when complete
  ```
- Host-side UART/SPI waveform analysis is separate from the scope's protocol decoder. It does not replace decode-list evidence.
- Digital channels are an option on the SDS800X HD family. Do not assume digital decode sources or optional protocol features are installed; read the manual/model/option state first.

## Evidence and Manual Pages

Source: `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Decode list selection, row count and list result: printed pp. 68-70.
- Bus result, decode format and protocol enumeration: printed pp. 71-72.
- Protocol-specific decoder settings (`:DECode:BUS<n>:{IIC,SPI,UART,CAN,LIN,FLEXray,CANFd,IIS,M1553,SENT,MANchester}:*`): printed pp. 73-120.
- Catalog coverage: `:DECode` 91 条，pp. 68-120（`python3 scripts/configure_scope.py list --root :DECode`）；条目是 `documented`，不是 `hardware-verified`。
- Model/firmware support table: printed p. 3; digital channels are identified as optional in the command-system index.
