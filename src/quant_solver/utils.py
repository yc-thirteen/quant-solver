"""Shared utilities: prompt loading, JSON extraction, answer normalization, logging."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import sympy as sp

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def configure_logging(verbose: bool = False) -> None:
    """Configure structlog to emit JSON to stderr and a human line to stdout if verbose.

    Args:
        verbose: If True, also emit a human-readable line per log record.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


@lru_cache(maxsize=None)
def read_prompt(name: str) -> str:
    """Load a prompt from ``prompts/<name>.md``.

    Args:
        name: Filename stem, e.g. ``"intake"`` for ``prompts/intake.md``.

    Returns:
        The file contents as a string.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def extract_json(text: str) -> dict[str, Any]:
    """Find and parse the first JSON object in a string.

    Models often wrap JSON in prose or markdown fences despite instructions
    to the contrary. This helper strips common wrappers and parses the first
    balanced ``{...}`` block.

    Args:
        text: Raw LLM output.

    Returns:
        The parsed JSON object.

    Raises:
        ValueError: If no JSON object can be parsed.
    """
    # Strip ```json ... ``` fences.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        # Find the first balanced brace block.
        start = text.find("{")
        if start < 0:
            raise ValueError("No JSON object found in model output.")
        depth = 0
        end = -1
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
        if end < 0:
            raise ValueError("Unbalanced braces in model output.")
        candidate = text[start:end]

    return json.loads(candidate)


def normalize_answer(answer: str) -> str:
    """Canonicalize an answer for equality comparison.

    Handles percentages (``"2.3%"`` → ``"0.023"``), strips whitespace, and
    attempts SymPy simplification. Returns a string representation that is
    stable across equivalent forms.

    Args:
        answer: Raw answer string.

    Returns:
        A canonical string form.
    """
    s = answer.strip()
    if not s:
        return ""

    # Percentage handling.
    if s.endswith("%"):
        try:
            value = float(s[:-1].strip()) / 100.0
            return _sympy_canonical(str(value))
        except ValueError:
            pass

    return _sympy_canonical(s)


def _sympy_canonical(s: str) -> str:
    """Attempt to reduce ``s`` to a canonical SymPy string.

    Falls back to the stripped original string on any parse error.
    """
    candidate = s.replace("^", "**")
    try:
        expr = sp.sympify(candidate, rational=True)
        simplified = sp.simplify(expr)
        return str(simplified)
    except (sp.SympifyError, TypeError, ValueError, SyntaxError):
        return s


def answers_equivalent(a: str, b: str, tol: float = 1e-6) -> bool:
    """Check whether two answer strings represent the same value.

    Tries symbolic equivalence via SymPy first. Falls back to numerical
    comparison within ``tol``.

    Args:
        a: First answer.
        b: Second answer.
        tol: Absolute numerical tolerance for the fallback check.

    Returns:
        True if the answers are equivalent.
    """
    if a.strip() == b.strip():
        return True

    # Expand percentages.
    def _pct(x: str) -> str:
        x = x.strip()
        if x.endswith("%"):
            try:
                return str(float(x[:-1].strip()) / 100.0)
            except ValueError:
                return x
        return x

    sa, sb = _pct(a).replace("^", "**"), _pct(b).replace("^", "**")
    try:
        ea = sp.sympify(sa, rational=True)
        eb = sp.sympify(sb, rational=True)
        diff = sp.simplify(ea - eb)
        if diff == 0:
            return True
        # Numerical fallback.
        da = float(ea.evalf())
        db = float(eb.evalf())
        return abs(da - db) < tol * max(1.0, abs(da), abs(db))
    except (sp.SympifyError, TypeError, ValueError, SyntaxError):
        return False


def slugify(text: str, max_len: int = 40) -> str:
    """Produce a filesystem-safe slug from arbitrary text."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    if not s:
        s = "problem"
    return s[:max_len]
