# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                               |
| ------------------ | --------------------------------------- |
| Họ và tên       | Nguyễn Thị Hoàng Yến                |
| Mã học viên     | 2A202601959                             |
| Khóa/Lớp         | K3                                      |
| Tên nhóm         | PRAI                                    |
| Vai trò chính    | Role 2 — Data foundation & recovery    |
| Repository         | `K3-Day10-2A202601113-NguyenHuyHoang` |
| Ngày hoàn thành | 2026-08-06                              |

## 2. Vai trò và phạm vi công việc

Phụ trách Crossref ingestion, clean schema, corruption và repair. Mục tiêu là tạo dữ liệu có lineage rõ ràng cho index, evaluation và observability.

| Module/deliverable | File/hàm phụ trách                                                                                     | Input nhận vào                | Output bàn giao                                                       | Trạng thái |
| ------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------- | ---------------------------------------------------------------------- | ------------ |
| Ingestion raw      | `src/ingestion/crossref.py`: `fetch_source_records`, `parse_crossref_payload`, `load_raw_records` | Crossref API hoặc raw snapshot | `crossref_response.json`, `crossref_records.json`, `PaperRecord` | Hoàn thành |
| Cleaning           | `src/ingestion/cleaning.py`: `build_clean_dataframe`, `save_clean_dataframe`                        | `list[PaperRecord]`           | Clean CSV/JSON,`text_for_embedding`, freshness fields                | Hoàn thành |
| Corruption         | `src/ingestion/corruption.py`: `corrupt_clean_dataframe`                                              | Baseline clean DataFrame, seed  | Corrupted CSV/JSON và corruption log                                  | Hoàn thành |
| Repair             | Raw snapshot + cleaning pipeline                                                                          | Raw records tin cậy            | Repaired CSV/JSON                                                      | Hoàn thành |

## 3. Kết quả bàn giao và bằng chứng

| Nhiệm vụ               | Artifact                                                                | Kết quả                             | Cách xác minh                                                  |
| ------------------------ | ----------------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------------- |
| Lưu raw artifacts       | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | 24 raw records có thể reload        | `load_raw_records()` đọc snapshot, không cần gọi lại API |
| Tạo baseline clean data | `data/clean/papers_clean.csv`, `papers_clean.json`                  | 24 rows                               | Quality baseline pass 7/7 checks                                 |
| Tạo corrupted data      | `data/clean/papers_clean_corrupted.csv`, `.json`                    | 24 rows sau drop và duplicate        | `data/results/corruption_log.json`, seed 42                    |
| Repair từ raw           | `data/clean/papers_clean_repaired.csv`, `.json`                     | 24 rows clean lại từ 24 raw records | Cleaning log: raw=24 → clean=24                                 |

Các corruption được log đầy đủ gồm drop latest SafeRAG, blank 2 summaries, inject noise 2 records, truncate 2 titles, stale 2 publication dates và duplicate 1 record. Việc log `paper_id`, count và before/after rows giúp các thành viên khác truy vết nguyên nhân thay vì chỉ nhìn kết quả metrics.

## 4. Giải thích kỹ thuật

### Vấn đề cần giải quyết

RAG không thể tái lập hoặc repair nếu raw source không được lưu trước parsing, clean schema không nhất quán, hoặc corruption sửa dữ liệu mà không để lại log. Role 2 tạo contract dữ liệu cho các bước sau.

### Cách triển khai

`parse_crossref_payload()` map payload Crossref về `PaperRecord` với stable `paper_id`. Raw API response được lưu trước parse; `load_raw_records()` đọc lại snapshot để baseline và repair dùng cùng nguồn.

Cleaning chuẩn hoá whitespace cho title/summary, authors/categories, parse published/updated, tính `age_days`, tạo `authors_joined`, `categories_joined`, `summary_chars` và `text_for_embedding`. Record thiếu ID/title/date hoặc summary dưới 100 ký tự bị loại; dedupe theo `paper_id`. CSV dùng các cột joined, JSON giữ list authors/categories.

Corruption dùng seed 42 để tái lập: drop latest record, blank summary, noise, truncate title, stale date và duplicate row. Sau mutation, `text_for_embedding` được build lại bằng cùng hàm với baseline. Repair không copy baseline: raw records được reload rồi chạy lại cleaning pipeline và ghi sang path repaired.

| Thành phần      | Contract                                                                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Input             | Crossref payload hoặc raw-record JSON;`run_date`; DataFrame clean cho corruption                                                       |
| Output            | Raw/clean/corrupted/repaired CSV và JSON; corruption log                                                                                 |
| Consumer          | Role 3 index/agent, Role 4 evaluation/observability                                                                                       |
| Điều kiện lỗi | API 429/503 phải retry/backoff; schema thiếu field, null/empty, duplicate và date không parse được phải được xử lý/truy vết |

### Cách xác minh

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

