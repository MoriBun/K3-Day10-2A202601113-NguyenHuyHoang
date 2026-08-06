"""Baseline pipeline (CP3).

raw -> clean -> index -> test set -> evaluate -> quality/freshness -> report

Chay: python script/run_phase1.py

Ba nguyen tac phai giu (CONTRACT.md muc 0):
- Mac dinh KHONG fetch lai Crossref. Doc snapshot trong data/raw/ de baseline,
  corrupted va repaired cung so sanh tren mot nguon. Muon fetch lai: REFRESH_SOURCE=1.
- Test set khoa lai tu CP2. Muon sinh lai: REFRESH_TEST_SET=1.
- Index baseline phai ghi vao `paths.embeddings_json` de collection duoc dat ten
  `papers-baseline`. Bo trong tham so nay la ca ba trang thai cung de len nhau.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe, save_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

_QUALITY_REPORT_NAME = "baseline"


def _step(number: int, label: str) -> None:
    print(f"\n[{number}/10] {label}")


def _load_records(settings: Settings) -> tuple[list[PaperRecord], str]:
    """Doc raw records. Uu tien snapshot da co de baseline tai lap duoc."""
    raw_path = settings.paths.raw_records_json

    if settings.refresh_source:
        print("  REFRESH_SOURCE=1 -> goi lai Crossref")
        return fetch_source_records(settings), "crossref-api"

    if raw_path.exists():
        records = load_raw_records(raw_path)
        print(f"  doc snapshot {raw_path.name}: {len(records)} records (khong goi API)")
        return records, "snapshot"

    print("  chua co snapshot -> fetch lan dau tu Crossref")
    return fetch_source_records(settings), "crossref-api"


def _resolve_test_set(settings: Settings, df: pd.DataFrame):
    """Tao test set neu chua co. Da co thi giu nguyen -- test set la hang so
    cua ca ba trang thai baseline/corrupted/repaired."""
    path = settings.paths.eval_testset

    if settings.refresh_test_set or not path.exists():
        reason = "REFRESH_TEST_SET=1" if path.exists() else "chua ton tai"
        print(f"  sinh test set moi ({reason})")
        items = build_test_set(df, path)
        print(f"  tao {len(items)} cau hoi -> {path.name}")
    else:
        print(f"  dung lai test set da khoa: {path.name}")

    return path


def _build_source_summary(
    settings: Settings,
    records: list[PaperRecord],
    df: pd.DataFrame,
    source_mode: str,
    run_date: datetime,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source_api": settings.source_api,
        "source_mode": source_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "top_k": settings.top_k,
        "embedding_model": settings.embedding_model,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
        "run_date": run_date.isoformat(),
        "raw_records": len(records),
        "clean_rows": int(len(df)),
    }
    # `clean_stats` do cleaning.py gan vao -- cho phep truy vet record bi loai.
    summary["clean_stats"] = dict(df.attrs.get("clean_stats", {}))
    return summary


def _demo_agent(settings: Settings, index: LocalEmbeddingIndex, df: pd.DataFrame) -> None:
    """Demo agent tren vai cau hoi that. Loi o day khong duoc lam hong baseline."""
    if df.empty:
        return

    title = str(df["title"].iloc[0])
    questions = [
        f"What is the paper '{title}' about?",
        f"Who authored the paper '{title}'?",
        "Which indexed papers discuss retrieval augmented generation?",
    ]

    try:
        agent = build_agent(settings=settings, index=index)
        answers = [
            {"question": question, "answer": run_agent_question(agent, question)}
            for question in questions
        ]
        write_json(settings.paths.demo_answers, answers)
        print(f"  {len(answers)} cau -> {settings.paths.demo_answers.name}")
    except Exception as exc:  # pragma: no cover - phu thuoc LLM provider ben ngoai
        print(f"  BO QUA demo agent: {exc}")
        print("  (baseline metrics khong bi anh huong -- qa.py khong dung LLM)")


def main() -> None:
    run_date = now_utc()
    settings = load_settings()

    print("=" * 68)
    print("PHASE 1 - BASELINE PIPELINE")
    print(f"provider={settings.llm_provider} model={settings.model_name} top_k={settings.top_k}")
    print("=" * 68)

    _step(1, "Load raw records")
    records, source_mode = _load_records(settings)
    if not records:
        raise RuntimeError("Khong co raw record nao. Kiem tra data/raw/ hoac chay lai voi REFRESH_SOURCE=1.")

    _step(2, "Clean data")
    df = build_clean_dataframe(records, run_date)
    if df.empty:
        raise RuntimeError("Cleaned dataframe rong -- xem lai rule loc trong cleaning.py.")

    _step(3, "Save clean artifacts")
    save_clean_dataframe(df, settings)
    print(f"  {settings.paths.clean_csv.name} + {settings.paths.clean_json.name} ({len(df)} dong)")

    _step(4, "Build embedding index")
    # Truyen embeddings_json de collection duoc dat ten `papers-baseline`
    # (index.py:68-81). Bo trong la ca ba trang thai ghi de len nhau.
    index = LocalEmbeddingIndex.build(df, settings, settings.paths.embeddings_json)
    print(f"  collection={index.collection_name} documents={len(index.documents)}")

    _step(5, "Test set")
    test_set_path = _resolve_test_set(settings, df)

    _step(6, "Evaluate")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=test_set_path,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    metrics = bundle.summary
    for key in ("samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"  {key:20s}: {metrics.get(key)}")

    _step(7, "Data quality checks")
    quality = run_data_quality_checks(df, settings, _QUALITY_REPORT_NAME)

    _step(8, "Freshness report")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    _step(9, "Markdown report")
    source_summary = _build_source_summary(settings, records, df, source_mode, run_date)
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=metrics,
        quality=quality,
        freshness=freshness,
    )
    print(f"  {settings.paths.baseline_report}")

    _step(10, "Demo agent")
    _demo_agent(settings, index, df)

    print("\n" + "=" * 68)
    print("ARTIFACT DA GHI")
    for path in (
        settings.paths.raw_api_response,
        settings.paths.raw_records_json,
        settings.paths.clean_csv,
        settings.paths.clean_json,
        settings.paths.embeddings_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
        settings.paths.freshness_report,
        settings.paths.baseline_report,
    ):
        mark = "OK  " if path.exists() else "MISS"
        print(f"  [{mark}] {path.relative_to(settings.paths.project_dir)}")
    print("=" * 68)
    print("Baseline chi hoan tat khi artifact, metrics va report khop nhau,")
    print("khong phai khi script exit code 0.")


if __name__ == "__main__":
    main()
