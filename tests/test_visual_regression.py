from pathlib import Path

from PIL import Image

from preflight_qa.config import VisualRegressionConfig
from preflight_qa.visual_regression import compare_visual_baseline


def _image(path: Path, color: str) -> None:
    Image.new("RGB", (20, 20), color).save(path)


def test_visual_baseline_create_match_and_change(tmp_path: Path) -> None:
    actual = tmp_path / "actual.png"
    baseline_dir = tmp_path / "baselines"
    output_dir = tmp_path / "report"
    _image(actual, "white")

    update = VisualRegressionConfig(enabled=True, baseline_dir=str(baseline_dir), update_baselines=True)
    comparison, finding = compare_visual_baseline(
        url="https://example.com/",
        viewport="desktop",
        screenshot_path=actual,
        output_dir=output_dir,
        config=update,
    )
    assert comparison["status"] == "created"
    assert finding is None

    compare = VisualRegressionConfig(enabled=True, baseline_dir=str(baseline_dir))
    comparison, finding = compare_visual_baseline(
        url="https://example.com/",
        viewport="desktop",
        screenshot_path=actual,
        output_dir=output_dir,
        config=compare,
    )
    assert comparison["status"] == "matched"
    assert finding is None

    _image(actual, "black")
    comparison, finding = compare_visual_baseline(
        url="https://example.com/",
        viewport="desktop",
        screenshot_path=actual,
        output_dir=output_dir,
        config=compare,
    )
    assert comparison["changed_pixel_ratio"] == 1.0
    assert finding is not None
    assert finding.rule_id == "visual.regression-detected"
    assert (output_dir / finding.evidence["diff_screenshot"]).is_file()


def test_missing_visual_baseline_is_informational(tmp_path: Path) -> None:
    actual = tmp_path / "actual.png"
    _image(actual, "white")
    comparison, finding = compare_visual_baseline(
        url="https://example.com/",
        viewport="mobile",
        screenshot_path=actual,
        output_dir=tmp_path / "report",
        config=VisualRegressionConfig(enabled=True, baseline_dir=str(tmp_path / "missing-baselines")),
    )
    assert comparison["status"] == "missing"
    assert finding is not None
    assert finding.severity.value == "info"
