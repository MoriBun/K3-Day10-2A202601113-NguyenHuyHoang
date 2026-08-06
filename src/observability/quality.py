"""Data quality checks va freshness monitoring cho ba trang thai pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json

_MIN_ROW_COUNT = 20
_MIN_SUMMARY_CHARS = 100
_MAX_SAMPLE_IDS = 5


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chay 7 check contract va ghi artifact rieng cho tung trang thai."""
    total_rows = int(len(df))
    checks = [
        _check_row_count(total_rows),
        _check_not_null(df, "paper_id", "paper_id_not_null"),
        _check_paper_id_unique(df),
        _check_not_null(df, "title", "title_not_null"),
        _check_summary_length(df),
        _check_no_duplicate_rows(df),
        _check_freshness(df, settings),
    ]
    checks_passed = sum(check["success"] for check in checks)
    payload: dict[str, Any] = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": total_rows,
        "checks_total": len(checks),
        "checks_passed": checks_passed,
        "checks_failed": len(checks) - checks_passed,
        "success": checks_passed == len(checks),
        "checks": checks,
    }
    output_path = settings.paths.quality_dir / f"quality_{report_name}.json"
    write_json(output_path, payload)
    print(f"  [{'PASS' if payload['success'] else 'FAIL'}] {checks_passed}/{len(checks)} check -> {output_path.name}")
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness tu artifact columns, khong lay system time lam su that."""
    threshold = settings.freshness_threshold_days
    total_rows = int(len(df))
    published = pd.to_datetime(df.get("published", pd.Series(dtype="object")), errors="coerce", utc=True)
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype="float64")), errors="coerce")
    invalid_age = age_days.isna() | age_days.lt(0)
    stale_mask = age_days.gt(threshold)
    undated = published.isna()
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold_days": threshold,
        "total_rows": total_rows,
        "stale_rows": int(stale_mask.sum()),
        "invalid_age_rows": int(invalid_age.sum()),
        "undated_rows": int(undated.sum()),
        "fresh_rows": total_rows - int(stale_mask.sum()) - int(invalid_age.sum()),
        "is_fresh": bool(total_rows > 0 and not stale_mask.any() and not invalid_age.any() and not undated.any()),
        "latest_published": _as_date_string(published.max()),
        "oldest_published": _as_date_string(published.min()),
        "min_age_days": _as_int(age_days.min()),
        "max_age_days": _as_int(age_days.max()),
        "mean_age_days": _as_int(age_days.mean()),
        "stale_paper_ids": _sample_ids(df, stale_mask | invalid_age | undated),
    }
    write_json(report_path, payload)
    print(f"  [{'FRESH' if payload['is_fresh'] else 'STALE'}] {payload['stale_rows']}/{total_rows} stale rows")
    return payload


def _result(name: str, success: bool, expected: str, observed: Any, failed_rows: int = 0, sample_ids: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "success": bool(success), "expected": expected, "observed": observed, "failed_rows": int(failed_rows), "sample_failed_paper_ids": sample_ids or []}


def _check_row_count(total_rows: int) -> dict[str, Any]:
    return _result("row_count_min", total_rows >= _MIN_ROW_COUNT, f">= {_MIN_ROW_COUNT} rows", f"{total_rows} rows", max(0, _MIN_ROW_COUNT - total_rows))


def _check_not_null(df: pd.DataFrame, column: str, name: str) -> dict[str, Any]:
    if column not in df.columns:
        return _result(name, False, f"column `{column}` exists", "missing column")
    bad_mask = df[column].isna() | df[column].astype(str).str.strip().eq("")
    return _result(name, not bad_mask.any(), f"`{column}` is not blank", f"{int(bad_mask.sum())} blank rows", int(bad_mask.sum()), _sample_ids(df, bad_mask))


def _check_paper_id_unique(df: pd.DataFrame) -> dict[str, Any]:
    if "paper_id" not in df.columns:
        return _result("paper_id_unique", False, "column `paper_id` exists", "missing column")
    normalized = df["paper_id"].fillna("").astype(str).str.strip().str.lower()
    duplicate_mask = normalized.ne("") & normalized.duplicated(keep=False)
    return _result("paper_id_unique", not duplicate_mask.any(), "each paper_id occurs once", f"{int(duplicate_mask.sum())} duplicate rows", int(duplicate_mask.sum()), _sample_ids(df, duplicate_mask))


def _check_summary_length(df: pd.DataFrame) -> dict[str, Any]:
    lengths = pd.to_numeric(df["summary_chars"], errors="coerce").fillna(0) if "summary_chars" in df.columns else df.get("summary", pd.Series(index=df.index, dtype="object")).fillna("").astype(str).str.len()
    bad_mask = lengths.lt(_MIN_SUMMARY_CHARS)
    return _result("summary_min_length", not bad_mask.any(), f"summary >= {_MIN_SUMMARY_CHARS} chars", f"{int(bad_mask.sum())} short rows", int(bad_mask.sum()), _sample_ids(df, bad_mask))


def _check_no_duplicate_rows(df: pd.DataFrame) -> dict[str, Any]:
    comparable = df.copy()
    for column in comparable.columns:
        comparable[column] = comparable[column].map(lambda value: str(value) if not isinstance(value, (list, dict)) else repr(value))
    duplicate_mask = comparable.duplicated(keep=False)
    return _result("no_duplicate_rows", not duplicate_mask.any(), "no duplicate complete rows", f"{int(duplicate_mask.sum())} duplicate rows", int(duplicate_mask.sum()), _sample_ids(df, duplicate_mask))


def _check_freshness(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    if "age_days" not in df.columns:
        return _result("freshness_age", False, "column `age_days` exists", "missing column")
    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    bad_mask = age_days.isna() | age_days.lt(0) | age_days.gt(settings.freshness_threshold_days)
    return _result("freshness_age", not bad_mask.any(), f"0 <= age_days <= {settings.freshness_threshold_days}", f"{int(bad_mask.sum())} invalid or stale rows", int(bad_mask.sum()), _sample_ids(df, bad_mask))


def _sample_ids(df: pd.DataFrame, mask) -> list[str]:
    if "paper_id" not in df.columns:
        return []
    return [str(value) for value in df.loc[mask.fillna(False), "paper_id"].head(_MAX_SAMPLE_IDS).tolist()]


def _as_date_string(value) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date().isoformat()


def _as_int(value) -> int | None:
    return None if value is None or pd.isna(value) else int(round(float(value)))
