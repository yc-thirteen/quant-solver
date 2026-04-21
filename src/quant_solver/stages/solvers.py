"""Stage 2: Parallel Solvers.

Five agents, each with its own prompt, run concurrently via ``asyncio.gather``.
Each receives ONLY the ``IntakeResult`` (never each other's outputs) so that
later consensus is a meaningful signal rather than groupthink.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import structlog

from ..anth_client import AnthropicClient
from ..config import Config
from ..models import IntakeResult, ProblemType, SolverOutput
from ..utils import read_prompt

log = structlog.get_logger(__name__)


_AGENT_PROMPT_FILES: dict[str, str] = {
    "symbolic": "solver_symbolic",
    "brute_force": "solver_brute_force",
    "monte_carlo": "solver_monte_carlo",
    "known_results": "solver_known_results",
    "symmetry": "solver_symmetry",
}


def _problem_brief(problem: IntakeResult) -> str:
    """Format the problem for a solver's user message. English only."""
    constraints = "\n".join(f"- {c}" for c in problem.key_constraints) or "(none listed)"
    return (
        f"## Problem (English translation)\n{problem.english_text}\n\n"
        f"## Extracted math\n{problem.extracted_math}\n\n"
        f"## Problem type\n{problem.problem_type.value}\n\n"
        f"## Constraints\n{constraints}\n\n"
        f"## Requested answer format\n{problem.requested_format}\n"
    )


async def _run_one_solver(
    agent_name: str,
    problem: IntakeResult,
    *,
    client: AnthropicClient,
    config: Config,
) -> SolverOutput:
    """Run a single solver agent and return its validated output."""
    prompt_name = _AGENT_PROMPT_FILES[agent_name]
    system = read_prompt(prompt_name)
    user_blocks = [{"type": "text", "text": _problem_brief(problem)}]

    try:
        raw = await client.complete_json(
            model=config.solver_model,
            system=system,
            user_blocks=user_blocks,
            caller=f"solver/{agent_name}",
        )
    except Exception as exc:  # noqa: BLE001 — we want to survive one solver's failure
        log.error("solver_failed", agent=agent_name, error=type(exc).__name__, message=str(exc)[:300])
        return SolverOutput(
            agent_name=agent_name,
            answer="",
            reasoning=f"Solver failed with {type(exc).__name__}: {exc}",
            assumptions=[],
            confidence=0.0,
            approach=agent_name,
        )

    raw.setdefault("agent_name", agent_name)
    raw.setdefault("approach", agent_name)
    # Guard against models returning non-string answers.
    if "answer" in raw and not isinstance(raw["answer"], str):
        raw["answer"] = str(raw["answer"])
    return SolverOutput.model_validate(raw)


async def run_solvers(
    problem: IntakeResult,
    *,
    client: AnthropicClient,
    config: Config,
) -> list[SolverOutput]:
    """Run all applicable solvers in parallel.

    Monte Carlo is skipped for non-probabilistic problems.

    Args:
        problem: Intake result to solve.
        client: Anthropic client.
        config: Pipeline configuration.

    Returns:
        List of ``SolverOutput`` objects, one per agent that ran.
    """
    agents = ["symbolic", "brute_force", "monte_carlo", "known_results", "symmetry"]
    if problem.problem_type != ProblemType.PROBABILITY:
        agents.remove("monte_carlo")

    tasks: list[Awaitable[SolverOutput]] = [
        _run_one_solver(name, problem, client=client, config=config) for name in agents
    ]
    results = await asyncio.gather(*tasks)

    log.info(
        "solvers_done",
        count=len(results),
        answers=[r.answer for r in results],
    )
    return list(results)
