from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from core.config import load_settings
from evaluation.testset import build_test_set
from observability.quality import build_freshness_report, run_data_quality_checks


ROOT = Path(__file__).resolve().parents[1]


def _sample_dataframe() -> pd.DataFrame:
    rows = []
    for index, published in enumerate(("2026-07-22", "2026-06-30", "2026-05-14", "2026-04-02", "2026-03-11", "2026-02-19"), start=1):
        summary = f"Sample scholarly summary {index} explains a reproducible retrieval evaluation scenario with enough detail to satisfy the minimum summary-length quality requirement."
        rows.append({
            "paper_id": f"10.5555/test.{index:04d}", "title": f"Test Paper {index}", "summary": summary,
            "authors_joined": f"Author {index}; Collaborator {index}", "categories_joined": "Testing; Evaluation",
            "primary_category": "Testing", "published": published, "updated": published,
            "abs_url": f"https://doi.org/10.5555/test.{index:04d}", "pdf_url": "",
            "text_for_embedding": summary, "age_days": index * 20 - 5, "summary_chars": len(summary),
        })
    return pd.DataFrame(rows)


class Role4ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.df = _sample_dataframe()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_test_set_uses_four_fixed_templates_for_representative_papers(self) -> None:
        output_path = self.output_dir / "test_set.json"
        test_set = build_test_set(self.df, output_path)

        self.assertEqual(len(test_set), 24)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), test_set)
        self.assertEqual({item["question_type"] for item in test_set}, {"summary", "authors", "date", "categories"})
        self.assertTrue(all("'" in item["question"] for item in test_set))
        self.assertTrue(all(item["ground_truth_doc_ids"][0] in set(self.df["paper_id"]) for item in test_set))

    def test_row_count_failure_does_not_hide_other_quality_results(self) -> None:
        settings = replace(load_settings(project_dir=ROOT), paths=replace(load_settings(project_dir=ROOT).paths, quality_dir=self.output_dir))
        report = run_data_quality_checks(self.df, settings, "fixture")
        checks = {check["name"]: check for check in report["checks"]}

        self.assertFalse(report["success"])
        self.assertFalse(checks["row_count_min"]["success"])
        self.assertTrue(checks["summary_min_length"]["success"])
        self.assertTrue(checks["no_duplicate_rows"]["success"])
        self.assertTrue((self.output_dir / "quality_fixture.json").exists())

    def test_freshness_uses_artifact_columns_and_rejects_invalid_age(self) -> None:
        settings = load_settings(project_dir=ROOT)
        report = build_freshness_report(self.df, settings, self.output_dir / "freshness.json")
        self.assertTrue(report["is_fresh"])
        self.assertEqual(report["latest_published"], "2026-07-22")

        invalid = self.df.copy()
        invalid.loc[0, "age_days"] = -1
        invalid_report = build_freshness_report(invalid, settings, self.output_dir / "freshness_invalid.json")
        self.assertFalse(invalid_report["is_fresh"])
        self.assertEqual(invalid_report["invalid_age_rows"], 1)


if __name__ == "__main__":
    unittest.main()
