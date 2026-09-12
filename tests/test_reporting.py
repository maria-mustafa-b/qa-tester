import json

from preflight_qa.models import ScanReport
from preflight_qa.reporting import write_reports


def test_reports_are_created(tmp_path) -> None:
    report = ScanReport(target="https://example.com")
    report.finish()
    json_path, html_path = write_reports(report, tmp_path)
    assert json.loads(json_path.read_text())["schema_version"] == "1.0"
    assert "Preflight QA" in html_path.read_text()

