# Phase 1 — Baseline Report

_Sinh tu dong luc 2026-08-06T04:41:52.700768+00:00_

## 1. Nguon du lieu

| Muc | Gia tri |
| --- | --- |
| Source API | Crossref REST API |
| Che do nap | `snapshot` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| max_results / top_k | 24 / 4 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| LLM judge | `openai` / `gpt-4o-mini` |
| Raw records | 24 |
| Clean rows | 24 |

### Truy vet record bi loai khi cleaning

| Ly do | So dong |
| --- | --: |
| `raw_count` | 24 |
| `dropped_duplicate` | 0 |
| `dropped_no_paper_id` | 0 |
| `dropped_no_title` | 0 |
| `dropped_short_summary` | 0 |
| `dropped_bad_published` | 0 |
| `clean_count` | 24 |

> Cac con so `dropped_*` co the chong lan nhau khi mot dong hong nhieu tieu chi.

## 2. Ket qua evaluation

So sample: **60**

| Metric | Gia tri |
| --- | --: |
| Retrieval hit rate | 1 |
| Mean token F1 | 1 |
| Judge accuracy | 0.9667 |
| Mean judge score (1-5) | 4.9 |

> Ragas: Set RUN_RAGAS=1 to enable the slower Ragas pass.

## 3. Data quality

**7/7** check pass tren 24 dong.

| Check | Ket qua | Ky vong | Quan sat |
| --- | --- | --- | --- |
| `row_count_min` | PASS | >= 20 dong | 24 dong |
| `paper_id_not_null` | PASS | `paper_id` khong null/rong | 0 dong null hoac rong |
| `paper_id_unique` | PASS | moi `paper_id` chi xuat hien 1 lan | 0 dong trung |
| `title_not_null` | PASS | `title` khong null/rong | 0 dong null hoac rong |
| `summary_min_length` | PASS | summary >= 100 ky tu | 0 dong ngan hon nguong (min=826) |
| `no_duplicate_rows` | PASS | khong co dong trung hoan toan | 0 dong trung |
| `freshness_age` | PASS | age_days <= 180 | 0 dong qua han (max=175) |

## 4. Freshness

| Muc | Gia tri |
| --- | --- |
| Nguong | 180 ngay |
| Moi nhat | 2026-08-01 |
| Cu nhat | 2026-02-12 |
| Tuoi trung binh | 81 ngay |
| Stale rows | 0 / 24 |
| is_fresh | co |

## 5. Ket luan baseline

Retrieval hit rate baseline dat **1** tren 60 cau hoi. Data quality **pass toan bo**. Du lieu **con moi**, khong co dong nao qua han.

> Baseline chi duoc coi la hoan tat khi artifact, metrics va report khop nhau,
> khong phai khi script chay xong khong loi.
