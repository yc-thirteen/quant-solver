"""End-to-end smoke test. Hits the live Anthropic API and is skipped by default.

Run with:

    QS_INTEGRATION_IMAGE=path/to/problem.png \
    QS_INTEGRATION_EXPECTED="2.3%" \
    pytest -m slow tests/test_pipeline_integration.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from quant_solver.config import load_config
from quant_solver.pipeline import run_pipeline
from quant_solver.utils import answers_equivalent


@pytest.mark.slow
def test_end_to_end_user_supplied_image() -> None:
    config = load_config()
    if not config.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    image_env = os.environ.get("QS_INTEGRATION_IMAGE")
    expected = os.environ.get("QS_INTEGRATION_EXPECTED")
    if not image_env or not expected:
        pytest.skip("QS_INTEGRATION_IMAGE and QS_INTEGRATION_EXPECTED not set")

    image = Path(image_env)
    if not image.exists():
        pytest.skip(f"{image} not present")

    final = asyncio.run(run_pipeline(image))
    assert answers_equivalent(final.answer, expected), (
        f"Expected {expected!r}, got {final.answer!r}; audit={final.audit_trail_path}"
    )
