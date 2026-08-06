# DATA CONTRACT — Day 10 Data Pipeline & Observability

> **Chủ sở hữu tài liệu:** Vai trò 1 (Pipeline integrator).
> **Trạng thái:** chốt tại CP0. Mọi thay đổi sau CP0 phải báo cả nhóm trước khi sửa code.
>
> Tài liệu này tồn tại vì 4 người làm song song trên cùng một luồng dữ liệu. Nếu mỗi
> người tự đặt tên cột hoặc tự định nghĩa ID, phần ghép ở CP3 sẽ hỏng và không kịp sửa.
> **Phần lớn contract dưới đây không phải lựa chọn tự do — nó đã bị code có sẵn ràng buộc.**
> Chỗ nào là quyết định của nhóm đều được đánh dấu 🔧.

---

## 0. Nguyên tắc bất biến

Trích từ bảng phân công (`phan-cong-day-10-data-pipeline-4h.html`), áp dụng toàn lab:

1. Chỉ chạy corruption sau khi baseline đã tạo đủ artifact.
2. Giữ nguyên test set, ground truth, evaluator và `top_k` khi so sánh baseline / corrupted / repaired.
3. Dùng path và collection riêng cho ba trạng thái; **không ghi đè baseline**.
4. Repair bằng cách chạy lại từ raw source đáng tin, **không sửa tay** answers hoặc metrics.
5. Report phải trỏ tới artifact thật; **không commit API key hoặc `.env`**.

Thêm hai quy tắc của nhóm:

6. **Không hard-code path.** Mọi đường dẫn lấy từ `settings.paths` (`src/core/config.py`).
   Rubric trừ điểm trực tiếp mục này.
7. **Không đổi chữ ký hàm** mà module khác đang gọi. Cần đổi → báo Vai trò 1 trước.

---

## 1. Phân công và artifact bàn giao

| | Vai trò | Sở hữu | Artifact phải bàn giao |
|---|---|---|---|
| **VT1** | Pipeline integrator | `src/core/` · `src/pipelines/` | `phase1.py`, `corruption_flow.py` chạy end-to-end |
| **VT2** | Nền tảng dữ liệu & recovery | `src/ingestion/` · `data/raw/` · `data/clean/` | raw response, raw records, clean dataset, corruption log |
| **VT3** | RAG & agent | `src/retrieval/` · `data/embeddings/` | 3 collection Chroma + 3 embedding manifest |
| **VT4** | Evaluation & observability | `src/evaluation/` · `src/observability/` | test set, metrics, answers, quality, freshness, 2 report |

Bảng đầy đủ 27 artifact: xem `Paths` trong `src/core/config.py:12-40`.

---

## 2. Contract 1 — Raw record

### 2.1 `PaperRecord` (11 field, đã cố định tại `src/ingestion/crossref.py:9-21`)

`paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`,
`published`, `updated`, `abs_url`, `pdf_url`, `comment`

### 2.2 Mapping Crossref → `PaperRecord`

| PaperRecord | Crossref field | Xử lý |
|---|---|---|
| `paper_id` | `DOI` | `.strip().lower()` — **xem 2.3** |
| `title` | `title[0]` | list; rỗng → **loại record** |
| `summary` | `abstract` | JATS XML → phải strip tag, xem 2.4 |
| `authors` | `author[].given` + `.family` | thiếu → dùng `.name` (tổ chức); không có `author` → `[]` |
| `categories` | `subject[]` | thường vắng → `[]` |
| `primary_category` | `subject[0]` | không có → `""` |
| `published` | `published.date-parts[0]` | `[Y]`, `[Y,M]` hoặc `[Y,M,D]` → thiếu thì mặc định `1` |
| `updated` | `indexed.date-time` | fallback `deposited.date-time`; không có → bằng `published` |
| `abs_url` | `URL` | |
| `pdf_url` | `link[]` có `content-type == "application/pdf"` → `.URL` | không có → `""` |
| `comment` | *(Crossref không có)* | luôn `""`; giữ field cho tương thích schema |

