from __future__ import annotations

import pandas as pd

from core.utils import write_json
from ingestion.cleaning import build_embedding_text


def _pick_positions(length: int, count: int, offset: int = 0) -> list[int]:
    if length == 0:
        return []
    return [((offset + index * max(1, length // count)) % length) for index in range(count)]


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Return a reproducibly degraded copy of the cleaned corpus and an audit log."""
    required = {"paper_id", "title", "summary", "published", "authors_joined", "categories_joined"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Cannot corrupt dataframe missing columns: {sorted(missing)}")
    if len(df) < 5:
        raise ValueError("At least five clean records are required to simulate corruption.")

    working = df.copy().sort_values("published", ascending=False, kind="stable").reset_index(drop=True)
    log: dict[str, object] = {"input_rows": len(working), "operations": {}}

    drop_count = min(max(1, len(working) // 5), len(working) - 4)
    dropped_ids = working.loc[: drop_count - 1, "paper_id"].tolist()
    working = working.iloc[drop_count:].reset_index(drop=True)
    log["operations"]["dropped_latest_records"] = dropped_ids  # type: ignore[index]

    affected_count = min(max(1, len(working) // 6), 3)
    blank_positions = _pick_positions(len(working), affected_count)
    blanked_ids = working.loc[blank_positions, "paper_id"].tolist()
    working.loc[blank_positions, "summary"] = ""
    log["operations"]["blank_summaries"] = blanked_ids  # type: ignore[index]

    noise_positions = _pick_positions(len(working), affected_count, offset=1)
    noise_ids = working.loc[noise_positions, "paper_id"].tolist()
    noise = " [CORRUPTED_TEXT: xqzv 123 ### repeated irrelevant tokens]"
    working.loc[noise_positions, "summary"] = working.loc[noise_positions, "summary"].astype(str) + noise
    log["operations"]["noisy_summaries"] = noise_ids  # type: ignore[index]

    truncate_positions = _pick_positions(len(working), min(2, affected_count), offset=2)
    truncated_ids = working.loc[truncate_positions, "paper_id"].tolist()
    working.loc[truncate_positions, "title"] = working.loc[truncate_positions, "title"].map(
        lambda value: str(value)[: max(8, len(str(value)) // 3)] + "..."
    )
    log["operations"]["truncated_titles"] = truncated_ids  # type: ignore[index]

    stale_positions = _pick_positions(len(working), min(2, affected_count), offset=3)
    stale_ids = working.loc[stale_positions, "paper_id"].tolist()
    stale_date = (pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=730)).date().isoformat()
    working.loc[stale_positions, "published"] = stale_date
    working.loc[stale_positions, "age_days"] = 730
    log["operations"]["stale_publication_dates"] = stale_ids  # type: ignore[index]

    duplicate_count = min(2, len(working))
    duplicate_rows = working.iloc[-duplicate_count:].copy()
    duplicate_ids = duplicate_rows["paper_id"].tolist()
    working = pd.concat([working, duplicate_rows], ignore_index=True)
    log["operations"]["duplicated_records"] = duplicate_ids  # type: ignore[index]

    working["summary"] = working["summary"].fillna("").astype(str)
    working["summary_chars"] = working["summary"].str.len()
    working["text_for_embedding"] = working.apply(lambda row: build_embedding_text(row.to_dict()), axis=1)
    working = working.reset_index(drop=True)
    log["output_rows"] = len(working)
    write_json(output_log_path, log)
    return working
