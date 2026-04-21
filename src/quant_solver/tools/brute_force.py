"""Brute-force verification: run solver-provided enumeration code in a sandbox.

The "tool" is minimal — the real work is done by code the solver wrote. This
module exists as a thin, testable wrapper around the sandbox, with the same
interface shape as ``monte_carlo.py`` so ``verifier.py`` can dispatch uniformly.
"""

from __future__ import annotations

from ..models import VerificationResult
from .monte_carlo import _last_float_in
from .sandbox import run_python
from .sympy_tools import _parse_answer


def verify_brute_force(
    candidate_answer: str,
    enumeration_code: str,
    *,
    tolerance: float = 1e-6,
    timeout_s: int = 60,
) -> VerificationResult:
    """Run solver-provided brute-force enumeration and compare the output.

    The enumeration code must print its final computed result as the last
    number on stdout. Exact arithmetic (``fractions.Fraction``, SymPy) is
    recommended; the verifier still only compares decimals at the end.

    Args:
        candidate_answer: The solver's closed-form / conjectured answer.
        enumeration_code: Python source written by a brute-force solver.
        tolerance: Relative tolerance (most exact enumerations match to 1e-9,
            but we leave headroom for floating-point artefacts).
        timeout_s: Wall-clock budget for the subprocess.

    Returns:
        A ``VerificationResult`` with ``method='brute_force'``.
    """
    method = "brute_force"
    if not enumeration_code or not enumeration_code.strip():
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details="No enumeration code supplied.",
        )

    sandbox = run_python(enumeration_code, timeout_s=timeout_s)
    if sandbox.timed_out:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Enumeration timed out after {timeout_s}s",
        )
    if sandbox.returncode != 0:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Enumeration exited with code {sandbox.returncode}. stderr: {sandbox.stderr[-500:]}",
        )

    empirical = _last_float_in(sandbox.stdout)
    if empirical is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"No float found in stdout. Last 300 chars: {sandbox.stdout[-300:]}",
        )

    expr = _parse_answer(candidate_answer)
    if expr is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not parse candidate for comparison; empirical={empirical:g}",
        )
    try:
        cand_val = float(expr.evalf()) if hasattr(expr, "evalf") else float(expr)
    except (TypeError, ValueError):
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not evaluate candidate; empirical={empirical:g}",
        )

    err = abs(empirical - cand_val)
    passed = err < tolerance * max(1.0, abs(cand_val))
    return VerificationResult(
        candidate_answer=candidate_answer,
        method=method,
        passed=passed,
        details=f"empirical={empirical:g}, candidate={cand_val:g}, |diff|={err:g}, tol={tolerance}",
        numerical_error=err,
    )
