# Parser Support Record

- Parser status: `firmware-scoped`
- Hardware verification: `partial` — see the per-claim list below, not a Skill-level claim
- Verified model/firmware/interface: `SIGLENT SDS824X HD`, firmware `4.8.12.1.1.6.5`, SCPI raw TCP `5025` (legacy shell port `5024` is not used)
- Manual source: *SDS800XHD Series Programming Guide* `CN11G` (local copy `ref/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf`); page numbers in the index are PDF physical pages
- Supported data kinds: `identity` (`*IDN?`), `scalar-measurement` (`:MEASure:*?`), `status-record` (`SYSTem:ERRor?`, undocumented but firmware-verified), `waveform` (`WF?`/`WAVeform` descriptor + payload), `screenshot` (`:PRINt?` raw PNG), and the decode list (`LIST<n>:RESult?`)

## Per-claim evidence

| Claim | Label | Evidence |
|---|---|---|
| Raw TCP session, one-command-per-write, silent rejected writes, `SYSTem:ERRor?` drain | `hardware-verified` | *Write-Failure Modes* in `references/command-reference.md`, reproduced on `4.8.12.1.1.6.5` |
| Capture and waveform download (descriptor, segments, hashes) | `hardware-verified` | capture manifest records and the frame/segment reports in `scripts/scope_protocol.py` |
| `:MEASure` readings | `hardware-verified` | `references/signal-discovery-and-measurement.md` |
| `:PRINt?` PNG screenshot reader | `documented` + offline-tested | `SKILL.md:141`, `:256` — explicit "not yet exercised against a physical instrument" |
| `waveform_evidence.py` five-axis report | `documented` + offline-tested | `SKILL.md:266` — same caveat |
| Reconstituted voltages from codes | `OBSERVED_UNVERIFIED` at best | no cross-check against the instrument's own `:MEASure` reading was implemented at the time of writing; see the known defects below |
| Decode list contents | `UNVERIFIED` for completeness | `row_count`/`raw_sha256`/`terminator` were not recorded by the reader at the time of writing |

## Known defects (open at the time of this record)

- **Voltage path can report a wrong level as valid.** Five independent paths were
  reproduced offline — including a reply from another channel accepted as this
  channel's V/div, an ampere scale reported as volts, and a legacy capture whose
  panel offset is never read. See `artifacts/check-waveform/report.md` and its
  reproduction script; they are local-only (git-ignored).
- **Eleven silent-accept paths** let incomplete data carry a usable status — for
  example an unparseable `WAV:STAR?` readback, a legacy DAT2 capture that writes a
  manifest and exits 0 without validating the descriptor, and a decode list that
  reports `likely_complete` for a header-only reply. See
  `artifacts/check-integrity/report.md`.
- **Status words are reused across claims**: `VALID` proves descriptor-versus-panel
  self-consistency, never an absolute voltage.

Do not upgrade this record without a captured reply: model, firmware, interface,
date, and the raw bytes. A passing offline test run is not hardware evidence.
