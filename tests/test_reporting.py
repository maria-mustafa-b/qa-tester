import json

from preflight_qa.models import PageResult, ScanReport
from preflight_qa.reporting import write_reports


def test_reports_are_created(tmp_path) -> None:
    report = ScanReport(target="https://example.com")
    report.pages.append(
        PageResult(
            url="https://example.com",
            final_url="https://example.com",
            title="Example",
            status=200,
            duration_ms=500,
            viewport="desktop",
            performance={
                "ttfb_ms": 100,
                "fcp_ms": 200,
                "lcp_ms": 300,
                "cls": 0.01,
                "transfer_kb": 42,
            },
        )
    )
    report.finish()
    json_path, html_path = write_reports(report, tmp_path)
    data = json.loads(json_path.read_text())
    assert data["schema_version"] == "1.1"
    assert "by_category" in data["summary"]
    assert "Preflight QA" in html_path.read_text()
    assert "42 KB" in html_path.read_text()
