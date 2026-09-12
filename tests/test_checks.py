from preflight_qa.checks.content import run_content_checks
from preflight_qa.checks.security import run_security_checks
from preflight_qa.checks.visual import run_visual_checks


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

