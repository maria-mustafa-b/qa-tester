from __future__ import annotations

from typing import Any

from preflight_qa.models import Category, Confidence, Finding, Severity


def run_visual_checks(snapshot: dict[str, Any], url: str, viewport: str) -> list[Finding]:
    findings: list[Finding] = []
    overflow = int(snapshot.get("horizontal_overflow", 0))
    if overflow > 1:
        findings.append(
            Finding(
                rule_id="visual.horizontal-overflow",
                title="Page overflows horizontally",
                category=Category.VISUAL,
                severity=Severity.MEDIUM,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description=f"Rendered content is {overflow}px wider than the viewport.",
                evidence={"overflow_pixels": overflow},
                recommendation="Fix fixed-width or positioned elements that exceed the viewport.",
            )
        )

    for item in snapshot.get("overflowing_elements", [])[:20]:
        findings.append(
            Finding(
                rule_id="visual.element-outside-viewport",
                title="Element extends outside the viewport",
                category=Category.VISUAL,
                severity=Severity.LOW,
                confidence=Confidence.LIKELY,
                url=url,
                viewport=viewport,
                description="A visible element extends beyond the horizontal viewport boundary.",
                evidence={"element": item.get("selector"), "right": item.get("right")},
                recommendation="Review responsive sizing, margins and absolute positioning.",
            )
        )
    return findings
