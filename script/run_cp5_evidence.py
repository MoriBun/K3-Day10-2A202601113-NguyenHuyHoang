"""Sinh bang chung cho CP5/CP6 — phan viec phan tich cua VT2, VT3, VT4.

Chay sau `run_corruption_flow.py`:
    python script/run_cp5_evidence.py

Ba khoi bang chung:
  VT2  lineage & raw integrity  -- raw con nguyen ven, record hong da phuc hoi
  VT3  retrieval impact         -- cung query, top-4 doi the nao giua 2 collection
  VT4  case study               -- cau hoi CU THE nao xau di va vi sao

Ket qua ghi ra data/results/cp5_evidence.json de trich thang vao bao cao.
Rubric muc 8 doi "do duoc impact ro" -- con so tong thi ai cung co, case study
cu the moi la thu thuyet phuc.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from core.config import load_settings
from core.utils import read_json, write_json
from retrieval.index import LocalEmbeddingIndex

_SMOKE_QUERIES = [
    "agentic retrieval augmented generation for question answering",
    "data quality and observability in machine learning pipelines",
    "large language model evaluation and benchmarking",
]


def _corruption_index(log: dict[str, Any]) -> dict[str, list[str]]:
    """paper_id -> danh sach kich ban corruption da tac dong len no."""
    mapping: dict[str, list[str]] = {}
    for action in log.get("actions", []):
        for key in ("dropped_paper_ids", "affected_paper_ids", "duplicated_paper_ids"):
            for paper_id in action.get(key, []):
                mapping.setdefault(paper_id, []).append(action["step"])
    return mapping


# --------------------------------------------------------------------------
# VT2 — lineage & raw integrity
# --------------------------------------------------------------------------


def evidence_lineage(settings, corruption_map: dict[str, list[str]]) -> dict[str, Any]:
    raw_records = read_json(settings.paths.raw_records_json)
    baseline = pd.read_csv(settings.paths.clean_csv)
    corrupted = pd.read_csv(settings.paths.corrupted_clean_csv)
    repaired = pd.read_csv(settings.paths.repaired_clean_csv)

    base_ids = set(baseline["paper_id"])
    corr_ids = set(corrupted["paper_id"])
    rep_ids = set(repaired["paper_id"])

    dropped = sorted(base_ids - corr_ids)
    restored = sorted(set(dropped) & rep_ids)

    # Voi cac paper bi corrupt, so noi dung repaired vs baseline: phai giong het.
    samples: list[dict[str, Any]] = []
    for paper_id in sorted(corruption_map)[:5]:
        b = baseline[baseline["paper_id"] == paper_id]
        c = corrupted[corrupted["paper_id"] == paper_id]
        r = repaired[repaired["paper_id"] == paper_id]
        if b.empty or r.empty:
            samples.append(
                {
                    "paper_id": paper_id,
                    "corruptions": corruption_map[paper_id],
                    "in_corrupted": not c.empty,
                    "restored_from_raw": not r.empty,
                    "note": "bi drop khoi corrupted, da phuc hoi tu raw" if not r.empty else "chua phuc hoi",
                }
            )
            continue
        samples.append(
            {
                "paper_id": paper_id,
                "corruptions": corruption_map[paper_id],
                "title_baseline": str(b["title"].iloc[0])[:70],
                "title_corrupted": (str(c["title"].iloc[0])[:70] if not c.empty else None),
                "title_repaired": str(r["title"].iloc[0])[:70],
                "title_khop_baseline": str(b["title"].iloc[0]) == str(r["title"].iloc[0]),
                "authors_khop_baseline": str(b["authors_joined"].iloc[0]) == str(r["authors_joined"].iloc[0]),
                "published_khop_baseline": str(b["published"].iloc[0]) == str(r["published"].iloc[0]),
            }
        )

    identical_columns = [
        column
        for column in ("paper_id", "title", "authors_joined", "published", "summary")
        if column in baseline.columns
        and baseline.sort_values("paper_id")[column].reset_index(drop=True).equals(
            repaired.sort_values("paper_id")[column].reset_index(drop=True)
        )
    ]

    return {
        "raw_records": len(raw_records),
        "raw_response_ton_tai": settings.paths.raw_api_response.exists(),
        "rows": {"baseline": len(baseline), "corrupted": len(corrupted), "repaired": len(repaired)},
        "paper_bi_drop_khoi_corrupted": dropped,
        "paper_da_phuc_hoi_tu_raw": restored,
        "phuc_hoi_day_du": len(restored) == len(dropped),
        "cot_repaired_giong_het_baseline": identical_columns,
        "samples": samples,
    }


# --------------------------------------------------------------------------
# VT3 — retrieval impact
# --------------------------------------------------------------------------


def evidence_retrieval(settings) -> dict[str, Any]:
    baseline_index = LocalEmbeddingIndex.load(settings, settings.paths.embeddings_json)
    corrupted_index = LocalEmbeddingIndex.load(settings, settings.paths.corrupted_embeddings_json)

    comparisons: list[dict[str, Any]] = []
    changed = 0
    for query in _SMOKE_QUERIES:
        base_hits = baseline_index.search(query, top_k=settings.top_k)
        corr_hits = corrupted_index.search(query, top_k=settings.top_k)
        base_ids = [h.paper_id for h in base_hits]
        corr_ids = [h.paper_id for h in corr_hits]
        if base_ids != corr_ids:
            changed += 1
        comparisons.append(
            {
                "query": query,
                "baseline_top_k": base_ids,
                "corrupted_top_k": corr_ids,
                "top1_doi": base_ids[:1] != corr_ids[:1],
                "so_paper_bi_day_ra": len(set(base_ids) - set(corr_ids)),
                "baseline_scores": [round(h.score, 4) for h in base_hits],
                "corrupted_scores": [round(h.score, 4) for h in corr_hits],
            }
        )

    return {
        "collection_baseline": baseline_index.collection_name,
        "collection_corrupted": corrupted_index.collection_name,
        "collection_tach_biet": baseline_index.collection_name != corrupted_index.collection_name,
        "baseline_documents": len(baseline_index.documents),
        "corrupted_documents": len(corrupted_index.documents),
        "so_query_bi_doi_ket_qua": changed,
        "tong_query": len(_SMOKE_QUERIES),
        "comparisons": comparisons,
    }


# --------------------------------------------------------------------------
# VT4 — case study
# --------------------------------------------------------------------------


def evidence_case_study(settings, corruption_map: dict[str, list[str]]) -> dict[str, Any]:
    baseline = {a["id"]: a for a in read_json(settings.paths.baseline_answers)}
    corrupted = {a["id"]: a for a in read_json(settings.paths.corrupted_answers)}
    repaired = {a["id"]: a for a in read_json(settings.paths.repaired_answers)}

    degraded: list[dict[str, Any]] = []
    for item_id, base in baseline.items():
        corr = corrupted.get(item_id)
        if corr is None:
            continue
        f1_drop = float(base["token_f1"]) - float(corr["token_f1"])
        hit_lost = bool(base["retrieval_hit"]) and not bool(corr["retrieval_hit"])
        judge_lost = bool(base["judge"]["correct"]) and not bool(corr["judge"]["correct"])
        if f1_drop <= 1e-9 and not hit_lost and not judge_lost:
            continue

        paper_id = base["ground_truth_doc_ids"][0]
        rep = repaired.get(item_id, {})
        degraded.append(
            {
                "id": item_id,
                "question_type": base["question_type"],
                "paper_id": paper_id,
                "corruptions": corruption_map.get(paper_id, []),
                "question": base["question"][:110],
                "ground_truth": str(base["ground_truth"])[:80],
                "answer_baseline": str(base["answer"])[:80],
                "answer_corrupted": str(corr["answer"])[:80],
                "token_f1": {
                    "baseline": round(float(base["token_f1"]), 4),
                    "corrupted": round(float(corr["token_f1"]), 4),
                    "repaired": round(float(rep.get("token_f1", 0)), 4) if rep else None,
                },
                "retrieval_hit": {
                    "baseline": bool(base["retrieval_hit"]),
                    "corrupted": bool(corr["retrieval_hit"]),
                    "repaired": bool(rep.get("retrieval_hit")) if rep else None,
                },
                "judge_correct": {
                    "baseline": bool(base["judge"]["correct"]),
                    "corrupted": bool(corr["judge"]["correct"]),
                    "repaired": bool(rep.get("judge", {}).get("correct")) if rep else None,
                },
                "phuc_hoi_hoan_toan": (
                    rep is not None
                    and abs(float(rep.get("token_f1", -1)) - float(base["token_f1"])) < 1e-9
                    and bool(rep.get("retrieval_hit")) == bool(base["retrieval_hit"])
                ),
            }
        )

    degraded.sort(key=lambda d: d["token_f1"]["baseline"] - d["token_f1"]["corrupted"], reverse=True)

    return {
        "tong_cau_hoi": len(baseline),
        "so_cau_xau_di": len(degraded),
        "theo_loai_cau_hoi": dict(Counter(d["question_type"] for d in degraded)),
        "theo_kich_ban_corruption": dict(
            Counter(step for d in degraded for step in d["corruptions"])
        ),
        "so_cau_phuc_hoi_hoan_toan": sum(1 for d in degraded if d["phuc_hoi_hoan_toan"]),
        "cases": degraded,
    }


# --------------------------------------------------------------------------


def main() -> None:
    settings = load_settings()
    log = read_json(settings.paths.corruption_log)
    corruption_map = _corruption_index(log)

    print("=" * 68)
    print("BANG CHUNG CP5/CP6")
    print("=" * 68)

    print("\n--- VT2: lineage & raw integrity ---")
    lineage = evidence_lineage(settings, corruption_map)
    print(f"  raw records con nguyen: {lineage['raw_records']} | raw response: {lineage['raw_response_ton_tai']}")
    print(f"  rows baseline/corrupted/repaired: {lineage['rows']}")
    print(f"  paper bi drop khoi corrupted: {lineage['paper_bi_drop_khoi_corrupted']}")
    print(f"  da phuc hoi tu raw          : {lineage['paper_da_phuc_hoi_tu_raw']}")
    print(f"  phuc hoi day du             : {lineage['phuc_hoi_day_du']}")
    print(f"  cot repaired giong het baseline: {lineage['cot_repaired_giong_het_baseline']}")

    print("\n--- VT3: retrieval impact ---")
    retrieval = evidence_retrieval(settings)
    print(f"  collection tach biet: {retrieval['collection_tach_biet']} "
          f"({retrieval['collection_baseline']} vs {retrieval['collection_corrupted']})")
    print(f"  query bi doi ket qua: {retrieval['so_query_bi_doi_ket_qua']}/{retrieval['tong_query']}")
    for comparison in retrieval["comparisons"]:
        flag = "DOI" if comparison["baseline_top_k"] != comparison["corrupted_top_k"] else "giu nguyen"
        print(f"    [{flag}] {comparison['query'][:52]}")
        if flag == "DOI":
            print(f"        bi day ra khoi top-{settings.top_k}: {comparison['so_paper_bi_day_ra']} paper")

    print("\n--- VT4: case study ---")
    case = evidence_case_study(settings, corruption_map)
    print(f"  {case['so_cau_xau_di']}/{case['tong_cau_hoi']} cau hoi xau di sau corruption")
    print(f"  theo loai cau hoi   : {case['theo_loai_cau_hoi']}")
    print(f"  theo kich ban       : {case['theo_kich_ban_corruption']}")
    print(f"  phuc hoi hoan toan  : {case['so_cau_phuc_hoi_hoan_toan']}/{case['so_cau_xau_di']}")
    print("\n  3 case ro nhat:")
    for c in case["cases"][:3]:
        print(f"    [{c['id']}] {c['question_type']} | corruption: {', '.join(c['corruptions']) or 'gian tiep'}")
        print(f"        token_f1  {c['token_f1']['baseline']} -> {c['token_f1']['corrupted']} -> {c['token_f1']['repaired']}")
        print(f"        can       : {c['ground_truth'][:66]}")
        print(f"        corrupted : {c['answer_corrupted'][:66]}")

    output_path = settings.paths.project_dir / "data" / "results" / "cp5_evidence.json"
    write_json(output_path, {"lineage": lineage, "retrieval": retrieval, "case_study": case})
    print(f"\n  -> {output_path.relative_to(settings.paths.project_dir)}")
    print("=" * 68)


if __name__ == "__main__":
    main()
