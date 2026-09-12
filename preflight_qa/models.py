from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Category(StrEnum):
    FUNCTIONAL = "functional"
    VISUAL = "visual"
    CONTENT = "content"
    PERFORMANCE = "performance"
    CRASH = "crash"
    ACCESSIBILITY = "accessibility"
    SECURITY = "security"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"


@dataclass(slots=True)
class Finding:
    rule_id: str
    title: str
    category: Category
    severity: Severity
    confidence: Confidence
    url: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    viewport: str | None = None

    def fingerprint(self) -> tuple[str, str, str | None, str]:
        return (self.rule_id, self.url, self.viewport, str(self.evidence.get("element", "")))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["severity"] = self.severity.value
        data["confidence"] = self.confidence.value
        return data


@dataclass(slots=True)
class PageResult:
    url: str
    final_url: str
    title: str
    status: int | None
    duration_ms: int
    viewport: str
    screenshot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanReport:
    target: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    pages: list[PageResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    skipped_urls: list[dict[str, str]] = field(default_factory=list)
    scanner_errors: list[dict[str, str]] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(UTC).isoformat()

    def add_finding(self, finding: Finding) -> None:
        fingerprints = {existing.fingerprint() for existing in self.findings}
        if finding.fingerprint() not in fingerprints:
            self.findings.append(finding)

    def to_dict(self) -> dict[str, Any]:
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        findings = sorted(
            self.findings,
            key=lambda item: (severity_order[item.severity], item.category.value, item.url),
        )
        counts: dict[str, int] = {severity.value: 0 for severity in Severity}
        for finding in findings:
            counts[finding.severity.value] += 1
        return {
            "schema_version": "1.0",
            "scanner": {"name": "Preflight QA", "version": __import__("preflight_qa").__version__},
            "target": self.target,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {
                "pages_tested": len(self.pages),
                "findings": len(findings),
                "by_severity": counts,
                "scanner_errors": len(self.scanner_errors),
            },
            "pages": [page.to_dict() for page in self.pages],
            "findings": [finding.to_dict() for finding in findings],
            "skipped_urls": self.skipped_urls,
            "scanner_errors": self.scanner_errors,
        }

