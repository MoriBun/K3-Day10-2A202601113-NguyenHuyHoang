# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Huy Hoàng |
| MSSV | 2A202601113 |
| Khóa/Lớp | K3 |
| Tên nhóm | PRAI |
| Vai trò chính | Vai trò 1 — Điều phối pipeline (Pipeline integrator) |
| Repository | https://github.com/MoriBun/K3-Day10-2A202601113-NguyenHuyHoang |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data contract & phân công | `CONTRACT.md` | Code có sẵn trong `src/`, `Rubric.md` | Contract 12 mục, sơ đồ handoff, bảng artifact, tiêu chí pass từng CP | Hoàn thành |
| Môi trường & provider config | `SETUP.md`, `.env`, `.gitignore` | `pyproject.toml`, `.env.example` | Môi trường chạy được, `LLM_PROVIDER=openai` / `gpt-4o-mini` | Hoàn thành |
| Fixture giải phóng phụ thuộc | `fixtures/make_sample.py` | Clean schema đã chốt | `papers_clean_sample.csv/json` 6 dòng đúng schema | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py` | `data/raw/`, các hàm của VT2/VT3/VT4 | 10 artifact của pha 1 | Hoàn thành |
| Corruption orchestration | `src/pipelines/corruption_flow.py` | `papers_clean.csv`, `test_set.json`, `data/raw/` | 16 artifact của pha 2 | Hoàn thành |
| Bằng chứng tích hợp | `script/run_cp5_evidence.py` | `*_answers.json`, `corruption_log.json` | `data/results/cp5_evidence.json` | Hoàn thành |
| Review & release | PR #1–#7, merge vào `main` | PR của 3 thành viên | `main` chạy được end-to-end | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Viết `src/ingestion/crossref.py` | VT2 — CP0 bị trễ, không có `data/raw/` thì cả nhóm đứng | 24 raw record, `data/raw/` đủ 2 file, CP0 pass |
| Sửa `cleaning.py` + `corruption.py` cho khớp contract | VT2 | 7 sai lệch, xem mục 6 |
| Thay phần sinh câu hỏi trong `testset.py` | VT4 | Sửa lỗi nghiêm trọng, xem mục 6 |
| Viết `observability/quality.py` và `reporting.py` | VT4 (đang quá tải 5/7 hàm) | Quality 7 check + 2 report markdown |
| Sửa `index.py::load()` bỏ đường dẫn tuyệt đối | VT3 | `load()` chạy được trên mọi máy |

> **Ghi chú về ownership:** phần code trong bảng "hỗ trợ" là file được phân công cho thành viên khác. Tôi ghi rõ ở đây để không nhận nhầm ownership, và các bạn liên quan cũng đã nêu trong báo cáo của mình. Toàn bộ quá trình có sử dụng AI assistant (Claude) để pair-programming; các quyết định kỹ thuật, tiêu chí chấp nhận và việc xác minh bằng artifact là do tôi thực hiện.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Chốt contract trước khi 4 người code song song | `CONTRACT.md` §3, §6 | Clean schema 13 cột, test-set schema, 4 template câu hỏi | `git log -- CONTRACT.md` (commit trước mọi PR code) |
| Kiểm tra môi trường và provider | `SETUP.md` | Python 3.12.6, 13/13 dependency, 6/6 module import được | `python -c "import core.config, ingestion.crossref, retrieval.index"` |
| Baseline pipeline end-to-end | `src/pipelines/phase1.py` | 10/10 artifact, 60 câu hỏi, metrics đầy đủ | `python script/run_phase1.py` |
| Corruption + repair + comparison | `src/pipelines/corruption_flow.py` | 16/16 artifact, `corruption_report.md` | `python script/run_corruption_flow.py` |
| Đối chiếu report với artifact thật | `data/reports/phase1_report.md` | 4/4 điểm kiểm tra khớp JSON nguồn | So `phase1_report.md` với `baseline_metrics.json` |
| Bằng chứng cho 3 vai trò còn lại | `data/results/cp5_evidence.json` | Lineage, retrieval impact, 10 case study | `python script/run_cp5_evidence.py` |

**Một output cụ thể phần việc của tôi tạo ra:**

`data/reports/corruption_report.md` — bảng so sánh 3 trạng thái trên **cùng một test set 60 câu**, kèm cột delta:

| Metric | Baseline | Corrupted | Repaired | Δ corrupt | Δ repair |
| --- | --: | --: | --: | --: | --: |
| Retrieval hit rate | 1.0000 | 0.9333 | 1.0000 | −0.0667 | +0.0667 |
| Mean token F1 | 1.0000 | 0.8357 | 1.0000 | −0.1643 | +0.1643 |
| Judge accuracy | 0.9667 | 0.8167 | 0.9667 | −0.1500 | +0.1500 |
| Mean judge score | 4.9000 | 4.3667 | 4.9000 | −0.5333 | +0.5333 |

Việc so sánh này chỉ có nghĩa vì orchestration bảo đảm được ba điều: cùng test set, cùng evaluator, cùng `top_k=4`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Vai trò điều phối không giải quyết một bài toán dữ liệu cụ thể, mà giải quyết bài toán **bốn người sửa cùng một luồng dữ liệu trong 4 giờ**. Rủi ro lớn nhất không phải ai đó viết sai thuật toán, mà là bốn người viết đúng theo bốn giả định khác nhau về schema, rồi tới lúc ghép mới phát hiện — khi không còn thời gian sửa.

Rủi ro thứ hai: kết quả so sánh baseline/corrupted/repaired mất giá trị nếu có bất kỳ biến nào khác ngoài chất lượng dữ liệu thay đổi giữa ba lần chạy.

### Cách triển khai

**Chốt contract trước, code sau.** Tôi đọc toàn bộ code có sẵn để tìm những chỗ đã bị ràng buộc cứng rồi viết `CONTRACT.md`. Điểm quan trọng là phần lớn contract **không phải lựa chọn tự do**: `index.py:54-63` đọc thẳng `row["authors_joined"]`, `metrics.py:116` so `ground_truth_doc_ids` với `paper_id`, `qa.py:20-29` match chuỗi cứng. Contract chỉ ghi lại các ràng buộc đó thành văn bản để không ai phải tự đoán.

**Phát fixture để phá phụ thuộc tuần tự.** Luồng tự nhiên là VT2 → VT3 → VT4, nghĩa là hai người ngồi chờ. Tôi sinh `fixtures/papers_clean_sample.csv` 6 dòng đúng 13 cột schema thật, để VT3 build index và VT4 viết test set ngay mà không cần đợi `data/raw/`.

**Ba đảm bảo về tính tái lập trong hai pipeline:**

1. *Không refetch.* `phase1.py` mặc định đọc snapshot `data/raw/`, chỉ gọi Crossref khi `REFRESH_SOURCE=1`. Crossref là nguồn sống — fetch lại giữa chừng là baseline và repaired chạy trên hai tập dữ liệu khác nhau.
2. *Test set khoá từ CP2.* Đã tồn tại thì dùng lại, trừ khi `REFRESH_TEST_SET=1`.
3. *Ba collection tách biệt.* `phase1.py` truyền `paths.embeddings_json`, `corruption_flow.py` truyền `corrupted_embeddings_json` và `repaired_embeddings_json`. Tên collection do `_derive_collection_name` suy ra từ chính đường dẫn đó, nên truyền sai là ba trạng thái ghi đè lên nhau.

**Suy ngược mốc thời gian.** `age_days` phụ thuộc `run_date`. Nếu repaired dùng `datetime.now()` thì nó lệch baseline vài giờ và so sánh freshness không còn chính xác. Tôi suy ngược `run_date` từ chính dữ liệu baseline: `published + age_days` của dòng đầu tiên.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `data/raw/crossref_records.json`, `data/clean/papers_clean.csv`, `data/eval/test_set.json`, `Settings` |
| Output | 10 artifact pha 1 + 16 artifact pha 2, đường dẫn lấy từ `settings.paths` |
| Module phụ thuộc | `ingestion.crossref`, `ingestion.cleaning`, `ingestion.corruption`, `retrieval.index`, `evaluation.testset`, `evaluation.metrics`, `observability.quality`, `observability.reporting` |
| Module sử dụng output | `script/run_phase1.py`, `script/run_corruption_flow.py`, `script/run_cp5_evidence.py` |
| Điều kiện lỗi cần xử lý | Thiếu artifact baseline → dừng sớm có thông báo; LLM lỗi → bỏ qua demo agent nhưng giữ metrics; corruption không giao test set → in cảnh báo |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python script/run_cp5_evidence.py
```

