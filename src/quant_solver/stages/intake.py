"""Stage 1: Intake.

Reads a screenshot in any language and returns a fully English ``IntakeResult``.
Uses ``claude-sonnet-4-6`` (fast / cheap) for vision + translation + classification.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from ..anth_client import AnthropicClient, load_image_block
from ..config import Config
from ..models import IntakeResult
from ..utils import read_prompt

log = structlog.get_logger(__name__)


async def run_intake(
    image_path: Path,
    *,
    client: AnthropicClient,
    config: Config,
) -> IntakeResult:
    """Run the intake stage on an image.

    Args:
        image_path: Path to a PNG, JPG, or WebP screenshot.
        client: Shared Anthropic client.
        config: Pipeline configuration.

    Returns:
        A validated ``IntakeResult``.

    Raises:
        ValueError: If the intake produces unparseable output after one repair,
            or if the vision stage flags the image as not containing a problem.
    """
    system = read_prompt("intake")
    image_block = load_image_block(image_path)
    user_blocks: list[dict] = [
        image_block,
        {
            "type": "text",
            "text": (
                "Extract this problem per the schema. Remember: transcribe the "
                "original language verbatim, translate fully to English, extract "
                "the math, classify the problem type. Return ONLY the JSON."
            ),
        },
    ]

    raw = await client.complete_json(
        model=config.intake_model,
        system=system,
        user_blocks=user_blocks,
        caller="intake",
    )
    result = IntakeResult.model_validate(raw)

    if result.english_text.strip().startswith("ERROR:"):
        log.error("intake_flagged_non_problem", english_text=result.english_text[:200])
        raise ValueError(f"Intake flagged image as non-problem: {result.english_text}")

    log.info(
        "intake_done",
        source_language=result.source_language,
        problem_type=result.problem_type.value,
        english_len=len(result.english_text),
        constraints=len(result.key_constraints),
    )
    return result
