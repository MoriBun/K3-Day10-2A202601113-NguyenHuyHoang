# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K3 |
| Tên nhóm | PRAI |
| Repository | https://github.com/MoriBun/K3-Day10-2A202601113-NguyenHuyHoang |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Huy Hoàng | 2A202601113 | Role 1 — Điều phối pipeline | `CONTRACT.md`, `SETUP.md`, `src/core/`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `script/run_cp5_evidence.py`, review & release |
| 2 | Nguyễn Thị Hoàng Yến | 2A202601959 | Role 2 — Data foundation & recovery | `src/ingestion/cleaning.py`, `src/ingestion/corruption.py`, `data/raw/`, `data/clean/` |
| 3 | Ngô Thị Hằng | 2A202601365 | Role 3 — RAG & agent | `src/retrieval/index.py`, `src/retrieval/smoke.py`, `data/embeddings/`, ba collection ChromaDB |
| 4 | Quách Xuân Trường | 2A202601371 | Role 4 — Evaluation & observability | `src/evaluation/testset.py`, `src/observability/quality.py`, `src/observability/reporting.py` |

> **Ghi chú ownership.** `src/ingestion/crossref.py` được phân công cho Role 2 nhưng do CP0 bị trễ nên Role 1 viết để gỡ chặn cả nhóm. `quality.py` và `reporting.py` ban đầu thuộc Role 4, được Role 1 hoàn thiện khi Role 4 đang gánh 5/7 hàm còn lại. Phần sinh câu hỏi trong `testset.py` do Role 4 viết bằng LLM đã được thay bằng template cố định — lý do kỹ thuật ở mục 11. Nhóm có sử dụng AI assistant để pair-programming; các quyết định kỹ thuật và việc xác minh bằng artifact do thành viên thực hiện.

## 2. Tóm tắt kết quả

Nhóm hoàn thành trọn vẹn hai pha của bài lab. Pha 1 dựng baseline từ Crossref REST API: 24 raw record được lưu snapshot trước khi parse, làm sạch thành 24 dòng clean không mất bản ghi nào, embed bằng `all-MiniLM-L6-v2` vào collection ChromaDB `papers-baseline`, sinh evaluation set 60 câu hỏi trên 15 paper và chấm bằng LLM judge `gpt-4o-mini`. Baseline đạt `retrieval_hit_rate` 1.0000, `mean_token_f1` 1.0000, `judge_accuracy` 0.9667, `mean_judge_score` 4.90; data quality pass 7/7 check và freshness 0/24 dòng quá hạn.

Pha 2 mô phỏng sáu kịch bản corruption với seed cố định trên 6/24 paper, trong đó 5 paper nằm trong test set nên 20/60 câu hỏi bị ảnh hưởng. Corruption làm `mean_token_f1` giảm mạnh nhất (−0,1643), `judge_accuracy` giảm 0,1500 và `retrieval_hit_rate` giảm 0,0667; data quality tụt xuống 3/7 và freshness xuất hiện 3 dòng stale với `age_days` cao nhất 411 ngày. Kịch bản ảnh hưởng rõ nhất là truncate title, vì cả bốn loại câu hỏi đều dùng tên paper làm đường vào tài liệu.

Repair được thực hiện bằng cách nạp lại raw snapshot rồi chạy lại cleaning, không sao chép file clean cũ. Sau repair, cả bốn metric trở về đúng mức baseline, quality trở lại 7/7 và freshness về 0 dòng stale; 10/10 câu hỏi từng xấu đi đều phục hồi hoàn toàn.