- **Kết quả mong đợi:** hai pipeline chạy hết không traceback; đủ artifact; `papers_clean.csv` không bị corruption ghi đè.
- **Kết quả thực tế:** `phase1` 10/10 artifact; `corruption_flow` 16/16 artifact; bước 7 xác nhận baseline còn 24 dòng, `paper_id` unique = True.
- **Artifact/log:** `data/reports/phase1_report.md`, `data/reports/corruption_report.md`, `data/results/cp5_evidence.json`. Không file nào chứa secret; `.env` nằm trong `.gitignore` từ đầu và chưa từng vào lịch sử git (`git log --all -- .env` rỗng).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `build_clean_dataframe(records, run_date)` nhận `run_date` từ ngoài. Ở CP6, repair chạy lại cleaning từ raw — cách chậm hơn baseline vài giờ. Cần chọn mốc thời gian nào cho lần chạy đó.
- **Các phương án đã cân nhắc:**
  1. Dùng `datetime.now(UTC)` tại thời điểm repair — đơn giản nhất.
  2. Lưu `run_date` của baseline ra file riêng rồi đọc lại — chính xác nhưng thêm một artifact và một điểm hỏng.
  3. Suy ngược từ dữ liệu baseline: `run_date = published + age_days`.
- **Phương án đã chọn:** phương án 3.
- **Lý do:** `age_days` là đầu vào của cả `freshness_age` check lẫn `build_freshness_report`. Nếu baseline và repaired tính trên hai mốc khác nhau thì chênh lệch freshness giữa hai trạng thái lẫn cả sai số thời gian chạy, không còn thuần tuý phản ánh chất lượng dữ liệu. Phương án 3 không cần thêm artifact nào và tự động đúng vì thông tin đã nằm sẵn trong `papers_clean.csv`.
- **Bằng chứng quyết định phù hợp:** `freshness_repaired.json` và `freshness_report.json` (baseline) trùng khớp hoàn toàn: `latest_published = 2026-08-01`, `oldest_published = 2026-02-12`, `stale_rows = 0`. Nếu dùng `datetime.now()`, `age_days` của repaired sẽ lệch baseline và hai file này không thể bằng nhau.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** khi review PR test set của VT4, tôi thấy `mean_token_f1` có nguy cơ chạm sàn ở mọi trạng thái. Bộ câu hỏi được sinh bằng LLM để nghe tự nhiên, với template dự phòng dạng `Who are the authors of "<title>"?`.

