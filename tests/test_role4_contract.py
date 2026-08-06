from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from core.config import load_settings
from evaluation.testset import build_test_set
from observability.quality import build_freshness_report, run_data_quality_checks


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "papers_clean_sample.json"


class Role4ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.df = pd.read_json(FIXTURE_PATH)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_test_set_uses_four_fixed_templates_for_four_papers(self) -> None:
        output_path = self.output_dir / "test_set.json"
        test_set = build_test_set(self.df, output_path)

        self.assertEqual(len(test_set), 16)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), test_set)
        self.assertEqual({item["question_type"] for item in test_set}, {"summary", "authors", "date", "categories"})
        self.assertTrue(all(len(item["ground_truth_doc_ids"]) == 1 for item in test_set))
        self.assertTrue(
            {item["ground_truth_doc_ids"][0] for item in test_set}.issubset(set(self.df["paper_id"]))
        )

    def test_fixture_exercises_the_row_count_gate_without_hiding_other_quality_results(self) -> None:
        settings = load_settings(project_dir=ROOT)
        settings = replace(settings, paths=replace(settings.paths, quality_dir=self.output_dir))

        report = run_data_quality_checks(self.df, settings, report_name="fixture_quality")

        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["row_count_min"]["passed"])
        self.assertTrue(report["checks"]["summary_min_length"]["passed"])
        self.assertTrue(report["checks"]["no_duplicate_rows"]["passed"])
        self.assertTrue((self.output_dir / "fixture-quality.json").exists())

    def test_fixture_freshness_is_calculated_from_artifact_columns(self) -> None:
        settings = load_settings(project_dir=ROOT)
        report_path = self.output_dir / "freshness.json"

        report = build_freshness_report(self.df, settings, report_path)

        self.assertTrue(report["is_fresh"])
        self.assertEqual(report["stale_rows"], 0)
        self.assertEqual(report["invalid_age_rows"], 0)
        self.assertEqual(report["latest_published"], "2026-07-22")
        self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
