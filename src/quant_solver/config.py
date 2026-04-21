"""Runtime configuration, loaded from environment variables.

Values can be overridden per-run by passing a ``Config`` instance to the
pipeline, which is useful for tests.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Pipeline configuration. Reads from env vars prefixed ``QS_``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="QS_",
        extra="ignore",
    )

    anthropic_api_key: str = ""

    solver_model: str = "claude-opus-4-7"
    intake_model: str = "claude-sonnet-4-6"
    critic_model: str = "claude-opus-4-7"

    max_tokens: int = 4096
    solver_timeout_s: int = 120
    monte_carlo_trials: int = 1_000_000
    brute_force_max_n: int = 20
    max_retries: int = 3

    # Where to write per-run audit trails.
    results_root: str = "results"

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        # ANTHROPIC_API_KEY has no prefix by convention — read it explicitly.
        import os

        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")


def load_config() -> Config:
    """Load a Config from the environment.

    Returns:
        A fresh ``Config`` instance.
    """
    return Config()
