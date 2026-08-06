"""Xay dung evaluation set tu cleaned dataframe.

QUAN TRONG -- doc truoc khi sua file nay (CONTRACT.md muc 6.2):

`retrieval/qa.py` KHONG dung LLM. `_extract_answer` match CHUOI CUNG de quyet
dinh tra ve field nao, va `answer_question` dung regex `'([^']+)'` (NHAY DON)
de kich hoat exact lookup theo title.

Hau qua: cau hoi paraphrase tu nhien -- du dung ngu phap hon -- se roi vao nhanh
mac dinh va tra ve cau dau cua summary. Da do thuc te tren du lieu that:

    "Who are the authors of \"<title>\"?"      -> SAI (tra ve summary)
    "What subject categories does ... ?"       -> SAI (tra ve summary)
    "Who authored the paper '<title>'?"        -> DUNG
    "What categories does the paper '<title>' belong to?" -> DUNG

Vi vay 4 template duoi day la BAT BUOC, khong duoc paraphrase. Neu sau nay
`qa.py` doi sang dung LLM thi moi noi long duoc rang buoc nay.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.utils import first_sentence, write_json

# So luong document toi thieu can co de tao duoc mot test set co y nghia.
_MIN_DOCUMENTS = 5

# So paper duoc chon lam dai dien. Cang nhieu paper thi test set cang de "giao"
# voi cac dong bi corruption o CP5 -- yeu to quyet dinh xem impact co do duoc khong.
_MAX_SAMPLE_PAPERS = 15


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set tu cleaned dataframe.

    1. Kiem tra so luong document toi thieu.
    2. Chon paper dai dien, trai deu theo thoi gian xuat ban.
    3. Sinh 4 loai cau hoi: summary / authors / date / categories.
    4. Moi row co id, question_type, question, ground_truth, ground_truth_doc_ids.
    5. Ghi JSON ra output_path.
    """
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
        f"({', '.join(f'{k}={v}' for k, v in sorted(by_type.items()))})"
    )

    return test_set


def _select_representative_papers(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """Chon toi da `n` paper, trai deu theo thoi gian xuat ban.

    Trai deu tot hon lay ngau nhien vi no bao gom ca paper cu lan moi -- can thiet
    de corruption "drop latest records" o CP5 co the cham vao test set.
    """
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

    # ground_truth phai khop CHINH XAC gia tri ma qa.py tra ve, neu khong
    # token_f1 se thap du retrieval dung. Xem qa.py:20-29.
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

    questions: list[dict[str, Any]] = []
    for question_type, question, ground_truth in specs:
        # Bo qua khi metadata rong: cau hoi khong co dap an thi khong cham diem duoc.
        if not ground_truth:
            continue
        questions.append(
            {
                "id": None,  # gan lai tuan tu o build_test_set
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [paper_id],
            }
        )
    return questions


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text
