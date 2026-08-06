# Phase 1 — Baseline Pipeline Report

## Source and artifacts

- **Source:** Crossref REST API
- **Mode:** existing raw snapshot
- **Query:** agentic retrieval augmented generation large language model
- **Filter:** from-pub-date:2026-02-07,has-abstract:true
- **Raw Records:** 24
- **Clean Records:** 24
- **Evaluation Questions:** 16

## Retrieval and answer evaluation

| Metric | Value |
| --- | ---: |
| samples | 16 |
| retrieval_hit_rate | 1.000 |
| mean_token_f1 | 1.000 |
| judge_accuracy | 1.000 |
| mean_judge_score | 5 |

- Judge evaluator: LLM judge used for every sample.
- Ragas: `{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`

## Data quality

Overall status: **PASS**
- PASS — `row_count_min`: 24
- PASS — `paper_id_not_null`: 24
- PASS — `paper_id_unique`: 0
- PASS — `title_not_null`: 24
- PASS — `summary_min_length`: {'valid_rows': 24, 'minimum_chars': 100}
- PASS — `no_duplicate_rows`: 0
- PASS — `freshness_age`: {'stale_rows': 0, 'invalid_age_rows': 0, 'threshold_days': 180}

## Freshness

- Status: **FRESH**
- Latest publication: 2026-08-01
- Oldest publication: 2026-02-12
- Stale rows: 0 of 24
