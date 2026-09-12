from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Any

from playwright.async_api import Page

from preflight_qa.models import Category, Confidence, Finding, Severity

IMPACT_SEVERITY = {
    "critical": Severity.CRITICAL,
    "serious": Severity.HIGH,
    "moderate": Severity.MEDIUM,
    "minor": Severity.LOW,
    None: Severity.INFO,
}


@lru_cache(maxsize=1)
def _axe_source() -> str:
    return files("preflight_qa").joinpath("vendor/axe.min.js").read_text(encoding="utf-8")


async def run_accessibility_checks(page: Page, url: str, viewport: str, tags: list[str]) -> list[Finding]:
    await page.evaluate(_axe_source())
    result = await page.evaluate(
        """
        async (tags) => await axe.run(document, {
          runOnly: { type: 'tag', values: tags },
          resultTypes: ['violations']
        })
        """,
        tags,
    )
    return findings_from_axe(result, url, viewport)


def findings_from_axe(result: dict[str, Any], url: str, viewport: str) -> list[Finding]:
    findings: list[Finding] = []
    for violation in result.get("violations", []):
        impact = violation.get("impact")
        nodes = violation.get("nodes", [])
        evidence_nodes = [
            {
                "target": node.get("target", [])[:5],
                "failure_summary": str(node.get("failureSummary", ""))[:1_000],
                "html": str(node.get("html", ""))[:500],
            }
            for node in nodes[:20]
        ]
        findings.append(
            Finding(
                rule_id=f"accessibility.axe.{violation.get('id', 'unknown')}",
                title=str(violation.get("help") or "Accessibility rule failed"),
                category=Category.ACCESSIBILITY,
                severity=IMPACT_SEVERITY.get(impact, Severity.INFO),
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description=str(violation.get("description") or "An axe-core rule failed."),
                evidence={
                    "axe_rule": violation.get("id"),
                    "impact": impact,
                    "help_url": violation.get("helpUrl"),
                    "tags": violation.get("tags", []),
                    "node_count": len(nodes),
                    "nodes": evidence_nodes,
                },
                recommendation=(
                    f"Fix the affected elements and review {violation.get('helpUrl', 'the axe rule guidance')}."
                ),
            )
        )
    return findings
