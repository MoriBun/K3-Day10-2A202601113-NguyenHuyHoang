"""Data quality checks va freshness monitoring.

Ket qua cua ba trang thai baseline / corrupted / repaired duoc tach file bang
tham so `report_name`, de khong trang thai nao ghi de trang thai nao
(CONTRACT.md muc 0, quy tac 3).

Moi nguong deu doc tu `Settings`, khong hard-code -- neu hard-code thi khi doi
`freshness_threshold_days` trong config, quality check se noi doi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json

# So dong toi thieu de corpus duoc coi la du de danh gia.
_MIN_ROW_COUNT = 20

# Do dai summary toi thieu. Phai bang `_MIN_SUMMARY_CHARS` trong cleaning.py,
# neu khong baseline se fail quality check ngay tren du lieu sach.
_MIN_SUMMARY_CHARS = 100

# So paper_id vi du duoc kem theo moi check that bai, de con truy vet.
_MAX_SAMPLE_IDS = 5


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chay 7 data quality check va ghi ket qua vao `data/quality/`.

    Tra ve payload da ghi, de pipeline dua thang vao report markdown.
    """
    total_rows = int(len(df))
    checks: list[dict[str, Any]] = [
        _check_row_count(df, total_rows),
        _check_not_null(df, "paper_id", "paper_id_not_null"),
        _check_paper_id_unique(df),
        _check_not_null(df, "title", "title_not_null"),
        _check_summary_length(df),
        _check_no_duplicate_rows(df),
        _check_freshness(df, settings),
    ]

    passed = sum(1 for check in checks if check["success"])
    payload: dict[str, Any] = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": total_rows,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": len(checks) - passed,
        "success": passed == len(checks),
        "checks": checks,
    }

    output_path = settings.paths.quality_dir / f"quality_{report_name}.json"
    write_json(output_path, payload)

    status = "PASS" if payload["success"] else "FAIL"
    print(f"  [{status}] {passed}/{len(checks)} check -> {output_path.name}")
    for check in checks:
        if not check["success"]:
            print(f"    - {check['name']}: {check['observed']} (can: {check['expected']})")

    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness tu cot `published` / `age_days` cua chinh du lieu.

    Khong lay `datetime.now()` lam nguon su that: neu lay gio he thong thi
    baseline va repaired chay o hai thoi diem khac nhau se ra ket qua khac nhau.
    """
    threshold = settings.freshness_threshold_days
    total_rows = int(len(df))

    published = pd.to_datetime(df.get("published"), errors="coerce", utc=True)
    age_days = pd.to_numeric(df.get("age_days"), errors="coerce")

    stale_mask = age_days > threshold
    stale_rows = int(stale_mask.sum())

    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold_days": threshold,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "fresh_rows": total_rows - stale_rows,
        "is_fresh": bool(stale_rows == 0 and total_rows > 0),
        "latest_published": _as_date_string(published.max()),
        "oldest_published": _as_date_string(published.min()),
        "min_age_days": _as_int(age_days.min()),
        "max_age_days": _as_int(age_days.max()),
        "mean_age_days": _as_int(age_days.mean()),
        "stale_paper_ids": _sample_ids(df, stale_mask),
    }

    write_json(report_path, payload)

    status = "FRESH" if payload["is_fresh"] else "STALE"
    print(
        f"  [{status}] {stale_rows}/{total_rows} dong qua han {threshold} ngay | "
        f"moi nhat {payload['latest_published']} | cu nhat {payload['oldest_published']}"
    )
    return payload


# --------------------------------------------------------------------------
# Cac check rieng le
# --------------------------------------------------------------------------


def _result(
    name: str,
    success: bool,
    expected: str,
    observed: Any,
    failed_rows: int = 0,
    sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "success": bool(success),
        "expected": expected,
        "observed": observed,
        "failed_rows": int(failed_rows),
        "sample_failed_paper_ids": sample_ids or [],
    }


def _check_row_count(df: pd.DataFrame, total_rows: int) -> dict[str, Any]:
    return _result(
        "row_count_min",
        total_rows >= _MIN_ROW_COUNT,
        f">= {_MIN_ROW_COUNT} dong",
        f"{total_rows} dong",
        failed_rows=max(0, _MIN_ROW_COUNT - total_rows),
    )


def _check_not_null(df: pd.DataFrame, column: str, name: str) -> dict[str, Any]:
    if column not in df.columns:
        return _result(name, False, f"co cot `{column}`", "thieu cot")

    series = df[column]
    bad_mask = series.isna() | series.astype(str).str.strip().eq("")
    bad = int(bad_mask.sum())
    return _result(
        name,
        bad == 0,
        f"`{column}` khong null/rong",
        f"{bad} dong null hoac rong",
        failed_rows=bad,
        sample_ids=_sample_ids(df, bad_mask),
    )


def _check_paper_id_unique(df: pd.DataFrame) -> dict[str, Any]:
    if "paper_id" not in df.columns:
        return _result("paper_id_unique", False, "co cot `paper_id`", "thieu cot")

    duplicated_mask = df["paper_id"].duplicated(keep=False)
    duplicated = int(df["paper_id"].duplicated().sum())
    return _result(
        "paper_id_unique",
        duplicated == 0,
        "moi `paper_id` chi xuat hien 1 lan",
        f"{duplicated} dong trung",
        failed_rows=duplicated,
        sample_ids=_sample_ids(df, duplicated_mask),
    )


def _check_summary_length(df: pd.DataFrame) -> dict[str, Any]:
    if "summary_chars" in df.columns:
        lengths = pd.to_numeric(df["summary_chars"], errors="coerce").fillna(0)
    elif "summary" in df.columns:
        lengths = df["summary"].fillna("").astype(str).str.len()
    else:
        return _result("summary_min_length", False, "co cot `summary`", "thieu cot")

    bad_mask = lengths < _MIN_SUMMARY_CHARS
    bad = int(bad_mask.sum())
    return _result(
        "summary_min_length",
        bad == 0,
        f"summary >= {_MIN_SUMMARY_CHARS} ky tu",
        f"{bad} dong ngan hon nguong (min={int(lengths.min()) if len(lengths) else 0})",
        failed_rows=bad,
        sample_ids=_sample_ids(df, bad_mask),
    )


def _check_no_duplicate_rows(df: pd.DataFrame) -> dict[str, Any]:
    # Bo cot kieu list truoc khi so sanh: list khong hashable nen `duplicated()` se raise.
    comparable = df.drop(columns=[c for c in ("authors", "categories") if c in df.columns])
    duplicated_mask = comparable.duplicated(keep=False)
    duplicated = int(comparable.duplicated().sum())
    return _result(
        "no_duplicate_rows",
        duplicated == 0,
        "khong co dong trung hoan toan",
        f"{duplicated} dong trung",
        failed_rows=duplicated,
        sample_ids=_sample_ids(df, duplicated_mask),
    )


def _check_freshness(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    threshold = settings.freshness_threshold_days
    if "age_days" not in df.columns:
        return _result("freshness_age", False, "co cot `age_days`", "thieu cot")

    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    bad_mask = age_days > threshold
    bad = int(bad_mask.sum())
    return _result(
        "freshness_age",
        bad == 0,
        f"age_days <= {threshold}",
        f"{bad} dong qua han (max={_as_int(age_days.max())})",
        failed_rows=bad,
        sample_ids=_sample_ids(df, bad_mask),
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _sample_ids(df: pd.DataFrame, mask) -> list[str]:
    if "paper_id" not in df.columns or mask is None:
        return []
    try:
        selected = df.loc[mask.fillna(False), "paper_id"]
    except Exception:
        return []
    return [str(value) for value in selected.head(_MAX_SAMPLE_IDS).tolist()]


def _as_date_string(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _as_int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(round(float(value)))
