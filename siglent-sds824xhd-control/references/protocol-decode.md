# Protocol Decode

Load this reference only when debugging a serial bus. The current Python scripts do not implement a general decoder-command client; the target firmware's documented SCPI query tree and MCP tool coverage are distinct.

## First Determine Existing Decode State

Manual-supported text queries; target response shape was spot-checked on firmware `4.8.12.1.1.6.5`:

| Query | Meaning / caveat |
|---|---|
| `:DECode:BUS1:PROTocol?` | Configured protocol for bus 1. Documented protocols include `IIC`, `SPI`, `UART`, `CAN`, `LIN`, `FLEXray`, `CANFd`, `IIS`, `M1553`, `SENT`, `MANchester`, `ARINC429`/`A429`, and `USB20`; availability may depend on model/options. |
| `:DECode:LIST?` | Current list display selection: `OFF`, `D1`, or `D2`. |
| `:DECode:LIST:LINE?` | Display row setting, integer 1-7; this is a UI row count, not total decoded frame count. |
| `:DECode:LIST<n>:RESult?` | Full ASCII decode-list export for list/bus 1 or 2, comma-separated fields with newline-separated records and a header. Preferred for event analysis. |
| `:DECode:BUS<n>:RESult?` | Visible bus summary as ASCII, comma-separated fields and semicolon-separated frames. It can be incomplete when many decoded events are present. |

On the target during this check, list result returned only the header `I2C, Time, Address, R/W, Data`, while bus summary returned `i2c,address,data;`. These are valid responses but not evidence that useful events exist in the current frame.

## Decode Workflow

1. Snapshot bus enabled state, protocol, list selection, and channel/logic sources using their documented readbacks.
2. If a decoder is already configured, read `LIST<n>:RESult?` first. Parse the header rather than assuming fixed fields; protocol and format change columns.
3. If no decode is configured, request permission before changing it. Configure the selected bus and signal source/threshold/bit rate from known DUT details, then read settings back. Decode configuration changes display/instrument state and is not part of immutable waveform retrieval.
4. Compare decoded event times and error/status fields with the raw waveform around the same time range. Treat an empty list, header-only response, or truncated transport response as “no decoded evidence,” not as a passing protocol.
5. Prefer the full list result over the bus result for root-cause analysis. Keep the bus result only as a short screen-summary check.

## MCP and Option Boundaries

- `safe_scpi_query_tcp` can issue these no-argument text queries because they end in `?`.
- The current MCP tool inventory has no dedicated decode configuration or result parser; use `safe_scpi_query_tcp` for documented scalar/text queries and a raw TCP session if large/multiline responses are truncated by the adapter.
- The available `analyze_uart_csv_file` is host-side waveform analysis, not the scope's protocol decoder. It does not replace decode-list evidence.
- Digital channels are an option on the SDS800X HD family. Do not assume digital decode sources or optional protocol features are installed; read the manual/model/option state first.

## Evidence and Manual Pages

Source: `docs/ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`.

- Decode list selection, row count and list result: printed pp. 68-70.
- Bus result and protocol enumeration: printed pp. 71-72.
- Protocol-specific decoder settings: printed pp. 73-148.
- Model/firmware support table: printed p. 3; digital channels are identified as optional in the command-system index.
