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


@dataclass(frozen=True, slots=True)
class VisualRegressionConfig:
    enabled: bool = False
    baseline_dir: str = "visual-baselines"
    update_baselines: bool = False
    max_changed_pixel_ratio: float = 0.01
    pixel_threshold: int = 25

    def validate(self) -> None:
        if not self.baseline_dir.strip() or self.baseline_dir.strip() in {".", "/"}:
            raise ValueError("visual_regression baseline_dir must be a specific directory")
        if not 0 <= self.max_changed_pixel_ratio <= 1:
            raise ValueError("visual_regression max_changed_pixel_ratio must be between 0 and 1")
        if not 0 <= self.pixel_threshold <= 255:
            raise ValueError("visual_regression pixel_threshold must be between 0 and 255")
        if self.update_baselines and not self.enabled:
            raise ValueError("visual_regression must be enabled when update_baselines is true")


FLOW_ACTIONS = {
    "goto",
    "click",
    "fill",
    "select",
    "check",
    "assert_visible",
    "assert_text",
    "assert_url",
}
SELECTOR_ACTIONS = {"click", "fill", "select", "check", "assert_visible", "assert_text"}
VALUE_ACTIONS = {"goto", "fill", "select", "assert_text", "assert_url"}


@dataclass(frozen=True, slots=True)
class FlowStep:
    action: str
    selector: str | None = None
    value: str | None = None
    value_from_env: str | None = None
    timeout_ms: int | None = None

    def validate(self, flow_name: str, index: int) -> None:
        label = f"flow {flow_name!r} step {index}"
        if self.action not in FLOW_ACTIONS:
            raise ValueError(f"{label} uses unsupported action {self.action!r}")
        if self.action in SELECTOR_ACTIONS and not self.selector:
            raise ValueError(f"{label} requires selector")
        has_value = self.value is not None or self.value_from_env is not None
        if self.action in VALUE_ACTIONS and not has_value:
            raise ValueError(f"{label} requires value or value_from_env")
        if self.value is not None and self.value_from_env is not None:
            raise ValueError(f"{label} cannot set both value and value_from_env")
        if self.value_from_env is not None and self.action not in {"fill", "select"}:
            raise ValueError(f"{label} only supports value_from_env for fill or select")
        if self.timeout_ms is not None and not 100 <= self.timeout_ms <= 120_000:
            raise ValueError(f"{label} timeout_ms must be between 100 and 120000")


@dataclass(frozen=True, slots=True)
class SmokeFlow:
    name: str
    start_path: str = "/"
    viewport: str = "desktop"
    allow_submit: bool = False
    steps: tuple[FlowStep, ...] = ()

    def validate(self, viewport_names: set[str]) -> None:
        if not self.name.strip():
            raise ValueError("flow name cannot be empty")
        if self.viewport not in viewport_names:
            raise ValueError(f"flow {self.name!r} references unknown viewport {self.viewport!r}")
        if not self.steps:
            raise ValueError(f"flow {self.name!r} must contain at least one step")
        for index, step in enumerate(self.steps, start=1):
            step.validate(self.name, index)


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
    visual_regression: VisualRegressionConfig = field(default_factory=VisualRegressionConfig)
    flows: list[SmokeFlow] = field(default_factory=list)
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
        self.visual_regression.validate()
        viewport_names = {viewport.name for viewport in self.viewports}
        if len(viewport_names) != len(self.viewports):
            raise ValueError("viewport names must be unique")
        flow_names = {flow.name for flow in self.flows}
        if len(flow_names) != len(self.flows):
            raise ValueError("flow names must be unique")
        for flow in self.flows:
            flow.validate(viewport_names)
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

    visual_data = raw.pop("visual_regression", None)
    visual_regression = None
    if visual_data is not None:
        if not isinstance(visual_data, dict):
            raise ValueError("visual_regression must be a mapping")
        try:
            visual_regression = VisualRegressionConfig(**visual_data)
        except TypeError as exc:
            raise ValueError(f"invalid visual regression configuration: {exc}") from exc

    flow_data = raw.pop("flows", None)
    flows: list[SmokeFlow] = []
    if flow_data is not None:
        if not isinstance(flow_data, list):
            raise ValueError("flows must be a list")
        try:
            for item in flow_data:
                if not isinstance(item, dict):
                    raise TypeError("each flow must be a mapping")
                item = dict(item)
                step_data = item.pop("steps", [])
                if not isinstance(step_data, list):
                    raise TypeError("flow steps must be a list")
                steps = tuple(FlowStep(**step) for step in step_data)
                flows.append(SmokeFlow(steps=steps, **item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid flow configuration: {exc}") from exc

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
    if visual_regression is not None:
        config.visual_regression = visual_regression
    config.flows = flows
    config.validate()
    return config