- **Lệnh tái hiện:** chạy chính các template đó qua `answer_question` trên dữ liệu thật:

  ```python
  answer_question(f'Who are the authors of "{title}"?', settings=s, index=idx)
  ```

  Kết quả: trả về câu đầu tiên của abstract thay vì danh sách tác giả.

- **Nguyên nhân gốc:** `retrieval/qa.py` **không dùng LLM**. `_extract_answer` (dòng 20-29) match chuỗi cứng — chỉ nhận `"who authored"` hoặc `"list the authors"`; `"who are the authors of"` không khớp chuỗi nào nên rơi vào nhánh mặc định trả về `first_sentence(summary)`. Tương tự, `"what subject categories"` không chứa `"what categories"`. Ngoài ra `answer_question` dùng regex `r"'([^']+)'"` — **nháy đơn** — nên title trong nháy kép không kích hoạt exact lookup.

  Đây là lỗi nguy hiểm vì nó không gây exception. Pipeline vẫn chạy, vẫn ra số, chỉ là số vô nghĩa: `token_f1` sẽ thấp bất kể dữ liệu tốt hay xấu, và như vậy toàn bộ mục tiêu "chứng minh data xấu làm RAG kém đi" sụp đổ.

- **Cách xử lý:** thay phần sinh câu hỏi bằng 4 template cố định trong `CONTRACT.md` §6.3, trả chữ ký hàm về `(df, output_path)` cho khớp `phase1.py`. Giữ lại `_select_representative_papers` của VT4 vì phần đó tốt.

- **Cách xác minh sau khi sửa:** chạy đối chứng hai bộ template trên cùng dữ liệu:

  ```
  TEMPLATE CŨ (nháy kép)        TEMPLATE CONTRACT (nháy đơn)
    summary     ĐÚNG              summary     ĐÚNG
    authors     SAI               authors     ĐÚNG
    date        ĐÚNG              date        ĐÚNG
    categories  SAI               categories  ĐÚNG
  ```

- **Điều học được:** lỗi tệ nhất trong data pipeline là lỗi không ném exception. Trước khi tin một metric, phải kiểm tra xem nó có khả năng thay đổi hay không — một metric luôn bằng 0 và một metric luôn bằng 1 đều đáng nghi như nhau. Bài học thứ hai: khi hàm downstream là rule-based, mọi cải tiến "cho tự nhiên hơn" ở upstream đều có thể là phá hoại; phải đọc code tiêu thụ trước khi thiết kế dữ liệu sản xuất.

## 7. Hiểu biết về luồng end-to-end

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?**

