# Quant Solver

Multi-agent verification pipeline for quant math problems. Takes a screenshot of a problem in any language (Chinese, English, Japanese, Korean, French, etc.) and produces an English solution with a verified answer.

## Quick commands
- `uv sync` — install deps
- `uv run pytest` — run unit tests
- `uv run quant-solver solve path/to/problem.png` — solve one problem from a screenshot
- `uv run quant-solver check-config` — print effective config (without the API key)

## Key files
- `src/quant_solver/pipeline.py` — main orchestrator
- `src/quant_solver/stages/intake.py` — vision + translation stage
- `src/quant_solver/stages/{solvers,verifier,critic,consensus}.py` — the five-agent pipeline
- `src/quant_solver/prompts/*.md` — all LLM prompts (edit these to improve accuracy)
- `src/quant_solver/config.py` — env-driven configuration (prefix `QS_`)

## Input contract
- Input is always a path to an image file: PNG, JPG, or WebP.
- No text input path. If you need to test with text, take a screenshot of the text first.
- Image can be in any language. The vision stage auto-detects and translates to English.

## Output contract
- All internal reasoning and final output is in English.
- Final answer is in canonical form (e.g. `(9*sqrt(2)-6)/7`, `4/3`, `50`, `2.3%`).
- Audit trail for every run is written to `$QS_RESULTS_ROOT/<timestamp>/<problem_slug>/` (default `results/`).

## When adding a new problem type
1. Add enum value to `models.ProblemType`.
2. Add verifier dispatch case in `stages/verifier.py`.
3. Add corresponding tool in `tools/` if needed.
4. Add a prompt hint in `prompts/` if the solvers need to know how to approach the new type.

## Architectural invariants
- Solvers never see each other's outputs. Only the critic sees all of them.
- All solver reasoning is in English, regardless of source language.
- LLM-generated code is never exec'd in-process. Always subprocess with timeout.
- Prompts live in `prompts/*.md`, never hardcoded in Python.
