# Data Corruption and Repair Report

## Evaluation comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted Δ | Repaired vs baseline Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| retrieval_hit_rate | 1.000 | 0.750 | 1.000 | -0.250 | 0.000 |
| mean_token_f1 | 1.000 | 0.509 | 1.000 | -0.491 | 0.000 |
| judge_accuracy | 1.000 | 0.500 | 1.000 | -0.500 | 0.000 |
| mean_judge_score | 5 | 3.312 | 5 | -1.688 | 0 |

## Evaluation provenance

- Baseline judge: LLM judge used for every sample.
- Corrupted judge: LLM judge used for every sample.
- Repaired judge: LLM judge used for every sample.

## Data quality comparison

- Corrupted quality: **FAIL**
- PASS — `row_count_min`: 24
- PASS — `paper_id_not_null`: 24
- FAIL — `paper_id_unique`: 2
- PASS — `title_not_null`: 24
- FAIL — `summary_min_length`: {'valid_rows': 22, 'minimum_chars': 100}
- FAIL — `no_duplicate_rows`: 2
- FAIL — `freshness_age`: {'stale_rows': 3, 'invalid_age_rows': 0, 'threshold_days': 180}
- Repaired quality: **PASS**
- PASS — `row_count_min`: 24
- PASS — `paper_id_not_null`: 24
- PASS — `paper_id_unique`: 0
- PASS — `title_not_null`: 24
- PASS — `summary_min_length`: {'valid_rows': 24, 'minimum_chars': 100}
- PASS — `no_duplicate_rows`: 0
- PASS — `freshness_age`: {'stale_rows': 0, 'invalid_age_rows': 0, 'threshold_days': 180}

## Freshness comparison

| State | Fresh | Stale rows | Total rows | Latest published |
| --- | --- | ---: | ---: | --- |
| Corrupted | False | 3 | 24 | 2026-07-13 |
| Repaired | True | 0 | 24 | 2026-08-01 |

A useful repair run brings retrieval and answer metrics near the baseline while restoring quality and freshness checks.
