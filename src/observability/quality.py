from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import safe_slug, write_json


def _check(passed: bool, observed: Any, expectation: str) -> dict[str, Any]:
    return {"passed": bool(passed), "observed": observed, "expectation": expectation}


def _non_blank_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].fillna("").astype(str).str.strip().ne("").sum())


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run transparent, artifact-backed quality checks over a cleaned dataframe."""
    row_count = len(df)
    paper_id_present = _non_blank_count(df, "paper_id")
    title_present = _non_blank_count(df, "title")
    summary_lengths = (
        df["summary"].fillna("").astype(str).str.len()
        if "summary" in df.columns
        else pd.Series(dtype="int64")
    )
    valid_summaries = int((summary_lengths >= 40).sum())
    duplicate_ids = 0
    if "paper_id" in df.columns:
        normalised_ids = df["paper_id"].fillna("").astype(str).str.strip().str.lower()
        duplicate_ids = int(normalised_ids[normalised_ids.ne("")].duplicated(keep=False).sum())
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype="float64")), errors="coerce")
    stale_rows = int((age_days > settings.freshness_threshold_days).sum())
    missing_age_rows = int(age_days.isna().sum())

    checks = {
        "row_count": _check(row_count > 0, row_count, "at least one row"),
        "paper_id_not_null": _check(paper_id_present == row_count, paper_id_present, "every row has a paper_id"),
        "paper_id_unique": _check(duplicate_ids == 0, duplicate_ids, "zero rows with a duplicate paper_id"),
        "title_not_null": _check(title_present == row_count, title_present, "every row has a title"),
        "summary_minimum_length": _check(
            valid_summaries == row_count,
            {"valid_rows": valid_summaries, "minimum_chars": 40},
            "every summary contains at least 40 characters",
        ),
        "freshness": _check(
            stale_rows == 0 and missing_age_rows == 0,
            {
                "stale_rows": stale_rows,
                "missing_age_rows": missing_age_rows,
                "threshold_days": settings.freshness_threshold_days,
            },
            "no stale or undated rows",
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
    undated_rows = int(published.isna().sum())
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold_days": settings.freshness_threshold_days,
        "latest_published": valid_dates.max().date().isoformat() if not valid_dates.empty else None,
        "oldest_published": valid_dates.min().date().isoformat() if not valid_dates.empty else None,
        "stale_rows": stale_rows,
        "undated_rows": undated_rows,
        "total_rows": total_rows,
        "is_fresh": total_rows > 0 and stale_rows == 0 and undated_rows == 0,
    }
    write_json(Path(report_path), report)
    return report
