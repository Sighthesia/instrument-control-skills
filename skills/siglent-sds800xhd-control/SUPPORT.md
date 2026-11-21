# Parser Support Record

- Parser status: `firmware-scoped`
- Hardware verification: `partial` — see the per-claim list below, not a Skill-level claim
- Verified model/firmware/interface: `SIGLENT SDS824X HD`, serial `SDS08A0Q909185`, firmware `4.8.12.1.1.6.5`, SCPI raw TCP `5025` (legacy shell port `5024` is not used); re-verified 2026-11-21
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
| Reconstituted voltages from codes | `hardware-verified` for the cross-check, `OBSERVED_UNVERIFIED` for absolute accuracy | 2026-11-21: reconstructed PKPK 3.0417 V vs the instrument's 3.04167 V (\|diff\| 0.00003 <= tolerance 0.0611, `level_confirmed: PASS`); a fabricated 5.0 V reconstruction on the same capture is `FAIL`. Scale derived from descriptor `vdiv=0.1 x probe=10` = panel `1.00E+00V`, `code_per_div=7680`. Evidence: `artifacts/hw-verify/2026-11-21-sds824xhd.md` (local). |
| Probe ratio readback | `hardware-verified` | `:CHANnel1:PROB?` answers `1.00E+01` (10x). The long forms `:CHANnel1:VDIV?`/`:OFST?` are `-113 Undefined header`; only `C1:VDIV?`/`C1:OFST?` work and they echo `C1:VDIV 1.00E+00V`. |
| Decode list contents | `UNVERIFIED` for completeness | `row_count`/`raw_sha256`/`terminator` were not recorded by the reader at the time of writing |

## Known defects (open at the time of this record)

- **Arming (fixed 2026-11-21, hardware-verified).** A single shot that completes
  before the first `SAST?` poll no longer discards the frame, and arming an
  already-stopped scope is refused with an instruction to use
  `--existing-stopped`.
- **Modern transfer window (fixed 2026-11-21, hardware-verified).** When `WFSU NP`
  exceeds `ACQ:POINts` the preamble reports the transfer window, not the record;
  the record length is now the authority for both the segment window and the
  probe sizes (frame and segment COMPLETE, 100000 points).
- **Modern WORD captures report `units: code`.** No `code_scale_v` is derived from
  `code_per_div*256`, so `scale_usable` and `level_confirmed` stay `UNKNOWN`
  (`level_reason: code_scale_unknown`) until an external calibration file is
  supplied. Absolute levels are confirmed only on the byte-domain path.
- **Voltage path can report a wrong level as valid.** Independent paths reproduce
  this offline — including a reply from another channel accepted as this
  channel's V/div, an ampere scale reported as volts, and a legacy capture whose
  panel offset is never read. See `artifacts/check-waveform/report.md` and its
  reproduction script; they are local-only (git-ignored).
- **Silent-accept paths** let incomplete data carry a usable status. The classes
  seen here are: a readback that cannot be parsed so the check is skipped, a
  legacy capture that records success without validating the descriptor, a
  validator with no point-count authority that still says `COMPLETE`, and a decode
  reader that calls "the bytes stopped" complete. Some are fixed; the local audit
  report in `artifacts/` (git-ignored) lists the rest.
- **Status words are reused across claims**: `VALID` proves descriptor-versus-panel
  self-consistency, never an absolute voltage.

Do not upgrade this record without a captured reply: model, firmware, interface,
date, and the raw bytes. A passing offline test run is not hardware evidence.
