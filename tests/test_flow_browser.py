import asyncio
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from preflight_qa.config import FlowStep, ScanConfig, SmokeFlow, Viewport
from preflight_qa.flows import run_smoke_flows


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def test_smoke_flow_runs_in_a_real_browser(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        '<!doctype html><html><body><a href="/done.html">Continue</a></body></html>',
        encoding="utf-8",
    )
    (site / "done.html").write_text(
        "<!doctype html><html><body><main>Journey complete</main></body></html>",
        encoding="utf-8",
    )
    handler = partial(QuietHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        asyncio.run(_run_browser_flow(server.server_port, tmp_path))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def _run_browser_flow(port: int, output_dir: Path) -> None:
    target = f"http://127.0.0.1:{port}"
    config = ScanConfig(
        target=target,
        max_pages=1,
        viewports=[Viewport("desktop", 1_024, 768)],
        flows=[
            SmokeFlow(
                name="browser journey",
                steps=(
                    FlowStep("click", selector='a[href="/done.html"]'),
                    FlowStep("assert_url", value="/done.html"),
                    FlowStep("assert_text", selector="main", value="Journey complete"),
                ),
            )
        ],
    )
    config.validate()
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Playwright Chromium is not installed")
            raise
        try:
            results, findings = await run_smoke_flows(browser, config, output_dir)
        finally:
            await browser.close()
    assert findings == []
    assert results[0].status == "passed"
    assert [step.status for step in results[0].steps] == ["passed", "passed", "passed"]
