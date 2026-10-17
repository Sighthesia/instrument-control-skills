# Status and Reports

## Minimum report shape

```json
{
  "schema_version": "integrity-report-v1",
  "status": "COMPLETE",
  "checks": [
    {
      "name": "declared_length_matches_observed",
      "status": "pass",
      "evidence": {
        "declared_bytes": 1024,
        "observed_bytes": 1024
      }
    }
  ],
  "reasons": [],
  "evidence": {},
  "provenance": {},
  "limitations": []
}
```

## Check status

Use lowercase `pass`, `fail`, and `not_checked` for individual checks. Use the
uppercase vocabulary from `SKILL.md` for the report's primary status. A report can
contain passing checks and still be `UNVERIFIED` when an essential property has no
available evidence.

## Failure reporting

Every failed or unperformed check should have a stable name and a concise reason.
Prefer machine-readable fields such as `declared_points`, `observed_points`,
`expected_sha256`, and `observed_sha256` over prose alone. Keep enough context for
an analyst to decide whether to reacquire, reparse, or limit the claim.

## Analysis gate

Expose an explicit result such as `analysis_allowed` or `trusted_claims` when a
report is consumed by analysis. Examples:

- `COMPLETE` structure with verified calibration: voltage analysis allowed.
- `COMPLETE` structure with unknown calibration: code or relative analysis only.
- `INCOMPLETE` waveform: no complete-record frequency or duration claims.
- `UNVERIFIED` scalar sequence: report values, but do not claim acquisition
  completeness or stable timing.