### 2.3 🔧 Quy tắc `paper_id` ổn định — **quyết định: dùng DOI**

```python
paper_id = record["DOI"].strip().lower()
```

Lý do bắt buộc phải ổn định: CP6 repair bằng cách nạp lại `data/raw/` rồi clean lại. Nếu
`paper_id` sinh theo index dòng hoặc theo hash của nội dung, bản repaired sẽ có ID khác
bản baseline → `ground_truth_doc_ids` trong test set trỏ vào hư không → `retrieval_hit_rate`
tụt về 0 dù dữ liệu đã phục hồi đúng. DOI do Crossref cấp, không đổi giữa các lần fetch.

**Cấm:** dùng `uuid4()`, số thứ tự, hoặc hash của `title`/`abstract`.

### 2.4 Abstract của Crossref là JATS XML

Trường `abstract` trả về dạng như:

```
<jats:p>We present an <jats:italic>agentic</jats:italic> retrieval pipeline&#x2026;</jats:p>
```

Bắt buộc xử lý theo thứ tự: strip tag → unescape HTML entity → `normalize_whitespace`
(`src/core/utils.py:37`). Nếu bỏ qua bước này, tag XML sẽ lọt vào `text_for_embedding`
và làm nhiễu embedding.

### 2.5 Gọi API

```
GET https://api.crossref.org/works
```

| Param | Giá trị | Nguồn |
|---|---|---|
| `query.bibliographic` | `settings.source_query` | `config.py:127` |
| `filter` | `settings.source_filter` | `config.py:128` — `from-pub-date:<hôm nay−180d>,has-abstract:true` |
| `rows` | `settings.max_results` | `config.py:129` — mặc định 24 |
| `mailto` | email của nhóm | 🔧 nên có: đưa request vào *polite pool*, giảm 429 |

- Crossref **không cần API key**.
- **Lưu raw response xuống `paths.raw_api_response` TRƯỚC khi parse.** Đây là điều kiện
  pass CP0 và là nguồn repair duy nhất ở CP6.
- Retry/backoff cho `429` và `503`: tối thiểu 3 lần, chờ `2^n` giây. Lỗi tạm thời **không**
  được phép thay bằng dữ liệu bịa.
- Nếu số record hợp lệ sau parse `< 20`: nới `max_results` trong `config.py` lên 40–60
  (VT1 sửa, vì `src/core/` thuộc VT1) và ghi rõ trong report.

---

## 3. Contract 2 — Clean schema *(quan trọng nhất)*

Đây là mặt cắt mà VT2, VT3, VT4 đều chạm vào. 13 cột, đúng tên, đúng kiểu:

| # | Cột | Kiểu | Ai tiêu thụ | Ràng buộc |
|---|---|---|---|---|
| 1 | `paper_id` | str | index (ID), eval (`ground_truth_doc_ids`), quality | **not null, unique** |
| 2 | `title` | str | index, `lookup()` theo title | **not null**, đã `normalize_whitespace` |
| 3 | `summary` | str | metadata, `_extract_answer` fallback | đã strip JATS |
| 4 | `authors_joined` | str | metadata, câu hỏi `authors` | join bằng `"; "` |
| 5 | `categories_joined` | str | metadata, câu hỏi `categories` | join bằng `"; "` |
| 6 | `primary_category` | str | report | có thể rỗng |
| 7 | `published` | str | metadata, câu hỏi `date`, freshness | **`YYYY-MM-DD`** |
| 8 | `updated` | str | report | `YYYY-MM-DD` |
| 9 | `abs_url` | str | metadata | |
| 10 | `pdf_url` | str | metadata | có thể rỗng |
| 11 | `text_for_embedding` | str | nội dung được embed | **not null**, xem §4 |
| 12 | `age_days` | int | quality + freshness | `>= 0` |
| 13 | `summary_chars` | int | quality | `== len(summary)` |