Baseline report ghi: raw 24 → clean 24, không duplicate, không title/ID rỗng, summary ngắn nhất 826 ký tự. Freshness report cho biết 0/24 stale rows, tuổi trung bình 81 ngày và max 175 ngày dưới ngưỡng 180 ngày.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh baseline, corrupted và repaired mà không làm thay đổi nguồn bằng một lần fetch mới.
- **Phương án cân nhắc:** Fetch Crossref lại ở mỗi phase; hoặc lưu snapshot raw rồi reload snapshot cho cleaning/repair.
- **Phương án chọn:** Lưu `crossref_response.json` và `crossref_records.json`, repair từ `load_raw_records()`.
- **Lý do:** Snapshot giữ cùng corpus, same `paper_id` và cùng ground truth; khác biệt sau corruption xuất phát từ mutation có chủ đích.
- **Bằng chứng:** Repaired dataset có 24 rows và Role 3 đã phục hồi SafeRAG lên top-1 retrieval từ raw-derived repaired data.

## 6. Lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Nếu summary/title thay đổi do corruption nhưng không rebuild `text_for_embedding`, index vẫn chứa nội dung cũ; phép đo impact trở nên không đáng tin.
- **Nguyên nhân gốc:** Embedding input là derived field, không tự cập nhật khi DataFrame source columns bị mutate.
- **Cách xử lý:** Sau các action corruption, gọi `_rebuild_embedding_text()` cho toàn bộ rows; hàm này dùng lại `build_text_for_embedding_from_row()` trong `cleaning.py`.
- **Xác minh:** Corrupted manifest cho thấy các record blank summary/noise có `content` khác baseline; baseline query SafeRAG không còn top-2 trên `papers-corrupted`.
- **Bài học:** Mọi derived field phải được tái tạo từ nguồn khi dữ liệu nguồn thay đổi.

## 7. Hiểu biết về luồng end-to-end

Crossref API → raw response/records → cleaning → clean artifacts → Role 3 tạo MiniLM/Chroma index → test set dùng `paper_id` làm ground-truth document IDs → evaluation đo retrieval và answer quality → quality/freshness giám sát dữ liệu. Corrupted và repaired phải dùng cùng test set/top-k để so sánh công bằng. Quality checks tập trung schema, null, duplicate, summary; freshness tập trung `published`, `age_days` và stale rows. Repair thành công khi raw lineage được giữ, repaired clean/index được tạo riêng và metrics/quality được đánh giá lại.

## 8. Phân tích kết quả

| Metric/signal          |   Baseline |                  Corrupted |                   Repaired | Nhận xét                                                                                      |
| ---------------------- | ---------: | -------------------------: | -------------------------: | ----------------------------------------------------------------------------------------------- |
| Clean rows             |         24 |                         24 |                         24 | Corrupted vẫn 24 vì drop 1 rồi duplicate 1; row count đơn lẻ không đủ phát hiện lỗi |
| `paper_id` duplicate |          0 |                          1 |                          0 | Duplicate được tạo có chủ đích, repair từ raw loại bỏ lại                           |
| `retrieval_hit_rate` |     1.0000 | Chưa sinh metric artifact | Chưa sinh metric artifact | Không suy diễn số liệu chưa evaluate                                                       |
| Quality checks         |   7/7 pass |          Chưa sinh report |          Chưa sinh report | Baseline quality/freshness có artifact                                                         |
| Freshness              | 0/24 stale |      Có action stale date |         Phục hồi từ raw | Cần report corrupted/repaired để định lượng đầy đủ                                   |

Chuỗi bằng chứng: `drop_latest_records` xoá SafeRAG → Role 3 dùng cùng query nhưng SafeRAG rơi khỏi top-2 trong corrupted index → raw snapshot được reload và clean lại → SafeRAG trở lại top-1 trong repaired index. Điều này cho thấy raw lineage và rebuild derived fields là điều kiện cần để repair đáng tin.

## 9. Điều học được và hướng cải thiện

1. Raw snapshot là nền tảng của reproducibility và repair; không nên fetch lại ngẫu nhiên khi làm comparison.
2. Data quality không thể chỉ nhìn row count: duplicate, empty summary và stale date có thể tồn tại dù tổng số dòng giữ nguyên.
3. Dữ liệu xấu ảnh hưởng RAG qua `text_for_embedding`; phải tái tạo field dẫn xuất sau mutation.

Nếu có thêm thời gian, tôi sẽ thêm unit tests cho từng corruption action và chạy quality/freshness/evaluation trên corrupted/repaired để tạo đủ metrics comparison report.

## 10. Cam kết

- [X] Báo cáo phản ánh Role 2 và artifact thực tế.
- [X] Không suy diễn metric corrupted/repaired khi artifact chưa tồn tại.
- [X] Không chứa API key, token hoặc `.env`.
- [X] Có thể giải thích raw → clean → corrupt/repair → index/evaluation.

**Họ và tên:** Nguyễn Thị Hoàng Yến

**Ngày xác nhận:** 2026-08-06
