# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Ngô Thị Hằng |
| Mã học viên | 2A202601365 |
| Khóa/Lớp | K3 |
| Tên nhóm | PRAI |
| Vai trò chính | Role 3 — RAG & Agent owner |
| Repository | `K3-Day10-2A202601113-NguyenHuyHoang` |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

Role 3 phụ trách đưa dữ liệu clean vào vector store, kiểm tra retrieval/lookup và xác minh agent chỉ trả lời factual dựa trên corpus.

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Embedding và Chroma index | `src/retrieval/index.py`, `src/retrieval/embeddings.py` | Clean DataFrame | Chroma collection và embedding manifest | Hoàn thành |
| Smoke plan | `src/retrieval/smoke.py` | `index.documents` | Semantic query và exact lookup có expected ID | Hoàn thành |
| RAG agent | `src/retrieval/agent.py` | `LocalEmbeddingIndex`, cấu hình LLM | Agent có `semantic_search_papers` và `lookup_paper` | Hoàn thành |
| So sánh ba trạng thái index | `data/embeddings/papers_embeddings*.json`, Chroma | Baseline/corrupted/repaired clean data | Ba collection tách biệt và smoke evidence | Hoàn thành |

Hỗ trợ ngoài phạm vi chính: chuẩn hoá metadata thiếu thành chuỗi rỗng trước khi add vào Chroma để tránh giá trị `NaN`; tái tạo repaired data từ raw snapshot để có đầu vào hợp lệ cho index repaired.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Build baseline index | `data/embeddings/papers_embeddings.json` | `papers-baseline`, 24 documents | Manifest và `collection.count()` đều là 24 |
| Build corrupted index | `data/embeddings/papers_embeddings_corrupted.json` | `papers-corrupted`, 24 documents | Collection tên riêng, baseline vẫn 24 documents |
| Build repaired index | `data/embeddings/papers_embeddings_repaired.json` | `papers-repaired`, 24 documents | Collection tên riêng, top-1 phục hồi như baseline |
| Smoke retrieval và lookup | `src/retrieval/smoke.py` | Query/lookup có kết quả truy vết được | SafeRAG top-1 ở baseline và repaired; exact lookup trả đúng `paper_id` |
| Smoke agent | `src/retrieval/agent.py` | Agent gọi tool rồi trả lời factual | Gemini trả lời ngày xuất bản SafeRAG sau 1 tool call |

Evidence cụ thể: query về SafeRAG cho baseline trả `10.2118/234689-pa` top-1 với score `0.6826`. Ở collection corrupted, tài liệu này rơi khỏi top-2. Khi repair từ raw rồi build `papers-repaired`, nó trở lại top-1 với score `0.6826`.

## 4. Giải thích kỹ thuật

### Vấn đề cần giải quyết

RAG chỉ đáng tin nếu clean data được biến đổi nhất quán thành vector và metadata, collection của ba trạng thái không ghi đè nhau, và agent có thể truy vết câu trả lời về đúng tài liệu.

### Cách triển khai

