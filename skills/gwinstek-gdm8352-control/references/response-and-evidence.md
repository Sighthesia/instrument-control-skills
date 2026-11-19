# Response Parsing and Evidence

## Parser stages

| Stage | Responsibility |
|---|---|
| Framing | Read exactly one terminated response from the saved bytes. A missing terminator is `INCOMPLETE`; bytes after the first frame are `INVALID`. |
| Metadata | Record response type, terminator, ASCII text, and raw evidence (original bytes, base64, and SHA-256). |
| Payload | Extract the scalar token, text, or comma-separated fields without rewriting the source. |
| Normalization | Convert numeric tokens directly to `Decimal` and map documented text states separately from the raw text. A unit taken from the command is not a unit observed on the wire. |
| Validation | Check field counts, numeric form, unit consistency, and identity as applicable. Report the status of the actual claim, including any semantic gaps. |

Never pad, truncate, clamp, interpolate, guess a missing calibration, or merge a
failed/retried read into a complete result.

## Numeric and text responses

- **IEEE 488.2 numeric tokens:** retain `+0.10466E-01` verbatim as the
  `numeric_token`. For arithmetic use `Decimal('+0.10466E-01')`, which is
  `Decimal('0.010466')`; never round-trip through `float`. The artifact stores
  `value_decimal` as a JSON-safe string, separate from the original token.
- **`READ?`:** the manual says it returns first- and second-display values
  (PDF p. 130). The fixture has two fields, `+0.00023E-02` and `+0.00000E+00`;
  keep them separate. `READ?` conveys neither display's function nor unit. The
  second field's function and unit stay `UNVERIFIED`; do not label it current,
  voltage, or "zero."
- **`SYST:BEEP:STAT?`:** the three documented texts are `No Beep`,
  `Beep on Pass`, and `Beep on Fail` (PDF p. 133). Only `No Beep` was captured.
  The historical write `SYST:BEEP:STAT OFF` produced no response bytes; that
  silence does not establish a state change. This Skill refuses the setter.
- **`CONF?`:** the captured attempt timed out without receiving a byte, not
  even an EOL. This is an invalid query, not an instrument fault or an empty
  response line. For the documented query forms, see
  [command-reference.md](command-reference.md).

## Integrity statuses

| Status | Meaning |
|---|---|
| `COMPLETE` | Framing and every required field agree with the stated claim. |
| `INCOMPLETE` | A terminator, field, or value is missing. |
| `INVALID` | The bytes contradict a framing, numeric, unit, or identity rule. |
| `UNVERIFIED` | Parsing succeeded but a semantic or completeness claim cannot be proven (second `READ?` display, unitless response, return layout). |
| `UNSUPPORTED` | The query or response shape is not implemented. |

## Fixture provenance

Source: [`assets/fixtures/captures.jsonl`](../assets/fixtures/captures.jsonl).
The 2026-11-19 session used a GW Instek GDM-8352 on USB CDC-ACM `2184:003b`
(`/dev/ttyACM0`), firmware `1.00`, serial `GEP848232`. `Bytes` and `sha256`
refer to the raw files, including the terminator when present. The table
contains six `hardware-verified` query responses and one zero-byte timeout
record for the undocumented `CONF?` probe. That record is not a response and
is not an additional `hardware-verified` command. The silent beeper write is
recorded only in the historical hardware log; it has no fixture row. The
synthetic fixtures under `assets/fixtures/synthetic/` are not captures.

| File | Command | Bytes | sha256 | Captured | Note |
|---|---|---:|---|---|---|
| `idn.txt` | `*IDN?` | 33 | `7101090c136112d7c9398e643cc5d3632bae81eab0595b15220bb71e47026671` | 2026-11-19 | Identity, firmware `1.00`, serial `GEP848232`; device disconnected after capture, not re-tested. |
| `meas-volt-dc.txt` | `MEAS:VOLT:DC?` | 14 | `6380eed705e5ce2f965d4af8cb94e60f15b3b5a3519607d6ade1cbbe843fbf34` | 2026-11-19 | DC voltage; unit from command, no wire suffix; device disconnected after capture, not re-tested. |
| `meas-curr-dc.txt` | `MEAS:CURR:DC?` | 14 | `7ab2c3a3df87ee8480385c406f78e9516cfd0286ce8682b5eb7dcad08892161b` | 2026-11-19 | DC current; unit from command, no wire suffix; device disconnected after capture, not re-tested. |
| `read-two-display.txt` | `READ?` | 27 | `d4aebf352351c0c55f5c162fbb6aa5fefab68949f9c1519857adf0dbba73e869` | 2026-11-19 | Two fields at default sample count; second function and unit `UNVERIFIED`; device disconnected after capture, not re-tested. |
| `syst-beep-stat-no-beep.txt` | `SYST:BEEP:STAT?` | 9 | `a77e2d0f1f3c6212032ba0b1d7bbe2c1e4d45be3380c6ea713d32b037a64f852` | 2026-11-19 | Exact text `No Beep`; device disconnected after capture, not re-tested. |
| `syst-err-command-error.txt` | `SYST:ERR?` | 15 | `524d46fcaf39f33d691eeb890ee6eb9f93c08635304baf54f196f9bee326f74a` | 2026-11-19 | Free text `Command error`, not a numbered queue entry; device disconnected after capture, not re-tested. |
| `conf-query-timeout.empty` | `CONF?` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 2026-11-19 | No bytes within the timeout; not an empty response line; device disconnected after capture, not re-tested. |
