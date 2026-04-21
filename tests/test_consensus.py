"""Unit tests for Stage 5 consensus logic."""

from __future__ import annotations

from quant_solver.models import (
    CriticOutput,
    IntakeResult,
    ProblemType,
    SolverOutput,
    VerificationResult,
)
from quant_solver.stages.consensus import compute_consensus


def _problem() -> IntakeResult:
    return IntakeResult(
        source_language="en",
        original_text="test",
        english_text="test",
        extracted_math="",
        problem_type=ProblemType.PROBABILITY,
        key_constraints=[],
        requested_format="number",
    )


def _solver(name: str, answer: str, confidence: float = 0.9) -> SolverOutput:
    return SolverOutput(
        agent_name=name,
        answer=answer,
        reasoning="",
        assumptions=[],
        confidence=confidence,
        approach=name,
    )


def _critic(recommendation: str = "NEEDS_HUMAN_REVIEW") -> CriticOutput:
    return CriticOutput(
        potential_flaws=[],
        flagged_traps=[],
        ranked_candidates=[],
        recommendation=recommendation,
    )


def _pass(answer: str) -> VerificationResult:
    return VerificationResult(
        candidate_answer=answer, method="sympy_equivalence", passed=True, details="ok"
    )


def test_high_confidence_when_all_agree_verify_pass_critic_approves():
    cands = [_solver(f"a{i}", "4/3") for i in range(5)]
    verifs = [_pass("4/3")]
    critic = _critic(recommendation="4/3")
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    assert final.confidence == "high"
    assert final.agreement_level == 1.0
    assert final.verification_passed
    assert final.critic_approved


def test_medium_when_three_agree_and_verification_passes():
    cands = [
        _solver("a", "4/3"),
        _solver("b", "4/3"),
        _solver("c", "4/3"),
        _solver("d", "3/2"),
        _solver("e", "3/2"),
    ]
    verifs = [_pass("4/3")]
    critic = _critic(recommendation="NEEDS_HUMAN_REVIEW")
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    assert final.answer == "4/3"
    assert final.confidence == "medium"


def test_low_when_disagreement_heavy():
    cands = [
        _solver("a", "1"),
        _solver("b", "2"),
        _solver("c", "3"),
        _solver("d", "4"),
        _solver("e", "5"),
    ]
    verifs: list[VerificationResult] = []
    critic = _critic()
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    assert final.confidence == "low"


def test_equivalent_forms_cluster_together():
    # These two expressions are algebraically identical.
    cands = [
        _solver("a", "(9*sqrt(2)-6)/7"),
        _solver("b", "3*sqrt(2)/(3+sqrt(2))"),
        _solver("c", "(9*sqrt(2)-6)/7"),
        _solver("d", "(9*sqrt(2)-6)/7"),
        _solver("e", "wrong"),
    ]
    verifs = [_pass("(9*sqrt(2)-6)/7")]
    critic = _critic(recommendation="(9*sqrt(2)-6)/7")
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    # Agent b's "3*sqrt(2)/(3+sqrt(2))" should cluster with the others.
    assert final.agreement_level == 0.8  # 4 of 5


def test_critic_override_picks_recommendation():
    # The critic contradicts the solver plurality — consensus follows the critic.
    cands = [_solver("a", "wrong"), _solver("b", "wrong"), _solver("c", "right")]
    verifs = [_pass("right")]
    critic = _critic(recommendation="right")
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    assert final.answer == "right"


def test_empty_solver_answers_ignored():
    cands = [
        _solver("a", "4/3"),
        _solver("b", ""),
        _solver("c", "4/3"),
    ]
    verifs = [_pass("4/3")]
    critic = _critic(recommendation="4/3")
    final = compute_consensus(_problem(), cands, verifs, critic, audit_trail_path="/tmp/x")
    # Agreement is over the two solvers that actually returned an answer.
    assert final.agreement_level == 1.0