Model embedding là `sentence-transformers/all-MiniLM-L6-v2`. Documents và query đều được chuẩn hoá embedding; Chroma dùng khoảng cách cosine. Mỗi record dùng ID `<paper_id>::<row_index>`, content là `text_for_embedding`, metadata gồm `paper_id`, `title`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url`.

`LocalEmbeddingIndex._derive_collection_name()` ánh xạ manifest baseline/corrupted/repaired sang lần lượt `papers-baseline`, `papers-corrupted`, `papers-repaired`. Vì vậy rebuild corrupted/repaired không xoá baseline. `lookup()` kiểm tra exact `paper_id` hoặc exact title; `search()` dùng vector query và trả `SearchResult` có score, content và metadata.

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean DataFrame có `paper_id`, `title`, `text_for_embedding` và metadata bắt buộc |
| Output | Chroma persistent store và manifest JSON chứa collection, model, documents |
| Module phụ thuộc | `cleaning.py`, `core/config.py`, `chromadb`, `sentence-transformers` |
| Module sử dụng output | `qa.py`, `agent.py`, evaluation pipeline |
| Lỗi cần xử lý | Metadata null/`NaN`, collection bị ghi đè, LLM model không khả dụng hoặc provider tạm quá tải |

### Cách xác minh

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

Với phần RAG, tôi còn kiểm tra trực tiếp `collection.count()`, query top-k, exact lookup và số tool messages trong kết quả `agent.invoke()`. Kết quả thực tế: ba collection đều độc lập 24 documents; agent repaired gọi 1 tool rồi trả lời ngày xuất bản SafeRAG là 2026-08-01.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần lưu baseline, corrupted và repaired trong cùng persistent Chroma directory.
- **Phương án đã cân nhắc:** Dùng một collection rồi xoá/build lại; hoặc dùng collection và manifest riêng cho từng trạng thái.
- **Phương án đã chọn:** `papers-baseline`, `papers-corrupted`, `papers-repaired` cùng các manifest JSON tương ứng.
- **Lý do:** Có thể so sánh công bằng, tái lập retrieval và kiểm tra baseline không bị mutate. Chi phí storage tăng nhỏ vì corpus chỉ 24 documents.
- **Bằng chứng:** Sau build corrupted, `papers-baseline` vẫn có 24 documents. Cùng query SafeRAG: baseline/repaired top-1 là `10.2118/234689-pa`, còn corrupted top-1 đổi sang `10.20944/preprints202604.0339.v1`.

## 6. Lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Chroma không chấp nhận metadata thiếu vì CSV có các `pdf_url` rỗng được pandas biểu diễn là `NaN`.
- **Nguyên nhân gốc:** Chroma metadata chỉ nhận các kiểu scalar hợp lệ; `NaN` không phải giá trị metadata hợp lệ.
- **Cách xử lý:** Trong `_build_documents`, chuẩn hoá giá trị thiếu thành chuỗi rỗng trước khi tạo content/metadata.
- **Xác minh:** Build thành công ba collection, mỗi collection có 24 documents.
- **Bài học:** Contract metadata phải tính cả giá trị thiếu, không chỉ danh sách tên cột.

Ngoài ra, `gemini-2.5-flash` bị API từ chối cho key hiện tại. Cấu hình được chuyển sang `gemini-3.5-flash`; agent sau đó tool-call thành công. Có một lượt Gemini trả `503 UNAVAILABLE` do tải cao, retry sau đó thành công; lỗi này được ghi nhận là lỗi dịch vụ tạm thời, không phải bằng chứng retrieval sai.

## 7. Hiểu biết về luồng end-to-end

Crossref được lưu raw response và raw records trước khi cleaning. Cleaning chuẩn hoá field, tạo `text_for_embedding`, rồi Role 3 build vector index từ dataframe clean. Test set giữ `ground_truth_doc_ids` là `paper_id`; evaluator dùng chúng để so ID retrieved và chấm câu trả lời. Quality checks kiểm schema, null/duplicate/độ dài summary; freshness monitoring đo tuổi publication và số record stale. Cùng test set/top-k phải được giữ cho ba trạng thái để khác biệt chỉ đến từ dữ liệu. Repair thành công khi repaired artifact được tạo lại từ raw, index riêng, quality/freshness và metrics được đánh giá lại; ở phạm vi Role 3, query SafeRAG đã phục hồi top-1.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | Chưa sinh artifact | Chưa sinh artifact | Baseline có 60 samples; không suy diễn số liệu hai trạng thái chưa evaluate |
| `mean_token_f1` | 1.0000 | Chưa sinh artifact | Chưa sinh artifact | Chỉ có `baseline_metrics.json` |
| `judge_accuracy` | 0.9667 | Chưa sinh artifact | Chưa sinh artifact | Baseline judge dùng 60 samples |
| `mean_judge_score` | 4.9000 | Chưa sinh artifact | Chưa sinh artifact | Không tự điền số liệu thiếu |
| Quality checks | 7/7 pass | Chưa sinh report | Chưa sinh report | Baseline có 24 rows, 0 duplicate, 0 stale |
| Freshness status | Fresh, 0/24 stale | Chưa sinh report | Chưa sinh report | Baseline mean age 81 ngày |

Chuỗi bằng chứng đã có ở scope RAG là: drop record SafeRAG trong `corruption_log.json` → query baseline không còn trả SafeRAG top-2 trên `papers-corrupted` → reload raw và clean lại → SafeRAG trở lại top-1 trên `papers-repaired`. Corruption ảnh hưởng rõ nhất là `drop_latest_records` vì nó xoá trực tiếp document đích khỏi corpus, nên vector retrieval không thể trả nó dù embedding model không đổi.

Tôi không kết luận retrieval hit rate/F1/judge của corrupted hoặc repaired đã giảm/phục hồi vì các artifact metrics tương ứng chưa tồn tại. Bước cần thiết tiếp theo là chạy evaluator trên test set đã khoá và ghi `corrupted_metrics.json`, `repaired_metrics.json`, quality/freshness reports trước khi lập comparison report.

## 9. Điều học được và hướng cải thiện

1. Vector index cần contract rõ về content, ID và metadata; thiếu một giá trị `NaN` cũng có thể làm ingest Chroma thất bại.
2. Tách collection và manifest theo trạng thái là điều kiện để kết quả comparison có thể tái lập.
3. Smoke query theo document thật giúp phát hiện ảnh hưởng dữ liệu nhanh, nhưng không thay thế evaluation set và metrics tổng thể.

Nếu có thêm thời gian, tôi sẽ thêm automated smoke test chạy trên cả ba manifest và kiểm tra: count, exact lookup, expected top-1, cùng điều kiện baseline không đổi. Sau đó đo chất lượng bằng test set cố định để báo cáo delta retrieval hit rate/F1/judge thay vì chỉ một case minh hoạ.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Thị Hằng
**Ngày xác nhận:** 2026-08-06
