"""Markdown reports built only from pipeline artifacts."""

from __future__ import annotations

from typing import Any

from core.utils import write_text

_METRICS = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _judge_status(metrics: dict[str, Any]) -> str:
    mode = metrics.get("judge_mode", "unknown")
    fallback = metrics.get("judge_fallback_count", "n/a")
    return "LLM judge used for every sample." if mode == "llm" else f"{mode}; fallback used for {fallback} sample(s)."


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    lines = [
        f"Quality: **{'PASS' if quality.get('success') else 'FAIL'}** "
        f"({quality.get('checks_passed')}/{quality.get('checks_total')} checks).",
        "",
        "| Check | Status | Expected | Observed |",
        "| --- | --- | --- | --- |",
    ]
    for check in quality.get("checks", []):
        lines.append(
            f"| `{check.get('name')}` | {'PASS' if check.get('success') else 'FAIL'} | "
            f"{check.get('expected')} | {check.get('observed')} |"
        )
    return lines


def generate_phase1_report(report_path, source_summary: dict[str, Any], metrics: dict[str, Any], quality: dict[str, Any], freshness: dict[str, Any]) -> None:
    lines = ["# Phase 1 — Baseline Pipeline Report", "", "## Source and artifacts", ""]
    for key, value in source_summary.items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines += ["", "## Evaluation", "", "| Metric | Value |", "| --- | ---: |"]
    for key in ("samples", *_METRICS):
        lines.append(f"| {key} | {_fmt(metrics.get(key))} |")
    lines += ["", f"- Judge evaluator: {_judge_status(metrics)}", f"- Ragas: `{metrics.get('ragas', {})}`", "", "## Data quality", ""]
    lines += _quality_lines(quality)
    lines += [
        "",
        "## Freshness",
        "",
        f"- Status: **{'FRESH' if freshness.get('is_fresh') else 'STALE / INCOMPLETE'}**",
        f"- Latest publication: {freshness.get('latest_published') or 'n/a'}",
        f"- Oldest publication: {freshness.get('oldest_published') or 'n/a'}",
        f"- Stale rows: {freshness.get('stale_rows', 'n/a')} of {freshness.get('total_rows', 'n/a')}",
        "",
    ]
    write_text(report_path, "\n".join(lines))


def generate_corruption_report(report_path, baseline_metrics: dict[str, Any], corrupted_metrics: dict[str, Any], repaired_metrics: dict[str, Any], corrupted_quality: dict[str, Any], repaired_quality: dict[str, Any], corrupted_freshness: dict[str, Any], repaired_freshness: dict[str, Any]) -> None:
    lines = [
        "# Data Corruption and Repair Report",
        "",
        "## Evaluation comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted Δ | Repaired vs baseline Δ |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in _METRICS:
        baseline, corrupted, repaired = (baseline_metrics.get(key), corrupted_metrics.get(key), repaired_metrics.get(key))
        corrupt_delta = corrupted - baseline if isinstance(baseline, (int, float)) and isinstance(corrupted, (int, float)) else None
        repair_delta = repaired - baseline if isinstance(baseline, (int, float)) and isinstance(repaired, (int, float)) else None
        lines.append(f"| {key} | {_fmt(baseline)} | {_fmt(corrupted)} | {_fmt(repaired)} | {_fmt(corrupt_delta)} | {_fmt(repair_delta)} |")
    lines += [
        "",
        "## Evaluation provenance",
        "",
        f"- Baseline judge: {_judge_status(baseline_metrics)}",
        f"- Corrupted judge: {_judge_status(corrupted_metrics)}",
        f"- Repaired judge: {_judge_status(repaired_metrics)}",
        "",
        "## Data quality comparison",
        "",
        f"- Corrupted: **{'PASS' if corrupted_quality.get('success') else 'FAIL'}** ({corrupted_quality.get('checks_passed')}/{corrupted_quality.get('checks_total')})",
        f"- Repaired: **{'PASS' if repaired_quality.get('success') else 'FAIL'}** ({repaired_quality.get('checks_passed')}/{repaired_quality.get('checks_total')})",
        "",
        "### Failed corrupted checks",
        "",
    ]
    for check in (check for check in corrupted_quality.get("checks", []) if not check.get("success")):
        lines.append(f"- `{check.get('name')}`: {check.get('observed')}")
    lines += [
        "",
        "## Freshness comparison",
        "",
        "| State | Fresh | Stale rows | Total rows | Latest published |",
        "| --- | --- | ---: | ---: | --- |",
        f"| Corrupted | {corrupted_freshness.get('is_fresh')} | {corrupted_freshness.get('stale_rows')} | {corrupted_freshness.get('total_rows')} | {corrupted_freshness.get('latest_published')} |",
        f"| Repaired | {repaired_freshness.get('is_fresh')} | {repaired_freshness.get('stale_rows')} | {repaired_freshness.get('total_rows')} | {repaired_freshness.get('latest_published')} |",
        "",
    ]
    write_text(report_path, "\n".join(lines))
