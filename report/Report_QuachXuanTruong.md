# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Quách Xuân Trường |
| MSSV | 2A202601371 |
| Khóa/Lớp | Khóa 3 |
| Vai trò chính | Role 4 — Evaluation & Observability |

## 2. Vai trò và phạm vi công việc

Tôi phụ trách tạo và xác minh bằng chứng đánh giá cho hệ thống RAG: evaluation set, metrics, data quality, freshness và báo cáo. Tôi không nhận ownership cho ingestion, cleaning, corruption/repair, embeddings, retrieval hay orchestration pipeline.

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Evaluation set | `src/evaluation/testset.py` | Cleaned dataset có `paper_id`, title, summary, authors, published, categories | 16 câu hỏi và ground truth cố định cho 4 paper | Hoàn thành |
| Evaluation metrics | `src/evaluation/metrics.py` | Evaluation set và câu trả lời/retrieval của agent | Metrics và answer artifacts cho baseline, corrupted, repaired | Hoàn thành |
| Quality & freshness | `src/observability/quality.py` | Cleaned/corrupted/repaired dataset | Quality checks và freshness signals | Hoàn thành |
| Reporting | `src/observability/reporting.py` | Metrics, quality và freshness artifacts | `phase1_report.md` và `corruption_report.md` | Hoàn thành |
| Kiểm thử contract Role 4 | `tests/test_role4_contract.py` | Dữ liệu mẫu trong bộ nhớ | 3 unit tests cho test set, quality gate, freshness | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chạy flow tích hợp để tạo evidence đánh giá | Pipeline chung | Đã xác nhận baseline → corrupted → repaired bằng artifact thực tế và LLM judge |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tạo test set tái lập | `src/evaluation/testset.py`, `data/eval/test_set.json` | 16 câu hỏi: 4 mẫu câu hỏi × 4 paper | Kiểm tra `samples: 16` trong metric và unit test |
| Đánh giá retrieval và answer | `src/evaluation/metrics.py`, `data/results/*_metrics.json` | Hit rate, token F1, LLM judge accuracy/score | Chạy Phase 1 và corruption flow |
| Kiểm tra quality/freshness | `src/observability/quality.py`, `data/quality/*.json` | 7 quality checks, trạng thái freshness | Đọc quality/freshness artifact |
| Viết báo cáo so sánh | `src/observability/reporting.py`, `data/reports/*.md` | Báo cáo baseline và corrupted/repaired | Đối chiếu report với JSON artifacts |

Artifact tiêu biểu là `data/reports/corruption_report.md`: report chứng minh corruption làm `retrieval_hit_rate` giảm từ 1.000 xuống 0.750, trong khi repair đưa chỉ số trở lại 1.000. Mọi sample đều dùng LLM judge, thể hiện bởi `judge_mode: "llm"` và `judge_fallback_count: 0`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần chứng minh tác động của data quality lên RAG bằng các kết quả có thể so sánh được, thay vì chỉ báo rằng lệnh chạy thành công. Vì vậy, phần evaluation phải giữ ổn định câu hỏi, ground truth, evaluator và cấu hình retrieval giữa baseline, corrupted và repaired; phần observability phải phát hiện được lỗi dữ liệu và độ cũ của dữ liệu.

### Cách triển khai

Evaluation set chọn 4 paper hợp lệ và tạo 4 dạng câu hỏi cố định cho mỗi paper: summary, authors, published date và categories. Mỗi mẫu giữ `ground_truth_doc_ids` để đo retrieval hit rate, đồng thời có ground truth answer để tính token F1 và chấm bằng LLM judge.

