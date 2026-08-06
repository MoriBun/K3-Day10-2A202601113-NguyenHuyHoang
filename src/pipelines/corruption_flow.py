"""Evaluate corrupted data, repair from raw, and compare all states."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from core.config import load_settings
from core.utils import read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe, write_clean_artifacts
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _baseline_run_date(df: pd.DataFrame) -> datetime:
    for _, row in df.iterrows():
        published = pd.to_datetime(row.get("published"), errors="coerce", utc=True)
        age_days = pd.to_numeric(row.get("age_days"), errors="coerce")
        if pd.notna(published) and pd.notna(age_days):
            return published.to_pydatetime() + timedelta(days=int(age_days))
    return datetime.now(UTC)


def _evaluate(settings, df: pd.DataFrame, state: str, embeddings_path, metrics_path, answers_path):
    index = LocalEmbeddingIndex.build(df, settings, embeddings_path)
    evaluation = evaluate_pipeline(settings, index, settings.paths.eval_testset, metrics_path, answers_path)
    quality = run_data_quality_checks(df, settings, state)
    freshness = build_freshness_report(df, settings, settings.paths.quality_dir / f"freshness_{state}.json")
    return evaluation.summary, quality, freshness


def main() -> None:
    settings = load_settings()
    required = (settings.paths.clean_csv, settings.paths.baseline_metrics, settings.paths.eval_testset, settings.paths.raw_records_json)
    if any(not path.exists() for path in required):
        raise FileNotFoundError("Missing baseline artifact; run `python script/run_phase1.py` first.")

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_df = pd.read_csv(settings.paths.clean_csv)
    run_date = _baseline_run_date(baseline_df)
    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    write_clean_artifacts(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    corrupted_metrics, corrupted_quality, corrupted_freshness = _evaluate(settings, corrupted_df, "corrupted", settings.paths.corrupted_embeddings_json, settings.paths.corrupted_metrics, settings.paths.corrupted_answers)

    repaired_df = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), run_date)
    if repaired_df.empty:
        raise RuntimeError("Repair produced no usable records from the raw snapshot.")
    write_clean_artifacts(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_metrics, repaired_quality, repaired_freshness = _evaluate(settings, repaired_df, "repaired", settings.paths.repaired_embeddings_json, settings.paths.repaired_metrics, settings.paths.repaired_answers)
    generate_corruption_report(settings.paths.comparison_report, baseline_metrics, corrupted_metrics, repaired_metrics, corrupted_quality, repaired_quality, corrupted_freshness, repaired_freshness)
    print(f"Corruption flow complete: hit rate baseline={baseline_metrics.get('retrieval_hit_rate', 0):.3f}, corrupted={corrupted_metrics['retrieval_hit_rate']:.3f}, repaired={repaired_metrics['retrieval_hit_rate']:.3f}.")


if __name__ == "__main__":
    main()
