# Corruption Impact & Recovery Report

_Sinh tu dong luc 2026-08-06T05:10:57.092367+00:00_

Ba trang thai duoc danh gia tren **cung mot test set**, cung evaluator va cung `top_k`.

## 1. So sanh metrics

| Metric | Baseline | Corrupted | Repaired | Δ corrupt | Δ repair |
| --- | --: | --: | --: | --: | --: |
| Retrieval hit rate | 1 | 0.9333 | 1 | -0.0667 | +0.0667 |
| Mean token F1 | 1 | 0.8357 | 1 | -0.1643 | +0.1643 |
| Judge accuracy | 0.9667 | 0.8167 | 0.9667 | -0.15 | +0.15 |
| Mean judge score (1-5) | 4.9 | 4.3667 | 4.9 | -0.5333 | +0.5333 |

- **Δ corrupt** = corrupted − baseline. Am nghia la data xau lam giam chat luong.
- **Δ repair** = repaired − corrupted. Duong nghia la repair da phuc hoi.

## 2. Data quality

| Trang thai | Check pass | Tong check | Ket qua |
| --- | --: | --: | --- |
| Corrupted | 3 | 7 | **FAIL** |
| Repaired | 7 | 7 | PASS |

### Check that bai sau corruption

| Check | Quan sat | Sample paper_id |
| --- | --- | --- |
| `paper_id_unique` | 1 dong trung | `10.54254/2753-8818/2026.dl34055`, `10.54254/2753-8818/2026.dl34055` |
| `summary_min_length` | 2 dong ngan hon nguong (min=0) | `10.21203/rs.3.rs-10178277/v1`, `10.70121/001c.158711` |
| `no_duplicate_rows` | 1 dong trung | `10.54254/2753-8818/2026.dl34055`, `10.54254/2753-8818/2026.dl34055` |
| `freshness_age` | 3 dong qua han (max=411) | `10.54254/2753-8818/2026.dl34055`, `10.70121/001c.158711`, `10.54254/2753-8818/2026.dl34055` |

## 3. Freshness

| Trang thai | Stale rows | Tong rows | Moi nhat | is_fresh |
| --- | --: | --: | --- | --- |
| Corrupted | 3 | 24 | 2026-07-13 | khong |
| Repaired | 0 | 24 | 2026-08-01 | co |

## 4. Ket luan

Corruption lam giam: **Retrieval hit rate, Mean token F1, Judge accuracy, Mean judge score (1-5)**. Repair phuc hoi duoc: **Retrieval hit rate, Mean token F1, Judge accuracy, Mean judge score (1-5)**. Tat ca metric da ve lai muc baseline.

> Chi ket luan da phuc hoi khi so lieu chung minh. Neu metric hoac quality signal
> van xau thi phai ghi ro la recovery chua hoan toan.
