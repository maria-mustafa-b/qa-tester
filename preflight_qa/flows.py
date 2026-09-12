from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import Browser, Locator, Page

from preflight_qa.config import FlowStep, ScanConfig, SmokeFlow, Viewport
from preflight_qa.models import Category, Confidence, Finding, FlowResult, FlowStepResult, Severity
from preflight_qa.urls import normalize_url, url_is_allowed

SUBMIT_TYPES = {"submit", "image"}
SUBMIT_WORDS = re.compile(r"\b(submit|sign[ -]?in|log[ -]?in|register|checkout|pay|purchase|delete|remove)\b", re.I)


class FlowSafetyError(RuntimeError):
    """Raised when a configured flow attempts an action outside its declared safety scope."""


async def run_smoke_flows(
    browser: Browser, config: ScanConfig, output_dir: Path
) -> tuple[list[FlowResult], list[Finding]]:
    results: list[FlowResult] = []
    findings: list[Finding] = []
    for flow in config.flows:
        viewport = next(item for item in config.viewports if item.name == flow.viewport)
        result, finding = await _run_flow(browser, config, flow, viewport, output_dir)
        results.append(result)
        if finding:
            findings.append(finding)
    return results, findings


async def _run_flow(
    browser: Browser,
    config: ScanConfig,
    flow: SmokeFlow,
    viewport: Viewport,
    output_dir: Path,
) -> tuple[FlowResult, Finding | None]:
    context = await browser.new_context(
        viewport={"width": viewport.width, "height": viewport.height},
        ignore_https_errors=config.ignore_https_errors,
    )
    page = await context.new_page()
    start_url = config.target
    started = time.perf_counter()
    step_results: list[FlowStepResult] = []
    secrets: list[str] = []
    try:
        try:
            start_url = _safe_url(config, flow.start_path)
            await page.goto(start_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        except Exception as exc:
            screenshot = await _flow_screenshot(page, output_dir, flow.name, 0)
            error = redact_values(str(exc), secrets)
            step = FlowStep(action="goto", value=flow.start_path)
            result = FlowResult(
                flow.name,
                flow.viewport,
                start_url,
                redact_values(page.url, secrets),
                "failed",
                round((time.perf_counter() - started) * 1000),
                [FlowStepResult(0, "goto", "failed", 0, error, screenshot)],
            )
            return result, _failure_finding(flow, redact_values(page.url, secrets), 0, step, error, screenshot)
        for index, step in enumerate(flow.steps, start=1):
            step_started = time.perf_counter()
            try:
                value = _step_value(step)
                if step.action in {"fill", "select"} and value:
                    secrets.append(value)
                await _run_step(page, config, flow, step, value)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - step_started) * 1000)
                screenshot = await _flow_screenshot(page, output_dir, flow.name, index)
                error = redact_values(str(exc), secrets)
                step_results.append(FlowStepResult(index, step.action, "failed", duration_ms, error, screenshot))
                result = FlowResult(
                    flow.name,
                    flow.viewport,
                    start_url,
                    redact_values(page.url, secrets),
                    "failed",
                    round((time.perf_counter() - started) * 1000),
                    step_results,
                )
                return result, _failure_finding(flow, redact_values(page.url, secrets), index, step, error, screenshot)
            step_results.append(
                FlowStepResult(
                    index,
                    step.action,
                    "passed",
                    round((time.perf_counter() - step_started) * 1000),
                )
            )
        return (
            FlowResult(
                flow.name,
                flow.viewport,
                start_url,
                redact_values(page.url, secrets),
                "passed",
                round((time.perf_counter() - started) * 1000),
                step_results,
            ),
            None,
        )
    finally:
        await context.close()


