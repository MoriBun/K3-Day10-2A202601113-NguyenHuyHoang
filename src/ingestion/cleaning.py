from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd

from core.config import Settings
from ingestion.crossref import PaperRecord

_WHITESPACE_RE = re.compile(r"\s+")

# So ky tu toi thieu de mot summary duoc coi la hop le (khong phai rac).
# Phai bang nguong cua quality check `summary_min_length` (CONTRACT.md muc 7.1),
# neu khong baseline se fail quality check ngay tren du lieu sach.
_MIN_SUMMARY_CHARS = 100

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
    # Khong dung `default=str`: no bien numpy int64 thanh chuoi ("15" thay vi 15)
    # va lam age_days/summary_chars trong JSON lech kieu so voi CSV.
    records = [{key: _jsonable(value) for key, value in row.items()} for row in df.to_dict(orient="records")]
    json_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
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
    raw_count = len(df)

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
    # CP1 yeu cau: moi lan loai/dedupe deu phai de lai so dem, khong duoc lam mat
    # record am tham (CONTRACT.md muc 3.3).
    before_dedupe = len(df)
    df = df.drop_duplicates(subset="paper_id", keep="first")

    has_paper_id = df["paper_id"].astype(str).str.strip().ne("")
    has_title = df["title"].astype(str).str.strip().ne("")
    long_enough = df["summary_chars"] >= _MIN_SUMMARY_CHARS
    has_published = published_dt.notna().reindex(df.index)

    # Cac con so duoi day co the chong lan nhau (mot row hong nhieu tieu chi).
    stats = {
        "raw_count": int(raw_count),
        "dropped_duplicate": int(before_dedupe - len(df)),
        "dropped_no_paper_id": int((~has_paper_id).sum()),
        "dropped_no_title": int((~has_title).sum()),
        "dropped_short_summary": int((~long_enough).sum()),
        "dropped_bad_published": int((~has_published).sum()),
    }

    df = df[has_paper_id & has_title & long_enough & has_published].copy()
    stats["clean_count"] = int(len(df))

    # age_days phai la int (CONTRACT.md muc 3). Truoc buoc filter cot nay co the
    # la float vi cac row co published = NaT, nen chi ep kieu sau khi da loc.
    df["age_days"] = df["age_days"].astype("int64")

    # 6. Sort dataframe (moi nhat truoc) va return -------------------------------
    df = df.sort_values(by="published", ascending=False, na_position="last")
    df = df.reset_index(drop=True)
    df.attrs["clean_stats"] = stats
    print(
        "[cleaning] raw={raw_count} -> clean={clean_count} "
        "(duplicate={dropped_duplicate}, no_title={dropped_no_title}, "
        "short_summary={dropped_short_summary}, bad_published={dropped_bad_published})".format(**stats)
    )

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


def build_text_for_embedding(
    title: str,
    summary: str,
    authors_joined: str,
    categories_joined: str,
    published: str,
) -> str:
    """Cong thuc chuan cua CONTRACT.md muc 4.1 -- NGUON DUY NHAT cho ca pipeline.

    Phai chua ca authors, categories va published vi test set co 4 loai cau hoi
    (summary / authors / date / categories). Neu chi embed title + summary thi cau
    hoi loai authors va date se retrieve sai document va lam metrics tut oan.

    `corruption.py` import lai chinh ham nay: neu hai noi tu viet cong thuc rieng,
    baseline va corrupted se khac nhau vi ly do khong phai do corruption.
    """
    return (
        f"{title}\n\n"
        f"{summary}\n\n"
        f"Authors: {authors_joined}\n"
        f"Categories: {categories_joined}\n"
        f"Published: {published}"
    )


def build_text_for_embedding_from_row(row) -> str:
    """Adapter goi `build_text_for_embedding` tu mot row cua dataframe."""
    return build_text_for_embedding(
        title=str(row.get("title") or ""),
        summary=str(row.get("summary") or ""),
        authors_joined=str(row.get("authors_joined") or ""),
        categories_joined=str(row.get("categories_joined") or ""),
        published=str(row.get("published") or ""),
    )


def _build_embedding_text(row: pd.Series) -> str:
    return build_text_for_embedding_from_row(row)


def _jsonable(value: object) -> object:
    """Doi numpy scalar / NaN ve kieu Python thuan de json.dumps khong can `default=str`."""
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT:
        return None
    return value