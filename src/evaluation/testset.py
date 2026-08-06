"""Xay dung evaluation set tu cleaned dataframe.

Bon template phai giu nguyen vi `retrieval.qa` match chuoi cung va dung title
trong nhay don de exact lookup. Test set duoc khoa lai sau baseline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.utils import first_sentence, write_json

_MIN_DOCUMENTS = 5
_MAX_SAMPLE_PAPERS = 15


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set co 4 loai cau hoi tren cac paper dai dien."""
    if len(df) < _MIN_DOCUMENTS:
        raise ValueError(
            f"Khong du document de tao test set: co {len(df)}, can it nhat {_MIN_DOCUMENTS}."
        )

    sample_df = _select_representative_papers(df, n=_MAX_SAMPLE_PAPERS)
    test_set: list[dict[str, Any]] = []
    for _, row in sample_df.iterrows():
        test_set.extend(_build_questions_for_row(row))

    for index, item in enumerate(test_set, start=1):
        item["id"] = f"q{index:04d}"

    write_json(output_path, test_set)
    by_type: dict[str, int] = {}
    for item in test_set:
        by_type[item["question_type"]] = by_type.get(item["question_type"], 0) + 1
    print(
        f"  {len(test_set)} cau hoi tu {len(sample_df)} paper "
        f"({', '.join(f'{key}={value}' for key, value in sorted(by_type.items()))})"
    )
    return test_set


def _select_representative_papers(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """Chon toi da `n` paper trai deu theo ngay xuat ban."""
    n = min(n, len(df))
    if "published" in df.columns:
        sorted_df = df.copy()
        sorted_df["_published_dt"] = pd.to_datetime(sorted_df["published"], errors="coerce", utc=True)
        sorted_df = sorted_df.sort_values("_published_dt", na_position="last").reset_index(drop=True)
        positions = sorted(set(np.linspace(0, len(sorted_df) - 1, num=n, dtype=int).tolist()))
        return sorted_df.iloc[positions].drop(columns=["_published_dt"]).reset_index(drop=True)
    return df.sample(n=n, random_state=seed).reset_index(drop=True)


def _build_questions_for_row(row: pd.Series) -> list[dict[str, Any]]:
    paper_id = _clean(row.get("paper_id"))
    title = _clean(row.get("title"))
    if not paper_id or not title:
        return []

    summary = _clean(row.get("summary"))
    specs = [
        ("summary", f"What is the paper '{title}' about?", first_sentence(summary) if summary else ""),
        ("authors", f"Who authored the paper '{title}'?", _clean(row.get("authors_joined"))),
        ("date", f"When was the paper '{title}' published?", _clean(row.get("published"))),
        (
            "categories",
            f"What categories does the paper '{title}' belong to?",
            _clean(row.get("categories_joined")),
        ),
    ]
    return [
        {
            "id": None,
            "question_type": question_type,
            "question": question,
            "ground_truth": ground_truth,
            "ground_truth_doc_ids": [paper_id],
        }
        for question_type, question, ground_truth in specs
        if ground_truth
    ]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text