### 3.1 🔧 Quyết định: CSV chỉ chứa scalar — không có cột kiểu list

`authors` và `categories` **không** được ghi vào CSV dưới dạng list Python.

Lý do: `phase1.py` ghi `papers_clean.csv`, rồi `corruption_flow.py` đọc lại file đó bằng
`pd.read_csv`. Một cột list sẽ quay về thành chuỗi `"['A', 'B']"` — không phải list. Bug này
âm thầm và chỉ lộ ra ở CP5 khi không còn thời gian sửa. Dùng `authors_joined` /
`categories_joined` là đủ cho mọi consumer phía sau.

Lý do thứ hai: **ChromaDB metadata không nhận list.** `src/retrieval/index.py:54-63` đọc
thẳng `row["authors_joined"]` và `row["categories_joined"]` để nhét vào metadata. Đưa list
vào sẽ raise ngay lúc `collection.add`.

### 3.2 🔧 Dấu phân tách là `"; "` chứ không phải `", "`

Tên tác giả có thể chứa dấu phẩy (`"Nguyen, Van A"`). Dùng `", "` sẽ không tách ngược được
và làm hỏng ground truth của câu hỏi loại `authors`.

### 3.3 Rule loại bỏ và dedupe

| Điều kiện | Hành động |
|---|---|
| Thiếu `DOI` | loại |
| `title` rỗng sau normalize | loại |
| `summary` rỗng sau strip JATS | loại |
| `len(summary) < 100` ký tự | loại (quá ngắn để sinh câu hỏi/embed) |
| Trùng `paper_id` | giữ bản đầu tiên (`drop_duplicates(subset="paper_id", keep="first")`) |
| Không parse được `published` | loại |

**Mọi lần loại và dedupe phải để lại số đếm.** Yêu cầu của CP1: *"đừng làm mất record âm
thầm"*. Tối thiểu in ra: `raw_count`, `dropped_no_title`, `dropped_short_summary`,
`dropped_duplicate`, `clean_count`.

Sắp xếp cuối cùng: `df.sort_values("published", ascending=False)` — để corruption
"drop latest records" ở CP5 có nghĩa rõ ràng.

---

## 4. Contract 3 — `text_for_embedding` và `age_days`

### 4.1 🔧 Công thức chuẩn của `text_for_embedding`

```python
text_for_embedding = (
    f"{title}\n\n"
    f"{summary}\n\n"
    f"Authors: {authors_joined}\n"
    f"Categories: {categories_joined}\n"
    f"Published: {published}"
)
```

Phải chứa cả authors, categories và published — vì test set có câu hỏi thuộc 4 loại đó
(§6). Nếu chỉ embed `title + summary`, câu hỏi loại `authors` và `date` sẽ retrieve sai
document và `retrieval_hit_rate` tụt oan, không phản ánh chất lượng dữ liệu.

> ⚠️ **Bắt buộc rebuild lại cột này sau corruption.** `corrupt_clean_dataframe` phá
> `summary`/`title`/`published` nhưng nếu quên dựng lại `text_for_embedding`, embedding
> vẫn giữ nội dung sạch → metrics không tụt → cả bài mất ý nghĩa (Rubric mục 8).

### 4.2 `age_days`

```python
age_days = (run_date.date() - published_date).days
```

`run_date` **truyền vào từ ngoài** (`build_clean_dataframe(records, run_date)` — chữ ký đã
có sẵn tại `src/ingestion/cleaning.py:10`), không gọi `datetime.now()` bên trong. Lý do:
baseline và repaired phải dùng cùng mốc thời gian thì so sánh freshness mới công bằng.

---

## 5. Contract 4 — Index, collection và metadata

`src/retrieval/index.py` **đã viết sẵn**, VT3 không phải code lại. Việc của VT3 là bảo đảm
clean data khớp contract và ba trạng thái không đè nhau.

### 5.1 Ba bộ ba path ↔ collection

