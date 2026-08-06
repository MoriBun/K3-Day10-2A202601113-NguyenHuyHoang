from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.config import Settings
from ingestion.crossref import PaperRecord

_WHITESPACE_RE = re.compile(r"\s+")

# So ky tu toi thieu de mot summary duoc coi la hop le (khong phai rac).
_MIN_SUMMARY_CHARS = 20

# Cac cot dang list (authors, categories) khong the ghi thang vao CSV,
# nen CSV se dung ban "_joined" (string), con JSON giu nguyen list goc.
_LIST_COLUMNS = ["authors", "categories"]


def save_clean_dataframe(df: pd.DataFrame, settings: Settings) -> None:
    """Ghi cleaned dataframe ra `settings.paths.clean_csv` va `settings.paths.clean_json`."""
    csv_path = settings.paths.clean_csv
    json_path = settings.paths.clean_json
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # CSV: khong the luu list truc tiep, nen drop cot list va dung ban "_joined".
    csv_df = df.drop(columns=[c for c in _LIST_COLUMNS if c in df.columns])
    csv_df.to_csv(csv_path, index=False)

    # JSON: giu nguyen cau truc list (authors, categories) cho de doc/xu ly lai.
    records = df.to_dict(orient="records")
    json_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def build_clean_dataframe(
    records: list[PaperRecord], run_date: datetime, settings: Settings | None = None
) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed.

    Pseudo-code (da trien khai):
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated date.
    3. Tinh age_days.
    4. Tao cot helper:
       - authors_joined
       - categories_joined
       - summary_chars
       - text_for_embedding
    5. Drop duplicates va filter row xau.
    6. Sort dataframe va return.
    """
    if not records:
        df = _empty_clean_dataframe()
        if settings is not None:
            save_clean_dataframe(df, settings)
        return df

    df = pd.DataFrame([asdict(r) for r in records])

    # 1. Normalize text fields ------------------------------------------------
    df["title"] = df["title"].map(_clean_text)
    df["summary"] = df["summary"].map(_clean_text)
    df["authors"] = df["authors"].map(_clean_str_list)
    df["categories"] = df["categories"].map(_clean_str_list)
    df["primary_category"] = df["primary_category"].map(_clean_text)
    df["comment"] = df["comment"].map(_clean_text)
    df["abs_url"] = df["abs_url"].map(_clean_text)
    df["pdf_url"] = df["pdf_url"].map(_clean_text)

    # 2. Parse published/updated date -----------------------------------------
    published_dt = pd.to_datetime(df["published"], errors="coerce", utc=True)
    updated_dt = pd.to_datetime(df["updated"], errors="coerce", utc=True)

    # Chuan hoa lai cot ve dang ISO date string ("YYYY-MM-DD") de de doc/luu CSV.
    df["published"] = published_dt.dt.strftime("%Y-%m-%d")
    df["updated"] = updated_dt.dt.strftime("%Y-%m-%d")

    # 3. Tinh age_days ------------------------------------------------------
    run_date_utc = _ensure_utc(run_date)
    age_delta = pd.Timestamp(run_date_utc) - published_dt
    df["age_days"] = age_delta.dt.days

    # 4. Cot helper -----------------------------------------------------------
    df["authors_joined"] = df["authors"].map(lambda a: "; ".join(a))
    df["categories_joined"] = df["categories"].map(lambda c: "; ".join(c))
    df["summary_chars"] = df["summary"].str.len()
    df["text_for_embedding"] = df.apply(_build_embedding_text, axis=1)

    # 5. Drop duplicates va filter row xau -------------------------------------
    df = df.drop_duplicates(subset="paper_id", keep="first")

    valid_mask = (
        df["paper_id"].astype(str).str.strip().ne("")
        & df["title"].astype(str).str.strip().ne("")
        & (df["summary_chars"] >= _MIN_SUMMARY_CHARS)
        & published_dt.notna().reindex(df.index)
    )
    df = df[valid_mask].copy()

    # 6. Sort dataframe (moi nhat truoc) va return -------------------------------
    df = df.sort_values(by="published", ascending=False, na_position="last")
    df = df.reset_index(drop=True)

    # 7. Luu cleaned data vao data/clean/ (neu co settings) -----------------------
    if settings is not None:
        save_clean_dataframe(df, settings)

    return df


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _empty_clean_dataframe() -> pd.DataFrame:
    columns = [
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
        "age_days",
        "authors_joined",
        "categories_joined",
        "summary_chars",
        "text_for_embedding",
    ]
    return pd.DataFrame(columns=columns)


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _clean_str_list(values: object) -> list[str]:
    if not values:
        return []
    cleaned = [_clean_text(v) for v in values]
    return [v for v in cleaned if v]


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _build_embedding_text(row: pd.Series) -> str:
    parts = [row["title"], row["summary"]]
    if row.get("categories_joined"):
        parts.append(f"Categories: {row['categories_joined']}")
    return _clean_text(" ".join(p for p in parts if p))