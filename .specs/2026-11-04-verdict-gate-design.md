# Verdict Gate Design

- **Status**: Draft — pending independent review
- **Created**: 2026-11-04
- **Target Files**: `skills/siglent-sds800xhd-control/scripts/scope_protocol.py`, `scripts/waveform_analysis.py`, `scripts/analyze_waveform.py`, `scripts/capture_scope.py`, `scripts/test_waveform_analysis.py`, `scripts/test_scope_protocol.py`, new `scripts/test_verdict_gate.py`, `SKILL.md`, `references/screenshot-and-waveform.md`

## 1. Intent

The mandatory analysis gate in `SKILL.md` is written as prose that an agent must
choose to execute. On 2026-11-04 an agent ran a real capture and produced a
conclusion that was wrong in almost every quantitative claim, without violating
any single safety rule. It bypassed the gate because the gate's own tooling could
not finish on the record it had captured, and it then derived voltages,
frequencies, edge counts, and windows itself.

This design removes the derivation from the agent. It adds one command that *is*
the gate, fixes the data defect that made the wrong arithmetic possible, removes
the performance cliff that made bypassing rational, and makes "the gate was not
run" a detectable state rather than a silent one.

## 2. Incident Evidence (frozen)

Capture: `AI8051U_AM32_ESC/firmware/DirectApp/bench/2026-11-04-CMPCR2延迟/capture`.

Frame facts, read from that capture's own `manifest.json`:

| Field | Value |
|---|---|
| Channels / segments | 4 channels, 16 segments (4 per channel) |
| Points per channel | 20,000,000 |
| Transfer | WORD, 2 bytes/point, LSB, `nominal_bits=16` |
| Sample interval / rate | 50 ns / 20 MSa/s |
| `TIM:SCAL` / `TRDL` | 100 ms/div / -0.4 s |
| Display origin `origin_s` | -0.1 s |
| Trigger | `EDGE`, source `C4`, `RISing`, level 2.5 V |
| Frame provenance | `existing_stop_claims_new_transition = false` |
| Integrity (`inspect`) | `COMPLETE`, 4 segments verified |

The 12 observed failures, grouped by cause:

**Derivation failures** — the agent computed something the tooling should have
computed (all reproducible from its own transcript):

- **E1 Word/byte domain confusion.** It applied the descriptor's
  `code_per_div = 30` (a BYTE-domain quantity) to a WORD transfer, printed
  "1 code = 66.7 mV", and reported a "3000 code" span as "200.00 V".
- **E2 Invented clipping.** From E1's inflated number it asserted C4 was
  "已被削顶". C4 never touches the rail: observed range `-1472..20528` codes,
  and the transport's representable limit is `±32767` codes with **zero**
  samples at it. The arithmetic that makes this checkable at all: at 2 V/div the
  panel's nominal full scale is `5 * 7680 = 38400` codes, but an int16 WORD
  payload stops at `32767` codes, i.e. **4.267 divisions / 8.53 V peak**.
  Clipping is therefore undetectable above 4.267 divisions on this setting, and
  any rail claim must be stated against the representable limit, never against
  the nominal 5-division screen.
- **E3 Wrong edge detector.** It used `abs(diff(x)) > 1500` — a sample-to-sample
  slew test — as if it were a level crossing, admitting noise and missing slow
  edges.
- **E4 Absence claim from a sparse look.** It examined 80 consecutive samples
  that happened to sit inside a high plateau and concluded "C4 实际是直流高电平
  …没有方波". `SKILL.md` forbids exactly this.
- **E5 Arithmetic error with a 1000x factor.** It read a 34085-sample gap and
  called it "1.70 s", derived "1 Hz 心跳", and from that asserted the wrong
  firmware was flashed. 34085 samples at 20 MSa/s is 1.7043 ms.
- **E7 No calibration attempt.** It never used `:MEASure:SIMPle:VALue? PKPK`,
  never supplied a calibration artifact, and never reported the
  `OBSERVED_UNVERIFIED` limitation that `SKILL.md` requires for WORD.
- **E8 No time anchors.** Every window it examined was addressed by bare sample
  index; no statement was converted to display time.
- **E9 Wrong count.** It reported "17 个分段"; the manifest has 16.
- **E11 Undetected context drift.** It did not notice the frame ran at 20 MSa/s
  over 1 s — four times the documented sample rate and one fifth of the record
  length of the skill's typical profile — which makes 400 kHz content only 50
  samples per cycle and puts the 25/26-sample quantization at the aliasing edge.

**Compliance failures** — the script cannot force these, only make them visible:

- **E6 Gate not run.** No full-record `structure` pass, no `regimes` pass, no
  percentile-based threshold derivation.
- **E10 Unstated provenance.** The frame was an `--existing-stopped` read; the
  agent never said so, although `SKILL.md` states that a `Stop` without a prior
  `Ready` does not prove a new capture.
- **E12 No error drain.** After a mid-session `C1:TRA?` socket timeout it
  re-identified and reconnected (correctly, per `SKILL.md`) but never drained
  `SYSTem:ERRor?`.

