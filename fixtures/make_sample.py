"""Sinh fixture clean dataset dung de unblock VT3 va VT4 truoc khi VT2 fetch xong.

Chay:  python fixtures/make_sample.py

Script nay CHI dung thu vien chuan, khong can pandas -> chay duoc ngay ca khi chua
`pip install -e .`. Day cung la ban tham chieu chay duoc cua cong thuc
`text_for_embedding` va `age_days` mo ta trong CONTRACT.md muc 4.

CANH BAO: du lieu ben duoi la GIA, DOI dung prefix 10.5555 (prefix danh rieng cho
test/dummy). Khong duoc dung fixture nay de sinh so lieu bao cao. Baseline that phai
den tu data/clean/papers_clean.csv do VT2 tao.
"""

from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path

# Moc thoi gian co dinh de fixture tai lap duoc (age_days khong doi theo ngay chay).
RUN_DATE = date(2026, 8, 6)

FIELDNAMES = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
    "age_days",
    "summary_chars",
]

RAW_ROWS = [
    {
        "paper_id": "10.5555/fixture.2026.0001",
        "title": "Agentic Retrieval Augmented Generation for Scholarly Question Answering",
        "summary": (
            "We introduce an agentic retrieval augmented generation framework that lets a "
            "language model decide when to call a semantic search tool and when to answer "
            "directly. On a corpus of scholarly abstracts the agent improves answer accuracy "
            "over a single-shot retrieval baseline while issuing fewer retrieval calls."
        ),
        "authors": ["Tran Minh Khoa", "Le Thi Hong", "Pham Quoc Bao"],
        "categories": ["Computer Science", "Information Retrieval"],
        "published": date(2026, 7, 22),
    },
    {
        "paper_id": "10.5555/fixture.2026.0002",
        "title": "Measuring Data Quality Drift in Retrieval Pipelines",
        "summary": (
            "Retrieval pipelines degrade silently when upstream data quality drifts. This work "
            "defines a set of observable signals over row counts, null rates, duplicate rates "
            "and record freshness, then correlates each signal with downstream retrieval hit "
            "rate on a fixed evaluation set."
        ),
        "authors": ["Nguyen Van An", "Do Thi Mai"],
        "categories": ["Data Engineering", "Machine Learning"],
        "published": date(2026, 6, 30),
    },
    {
        "paper_id": "10.5555/fixture.2026.0003",
        "title": "Embedding Staleness and Its Effect on Large Language Model Grounding",
        "summary": (
            "Vector stores are rebuilt far less often than the source corpus changes. We "
            "quantify how stale embeddings affect grounding quality for large language models, "
            "showing that recall on recently published documents degrades faster than overall "
            "recall and is therefore invisible to aggregate metrics."
        ),
        "authors": ["Hoang Gia Bao", "Vu Thi Lan", "Dang Hai Nam", "Bui Anh Tuan"],
        "categories": ["Natural Language Processing", "Information Retrieval"],
        "published": date(2026, 5, 14),
    },
    {
        "paper_id": "10.5555/fixture.2026.0004",
        "title": "A Controlled Corruption Benchmark for Retrieval Augmented Systems",
        "summary": (
            "We propose a benchmark that injects controlled corruption into a clean corpus: "
            "dropped recent records, blanked abstracts, injected noise, truncated titles, "
            "backdated timestamps and duplicated rows. Each corruption is logged with the "
            "affected identifiers so that downstream metric changes remain attributable."
        ),
        "authors": ["Ngo Thanh Son", "Truong Thi Ha"],
        "categories": ["Machine Learning", "Software Engineering"],
        "published": date(2026, 4, 2),
    },
    {
        "paper_id": "10.5555/fixture.2026.0005",
        "title": "Repairing Corrupted Corpora from Immutable Raw Snapshots",
        "summary": (
            "Recovery is only possible when the raw ingestion snapshot is preserved before any "
            "transformation. We describe a repair procedure that replays cleaning from the raw "
            "snapshot rather than patching derived artifacts, and we show that stable document "
            "identifiers are the precondition for a fair before and after comparison."
        ),
        "authors": ["Phan Duc Long", "Ly Thi Thu", "Cao Minh Hieu"],
        "categories": ["Data Engineering", "Reproducibility"],
        "published": date(2026, 3, 11),
    },
    {
        "paper_id": "10.5555/fixture.2026.0006",
        "title": "Judge Models Versus Token Overlap for Evaluating Grounded Answers",
        "summary": (
            "Token overlap metrics reward surface similarity and penalise correct paraphrases. "
            "We compare token level F1 against a structured language model judge on grounded "
            "question answering, and report where the two disagree most, namely on answers that "
            "are factually correct but lexically distant from the reference."
        ),
        "authors": ["Dinh Thi Ngoc", "Ha Van Thang"],
        "categories": ["Natural Language Processing", "Evaluation"],
        "published": date(2026, 2, 19),
    },
]


def build_text_for_embedding(
    title: str,
    summary: str,
    authors_joined: str,
    categories_joined: str,
    published: str,
) -> str:
    """Cong thuc chuan cua CONTRACT.md muc 4.1 -- VT2 phai dung y het cai nay."""
    return (
        f"{title}\n\n"
        f"{summary}\n\n"
        f"Authors: {authors_joined}\n"
        f"Categories: {categories_joined}\n"
        f"Published: {published}"
    )


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in RAW_ROWS:
        published = raw["published"]
        authors_joined = "; ".join(raw["authors"])
        categories_joined = "; ".join(raw["categories"])
        published_iso = published.isoformat()
        rows.append(
            {
                "paper_id": raw["paper_id"],
                "title": raw["title"],
                "summary": raw["summary"],
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "primary_category": raw["categories"][0],
                "published": published_iso,
                "updated": published_iso,
                "abs_url": f"https://doi.org/{raw['paper_id']}",
                "pdf_url": "",
                "text_for_embedding": build_text_for_embedding(
                    raw["title"],
                    raw["summary"],
                    authors_joined,
                    categories_joined,
                    published_iso,
                ),
                "age_days": (RUN_DATE - published).days,
                "summary_chars": len(raw["summary"]),
            }
        )
    rows.sort(key=lambda row: row["published"], reverse=True)
    return rows


def main() -> None:
    rows = build_rows()
    out_dir = Path(__file__).resolve().parent

    csv_path = out_dir / "papers_clean_sample.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    json_path = out_dir / "papers_clean_sample.json"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(f"rows            : {len(rows)}")
    print(f"columns         : {len(FIELDNAMES)}")
    print(f"paper_id unique : {len({row['paper_id'] for row in rows}) == len(rows)}")
    print(f"age_days range  : {min(r['age_days'] for r in rows)}..{max(r['age_days'] for r in rows)} (nguong 180)")
    print(f"summary_chars   : {min(r['summary_chars'] for r in rows)}..{max(r['summary_chars'] for r in rows)}")
    print(f"wrote           : {csv_path.name}, {json_path.name}")


if __name__ == "__main__":
    main()