| Trạng thái | `embeddings_output_path` | Collection tự suy ra |
|---|---|---|
| baseline | `paths.embeddings_json` | `papers-baseline` |
| corrupted | `paths.corrupted_embeddings_json` | `papers-corrupted` |
| repaired | `paths.repaired_embeddings_json` | `papers-repaired` |

Tên collection **không tự đặt** — `_derive_collection_name` (`index.py:68-81`) map theo
đường dẫn file manifest. **VT1 phải truyền đúng `embeddings_output_path` khi gọi
`LocalEmbeddingIndex.build()`.** Truyền sai hoặc bỏ trống → cả ba phase cùng ghi vào
`papers-baseline` và phá luôn nguyên tắc bất biến số 3.

### 5.2 Metadata tối thiểu (cố định tại `index.py:55-62`)

`paper_id`, `title`, `published`, `authors_joined`, `categories_joined`, `summary`,
`abs_url`, `pdf_url` — đúng 8 field, tất cả là scalar.

### 5.3 Hai cái bẫy của Chroma

- `LocalEmbeddingIndex.__init__` gọi `get_collection` (`index.py:39`) → **`load()` sẽ crash
  nếu chưa từng `build()`**. Luôn build trước trong cùng một lần chạy.
- `build()` **xoá collection cùng tên** trước khi tạo mới (`index.py:97-100`). Ba collection
  dùng chung thư mục `data/chroma/`, nên chỉ an toàn khi tên khác nhau.

### 5.4 Smoke test VT3 phải chạy sau khi build

```python
r = index.search("agentic retrieval augmented generation", top_k=4)
assert len(r) == 4 and r[0].score >= r[-1].score
assert index.lookup(df.iloc[0]["paper_id"]) is not None
assert index.lookup(df.iloc[0]["title"]) is not None
```

---

## 6. Contract 5 — Test set *(cái bẫy lớn nhất của bài)*

### 6.1 Schema mỗi item (cố định tại `src/evaluation/metrics.py:113-131`)

```json
{
  "id": "q001",
  "question_type": "summary | authors | date | categories",
  "question": "...",
  "ground_truth": "...",
  "ground_truth_doc_ids": ["10.5555/xxxx"]
}
```

`ground_truth_doc_ids` **phải là `paper_id` lấy từ clean dataset**. `metrics.py:116` so nó
với `result.retrieved_doc_ids`, mà giá trị đó chính là `paper_id` (`src/retrieval/qa.py:53`).
**Cấm tự bịa ID.**

### 6.2 ⚠️ `answer_question` là rule-based, KHÔNG dùng LLM

`src/retrieval/qa.py:20-29` match chuỗi cứng để quyết định trả về field nào:

| Câu hỏi bắt buộc chứa | Hàm trả về |
|---|---|
| `"who authored"` hoặc `"list the authors"` | `metadata["authors_joined"]` |
| `"when was"` / `"publication date"` / `"published on"` | `metadata["published"]` |
| `"what categories"` | `metadata["categories_joined"]` |
| *(không khớp gì)* | `first_sentence(metadata["summary"])` |

Và `qa.py:33` dùng regex `'([^']+)'` — **tên paper phải nằm trong dấu nháy đơn** thì mới
kích hoạt exact lookup.

**Hệ quả:** viết `"Who are the authors of X?"` sẽ rơi vào nhánh mặc định và trả về câu đầu
của summary → `token_f1 ≈ 0` dù retrieval đúng hoàn toàn. Đây là chỗ mất điểm oan phổ biến
nhất.

### 6.3 🔧 4 template bắt buộc dùng nguyên văn

| `question_type` | `question` | `ground_truth` |
|---|---|---|
| `summary` | ``What is the paper '<title>' about?`` | `first_sentence(summary)` |
| `authors` | ``Who authored the paper '<title>'?`` | `authors_joined` |
| `date` | ``When was the paper '<title>' published?`` | `published` |
| `categories` | ``What categories does the paper '<title>' belong to?`` | `categories_joined` |