Corrected values for the same frame, recomputed at original resolution with
proper hysteresis (main-agent verification, not the incident agent's numbers):

| Quantity | Value |
|---|---|
| C4 low / high level | -0.01 V / 5.00 V |
| C4 codes per volt (derived) | high 19200 codes / 5.00 V = 3840 codes/V -> 7680 codes/div at 2 V/div |
| C4 rail samples | 0 (representable limit `±32767`; clip limit 4.267 div / 8.53 V peak) |
| C4 edges, full record | 280,637 (hysteresis state machine) |
| C4 median half period (dense regions) | 25 samples = 1.25 us -> ~400 kHz |
| C4 mean half period, full record | 3.207 us -> 156 kHz |
| C4 structure | silent before 0.00 s; 0.00-0.20 s dense at ~305 kHz; 0.25-0.40 s steady high (99.5 %); 0.40-0.60 s dense at ~350 kHz; 0.60-0.90 s sparse at 20-45 kHz |

The 3840 codes/V figure is `SKILL.md`'s own hardware-verified WORD scale, and it
is independently reproduced by this frame's internal levels. The defect in §4.1
is therefore verifiable against existing evidence, with no new hardware run.

## 3. Root Causes

**R1 — Domain ambiguity is created in the parser, not chosen by the agent.**
`scope_protocol.py:1308-1317` unconditionally writes a BYTE-domain
`code_per_div` into every preamble:

```python
if abs(result["vertical_code_field"]) > 256:
    result["max_value"]    = result["vertical_code_field"]          # 7680
    result["code_per_div"] = result["vertical_code_field"] / 256.0   # -> 30
```

For a WORD frame the manifest therefore carries `data_width_bytes: 2`,
`nominal_bits: 16` and `code_per_div: 30` simultaneously, with no field naming
the domain. E1 and E2 are consequences of reading that field, not of bad
arithmetic. Fixing the agent's reasoning cannot fix this; the parser must stop
publishing an ambiguous field.

**R2 — The gate requires an input that only the gate can produce.**
`structure` and `regimes` declare `--threshold-codes` / `--threshold-volts` as a
required mutually exclusive group. Gate step 0, however, says the thresholds must
first be derived from `summarize` percentiles. A required parameter that the
documented procedure must compute first is a workflow hole encoded in the CLI.
The data is already available: `waveform_analysis.py:545` computes
`p01/p05/p50/p95/p99` for every summary.

**R3 — The budget mechanism is O(n^2), and this is the main reason the gate gets
bypassed.** `bound_json` (`waveform_analysis.py:4024`) removes items one at a
time and re-serializes the entire document for each removal. Measured
consequences:

- C4 has 280,637 edges through a single hysteresis state machine (561,274 if a
  crossed-high mask is concatenated with a crossed-low mask, which double counts
every edge); `DEFAULT_STRUCTURE_EDGE_LIMIT` is 20,000
  (`waveform_analysis.py:33`), so a full-record `structure` is `UNVERIFIED` by
  construction on this signal.
- A 0.05 s window (1 M points, ~120 k edges) did not finish within 300 s.

When the sanctioned tool cannot complete on a normal record, a competent agent
falls back to hand-rolled analysis. **Improving the prose gate cannot fix that;
the tool must first stop being a cliff.**

**R4 — The gate is prose, not an artifact.** Nothing is written that proves the
gate ran, and nothing written by the gate is authoritative enough to be quoted
instead of reinterpreted.

## 4. Design

### 4.0 Frozen decisions

- **D1** `verdict` lives in a **new module `waveform_scan.py`**, not inside
  `waveform_analysis.py`. It imports only `load_capture`, `AnalysisError`,
  `DEFAULT_CHUNK_POINTS` and `SCHEMA_VERSION` from the analyzer. This answers the
  reviewer's question of whether a future regression in the analyzer could take
  the gate down with it: it cannot, because the scanner is a separate file with a
  narrow import surface. The CLI still exposes it as
  `analyze_waveform.py verdict`, so there is one user-facing entry point.
- **D2** `verdict` emits aggregates and a fixed-width window table. It never
  emits an unbounded `edges` / `pulses` / `cycles` item list, so it cannot hit
  the `bound_json` path in normal use.
- **D3** Thresholds are derived automatically from the existing percentile
  family. Explicit `--threshold-codes` / `--threshold-volts` become **optional**
  overrides on `verdict`. `structure` and `regimes` keep their required
  thresholds so their published contract does not change.
- **D4** `verdict` returns `status = REFUSED` with a reason instead of a partial
  verdict whenever it cannot support a claim.
- **D5** The ambiguity fix keeps `code_per_div` as a working alias, resolved by
  transfer width, so existing BYTE behavior and tests do not change. WORD gains
  a correct value where it currently has a trap.
- **D6** Voltage auto-derivation happens at capture time. The offline analyzer
  must stay offline, so it cannot self-calibrate.
- **D7** `must_state` is a machine-emitted list of limitation strings, not a
  reminder the agent is expected to remember.
- **D8** `verdict` binds its output to the merged waveform SHA-256.
- **D9** The `SKILL.md` gate section becomes a three-step procedure that names
  `verdict`. The reasoning currently in steps 0-4 moves to
  `references/screenshot-and-waveform.md` so no rule is lost.

### 4.1 L0 — Parser domain annotation (`scope_protocol.py`)

Replace the ambiguous assignment with explicit, self-describing fields, **while
preserving the legacy two-branch interpretation** the current code already
implements (reviewer R1: the existing branches do not mean the same thing).
`vertical_code_field` is the WORD codes-per-division when its magnitude exceeds
256, and is itself the BYTE codes-per-division below that threshold:

```python
vcf = result["vertical_code_field"]
if abs(vcf) > 256:
    word_cpd, byte_cpd = vcf, vcf / 256.0      # today's interpreted layout
else:
    byte_cpd, word_cpd = vcf, vcf * 256.0      # today's legacy layout (test fixture: vcf=30)
result["max_value"]          = word_cpd
result["transfer_width"]     = "word" if result["comm_type"] == 1 else "byte"
result["code_domain"]        = result["transfer_width"]      # only "byte" or "word"
result["codes_per_div_byte"] = byte_cpd
result["codes_per_div_word"] = word_cpd
result["code_per_div"]       = byte_cpd if result["code_domain"] == "byte" else word_cpd
```

`data_width_bytes` is unchanged. A BYTE frame keeps `code_per_div == 30` in both
layouts, so `decode_analog_byte` (`scope_protocol.py:1154`, which already
rejects `data_width_bytes != 1`) is unaffected. A WORD frame now reports
`7680`, which matches `SKILL.md`'s hardware-verified text and this frame's own
levels (`19200 codes / 5.00 V = 3840 codes/V -> 7680 codes/div at 2 V/div`).

**The analyzer's refusal policy does not move.** `waveform_analysis.py` keeps
`word_scale_verified = false` and `OBSERVED_UNVERIFIED` for WORD until an
independent calibration artifact is supplied. A correct transfer ratio is not a
verified absolute voltage ratio; §4.3 refuses voltage output whenever
`scale_status != VALID`, regardless of what `code_per_div` now says.

Consumers to update in the same change (reviewer R5): `waveform_analysis.py:202`
-> `:266` echoes `code_per_div` into `inspect` output; `SKILL.md:195`, `:216`,
`:222`, `:224` quote `code_per_div=30` as a WORD descriptor fact and must be
reworded. Tests `test_scope_protocol.py:282` and `test_waveform_analysis.py:58`
construct their own dicts and never call `parse_wavedesc`; they must be given the
domain-appropriate value explicitly rather than relying on a default.

Constraint: `waveform_analysis.py` must not start silently trusting the WORD
value. The change makes the *manifest* honest; it does not change the analyzer's
refusal policy.

### 4.2 L0 — Linear budget (`waveform_analysis.py:4024`)

Replace the remove-and-reserialize loop with: compute every section's aggregate
and authoritative `count` first, then truncate each item list once, using a size
predicted from per-item byte cost instead of a full re-serialization per step.

**This does not make `structure` able to finish this record.** `--max-edges` is
capped at `MAX_STRUCTURE_EDGE_LIMIT = 200_000` (`waveform_analysis.py:48`,
enforced at `:1000-1001`), and this capture's C4 has 280,637 edges, so a
requested `structure` pass is `UNVERIFIED` by budget before the JSON loop is even
reached (reviewer R2, oracle objection 2). The spec therefore claims no
acceptance target for `structure`.

The performance target belongs to the new aggregate scanner in §4.3, which keeps
no item tables: **full-record original-resolution scan of this capture in under
10 s, and the whole `verdict` command under 60 s.** The linear `bound_json` fix is
still required, because `verdict` and `check` reuse it and any future item-bearing
command inherits the cliff.

Also fix the truncation blind spots found in review (R4): `windows` (and any
new list) must be added to `bound_json`'s `sections` tuple (`:4072-4083`), and
`_emit` (`analyze_waveform.py:185-190`) currently only annotates
truncation when a `evidence` dict exists — `verdict` has none, so a truncated
verdict would be silently truncated.

### 4.3 L1 — `analyze_waveform.py verdict`

One process, in this order:

1. `load_capture` + integrity, as `inspect` does today.
2. `summarize_capture` for the percentile family (already computed at
   `waveform_analysis.py:545`).
3. **Auto threshold derivation and its evidence.** Derive candidate levels from
   the code histogram, not from two fixed percentiles: find the occupied code
   plateaus and accept a two-level split only when exactly two plateaus hold the
   bulk of the record and are separated by a gap wider than the noise spread.
   Percentiles are the cross-check, not the rule (oracle objection 4: the
   gate-step-0 heuristic "p95 and p99 coincide, low above p50" holds only for a
   simple two-level signal with a dominant state; on a multi-level, bipolar, or
   low-duty record it lands on the wrong level or drops a minor state entirely).

   Refuse with distinct reasons when: no plateau structure is found
   (`thresholds_not_separated`); more than two plateaus carry significant mass
   (`multi_level_unresolved`, with the plateau list returned); or the
   near-threshold fraction exceeds the configured limit
   (`thresholds_inside_noise`). Always run a **second threshold pair** between
   the plateau midpoints and report whether the edge count changes — that is the
   mechanical form of the paired-pulse re-scan rule.

   On a calibrated BYTE capture there is no `percentiles_code` today
   (`waveform_analysis.py:548-560`: the two families are mutually exclusive), so
   the plateau search must read `underlying_code_statistics` or histogram the
   code domain directly rather than consuming the published percentile dict
   (reviewer R6).
4. **Full-record original-resolution hysteresis scan**, chunked, accumulating
   only: edge count, half-period/width histograms, level medians, min/max, rail
   sample count. No item table.
5. **Fixed-width window table** (default 0.05 s) with per-window duty, edge
   count, and a label from `{silent, dense, sparse, steady_high, steady_low,
   mixed}` derived from those two numbers. This is a **pre-screen, not a
   replacement for `regimes`** (oracle objection 3): it cannot detect paired
   pulses at an intermediate level, single-cycle anomalies, the five-cycle
   support rule, transition-uncertainty intervals, or drift. `verdict` must say
   so in `claims.cannot_claim` (`stability_and_transition_analysis`) instead of
   implying full coverage.
6. **Rail / clipping detection against the representable limit, not the nominal
   screen.** Report `full_scale_code = 5 * codes_per_div` (the panel's nominal),
   `representable_code_limit` (32767 for WORD, 127 for BYTE),
   `clip_limit_div = representable_code_limit / codes_per_div`, `rail_samples`,
   and `clipped = rail_samples > 0`. For this capture that is 38400 nominal
   versus 32767 representable, so clipping is only observable up to 4.267
   divisions / 8.53 V peak. A verdict must never claim "no clipping" beyond that
   limit; `claims.can_claim` gains `no_clipping` only when the observed range
   stays inside the representable limit, and `clipping_detectable_up_to_div`
   carries the boundary so E2 cannot recur in either direction.
7. **Time anchoring**: every window and every statistic carries display time from
   `origin_s`, so E8 cannot recur.
8. **Claims block** (§4.3.1) and `must_state` (§4.3.2).
9. **Optional multi-channel summary.** `--channels C1,C2,C3,C4` runs the same
   aggregate scan per channel and emits one window table plus a per-window
   alignment of level transitions across channels. This is an alignment
   summary, explicitly **not** a causality analysis (oracle objection 6): the
   incident analysed one channel out of four and could not have related C4 to
   ENABLE / nFAULT / HOC at all. `claims.cannot_claim` carries
   `multi_channel_causality` whenever more than one channel is analysed, and
   `must_state` carries `single_channel_analysis_only` when it is not.

#### 4.3.2a `must_state` and structured output

`must_state` is necessary but not sufficient (oracle objection 8): a fixed list
of strings can be copied verbatim without understanding, and a natural-language
`check` over Chinese prose is easy to miss or over-trigger. The design therefore
does not rely on either alone:

- `must_state` guarantees the limitations are *present*.
- The *quantitative* content of a conclusion must come from the verdict artifact,
  not from the prose. Where a downstream report is generated, it is a template
  render of `claims` + `levels` + `timing` + `windows`, so a number that is not
  in the artifact cannot appear in the report.
- `check` is a best-effort detector for the free-text path, not the enforcement
  mechanism. Its exit code is advisory by default.

The known failure mode of over-constrained templates — a correct-looking report
that inherits a wrong automatic decision — is handled by the refusal paths in
§4.3 step 3 rather than by the template.

#### 4.3.1 Output contract (shape, filled with this capture's corrected values)

```json
{
  "schema_version": "1.0",
  "tool": "verdict",
  "status": "OBSERVED",
  "capture": {"channel": "C4", "points": 20000000, "merged_sha256": "<...>",
              "interval_s": 5e-08, "origin_s": -0.1, "time_reference": "display"},
  "integrity": {"status": "COMPLETE", "segments_verified": 4},
  "provenance": {"frame_evidence": "existing_stopped_no_ready_to_stop",
                 "context_deviations": ["sample_rate_4.0x_typical",
                                        "record_length_0.2x_typical",
                                        "dense_frequency_50_samples_per_cycle"]},
  "domain": {"code_domain": "word", "codes_per_div": 7680, "v_per_div": 2.0,
             "codes_per_v": 3840, "scale_status": "OBSERVED_UNVERIFIED",
             "scale_source": "internal_pkpk_consistency"},
  "levels": {"low_v": -0.01, "high_v": 5.00,
             "threshold_codes": [5000, 15000],
             "threshold_evidence": {"p05": -32, "p50": 18896, "p95": 19200,
                                    "near_threshold_fraction": 3.6e-04}},
  "structure": {"scan": "full_record_original_resolution",
                "edge_count": 280637, "detection_resolution_s": 5e-08,
                "rail_samples": 0, "clipped": false,
                "min_code": -1472, "max_code": 20528,
                "full_scale_code": 38400,
                "representable_code_limit": 32767,
                "clip_limit_div": 4.267,
                "clipping_detectable_up_to_div": 4.267},
  "sampling_risk": {"samples_per_cycle_at_dense_frequency": 50,
                    "period_quantisation_s": 5e-08,
                    "period_quantisation_fraction_of_half_period": 0.04,
                    "harmonic_visibility": "fundamental resolved; harmonics above the 10th alias at 20 MSa/s",
                    "note": "the 25/26-sample alternation is sample-grid quantisation of a non-integer half period, not two distinct frequencies"},
  "timing": {"dominant_half_period_s": 1.25e-06,
             "basis": "median_half_period_within_dense_windows",
             "dense_window_local_frequency_hz": 400000,
             "dense_window_frequency_range_hz": [259000, 353000],
             "full_record_mean_half_period_s": 3.207e-06,
             "full_record_mean_frequency_hz": 156000,
             "distribution_note": "bimodal: short 25/26-sample runs interleaved with long gaps; neither statistic describes the whole record"},
  "windows": [
    {"t0_s": -0.10, "t1_s": -0.05, "label": "silent",      "duty": 0.000, "edge_count": 0},
    {"t0_s":  0.00, "t1_s":  0.05, "label": "dense",       "duty": 0.376, "edge_count": 25878, "cycle_rate_hz": 259000},
    {"t0_s":  0.10, "t1_s":  0.15, "label": "dense",       "duty": 0.392, "edge_count": 30597, "cycle_rate_hz": 306000},
    {"t0_s":  0.25, "t1_s":  0.30, "label": "steady_high", "duty": 0.995, "edge_count": 60},
    {"t0_s":  0.45, "t1_s":  0.50, "label": "dense",       "duty": 0.465, "edge_count": 35303, "cycle_rate_hz": 353000},
    {"t0_s":  0.85, "t1_s":  0.90, "label": "sparse",      "duty": 0.447, "edge_count": 4514,  "cycle_rate_hz": 45000}
  ],
  "claims": {
    "can_claim": ["levels", "dense_window_local_frequency",
                  "intermittent_burst_structure", "no_clipping"],
    "cannot_claim": ["absolute_voltage_accuracy", "single_continuous_frequency",
                     "period_stability_beyond_sample_grid",
                     "stability_and_transition_analysis",
                     "multi_channel_causality"],
    "must_state": ["existing_stopped_no_ready_to_stop",
                   "scale_observed_unverified_internal_consistency_only",
                   "detection_resolution_50ns",
                   "frequency_basis_is_window_local_not_record_wide",
                   "single_channel_analysis_only"]
  }
}
```

The `threshold_evidence` field and the `windows[].label` values are the direct
replacements for gate steps 0 and 2. `windows[]` carries one row per fixed-width
window; the array above is shortened for this document, and the real emission is
contiguous and complete. `cycle_rate_hz` is the window-local average
(`edges / 2 / window_seconds`) and must not be confused with the
`dominant_frequency_hz` statistic, which is a distribution median.

**Two-mask double counting is a bug, not a definition.** Concatenating a
"crossed high" transition list with a "crossed low" transition list reports each
physical edge twice: on this capture it yields 561,274 where the hysteresis state
machine yields 280,637. The scanner must be a single state machine that emits one
transition per level change, and §6 carries a test for the 2x signature.

#### 4.3.2 `must_state` semantics

`must_state` is an enumerated vocabulary. Every entry is emitted by the tool and
is a complete limitation statement. The rule that `SKILL.md` will carry: a
written conclusion must reproduce every `must_state` entry verbatim. This is
what converts E6 and E10 from "the agent should have remembered" into "the
string is missing", which a reviewer or a checker can see.

### 4.4 L2 — Capture-time context and calibration (`capture_scope.py`)

Four additions, all inside the existing single session, none of which change the
capture itself:

1. **PKPK internal-consistency calibration.** After the merged output is written,
   read `:MEASure:SIMPle:ITEM PKPK` + `:MEASure:SIMPle:VALue?` per channel,
   compute `codes_per_v = (max_code - min_code) / pkpk_v` per channel, and write
   `calibration.auto.json` bound to the merged waveform SHA-256 with
   `status: OBSERVED_UNVERIFIED` and an `evidence` string naming it an internal
   consistency check, not traceable calibration. This is the shape `SKILL.md`
   already documents as usable. `scope_protocol.py` currently has no `MEASure`
   support at all, so this adds the first read-only use.

   Guard rails required by review (oracle objection 9): confirm the spelling is
   accepted and the measurement source is the intended channel before trusting
   the reply; a rejected command returns no bytes and queues `-113`, which is
   exactly the off-by-one hazard `SKILL.md` warns about. Drain the error queue
   **before** the measurement and again after, and attribute only *new* entries.
   A single stale error must not downgrade the capture, and a missing or
   `9.9E+37`-class PKPK returns `calibration_unavailable` rather than a frozen or
   inferred scale.
2. **Context profile check.** `--profile typical` (default `as-is`) compares the
   captured acquisition context against the `SKILL.md` hardware profile
   (`500 ms/div`, `5.00 MSa/s`, `25.0 Mpts`, `200 ns/point`, `5 s`) and records
   `context_deviations` in the manifest. This makes E11 automatic.
3. **Error drain.** Every phase calls the existing
   `scope_protocol.drain_error_queue` and records the drained entries in
   `manifest.system_errors`. A non-empty queue at the end downgrades the capture
   to `UNVERIFIED`. `capture_scope.py` currently never calls it although
   `scope_protocol.py` provides it. This makes E12 automatic.
4. **`channel_mapping` becomes a parameter.** `capture_scope.py:463` hard-codes
   `{"C1": "ENABLE", "C2": "nFAULT", "C3": "HOC", "C4": "P4.1/CMP"}`. Add
   `--channel-map` with that mapping as default.

### 4.5 L3 — Making a skipped gate visible

1. `capture_scope.py` writes `analysis-required.json` into the capture directory,
   naming the single next command, the channel map, and any context deviations.
   Anything that opens the directory sees it without deciding to look.
2. `verdict` writes `evidence_sha256`, binding the verdict to the merged
   waveform SHA-256.
3. New `analyze_waveform.py check --capture <dir> --statement <file>`: extracts
   quantified claims from the statement (voltage literals, frequency literals,
   clipping / "no signal" phrases) and cross-checks them against the verdict. On
   contradiction, or when no verdict artifact exists, it exits non-zero. This
   turns "wrote a report without running the gate" into a visible state.

**Where the verdict file lives (reviewer R3).** `analyze_waveform.py:176-181`
(`_ensure_output_is_external`) *refuses* any `--out` inside the capture
directory, so `analysis/verdict.json` under the capture is impossible as written.
The verdict is therefore written **outside** the capture (default:
`<capture>-analysis/verdict.json`, beside it, never inside), and the capture
directory receives only a pointer — `analysis-required.json` gains
`verdict_path` and `evidence_sha256` once the gate has run. This keeps the
raw-evidence directory write-once and still lets anything opening it discover
whether the gate ran and where the artifact is.

**`REFUSED` is a success path (reviewer R7).** `main()` only emits the `error`
envelope, and exit code 2, for a raised `AnalysisError`
(`analyze_waveform.py:302-315`). A refusal is a normal verdict and must be
returned through `_emit` with exit code 0; otherwise callers that treat non-zero
as "tool broken" will retry or bypass, which is the exact behaviour this design
exists to prevent.

### 4.6 `SKILL.md` gate section replacement

Steps 0-4 collapse to:

0. Run `python3 scripts/analyze_waveform.py verdict --capture <dir> --channel <Cn>`.
1. Quote `claims.can_claim`; do not assert anything in `claims.cannot_claim`.
2. Reproduce every `claims.must_state` entry verbatim in the conclusion.

The current step 0-4 reasoning, including the threshold-placement failure
example and the paired-pulse re-scan rule, moves to
`references/screenshot-and-waveform.md` unchanged, so the knowledge is preserved
while the operational path becomes single-command.

## 5. Goals and Constraints

- No new third-party dependency. NumPy only, as today.
- `verdict` and `check` stay read-only and never connect to an instrument.
- Every existing `structure` / `regimes` / `events` / `summarize` contract is
  preserved. No published field is removed; `code_per_div` keeps its BYTE
  meaning and gains a correct WORD meaning.
- No conclusion is ever padded, interpolated, or guessed. `REFUSED` is a normal
  success path.
- Evidence labels follow the existing vocabulary: `documented` <
  `hardware-verified` = `firmware-scoped`. The auto calibration is
  `OBSERVED_UNVERIFIED` and must be labelled that way in output, in tests, and in
  `SKILL.md`.
- Do not commit vendor manuals. Thresholds, limits, and statuses reuse existing
  phrasing rather than new wording.

## 6. Acceptance Criteria

Regression tests in a new `scripts/test_verdict_gate.py`, one assertion per
incident failure:

| ID | Test | Assertion |
|---|---|---|
| E1 | WORD frame, no calibration artifact, `--threshold-volts` requested | `status = REFUSED`; response contains no `*_v` field |
| E2 | This capture's C4 | `structure.rail_samples == 0`, `structure.clipped == false`, and `clipping_detectable_up_to_div == representable_code_limit / codes_per_div` (4.267 here, not 5) |
| E3/E4 | Thresholds placed inside the noise band | `near_threshold_fraction` exceeds the limit -> `REFUSED` with `thresholds_not_separated` |
| E5 | 34085 samples at 20 MSa/s | reported interval `= 1.7043e-3` s |
| E6 | Full-record `verdict` on this capture | completes < 60 s, `status = OBSERVED`, `claims` non-empty |
| E7 | `capture_scope.py --measure-pkpk` (offline fixture) | `calibration.auto.json` carries `OBSERVED_UNVERIFIED`, a `codes_per_v` within 1 % of 3840, and no `absolute`/`traceable` wording |
| E8 | Any window in `verdict` output | every entry carries `t0_s`/`t1_s` derived from `origin_s` |
| E9 | Section counts | `sum(len(segments)) == 16` for this capture |
| E10 | `--existing-stopped` frame | `must_state` contains `existing_stopped_no_ready_to_stop` |
| E11 | 20 MSa/s frame with `--profile typical` | `context_deviations` is non-empty |
| E12 | Session with a drained error (fixture) | `manifest.system_errors` non-empty and capture downgraded to `UNVERIFIED` |
| R3 | 280,637-edge full-record aggregate scan (`verdict`) | completes < 10 s with no item table built |
| R3b | Two-mask scan of the same record | transition count equals the state-machine count; 561,274 is rejected as double counting |
| R3c | Requested `structure` pass on this capture | still returns `UNVERIFIED` on the 200,000 edge cap, and the spec must not claim otherwise |

Additional acceptance:

- `python3 scripts/test_scope_protocol.py`, `test_waveform_analysis.py`,
  `test_discover_scope.py`, and the new `test_verdict_gate.py` all pass.
- `python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py
  skills/siglent-sds800xhd-control` passes.
- `npx skills@latest add . --list` lists the same skill set as before.
- `README.md` and `README.zh-CN.md` are unaffected: they do not enumerate
  analyzer subcommands. If any edit becomes necessary they must be changed in
  lockstep.
- A WORD frame's `inspect` output reports `codes_per_div == 7680` and
  `code_domain == "word"`; a BYTE frame's reports `30` and `"byte"`.

## 7. Implementation Partition and Verification

1. `scope_protocol.py` (one owner): §4.1 domain annotation, and the read-only
   `MEASure` query helpers §4.4.1 needs. Verify against `test_scope_protocol.py`
   plus a new WORD/BYTE domain assertion.
2. `waveform_scan.py` (**new file**, one owner, depends only on the frozen
   `load_capture` signature): §4.3 threshold derivation, the hysteresis aggregate
   scanner, the window table, rail detection, and the `verdict` result builder.
   Deliberately not in `waveform_analysis.py` (D1).
3. `waveform_analysis.py` (separate owner, parallel with 2): §4.2 linear
   `bound_json` only. No other function in that file is touched.
3. `analyze_waveform.py` (separate owner, after the `build_verdict` signature
   freezes): the `verdict` and `check` subcommands and their argument surface.
4. `capture_scope.py` (separate owner, independent of 2 and 3): §4.4 PKPK
   calibration, context profile check, error drain, `--channel-map`,
   `analysis-required.json`.
5. `test_verdict_gate.py` (separate owner, after behavior freezes): the §6
   table.
6. `SKILL.md` + `references/screenshot-and-waveform.md` (separate doc owner,
   after the schema freezes): §4.6, plus the `must_state` verbatim rule.

Parts 1-3 are one dependency chain and must not share a file with part 4.
Part 4 can run in parallel with 2-3.

Parent integrates, audits the §6 table against real output, runs every test and
both consistency checks, and commits in English with a conventional message.

## 8. Review Findings and Disposition

Two independent reviewers were run against the code and the specification. Both
converged on **approve with changes**, and both rejected as insufficient the
original framing that a script plus an optional read could prevent recurrence.

Facts confirmed by reading the code (not accepted from the spec): the `> 256`
domain branch at `scope_protocol.py:1308-1316`; the O(n²) re-serialization in
`bound_json` (`:4066`, `:4072-4083`, called inside the removal loop); the existing
percentile family at `:545`; `DEFAULT_STRUCTURE_EDGE_LIMIT = 20_000` (`:33`) and
the previously unmentioned `MAX_STRUCTURE_EDGE_LIMIT = 200_000` (`:48`, enforced
`:1000-1001`); the hard-coded channel map at `capture_scope.py:463` with no CLI
override; the total absence of `drain_error_queue` / `SYST:ERR` usage in
`capture_scope.py`; the absence of any socket in the offline analyzer; and the
`required=True` threshold groups at `analyze_waveform.py:64`, `:82-84`, `:102-104`.
All capture-manifest facts in §2 were confirmed; `integrity: COMPLETE` is derived
by the analyzer (`waveform_analysis.py:497-501`), not stored in the manifest, and
§2's wording has been corrected accordingly.

Changes made to this document as a result:

| Finding | Source | Disposition |
|---|---|---|
| §4.1's replacement code would have silently scaled legacy BYTE fixtures by 256× and no test would have caught it | reviewer R1 | §4.1 rewritten to preserve both existing descriptor layouts and to list every consumer to update |
| The "`structure` < 10 s on 280k edges" acceptance target is unachievable: the 200,000 edge cap forces `UNVERIFIED` first | reviewer R2, oracle #2 | §4.2 now claims no `structure` target; the target moved to the aggregate scanner; new test R3c asserts the cap still refuses |
| A verdict written inside the capture directory is rejected by `_ensure_output_is_external` | reviewer R3 | §4.5 relocated the artifact outside the capture, with a pointer left behind |
| `windows` is absent from `bound_json`'s `sections`, and `_emit` only annotates truncation when an `evidence` dict exists | reviewer R4 | §4.2 adds both fixes as required work |
| `code_per_div` consumers and the two fixtures that bypass `parse_wavedesc` | reviewer R5 | §4.1 lists them explicitly |
| A calibrated BYTE capture publishes no `percentiles_code`, so a percentile-only auto threshold cannot run | reviewer R6 | §4.3 step 3 now histograms the code domain directly |
| `REFUSED` cannot be delivered through `error_envelope`/exit 2 | reviewer R7 | §4.5 pins refusal to the success path |
| The gate-0 percentile rule is unsafe on multi-level, bipolar, or low-duty records | oracle #4 | §4.3 step 3 replaced with plateau detection plus a mandatory second threshold pair |
| `verdict` does not replace `regimes` | oracle #3 | §4.3 step 5 relabelled a pre-screen; `cannot_claim` carries `stability_and_transition_analysis` |
| A single "dominant frequency" would mislead on a bimodal record | oracle #5 | §4.3.1 separates dense-window local frequency (400 kHz) from full-record mean (156 kHz) and states the distribution is bimodal |
| "Aliasing" was used loosely | oracle #7 | new `sampling_risk` block distinguishes fundamental resolution, harmonic aliasing, and sample-grid quantisation |
| Multi-channel analysis was missing entirely | oracle #6 | §4.3 step 9 adds `--channels` as an alignment summary with causality explicitly excluded |
| `must_state` invites mechanical copying | oracle #8 | §4.3.2a: numbers must come from the artifact, `check` demoted to advisory |
| `PKPK` needs error-queue attribution and a sentinel-value guard | oracle #9 | §4.4.1 guard rails added |
| §6 had a broken table row (`E6 ... || E7`) | oracle | fixed |

**Unresolved disagreement, recorded rather than papered over.** The oracle argues
`verdict` is still an optional command and will be skipped exactly as `structure`
and `regimes` are skipped today, so the plan's core promise is unmet. This
document accepts that criticism as a limit, not a solvable requirement: no
in-process Python artifact can compel a caller that does not invoke it. §4.5 is
the strongest available answer (a pointer in the capture directory + an artifact
bound to the waveform hash + a checker), and §10 asks the user to decide whether
`check` should be blocking. Claiming more than that would be false.

**Both reviewers recommended a narrower first ship than the full plan.** Their
consensus minimum, adopted as the implementation order in §7: fix the WORD/BYTE
domain fields, add the item-table-free aggregate scanner, refuse on ambiguous
levels, and emit the local-frequency distribution, `sampling_risk`, `must_state`
and the waveform SHA-256. Capture-time PKPK, natural-language `check`, and the
large `SKILL.md` rewrite follow, and none of them is required to stop the twelve
observed failures.

## 9. Open Questions

- ~~Does the reviewer accept `verdict` as a subcommand of the existing analyzer,
  or should it be a separate script so a future regression in the analyzer cannot
  take the gate down with it?~~ **Resolved: separate module `waveform_scan.py`,
  one CLI entry point via `analyze_waveform.py verdict` (D1).**
- Should `check` be advisory (non-zero exit) or blocking (a documented
  pre-condition for quoting any conclusion)?
- Is `--profile typical` a safe default, given that a deliberate off-profile
  capture (a legitimate experiment) would then always carry deviations? The
  current proposal defaults to `as-is` and requires the flag.
- The window label vocabulary (`silent`, `dense`, `sparse`, `steady_high`,
  `steady_low`, `mixed`) is new. It must not be confused with the existing
  `classification.label` vocabulary (`continuous_carrier`,
  `low_duty_pulse_train`, ...). Confirm the separation or reuse the existing
  names.

## 10. Implementation Status

Shipped in this change:

- `scope_protocol.py` §4.1 domain annotation plus `representable_code_limit`.
  Verified on the real capture: all four WORD preambles now report
  `code_per_div = 7680`, `code_domain = "word"`, `codes_per_div_byte = 30`,
  where they previously reported 30 with nothing naming the domain.
- `waveform_scan.py` (new module) with `derive_thresholds`,
  `scan_hysteresis_aggregates`, `build_verdict`.
- `waveform_analysis.py` §4.2 linear `bound_json`: 120,000 items now truncate in
  0.24 s (previously a 120k window did not finish in 300 s), the authoritative
  count survives, and the budget is respected at 256 KiB, 1 MiB and 4 MiB.
- `analyze_waveform.py` `verdict` subcommand, with `REFUSED` returned as a
  success path (exit 0) and truncation annotated on the top-level limitations
  list.
- `SKILL.md` gate step 0 naming the single command.
- `test_verdict_gate.py`: 23 regression tests, one group per incident failure.

**Reference-capture result.** `verdict --channel C4` now reports `OBSERVED`,
`edge_count = 280637`, 20 contiguous windows, `rail_samples = 0`,
`clip_limit_div = 4.267`, dense-window frequency 400.0 kHz, full-record mean
155.9 kHz, and a bimodal note. All four channels resolve: C1 12135 edges at
19.8 kHz, C2 10250 at 17.5 kHz, C3 12291 at 19.5 kHz, C4 280637 at 400 kHz.
The C4 edge count matches an independent hand computation exactly.

**Design corrections found during implementation**, all recorded because the
spec was wrong rather than the code:

1. Thresholds cannot be placed at a *mass quantile* between the two level peaks.
   On an oscillating signal the transition samples spread evenly across the gap,
   so a 25% quantile lands 0.6 sigma from the low level, i.e. inside its noise
   band. They are now placed symmetrically about the gap centre, which yields
   45.8 sigma and 63.0 sigma clearance on the reference capture.
2. The `near_threshold_fraction` test in §4.3 step 3 is not a valid placement
   test for a fast oscillation: the reference capture legitimately has 22% of
   its samples between the thresholds. Placement is now judged by each level's
   own measured noise sigma, and `near_threshold_fraction` is kept as a
   diagnostic only.
3. Contiguous-occupancy plateau detection fails on this signal by construction:
   the transition band holds 49% of the record, so the two levels fuse into one
   plateau. Level detection now uses histogram mass peaks relative to the
   dominant peak. The 0.10 relative floor is stable across 0.05-0.30 on all four
   channels.
4. Bimodality cannot be decided by a median-versus-mean test alone: a record
   that is half fast oscillation and half silence keeps the mean within 50% of
   the median. A p90-versus-median spread test was added alongside it.
5. `calibration.codes_per_div` is the BYTE value and must never be used for a
   WORD frame's clip limit; the scanner reads the preamble domain instead and
   reinterprets a legacy preamble with the parser's own two-branch rule rather
   than rewriting stored evidence.
6. The window count must snap a near-integer span to the integer. A 1.0000000117 s
   record divides to 20.0000002 windows, and ceiling that invents a 21st window of
   zero width.

**Known limitation, deliberately accepted.** A narrow pulse whose level holds
under 10% of the dominant peak's mass is not accepted as a level, so a record
like 2000 high samples in 200000 REFUSES instead of reporting `OBSERVED`. That is
the conservative direction — it says the level structure is unresolved rather
than either dismissing the pulse as noise or fabricating a threshold pair — but
it does mean E4 is only half solved. A time-contiguity test (a level that forms a
contiguous run is a level regardless of mass) is the natural next step and is not
part of this change.

## 11. Approval

- [ ] User approved the direction: one-command gate, parser domain fix, linear
      budget, capture-time auto calibration, detectable skipped gate.
- [x] Independent review completed; findings incorporated (§8).
- [ ] User decided whether `check` is advisory or blocking.
- [ ] Implementation partitioned and assigned.
- [ ] All §6 acceptance criteria verified against real output.
- [ ] Final audit and commit.
