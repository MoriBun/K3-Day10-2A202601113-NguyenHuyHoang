from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


_CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def build_embedding_text(row: dict) -> str:
    """Create the single text field used by the vector index."""
    parts = [
        f"Title: {row.get('title', '')}",
        f"Summary: {row.get('summary', '')}",
        f"Authors: {row.get('authors_joined', '')}",
        f"Categories: {row.get('categories_joined', '')}",
        f"Published: {row.get('published', '')}",
    ]
    return "\n".join(part for part in parts if not part.endswith(": "))


def _normalise_list(values: list[str], fallback: str) -> list[str]:
    cleaned = [normalize_whitespace(value) for value in values if normalize_whitespace(value)]
    return list(dict.fromkeys(cleaned)) or [fallback]


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean source records into a deterministic dataframe ready for retrieval."""
    rows: list[dict] = []
    run_timestamp = pd.Timestamp(run_date)
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.tz_localize(UTC)
    else:
        run_timestamp = run_timestamp.tz_convert(UTC)
    run_timestamp = run_timestamp.normalize()

    for record in records:
        paper_id = normalize_whitespace(record.paper_id).lower()
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)
        if not paper_id or not title or len(summary) < 40:
            continue

        published_timestamp = pd.to_datetime(record.published, errors="coerce", utc=True)
        if pd.isna(published_timestamp):
            continue
        updated_timestamp = pd.to_datetime(record.updated, errors="coerce", utc=True)
        authors = _normalise_list(record.authors, "Unknown")
        categories = _normalise_list(record.categories, "Uncategorized")
        row = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "categories": categories,
            "primary_category": normalize_whitespace(record.primary_category) or categories[0],
            "published": published_timestamp.date().isoformat(),
            "updated": "" if pd.isna(updated_timestamp) else updated_timestamp.date().isoformat(),
            "abs_url": normalize_whitespace(record.abs_url),
            "pdf_url": normalize_whitespace(record.pdf_url),
            "comment": normalize_whitespace(record.comment),
            "authors_joined": compact_join(authors),
            "categories_joined": compact_join(categories),
            "summary_chars": len(summary),
            "age_days": max(0, int((run_timestamp - published_timestamp.normalize()).days)),
        }
        row["text_for_embedding"] = build_embedding_text(row)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=_CLEAN_COLUMNS)
    clean = pd.DataFrame(rows, columns=_CLEAN_COLUMNS)
    clean = clean.drop_duplicates(subset="paper_id", keep="first")
    clean = clean.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    return clean
