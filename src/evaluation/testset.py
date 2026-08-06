from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from core.config import Settings
from core.utils import write_json
from retrieval.llm import build_llm

# So luong document toi thieu can co de tao duoc mot test set co y nghia.
_MIN_DOCUMENTS = 5

# So paper toi da duoc chon lam dai dien de sinh cau hoi (moi paper = 1 LLM call).
_MAX_SAMPLE_PAPERS = 15


class PaperQuestions(BaseModel):
    """Cau hoi tu nhien (paraphrase) cho tung loai, sinh boi LLM.

    LLM chi duoc yeu cau *dat cau hoi*, khong duoc tra loi hay bia du lieu -
    ground_truth van lay tu metadata that cua paper de tranh hallucination.
    """

    summary_question: str | None = Field(
        default=None, description="A natural question asking what the paper is about."
    )
    authors_question: str | None = Field(
        default=None, description="A natural question asking who wrote the paper."
    )
    date_question: str | None = Field(
        default=None, description="A natural question asking when the paper was published."
    )
    categories_question: str | None = Field(
        default=None, description="A natural question asking what subject/category the paper belongs to."
    )


def build_test_set(df: pd.DataFrame, settings: Settings, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set tu cleaned dataframe, dung LLM de sinh cau hoi tu nhien.

    Pseudo-code (da trien khai):
    1. Kiem tra so luong document toi thieu.
    2. Chon mot so paper dai dien.
    3. Tao nhieu loai cau hoi (qua LLM, fallback template neu LLM loi):
       - summary
       - authors
       - date
       - categories
    4. Moi row can co:
       - id
       - question_type
       - question
       - ground_truth
       - ground_truth_doc_ids
    5. Ghi file JSON vao output_path.
    """
    # 1. Kiem tra so luong document toi thieu ------------------------------
    if len(df) < _MIN_DOCUMENTS:
        raise ValueError(
            f"Not enough documents to build a test set: got {len(df)}, "
            f"need at least {_MIN_DOCUMENTS}."
        )

    # 2. Chon mot so paper dai dien -----------------------------------------
    sample_df = _select_representative_papers(df, n=_MAX_SAMPLE_PAPERS)

    # 3-4. Tao cac loai cau hoi cho tung paper (LLM, co fallback) --------------
    llm_question_gen = _build_question_generator(settings)

    test_set: list[dict[str, Any]] = []
    for _, row in sample_df.iterrows():
        test_set.extend(_build_questions_for_row(row, llm_question_gen))

    # Gan lai id tuan tu, on dinh (0001, 0002, ...)
    for i, item in enumerate(test_set, start=1):
        item["id"] = f"q{i:04d}"

    # 5. Ghi file JSON vao output_path ---------------------------------------
    write_json(output_path, test_set)

    return test_set


# --------------------------------------------------------------------------
# LLM question generation
# --------------------------------------------------------------------------


def _build_question_generator(settings: Settings):
    """Tra ve mot callable(paper_fields) -> PaperQuestions | None.

    Neu khong the khoi tao LLM (thieu API key, provider chua ho tro, ...),
    tra ve None de goi noi bao luon fallback sang template.
    """
    try:
        llm = build_llm(settings=settings, temperature=0.3).with_structured_output(PaperQuestions)
    except Exception:
        return None

    def _generate(paper_fields: dict[str, str]) -> PaperQuestions | None:
        prompt = f"""
You are creating evaluation questions for a RAG system based on a research paper's metadata.

Paper title: {paper_fields.get("title", "")}
Paper summary: {paper_fields.get("summary", "")}
Authors: {paper_fields.get("authors", "")}
Published date: {paper_fields.get("published", "")}
Categories: {paper_fields.get("categories", "")}

Write ONE natural, concise question for each metadata field that is non-empty above.
Do NOT answer the questions. Do NOT invent facts not shown above.
Refer to the paper by its title so the question is unambiguous.
Only fill in a field if the corresponding metadata above is non-empty; otherwise leave it null.
""".strip()
        try:
            return llm.invoke(prompt)
        except Exception:
            return None

    return _generate


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _select_representative_papers(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """Chon toi da `n` paper, trai deu theo thoi gian xuat ban de dai dien tot hon
    la lay ngau nhien thuan tuy (bao gom ca paper cu va moi)."""
    n = min(n, len(df))

    if "published" in df.columns:
        sorted_df = df.copy()
        sorted_df["_published_dt"] = pd.to_datetime(sorted_df["published"], errors="coerce", utc=True)
        sorted_df = sorted_df.sort_values("_published_dt", na_position="last").reset_index(drop=True)
        positions = np.linspace(0, len(sorted_df) - 1, num=n, dtype=int)
        positions = sorted(set(positions.tolist()))
        selected = sorted_df.iloc[positions].drop(columns=["_published_dt"])
        return selected.reset_index(drop=True)

    # Fallback neu khong co cot published: random sample co seed co dinh.
    return df.sample(n=n, random_state=seed).reset_index(drop=True)


def _build_questions_for_row(row: pd.Series, llm_question_gen) -> list[dict[str, Any]]:
    paper_id = row.get("paper_id")
    title = _clean(row.get("title"))
    summary = _clean(row.get("summary"))
    authors = _get_authors_text(row)
    published = _clean(row.get("published"))
    categories = _get_categories_text(row)

    if not paper_id or not title:
        return []

    # Thu sinh cau hoi bang LLM cho ca 4 loai trong 1 lan goi.
    generated: PaperQuestions | None = None
    if llm_question_gen is not None:
        generated = llm_question_gen(
            {
                "title": title,
                "summary": summary,
                "authors": authors,
                "published": published,
                "categories": categories,
            }
        )

    questions: list[dict[str, Any]] = []

    field_map = [
        ("summary", summary, getattr(generated, "summary_question", None) if generated else None,
         f"What is the paper \"{title}\" about?"),
        ("authors", authors, getattr(generated, "authors_question", None) if generated else None,
         f"Who are the authors of \"{title}\"?"),
        ("date", published, getattr(generated, "date_question", None) if generated else None,
         f"When was \"{title}\" published?"),
        ("categories", categories, getattr(generated, "categories_question", None) if generated else None,
         f"What subject categories does \"{title}\" belong to?"),
    ]

    for question_type, ground_truth, llm_question, fallback_question in field_map:
        if not ground_truth:
            continue
        question_text = llm_question.strip() if llm_question and llm_question.strip() else fallback_question
        questions.append(
            _make_item(
                question_type=question_type,
                question=question_text,
                ground_truth=ground_truth,
                doc_ids=[paper_id],
            )
        )

    return questions


def _make_item(question_type: str, question: str, ground_truth: str, doc_ids: list[str]) -> dict[str, Any]:
    return {
        "id": None,  # se duoc gan lai tuan tu o build_test_set
        "question_type": question_type,
        "question": question,
        "ground_truth": ground_truth,
        "ground_truth_doc_ids": doc_ids,
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def _get_authors_text(row: pd.Series) -> str:
    if "authors_joined" in row.index:
        text = _clean(row.get("authors_joined"))
        if text:
            return text
    authors = row.get("authors")
    if isinstance(authors, (list, tuple)) and authors:
        return "; ".join(str(a) for a in authors if str(a).strip())
    return ""


def _get_categories_text(row: pd.Series) -> str:
    if "categories_joined" in row.index:
        text = _clean(row.get("categories_joined"))
        if text:
            return text
    categories = row.get("categories")
    if isinstance(categories, (list, tuple)) and categories:
        return "; ".join(str(c) for c in categories if str(c).strip())
    return _clean(row.get("primary_category"))