Giới hạn quan trọng nhất còn lại: `mean_token_f1` baseline bằng 1,0 là trần của bộ khung đánh giá rule-based chứ không phản ánh năng lực mô hình, và nhóm mới đo tác động corruption ở đúng một mức cường độ.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```
Crossref REST API
  │  fetch_source_records()  ── lưu raw response TRƯỚC khi parse
  ▼
data/raw/crossref_response.json ──► crossref_records.json      [Role 2 · Role 1]
  │  build_clean_dataframe(records, run_date)
  ▼
data/clean/papers_clean.csv / .json   (24 dòng, schema 13 cột)  [Role 2]
  │
  ├──► LocalEmbeddingIndex.build() ──► data/chroma/  collection papers-baseline
  │                                     data/embeddings/papers_embeddings.json   [Role 3]
  │
  ├──► build_test_set() ──► data/eval/test_set.json (60 câu, khoá từ CP2)        [Role 4]
  │
  └──► run_data_quality_checks() · build_freshness_report()                       [Role 4 · Role 1]
                    │
       evaluate_pipeline(index, test_set)
                    ▼
       data/results/baseline_metrics.json + baseline_answers.json
                    ▼
       data/reports/phase1_report.md

  ═══════════ chỉ chạy sau khi baseline đủ artifact ═══════════

data/clean/papers_clean.csv
  │  corrupt_clean_dataframe(df, corruption_log)   seed = 42
  ▼
papers_clean_corrupted.csv ──► papers-corrupted ──► corrupted_metrics / answers
                                                     quality_corrupted · freshness_corrupted

data/raw/crossref_records.json     ← nguồn repair, corruption không bao giờ chạm tới
  │  load_raw_records() → build_clean_dataframe()
  ▼
papers_clean_repaired.csv ──► papers-repaired ──► repaired_metrics / answers
                                                   quality_repaired · freshness_repaired
                    │
                    ▼
       data/reports/corruption_report.md   (bảng delta ba trạng thái)
```

### Trách nhiệm của từng khối

| Khối | Owner | Input | Output |
| --- | --- | --- | --- |
| Raw ingestion | Role 2 (Role 1 hỗ trợ) | Crossref API | `data/raw/` 2 file |
| Cleaning & data modeling | Role 2 | `list[PaperRecord]` | Clean CSV/JSON 13 cột |
| Embedding & vector store | Role 3 | Clean DataFrame | 3 collection + 3 manifest |
| Evaluation set | Role 4 | Clean DataFrame | `test_set.json` 60 câu |
| Metrics | Role 4 | Test set + index | `*_metrics.json`, `*_answers.json` |
| Quality & freshness | Role 4 (Role 1 hoàn thiện) | DataFrame của mỗi trạng thái | `data/quality/` 6 file |
| Reporting | Role 4 (Role 1 hoàn thiện) | Metrics + quality + freshness | 2 report markdown |
| Corruption & repair | Role 2 (code) · Role 1 (orchestration) | Clean baseline + raw snapshot | Corrupted/repaired artifacts |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

`.env` nằm trong `.gitignore` từ commit đầu tiên và chưa từng xuất hiện trong lịch sử git — kiểm tra bằng `git log --all -- .env`, kết quả rỗng. Cấu hình nhóm dùng:

```ini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=<khoá riêng của từng người, không commit>
```

Crossref REST API là nguồn công khai, không cần API key. Biến tuỳ chọn `CROSSREF_MAILTO` đưa request vào polite pool, cũng đọc từ môi trường chứ không hard-code vào mã nguồn.

> **Vì sao là `gpt-4o-mini`.** `src/retrieval/llm.py` truyền cứng `temperature=0.0` vào `ChatOpenAI`, trong khi dòng GPT-5 chỉ chấp nhận `temperature=1`. Nhóm đã kiểm chứng bằng request thật: `gpt-4o-mini` chạy được, `gpt-5-mini` trả lỗi `Unsupported value: 'temperature' does not support 0 with this model`.

