from __future__ import annotations

from typing import Any

from preflight_qa.models import Category, Confidence, Finding, Severity

PLACEHOLDER_TERMS = (
    "lorem ipsum",
    "todo:",
    "replace me",
    "sample text",
    "[object object]",
)


def run_content_checks(snapshot: dict[str, Any], url: str, viewport: str) -> list[Finding]:
    findings: list[Finding] = []
    title = str(snapshot.get("title", "")).strip()
    lang = str(snapshot.get("lang", "")).strip()

    if not title:
        findings.append(
            Finding(
                rule_id="content.missing-title",
                title="Page has no document title",
                category=Category.CONTENT,
                severity=Severity.MEDIUM,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description="The page does not provide a non-empty <title> element.",
                recommendation="Add a concise, unique title that describes the page.",
            )
        )
    if not lang:
        findings.append(
            Finding(
                rule_id="content.missing-language",
                title="Page language is not declared",
                category=Category.ACCESSIBILITY,
                severity=Severity.LOW,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description="The root HTML element has no lang attribute.",
                recommendation="Set the HTML lang attribute to the page's primary language.",
            )
        )

    for image in snapshot.get("images", []):
        if not image.get("alt_present"):
            findings.append(
                Finding(
                    rule_id="content.image-missing-alt",
                    title="Image is missing alternative text",
                    category=Category.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    url=url,
                    viewport=viewport,
                    description="An image has no alt attribute.",
                    evidence={"element": image.get("selector"), "source": image.get("src")},
                    recommendation="Add meaningful alt text, or alt=\"\" if the image is decorative.",
                )
            )
        if image.get("complete") and image.get("natural_width") == 0:
            findings.append(
                Finding(
                    rule_id="functional.broken-image",
                    title="Image failed to load",
                    category=Category.FUNCTIONAL,
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    url=url,
                    viewport=viewport,
                    description="The browser completed the image request but decoded no image pixels.",
                    evidence={"element": image.get("selector"), "source": image.get("src")},
                    recommendation="Correct the image URL or ensure the asset is deployed.",
                )
            )

    for element in snapshot.get("empty_interactives", []):
        findings.append(
            Finding(
                rule_id="content.empty-interactive-name",
                title="Interactive element has no accessible name",
                category=Category.ACCESSIBILITY,
                severity=Severity.MEDIUM,
                confidence=Confidence.LIKELY,
                url=url,
                viewport=viewport,
                description="A link or button contains no visible text or accessible label.",
                evidence={"element": element},
                recommendation="Give the control clear text or an appropriate accessible label.",
            )
        )

    body_text = str(snapshot.get("body_text", "")).lower()
    for term in PLACEHOLDER_TERMS:
        if term in body_text:
            findings.append(
                Finding(
                    rule_id="content.placeholder-text",
                    title="Placeholder or development text is visible",
                    category=Category.CONTENT,
                    severity=Severity.LOW,
                    confidence=Confidence.LIKELY,
                    url=url,
                    viewport=viewport,
                    description=f"The rendered page contains the text {term!r}.",
                    evidence={"matched_text": term},
                    recommendation="Replace development copy with reviewed production content.",
                )
            )
    return findings

