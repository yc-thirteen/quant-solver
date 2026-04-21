"""Monte Carlo verification: run solver-provided simulation code in a sandbox."""

from __future__ import annotations

import re

from ..models import VerificationResult
from .sandbox import run_python


_LAST_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _last_float_in(stdout: str) -> float | None:
    """Return the last floating-point number printed on stdout, or ``None``."""
    matches = _LAST_FLOAT_RE.findall(stdout)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def verify_monte_carlo(
    candidate_answer: str,
    candidate_decimal: float | None,
    simulation_code: str,
    *,
    tolerance: float = 0.01,
    timeout_s: int = 30,
) -> VerificationResult:
    """Run a Monte Carlo simulation and compare the result to a candidate decimal.

    Args:
        candidate_answer: The candidate answer string (preserved verbatim on the result).
        candidate_decimal: The numeric value of the candidate to compare against.
            If ``None``, the function attempts to parse it from the answer string.
        simulation_code: Python source produced by a solver. It should print its
            final numeric estimate as the last number on stdout.
        tolerance: Absolute tolerance for the comparison (after scaling by |candidate|).
        timeout_s: Subprocess timeout.

    Returns:
        A ``VerificationResult`` with ``method='monte_carlo'``.
    """
    method = "monte_carlo"
    if not simulation_code or not simulation_code.strip():
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details="No simulation code supplied.",
        )

    sandbox = run_python(simulation_code, timeout_s=timeout_s)
    if sandbox.timed_out:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Simulation timed out after {timeout_s}s",
        )
    if sandbox.returncode != 0:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Simulation exited with code {sandbox.returncode}. stderr: {sandbox.stderr[-500:]}",
        )

    empirical = _last_float_in(sandbox.stdout)
    if empirical is None:
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"Could not parse a float from simulation stdout. Last 300 chars: {sandbox.stdout[-300:]}",
        )

    if candidate_decimal is None:
        # Try to parse the answer itself.
        from .sympy_tools import _parse_answer  # local import to avoid cycle at module top

        expr = _parse_answer(candidate_answer)
        if expr is not None:
            try:
                candidate_decimal = float(expr.evalf()) if hasattr(expr, "evalf") else float(expr)
            except (TypeError, ValueError):
                candidate_decimal = None

    if candidate_decimal is None:
        # We can't compare numerically; report the empirical value so the critic sees it.
        return VerificationResult(
            candidate_answer=candidate_answer,
            method=method,
            passed=False,
            details=f"No candidate decimal to compare against; empirical={empirical:g}",
            numerical_error=None,
        )

    err = abs(empirical - candidate_decimal)
    passed = err < tolerance * max(1.0, abs(candidate_decimal))
    return VerificationResult(
        candidate_answer=candidate_answer,
        method=method,
        passed=passed,
        details=f"empirical={empirical:g}, candidate={candidate_decimal:g}, |diff|={err:g}, tol={tolerance}",
        numerical_error=err,
    )
