from preflight_qa.checks.accessibility import findings_from_axe
from preflight_qa.checks.content import run_content_checks
from preflight_qa.checks.forms import run_form_checks
from preflight_qa.checks.performance import run_performance_checks
from preflight_qa.checks.security import run_security_checks
from preflight_qa.checks.visual import run_visual_checks
from preflight_qa.config import PerformanceBudgets


def test_content_checks_find_missing_metadata_and_broken_image() -> None:
    snapshot = {
        "title": "",
        "lang": "",
        "body_text": "Lorem ipsum",
        "images": [
            {
                "selector": "img",
                "src": "/missing.png",
                "alt_present": False,
                "complete": True,
                "natural_width": 0,
            }
        ],
        "empty_interactives": ["button"],
    }
    rule_ids = {item.rule_id for item in run_content_checks(snapshot, "https://x.test", "desktop")}
    assert {
        "content.missing-title",
        "content.missing-language",
        "content.image-missing-alt",
        "functional.broken-image",
        "content.empty-interactive-name",
        "content.placeholder-text",
    } <= rule_ids


def test_security_checks_redact_secret() -> None:
    html = "<script>const key='AKIAABCDEFGHIJKLMNOP'</script>"
    findings = run_security_checks(url="https://x.test", headers={}, html=html, viewport="desktop")
    secret = next(item for item in findings if item.rule_id.startswith("security.exposed-secret"))
    assert secret.evidence["redacted_match"] == "AKIA…MNOP"
    assert "AKIAABCDEFGHIJKLMNOP" not in str(secret.to_dict())


def test_visual_overflow_is_reported() -> None:
    findings = run_visual_checks(
        {"horizontal_overflow": 200, "overflowing_elements": []},
        "https://x.test",
        "mobile",
    )
    assert findings[0].rule_id == "visual.horizontal-overflow"


def test_axe_violations_become_redacted_structured_findings() -> None:
    result = {
        "violations": [
            {
                "id": "button-name",
                "impact": "critical",
                "help": "Buttons must have discernible text",
                "description": "Ensures buttons have names",
                "helpUrl": "https://dequeuniversity.com/rules/axe/button-name",
                "tags": ["wcag2a"],
                "nodes": [
                    {"target": ["#save"], "html": "<button id='save'></button>", "failureSummary": "Fix the button"}
                ],
            }
        ]
    }
    finding = findings_from_axe(result, "https://x.test", "desktop")[0]
    assert finding.rule_id == "accessibility.axe.button-name"
    assert finding.severity.value == "critical"
    assert finding.evidence["node_count"] == 1


def test_form_checks_are_passive_and_find_invalid_markup() -> None:
    snapshot = {
        "forms": [
            {
                "selector": "#login",
                "method": "get",
                "action": "/login",
                "controls": [
                    {"selector": "#password", "type": "password", "required": True, "name": "", "autocomplete": ""},
                    {"selector": "#age", "type": "number", "name": "age", "min": "20", "max": "10"},
                ],
            }
        ]
    }
    rule_ids = {item.rule_id for item in run_form_checks(snapshot, "https://x.test", "desktop")}
    assert {
        "security.password-form-uses-get",
        "functional.required-control-missing-name",
        "content.password-autocomplete",
        "functional.invalid-input-range",
    } <= rule_ids


def test_performance_checks_use_configured_budgets() -> None:
    metrics = {"ttfb_ms": 900, "fcp_ms": 1_000, "lcp_ms": None, "cls": 0.25, "transfer_kb": 50, "request_count": 10}
    findings = run_performance_checks(metrics, "https://x.test", "mobile", PerformanceBudgets())
    assert {item.rule_id for item in findings} == {
        "performance.budget.ttfb_ms",
        "performance.budget.cls",
    }