`ground_truth_doc_ids = [paper_id]` của chính paper đó.
`first_sentence` có sẵn tại `src/core/utils.py:50` — dùng đúng hàm đó để ground truth khớp
byte-by-byte với thứ `qa.py` trả về.

### 6.4 Quy mô

Tối thiểu 12 câu, khuyến nghị **4 paper × 4 loại = 16 câu**. Chọn paper có `summary` dài và
`authors_joined` không rỗng. Test set ghi ra `paths.eval_testset` và **khoá lại từ CP2** —
baseline, corrupted, repaired dùng chung đúng file này.

---

## 7. Contract 6 — Quality signals và freshness

### 7.1 Data quality checks (`run_data_quality_checks`)

| Check | Điều kiện pass | Cột |
|---|---|---|
| `row_count_min` | `len(df) >= 20` | — |
| `paper_id_not_null` | không null | `paper_id` |
| `paper_id_unique` | `nunique == len` | `paper_id` |
| `title_not_null` | không null / không rỗng | `title` |
| `summary_min_length` | `summary_chars >= 100` | `summary_chars` |
| `no_duplicate_rows` | không có dòng trùng hoàn toàn | — |
| `freshness_age` | `age_days <= 180` | `age_days` |

Ngưỡng 180 lấy từ `settings.freshness_threshold_days` (`config.py:73`) — **không hard-code
số 180 trong `quality.py`**.

Kết quả ghi vào `paths.quality_dir`, tên file theo tham số `report_name` để ba trạng thái
không đè nhau: `baseline`, `corrupted`, `repaired`.

### 7.2 Freshness report (`build_freshness_report` → `paths.freshness_report`)

Payload bắt buộc: `latest_published`, `oldest_published`, `stale_rows`, `total_rows`,
`is_fresh`.

Mốc thời gian lấy từ cột `published` của dữ liệu, **không** lấy `datetime.now()` làm nguồn
sự thật.

### 7.3 Ghi chú về baseline

Filter Crossref đã chặn sẵn `from-pub-date:<hôm nay−180d>` → **baseline gần như chắc chắn
`is_fresh = True` và `stale_rows = 0`**. Đó là kết quả đúng, không phải lỗi. Chính vì vậy
corruption "làm stale publication date" ở CP5 mới tạo được tín hiệu tương phản rõ ràng.

---

## 8. Contract 7 — Corruption và repair

### 8.1 Sáu kịch bản, mỗi kịch bản phải ghi log

| Kịch bản | Tác động dự kiến lên metric/signal |
|---|---|
| Drop N record mới nhất | `freshness.stale_rows` ↑, `retrieval_hit_rate` ↓ với câu hỏi trỏ vào record bị mất |
| Blank `summary` | `summary_min_length` fail, `token_f1` ↓ mạnh với loại `summary` |
| Thêm noise vào `summary` | `token_f1` ↓, judge score ↓ |
| Truncate `title` | `lookup()` theo title fail → exact match mất |
| Làm cũ `published` | `age_days` ↑, `freshness_age` fail, `is_fresh = False` |
| Thêm dòng duplicate | `paper_id_unique` fail, `no_duplicate_rows` fail |

`paths.corruption_log` phải ghi cho **từng** kịch bản: loại, tham số, danh sách `paper_id`
bị tác động, count trước/sau. Yêu cầu CP5: *"Lỗi data phải có chủ đích, có log và đo được
tác động; không tạo corruption chỉ để có file."*

### 8.2 Ranh giới cứng

- Corruption chỉ đọc/ghi `data/clean/papers_clean*.csv`. **Không bao giờ chạm `data/raw/`.**
- Corrupted ghi vào `paths.corrupted_clean_csv` / `_json`, **không đè** `papers_clean.csv`.
- Sau khi phá xong → **rebuild `text_for_embedding`** (xem §4.1).

### 8.3 Repair

```
load_raw_records(paths.raw_records_json)
    → build_clean_dataframe(records, run_date)
    → ghi paths.repaired_clean_csv / _json
```

