# SETUP — môi trường thống nhất cho cả nhóm

> Chủ sở hữu: Vai trò 1. Mọi thành viên chạy đúng các bước dưới đây trước CP1.
> Tài liệu này ghi đè phần lệnh trong `Guide.md` ở hai chỗ, xem §0.

---

## 0. Hai khác biệt so với `Guide.md`

| `Guide.md` viết | Thực tế | Dùng thay bằng |
|---|---|---|
| `uv sync` / `uv run python …` | **`uv` không có trên máy nhóm** | `python -m pip install -e .` / `python script/…` |
| `pip install -r requirements.txt` | Chỉ cài thư viện, **không cài package trong `src/`** | `pip install -e .` (bắt buộc) |

### Vì sao bắt buộc `pip install -e .`

Code import theo dạng top-level chứ không phải `src.*`:

```python
from core.config import Settings          # src/retrieval/index.py:10
from ingestion.crossref import PaperRecord # src/ingestion/cleaning.py:7
```

`pyproject.toml` khai `package-dir = {"" = "src"}`, nên chỉ khi cài editable thì `core`,
`ingestion`, `retrieval`, `evaluation`, `observability`, `pipelines` mới nằm trên
`sys.path`. Nếu chỉ `pip install -r requirements.txt`, `script/run_phase1.py` sẽ chết ngay
dòng import đầu tiên với `ModuleNotFoundError: No module named 'pipelines'`.

---

## 1. Kiểm tra Python

Yêu cầu **3.11 – 3.13** (`pyproject.toml`: `requires-python = ">=3.11,<3.14"`).

```powershell
python --version
```

Máy tham chiếu của nhóm: **Python 3.12.6** ✅

---

## 2. Virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**macOS / Linux / Git Bash**

```bash
python -m venv .venv
source .venv/bin/activate
```

`.venv/` đã nằm trong `.gitignore` — không commit.

---

## 3. Cài dependency

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

⏳ Bước này tải khá nặng: `sentence-transformers` kéo theo PyTorch (~2 GB). Chạy sớm, đừng
để đến CP2 mới cài.

**Xác minh:**

```powershell
python -c "import core.config, ingestion.crossref, retrieval.index; print('imports OK')"
```

---

## 4. Tạo `.env`

```powershell
Copy-Item .env.example .env
```

Chỉ điền credential của **một** provider sẽ dùng. Cấu hình hiện tại của nhóm:

```ini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=<key cua rieng ban>
```

> `.env` đã bị ignore tại `.gitignore:2` và **chưa từng bị commit** — đã kiểm tra.
> Mỗi người tự tạo `.env` với key riêng. Không gửi key qua chat nhóm, không commit.

### ⚠️ Vì sao là `gpt-4o-mini` chứ không phải model mới hơn

`src/retrieval/llm.py:22-26` truyền **cứng** `temperature=temperature` (mặc định `0.0`) vào
`ChatOpenAI`, và `src/evaluation/metrics.py:62` gọi `build_llm(settings, temperature=0.0)`
cho LLM judge. Toàn bộ dòng GPT-5 (reasoning model) chỉ chấp nhận `temperature=1` và sẽ trả
lỗi:

```
Unsupported value: 'temperature' does not support 0 with this model.
```

Đã kiểm chứng bằng request thật: `gpt-4o-mini` OK, `gpt-5-mini` lỗi. Nếu muốn judge mạnh hơn
mà không phải sửa code, đổi sang `LLM_MODEL=gpt-4.1-mini` (cũng nhận `temperature=0`).

### Provider khác

`normalized_provider` / `require_llm_credentials` (`src/core/config.py:138-173`) hỗ trợ:
`openai`, `gemini`, `anthropic`, `openrouter`, `ollama`, `custom`. Đổi provider chỉ cần sửa
`LLM_PROVIDER` + key tương ứng trong `.env`, **không sửa code**.

---

## 5. Chạy pipeline

```powershell
python script\run_phase1.py           # baseline  (CP3)
python script\run_corruption_flow.py  # corruption (CP5)
```

Biến môi trường tuỳ chọn:

| Biến | Tác dụng | Nguồn |
|---|---|---|
| `REFRESH_SOURCE=1` | Fetch lại Crossref thay vì đọc `data/raw/` | `config.py:132` |
| `REFRESH_TEST_SET=1` | Sinh lại test set thay vì dùng file đã khoá | `config.py:133` |
| `RUN_RAGAS=1` | Bật Ragas (chậm, mặc định tắt) | `metrics.py:74` |

> **Để trống cả ba khi so sánh baseline / corrupted / repaired.** Fetch lại giữa chừng hoặc
> sinh lại test set sẽ làm phép so sánh mất công bằng — vi phạm nguyên tắc bất biến số 2
> trong `CONTRACT.md`.

---

## 6. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `ModuleNotFoundError: No module named 'core'` | Chưa cài editable | `pip install -e .` |
| `uv: command not found` | Máy không có `uv` | Dùng lệnh `python` ở §5 |
| Lần chạy đầu treo lâu ở bước embedding | Đang tải model MiniLM (~90 MB) | Chờ; lần sau có cache |
| Chroma in log telemetry ồn | Mặc định của thư viện | Bỏ qua, không ảnh hưởng kết quả |
| `Collection … does not exist` | Gọi `LocalEmbeddingIndex.load()` trước khi `build()` | Build trước trong cùng lần chạy (`CONTRACT.md` §5.3) |
| Judge trả `"Fallback heuristic judge used…"` | `.env` sai hoặc thiếu key | Kiểm tra `LLM_PROVIDER` / key; metrics vẫn chạy nhưng judge không đáng tin |
| Crossref trả `429` | Gọi quá nhanh | Retry/backoff + thêm `mailto` (`CONTRACT.md` §2.5) |

---

## 7. Checklist trước khi báo "môi trường xong"

- [ ] `python --version` trong khoảng 3.11–3.13
- [ ] `.venv` đã activate
- [ ] `python -c "import core.config"` chạy được
- [ ] `.env` tồn tại, có key riêng, **không** xuất hiện trong `git status`
- [ ] Đã đọc hết `CONTRACT.md`
- [ ] Đã push thử một commit để xác nhận có quyền ghi vào repo
