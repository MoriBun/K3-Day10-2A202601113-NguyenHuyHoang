from __future__ import annotations

from typing import Any

from retrieval.index import LocalEmbeddingIndex


def build_smoke_plan(index: LocalEmbeddingIndex, top_n: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Create deterministic semantic-search and exact-lookup checks for an index.

    The returned plan is intentionally data-only so a pipeline can save it before
    running checks against the just-built collection.
    """
    if top_n < 1:
        raise ValueError("top_n must be at least 1.")

    selected_documents = index.documents[:top_n]
    queries = [
        {
            "query": f"What is the paper '{document['title']}' about?",
            "expected_paper_id": document["paper_id"],
        }
        for document in selected_documents
    ]
    lookups = [
        {
            "value": value,
            "expected_paper_id": document["paper_id"],
        }
        for document in selected_documents
        for value in (document["paper_id"], document["title"])
    ]
    return {"queries": queries, "lookups": lookups}
