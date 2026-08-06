"""Sinh report markdown tu artifact that.

Nguyen tac: report chi in lai so lieu duoc truyen vao tu metrics/quality/
freshness da ghi ra file. Khong tu tinh lai, khong to dep. Neu report va
artifact lech nhau thi bai bi tru diem (Rubric muc "Bao cao khong match
artifact thuc te").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.utils import write_text

_METRIC_LABELS = [
    ("retrieval_hit_rate", "Retrieval hit rate", "cao hon tot hon"),
    ("mean_token_f1", "Mean token F1", "cao hon tot hon"),
    ("judge_accuracy", "Judge accuracy", "cao hon tot hon"),
    ("mean_judge_score", "Mean judge score (1-5)", "cao hon tot hon"),
]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Report baseline cho CP3."""
    lines: list[str] = [
        "# Phase 1 — Baseline Report",
        "",
        f"_Sinh tu dong luc {datetime.now(UTC).isoformat()}_",
        "",
        "## 1. Nguon du lieu",
        "",
        "| Muc | Gia tri |",
        "| --- | --- |",
        f"| Source API | {source_summary.get('source_api')} |",
        f"| Che do nap | `{source_summary.get('source_mode')}` |",
        f"| Query | `{source_summary.get('query')}` |",
        f"| Filter | `{source_summary.get('filter')}` |",
        f"| max_results / top_k | {source_summary.get('max_results')} / {source_summary.get('top_k')} |",
        f"| Embedding model | `{source_summary.get('embedding_model')}` |",
        f"| LLM judge | `{source_summary.get('llm_provider')}` / `{source_summary.get('llm_model')}` |",
        f"| Raw records | {source_summary.get('raw_records')} |",
        f"| Clean rows | {source_summary.get('clean_rows')} |",
        "",
    ]

    stats = source_summary.get("clean_stats") or {}
    if stats:
        lines += [
            "### Truy vet record bi loai khi cleaning",
            "",
            "| Ly do | So dong |",
            "| --- | --: |",
        ]
        for key in (
            "raw_count",
            "dropped_duplicate",
            "dropped_no_paper_id",
            "dropped_no_title",
            "dropped_short_summary",
            "dropped_bad_published",
            "clean_count",
        ):
            if key in stats:
                lines.append(f"| `{key}` | {stats[key]} |")
        lines += [
            "",
            "> Cac con so `dropped_*` co the chong lan nhau khi mot dong hong nhieu tieu chi.",
            "",
        ]

    lines += [
        "## 2. Ket qua evaluation",
        "",
        f"So sample: **{metrics.get('samples')}**",
        "",
        "| Metric | Gia tri |",
        "| --- | --: |",
    ]
    for key, label, _ in _METRIC_LABELS:
        lines.append(f"| {label} | {_fmt(metrics.get(key))} |")
    lines.append("")

    ragas = metrics.get("ragas")
    if isinstance(ragas, dict):
        if "skipped" in ragas:
            lines += [f"> Ragas: {ragas['skipped']}", ""]
        elif "error" in ragas:
            lines += [f"> Ragas loi: {ragas['error']}", ""]
        else:
            lines += ["### Ragas", "", "| Metric | Gia tri |", "| --- | --: |"]
            for key, value in ragas.items():
                lines.append(f"| {key} | {_fmt(value)} |")
            lines.append("")

    lines += _quality_section(quality)
    lines += _freshness_section(freshness)

    lines += [
        "## 5. Ket luan baseline",
        "",
        _baseline_verdict(metrics, quality, freshness),
        "",
        "> Baseline chi duoc coi la hoan tat khi artifact, metrics va report khop nhau,",
        "> khong phai khi script chay xong khong loi.",
        "",
    ]

    write_text(report_path, "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Report so sanh baseline / corrupted / repaired cho CP6."""
    lines: list[str] = [
        "# Corruption Impact & Recovery Report",
        "",
        f"_Sinh tu dong luc {datetime.now(UTC).isoformat()}_",
        "",
        "Ba trang thai duoc danh gia tren **cung mot test set**, cung evaluator va cung `top_k`.",
        "",
        "## 1. So sanh metrics",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Δ corrupt | Δ repair |",
        "| --- | --: | --: | --: | --: | --: |",
    ]

    for key, label, _ in _METRIC_LABELS:
        base = baseline_metrics.get(key)
        corrupt = corrupted_metrics.get(key)
        repair = repaired_metrics.get(key)
        lines.append(
            f"| {label} | {_fmt(base)} | {_fmt(corrupt)} | {_fmt(repair)} "
            f"| {_delta(base, corrupt)} | {_delta(corrupt, repair)} |"
        )

    lines += [
        "",
        "- **Δ corrupt** = corrupted − baseline. Am nghia la data xau lam giam chat luong.",
        "- **Δ repair** = repaired − corrupted. Duong nghia la repair da phuc hoi.",
        "",
        "## 2. Data quality",
        "",
        "| Trang thai | Check pass | Tong check | Ket qua |",
        "| --- | --: | --: | --- |",
        _quality_row("Corrupted", corrupted_quality),
        _quality_row("Repaired", repaired_quality),
        "",
        "### Check that bai sau corruption",
        "",
    ]
    failed = [c for c in (corrupted_quality.get("checks") or []) if not c.get("success")]
    if failed:
        lines += ["| Check | Quan sat | Sample paper_id |", "| --- | --- | --- |"]
        for check in failed:
            sample = ", ".join(f"`{i}`" for i in (check.get("sample_failed_paper_ids") or [])[:3]) or "—"
            lines.append(f"| `{check.get('name')}` | {check.get('observed')} | {sample} |")
    else:
        lines.append("Khong check nao that bai — corruption chua du manh de tao tin hieu quality.")
    lines.append("")

    lines += [
        "## 3. Freshness",
        "",
        "| Trang thai | Stale rows | Tong rows | Moi nhat | is_fresh |",
        "| --- | --: | --: | --- | --- |",
        _freshness_row("Corrupted", corrupted_freshness),
        _freshness_row("Repaired", repaired_freshness),
        "",
        "## 4. Ket luan",
        "",
        _recovery_verdict(baseline_metrics, corrupted_metrics, repaired_metrics),
        "",
        "> Chi ket luan da phuc hoi khi so lieu chung minh. Neu metric hoac quality signal",
        "> van xau thi phai ghi ro la recovery chua hoan toan.",
        "",
    ]

    write_text(report_path, "\n".join(lines))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "co" if value else "khong"
    if isinstance(value, (int, float)):
        return f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    return str(value)


def _delta(before: Any, after: Any) -> str:
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return "—"
    diff = float(after) - float(before)
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.4f}".rstrip("0").rstrip(".")


