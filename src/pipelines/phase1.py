"""Baseline pipeline: raw -> clean -> index -> evaluate -> observability."""

from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe, save_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def _test_set_matches_corpus(test_set, clean_df) -> bool:
    available_ids = set(clean_df["paper_id"].astype(str))
    return bool(test_set) and all(
        isinstance(item, dict)
        and isinstance(item.get("ground_truth_doc_ids"), list)
        and len(item["ground_truth_doc_ids"]) == 1
        and str(item["ground_truth_doc_ids"][0]) in available_ids
        for item in test_set
    )


def main() -> None:
    settings = load_settings()
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records, source_mode = load_raw_records(settings.paths.raw_records_json), "existing raw snapshot"
    else:
        records, source_mode = fetch_source_records(settings), "fresh Crossref API response"

    run_date = now_utc()
    clean_df = build_clean_dataframe(records, run_date)
    if clean_df.empty:
        raise RuntimeError("Cleaning produced no usable records.")
    save_clean_dataframe(clean_df, settings)

    index = LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)
    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        try:
            test_set = read_json(settings.paths.eval_testset)
        except Exception:
            test_set = []
    else:
        test_set = []
    if not _test_set_matches_corpus(test_set, clean_df):
        test_set = build_test_set(clean_df, settings.paths.eval_testset)

    evaluation = evaluate_pipeline(settings, index, settings.paths.eval_testset, settings.paths.baseline_metrics, settings.paths.baseline_answers)
    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    demo_answers = [{"question": item["question"], "answer": answer_question(item["question"], settings, index).answer} for item in test_set[:3]]
    write_json(settings.paths.demo_answers, demo_answers)
    generate_phase1_report(
        settings.paths.baseline_report,
        {"source": settings.source_api, "mode": source_mode, "query": settings.source_query, "filter": settings.source_filter, "raw_records": len(records), "clean_records": len(clean_df), "evaluation_questions": len(test_set), "top_k": settings.top_k},
        evaluation.summary,
        quality,
        freshness,
    )
    print(f"Baseline pipeline complete: {len(clean_df)} clean papers, {evaluation.summary['retrieval_hit_rate']:.3f} retrieval hit rate.")


if __name__ == "__main__":
    main()
