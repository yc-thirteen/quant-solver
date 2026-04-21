"""Thin wrapper around the Anthropic SDK with retries, timing, and structured logging.

Keeps all model I/O in one place so the rest of the pipeline can stay testable.
"""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Any

import structlog
from anthropic import AsyncAnthropic, APIError

from .config import Config
from .utils import extract_json

log = structlog.get_logger(__name__)


_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def load_image_block(image_path: Path) -> dict[str, Any]:
    """Load an image file and format it as an Anthropic content block.

    Args:
        image_path: Path to a PNG, JPG, or WebP image.

    Returns:
        A dict with ``type="image"`` and base64-encoded source data.

    Raises:
        ValueError: If the file extension is not a supported image format.
        FileNotFoundError: If the image does not exist.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported image format: {image_path.suffix}")
    data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


class AnthropicClient:
    """Async wrapper with retries, timeouts, and log-friendly call IDs."""

    def __init__(self, config: Config) -> None:
        if not config.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Export it or put it in .env."
            )
        self._client = AsyncAnthropic(api_key=config.anthropic_api_key)
        self._config = config

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user_blocks: list[dict[str, Any]],
        max_tokens: int | None = None,
        timeout_s: int | None = None,
        caller: str = "unknown",
    ) -> str:
        """Run a single chat completion and return the concatenated text.

        Args:
            model: Anthropic model ID (e.g. ``"claude-opus-4-7"``).
            system: System prompt.
            user_blocks: List of content blocks (text and/or image).
            max_tokens: Override for ``config.max_tokens``.
            timeout_s: Override for ``config.solver_timeout_s``.
            caller: Free-form identifier used in structured logs.

        Returns:
            The assistant's text output. Non-text blocks are ignored.
        """
        max_tokens = max_tokens or self._config.max_tokens
        timeout_s = timeout_s or self._config.solver_timeout_s

        last_exc: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self._client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=[{"role": "user", "content": user_blocks}],
                    ),
                    timeout=timeout_s,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", None) == "text"
                )
                log.info(
                    "llm_call",
                    caller=caller,
                    model=model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_blocks=len(user_blocks),
                    output_chars=len(text),
                    input_tokens=getattr(response.usage, "input_tokens", None),
                    output_tokens=getattr(response.usage, "output_tokens", None),
                )
                return text
            except (APIError, asyncio.TimeoutError) as exc:
                last_exc = exc
                latency_ms = int((time.perf_counter() - started) * 1000)
                log.warning(
                    "llm_call_failed",
                    caller=caller,
                    model=model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    error=type(exc).__name__,
                    message=str(exc)[:500],
                )
                if attempt < self._config.max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

        assert last_exc is not None
        raise last_exc

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user_blocks: list[dict[str, Any]],
        max_tokens: int | None = None,
        timeout_s: int | None = None,
        caller: str = "unknown",
    ) -> dict[str, Any]:
        """Like ``complete``, but parse the response as JSON with one repair pass.

        If the first response is not parseable, send a follow-up asking the model
        to fix its JSON (without re-reasoning). This handles the common case where
        a model wraps JSON in prose despite instructions.

        Raises:
            ValueError: If JSON cannot be parsed after the repair attempt.
        """
        text = await self.complete(
            model=model,
            system=system,
            user_blocks=user_blocks,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            caller=caller,
        )
        try:
            return extract_json(text)
        except (ValueError, Exception) as exc:  # json.JSONDecodeError subclasses ValueError
            log.warning("json_parse_failed_first_attempt", caller=caller, error=str(exc)[:200])

        repair_blocks = user_blocks + [
            {"type": "text", "text": "Your last reply did not contain a parseable JSON object."},
            {"type": "text", "text": f"Your reply was:\n\n{text}"},
            {
                "type": "text",
                "text": (
                    "Reply again with ONLY a valid JSON object matching the schema. "
                    "Do NOT include any prose, markdown fences, or commentary."
                ),
            },
        ]
        repaired = await self.complete(
            model=model,
            system=system,
            user_blocks=repair_blocks,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            caller=f"{caller}/repair",
        )
        return extract_json(repaired)