def _quality_section(quality: dict[str, Any]) -> list[str]:
    lines = [
        "## 3. Data quality",
        "",
        f"**{quality.get('checks_passed')}/{quality.get('checks_total')}** check pass "
        f"tren {quality.get('total_rows')} dong.",
        "",
        "| Check | Ket qua | Ky vong | Quan sat |",
        "| --- | --- | --- | --- |",
    ]
    for check in quality.get("checks") or []:
        mark = "PASS" if check.get("success") else "**FAIL**"
        lines.append(f"| `{check.get('name')}` | {mark} | {check.get('expected')} | {check.get('observed')} |")
    lines.append("")
    return lines


def _freshness_section(freshness: dict[str, Any]) -> list[str]:
    return [
        "## 4. Freshness",
        "",
        "| Muc | Gia tri |",
        "| --- | --- |",
        f"| Nguong | {freshness.get('threshold_days')} ngay |",
        f"| Moi nhat | {freshness.get('latest_published')} |",
        f"| Cu nhat | {freshness.get('oldest_published')} |",
        f"| Tuoi trung binh | {freshness.get('mean_age_days')} ngay |",
        f"| Stale rows | {freshness.get('stale_rows')} / {freshness.get('total_rows')} |",
        f"| is_fresh | {_fmt(freshness.get('is_fresh'))} |",
        "",
    ]


def _quality_row(label: str, quality: dict[str, Any]) -> str:
    verdict = "PASS" if quality.get("success") else "**FAIL**"
    return f"| {label} | {quality.get('checks_passed')} | {quality.get('checks_total')} | {verdict} |"


def _freshness_row(label: str, freshness: dict[str, Any]) -> str:
    return (
        f"| {label} | {freshness.get('stale_rows')} | {freshness.get('total_rows')} "
        f"| {freshness.get('latest_published')} | {_fmt(freshness.get('is_fresh'))} |"
    )


def _baseline_verdict(metrics: dict[str, Any], quality: dict[str, Any], freshness: dict[str, Any]) -> str:
    parts = []
    hit_rate = metrics.get("retrieval_hit_rate")
    if isinstance(hit_rate, (int, float)):
        parts.append(f"Retrieval hit rate baseline dat **{_fmt(hit_rate)}** tren {metrics.get('samples')} cau hoi.")
    parts.append(
        "Data quality **pass toan bo**." if quality.get("success")
        else f"Data quality con **{quality.get('checks_failed')} check that bai** — can xu ly truoc khi chay corruption."
    )
    parts.append(
        "Du lieu **con moi**, khong co dong nao qua han." if freshness.get("is_fresh")
        else f"Co **{freshness.get('stale_rows')} dong qua han** nguong {freshness.get('threshold_days')} ngay."
    )
    return " ".join(parts)


def _recovery_verdict(
    baseline: dict[str, Any], corrupted: dict[str, Any], repaired: dict[str, Any]
) -> str:
    degraded: list[str] = []
    recovered: list[str] = []
    incomplete: list[str] = []

    for key, label, _ in _METRIC_LABELS:
        base, corrupt, repair = baseline.get(key), corrupted.get(key), repaired.get(key)
        if not all(isinstance(v, (int, float)) for v in (base, corrupt, repair)):
            continue
        if corrupt < base:
            degraded.append(label)
        if repair > corrupt:
            recovered.append(label)
        if repair < base - 1e-9:
            incomplete.append(label)

    if not degraded:
        return (
            "Khong metric nao giam sau corruption. Corruption chua cham vao cac paper "
            "co trong test set, hoac cuong do con qua nhe — can tang ty le corruption "
            "roi chay lai truoc khi ket luan."
        )

    sentences = [f"Corruption lam giam: **{', '.join(degraded)}**."]
    if recovered:
        sentences.append(f"Repair phuc hoi duoc: **{', '.join(recovered)}**.")
    else:
        sentences.append("Repair **chua** phuc hoi duoc metric nao.")
    if incomplete:
        sentences.append(f"Chua ve lai muc baseline: **{', '.join(incomplete)}** — recovery chua hoan toan.")
    else:
        sentences.append("Tat ca metric da ve lai muc baseline.")
    return " ".join(sentences)