### Lệnh cài đặt

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
python -m pip install -e .
```

Bắt buộc cài dạng editable. Code import top-level (`from core.config import Settings`) trong khi `pyproject.toml` khai `package-dir = {"" = "src"}`; nếu chỉ chạy `pip install -r requirements.txt` sẽ gặp `ModuleNotFoundError: No module named 'pipelines'`.

Nhóm không dùng `uv` vì máy không cài; mọi lệnh `uv run` trong `Guide.md` được thay bằng `python` tương ứng và ghi lại trong `SETUP.md`.

### Lệnh chạy

```bash
python script/run_phase1.py           # baseline, 10 artifact
python script/run_corruption_flow.py  # corruption + repair, 16 artifact
python script/run_cp5_evidence.py     # bằng chứng lineage / retrieval / case study
```

Ba biến môi trường tuỳ chọn phải **để trống** khi so sánh ba trạng thái: `REFRESH_SOURCE`, `REFRESH_TEST_SET`, `RUN_RAGAS`. Fetch lại nguồn hoặc sinh lại test set giữa chừng sẽ làm phép so sánh mất công bằng.

### Kết quả tái hiện

`data/chroma/` nằm trong `.gitignore` vì là sqlite binary. Người mới clone repo chỉ cần chạy `run_phase1.py` một lần, collection sẽ được dựng lại từ `papers_clean.csv` đã commit. Corruption dùng `seed=42` nên `corruption_log.json` tái lập chính xác; riêng `judge_accuracy` có thể lệch nhẹ giữa các lần chạy vì LLM judge không hoàn toàn tất định.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Tham số | Giá trị |
| --- | --- |
| Source API | Crossref REST API — `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` (180 ngày gần nhất) |
| `rows` | 24 |
| Kết quả | 24 item; `total-results` trên Crossref: 99.767 |

### Raw và clean schema

`PaperRecord` gồm 11 trường: `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment`.

Clean schema 13 cột bắt buộc: `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `text_for_embedding`, `age_days`, `summary_chars`.

Ba quyết định schema quan trọng, ghi trong `CONTRACT.md`:

1. **`paper_id` = DOI viết thường.** ID phải ổn định giữa các lần chạy; nếu không, bản repaired sẽ mang ID khác baseline, `ground_truth_doc_ids` trỏ vào tài liệu không tồn tại và hit rate về 0 dù dữ liệu đã đúng.
2. **CSV không chứa cột kiểu list.** `corruption_flow` đọc lại CSV bằng `pd.read_csv`; một cột list sẽ quay về thành chuỗi `"['A','B']"`. Ngoài ra metadata của ChromaDB không nhận list. Nhóm dùng `authors_joined`/`categories_joined` phân tách bằng `"; "` — không dùng `", "` vì tên tác giả có thể chứa dấu phẩy.
3. **`categories` phải dùng proxy.** Crossref đã ngừng cập nhật trường `subject`: đo trên chính bộ dữ liệu của nhóm là **0/24 record** có giá trị. Nhóm chuyển sang `[type, container-title]`, thiếu `container-title` thì lùi về `[type, publisher]` — độ phủ `type` 24/24, `publisher` 24/24, `container-title` 16/24. Kết quả 24/24 record có categories, dạng `journal-article; Buildings`.

### Quy tắc cleaning

Loại bỏ record thiếu DOI, thiếu title, summary rỗng hoặc dưới 100 ký tự, `published` không parse được; dedupe theo `paper_id` giữ bản đầu tiên. Abstract của Crossref là JATS XML nên phải strip tag, unescape HTML entity và bỏ nhãn `Abstract`/`Summary` ở đầu — nhãn này nếu để lại sẽ lọt vào `ground_truth` của câu hỏi loại summary.

Mọi lần loại bỏ đều để lại số đếm trong `df.attrs["clean_stats"]` và in ra log. Lần chạy thực tế: `raw=24 → clean=24 (duplicate=0, no_title=0, short_summary=0, bad_published=0)` — không mất bản ghi nào.

`text_for_embedding` gồm title, summary, `Authors:`, `Categories:` và `Published:`. Phải chứa đủ bốn loại thông tin vì test set có bốn loại câu hỏi tương ứng; nếu chỉ embed title và summary thì câu hỏi authors và date sẽ retrieve sai tài liệu.

## 6. Evaluation setup

Test set gồm **60 câu hỏi trên 15 paper** (4 loại × 15), sinh bằng `build_test_set` và **khoá lại từ CP2** — cả ba trạng thái dùng đúng file `data/eval/test_set.json` này.

