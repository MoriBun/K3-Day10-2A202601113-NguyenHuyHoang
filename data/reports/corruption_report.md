# Data Corruption and Repair Report

## Evaluation comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted Δ | Repaired vs baseline Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| retrieval_hit_rate | 1.000 | 0.933 | 1.000 | -0.067 | 0.000 |
| mean_token_f1 | 1.000 | 0.836 | 1.000 | -0.164 | 0.000 |
| judge_accuracy | 1.000 | 0.833 | 1.000 | -0.167 | 0.000 |
| mean_judge_score | 5 | 4.333 | 5 | -0.667 | 0 |

## Evaluation provenance

- Baseline judge: fallback_heuristic; fallback used for 60 sample(s).
- Corrupted judge: fallback_heuristic; fallback used for 60 sample(s).
- Repaired judge: fallback_heuristic; fallback used for 60 sample(s).

## Data quality comparison

- Corrupted: **FAIL** (3/7)
- Repaired: **PASS** (7/7)

### Failed corrupted checks

- `paper_id_unique`: 2 duplicate rows
- `summary_min_length`: 2 short rows
- `no_duplicate_rows`: 2 duplicate rows
- `freshness_age`: 3 invalid or stale rows

## Freshness comparison

| State | Fresh | Stale rows | Total rows | Latest published |
| --- | --- | ---: | ---: | --- |
| Corrupted | False | 3 | 24 | 2026-07-13 |
| Repaired | True | 0 | 24 | 2026-08-01 |
