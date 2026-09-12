from pathlib import Path

import pytest

from preflight_qa.config import ScanConfig, load_config
from preflight_qa.flows import (
    FlowSafetyError,
    _safe_url,
    click_requires_submit_permission,
    redact_values,
)


def test_flow_configuration_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
target: https://example.com
flows:
  - name: homepage
    steps:
      - action: assert_visible
        selector: h1
      - action: assert_text
        selector: main
        value: Welcome
""".strip(),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.flows[0].name == "homepage"
    assert config.flows[0].steps[1].value == "Welcome"


def test_unknown_flow_action_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "target: https://example.com\nflows:\n  - name: unsafe\n    steps:\n      - action: evaluate\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported action"):
        load_config(path)


def test_flow_navigation_obeys_scope_and_blocked_paths() -> None:
    config = ScanConfig(target="https://example.com", blocked_url_patterns=["/delete"])
    config.validate()
    assert _safe_url(config, "/docs") == "https://example.com/docs"
    with pytest.raises(FlowSafetyError, match="outside"):
        _safe_url(config, "https://other.example/docs")
    with pytest.raises(FlowSafetyError, match="blocked"):
        _safe_url(config, "/delete/account")


def test_report_errors_redact_flow_values() -> None:
    assert redact_values("login failed for secret-123", ["secret-123"]) == "login failed for [REDACTED]"


def test_submit_guard_distinguishes_navigation_links_from_form_controls() -> None:
    assert click_requires_submit_permission(
        {"tag": "button", "type": "submit", "text": "Continue", "href": "", "formAction": ""}
    )
    assert not click_requires_submit_permission(
        {"tag": "a", "type": "", "text": "Sign in", "href": "/login", "formAction": ""}
    )