**Cấm** copy `papers_clean.csv` sang `papers_clean_repaired.csv`, và cấm sửa tay answers
hoặc metrics. Repair phải là kết quả chạy lại thật từ raw.

---

## 9. Sơ đồ handoff

```
 [VT2] Crossref API ──▶ [VT2] clean ──▶ [VT3] index ──▶ [VT4] evaluate ──▶ [VT4] report
        │                    │                │                │                  │
  raw_api_response     papers_clean.csv   papers-baseline  baseline_metrics  phase1_report.md
  raw_records_json     papers_clean.json  embeddings.json  baseline_answers
        │                    │                                 ▲
        │                    └──▶ [VT4] test_set.json ─────────┘   (khoá từ CP2)
        │                    │
        │                    └──▶ [VT4] quality + freshness
        │
        │  ═══════════ sau khi baseline đủ artifact ═══════════
        │
        └──▶ [VT2] corrupt ──▶ [VT3] papers-corrupted ──▶ [VT4] corrupted_metrics
             (log bắt buộc)                                      │
        └──▶ [VT2] repair từ raw ──▶ [VT3] papers-repaired ──▶ [VT4] repaired_metrics
                                                                 │
                                              [VT4] corruption_report.md (delta 3 trạng thái)

  [VT1] sở hữu 2 orchestrator gọi toàn bộ chuỗi trên:
        src/pipelines/phase1.py          ← script/run_phase1.py
        src/pipelines/corruption_flow.py ← script/run_corruption_flow.py
```

---

## 10. Tiêu chí hoàn thành theo checkpoint

| CP | Pass khi | Lệnh kiểm tra |
|---|---|---|
| **CP0** | `data/raw/` có 2 file; `paper_id` là DOI ổn định; mỗi người biết artifact mình giao | `ls data/raw` |
| **CP1** | Clean CSV/JSON đọc được; `paper_id` unique; có `text_for_embedding` + `age_days`; count record bị loại truy vết được | `ls data/clean` |
| **CP2** | `test_set.json` + embedding manifest + collection baseline tồn tại; search/lookup/agent đều trả kết quả có nguồn | `find data -maxdepth 2 -type f \| sort` |
| **CP3** | `baseline_metrics.json`, answers, quality/freshness, `phase1_report.md` tồn tại và **khớp nhau** | `python script/run_phase1.py` |
| **CP5** | Corruption log + corrupted artifacts đủ; **baseline không bị ghi đè** | `python script/run_corruption_flow.py` |
| **CP6** | Repaired artifacts + comparison report có đủ delta 3 trạng thái; repo không có secret | `ls data/results/repaired_metrics.json data/reports/corruption_report.md` |

> Baseline chỉ hoàn tất khi artifact, metrics và report khớp nhau — **không phải khi script
> exit code 0**.

---

## 11. Quy tắc git

| Việc | Quy ước |
|---|---|
| Branch | `feat/cp<N>-<mô-tả>`, `docs/cp<N>-<tên>`, `chore/cp<N>-<mô-tả>` |
| Commit | `<type>(cp<N>): <mô tả>` — ví dụ `feat(cp0): fetch+parse Crossref` |
| Merge | PR vào `main`; VT1 review PR chạm vào contract |
| `.env` | Đã ignore tại `.gitignore:2`. **Không bao giờ `git add -f .env`** |
| `data/chroma/` | Đã ignore — sqlite binary, tái lập được bằng `build()` |
| Artifact khác trong `data/` | **Commit hết.** Rubric yêu cầu raw/clean/eval/results đầy đủ |

Trước mỗi PR, tự kiểm 4 câu: đúng contract chưa? có hard-code path/secret không? có làm hỏng
module kế tiếp không? có artifact hoặc lệnh xác minh đi kèm không?

---

## 12. Nhật ký thay đổi contract

| Ngày | Ai | Thay đổi | Lý do |
|---|---|---|---|
| 2026-08-06 | VT1 | Bản đầu tiên, chốt tại CP0 | — |
