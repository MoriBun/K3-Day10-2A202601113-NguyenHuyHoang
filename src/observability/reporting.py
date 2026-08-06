from __future__ import annotations

from typing import Any

from core.utils import write_text


def _metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return "n/a" if value is None else str(value)


def _check_lines(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks", {})
    if not isinstance(checks, dict):
        return ["- No check detail was recorded."]
    return [
        f"- {'PASS' if check.get('passed') else 'FAIL'} — `{name}`: {check.get('observed')}"
        for name, check in checks.items()
        if isinstance(check, dict)
    ]

def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a concise markdown hand-off for the baseline run."""
    lines = [
        "# Phase 1 — Baseline Pipeline Report",
        "",
        "## Source and artifacts",
        "",
    ]
    for key, value in source_summary.items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.extend(
        [
            "",
            "## Retrieval and answer evaluation",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
    )
    for name in ("samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        lines.append(f"| {name} | {_metric(metrics.get(name))} |")
    lines.extend(["", f"Ragas: `{metrics.get('ragas', {})}`", "", "## Data quality", ""])
    lines.append(f"Overall status: **{'PASS' if quality.get('passed') else 'FAIL'}**")
    lines.extend(_check_lines(quality))
    lines.extend(
        [
            "",
            "## Freshness",
            "",
            f"- Status: **{'FRESH' if freshness.get('is_fresh') else 'STALE / INCOMPLETE'}**",
            f"- Latest publication: {freshness.get('latest_published') or 'n/a'}",
            f"- Oldest publication: {freshness.get('oldest_published') or 'n/a'}",
            f"- Stale rows: {freshness.get('stale_rows', 'n/a')} of {freshness.get('total_rows', 'n/a')}",
            "",
        ]
    )
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
    """Write a before/corrupted/repaired comparison report."""
    metric_names = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")
    lines = [
        "# Data Corruption and Repair Report",
        "",
        "## Evaluation comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted Δ | Repaired vs baseline Δ |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in metric_names:
        baseline = baseline_metrics.get(name)
        corrupted = corrupted_metrics.get(name)
        repaired = repaired_metrics.get(name)
        corrupted_delta = corrupted - baseline if isinstance(corrupted, (int, float)) and isinstance(baseline, (int, float)) else None
        repaired_delta = repaired - baseline if isinstance(repaired, (int, float)) and isinstance(baseline, (int, float)) else None
        lines.append(
            f"| {name} | {_metric(baseline)} | {_metric(corrupted)} | {_metric(repaired)} | "
            f"{_metric(corrupted_delta)} | {_metric(repaired_delta)} |"
        )
    lines.extend(
        [
            "",
            "## Data quality comparison",
            "",
            f"- Corrupted quality: **{'PASS' if corrupted_quality.get('passed') else 'FAIL'}**",
            *_check_lines(corrupted_quality),
            f"- Repaired quality: **{'PASS' if repaired_quality.get('passed') else 'FAIL'}**",
            *_check_lines(repaired_quality),
            "",
            "## Freshness comparison",
            "",
            f"| State | Fresh | Stale rows | Total rows | Latest published |",
            "| --- | --- | ---: | ---: | --- |",
            (
                f"| Corrupted | {corrupted_freshness.get('is_fresh')} | {corrupted_freshness.get('stale_rows')} | "
                f"{corrupted_freshness.get('total_rows')} | {corrupted_freshness.get('latest_published')} |"
            ),
            (
                f"| Repaired | {repaired_freshness.get('is_fresh')} | {repaired_freshness.get('stale_rows')} | "
                f"{repaired_freshness.get('total_rows')} | {repaired_freshness.get('latest_published')} |"
            ),
            "",
            "A useful repair run brings retrieval and answer metrics near the baseline while restoring quality and freshness checks.",
            "",
        ]
    )
    write_text(report_path, "\n".join(lines))
