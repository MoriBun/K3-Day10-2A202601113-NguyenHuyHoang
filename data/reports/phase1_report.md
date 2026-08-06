# Phase 1 — Baseline Pipeline Report

## Source and artifacts

- **Source:** Crossref REST API
- **Mode:** existing raw snapshot
- **Query:** agentic retrieval augmented generation large language model
- **Filter:** from-pub-date:2026-02-07,has-abstract:true
- **Raw Records:** 24
- **Clean Records:** 24
- **Evaluation Questions:** 60
- **Top K:** 4

## Evaluation

| Metric | Value |
| --- | ---: |
| samples | 60 |
| retrieval_hit_rate | 1.000 |
| mean_token_f1 | 1.000 |
| judge_accuracy | 1.000 |
| mean_judge_score | 5 |

- Judge evaluator: fallback_heuristic; fallback used for 60 sample(s).
- Ragas: `{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`

## Data quality

Quality: **PASS** (7/7 checks).

| Check | Status | Expected | Observed |
| --- | --- | --- | --- |
| `row_count_min` | PASS | >= 20 rows | 24 rows |
| `paper_id_not_null` | PASS | `paper_id` is not blank | 0 blank rows |
| `paper_id_unique` | PASS | each paper_id occurs once | 0 duplicate rows |
| `title_not_null` | PASS | `title` is not blank | 0 blank rows |
| `summary_min_length` | PASS | summary >= 100 chars | 0 short rows |
| `no_duplicate_rows` | PASS | no duplicate complete rows | 0 duplicate rows |
| `freshness_age` | PASS | 0 <= age_days <= 180 | 0 invalid or stale rows |

## Freshness

- Status: **FRESH**
- Latest publication: 2026-08-01
- Oldest publication: 2026-02-12
- Stale rows: 0 of 24
