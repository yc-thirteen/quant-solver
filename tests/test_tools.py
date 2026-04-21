"""Unit tests for pure-Python verification tools."""

from __future__ import annotations

from quant_solver.tools.brute_force import verify_brute_force
from quant_solver.tools.monte_carlo import verify_monte_carlo
from quant_solver.tools.sandbox import run_python
from quant_solver.tools.sympy_tools import (
    verify_equivalence,
    verify_numeric_close,
    verify_psd_condition,
)


def test_sympy_equivalence_equal_forms():
    # Two algebraically identical forms of the same answer.
    r = verify_equivalence("(9*sqrt(2)-6)/7", "3*sqrt(2)/(3+sqrt(2))")
    assert r.passed, r.details


def test_sympy_equivalence_differ():
    r = verify_equivalence("1/2", "1/3")
    assert not r.passed


def test_sympy_numeric_close_pass():
    r = verify_numeric_close("2/3", expected_decimal=0.6667, tol=1e-3)
    assert r.passed


def test_sympy_numeric_close_fail():
    r = verify_numeric_close("2/3", expected_decimal=0.5, tol=1e-3)
    assert not r.passed


def test_psd_4x4_min_r():
    matrix_spec = "Matrix([[1, r, r, r], [r, 1, r, r], [r, r, 1, r], [r, r, r, 1]])"
    # At r = -1/3 the matrix is PSD with a zero eigenvalue (1 + 3r = 0).
    r = verify_psd_condition("-1/3", matrix_spec, variable="r")
    assert r.passed, r.details


def test_psd_4x4_r_below_threshold_fails():
    matrix_spec = "Matrix([[1, r, r, r], [r, 1, r, r], [r, r, 1, r], [r, r, r, 1]])"
    # At r = -1/2 the matrix is NOT PSD (1 + 3*(-1/2) = -1/2 < 0).
    r = verify_psd_condition("-1/2", matrix_spec, variable="r")
    assert not r.passed


def test_sandbox_runs_simple_code():
    res = run_python("print(1 + 1)", timeout_s=10)
    assert res.returncode == 0
    assert "2" in res.stdout
    assert not res.timed_out


def test_sandbox_timeout():
    res = run_python("while True: pass", timeout_s=1)
    assert res.timed_out


def test_monte_carlo_verify_passes_for_matching_sim():
    sim = (
        "import numpy as np\n"
        "rng = np.random.default_rng(42)\n"
        "x = rng.standard_normal(1_000_000)\n"
        "print(float((x < -2).mean()))\n"
    )
    r = verify_monte_carlo(
        candidate_answer="0.0228",
        candidate_decimal=0.0228,
        simulation_code=sim,
        tolerance=0.05,
    )
    assert r.passed, r.details


def test_monte_carlo_verify_fails_on_mismatch():
    sim = "print(0.5)\n"
    r = verify_monte_carlo(
        candidate_answer="0.1",
        candidate_decimal=0.1,
        simulation_code=sim,
        tolerance=0.01,
    )
    assert not r.passed


def test_brute_force_verify_passes_for_sum_formula():
    # Verify 1+2+...+n == n(n+1)/2 for n=100.
    code = (
        "from fractions import Fraction\n"
        "n = 100\n"
        "print(float(sum(Fraction(i) for i in range(1, n + 1))))\n"
    )
    r = verify_brute_force(candidate_answer="100*101/2", enumeration_code=code)
    assert r.passed, r.details


def test_brute_force_verify_fails_on_mismatch():
    code = "print(42.0)\n"
    r = verify_brute_force(candidate_answer="41", enumeration_code=code, tolerance=1e-3)
    assert not r.passed
