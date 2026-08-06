from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build deterministic factual questions whose answers are in the clean corpus."""
    required = {"paper_id", "title", "summary", "authors_joined", "published", "categories_joined"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Cannot build test set; dataframe missing columns: {sorted(missing)}")
    unique = df.drop_duplicates(subset="paper_id", keep="first").reset_index(drop=True)
    if len(unique) < 4:
        raise ValueError("At least four clean papers are required to build the evaluation set.")

    sample_size = min(8, len(unique))
    positions = sorted({round(index * (len(unique) - 1) / (sample_size - 1)) for index in range(sample_size)})
    selected = unique.iloc[positions]
    test_set: list[dict[str, Any]] = []
    question_templates = (
        ("summary", "What is the main contribution described in '{title}'?", "summary"),
        ("authors", "Who authored '{title}'?", "authors_joined"),
        ("publication_date", "When was '{title}' published?", "published"),
        ("categories", "What categories are assigned to '{title}'?", "categories_joined"),
    )
    for row_index, (_, row) in enumerate(selected.iterrows(), start=1):
        values = row.to_dict()
        for question_type, template, answer_column in question_templates:
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
