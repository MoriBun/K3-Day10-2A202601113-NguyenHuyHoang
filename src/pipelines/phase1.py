from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def _save_dataframe(df, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def _test_set_matches_corpus(test_set, clean_df) -> bool:
    if not isinstance(test_set, list) or not test_set:
        return False
    available_ids = set(clean_df["paper_id"].astype(str))
    for item in test_set:
        if not isinstance(item, dict):
            return False
        document_ids = item.get("ground_truth_doc_ids")
        if not isinstance(document_ids, list) or not set(map(str, document_ids)).issubset(available_ids):
            return False
    return True


def main() -> None:
    """Build the reproducible baseline: source -> clean -> index -> evaluate -> report."""
    settings = load_settings()
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records = load_raw_records(settings.paths.raw_records_json)
        source_mode = "existing raw snapshot"
    else:
        records = fetch_source_records(settings)
        source_mode = "fresh Crossref API response"

    clean_df = build_clean_dataframe(records, run_date=now_utc())
    if clean_df.empty:
        raise RuntimeError("Cleaning produced no usable records; inspect data/raw/crossref_records.json and source filters.")
    _save_dataframe(clean_df, settings.paths.clean_csv, settings.paths.clean_json)

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )
    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set = read_json(settings.paths.eval_testset)
        if not _test_set_matches_corpus(test_set, clean_df):
            test_set = build_test_set(clean_df, settings.paths.eval_testset)
    else:
        test_set = build_test_set(clean_df, settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(clean_df, settings, report_name="baseline_quality")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)

    demo_questions = [item["question"] for item in test_set[: min(3, len(test_set))]]
    demo_answers = [
        {
            "question": question,
            "answer": answer_question(question, settings=settings, index=index).answer,
        }
        for question in demo_questions
    ]
    write_json(settings.paths.demo_answers, demo_answers)
    source_summary = {
        "source": settings.source_api,
        "mode": source_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "raw_records": len(records),
        "clean_records": len(clean_df),
        "evaluation_questions": len(test_set),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
    print(
        "Baseline pipeline complete: "
        f"{len(clean_df)} clean papers, {evaluation.summary['retrieval_hit_rate']:.3f} retrieval hit rate."
    )
