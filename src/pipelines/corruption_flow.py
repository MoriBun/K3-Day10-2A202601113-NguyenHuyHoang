"""Corruption flow (CP5 + CP6).

baseline -> corrupt -> evaluate -> repair tu raw -> evaluate -> comparison report

Chay: python script/run_corruption_flow.py

Nam nguyen tac bat buoc (CONTRACT.md muc 0):
1. Chi chay sau khi baseline da tao du artifact -- script dung ngay neu thieu.
2. Dung LAI test set da khoa, khong sinh moi. Ba trang thai phai cham tren cung
   mot bo cau hoi thi so sanh moi co nghia.
3. Ba trang thai co path va collection rieng; baseline khong bao gio bi ghi de.
4. Repair = chay lai cleaning tu raw snapshot, KHONG copy file clean cu.
5. Khong fetch lai Crossref o day. Fetch giua chung lam comparison mat cong bang.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe, write_clean_artifacts
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex

_METRIC_KEYS = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")


def _step(number: int, label: str) -> None:
    print(f"\n[{number}/8] {label}")


def _freshness_path(settings: Settings, name: str) -> Path:
    """Freshness cua tung trang thai phai ra file rieng.

    `paths.freshness_report` chi co mot duong dan (baseline dang dung). Neu
    corrupted/repaired cung ghi vao do thi bang chung baseline bi xoa mat.
    """
    return settings.paths.quality_dir / f"freshness_{name}.json"


def _require_baseline(settings: Settings) -> dict[str, Any]:
    """Chan som neu baseline chua hoan tat (nguyen tac bat buoc so 1)."""
    required = {
        "baseline metrics": settings.paths.baseline_metrics,
        "clean dataset": settings.paths.clean_csv,
        "test set": settings.paths.eval_testset,
        "raw records (nguon repair)": settings.paths.raw_records_json,
    }
    missing = [f"{label} ({path})" for label, path in required.items() if not path.exists()]
    if missing:
        raise RuntimeError(
            "Chua the chay corruption flow, thieu artifact baseline:\n  - "
            + "\n  - ".join(missing)
            + "\nChay `python script/run_phase1.py` truoc."
        )
    return read_json(settings.paths.baseline_metrics)


def _baseline_run_date(df: pd.DataFrame) -> datetime:
    """Dung lai dung moc thoi gian ma baseline da dung de tinh `age_days`.

    Suy nguoc tu chinh du lieu baseline: run_date = published + age_days. Neu lay
    `datetime.now()` thi repaired se lech baseline vai gio va lam `age_days`
    khac nhau -- so sanh freshness khong con chinh xac.
    """
    for _, row in df.iterrows():
        published = pd.to_datetime(row.get("published"), errors="coerce", utc=True)
        age_days = pd.to_numeric(row.get("age_days"), errors="coerce")
        if pd.notna(published) and pd.notna(age_days):
            return published.to_pydatetime() + timedelta(days=int(age_days))
    return datetime.now(UTC)


def _evaluate_state(
    settings: Settings,
    df: pd.DataFrame,
    name: str,
    embeddings_path: Path,
    metrics_path: Path,
    answers_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build index rieng -> evaluate tren test set cu -> quality + freshness."""
    index = LocalEmbeddingIndex.build(df, settings, embeddings_path)
    print(f"  collection={index.collection_name} documents={len(index.documents)}")

    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=metrics_path,
        answers_output_path=answers_path,
    )
    for key in _METRIC_KEYS:
        print(f"  {key:20s}: {bundle.summary.get(key)}")

    quality = run_data_quality_checks(df, settings, name)
    freshness = build_freshness_report(df, settings, _freshness_path(settings, name))
    return bundle.summary, quality, freshness


