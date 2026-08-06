from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import safe_slug, write_json


MINIMUM_ROW_COUNT = 20
MINIMUM_SUMMARY_CHARS = 100


def _check(passed: bool, observed: Any, expectation: str) -> dict[str, Any]:
    return {"passed": bool(passed), "observed": observed, "expectation": expectation}


def _non_blank_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].fillna("").astype(str).str.strip().ne("").sum())


def _duplicate_row_count(df: pd.DataFrame) -> int:
    """Count duplicate whole rows, including rows with list or dict values."""
    if df.empty:
        return 0

    def serialise(value: Any) -> str:
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        if pd.isna(value):
            return "<missing>"
        return str(value)

    comparable = df.apply(lambda column: column.map(serialise))
    return int(comparable.duplicated(keep=False).sum())


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run transparent, artifact-backed quality checks over a cleaned dataframe."""
    row_count = len(df)
    paper_id_present = _non_blank_count(df, "paper_id")
    title_present = _non_blank_count(df, "title")
    summary_chars = pd.to_numeric(df.get("summary_chars", pd.Series(index=df.index, dtype="float64")), errors="coerce")
    valid_summaries = int((summary_chars >= MINIMUM_SUMMARY_CHARS).sum())
    duplicate_ids = 0
    if "paper_id" in df.columns:
        normalised_ids = df["paper_id"].fillna("").astype(str).str.strip().str.lower()
        duplicate_ids = int(normalised_ids[normalised_ids.ne("")].duplicated(keep=False).sum())
    duplicate_rows = _duplicate_row_count(df)
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype="float64")), errors="coerce")
    stale_rows = int((age_days > settings.freshness_threshold_days).sum())
    invalid_age_rows = int((age_days.isna() | age_days.lt(0)).sum())

    checks = {
        "row_count_min": _check(row_count >= MINIMUM_ROW_COUNT, row_count, f"at least {MINIMUM_ROW_COUNT} rows"),
        "paper_id_not_null": _check(paper_id_present == row_count, paper_id_present, "every row has a paper_id"),
        "paper_id_unique": _check(duplicate_ids == 0, duplicate_ids, "zero rows with a duplicate paper_id"),
        "title_not_null": _check(title_present == row_count, title_present, "every row has a title"),
        "summary_min_length": _check(
            valid_summaries == row_count,
            {"valid_rows": valid_summaries, "minimum_chars": MINIMUM_SUMMARY_CHARS},
            f"every summary contains at least {MINIMUM_SUMMARY_CHARS} characters",
        ),
        "no_duplicate_rows": _check(
            duplicate_rows == 0,
            duplicate_rows,
            "zero rows duplicated across every column",
        ),
        "freshness_age": _check(
            stale_rows == 0 and invalid_age_rows == 0,
            {
                "stale_rows": stale_rows,
                "invalid_age_rows": invalid_age_rows,
                "threshold_days": settings.freshness_threshold_days,
            },
            "every age_days value is between zero and the freshness threshold",
        ),
    }
    report = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "row_count": row_count,
        "passed": all(check["passed"] for check in checks.values()),
        "checks": checks,
    }
    write_json(settings.paths.quality_dir / f"{safe_slug(report_name)}.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarise dataset freshness using the same threshold as quality checks."""
    published = pd.to_datetime(df.get("published", pd.Series(dtype="object")), errors="coerce", utc=True)
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype="float64")), errors="coerce")
    total_rows = len(df)
    valid_dates = published.dropna()
    stale_rows = int((age_days > settings.freshness_threshold_days).sum())
    invalid_age_rows = int((age_days.isna() | age_days.lt(0)).sum())
    undated_rows = int(published.isna().sum())
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold_days": settings.freshness_threshold_days,
        "latest_published": valid_dates.max().date().isoformat() if not valid_dates.empty else None,
        "oldest_published": valid_dates.min().date().isoformat() if not valid_dates.empty else None,
        "stale_rows": stale_rows,
        "invalid_age_rows": invalid_age_rows,
        "undated_rows": undated_rows,
        "total_rows": total_rows,
        "is_fresh": total_rows > 0 and stale_rows == 0 and invalid_age_rows == 0 and undated_rows == 0,
    }
    write_json(Path(report_path), report)
    return report