`fetch_source_records` gọi `api.crossref.org/works` với query và filter lấy từ `Settings`, **ghi raw response xuống `data/raw/crossref_response.json` trước khi parse** — đây là điều kiện bắt buộc để CP6 repair được. `parse_crossref_payload` chuyển payload thành `PaperRecord` với `paper_id` là DOI viết thường, strip JATS XML khỏi abstract. `build_clean_dataframe` chuẩn hoá, tính `age_days`, ghép `text_for_embedding` gồm title + summary + authors + categories + published. `LocalEmbeddingIndex.build` embed cột đó bằng `all-MiniLM-L6-v2` và nạp vào collection ChromaDB persistent tại `data/chroma/`.

**2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**

Mỗi câu hỏi mang `ground_truth_doc_ids` là `paper_id` của paper mà câu hỏi hỏi về. `evaluate_pipeline` gọi `answer_question`, nhận về `retrieved_doc_ids` cũng là `paper_id`. `retrieval_hit` = có giao nhau hay không — đo **retrieval**. `token_f1` so câu trả lời với `ground_truth` — đo **answer**. LLM judge chấm thêm 1–5 và đúng/sai. Vì thế `paper_id` phải ổn định: nếu ID đổi giữa các lần chạy thì repaired sẽ trỏ vào ID không tồn tại và hit rate về 0 dù dữ liệu đã đúng.

**3. Quality checks khác freshness monitoring ở điểm nào?**

Quality check hỏi "dữ liệu có **hợp lệ** không" — không null, không trùng, đủ dài. Freshness hỏi "dữ liệu có **còn mới** không" — tính theo `age_days` so với ngưỡng 180 ngày. Một dataset có thể pass toàn bộ quality mà vẫn stale, và ngược lại. Trong bài này chúng bắt hai loại corruption khác nhau: blank summary và duplicate rows bị quality bắt, còn backdate publication chỉ freshness thấy.

**4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**

Vì đây là thí nghiệm có đối chứng. Biến độc lập duy nhất được phép thay đổi là chất lượng dữ liệu. Nếu sinh lại test set giữa chừng, chênh lệch metric sẽ lẫn giữa "dữ liệu xấu đi" và "bộ câu hỏi khác đi", và không tách ra được. Đó là lý do `corruption_flow.py` đọc lại `data/eval/test_set.json` chứ không gọi `build_test_set`.

**5. Repair được xem là thành công dựa trên artifact và metric nào?**

Cần cả ba lớp bằng chứng khớp nhau: (a) metric quay lại mức baseline trong `repaired_metrics.json`; (b) quality trở lại 7/7 trong `quality_repaired.json` và freshness về 0 stale; (c) lineage chứng minh dữ liệu thật sự được dựng lại từ raw chứ không phải chép — trong `cp5_evidence.json`, paper `10.2118/234689-pa` bị drop khỏi corrupted đã xuất hiện lại trong repaired, và 5 cột `paper_id`/`title`/`authors_joined`/`published`/`summary` của repaired giống hệt baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.9333 | 1.0000 | Giảm ít nhất vì title vẫn còn phần lớn thông tin; chỉ 4/60 câu mất hit |
| `mean_token_f1` | 1.0000 | 0.8357 | 1.0000 | Nhạy nhất với corruption — nó đo nội dung câu trả lời chứ không chỉ "có tìm đúng paper không" |
| `judge_accuracy` | 0.9667 | 0.8167 | 0.9667 | Judge độc lập xác nhận cùng xu hướng, không phải hiệu ứng của riêng token overlap |
| `mean_judge_score` | 4.9000 | 4.3667 | 4.9000 | Giảm 0.53 điểm trên thang 5 |
| Quality checks | 7/7 | **3/7** | 7/7 | Bốn check fail: `paper_id_unique`, `summary_min_length`, `no_duplicate_rows`, `freshness_age` |
| Freshness status | 0 stale | **3 stale** | 0 stale | `age_days` max nhảy từ 175 lên 411 |

### Kết luận từ số liệu

1. **Corruption** (truncate title + inject noise + blank summary trên 6/24 paper, trong đó 5 paper nằm trong test set) → **quality tụt 7/7 xuống 3/7, freshness từ 0 lên 3 dòng stale** → **agent metric giảm: token_f1 −0.164, judge_accuracy −0.150, hit_rate −0.067**.

2. **Repair** (chạy lại `build_clean_dataframe` từ `crossref_records.json`, không chép file clean cũ) → **quality về 7/7, freshness về 0 stale** → **cả bốn metric về đúng mức baseline; 10/10 câu hỏi từng xấu đi đều phục hồi hoàn toàn**.

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

