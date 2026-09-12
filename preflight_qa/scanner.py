from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, Page, Response, async_playwright

from preflight_qa.checks.accessibility import run_accessibility_checks
from preflight_qa.checks.content import run_content_checks
from preflight_qa.checks.forms import run_form_checks
from preflight_qa.checks.performance import run_performance_checks
from preflight_qa.checks.security import run_security_checks
from preflight_qa.checks.visual import run_visual_checks
from preflight_qa.config import ScanConfig, Viewport
from preflight_qa.models import (
    Category,
    Confidence,
    Finding,
    PageResult,
    ScanReport,
    Severity,
)
from preflight_qa.urls import normalize_url, url_is_allowed

SNAPSHOT_SCRIPT = """
() => {
  const selector = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const tag = el.tagName.toLowerCase();
    const name = el.getAttribute('name');
    if (name) return `${tag}[name=${JSON.stringify(name)}]`;
    const text = (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 50);
    return text ? `${tag}:${JSON.stringify(text)}` : tag;
  };
  const visible = (el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
  };
  const elements = [...document.querySelectorAll('body *')].filter(visible);
  return {
    title: document.title || '',
    lang: document.documentElement.lang || '',
    body_text: (document.body?.innerText || '').slice(0, 200000),
    links: [...document.querySelectorAll('a[href]')].map(a => a.href),
    images: [...document.images].map(img => ({
      selector: selector(img),
      src: img.currentSrc || img.src,
      alt_present: img.hasAttribute('alt'),
      complete: img.complete,
      natural_width: img.naturalWidth,
    })),
    forms: [...document.forms].map(form => ({
      selector: selector(form),
      action: form.getAttribute('action') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      controls: [...form.elements]
        .filter(el => ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(el.tagName))
        .map(el => ({
          selector: selector(el),
          type: (el.getAttribute('type') || el.tagName.toLowerCase()).toLowerCase(),
          name: el.getAttribute('name') || '',
          required: Boolean(el.required),
          disabled: Boolean(el.disabled),
          autocomplete: el.getAttribute('autocomplete') || '',
          min: el.getAttribute('min'),
          max: el.getAttribute('max'),
        })),
    })),
    empty_interactives: [...document.querySelectorAll('a[href], button')]
      .filter(el => visible(el))
      .filter(el => !(el.innerText || '').trim() && !el.getAttribute('aria-label') && !el.getAttribute('title'))
      .map(selector),
    horizontal_overflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
    overflowing_elements: elements
      .map(el => ({ selector: selector(el), right: Math.round(el.getBoundingClientRect().right) }))
      .filter(item => item.right > window.innerWidth + 1)
      .slice(0, 20),
  };
}
"""

PERFORMANCE_INIT_SCRIPT = """
(() => {
  window.__preflightPerformance = { lcp_ms: null, cls: 0, long_task_ms: 0, long_task_count: 0 };
  try {
    new PerformanceObserver(list => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) window.__preflightPerformance.lcp_ms = last.startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (_) {}
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__preflightPerformance.cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (_) {}
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        window.__preflightPerformance.long_task_ms += entry.duration;
        window.__preflightPerformance.long_task_count += 1;
      }
    }).observe({ type: 'longtask', buffered: true });
  } catch (_) {}
})();
"""

PERFORMANCE_SNAPSHOT_SCRIPT = """
() => {
  const navigation = performance.getEntriesByType('navigation')[0];
  const resources = performance.getEntriesByType('resource');
  const paints = performance.getEntriesByType('paint');
  const fcp = paints.find(entry => entry.name === 'first-contentful-paint');
  const observed = window.__preflightPerformance || {};
  const transferBytes = resources.reduce((total, item) => total + (item.transferSize || 0), 0)
    + (navigation?.transferSize || 0);
  return {
    ttfb_ms: navigation ? navigation.responseStart : null,
    dom_content_loaded_ms: navigation ? navigation.domContentLoadedEventEnd : null,
    load_ms: navigation?.loadEventEnd || null,
    fcp_ms: fcp?.startTime || null,
    lcp_ms: observed.lcp_ms ?? null,
    cls: observed.cls ?? null,
    transfer_kb: Math.round((transferBytes / 1024) * 100) / 100,
    request_count: resources.length + 1,
    long_task_ms: Math.round((observed.long_task_ms || 0) * 100) / 100,
    long_task_count: observed.long_task_count || 0,
  };
}
"""


