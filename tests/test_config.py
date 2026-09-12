from pathlib import Path

import pytest

from preflight_qa.config import load_config


def test_url_override_builds_default_config() -> None:
    config = load_config(None, "https://example.com")
    assert config.target == "https://example.com"
    assert config.allowed_hosts == ["example.com"]
    assert {viewport.name for viewport in config.viewports} == {"desktop", "mobile"}


def test_invalid_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="absolute"):
        load_config(None, "example.com")


def test_unknown_configuration_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("target: https://example.com\nunknown: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown configuration"):
        load_config(path)


def test_nested_performance_budgets_are_loaded(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "target: https://example.com\nperformance_budgets:\n  lcp_ms: 3000\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.performance_budgets.lcp_ms == 3000
    assert config.performance_budgets.cls == 0.1


def test_visual_regression_configuration_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
target: https://example.com
visual_regression:
  enabled: true
  baseline_dir: snapshots
  max_changed_pixel_ratio: 0.02
  pixel_threshold: 30
""".strip(),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.visual_regression.enabled
    assert config.visual_regression.baseline_dir == "snapshots"
    assert config.visual_regression.max_changed_pixel_ratio == 0.02
