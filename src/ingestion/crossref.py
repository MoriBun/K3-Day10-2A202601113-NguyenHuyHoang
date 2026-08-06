"""Ingestion tu Crossref REST API.

Trien khai theo CONTRACT.md muc 2. Ba diem bat buoc:

1. `paper_id` = DOI viet thuong -- ID on dinh giua cac lan fetch. Neu ID doi,
   ban repaired o CP6 se khong khop `ground_truth_doc_ids` cua test set va
   `retrieval_hit_rate` tut ve 0 du du lieu da phuc hoi dung.
2. Raw response duoc GHI XUONG FILE TRUOC KHI PARSE. Day la nguon repair duy
   nhat o CP6; parse truoc roi moi luu la mat kha nang khoi phuc.
3. Retry/backoff cho 429/503. Loi tam thoi cua Crossref khong duoc phep thay
   bang du lieu bia.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import html
import os
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"

_TAG_RE = re.compile(r"<[^>]+>")
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_TIMEOUT_SECONDS = 30
_BACKOFF_CAP_SECONDS = 30


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list `PaperRecord`.

    Chi loai record hong ve mat cau truc (thieu DOI hoac title) -- day la
    ranh gioi cua CONTRACT.md muc 2.2. Cac rule chat luong (summary qua ngan,
    published khong parse duoc) thuoc ve `cleaning.py` muc 3.3, de raw giu
    duoc nhieu thong tin nhat co the cho buoc repair.
    """
    items = ((payload or {}).get("message") or {}).get("items") or []

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()

    for item in items:
        paper_id = normalize_whitespace(str(item.get("DOI") or "")).lower()
        if not paper_id or paper_id in seen_ids:
            continue

        titles = item.get("title") or []
        title = normalize_whitespace(str(titles[0])) if titles else ""
        if not title:
            continue

        categories = _categories(item)

        seen_ids.add(paper_id)
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=_strip_jats(item.get("abstract")),
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=_published_date(item),
                updated=_updated_date(item),
                abs_url=normalize_whitespace(str(item.get("URL") or "")),
                pdf_url=_pdf_url(item.get("link")),
                # Crossref khong co truong tuong duong; giu lai de dung schema.
                comment="",
            )
        )

    return records


def _strip_jats(value: object) -> str:
    """Abstract cua Crossref la JATS XML: `<jats:p>...</jats:p>`, kem HTML entity.

    Khong xu ly buoc nay thi tag XML se lot vao `text_for_embedding` va lam
    nhieu embedding (CONTRACT.md muc 2.4).
    """
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    # Pass thu hai: bat truong hop tag bi encode hai lan (`&lt;jats:p&gt;`).
    text = _TAG_RE.sub(" ", text)
    text = normalize_whitespace(text)
    # JATS thuong co `<jats:title>Abstract</jats:title>` (hoac Summary) o dau.
    # Sau khi strip tag, nhan nay dinh vao dau abstract va se lot vao
    # `ground_truth` cua cau hoi loai summary -> bo di.
    for label in ("abstract", "summary", "graphical abstract"):
        if text.lower().startswith(label + " "):
            text = text[len(label) + 1 :].strip()
            break
    return text


def _categories(item: dict) -> list[str]:
    """Chu de cua paper.

    Crossref da ngung cap nhat truong `subject`: do trong bo du lieu cua nhom
    la 0/24 record. Neu de rong thi cau hoi loai `categories` trong test set se
    co ground_truth rong va khong cham diem duoc.

    Nen dung proxy khi `subject` vang: `type` (24/24) + venue lay tu
    `container-title` (16/24), thieu thi lui ve `publisher` (24/24). Moi record
    vi vay luon co it nhat 2 gia tri co nghia. Xem CONTRACT.md muc 2.2.
    """
    values = [normalize_whitespace(str(s)) for s in (item.get("subject") or [])]
    values = [v for v in values if v]

    if not values:
        work_type = normalize_whitespace(str(item.get("type") or ""))
        if work_type:
            values.append(work_type)

        container = item.get("container-title") or []
        venue = normalize_whitespace(str(container[0])) if container else ""
        if not venue:
            venue = normalize_whitespace(str(item.get("publisher") or ""))
        if venue:
            values.append(venue)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value.lower() not in seen:
            seen.add(value.lower())
            deduped.append(value)
    return deduped


def _parse_authors(authors: object) -> list[str]:
    parsed: list[str] = []
    for author in authors or []:
        if not isinstance(author, dict):
            continue
        given = normalize_whitespace(str(author.get("given") or ""))
        family = normalize_whitespace(str(author.get("family") or ""))
        full_name = " ".join(part for part in (given, family) if part)
        if not full_name:
            # Tac gia la to chuc -> Crossref dung truong `name`.
            full_name = normalize_whitespace(str(author.get("name") or ""))
        if full_name:
            parsed.append(full_name)
    return parsed


