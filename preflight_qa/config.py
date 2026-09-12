from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True, slots=True)
class Viewport:
    name: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PerformanceBudgets:
    ttfb_ms: int = 800
    fcp_ms: int = 1_800
    lcp_ms: int = 2_500
    cls: float = 0.1
    transfer_kb: int = 3_000
    request_count: int = 100

    def validate(self) -> None:
        if min(self.ttfb_ms, self.fcp_ms, self.lcp_ms, self.transfer_kb, self.request_count) <= 0:
            raise ValueError("performance budgets must be greater than zero")
        if self.cls <= 0:
            raise ValueError("performance budget cls must be greater than zero")


@dataclass(slots=True)
class ScanConfig:
    target: str
    max_pages: int = 20
    timeout_ms: int = 10_000
    headless: bool = True
    ignore_https_errors: bool = False
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_url_patterns: list[str] = field(default_factory=lambda: ["/logout", "/delete", "/remove", "/purchase"])
    viewports: list[Viewport] = field(
        default_factory=lambda: [Viewport("desktop", 1440, 900), Viewport("mobile", 390, 844)]
    )
    accessibility_tags: list[str] = field(default_factory=lambda: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    performance_budgets: PerformanceBudgets = field(default_factory=PerformanceBudgets)
    fail_on: str = "high"

    def validate(self) -> None:
        parsed = urlparse(self.target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("target must be an absolute http:// or https:// URL")
        if not 1 <= self.max_pages <= 500:
            raise ValueError("max_pages must be between 1 and 500")
        if not 1_000 <= self.timeout_ms <= 120_000:
            raise ValueError("timeout_ms must be between 1000 and 120000")
        if self.fail_on not in {"critical", "high", "medium", "low", "never"}:
            raise ValueError("fail_on must be critical, high, medium, low, or never")
        if not self.viewports:
            raise ValueError("at least one viewport is required")
        for viewport in self.viewports:
            if viewport.width < 240 or viewport.height < 240:
                raise ValueError(f"viewport {viewport.name!r} is too small")
        if not self.accessibility_tags or not all(
            isinstance(tag, str) and tag.strip() for tag in self.accessibility_tags
        ):
            raise ValueError("accessibility_tags must contain at least one non-empty tag")
        self.performance_budgets.validate()
        if not self.allowed_hosts:
            self.allowed_hosts = [parsed.hostname]


def load_config(path: Path | None, target_override: str | None = None) -> ScanConfig:
    raw: dict = {}
    if path:
        if not path.is_file():
            raise ValueError(f"configuration file not found: {path}")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError("configuration root must be a mapping")
        raw = loaded or {}

    target = target_override or raw.pop("target", None)
    if not target:
        raise ValueError("a target URL is required through --url or the configuration file")

    viewport_data = raw.pop("viewports", None)
    viewports = None
    if viewport_data is not None:
        try:
            viewports = [Viewport(**item) for item in viewport_data]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid viewport configuration: {exc}") from exc

    budget_data = raw.pop("performance_budgets", None)
    budgets = None
    if budget_data is not None:
        if not isinstance(budget_data, dict):
            raise ValueError("performance_budgets must be a mapping")
        try:
            budgets = PerformanceBudgets(**budget_data)
        except TypeError as exc:
            raise ValueError(f"invalid performance budget configuration: {exc}") from exc

    allowed_fields = {
        "max_pages",
        "timeout_ms",
        "headless",
        "ignore_https_errors",
        "allowed_hosts",
        "blocked_url_patterns",
        "accessibility_tags",
        "fail_on",
    }
    unknown = sorted(set(raw) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(unknown)}")

    config = ScanConfig(target=target, **raw)
    if viewports is not None:
        config.viewports = viewports
    if budgets is not None:
        config.performance_budgets = budgets
    config.validate()
    return config
