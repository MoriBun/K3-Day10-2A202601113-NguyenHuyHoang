from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def _require_file(path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {description}: {path}. Run `python script/run_phase1.py` first.")

def main() -> None:
    """Measure corruption impact, repair from raw data, and publish the comparison."""
    settings = load_settings()
    _require_file(settings.paths.clean_csv, "baseline clean dataset")
    _require_file(settings.paths.baseline_metrics, "baseline metrics")
    _require_file(settings.paths.eval_testset, "baseline evaluation test set")
    _require_file(settings.paths.raw_records_json, "raw records snapshot")
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_df = pd.read_csv(settings.paths.clean_csv, keep_default_na=False)

    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    _save_dataframe(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings=settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_evaluation = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, report_name="corrupted_quality")
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings,
        settings.paths.quality_dir / "freshness_corrupted.json",
    )

    repaired_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(repaired_records, run_date=now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair produced no usable records from the raw snapshot.")
    _save_dataframe(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings=settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_evaluation = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired_quality")
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings,
        settings.paths.quality_dir / "freshness_repaired.json",
    )
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(
        "Corruption flow complete: "
        f"hit rate baseline={baseline_metrics.get('retrieval_hit_rate', 0):.3f}, "
        f"corrupted={corrupted_evaluation.summary['retrieval_hit_rate']:.3f}, "
        f"repaired={repaired_evaluation.summary['retrieval_hit_rate']:.3f}."
    )
