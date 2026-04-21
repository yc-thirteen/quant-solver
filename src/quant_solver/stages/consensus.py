"""Stage 5: Consensus.

Pure Python, no LLM. Aggregates solver answers, verification results, and the
critic's recommendation into a single ``FinalAnswer`` with a confidence label.

Confidence rules:
    - **high**: >= 4 solvers agree AND verification passed AND critic approved.
    - **medium**: 3 solvers agree AND (verification passed OR critic approved).
    - **low**: everything else.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from ..models import (
    CriticOutput,
    FinalAnswer,
    IntakeResult,
    SolverOutput,
    VerificationResult,
)
from ..utils import answers_equivalent, normalize_answer


def _cluster_answers(candidates: list[SolverOutput]) -> dict[str, list[SolverOutput]]:
    """Group candidates by *equivalent* answer.

    Two solvers that report ``"(9*sqrt(2)-6)/7"`` and ``"3*sqrt(2)/(3+sqrt(2))"``
    should count as agreeing. We canonicalize via SymPy simplification and then
    group by the canonical string. Empty answers (solver failures) are dropped.
    """
    real = [c for c in candidates if c.answer and c.answer.strip()]
    if not real:
        return {}

    # Greedy clustering using answers_equivalent for equivalence testing.
    clusters: list[list[SolverOutput]] = []
    cluster_keys: list[str] = []
    for c in real:
        matched = False
        for i, key in enumerate(cluster_keys):
            if answers_equivalent(c.answer, key):
                clusters[i].append(c)
                matched = True
                break
        if not matched:
            clusters.append([c])
            cluster_keys.append(c.answer)

    # Represent each cluster by its canonical (normalized) form.
    return {normalize_answer(key): group for key, group in zip(cluster_keys, clusters)}


def _verification_passed_for(answer: str, verifications: list[VerificationResult]) -> bool:
    """Return True if at least one verification passed for an equivalent answer.

    "No applicable method" results don't count as passing.
    """
    for v in verifications:
        if v.method == "no_applicable_method":
            continue
        if v.passed and answers_equivalent(v.candidate_answer, answer):
            return True
    return False


def _choose_final(
    clusters: dict[str, list[SolverOutput]],
    verifications: list[VerificationResult],
    critic: CriticOutput,
) -> tuple[str, list[SolverOutput]]:
    """Pick the final answer and the list of solvers that agreed on it."""
    if not clusters:
        return ("NEEDS_HUMAN_REVIEW", [])

    # 1. If the critic recommended a concrete answer that matches a cluster, use it.
    rec = critic.recommendation.strip()
    if rec and rec != "NEEDS_HUMAN_REVIEW":
        for key, group in clusters.items():
            if answers_equivalent(rec, key) or answers_equivalent(
                rec, group[0].answer
            ):
                return (group[0].answer, group)
        # Critic recommended something no solver produced — keep it but return no cluster.
        return (rec, [])

    # 2. Otherwise, pick the largest cluster. Break ties by max summed confidence.
    best_key = max(
        clusters,
        key=lambda k: (len(clusters[k]), sum(c.confidence for c in clusters[k])),
    )
    return (clusters[best_key][0].answer, clusters[best_key])


def _confidence_label(
    n_agree: int,
    n_solvers: int,
    verification_passed: bool,
    critic_approved: bool,
) -> Literal["high", "medium", "low"]:
    if n_agree >= 4 and verification_passed and critic_approved:
        return "high"
    if n_agree >= 3 and (verification_passed or critic_approved):
        return "medium"
    return "low"


def compute_consensus(
    problem: IntakeResult,
    candidates: list[SolverOutput],
    verifications: list[VerificationResult],
    critic: CriticOutput,
    *,
    audit_trail_path: str,
) -> FinalAnswer:
    """Merge solver, verifier, and critic outputs into a final answer.

    Args:
        problem: The intake result (attached for convenience).
        candidates: All solver outputs.
        verifications: All verification results.
        critic: The critic's review.
        audit_trail_path: Directory where per-stage JSON is written.

    Returns:
        A ``FinalAnswer``.
    """
    clusters = _cluster_answers(candidates)
    final_answer, supporters = _choose_final(clusters, verifications, critic)
    n_solvers = len([c for c in candidates if c.answer and c.answer.strip()])
    n_agree = len(supporters)
    agreement_level = (n_agree / n_solvers) if n_solvers else 0.0

    verification_passed = _verification_passed_for(final_answer, verifications)
    critic_approved = critic.recommendation.strip() not in {"", "NEEDS_HUMAN_REVIEW"} and (
        not supporters or answers_equivalent(critic.recommendation, final_answer)
    )

    confidence = _confidence_label(n_agree, n_solvers, verification_passed, critic_approved)

    return FinalAnswer(
        answer=final_answer,
        confidence=confidence,
        agreement_level=agreement_level,
        verification_passed=verification_passed,
        critic_approved=critic_approved,
        all_candidates=candidates,
        audit_trail_path=audit_trail_path,
        intake=problem,
        verifications=verifications,
        critic=critic,
    )