Theo `cp5_evidence.json`, thống kê 10 câu hỏi xấu đi theo kịch bản: `truncate_titles` 5 câu, `inject_text_noise` 4 câu, `drop_latest_records` 4 câu (các con số chồng lấn vì một paper có thể dính nhiều kịch bản).

`truncate_titles` gây hại nhiều nhất, và lý do mang tính cấu trúc chứ không ngẫu nhiên: cả 4 loại câu hỏi đều nhắc tên paper trong dấu nháy đơn, nên title là đường dẫn chính vào đúng document — qua cả exact lookup lẫn semantic search. Cắt title là cắt đồng thời hai cơ chế đó. Ví dụ rõ nhất là `q0002`: câu hỏi tác giả, đáp án đúng `"Donald Martin; Blake Bowman"`, sau corruption trả về `"Eason Ni"` — tức là agent tìm nhầm sang một paper khác hẳn, `token_f1` từ 1.0 xuống 0.0, rồi về lại 1.0 sau repair.

Ngược lại, `make_dates_stale` gần như không ảnh hưởng metric của agent (chỉ 1 câu) nhưng lại là kịch bản duy nhất bị freshness bắt. Điều này cho thấy **quality signal và agent metric bắt hai loại hỏng khác nhau**, cần cả hai chứ không thay thế được nhau.

**Kết quả nào khác với kỳ vọng ban đầu?**

`mean_token_f1 = 1.0` ở baseline. Ban đầu tôi nghi ngờ có gì đó sai. Kiểm tra lại thì đây là hệ quả tất yếu của thiết kế: `qa.py` trả về nguyên văn `metadata["authors_joined"]`, mà `ground_truth` trong test set cũng chính là `authors_joined` — hai chuỗi giống hệt nhau nên F1 = 1. Đó không phải model giỏi, mà là trần của bộ khung đánh giá rule-based.

Tôi giữ nguyên vì contract yêu cầu `ground_truth` phải khớp đúng thứ `qa.py` trả về, và vì nó có lợi cho thí nghiệm: baseline hoàn hảo khiến mọi sụt giảm sau corruption đều rõ ràng, không lẫn với nhiễu nền. Nếu baseline chỉ đạt 0.6 thì tụt xuống 0.5 sẽ không kết luận được gì chắc chắn.

Chi tiết củng cố độ tin cậy: judge chấm sai 2/60 câu ngay ở baseline, tức nó thật sự đánh giá chứ không đóng dấu bừa.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** lưu raw response trước khi parse không phải thói quen tốt cho vui, nó là điều kiện cần để có thể phục hồi. Ở giữa bài tôi phải đổi cách lấy `categories` (Crossref trả `subject` rỗng 0/24 record) — nhờ đã có snapshot nên chỉ cần parse lại từ file, không phải gọi API lần hai và không làm dữ liệu lệch đi.

2. **Về data quality/observability:** ngưỡng phải nhất quán xuyên suốt pipeline. `cleaning.py` từng lọc summary ở 20 ký tự trong khi quality check đòi 100 — hậu quả là baseline fail quality check ngay trên dữ liệu sạch, và như vậy mất luôn mốc đối chứng cho corruption. Quality check chỉ có nghĩa khi nó và bước sinh dữ liệu dùng chung một định nghĩa "hợp lệ".

3. **Về ảnh hưởng của data đến RAG agent:** dữ liệu hỏng không làm hệ thống báo lỗi, nó làm hệ thống trả lời sai một cách tự tin. `q0002` trả về `"Eason Ni"` — một cái tên có thật, đúng định dạng, không có dấu hiệu bất thường nào. Chỉ khi so với ground truth mới biết là sai. Đó chính là lý do phải có observability chứ không thể dựa vào việc pipeline chạy không lỗi.

### Nếu có thêm thời gian

Tôi sẽ chạy corruption ở nhiều cường độ khác nhau (tỉ lệ 5%, 15%, 25%, 40%) và vẽ đường quan hệ giữa mức độ hỏng dữ liệu và `mean_token_f1`. Hiện tại tôi mới chứng minh được quan hệ định tính "dữ liệu xấu → metric giảm" tại đúng một điểm. Có đường cong thì trả lời được câu hỏi thực tế hơn: **bao nhiêu phần trăm dữ liệu hỏng thì hệ thống bắt đầu suy giảm rõ rệt** — chính là ngưỡng cần đặt cảnh báo trong giám sát thật. Cách đo: chạy `corruption_flow.py` với các giá trị `_*_FRACTION` khác nhau, mỗi lần ghi ra một `corrupted_metrics.json` riêng, rồi vẽ biểu đồ metric theo tỉ lệ corruption.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Huy Hoàng
**Ngày xác nhận:** 2026-08-06
