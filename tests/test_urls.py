from preflight_qa.urls import normalize_url, url_is_allowed


def test_normalize_relative_url_and_remove_fragment() -> None:
    assert normalize_url("https://example.com/a/", "../docs/#intro") == "https://example.com/docs"


def test_ignored_scheme_returns_none() -> None:
    assert normalize_url("https://example.com", "mailto:test@example.com") is None


def test_scope_and_blocked_patterns() -> None:
    assert url_is_allowed("https://example.com/docs", ["example.com"], ["/delete"])
    assert not url_is_allowed("https://example.com/delete/1", ["example.com"], ["/delete"])
    assert not url_is_allowed("https://other.example/docs", ["example.com"], [])