Paper đại diện được chọn trải đều theo thời gian xuất bản thay vì lấy ngẫu nhiên, để bao gồm cả bài cũ lẫn bài mới. Nhờ độ phủ 15/24 paper, corruption giao với test set ở 5/6 paper và 20/60 câu hỏi bị ảnh hưởng. Nếu test set chỉ phủ 4 paper thì xác suất corruption trượt hoàn toàn khỏi test set là khoảng 29% và bài sẽ không chứng minh được điều gì.

Bốn mẫu câu hỏi cố định, dùng nguyên văn, tên paper đặt trong **dấu nháy đơn**:

| `question_type` | `question` | `ground_truth` |
| --- | --- | --- |
| `summary` | `What is the paper '<title>' about?` | `first_sentence(summary)` |
| `authors` | `Who authored the paper '<title>'?` | `authors_joined` |
| `date` | `When was the paper '<title>' published?` | `published` |
| `categories` | `What categories does the paper '<title>' belong to?` | `categories_joined` |

`ground_truth_doc_ids` luôn là `paper_id` lấy từ clean dataset, không bịa ID. Lý do các mẫu này bắt buộc chứ không được paraphrase: xem mục 11.

Metrics gồm `retrieval_hit_rate` (giao giữa `retrieved_doc_ids` và `ground_truth_doc_ids`), `mean_token_f1` (token overlap giữa câu trả lời và ground truth), `judge_accuracy` và `mean_judge_score` từ LLM judge có structured output. Ragas tắt mặc định, bật bằng `RUN_RAGAS=1`.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Trạng thái |
| --- | --- |
| `data/raw/crossref_response.json` | ✅ 290 KB |
| `data/raw/crossref_records.json` | ✅ 24 record |
| `data/clean/papers_clean.csv` / `.json` | ✅ 24 dòng |
| `data/embeddings/papers_embeddings.json` | ✅ collection `papers-baseline`, 24 document |
| `data/eval/test_set.json` | ✅ 60 câu, 4 loại |
| `data/results/baseline_metrics.json` | ✅ |
| `data/results/baseline_answers.json` | ✅ 60 bản ghi |
| `data/results/agent_demo_answers.json` | ✅ 3 câu demo agent |
| `data/quality/quality_baseline.json` | ✅ 7/7 pass |
| `data/quality/freshness_report.json` | ✅ 0 stale |
| `data/reports/phase1_report.md` | ✅ |

### Baseline metrics

| Metric | Giá trị |
| --- | --: |
| `samples` | 60 |
| `retrieval_hit_rate` | 1,0000 |
| `mean_token_f1` | 1,0000 |
| `judge_accuracy` | 0,9667 |
| `mean_judge_score` | 4,9000 |

LLM judge chấm sai 2/60 câu ngay ở baseline, cho thấy judge thực sự đánh giá chứ không đóng dấu bừa.

## 8. Data quality và freshness

### Quality checks

Bảy check, ngưỡng đọc từ `Settings` chứ không hard-code:

| Check | Điều kiện pass | Baseline |
| --- | --- | --- |
| `row_count_min` | ≥ 20 dòng | PASS (24) |
| `paper_id_not_null` | không null/rỗng | PASS |
| `paper_id_unique` | không trùng | PASS |
| `title_not_null` | không null/rỗng | PASS |
| `summary_min_length` | ≥ 100 ký tự | PASS (min 826) |
| `no_duplicate_rows` | không có dòng trùng hoàn toàn | PASS |
| `freshness_age` | `age_days` ≤ 180 | PASS (max 175) |

Kết quả của ba trạng thái ghi ra ba file riêng theo tham số `report_name`, tránh trạng thái sau xoá mất bằng chứng của trạng thái trước.

### Freshness

| Trạng thái | latest | oldest | stale | max `age_days` |
| --- | --- | --- | --: | --: |
| Baseline | 2026-08-01 | 2026-02-12 | 0 | 175 |
| Corrupted | 2026-07-13 | 2025-06-21 | 3 | 411 |
| Repaired | 2026-08-01 | 2026-02-12 | 0 | 175 |

