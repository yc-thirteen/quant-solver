"""Main pipeline orchestrator.

Wires intake → solvers → verification → critic → consensus and writes a
complete audit trail per run.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from .anth_client import AnthropicClient
from .config import Config, load_config
from .models import FinalAnswer, IntakeResult, SolverOutput, VerificationResult
from .stages.consensus import compute_consensus
from .stages.critic import run_critic
from .stages.intake import run_intake
from .stages.solvers import run_solvers
from .stages.verifier import verify_candidates
from .utils import configure_logging, slugify

log = structlog.get_logger(__name__)


def _audit_dir(image_path: Path, config: Config) -> Path:
    """Compute a fresh audit directory under ``config.results_root``."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    slug = slugify(image_path.stem)
    path = Path(config.results_root) / ts / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, obj) -> None:
    """Write a pydantic model or JSON-serialisable object to ``path``."""
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
    elif isinstance(obj, list) and obj and hasattr(obj[0], "model_dump"):
        data = [o.model_dump(mode="json") for o in obj]
    else:
        data = obj
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def run_pipeline(
    image_path: Path,
    *,
    config: Config | None = None,
    verbose: bool = False,
) -> FinalAnswer:
    """Run the full solve pipeline on a single screenshot.

    Args:
        image_path: Path to a PNG/JPG/WebP screenshot.
        config: Optional override config. Defaults to ``load_config()``.
        verbose: If True, enable verbose logging.

    Returns:
        A ``FinalAnswer`` with attached intake, verifications, and critic for
        downstream formatting without re-reading the audit trail.
    """
    configure_logging(verbose=verbose)
    cfg = config or load_config()
    client = AnthropicClient(cfg)
    audit = _audit_dir(image_path, cfg)
    log.info("pipeline_start", image=str(image_path), audit=str(audit))

    intake: IntakeResult = await run_intake(image_path, client=client, config=cfg)
    _write_json(audit / "01_intake.json", intake)

    solvers: list[SolverOutput] = await run_solvers(intake, client=client, config=cfg)
    _write_json(audit / "02_solvers.json", solvers)

    # Verifier and critic can run in parallel once solver results are known:
    # the critic sees raw solver outputs even before verification finishes,
    # but we want verification results IN the critic prompt. Keep sequential.
    verifications: list[VerificationResult] = await verify_candidates(intake, solvers)
    _write_json(audit / "03_verifications.json", verifications)

    critic = await run_critic(
        intake, solvers, verifications, client=client, config=cfg
    )
    _write_json(audit / "04_critic.json", critic)

    final = compute_consensus(
        intake, solvers, verifications, critic, audit_trail_path=str(audit)
    )
    _write_json(audit / "05_final.json", final)

    log.info(
        "pipeline_done",
        answer=final.answer,
        confidence=final.confidence,
        agreement=final.agreement_level,
        verification=final.verification_passed,
        critic_approved=final.critic_approved,
    )
    return final


def run_pipeline_sync(
    image_path: Path,
    *,
    config: Config | None = None,
    verbose: bool = False,
) -> FinalAnswer:
    """Synchronous convenience wrapper for callers that aren't async."""
    return asyncio.run(run_pipeline(image_path, config=config, verbose=verbose))