async def _run_step(page: Page, config: ScanConfig, flow: SmokeFlow, step: FlowStep, value: str | None) -> None:
    timeout = step.timeout_ms or config.timeout_ms
    if step.action == "goto":
        await page.goto(_safe_url(config, value or ""), wait_until="domcontentloaded", timeout=timeout)
        return
    if step.action == "assert_url":
        expected = _safe_url(config, value or "")
        await page.wait_for_url(expected, timeout=timeout)
        return

    locator = page.locator(step.selector or "").first
    if step.action == "click":
        await _guard_click(locator, config, flow.allow_submit)
        await locator.click(timeout=timeout)
    elif step.action == "fill":
        await locator.fill(value or "", timeout=timeout)
    elif step.action == "select":
        await locator.select_option(value or "", timeout=timeout)
    elif step.action == "check":
        await locator.check(timeout=timeout)
    elif step.action == "assert_visible":
        await locator.wait_for(state="visible", timeout=timeout)
    elif step.action == "assert_text":
        await locator.filter(has_text=value or "").wait_for(state="visible", timeout=timeout)
    _safe_url(config, page.url)


async def _guard_click(locator: Locator, config: ScanConfig, allow_submit: bool) -> None:
    metadata = await locator.evaluate(
        """
        element => ({
          tag: element.tagName.toLowerCase(),
          type: (element.getAttribute('type') || '').toLowerCase(),
          text: (element.innerText || element.getAttribute('aria-label') || '').trim().slice(0, 100),
          href: element.href || '',
          formAction: element.formAction || ''
        })
        """
    )
    if metadata["href"]:
        _safe_url(config, metadata["href"])
    if metadata["formAction"]:
        _safe_url(config, metadata["formAction"])
    if click_requires_submit_permission(metadata) and not allow_submit:
        raise FlowSafetyError("submit-like click blocked; set allow_submit: true for this authorized flow")


def click_requires_submit_permission(metadata: dict[str, str]) -> bool:
    submit_like = metadata["type"] in SUBMIT_TYPES or (
        metadata["tag"] == "button" and metadata["type"] in {"", "submit"}
    )
    risky_control = metadata["tag"] != "a" and bool(SUBMIT_WORDS.search(metadata["text"]))
    return submit_like or risky_control


def _safe_url(config: ScanConfig, value: str) -> str:
    candidate = normalize_url(config.target, urljoin(config.target, value))
    if not candidate or not url_is_allowed(candidate, config.allowed_hosts, config.blocked_url_patterns):
        raise FlowSafetyError("flow navigation is outside the allowed scope or matches a blocked path")
    return candidate


def _step_value(step: FlowStep) -> str | None:
    if step.value_from_env:
        value = os.environ.get(step.value_from_env)
        if value is None:
            raise ValueError(f"required environment variable {step.value_from_env!r} is not set")
        return value
    return step.value


def redact_values(text: str, values: list[str]) -> str:
    for value in sorted((item for item in values if item), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text[:4_000]


async def _flow_screenshot(page: Page, output_dir: Path, flow_name: str, step: int) -> str | None:
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", flow_name).strip("-")[:80] or "flow"
    path = evidence_dir / f"flow-{slug}-step-{step}.png"
    try:
        await page.screenshot(
            path=path,
            full_page=True,
            mask=[page.locator("input, textarea, select")],
            mask_color="#6b7280",
        )
    except Exception:
        return None
    return path.relative_to(output_dir).as_posix()


def _failure_finding(
    flow: SmokeFlow,
    url: str,
    index: int,
    step: FlowStep,
    error: str,
    screenshot: str | None,
) -> Finding:
    evidence = {"flow": flow.name, "step": index, "action": step.action, "error": error}
    if step.selector:
        evidence["selector"] = step.selector
    if screenshot:
        evidence["screenshot"] = screenshot
    return Finding(
        rule_id="functional.smoke-flow-failed",
        title=f"Smoke flow failed: {flow.name}",
        category=Category.FUNCTIONAL,
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        url=url,
        viewport=flow.viewport,
        description=f"Step {index} ({step.action}) did not complete successfully.",
        evidence=evidence,
        recommendation="Reproduce the flow, inspect the screenshot and correct the failing behavior or locator.",
    )
