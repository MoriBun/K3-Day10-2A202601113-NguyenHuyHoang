from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ingestion.cleaning import build_text_for_embedding_from_row

# Ty le (fraction) so dong bi anh huong boi tung loai corruption.
# Chinh lai cac hang so nay neu ban muon corruption manh/nhe hon.
_DROP_LATEST_FRACTION = 0.05
_BLANK_SUMMARY_FRACTION = 0.10
_NOISE_FRACTION = 0.10
_TRUNCATE_TITLE_FRACTION = 0.10
_STALE_DATE_FRACTION = 0.10
_DUPLICATE_FRACTION = 0.05

_STALE_EXTRA_DAYS_RANGE = (60, 400)  # so ngay "day lui" published date
_NOISE_TOKENS = ["####", "@@@@", "!!ERR!!", "<corrupt>", "xx??xx"]


def corrupt_clean_dataframe(
    df: pd.DataFrame, output_log_path, seed: int = 42
) -> pd.DataFrame:
    """Simulate nhieu dang data corruption tren cleaned dataframe.

    Pseudo-code (da trien khai):
    1. Drop mot so latest records.
    2. Blank summary o mot so dong.
    3. Inject noise vao text.
    4. Lam title bi truncate.
    5. Lam published date cu di.
    6. Add duplicate rows.
    7. Rebuild `text_for_embedding`.
    8. Ghi corruption log vao output_log_path.
    """
    rng = np.random.default_rng(seed)
    log: dict[str, Any] = {
        "seed": seed,
        "generated_at": datetime.now(UTC).isoformat(),
        "rows_before": int(len(df)),
        "actions": [],
    }

    if df.empty:
        log["rows_after"] = 0
        _write_log(output_log_path, log)
        return df.copy()

    corrupted = df.copy().reset_index(drop=True)

    corrupted, drop_action = _drop_latest_records(corrupted, rng)
    log["actions"].append(drop_action)

    corrupted, blank_action = _blank_summaries(corrupted, rng)
    log["actions"].append(blank_action)

    corrupted, noise_action = _inject_text_noise(corrupted, rng)
    log["actions"].append(noise_action)

    corrupted, truncate_action = _truncate_titles(corrupted, rng)
    log["actions"].append(truncate_action)

    corrupted, stale_action = _make_dates_stale(corrupted, rng)
    log["actions"].append(stale_action)

    corrupted, dup_action = _add_duplicate_rows(corrupted, rng)
    log["actions"].append(dup_action)

    # 7. Rebuild text_for_embedding vi title/summary da thay doi ---------------
    corrupted["text_for_embedding"] = corrupted.apply(_rebuild_embedding_text, axis=1)
    corrupted["summary_chars"] = corrupted["summary"].fillna("").astype(str).str.len()

    corrupted = corrupted.reset_index(drop=True)
    log["rows_after"] = int(len(corrupted))

    # 8. Ghi corruption log -----------------------------------------------------
    _write_log(output_log_path, log)

    return corrupted


# --------------------------------------------------------------------------
# Individual corruption steps
# --------------------------------------------------------------------------


