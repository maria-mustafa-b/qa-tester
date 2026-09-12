from __future__ import annotations

import re
from urllib.parse import urlparse

from preflight_qa.models import Category, Confidence, Finding, Severity

SECURITY_HEADERS = {
    "content-security-policy": ("Content-Security-Policy", Severity.MEDIUM),
    "x-content-type-options": ("X-Content-Type-Options", Severity.LOW),
    "referrer-policy": ("Referrer-Policy", Severity.LOW),
    "permissions-policy": ("Permissions-Policy", Severity.LOW),
}

SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,255}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def run_security_checks(*, url: str, headers: dict[str, str], html: str, viewport: str) -> list[Finding]:
    findings: list[Finding] = []
    normalized = {key.lower(): value for key, value in headers.items()}
    parsed = urlparse(url)

    for key, (display_name, severity) in SECURITY_HEADERS.items():
        if key not in normalized:
            findings.append(
                Finding(
                    rule_id=f"security.missing-header.{key}",
                    title=f"Missing {display_name} header",
                    category=Category.SECURITY,
                    severity=severity,
                    confidence=Confidence.CONFIRMED,
                    url=url,
                    viewport=viewport,
                    description=f"The response does not include the {display_name} security header.",
                    recommendation=f"Configure the application or reverse proxy to send {display_name}.",
                )
            )

    if parsed.scheme == "https" and "strict-transport-security" not in normalized:
        findings.append(
            Finding(
                rule_id="security.missing-header.hsts",
                title="HTTPS response is missing HSTS",
                category=Category.SECURITY,
                severity=Severity.MEDIUM,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description="The HTTPS response does not instruct browsers to enforce HTTPS.",
                recommendation="Add a reviewed Strict-Transport-Security policy after confirming HTTPS coverage.",
            )
        )

    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        findings.append(
            Finding(
                rule_id="security.insecure-transport",
                title="Page is served without HTTPS",
                category=Category.SECURITY,
                severity=Severity.HIGH,
                confidence=Confidence.CONFIRMED,
                url=url,
                viewport=viewport,
                description="Traffic to the page is not protected by TLS.",
                recommendation="Serve the application over HTTPS and redirect HTTP traffic.",
            )
        )

    for secret_name, pattern in SECRET_PATTERNS.items():
        match = pattern.search(html)
        if match:
            findings.append(
                Finding(
                    rule_id=f"security.exposed-secret.{secret_name.lower().replace(' ', '-')}",
                    title=f"Possible exposed {secret_name}",
                    category=Category.SECURITY,
                    severity=Severity.CRITICAL,
                    confidence=Confidence.LIKELY,
                    url=url,
                    viewport=viewport,
                    description="A credential-shaped value was found in rendered client-side HTML.",
                    evidence={"type": secret_name, "redacted_match": _redact(match.group(0))},
                    recommendation="Revoke the credential, remove it from client code and rotate affected secrets.",
                )
            )
    return findings


def _redact(value: str) -> str:
    if len(value) < 10:
        return "***"
    return f"{value[:4]}…{value[-4:]}"