Freshness lấy mốc từ cột `published` của chính dữ liệu, không lấy giờ hệ thống. `run_date` của bước repair được suy ngược từ baseline (`published + age_days`) để hai trạng thái tính `age_days` trên cùng một mốc — nhờ vậy freshness của baseline và repaired trùng khớp hoàn toàn.

Baseline fresh 100% là kết quả đúng chứ không phải lỗi: filter Crossref đã chặn sẵn `from-pub-date` trong 180 ngày. Chính vì thế kịch bản làm cũ ngày xuất bản mới tạo được tín hiệu tương phản rõ ràng.

## 9. Corruption scenarios và repair

Sáu kịch bản, `seed=42`, log đầy đủ `paper_id` bị tác động cùng count trước/sau:

| Kịch bản | Số dòng | Tín hiệu kỳ vọng | Thực tế quan sát |
| --- | --: | --- | --- |
| Drop latest records | 1 | Mất tài liệu mới nhất | `10.2118/234689-pa` biến mất khỏi corpus |
| Blank summary | 2 | `summary_min_length` fail | FAIL, min = 0 ký tự |
| Inject noise vào summary | 2 | `token_f1` giảm | 4 câu hỏi xấu đi |
| Truncate title | 2 | Exact lookup hỏng | 5 câu hỏi xấu đi — nhiều nhất |
| Làm cũ publication date | 2 | `freshness_age` fail | FAIL, 3 dòng stale, max 411 ngày |
| Thêm duplicate row | 1 | `paper_id_unique` fail | FAIL, kèm `no_duplicate_rows` |

Tổng cộng 6/24 paper bị tác động, trong đó **5 paper nằm trong test set → 20/60 câu hỏi bị ảnh hưởng**. Sau mọi mutation, `text_for_embedding` được dựng lại bằng đúng hàm mà cleaning dùng; nếu bỏ bước này thì embedding vẫn giữ nội dung sạch và corruption sẽ không đo được.

**Repair** nạp lại `data/raw/crossref_records.json` rồi chạy lại `build_clean_dataframe`, ghi sang `papers_clean_repaired.*`. Không sao chép file clean baseline. Corruption chỉ đọc/ghi trong `data/clean/`, không bao giờ chạm `data/raw/` — đó chính là lý do repair khả thi.

Bằng chứng lineage trong `data/results/cp5_evidence.json`: paper `10.2118/234689-pa` bị drop khỏi corrupted đã xuất hiện lại trong repaired, và 5 cột `paper_id`, `title`, `authors_joined`, `published`, `summary` của repaired giống hệt baseline.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | --: | --: | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1,0000 | 0,9333 | 1,0000 | −0,0667 | +0,0667 | Giảm ít nhất; 4/60 câu mất hit |
| `mean_token_f1` | 1,0000 | 0,8357 | 1,0000 | −0,1643 | +0,1643 | Nhạy nhất — đo nội dung câu trả lời |
| `judge_accuracy` | 0,9667 | 0,8167 | 0,9667 | −0,1500 | +0,1500 | Judge độc lập xác nhận cùng xu hướng |
| `mean_judge_score` | 4,9000 | 4,3667 | 4,9000 | −0,5333 | +0,5333 | Giảm 0,53 điểm trên thang 5 |
| Quality checks pass/fail | 7/7 | **3/7** | 7/7 | −4 check | +4 check | 4 check fail: unique, summary length, duplicate, freshness |
| Freshness status | 0 stale | **3 stale** | 0 stale | +3 dòng | −3 dòng | `age_days` max nhảy 175 → 411 |

Hai kết luận nhân quả có artifact hỗ trợ:

1. **Corruption** (truncate title, inject noise, blank summary, backdate, duplicate trên 6/24 paper, 5 trong số đó thuộc test set) → **quality 7/7 → 3/7 và freshness 0 → 3 dòng stale** → **`mean_token_f1` −0,1643, `judge_accuracy` −0,1500, `retrieval_hit_rate` −0,0667**.

