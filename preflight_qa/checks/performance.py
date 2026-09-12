from __future__ import annotations

from typing import Any

from preflight_qa.config import PerformanceBudgets
from preflight_qa.models import Category, Confidence, Finding, Severity


def run_performance_checks(
    metrics: dict[str, Any], url: str, viewport: str, budgets: PerformanceBudgets
) -> list[Finding]:
    checks = (
        ("ttfb_ms", budgets.ttfb_ms, "Time to first byte", "Reduce server, network and redirect latency."),
        (
            "fcp_ms",
            budgets.fcp_ms,
            "First Contentful Paint",
            "Reduce render-blocking work and prioritize above-the-fold content.",
        ),
        (
            "lcp_ms",
            budgets.lcp_ms,
            "Largest Contentful Paint",
            "Optimize the largest visible element and its critical request path.",
        ),
        (
            "cls",
            budgets.cls,
            "Cumulative Layout Shift",
            "Reserve layout space and avoid inserting content above rendered elements.",
        ),
        (
            "transfer_kb",
            budgets.transfer_kb,
            "Transferred page weight",
            "Compress, cache and remove unnecessary page resources.",
        ),
        (
            "request_count",
            budgets.request_count,
            "Network request count",
            "Bundle or defer non-critical resources and remove unused requests.",
        ),
    )
    findings: list[Finding] = []
    for key, budget, label, recommendation in checks:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or value <= budget:
            continue
        ratio = value / budget
        findings.append(
            Finding(
                rule_id=f"performance.budget.{key}",
                title=f"{label} exceeds its budget",
                category=Category.PERFORMANCE,
                severity=Severity.MEDIUM if ratio >= 2 else Severity.LOW,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description=f"Measured {label.lower()} is above the configured pre-release budget.",
                evidence={"metric": key, "value": round(value, 2), "budget": budget},
                recommendation=recommendation,
            )
        )
    return findings