Quality check xác minh tối thiểu 20 dòng, `paper_id` không rỗng/không trùng, title không rỗng, summary có ít nhất 100 ký tự, không có duplicate row và `age_days` hợp lệ theo ngưỡng 180 ngày. Freshness report tách riêng việc theo dõi dữ liệu cũ, ngày xuất bản mới nhất/cũ nhất và các giá trị ngày không hợp lệ. Reporting đọc artifacts để hiển thị cùng lúc metrics, provenance của judge, quality và freshness.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Cleaned dataset; test set/ground truth; agent answers và retrieved document IDs; quality/freshness artifacts |
| Output | Metrics JSON, quality JSON, freshness JSON và Markdown reports |
| Module phụ thuộc | `src/ingestion/cleaning.py` cung cấp clean schema; `src/retrieval/*` cung cấp retrieval/answers; pipeline cung cấp thứ tự chạy |
| Module sử dụng output | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` và người đọc report |
| Điều kiện lỗi cần xử lý | Thiếu/trùng paper ID, summary ngắn, duplicate row, dữ liệu stale/invalid date, LLM judge không gọi được |

### Cách xác minh

```powershell
python script\run_phase1.py
python script\run_corruption_flow.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- **Kết quả thực tế:** Baseline và repaired có hit rate 1.000; corrupted là 0.750; 3 unit tests pass.
- **Artifact/log:** `data/results/*_metrics.json`, `data/quality/*.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh công bằng tác động của corruption và repair.
- **Các phương án đã cân nhắc:** (1) tạo evaluation set mới ở mỗi lần chạy; (2) dùng một test set và ground truth cố định cho cả ba trạng thái.
- **Phương án đã chọn:** Giữ cùng test set, ground truth document IDs, evaluator và `top_k` cho baseline, corrupted và repaired.
- **Lý do:** Nếu đổi câu hỏi hoặc ground truth giữa các lần chạy thì thay đổi metric không thể quy cho chất lượng dữ liệu. Test set cố định làm phép đo tái lập và so sánh được.
- **Bằng chứng quyết định phù hợp:** Cùng 16 samples được dùng trong ba metrics JSON; chỉ số giảm ở corrupted và phục hồi ở repaired.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `429 RESOURCE_EXHAUSTED` khi gọi Gemini model `gemini-2.5-flash`.
- **Lệnh hoặc bước tái hiện:** Chạy pipeline khi quota Gemini free-tier đã hết.
- **Nguyên nhân gốc:** Giới hạn quota request theo project/model của Gemini, không phải lỗi format API key hay lỗi evaluation code.
- **Cách xử lý:** Không coi fallback heuristic là LLM result; sau khi quota khả dụng, chạy lại pipeline và kiểm tra provenance trong metrics.
- **Cách xác minh sau khi sửa:** Cả ba metrics artifacts đều có `judge_mode: "llm"` và `judge_fallback_count: 0`.
- **Điều học được:** Luôn lưu provenance của evaluator để không diễn giải nhầm kết quả fallback thành kết quả chấm bởi LLM.

## 7. Hiểu biết về luồng end-to-end

1. Crossref cung cấp raw records; dữ liệu được cleaning thành clean dataset, sau đó Role 3 tạo embedding/vector index từ nội dung chuẩn hoá.
2. Evaluation set chứa câu hỏi, answer ground truth và `ground_truth_doc_ids`. Retrieved IDs dùng để tính retrieval hit rate; answer dùng để tính token F1 và LLM judge score.
3. Quality checks kiểm tra tính hợp lệ/cấu trúc dữ liệu tại thời điểm chạy; freshness monitoring tập trung vào tuổi dữ liệu và trạng thái stale theo thời gian.
4. Phải dùng cùng test set ở ba trạng thái để metric thay đổi phản ánh tác động của corruption/repair, không phải do thay đổi câu hỏi.
5. Repair thành công khi quality/freshness trở lại pass/fresh và retrieval/answer metrics trở về gần baseline trên cùng test set.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.750 | 1.000 | Corruption làm giảm 0.250; repair phục hồi hoàn toàn. |
| `mean_token_f1` | 1.000 | 0.509 | 1.000 | Nội dung trả lời suy giảm khi dữ liệu bị hỏng. |
| `judge_accuracy` | 1.000 | 0.500 | 1.000 | Một nửa câu trả lời corrupted không đạt theo LLM judge. |
| `mean_judge_score` | 5.000 | 3.312 | 5.000 | Điểm LLM judge giảm 1.688 rồi phục hồi. |
| Quality checks | PASS | FAIL | PASS | Corrupted có duplicate ID/row, summary ngắn và stale rows. |
| Freshness status | FRESH | NOT FRESH | FRESH | Corrupted có 3 stale rows; repaired có 0 stale rows. |

### Kết luận từ số liệu

1. Blank summary, duplicate row/paper ID và stale date trong data corruption → quality FAIL và freshness NOT FRESH → retrieval hit rate giảm 1.000 xuống 0.750, judge accuracy giảm xuống 0.500.
2. Repair từ nguồn raw/clean hợp lệ → mọi quality check PASS và freshness FRESH → retrieval, token F1 và judge accuracy phục hồi về 1.000.

Ảnh hưởng rõ nhất là việc summary bị làm rỗng/ngắn vì summary là một phần quan trọng của nội dung embedding, đồng thời quality artifact xác nhận chỉ còn 22/24 summary đạt tối thiểu 100 ký tự. Tuy nhiên, đây là kết luận theo toàn bộ corruption scenario; log cũng có các tác động đồng thời như duplicate, title truncation và stale date.

Kết quả phù hợp kỳ vọng: corrupted giảm metric và repair phục hồi metric. LLM judge được dùng thật trong cả ba trạng thái, không phải heuristic fallback.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Cùng một test set là điều kiện bắt buộc để so sánh baseline, corrupted và repaired có ý nghĩa.
2. Data quality và freshness là tín hiệu vận hành: chúng chỉ ra dữ liệu lỗi trước khi hoặc đồng thời với việc RAG suy giảm.
3. Chất lượng data đầu vào ảnh hưởng trực tiếp đến retrieval và chất lượng câu trả lời của RAG.

### Nếu có thêm thời gian

Có thể bật Ragas bằng `RUN_RAGAS=1` để bổ sung một lớp đánh giá chậm hơn. Việc cải thiện được đo bằng cách đối chiếu metric Ragas giữa baseline, corrupted và repaired trên cùng test set; các metric hiện tại vẫn là bằng chứng chính vì Ragas chưa được chạy.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.