def _drop_latest_records(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n_drop = max(1, int(len(df) * _DROP_LATEST_FRACTION)) if len(df) > 1 else 0
    if n_drop == 0:
        return df, {"step": "drop_latest_records", "dropped_paper_ids": [], "count": 0}

    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    latest_idx = published.sort_values(ascending=False, na_position="last").index[:n_drop]
    dropped_ids = df.loc[latest_idx, "paper_id"].tolist()

    remaining = df.drop(index=latest_idx).reset_index(drop=True)
    action = {
        "step": "drop_latest_records",
        "dropped_paper_ids": dropped_ids,
        "count": len(dropped_ids),
    }
    return remaining, action


def _blank_summaries(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n = _affected_count(len(df), _BLANK_SUMMARY_FRACTION)
    if n == 0:
        return df, {"step": "blank_summaries", "affected_paper_ids": [], "count": 0}

    idx = rng.choice(df.index, size=n, replace=False)
    affected_ids = df.loc[idx, "paper_id"].tolist()
    df.loc[idx, "summary"] = ""

    action = {
        "step": "blank_summaries",
        "affected_paper_ids": affected_ids,
        "count": len(affected_ids),
    }
    return df, action


def _inject_text_noise(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n = _affected_count(len(df), _NOISE_FRACTION)
    if n == 0:
        return df, {"step": "inject_text_noise", "affected_paper_ids": [], "count": 0}

    idx = rng.choice(df.index, size=n, replace=False)
    affected_ids = []
    for i in idx:
        text = str(df.at[i, "summary"] or "")
        token = _NOISE_TOKENS[rng.integers(0, len(_NOISE_TOKENS))]
        if text:
            words = text.split()
            pos = int(rng.integers(0, len(words) + 1))
            words.insert(pos, token)
            df.at[i, "summary"] = " ".join(words)
        else:
            df.at[i, "summary"] = token
        affected_ids.append(df.at[i, "paper_id"])

    action = {
        "step": "inject_text_noise",
        "affected_paper_ids": affected_ids,
        "count": len(affected_ids),
    }
    return df, action


def _truncate_titles(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n = _affected_count(len(df), _TRUNCATE_TITLE_FRACTION)
    if n == 0:
        return df, {"step": "truncate_titles", "affected_paper_ids": [], "count": 0}

    idx = rng.choice(df.index, size=n, replace=False)
    affected_ids = []
    for i in idx:
        title = str(df.at[i, "title"] or "")
        if len(title) <= 3:
            continue
        cut_at = int(rng.integers(1, max(2, len(title) - 1)))
        df.at[i, "title"] = title[:cut_at].rstrip()
        affected_ids.append(df.at[i, "paper_id"])

    action = {
        "step": "truncate_titles",
        "affected_paper_ids": affected_ids,
        "count": len(affected_ids),
    }
    return df, action


def _make_dates_stale(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n = _affected_count(len(df), _STALE_DATE_FRACTION)
    if n == 0:
        return df, {"step": "make_dates_stale", "affected_paper_ids": [], "count": 0}

    idx = rng.choice(df.index, size=n, replace=False)
    affected_ids = []
    for i in idx:
        published = pd.to_datetime(df.at[i, "published"], errors="coerce", utc=True)
        if pd.isna(published):
            continue
        extra_days = int(rng.integers(*_STALE_EXTRA_DAYS_RANGE))
        new_published = published - pd.Timedelta(days=extra_days)
        df.at[i, "published"] = new_published.strftime("%Y-%m-%d")
        if "age_days" in df.columns and pd.notna(df.at[i, "age_days"]):
            df.at[i, "age_days"] = float(df.at[i, "age_days"]) + extra_days
        affected_ids.append(df.at[i, "paper_id"])

    action = {
        "step": "make_dates_stale",
        "affected_paper_ids": affected_ids,
        "count": len(affected_ids),
    }
    return df, action


def _add_duplicate_rows(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    n = _affected_count(len(df), _DUPLICATE_FRACTION)
    if n == 0:
        return df, {"step": "add_duplicate_rows", "duplicated_paper_ids": [], "count": 0}

    idx = rng.choice(df.index, size=n, replace=False)
    dup_rows = df.loc[idx].copy()
    duplicated_ids = dup_rows["paper_id"].tolist()

    combined = pd.concat([df, dup_rows], ignore_index=True)
    action = {
        "step": "add_duplicate_rows",
        "duplicated_paper_ids": duplicated_ids,
        "count": len(duplicated_ids),
    }
    return combined, action


# --------------------------------------------------------------------------
# Misc helpers
# --------------------------------------------------------------------------


def _affected_count(total: int, fraction: float) -> int:
    """So dong bi tac dong. `int(total * fraction)` tra ve 0 voi corpus nho
    (vi du fixture 6 dong x 0.10 = 0) khien corruption thanh no-op va khong do
    duoc impact. Bao dam toi thieu 1 dong khi corpus co tu 2 dong tro len."""
    if total <= 1:
        return 0
    return max(1, int(total * fraction))


def _rebuild_embedding_text(row: pd.Series) -> str:
    # Dung dung cong thuc cua cleaning.py -- xem CONTRACT.md muc 4.1.
    return build_text_for_embedding_from_row(row)


def _write_log(output_log_path, log: dict[str, Any]) -> None:
    path = Path(output_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")