from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

IGNORED_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


def normalize_url(base_url: str, candidate: str) -> str | None:
    candidate = candidate.strip()
    if not candidate or candidate.lower().startswith(IGNORED_SCHEMES):
        return None
    absolute = urljoin(base_url, candidate)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def url_is_allowed(url: str, allowed_hosts: list[str], blocked_patterns: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.hostname not in allowed_hosts:
        return False
    lowered = url.lower()
    return not any(pattern.lower() in lowered for pattern in blocked_patterns)