2. **Repair từ raw snapshot** (không copy file clean cũ) → **quality 3/7 → 7/7 và freshness 3 → 0 stale** → **cả bốn metric về đúng mức baseline; 10/10 câu hỏi từng xấu đi phục hồi hoàn toàn**.

**Corruption nào ảnh hưởng rõ nhất.** Thống kê 10 câu hỏi xấu đi theo kịch bản (các con số chồng lấn vì một paper có thể dính nhiều kịch bản): `truncate_titles` 5 câu, `inject_text_noise` 4 câu, `drop_latest_records` 4 câu, `blank_summaries` 1, `make_dates_stale` 1, `add_duplicate_rows` 1.

Truncate title gây hại nhiều nhất vì lý do cấu trúc chứ không ngẫu nhiên: cả bốn loại câu hỏi đều nhắc tên paper trong dấu nháy đơn, nên title là đường vào chính tới đúng tài liệu qua cả exact lookup lẫn semantic search. Cắt title là cắt đồng thời hai cơ chế.

**Case study cụ thể — `q0002`.** Câu hỏi tác giả, ground truth `Donald Martin; Blake Bowman`. Sau corruption agent trả về `Eason Ni` — tên tác giả của một paper khác, tức retrieval đã nhảy sang tài liệu sai. `token_f1` từ 1,0 xuống 0,0 rồi về lại 1,0 sau repair. Điều đáng chú ý là câu trả lời sai này hoàn toàn hợp lệ về hình thức: đúng định dạng tên người, không có dấu hiệu bất thường nào. Chỉ khi đối chiếu ground truth mới phát hiện — đây chính là lý do phải có observability chứ không thể dựa vào việc pipeline chạy không lỗi.

**Kết quả khác kỳ vọng.** `mean_token_f1 = 1,0` ở baseline ban đầu khiến nhóm nghi ngờ có lỗi. Kiểm tra lại thì đây là hệ quả tất yếu của thiết kế: `qa.py` trả về nguyên văn `metadata["authors_joined"]`, mà `ground_truth` cũng chính là trường đó, nên hai chuỗi trùng khít và F1 = 1. Nhóm giữ nguyên vì contract yêu cầu ground truth phải khớp thứ `qa.py` trả về, và vì baseline hoàn hảo khiến mọi sụt giảm sau corruption đều rõ ràng, không lẫn với nhiễu nền.

Ngược lại, `make_dates_stale` gần như không ảnh hưởng metric của agent nhưng lại là kịch bản duy nhất bị freshness bắt. Điều này cho thấy quality signal và agent metric bắt hai loại hỏng khác nhau và không thay thế được nhau.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** bản `testset.py` đầu tiên dùng LLM sinh câu hỏi tự nhiên, với template dự phòng dạng `Who are the authors of "<title>"?`. Khi review tích hợp, nhóm thấy `mean_token_f1` có nguy cơ chạm sàn ở mọi trạng thái — nghĩa là metric sẽ không phản ánh chất lượng dữ liệu.

- **Nguyên nhân:** `src/retrieval/qa.py` **không dùng LLM**. `_extract_answer` match chuỗi cứng, chỉ nhận `"who authored"` hoặc `"list the authors"`; `"who are the authors of"` không khớp chuỗi nào nên rơi vào nhánh mặc định trả về `first_sentence(summary)`. Tương tự `"what subject categories"` không chứa `"what categories"`. Ngoài ra `answer_question` dùng regex `r"'([^']+)'"` — **dấu nháy đơn** — nên title đặt trong nháy kép không kích hoạt exact lookup. Lỗi này nguy hiểm vì **không ném exception**: pipeline vẫn chạy, vẫn ra số, chỉ là số vô nghĩa.

- **Cách xử lý:** thay phần sinh câu hỏi bằng bốn template cố định ghi trong `CONTRACT.md`, trả chữ ký hàm về `build_test_set(df, output_path)` cho khớp `phase1.py`. Giữ lại `_select_representative_papers` vì phần chọn paper trải đều theo thời gian là thiết kế tốt và chính nó làm corruption giao được với test set.

