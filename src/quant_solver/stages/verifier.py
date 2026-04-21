"""Stage 3: Verification.

Deduplicates candidate answers and dispatches each one to the appropriate
verification tool based on ``problem_type`` and what simulation / enumeration
code the originating solver provided. No LLM calls in this stage.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import structlog

from ..models import IntakeResult, ProblemType, SolverOutput, VerificationResult
from ..tools.brute_force import verify_brute_force
from ..tools.monte_carlo import verify_monte_carlo
from ..tools.sympy_tools import (
    _parse_answer,
    verify_equivalence,
    verify_numeric_close,
)

log = structlog.get_logger(__name__)


def _pick_simulation_code(candidates_for_answer: list[SolverOutput]) -> str | None:
    """Return the first non-empty ``simulation_code`` among solvers for this answer."""
    for c in candidates_for_answer:
        if c.simulation_code and c.simulation_code.strip():
            return c.simulation_code
    return None


def _first_decimal(candidates_for_answer: list[SolverOutput]) -> float | None:
    """Return the first non-null ``answer_decimal`` among solvers for this answer."""
    for c in candidates_for_answer:
        if c.answer_decimal is not None:
            return c.answer_decimal
    return None


def _group_by_answer(candidates: Iterable[SolverOutput]) -> dict[str, list[SolverOutput]]:
    """Group solver outputs by their raw ``answer`` string."""
    groups: dict[str, list[SolverOutput]] = {}
    for c in candidates:
        groups.setdefault(c.answer.strip(), []).append(c)
    return groups


def _verify_one(
    problem: IntakeResult,
    answer: str,
    supporters: list[SolverOutput],
    all_candidates: list[SolverOutput],
) -> list[VerificationResult]:
    """Run all applicable verification methods for a single candidate answer.

    Args:
        problem: The intake result (used for problem-type routing).
        answer: The candidate answer string.
        supporters: Solver outputs that produced this exact ``answer`` (used to
            pull simulation code / decimal).
        all_candidates: All solver outputs (used to source simulation code from
            other solvers when the supporters did not provide any).

    Returns:
        A list of ``VerificationResult``. Possibly empty if no applicable
        method could be run (the critic will flag this).
    """
    results: list[VerificationResult] = []

    # (1) Monte Carlo — only for probability problems, and only if ANY solver
    # provided simulation code (Agent C is the primary source but brute-force
    # solvers may also include runnable code).
    if problem.problem_type == ProblemType.PROBABILITY:
        sim_code = _pick_simulation_code(all_candidates)
        if sim_code is not None:
            candidate_decimal = _first_decimal(supporters) or _first_decimal(all_candidates)
            results.append(
                verify_monte_carlo(
                    candidate_answer=answer,
                    candidate_decimal=candidate_decimal,
                    simulation_code=sim_code,
                )
            )

    # (2) Brute force — useful for combinatorics / number theory / discrete
    # optimisation. Pulls Agent B's enumeration code if present.
    if problem.problem_type in {
        ProblemType.COMBINATORICS,
        ProblemType.NUMBER_THEORY,
        ProblemType.OPTIMIZATION,
    }:
        # Prefer explicit brute-force code from Agent B.
        brute_code = None
        for c in all_candidates:
            if c.approach == "brute_force" and c.simulation_code:
                brute_code = c.simulation_code
                break
        if brute_code is None:
            brute_code = _pick_simulation_code(all_candidates)
        if brute_code is not None:
            results.append(
                verify_brute_force(
                    candidate_answer=answer,
                    enumeration_code=brute_code,
                )
            )

    # (3) Cross-solver symbolic equivalence. Pick the reference as the highest-
    # confidence solver whose answer differs from this candidate; if they
    # simplify to the same thing, that's a second opinion.
    others = [c for c in all_candidates if c.answer.strip() != answer and c.answer.strip()]
    if others:
        ref = max(others, key=lambda c: c.confidence)
        results.append(verify_equivalence(answer, ref.answer))

    # (4) Numeric close check against Monte Carlo output, if we have one and
    # it printed a decimal but didn't pass the candidate-specific MC check.
    # Done implicitly by verify_monte_carlo; nothing to add here.

    # (5) If nothing ran, produce a stub "no_applicable_method" result so the
    # audit trail shows the attempt.
    if not results:
        results.append(
            VerificationResult(
                candidate_answer=answer,
                method="no_applicable_method",
                passed=False,
                details=(
                    f"No verification method available for problem_type={problem.problem_type.value} "
                    "with the provided solver outputs."
                ),
            )
        )

    return results


async def verify_candidates(
    problem: IntakeResult,
    candidates: list[SolverOutput],
) -> list[VerificationResult]:
    """Verify the unique candidate answers from the solver stage.

    Args:
        problem: The intake result.
        candidates: All solver outputs from Stage 2.

    Returns:
        A flat list of verification results across all unique candidate answers.
    """
    # Drop empty answers (solver failures) — they are not verifiable.
    real_candidates = [c for c in candidates if c.answer and c.answer.strip()]
    if not real_candidates:
        log.warning("no_verifiable_candidates")
        return []

    groups = _group_by_answer(real_candidates)

    # Verification tools are blocking Python work; run them in a thread pool
    # so the event loop stays free for parallel solver / critic calls.
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _verify_one, problem, answer, supporters, real_candidates)
        for answer, supporters in groups.items()
    ]
    nested = await asyncio.gather(*tasks)
    flat = [r for group in nested for r in group]

    log.info(
        "verification_done",
        unique_candidates=len(groups),
        total_results=len(flat),
        passed=sum(1 for r in flat if r.passed),
    )
    return flat
