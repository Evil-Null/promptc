# Routing Evaluation Corpus

Pinned ground-truth corpus and harness for validating the promptc router
across releases.

## Files

| File | Purpose |
|---|---|
| `corpus.jsonl` | Canonical intents tagged with expected template + minimum zone |
| `baseline_v1.3.1.json` | Snapshot of router behavior at tag-equivalent commit `9ba2198` |

## Usage

```bash
# Produce a fresh snapshot and compare to baseline
PYTHONPATH=src python scripts/eval_route.py --snapshot /tmp/current.json

# Diff against baseline
diff <(jq -S . tests/eval/baseline_v1.3.1.json) \
     <(jq -S . /tmp/current.json)
```

## Contract

- `expected_template = null` means the input must route to `PASSTHROUGH`.
- `expected_zone_min` defines the lowest acceptable zone (`PASSTHROUGH` <
  `SUGGEST` < `CONFIRM` < `AUTO_SELECT`). Actual zone must be ≥ this value.
- Corpus is builtin-only: plugins and custom templates are isolated to avoid
  cross-contamination.

## Adding cases

1. Append a JSONL record with stable `id` (kebab-case).
2. Re-run the harness.
3. Commit the updated baseline only after human review confirms the routing
   decision is correct — never auto-bless snapshots.