def _published_date(item: dict) -> str:
    """Crossref co nhieu truong ngay xuat ban; thu theo do tin cay giam dan."""
    for key in ("published", "issued", "published-online", "published-print", "created"):
        parsed = _date_from_parts(item.get(key))
        if parsed:
            return parsed
    return ""


def _date_from_parts(container: object) -> str:
    """`date-parts` co the la [Y], [Y, M] hoac [Y, M, D] -> thieu thi mac dinh 1."""
    if not isinstance(container, dict):
        return ""
    date_parts = container.get("date-parts") or []
    if not date_parts or not isinstance(date_parts[0], list):
        return ""

    parts = [p for p in date_parts[0] if p is not None]
    if not parts:
        return ""

    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        # Ngay khong hop le (vi du 2026-02-30) -> lui ve ngay dau thang.
        try:
            return date(int(parts[0]), min(max(int(parts[1]), 1), 12) if len(parts) > 1 else 1, 1).isoformat()
        except (TypeError, ValueError, IndexError):
            return ""


def _updated_date(item: dict) -> str:
    for key in ("indexed", "deposited"):
        container = item.get(key)
        if isinstance(container, dict) and container.get("date-time"):
            try:
                raw = str(container["date-time"]).replace("Z", "+00:00")
                return datetime.fromisoformat(raw).date().isoformat()
            except ValueError:
                continue
    return _published_date(item)


def _pdf_url(links: object) -> str:
    for link in links or []:
        if not isinstance(link, dict):
            continue
        if str(link.get("content-type") or "").lower() == "application/pdf":
            return normalize_whitespace(str(link.get("URL") or ""))
    return ""


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref, luu raw response, parse thanh records, luu records."""
    params: dict[str, Any] = {
        "query.bibliographic": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }

    # Crossref khong can API key. `mailto` dua request vao "polite pool" (it bi
    # 429 hon). Doc tu env chu khong hard-code de khong day email len repo public.
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto

    payload = _request_with_retry(CROSSREF_API_URL, params)

    # BAT BUOC: luu raw response TRUOC khi parse (CONTRACT.md muc 2.5).
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])

    total = ((payload or {}).get("message") or {}).get("total-results")
    print(
        f"[crossref] items={len(((payload or {}).get('message') or {}).get('items') or [])} "
        f"-> records={len(records)} (total-results tren Crossref: {total})"
    )
    return records


def _request_with_retry(url: str, params: dict[str, Any]) -> dict:
    headers = {"User-Agent": "day10-data-pipeline-lab/0.1 (+https://api.crossref.org)"}
    last_error: Exception | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == _MAX_ATTEMPTS:
                break
            _sleep_backoff(attempt, None)
            continue

        if response.status_code in _RETRY_STATUS:
            last_error = RuntimeError(f"HTTP {response.status_code} tu Crossref")
            if attempt == _MAX_ATTEMPTS:
                break
            _sleep_backoff(attempt, response.headers.get("Retry-After"))
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError(
        f"Crossref khong phan hoi thanh cong sau {_MAX_ATTEMPTS} lan thu: {last_error}. "
        "Khong duoc thay bang du lieu bia -- thu lai sau hoac dung snapshot trong data/raw/."
    )


def _sleep_backoff(attempt: int, retry_after: str | None) -> None:
    delay = min(2**attempt, _BACKOFF_CAP_SECONDS)
    if retry_after:
        try:
            delay = min(max(float(retry_after), 1.0), _BACKOFF_CAP_SECONDS)
        except ValueError:
            pass
    print(f"[crossref] lan thu {attempt} that bai, cho {delay:.0f}s roi thu lai...")
    time.sleep(delay)


# --------------------------------------------------------------------------
# Loading snapshot (duong repair cua CP6)
# --------------------------------------------------------------------------


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot da parse va map nguoc thanh `PaperRecord`.

    CP6 repair bang cach goi ham nay roi chay lai `build_clean_dataframe`,
    KHONG copy file clean cu.
    """
    payload = read_json(Path(path))
    if not isinstance(payload, list):
        raise ValueError(f"{path} phai chua mot JSON list cac record.")

    records: list[PaperRecord] = []
    for row in payload:
        records.append(
            PaperRecord(
                paper_id=str(row.get("paper_id") or ""),
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
                authors=[str(a) for a in (row.get("authors") or [])],
                categories=[str(c) for c in (row.get("categories") or [])],
                primary_category=str(row.get("primary_category") or ""),
                published=str(row.get("published") or ""),
                updated=str(row.get("updated") or ""),
                abs_url=str(row.get("abs_url") or ""),
                pdf_url=str(row.get("pdf_url") or ""),
                comment=str(row.get("comment") or ""),
            )
        )
    return records
