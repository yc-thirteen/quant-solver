"""Stage 4: Adversarial Critic.

Sees everything. Its job is to find the flaw. Uses ``claude-opus-4-7``.
"""

from __future__ import annotations

import json

import structlog

from ..anth_client import AnthropicClient
from ..config import Config
from ..models import CriticOutput, IntakeResult, SolverOutput, VerificationResult
from ..utils import read_prompt

log = structlog.get_logger(__name__)


def _format_candidates(candidates: list[SolverOutput]) -> str:
    """Render solver outputs for the critic, stripped down to the relevant fields."""
    lines = []
    for c in candidates:
        lines.append(f"### Agent {c.agent_name} (approach={c.approach}, confidence={c.confidence:.2f})")
        lines.append(f"Answer: {c.answer!r}")
        if c.answer_decimal is not None:
            lines.append(f"Decimal: {c.answer_decimal}")
        lines.append(f"Assumptions: {c.assumptions}")
        lines.append(f"Reasoning: {c.reasoning}")
        lines.append("")
    return "\n".join(lines)


def _format_verifications(verifications: list[VerificationResult]) -> str:
    lines = []
    for v in verifications:
        lines.append(
            f"- candidate={v.candidate_answer!r} method={v.method} "
            f"passed={v.passed} numerical_error={v.numerical_error} — {v.details}"
        )
    return "\n".join(lines) if lines else "(no verification results)"


async def run_critic(
    problem: IntakeResult,
    candidates: list[SolverOutput],
    verifications: list[VerificationResult],
    *,
    client: AnthropicClient,
    config: Config,
) -> CriticOutput:
    """Run the adversarial critic and return a validated ``CriticOutput``."""
    system = read_prompt("critic")
    context = (
        "## Problem (English)\n"
        f"{problem.english_text}\n\n"
        "## Extracted math\n"
        f"{problem.extracted_math}\n\n"
        "## Constraints\n"
        + ("\n".join(f"- {c}" for c in problem.key_constraints) or "(none)")
        + "\n\n"
        f"## Requested format\n{problem.requested_format}\n\n"
        "## Candidate solver outputs\n"
        f"{_format_candidates(candidates)}\n"
        "## Verification results\n"
        f"{_format_verifications(verifications)}\n"
    )

    user_blocks = [{"type": "text", "text": context}]
    raw = await client.complete_json(
        model=config.critic_model,
        system=system,
        user_blocks=user_blocks,
        caller="critic",
    )
    try:
        result = CriticOutput.model_validate(raw)
    except Exception:  # noqa: BLE001
        log.warning("critic_json_invalid", raw=json.dumps(raw)[:500])
        raise

    log.info(
        "critic_done",
        flaws=len(result.potential_flaws),
        traps=result.flagged_traps,
        recommendation=result.recommendation,
    )
    return result
