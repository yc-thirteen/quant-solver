"""Pydantic data models for the solver pipeline.

Every LLM-produced artifact in the pipeline is validated through one of these
models, so that downstream stages can rely on a strict, typed contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProblemType(str, Enum):
    """Coarse classification of the problem, used to route verification."""

    PROBABILITY = "probability"
    LINEAR_ALGEBRA = "linear_algebra"
    COMBINATORICS = "combinatorics"
    OPTIMIZATION = "optimization"
    GEOMETRY = "geometry"
    NUMBER_THEORY = "number_theory"
    OTHER = "other"


class IntakeResult(BaseModel):
    """Output of Stage 1. Everything downstream reads from this."""

    source_language: str = Field(
        ...,
        description="ISO 639-1 code of the detected source language ('zh', 'en', 'ja', ...). "
        "Use 'mixed' if multiple languages appear.",
    )
    original_text: str = Field(..., description="Verbatim transcription in the source language.")
    english_text: str = Field(..., description="Full English translation of the problem statement.")
    extracted_math: str = Field(
        ...,
        description="LaTeX or plain math notation for all formulas in the problem (language-neutral).",
    )
    problem_type: ProblemType
    key_constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints in English, e.g. 'integer solutions only', 'n >= 1'.",
    )
    requested_format: str = Field(
        ...,
        description="Requested answer format in English, e.g. 'decimal to 2 sig figs', 'closed form'.",
    )


class SolverOutput(BaseModel):
    """Output from a single solver agent. All fields are English."""

    agent_name: str
    answer: str = Field(..., description="Canonical symbolic or numeric answer.")
    answer_latex: str | None = None
    answer_decimal: float | None = None
    reasoning: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    approach: str = Field(
        ...,
        description="One of: symbolic | brute_force | monte_carlo | known_results | symmetry",
    )
    # Optional executable Python that the verifier may run.
    simulation_code: str | None = None


class VerificationResult(BaseModel):
    """Output from a single verification attempt for a single candidate answer."""

    candidate_answer: str
    method: str = Field(
        ...,
        description="e.g. 'sympy_substitute', 'monte_carlo', 'brute_force_n10'.",
    )
    passed: bool
    details: str = ""
    numerical_error: float | None = None


class CriticOutput(BaseModel):
    """Adversarial critic review of all solver outputs."""

    potential_flaws: list[str] = Field(default_factory=list)
    flagged_traps: list[str] = Field(
        default_factory=list,
        description="Short trap tags, e.g. 'continuous_vs_discrete', 'boundary_case'.",
    )
    ranked_candidates: list[str] = Field(
        default_factory=list,
        description="Candidate answers ordered from most to least plausible.",
    )
    recommendation: str = Field(
        ...,
        description="Recommended final answer, or 'NEEDS_HUMAN_REVIEW'.",
    )


class FinalAnswer(BaseModel):
    """Top-level pipeline output."""

    answer: str
    confidence: Literal["high", "medium", "low"]
    agreement_level: float = Field(
        ...,
        description="Fraction of solvers that agreed with the final answer.",
    )
    verification_passed: bool
    critic_approved: bool
    all_candidates: list[SolverOutput]
    audit_trail_path: str
    # Attached for convenience so CLI can format without re-reading the audit dir.
    intake: IntakeResult | None = None
    verifications: list[VerificationResult] = Field(default_factory=list)
    critic: CriticOutput | None = None