- **Cách xác minh:** chạy đối chứng hai bộ template trên cùng dữ liệu và cùng index:

```
TEMPLATE PARAPHRASE (nháy kép)     TEMPLATE CỐ ĐỊNH (nháy đơn)
  summary     ĐÚNG                   summary     ĐÚNG
  authors     SAI                    authors     ĐÚNG
  date        ĐÚNG                   date        ĐÚNG
  categories  SAI                    categories  ĐÚNG
```

**Bốn vấn đề tích hợp khác đã xử lý:**

| Vấn đề | Hậu quả nếu bỏ qua | Cách sửa |
| --- | --- | --- |
| Ngưỡng summary lệch: cleaning 20 ký tự vs quality check 100 | Baseline fail quality check ngay trên dữ liệu sạch, mất mốc đối chứng | Đồng bộ về 100 ở cả hai nơi |
| `cleaning.py` và `corruption.py` mỗi bên tự viết công thức `text_for_embedding` | Baseline khác corrupted vì lý do không phải corruption | `corruption.py` import chung hàm từ `cleaning.py` |
| Manifest embeddings chứa đường dẫn tuyệt đối của máy build | `load()` trỏ sai kho vector trên máy khác | `load()` luôn dùng `settings.paths.chroma_dir` |
| `json.dumps(default=str)` biến `age_days` thành chuỗi `"15"` | JSON lệch kiểu so với CSV | Chuyển numpy scalar về kiểu Python trước khi serialize |

**Về quy trình:** nhóm chốt `CONTRACT.md` và phát một fixture clean 6 dòng đúng schema ngay ở CP0, nhờ đó Role 3 và Role 4 làm song song mà không phải chờ `data/raw/`. Đây là quyết định tổ chức có tác động lớn nhất tới việc kịp tiến độ.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| `mean_token_f1` baseline = 1,0 là trần của bộ khung rule-based | Metric không phản ánh năng lực mô hình, chỉ phản ánh việc trùng chuỗi | Thay `qa.py` bằng phiên bản dùng LLM sinh câu trả lời tự do, đo lại token F1 và so với bản rule-based |
| Mới đo tác động ở đúng một mức cường độ corruption | Chỉ chứng minh được quan hệ định tính tại một điểm | Chạy corruption ở tỉ lệ 5%, 15%, 25%, 40%, vẽ đường `mean_token_f1` theo tỉ lệ để tìm ngưỡng cần đặt cảnh báo |
| `categories` là proxy `type` + venue, không phải chủ đề học thuật | Câu hỏi loại categories kiểm tra siêu dữ liệu xuất bản chứ không phải nội dung | Lấy chủ đề từ OpenAlex concepts hoặc Semantic Scholar fields of study, so độ phủ với bản hiện tại |
| Corpus 24 paper là nhỏ | Đủ chứng minh cơ chế nhưng chưa kết luận được về độ ổn định của metric | Nâng `max_results` lên 100–200, chạy lại toàn bộ và so độ lệch chuẩn của metric giữa các lần |
| `judge_accuracy` phụ thuộc LLM nên không hoàn toàn tất định | Kết quả lệch nhẹ giữa các lần chạy | Chạy lặp 3 lần trên cùng test set và báo cáo khoảng dao động thay vì một con số |
| Chưa dùng Great Expectations, `data/quality/gx/` còn trống | Quality check chạy tốt nhưng chưa theo chuẩn công nghiệp | Chuyển 7 check sang expectation suite của GX và đối chiếu kết quả với bản pandas hiện tại |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế; phần được người khác làm hộ đã ghi rõ.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set (`data/eval/test_set.json`, 60 câu, khoá từ CP2).
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Mỗi thành viên có một báo cáo cá nhân riêng trong `report/individual_report/`.
- [x] Không có `.env`, API key hoặc secret trong repository, report hoặc log.
- [x] Hai pipeline chạy end-to-end: `run_phase1.py` 10/10 artifact, `run_corruption_flow.py` 16/16 artifact.
