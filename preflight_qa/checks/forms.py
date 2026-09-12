from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from preflight_qa.models import Category, Confidence, Finding, Severity


def run_form_checks(snapshot: dict[str, Any], url: str, viewport: str) -> list[Finding]:
    findings: list[Finding] = []
    page_scheme = urlparse(url).scheme
    for form in snapshot.get("forms", []):
        selector = form.get("selector", "form")
        action = urljoin(url, str(form.get("action") or url))
        controls = form.get("controls", [])
        password_controls = [item for item in controls if item.get("type") == "password"]

        if password_controls and str(form.get("method", "get")).lower() == "get":
            findings.append(
                _finding(
                    "security.password-form-uses-get",
                    "Password form uses the GET method",
                    Category.SECURITY,
                    Severity.HIGH,
                    url,
                    viewport,
                    selector,
                    "A password form can place credentials in URLs, browser history and server logs.",
                    "Submit password forms with POST over HTTPS.",
                    {"method": "get", "action": action},
                )
            )

        if page_scheme == "https" and urlparse(action).scheme == "http":
            findings.append(
                _finding(
                    "security.form-action-downgrade",
                    "Secure page submits a form over HTTP",
                    Category.SECURITY,
                    Severity.CRITICAL,
                    url,
                    viewport,
                    selector,
                    "The form action downgrades data submission from HTTPS to unencrypted HTTP.",
                    "Use an HTTPS form action and enforce secure transport server-side.",
                    {"action": action},
                )
            )

        for control in controls:
            control_selector = control.get("selector", selector)
            control_type = str(control.get("type", "text"))
            if control.get("required") and not control.get("name"):
                findings.append(
                    _finding(
                        "functional.required-control-missing-name",
                        "Required form control has no name",
                        Category.FUNCTIONAL,
                        Severity.MEDIUM,
                        url,
                        viewport,
                        control_selector,
                        "A required control without a name is normally omitted from submitted form data.",
                        "Add a stable name that the server expects.",
                    )
                )
            if control_type == "password" and control.get("autocomplete") not in {
                "current-password",
                "new-password",
            }:
                findings.append(
                    _finding(
                        "content.password-autocomplete",
                        "Password field has no recognized autocomplete purpose",
                        Category.ACCESSIBILITY,
                        Severity.LOW,
                        url,
                        viewport,
                        control_selector,
                        "Password managers cannot reliably distinguish a current password from a new one.",
                        "Set autocomplete to current-password or new-password as appropriate.",
                    )
                )
            minimum = _number(control.get("min"))
            maximum = _number(control.get("max"))
            if minimum is not None and maximum is not None and minimum > maximum:
                findings.append(
                    _finding(
                        "functional.invalid-input-range",
                        "Form control has an impossible range",
                        Category.FUNCTIONAL,
                        Severity.MEDIUM,
                        url,
                        viewport,
                        control_selector,
                        "The control's minimum value is greater than its maximum value.",
                        "Correct the min and max constraints and add a regression test.",
                        {"min": minimum, "max": maximum},
                    )
                )
    return findings


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _finding(
    rule_id: str,
    title: str,
    category: Category,
    severity: Severity,
    url: str,
    viewport: str,
    element: str,
    description: str,
    recommendation: str,
    extra_evidence: dict[str, Any] | None = None,
) -> Finding:
    evidence = {"element": element}
    evidence.update(extra_evidence or {})
    return Finding(
        rule_id=rule_id,
        title=title,
        category=category,
        severity=severity,
        confidence=Confidence.CONFIRMED,
        url=url,
        viewport=viewport,
        description=description,
        evidence=evidence,
        recommendation=recommendation,
    )
