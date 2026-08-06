from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


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


def _text(value: Any) -> str:
    """Convert Crossref's HTML-ish text fields into compact plain text."""
    if not isinstance(value, str):
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return normalize_whitespace(without_tags)


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return _text(value[0]) if value else ""
    return _text(value)


def _crossref_date(item: dict[str, Any]) -> str:
    """Return the best available Crossref date as an ISO calendar date."""
    for field in (
        "published-print",
        "published-online",
        "published",
        "issued",
        "created",
        "deposited",
        "indexed",
    ):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list):
            continue
        parts = date_parts[0]
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
            return date(year, month, day).isoformat()
        except (IndexError, TypeError, ValueError):
            continue
    return ""


def _authors(item: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in item.get("author", []) if isinstance(item.get("author"), list) else []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(
            " ".join(
                part
                for part in (_text(author.get("given")), _text(author.get("family")), _text(author.get("name")))
                if part
            )
        )
        if name and name not in authors:
            authors.append(name)
    return authors


def _links(item: dict[str, Any]) -> tuple[str, str]:
    resource = item.get("resource")
    primary = resource.get("primary", {}) if isinstance(resource, dict) else {}
    abs_url = _text(item.get("URL")) or _text(primary.get("URL"))
    pdf_url = ""
    links = item.get("link", [])
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            content_type = _text(link.get("content-type")).lower()
            url = _text(link.get("URL"))
            if url and ("pdf" in content_type or url.lower().endswith(".pdf")):
                pdf_url = url
                break
    return abs_url, pdf_url


def _record_from_mapping(item: dict[str, Any]) -> PaperRecord | None:
    paper_id = _text(item.get("DOI") or item.get("paper_id")).lower()
    title = _first_text(item.get("title"))
    summary = _text(item.get("abstract") or item.get("summary"))
    published = _text(item.get("published")) or _crossref_date(item)
    updated = _text(item.get("updated")) or _crossref_date({"indexed": item.get("indexed")})
    authors = _authors(item) if "author" in item else [_text(value) for value in item.get("authors", []) if _text(value)]
    raw_categories = item.get("subject", item.get("categories", []))
    categories = [_text(value) for value in raw_categories if _text(value)] if isinstance(raw_categories, list) else []
    categories = list(dict.fromkeys(categories))
    primary_category = _text(item.get("primary_category")) or (categories[0] if categories else "")
    if "DOI" in item or "URL" in item:
        abs_url, pdf_url = _links(item)
    else:
        abs_url, pdf_url = _text(item.get("abs_url")), _text(item.get("pdf_url"))
    comment = _text(item.get("comment")) or _first_text(item.get("container-title")) or _text(item.get("publisher"))

    if not paper_id or not title:
        return None
    return PaperRecord(
        paper_id=paper_id,
        title=title,
        summary=summary,
        authors=list(dict.fromkeys(authors)),
        categories=categories,
        primary_category=primary_category,
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        comment=comment,
    )


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref works response into the stable project record schema."""
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    items = message.get("items", []) if isinstance(message, dict) else []
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        record = _record_from_mapping(item)
        if record is None or record.paper_id in seen_ids:
            continue
        seen_ids.add(record.paper_id)
        records.append(record)
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch, snapshot, and parse a bounded Crossref query with retry/backoff."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "sort": "published",
        "order": "desc",
    }
    retry_statuses = {429, 500, 502, 503, 504}
    response: requests.Response | None = None
    for attempt in range(4):
        try:
            candidate = requests.get(
                "https://api.crossref.org/works",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "day10-data-observability-lab/0.1 (educational use)",
                },
                timeout=30,
            )
            if candidate.status_code in retry_statuses and attempt < 3:
                time.sleep(2**attempt)
                continue
            candidate.raise_for_status()
            response = candidate
            break
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2**attempt)

    if response is None:  # Defensive guard for type-checkers and future refactors.
        raise RuntimeError("Crossref request did not return a response.")
    payload = response.json()
    write_json(settings.paths.raw_api_response, payload)
    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [record.__dict__ for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load the parsed raw snapshot, ignoring malformed rows safely."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Raw records snapshot must be a JSON list: {path}")
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        record = _record_from_mapping(item)
        if record is None or record.paper_id in seen_ids:
            continue
        seen_ids.add(record.paper_id)
        records.append(record)
    return records
