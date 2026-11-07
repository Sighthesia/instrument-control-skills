# Protocol Decode

Load this reference only when debugging a serial bus. `scripts/read_decode_list.py` fetches the documented decode queries read-only over raw SCPI TCP port 5025 (it never changes scope state). Protocol-specific decoder *configuration* (enable, source/threshold/bit-rate, protocol settings) still requires the raw SCPI tree and explicit user authorization; see manual pp. 73-148.

## First Determine Existing Decode State

Manual-supported text queries; target response shape was spot-checked on firmware `4.8.12.1.1.6.5` (SDS824X HD):

| Query | Meaning / caveat |
|---|---|
| `:DECode:BUS1:PROTocol?` | Configured protocol for bus 1. Documented protocols include `IIC`, `SPI`, `UART`, `CAN`, `LIN`, `FLEXray`, `CANFd`, `IIS`, `M1553`, `SENT`, `MANchester`, `ARINC429`/`A429`, and `USB20`; availability may depend on model/options. |
| `:DECode:LIST?` | Current list display selection: `OFF`, `D1`, or `D2`. |
| `:DECode:LIST:LINE?` | Display row setting, integer 1-7; this is a UI row count, not total decoded frame count. |
| `:DECode:LIST<n>:RESult?` | Full ASCII decode-list export for list/bus 1 or 2, comma-separated fields with newline-separated records and a header. **Preferred for event analysis.** |
| `:DECode:BUS<n>:RESult?` | Visible bus summary as ASCII, comma-separated fields and semicolon-separated frames. It can be incomplete when many decoded events are present; use only as a screen-summary check. |

**Use the documented `:DECode:...` / `DECode:...` tree. Do not guess command names or invent nodes/headers.** `firmware-scoped` (SDS824X HD, firmware `4.8.12.1.1.6.5`, SCPI TCP 5025): guessed forms such as `DEC1?`, `DEC1:STAT?`, `DEC1:TYPE?`, `DEC1:SPI?`, `DEC:SPI?`, `DEC:A:*`, `D1:*` are **not** valid queries for this instrument. An undefined-header *query* returns **0 bytes** and queues `-113,"Undefined header;..."`; a naive `readline()` then waits forever and times out. `DEC?` / `DECODE?` may report global decode on/off (`ON` observed) but **do not** enumerate buses or return decode lists. Manual short forms shown by the programming guide (for example `DEC:LIST1:RES?`) remain valid; the rule is to avoid invented headers/nodes, not to forbid documented short forms. When a query returns no data, open a fresh connection and drain `SYST:ERR?` until `0,"No error"` to confirm the cause (stale backlog can mislead).

On the target, `LIST?=D1`, `BUS1:PROTocol?=SPI`, `BUS2:PROTocol?=IIC`. `LIST1:RESult?` returned a full SPI table (`SPI, Time, MISO, MOSI` header + records); `BUS2/LIST2` returned I2C header/empty summary only — valid responses but not evidence that useful I2C events exist in the current frame. A header-only or empty result is "no decoded evidence", not a passing protocol.

## Decode Workflow

1. Snapshot bus enabled state, protocol, list selection, and channel/logic sources using their documented readbacks.
2. If a decoder is already configured, read `LIST<n>:RESult?` first. Parse the header rather than assuming fixed fields; protocol and format change columns.
3. If no decode is configured, request permission before changing it. Configure the selected bus and signal source/threshold/bit rate from known DUT details, then read settings back. Decode configuration changes display/instrument state and is not part of immutable waveform retrieval.
4. Compare decoded event times and error/status fields with the raw waveform around the same time range. Treat an empty list, header-only response, or truncated transport response as “no decoded evidence,” not as a passing protocol.
5. Prefer the full list result over the bus result for root-cause analysis. Keep the bus result only as a short screen-summary check.

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
- Bus result and protocol enumeration: printed pp. 71-72.
- Protocol-specific decoder settings: printed pp. 73-148.
- Model/firmware support table: printed p. 3; digital channels are identified as optional in the command-system index.
