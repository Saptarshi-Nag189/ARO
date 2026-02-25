"""
ARO — Autonomous Research Operator
====================================
CLI entry point for the multi-agent research engine.

Usage:
    python main.py --objective "Your research question" --mode autonomous
    python main.py --objective "Your research question" --mode innovation --max-iterations 5
    python main.py --objective "Your research question" --mode interactive
"""

import json
import logging
import os
import sys
import uuid

import click

# Ensure the aro/ directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AROConfig
from memory.memory_service import MemoryService
from runtime.model_gateway import ModelGateway
from runtime.logger import SessionLogger
from agents.orchestrator import Orchestrator


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@click.command()
@click.option(
    "--objective", "-o",
    required=True,
    help="Research objective or question to investigate.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["interactive", "autonomous", "innovation"]),
    default="autonomous",
    help="Operation mode: interactive, autonomous, or innovation.",
)
@click.option(
    "--max-iterations", "-n",
    type=int,
    default=None,
    help="Maximum number of research iterations (overrides config).",
)
@click.option(
    "--runtime-mode",
    type=click.Choice(["production", "audit"]),
    default=None,
    help="Runtime execution mode for ModelGateway reasoning behavior.",
)
@click.option(
    "--session-id", "-s",
    type=str,
    default=None,
    help="Session ID (generated if not provided).",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose/debug logging.",
)
@click.option(
    "--model", "-M",
    type=str,
    default=None,
    help="Override default model (e.g. 'anthropic/claude-3.5-sonnet').",
)
@click.option(
    "--budget", "-b",
    type=float,
    default=None,
    help="Budget cap in USD (overrides config).",
)
def main(
    objective: str,
    mode: str,
    max_iterations: int,
    runtime_mode: str,
    session_id: str,
    verbose: bool,
    model: str,
    budget: float,
):
    """
    ARO — Autonomous Research Operator

    A multi-agent research engine capable of:
    - Assisting interactive research
    - Replacing early-stage research loops
    - Generating patent-grade architectural proposals
    """
    setup_logging(verbose)
    logger = logging.getLogger("aro.main")

    # Build configuration
    config = AROConfig()

    if max_iterations is not None:
        config.max_iterations = max_iterations
    if runtime_mode is not None:
        config.mode = runtime_mode
    if budget is not None:
        config.budget_cap_usd = budget
    if model:
        config.default_model = model
        # Update all agent model configs
        for agent_config in config.agent_models.values():
            agent_config.model_id = model

    # Validate API key
    if not config.openrouter_api_key:
        click.echo(
            "ERROR: OPENROUTER_API_KEY not set. "
            "Set it in .env or as an environment variable.",
            err=True,
        )
        sys.exit(1)

    # Generate session ID
    sid = session_id or f"session_{uuid.uuid4().hex[:12]}"

    logger.info("=" * 60)
    logger.info("ARO — Autonomous Research Operator")
    logger.info("=" * 60)
    logger.info("Objective: %s", objective)
    logger.info("Mode: %s", mode)
    logger.info("Runtime Mode: %s", config.mode)
    logger.info("Max Iterations: %d", config.max_iterations)
    logger.info("Session: %s", sid)
    logger.info("Model: %s", config.default_model)
    logger.info("=" * 60)

    logs_root = os.path.join(os.path.dirname(__file__), config.log_dir)

    # Initialize components
    memory = MemoryService(
        db_path=os.path.join(os.path.dirname(__file__), config.db_path),
        session_id=sid,
    )
    gateway = ModelGateway(config, session_id=sid, log_dir=logs_root)
    session_logger = SessionLogger(
        log_dir=logs_root,
        session_id=sid,
        mode=config.mode,
    )
    orchestrator = Orchestrator(config, memory, gateway, session_logger)

    try:
        # Execute the research loop
        report = orchestrator.run(
            research_objective=objective,
            mode=mode,
        )

        # Print summary to stdout
        click.echo("\n" + "=" * 60)
        click.echo("RESEARCH COMPLETE")
        click.echo("=" * 60)
        click.echo(f"\n{report.executive_summary}")
        click.echo(f"\nTotal Iterations: {report.total_iterations}")
        click.echo(f"Total Tokens: {report.total_tokens_used}")
        click.echo(f"Execution Time: {report.total_execution_time_seconds:.1f}s")
        click.echo(f"Termination: {report.termination_reason}")
        click.echo(f"\nFinal Scores:")
        click.echo(f"  Confidence: {report.final_hypothesis_confidence:.4f}")
        click.echo(f"  Risk:       {report.final_epistemic_risk:.4f}")
        click.echo(f"  Novelty:    {report.final_novelty_score:.4f}")

        if report.innovation_proposals:
            click.echo(f"\nInnovation Proposals: {len(report.innovation_proposals)}")
            for p in report.innovation_proposals:
                click.echo(f"  - [{p.novelty_interpretation}] {p.title}")

        click.echo(f"\nFull report saved to: logs/{sid}/final_report.json")
        click.echo("=" * 60)

        # Also write report JSON to stdout if not verbose
        report_path = os.path.join(
            os.path.dirname(__file__), "logs", sid, "final_report.json"
        )
        click.echo(f"\nReport path: {report_path}")

    except KeyboardInterrupt:
        click.echo("\nResearch interrupted by user.")
        memory.update_session_status("interrupted")
    except Exception as e:
        logger.exception("Fatal error during research")
        click.echo(f"\nERROR: {e}", err=True)
        memory.update_session_status("error")
        sys.exit(1)
    finally:
        memory.close()


if __name__ == "__main__":
    main()
