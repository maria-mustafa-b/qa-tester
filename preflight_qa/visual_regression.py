from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageChops

from preflight_qa.config import VisualRegressionConfig
from preflight_qa.models import Category, Confidence, Finding, Severity


def compare_visual_baseline(
    *,
    url: str,
    viewport: str,
    screenshot_path: Path,
    output_dir: Path,
    config: VisualRegressionConfig,
) -> tuple[dict[str, object], Finding | None]:
    baseline_dir = Path(config.baseline_dir)
    baseline_path = baseline_dir / _baseline_name(url, viewport)
    comparison: dict[str, object] = {"baseline": baseline_path.as_posix()}

    if config.update_baselines:
        baseline_dir.mkdir(parents=True, exist_ok=True)
        status = "updated" if baseline_path.exists() else "created"
        with Image.open(screenshot_path) as actual:
            actual.save(baseline_path, format="PNG")
        comparison["status"] = status
        return comparison, None

    if not baseline_path.is_file():
        comparison["status"] = "missing"
        return comparison, Finding(
            rule_id="visual.baseline-missing",
            title="Visual regression baseline is missing",
            category=Category.VISUAL,
            severity=Severity.INFO,
            confidence=Confidence.CONFIRMED,
            url=url,
            viewport=viewport,
            description="Visual comparison was enabled but no approved baseline exists for this page and viewport.",
            evidence={"baseline": baseline_path.as_posix()},
            recommendation="Review the current rendering, then run once with --update-baselines to approve it.",
        )

    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stem = baseline_path.stem
    baseline_evidence = evidence_dir / f"{stem}-baseline.png"
    diff_path = evidence_dir / f"{stem}-diff.png"

    with Image.open(screenshot_path) as actual_source, Image.open(baseline_path) as baseline_source:
        actual = actual_source.convert("RGB")
        baseline = baseline_source.convert("RGB")
        comparison["actual_size"] = list(actual.size)
        comparison["baseline_size"] = list(baseline.size)
        if actual.size != baseline.size:
            baseline.save(baseline_evidence, format="PNG")
            comparison.update({"status": "changed", "changed_pixel_ratio": 1.0})
            return comparison, _visual_finding(
                url,
                viewport,
                1.0,
                config.max_changed_pixel_ratio,
                baseline_evidence,
                None,
                output_dir,
                "The current screenshot dimensions differ from the approved baseline.",
            )

        difference = ImageChops.difference(actual, baseline)
        channels = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        mask = maximum.point(lambda value: 255 if value > config.pixel_threshold else 0)
        changed_pixels = mask.histogram()[255]
        total_pixels = actual.width * actual.height
        ratio = changed_pixels / total_pixels if total_pixels else 0.0
        comparison.update(
            {
                "status": "changed" if ratio > config.max_changed_pixel_ratio else "matched",
                "changed_pixels": changed_pixels,
                "total_pixels": total_pixels,
                "changed_pixel_ratio": round(ratio, 6),
            }
        )
        if ratio <= config.max_changed_pixel_ratio:
            return comparison, None

        baseline.save(baseline_evidence, format="PNG")
        overlay = Image.new("RGB", actual.size, "#ff2d55")
        Image.composite(overlay, actual, mask).save(diff_path, format="PNG")

    return comparison, _visual_finding(
        url,
        viewport,
        ratio,
        config.max_changed_pixel_ratio,
        baseline_evidence,
        diff_path,
        output_dir,
        "The current rendering differs from the approved screenshot baseline.",
    )


def _baseline_name(url: str, viewport: str) -> str:
    parsed = urlparse(url)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{parsed.netloc}{parsed.path}").strip("-")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{(slug or 'home')[:80]}-{digest}-{viewport}.png"


def _visual_finding(
    url: str,
    viewport: str,
    ratio: float,
    threshold: float,
    baseline_path: Path,
    diff_path: Path | None,
    output_dir: Path,
    description: str,
) -> Finding:
    evidence: dict[str, object] = {
        "changed_pixel_ratio": round(ratio, 6),
        "allowed_ratio": threshold,
        "baseline_screenshot": baseline_path.relative_to(output_dir).as_posix(),
    }
    if diff_path:
        evidence["diff_screenshot"] = diff_path.relative_to(output_dir).as_posix()
    return Finding(
        rule_id="visual.regression-detected",
        title="Page rendering differs from its visual baseline",
        category=Category.VISUAL,
        severity=Severity.HIGH if ratio > 0.2 else Severity.MEDIUM,
        confidence=Confidence.CONFIRMED,
        url=url,
        viewport=viewport,
        description=description,
        evidence=evidence,
        recommendation="Review the actual, baseline and diff images; fix the regression or approve a new baseline.",
    )