def main() -> None:
    settings = load_settings()

    print("=" * 68)
    print("CORRUPTION FLOW - corrupt / evaluate / repair / compare")
    print("=" * 68)

    _step(1, "Kiem tra baseline va nap clean dataset")
    baseline_metrics = _require_baseline(settings)
    baseline_df = pd.read_csv(settings.paths.clean_csv)
    run_date = _baseline_run_date(baseline_df)
    test_set = read_json(settings.paths.eval_testset)
    print(f"  baseline: {len(baseline_df)} dong | test set: {len(test_set)} cau (dung lai, khong sinh moi)")
    print(f"  run_date suy tu baseline: {run_date.date().isoformat()}")

    _step(2, "Tao corrupted dataset")
    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    log = read_json(settings.paths.corruption_log)
    affected: set[str] = set()
    for action in log.get("actions", []):
        for key in ("dropped_paper_ids", "affected_paper_ids", "duplicated_paper_ids"):
            affected.update(action.get(key, []))
        print(f"  {action['step']:22s} count={action['count']}")

    # Corruption chon dong ngau nhien nhung test set chi phu mot phan corpus.
    # Neu khong giao nhau thi metrics se dung im va bai mat luan diem chinh.
    test_ids = {item["ground_truth_doc_ids"][0] for item in test_set}
    overlap = affected & test_ids
    affected_questions = sum(1 for item in test_set if item["ground_truth_doc_ids"][0] in overlap)
    print(f"  paper bi corrupt: {len(affected)} | giao voi test set: {len(overlap)}")
    print(f"  -> {affected_questions}/{len(test_set)} cau hoi bi anh huong")
    if not overlap:
        print("  CANH BAO: corruption khong cham cau hoi nao. Metrics se khong doi.")
        print("  Tang cac _*_FRACTION trong corruption.py roi chay lai.")

    _step(3, "Luu corrupted artifacts (path rieng, khong de len baseline)")
    write_clean_artifacts(
        corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json
    )
    print(f"  {settings.paths.corrupted_clean_csv.name} ({len(corrupted_df)} dong)")

    _step(4, "Rebuild index + evaluate CORRUPTED")
    corrupted_metrics, corrupted_quality, corrupted_freshness = _evaluate_state(
        settings,
        corrupted_df,
        "corrupted",
        settings.paths.corrupted_embeddings_json,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )

    _step(5, "Repair: chay lai cleaning tu raw snapshot")
    # KHONG copy papers_clean.csv. Repair phai la ket qua chay that tu raw,
    # neu khong thi khong chung minh duoc gi ca.
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date)
    write_clean_artifacts(
        repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json
    )
    print(f"  {len(raw_records)} raw records -> {len(repaired_df)} dong repaired")

    _step(6, "Rebuild index + evaluate REPAIRED")
    repaired_metrics, repaired_quality, repaired_freshness = _evaluate_state(
        settings,
        repaired_df,
        "repaired",
        settings.paths.repaired_embeddings_json,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )

    _step(7, "Kiem tra baseline khong bi ghi de")
    baseline_after = pd.read_csv(settings.paths.clean_csv)
    intact = len(baseline_after) == len(baseline_df) and baseline_after["paper_id"].is_unique
    print(f"  papers_clean.csv: {len(baseline_after)} dong, paper_id unique={baseline_after['paper_id'].is_unique}")
    print(f"  baseline nguyen ven: {'OK' if intact else 'HONG - dieu tra ngay'}")

    _step(8, "Comparison report")
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_metrics,
        repaired_metrics=repaired_metrics,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f"  {settings.paths.comparison_report}")

    print("\n" + "=" * 68)
    print("SO SANH BA TRANG THAI")
    print(f"  {'metric':22s} {'baseline':>10s} {'corrupted':>10s} {'repaired':>10s}")
    for key in _METRIC_KEYS:
        base, corrupt, repair = (
            baseline_metrics.get(key),
            corrupted_metrics.get(key),
            repaired_metrics.get(key),
        )
        fmt = lambda v: f"{v:.4f}" if isinstance(v, (int, float)) else str(v)
        print(f"  {key:22s} {fmt(base):>10s} {fmt(corrupt):>10s} {fmt(repair):>10s}")

    print("\nARTIFACT DA GHI")
    for path in (
        settings.paths.corruption_log,
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
        settings.paths.corrupted_embeddings_json,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
        settings.paths.quality_dir / "quality_corrupted.json",
        _freshness_path(settings, "corrupted"),
        settings.paths.repaired_clean_csv,
        settings.paths.repaired_clean_json,
        settings.paths.repaired_embeddings_json,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
        settings.paths.quality_dir / "quality_repaired.json",
        _freshness_path(settings, "repaired"),
        settings.paths.comparison_report,
    ):
        mark = "OK  " if path.exists() else "MISS"
        print(f"  [{mark}] {path.relative_to(settings.paths.project_dir)}")
    print("=" * 68)


if __name__ == "__main__":
    main()
