from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json


_EVALUATION_PAPER_COUNT = 4
_MINIMUM_SUMMARY_CHARS = 100
_QUESTION_TEMPLATES = (
    ("summary", "What is the paper '{title}' about?", "summary"),
    ("authors", "Who authored the paper '{title}'?", "authors_joined"),
    ("date", "When was the paper '{title}' published?", "published"),
    ("categories", "What categories does the paper '{title}' belong to?", "categories_joined"),
)


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build the fixed 16-question factual evaluation set from clean papers."""
    required = {"paper_id", "title", "summary", "authors_joined", "published", "categories_joined"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Cannot build test set; dataframe missing columns: {sorted(missing)}")
    unique = df.drop_duplicates(subset="paper_id", keep="first").reset_index(drop=True)
    eligible = unique[
        unique["paper_id"].fillna("").astype(str).str.strip().ne("")
        & unique["title"].fillna("").astype(str).str.strip().ne("")
        & unique["authors_joined"].fillna("").astype(str).str.strip().ne("")
        & unique["summary"].fillna("").astype(str).str.len().ge(_MINIMUM_SUMMARY_CHARS)
    ].reset_index(drop=True)
    if len(eligible) < _EVALUATION_PAPER_COUNT:
        raise ValueError(
            "At least four clean papers with a non-empty title, authors, and 100-character summary are required."
        )

    positions = [
        round(index * (len(eligible) - 1) / (_EVALUATION_PAPER_COUNT - 1))
        for index in range(_EVALUATION_PAPER_COUNT)
    ]
    selected = eligible.iloc[positions]
    test_set: list[dict[str, Any]] = []
    for row_index, (_, row) in enumerate(selected.iterrows(), start=1):
        values = row.to_dict()
        for question_type, template, answer_column in _QUESTION_TEMPLATES:
            test_set.append(
                {
                    "id": f"eval-{row_index:02d}-{question_type}",
                    "question_type": question_type,
                    "question": template.format(title=values["title"]),
                    "ground_truth": (
                        first_sentence(str(values[answer_column]))
                        if question_type == "summary"
                        else str(values[answer_column])
                    ),
                    "ground_truth_doc_ids": [str(values["paper_id"])],
                }
            )
    write_json(output_path, test_set)
    return test_set
