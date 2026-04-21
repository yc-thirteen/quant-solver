"""Command-line interface for Quant Solver."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config
from .models import FinalAnswer
from .pipeline import run_pipeline

app = typer.Typer(
    help="Multi-agent quant interview math solver. Input: a screenshot in any language.",
    no_args_is_help=True,
)
console = Console()


def _render(final: FinalAnswer) -> None:
    """Pretty-print a ``FinalAnswer`` to stdout using Rich."""
    intake = final.intake
    lang = intake.source_language if intake else "?"
    problem_text = intake.english_text if intake else "(intake missing)"

    console.print(
        Panel(
            problem_text.strip(),
            title=f"Problem (detected language: {lang})",
            border_style="blue",
        )
    )

    # The final answer card.
    conf_color = {"high": "green", "medium": "yellow", "low": "red"}[final.confidence]
    summary = (
        f"[bold]Final Answer:[/bold] {final.answer}\n"
        f"[bold]Confidence:[/bold] [{conf_color}]{final.confidence}[/] "
        f"(agreement={final.agreement_level:.0%}, "
        f"verification={'pass' if final.verification_passed else 'fail'}, "
        f"critic_approved={final.critic_approved})"
    )
    console.print(Panel(summary, title="Result", border_style=conf_color))

    # Solver breakdown.
    table = Table(title="Solver candidates", show_lines=False)
    table.add_column("Agent")
    table.add_column("Approach")
    table.add_column("Answer")
    table.add_column("Decimal", justify="right")
    table.add_column("Conf", justify="right")
    for c in final.all_candidates:
        table.add_row(
            c.agent_name,
            c.approach,
            c.answer or "(failed)",
            f"{c.answer_decimal:.6g}" if c.answer_decimal is not None else "-",
            f"{c.confidence:.2f}",
        )
    console.print(table)

    if final.critic and final.critic.flagged_traps:
        console.print(
            Panel(
                ", ".join(final.critic.flagged_traps),
                title="Flagged traps",
                border_style="yellow",
            )
        )

    console.print(f"[dim]Audit trail: {final.audit_trail_path}[/dim]")


@app.command()
def solve(
    image: Path = typer.Argument(..., exists=True, readable=True, help="Path to problem image."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    json_out: bool = typer.Option(False, "--json", help="Emit the FinalAnswer as JSON only."),
) -> None:
    """Solve a single problem from an image."""
    final = asyncio.run(run_pipeline(image, verbose=verbose))
    if json_out:
        sys.stdout.write(json.dumps(final.model_dump(mode="json"), indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        _render(final)


@app.command()
def check_config() -> None:
    """Print the effective config (without the API key) for debugging."""
    cfg = load_config()
    data = cfg.model_dump()
    data["anthropic_api_key"] = "(set)" if cfg.anthropic_api_key else "(missing)"
    console.print_json(json.dumps(data))


if __name__ == "__main__":
    app()
