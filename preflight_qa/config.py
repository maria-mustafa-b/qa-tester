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


@dataclass(slots=True)
class ScanConfig:
    target: str
    max_pages: int = 20
    timeout_ms: int = 10_000
    headless: bool = True
    ignore_https_errors: bool = False
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_url_patterns: list[str] = field(
        default_factory=lambda: ["/logout", "/delete", "/remove", "/purchase"]
    )
    viewports: list[Viewport] = field(
        default_factory=lambda: [Viewport("desktop", 1440, 900), Viewport("mobile", 390, 844)]
    )
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

    allowed_fields = {
        "max_pages",
        "timeout_ms",
        "headless",
        "ignore_https_errors",
        "allowed_hosts",
        "blocked_url_patterns",
        "fail_on",
    }
    unknown = sorted(set(raw) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(unknown)}")

    config = ScanConfig(target=target, **raw)
    if viewports is not None:
        config.viewports = viewports
    config.validate()
    return config

