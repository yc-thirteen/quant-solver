"""Tests for Stage 1: Intake.

Includes a test that generates a synthetic image with non-English text via PIL
to exercise the multilingual vision path without requiring a real screenshot.
Marked ``@pytest.mark.slow`` because it hits the Anthropic API.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:
    Image = None  # type: ignore


from quant_solver.anth_client import AnthropicClient, load_image_block
from quant_solver.config import load_config
from quant_solver.stages.intake import run_intake


def test_load_image_block_rejects_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "foo.bmp"
    p.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ValueError):
        load_image_block(p)


def test_load_image_block_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_image_block(tmp_path / "nope.png")


def test_load_image_block_accepts_png(tmp_path: Path) -> None:
    # Minimal 1x1 PNG file header + body (valid PNG bytes).
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "8900000000494441540878DA63F8FFFF3F00050FE22E6F6C8BFB0000000049454E44AE426082"
    )
    p = tmp_path / "one.png"
    p.write_bytes(png_bytes)
    block = load_image_block(p)
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"


@pytest.fixture
def synthetic_chinese_image(tmp_path: Path) -> Path:
    """Render a simple Chinese math problem into a PNG for integration testing."""
    if Image is None:
        pytest.skip("Pillow not installed; skipping synthetic image test")

    img = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(img)
    # Try a CJK-capable font; fall back to default (may not render CJK but the
    # test still exercises the code path).
    font = None
    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).exists():
            try:
                font = ImageFont.truetype(candidate, 28)
                break
            except OSError:
                continue
    text = "假设 X ~ N(0, 1)。求 P(X < -2) 的值,保留两位有效数字。"
    draw.text((20, 80), text, fill="black", font=font)
    path = tmp_path / "synthetic_zh.png"
    img.save(path)
    return path


@pytest.mark.slow
def test_intake_on_synthetic_chinese_image(synthetic_chinese_image: Path) -> None:
    """End-to-end smoke test: run the real intake on a synthetic Chinese image.

    Skipped by default. Run with ``pytest -m slow``. Requires ANTHROPIC_API_KEY.
    """
    config = load_config()
    if not config.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    client = AnthropicClient(config)
    result = asyncio.run(run_intake(synthetic_chinese_image, client=client, config=config))

    assert result.source_language in {"zh", "zh-CN", "zh-TW", "mixed"}
    assert "P(X" in result.extracted_math or "X" in result.extracted_math
    assert result.problem_type.value == "probability"
    # The English translation should mention the standard normal or something about X < -2.
    assert any(token in result.english_text for token in ["X", "-2", "probability", "normal"])