class WebScanner:
    def __init__(self, config: ScanConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.evidence_dir = output_dir / "evidence"
        self.report = ScanReport(target=config.target)

    async def run(self) -> ScanReport:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.config.headless)
            try:
                await self._crawl(browser)
            finally:
                await browser.close()
        self.report.finish()
        return self.report

    async def _crawl(self, browser: Browser) -> None:
        starting_url = normalize_url(self.config.target, self.config.target)
        if not starting_url:
            raise ValueError("target URL could not be normalized")
        queue: deque[str] = deque([starting_url])
        visited: set[str] = set()

        while queue and len(visited) < self.config.max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            discovered: list[str] = []
            for index, viewport in enumerate(self.config.viewports):
                links = await self._scan_page(browser, url, viewport)
                if index == 0:
                    discovered = links
            for candidate in discovered:
                normalized = normalize_url(url, candidate)
                if not normalized or normalized in visited or normalized in queue:
                    continue
                if url_is_allowed(normalized, self.config.allowed_hosts, self.config.blocked_url_patterns):
                    queue.append(normalized)
                else:
                    self.report.skipped_urls.append(
                        {"url": normalized, "reason": "outside scope or blocked by configuration"}
                    )

    async def _scan_page(self, browser: Browser, url: str, viewport: Viewport) -> list[str]:
        context = await browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            ignore_https_errors=self.config.ignore_https_errors,
        )
        await context.add_init_script(script=PERFORMANCE_INIT_SCRIPT)
        page = await context.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[dict[str, str]] = []
        error_responses: list[dict[str, str | int]] = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                {"url": request.url, "method": request.method, "failure": request.failure or "unknown"}
            ),
        )
        page.on(
            "response",
            lambda response: (
                error_responses.append({"url": response.url, "status": response.status})
                if response.status >= 400
                else None
            ),
        )

        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            try:
                await page.wait_for_load_state("load", timeout=min(self.config.timeout_ms, 3_000))
            except Exception:
                pass
            await page.wait_for_timeout(500)
            duration_ms = round((time.perf_counter() - started) * 1000)
            snapshot = await page.evaluate(SNAPSHOT_SCRIPT)
            performance = await page.evaluate(PERFORMANCE_SNAPSHOT_SCRIPT)
            html = await page.content()
            headers = await response.all_headers() if response else {}
            screenshot = await self._take_screenshot(page, url, viewport.name)
            final_url = page.url

            self.report.pages.append(
                PageResult(
                    url=url,
                    final_url=final_url,
                    title=await page.title(),
                    status=response.status if response else None,
                    duration_ms=duration_ms,
                    viewport=viewport.name,
                    screenshot=screenshot,
                    performance=performance,
                )
            )

            for finding in run_content_checks(snapshot, final_url, viewport.name):
                self._attach_screenshot(finding, screenshot)
                self.report.add_finding(finding)
            for finding in run_visual_checks(snapshot, final_url, viewport.name):
                self._attach_screenshot(finding, screenshot)
                self.report.add_finding(finding)
            for finding in run_form_checks(snapshot, final_url, viewport.name):
                self._attach_screenshot(finding, screenshot)
                self.report.add_finding(finding)
            for finding in run_performance_checks(
                performance, final_url, viewport.name, self.config.performance_budgets
            ):
                self._attach_screenshot(finding, screenshot)
                self.report.add_finding(finding)
            for finding in run_security_checks(url=final_url, headers=headers, html=html, viewport=viewport.name):
                self._attach_screenshot(finding, screenshot)
                self.report.add_finding(finding)

            try:
                accessibility_findings = await run_accessibility_checks(
                    page, final_url, viewport.name, self.config.accessibility_tags
                )
            except Exception as exc:
                self.report.scanner_errors.append(
                    {"url": final_url, "error": f"axe-core accessibility audit failed: {exc}"}
                )
            else:
                for finding in accessibility_findings:
                    self._attach_screenshot(finding, screenshot)
                    self.report.add_finding(finding)

            self._add_runtime_findings(
                url=final_url,
                viewport=viewport.name,
                screenshot=screenshot,
                status=response.status if response else None,
                console_errors=console_errors,
                page_errors=page_errors,
                failed_requests=failed_requests,
                error_responses=error_responses,
            )
            return list(snapshot.get("links", []))
        except Exception as exc:  # Playwright errors carry useful browser failure context.
            duration_ms = round((time.perf_counter() - started) * 1000)
            screenshot = await self._take_screenshot(page, url, viewport.name, tolerate_failure=True)
            finding = Finding(
                rule_id="crash.navigation-failure",
                title="Page could not be loaded",
                category=Category.CRASH,
                severity=Severity.HIGH,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport.name,
                description="Browser navigation failed or exceeded the configured timeout.",
                evidence={"error": str(exc), "duration_ms": duration_ms},
                recommendation="Inspect application availability, redirect behaviour and browser logs.",
            )
            self._attach_screenshot(finding, screenshot)
            self.report.add_finding(finding)
            self.report.scanner_errors.append({"url": url, "error": str(exc)})
            return []
        finally:
            await context.close()

    def _add_runtime_findings(
        self,
        *,
        url: str,
        viewport: str,
        screenshot: str | None,
        status: int | None,
        console_errors: list[str],
        page_errors: list[str],
        failed_requests: list[dict[str, str]],
        error_responses: list[dict[str, str | int]],
    ) -> None:
        runtime_findings: list[Finding] = []
        if status is not None and status >= 400:
            runtime_findings.append(
                Finding(
                    "functional.http-error",
                    f"Page returned HTTP {status}",
                    Category.FUNCTIONAL,
                    Severity.HIGH if status >= 500 else Severity.MEDIUM,
                    Confidence.CONFIRMED,
                    url,
                    "The primary document request returned an error status.",
                    evidence={"status": status},
                    recommendation="Correct the route or server error before deployment.",
                    viewport=viewport,
                )
            )
        if page_errors or console_errors:
            runtime_findings.append(
                Finding(
                    "crash.javascript-error",
                    "JavaScript errors occurred while loading the page",
                    Category.CRASH,
                    Severity.HIGH if page_errors else Severity.MEDIUM,
                    Confidence.CONFIRMED,
                    url,
                    "The browser recorded uncaught exceptions or error-level console messages.",
                    evidence={"page_errors": page_errors[:10], "console_errors": console_errors[:10]},
                    recommendation="Reproduce with the attached page and correct the client-side exception.",
                    viewport=viewport,
                )
            )
        if failed_requests or error_responses:
            runtime_findings.append(
                Finding(
                    "functional.network-failure",
                    "Network requests failed while loading the page",
                    Category.FUNCTIONAL,
                    Severity.MEDIUM,
                    Confidence.CONFIRMED,
                    url,
                    "One or more resources or API requests failed.",
                    evidence={
                        "failed_requests": failed_requests[:20],
                        "error_responses": error_responses[:20],
                    },
                    recommendation="Inspect the failed endpoints, deployment paths and server logs.",
                    viewport=viewport,
                )
            )
        for finding in runtime_findings:
            self._attach_screenshot(finding, screenshot)
            self.report.add_finding(finding)

    async def _take_screenshot(self, page: Page, url: str, viewport: str, tolerate_failure: bool = False) -> str | None:
        parsed = urlparse(url)
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{parsed.netloc}{parsed.path}").strip("-")
        slug = (slug or "home")[:100]
        path = self.evidence_dir / f"{slug}-{viewport}.png"
        try:
            await page.screenshot(path=path, full_page=True, timeout=self.config.timeout_ms)
            return path.relative_to(self.output_dir).as_posix()
        except Exception:
            if tolerate_failure:
                return None
            raise

    @staticmethod
    def _attach_screenshot(finding: Finding, screenshot: str | None) -> None:
        if screenshot:
            finding.evidence.setdefault("screenshot", screenshot)


async def scan(config: ScanConfig, output_dir: Path) -> ScanReport:
    return await WebScanner(config, output_dir).run()


def run_scan(config: ScanConfig, output_dir: Path) -> ScanReport:
    return asyncio.run(scan(config, output_dir))
