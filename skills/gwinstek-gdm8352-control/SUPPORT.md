# GDM-8352 Support and Evidence

The seven `hardware-verified` rows below are scoped to GW Instek GDM-8352,
firmware `1.00`, serial `GEP848232`, over USB CDC-ACM `2184:003b`
(`/dev/ttyACM0`), captured 2026-11-19. The device was disconnected after capture
and was not re-tested. The six query responses are preserved in
[`assets/fixtures/`](assets/fixtures/); the silent beeper write is recorded only
in the historical hardware log, `artifacts/manuals/ground-truth.md`.

Manual basis: *GDM-8352 User Manual*, GW Instek part no. `82DM-83520E01`;
command tables PDF pp. 99-106, command reference PDF pp. 107-141. Page numbers
are PDF physical pages. See [command-reference.md](references/command-reference.md)
for syntax and [response-and-evidence.md](references/response-and-evidence.md)
for capture provenance. The table describes evidence, not permission to send a
command. The Skill sends only read-only queries in `QUERY_SPECS`; all setters
are refused, including the historical beeper write.

| Command | Evidence | Basis | Notes |
|---|---|---|---|
| `*IDN?` | `hardware-verified` | `idn.txt` | Captured `GWInstek,GDM8352,GEP848232,1.00`. |
| `MEAS:VOLT:DC?` | `hardware-verified` | `meas-volt-dc.txt` | Captured `+0.10466E-01`; no unit suffix. |
| `MEAS:CURR:DC?` | `hardware-verified` | `meas-curr-dc.txt` | Captured `+0.00026E-02`; no unit suffix. |
| `READ?` | `hardware-verified` | `read-two-display.txt` | Two display fields captured; the second display's function and unit are `UNVERIFIED`. |
| `SYST:BEEP:STAT?` | `hardware-verified` | `syst-beep-stat-no-beep.txt` | Only `No Beep` was captured; `Beep on Pass` and `Beep on Fail` are `documented`. |
| `SYST:BEEP:STAT OFF` | `hardware-verified` | Historical hardware log | Recorded as accepted with no response; the subsequent query still reported `No Beep`. No state transition was demonstrated. The Skill refuses the setter. |
| `SYST:ERR?` | `hardware-verified` | `syst-err-command-error.txt` | Limited to the observed free text `Command error`; not a numbered error queue. |
| `CONFigure`, `CONFigure2` | `documented` | Manual | Includes `CONF:FUNC?`, `CONF:RANG?`, and `CONF:AUTO?`; no settings changed for verification. |
| `MEASure`, `MEASure2` (other forms) | `documented` | Manual | No other measurement functions or second-display measurement queries were captured. Parameterized forms can change measurement context and are refused. |
| `SENSe` | `documented` | Manual | Includes the temperature-unit query; no setters exercised. |
| `CALCulate` | `documented` | Manual | No commands in this family verified. |
| `TRIGger` | `documented` | Manual | No commands in this family verified. |
| `SAMPle` | `documented` | Manual | No commands in this family verified. |
| `SYSTem` (other manual-listed forms) | `documented` | Manual | No other forms verified. |
| `DISPlay`, `DIGitalio`, `STATus`, interface commands | `documented` | Manual | No commands in these families verified. |
| IEEE 488.2 common commands other than `*IDN?` | `documented` | Manual | `*RST` and `*CLS` are outside this Skill's scope. |

## Support levels

| Level | Meaning |
|---|---|
| `documented` | Implementation follows the cited manual; no real-device evidence for this command. |
| `hardware-verified` | A real instrument response was captured and checked for this exact command and firmware. |
| `firmware-scoped` | Hardware evidence records exact model, firmware, interface, and date. |
| `UNVERIFIED` | Parsing succeeded but a semantic or completeness claim cannot be proven (second `READ?` display, unitless response, return layout). |

These labels describe evidence, not feature count. `UNVERIFIED` can apply to a
specific semantic claim within a `hardware-verified` response. The historical
silent setter is the one logged observation without response bytes; silence
alone is never proof of success.

## What is deliberately not claimed

- USB-TMC was not exercised. USB CDC-ACM is the only transport with hardware evidence.
- No function, range, or input-terminal switching was exercised. Input-terminal selection (front-panel input vs. the separate 10 A terminal) was not verified.
- Accuracy and calibration were not verified; no known input source was attached for a cross-check. The captures make no accuracy, uncertainty, or traceability claim.
- The function and unit of the second `READ?` field remain `UNVERIFIED`. Units without a wire suffix, the temperature unit, the `CONF:RANG?` unit, and the return layouts of `MEAS:PER?`, `MEAS:CONT?`, `MEAS:DIOD?`, and `MEAS:CAP?` are also `UNVERIFIED`.
- No AC voltage, AC current, 2-wire or 4-wire resistance, frequency, period, capacitance, temperature, diode, or continuity response was captured.
