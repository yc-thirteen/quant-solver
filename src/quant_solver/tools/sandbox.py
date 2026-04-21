"""Safely execute LLM-generated Python code in a subprocess with a timeout.

**Security note.** Never ``exec()`` code produced by an LLM in the host process.
This module spawns a fresh ``python`` subprocess, passes the code on stdin, and
enforces a wall-clock timeout. The subprocess inherits the host environment, so
callers running untrusted code in production should run this inside an
additional container / sandbox. For the v1 portfolio project this is enough
defense-in-depth to catch typical failure modes (infinite loops, broken imports).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass
class SandboxResult:
    """Result of a sandboxed subprocess run."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def run_python(code: str, *, timeout_s: int = 30) -> SandboxResult:
    """Run Python source code in a subprocess with a timeout.

    Args:
        code: The Python source to execute.
        timeout_s: Wall-clock timeout in seconds.

    Returns:
        A ``SandboxResult`` with captured stdout, stderr, exit code, and a
        ``timed_out`` flag.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return SandboxResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            returncode=-1,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )
