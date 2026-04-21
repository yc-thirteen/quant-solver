"""SymPy-based verification helpers.

These are pure functions. No LLM calls. They take a candidate answer and
information about the problem and return a ``VerificationResult``.
"""

from __future__ import annotations

import sympy as sp

from ..models import VerificationResult


def _parse_answer(answer: str) -> sp.Expr | None:
    """Best-effort parse of a string answer into a SymPy expression.

    Returns:
        A SymPy expression, or ``None`` if parsing fails.
    """
    s = answer.strip()
    if not s:
        return None
    if s.endswith("%"):
        try:
            return sp.Rational(str(float(s[:-1].strip()) / 100.0))
        except ValueError:
            return None
    try:
        return sp.sympify(s.replace("^", "**"), rational=True)
    except (sp.SympifyError, TypeError, ValueError, SyntaxError):
        return None


def verify_equivalence(
    candidate_answer: str,
    reference_expression: str,
) -> VerificationResult:
    """Check that ``candidate_answer`` equals ``reference_expression`` symbolically.

    Used when a separate derivation has produced a reference closed form and we
    want to confirm another solver's answer matches it.

    Args:
        candidate_answer: A solver's answer.
        reference_expression: An independently-derived reference form.

    Returns:
        A ``VerificationResult`` with ``method='sympy_equivalence'``.
    """
    method = "sympy_equivalence"
    c = _parse_answer(candidate_answer)
    r = _parse_answer(reference_expression)
    if c is None or r is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not parse answer or reference: {candidate_answer!r} vs {reference_expression!r}",
        )
    try:
        diff = sp.simplify(c - r)
        if diff == 0:
            return VerificationResult(
                candidate_answer=candidate_answer,
                method=method,
                passed=True,
                details=f"simplify({candidate_answer} - {reference_expression}) == 0",
                numerical_error=0.0,
            )
        num_err = float(abs(sp.N(diff)))
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=num_err < 1e-9,
            details=f"Nonzero symbolic difference; numeric |diff|={num_err:g}",
            numerical_error=num_err,
        )
    except (TypeError, ValueError) as exc:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"SymPy error: {exc}",
        )


def verify_numeric_close(
    candidate_answer: str,
    expected_decimal: float,
    tol: float = 1e-3,
) -> VerificationResult:
    """Check that ``candidate_answer`` evaluates close to ``expected_decimal``.

    Useful when a Monte Carlo or brute-force tool produced a numeric reference
    and we want to confirm the symbolic candidate matches.
    """
    method = "sympy_numeric_close"
    c = _parse_answer(candidate_answer)
    if c is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not parse {candidate_answer!r}",
        )
    try:
        val = float(sp.N(c))
    except (TypeError, ValueError) as exc:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not evaluate: {exc}",
        )
    err = abs(val - expected_decimal)
    return VerificationResult(
        candidate_answer=candidate_answer,
        method=method,
        passed=err < tol * max(1.0, abs(expected_decimal)),
        details=f"|{val} - {expected_decimal}| = {err:g}",
        numerical_error=err,
    )


def verify_psd_condition(
    candidate_answer: str,
    matrix_spec: str,
    variable: str = "r",
) -> VerificationResult:
    """Verify a "minimum r such that M(r) is PSD" type of answer.

    Args:
        candidate_answer: The candidate minimum value of the parameter.
        matrix_spec: A SymPy-parseable string for the matrix in terms of ``variable``.
            Example: ``"Matrix([[1, r, r, r], [r, 1, r, r], [r, r, 1, r], [r, r, r, 1]])"``.
        variable: Name of the scalar parameter.

    Returns:
        A ``VerificationResult``. Passes when the matrix is PSD at ``candidate_answer``
        and has a zero eigenvalue there (boundary of the PSD cone).
    """
    method = "sympy_psd"
    c = _parse_answer(candidate_answer)
    if c is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not parse {candidate_answer!r}",
        )
    try:
        var = sp.Symbol(variable)
        m = sp.sympify(matrix_spec, locals={variable: var}, rational=True)
        if not isinstance(m, sp.Matrix):
            return VerificationResult(
                candidate_answer=candidate_answer,
                method=method,
                passed=False,
                details="matrix_spec did not evaluate to a Matrix",
            )
        evs = list(m.subs(var, c).eigenvals().keys())
        numeric_evs = [float(sp.N(e)) for e in evs]
        min_ev = min(numeric_evs)
        passed = min_ev >= -1e-9 and min(abs(ev) for ev in numeric_evs) < 1e-6
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=passed,
            details=f"eigenvalues at {variable}={candidate_answer}: {numeric_evs}; min={min_ev:g}",
            numerical_error=abs(min_ev) if min_ev < 0 else 0.0,
        )
    except (sp.SympifyError, TypeError, ValueError) as exc:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"SymPy error: {exc}",
        )
