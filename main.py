"""
ARO — Autonomous Research Operator
====================================
CLI entry point for the LangGraph-based multi-agent research engine.

Usage:
    python main.py --objective "Your research question" --mode autonomous
    python main.py --objective "Your research question" --mode innovation --max-iterations 5
    python main.py --objective "Your research question" --mode interactive
    python main.py --objective "Your research question" --mode fast

    # Resume a crashed or interrupted run from its durable checkpoint:
    python main.py --objective "same question" --session-id session_ab12cd34ef56 --resume
"""

import logging
import os
import sys
import time
import uuid

import click

# Ensure the aro/ directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AROConfig
from graph import GraphServices, build_fast_graph, build_research_graph, get_checkpointer
from memory.memory_service import MemoryService
from runtime.logger import SessionLogger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _handle_interrupts(graph, result, invoke_config):
    """Drive the human-in-the-loop cycle for interactive mode."""
    from langgraph.types import Command

    while isinstance(result, dict) and result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        metrics = payload.get("metrics", {})
        click.echo("\n" + "-" * 60)
        click.echo(f"Iteration {payload.get('completed_iteration')} complete.")
        if metrics:
            click.echo(
                f"  Confidence: {metrics.get('hypothesis_confidence', 0):.3f} | "
                f"Risk: {metrics.get('epistemic_risk', 1):.3f} | "
                f"Novelty: {metrics.get('novelty_score', 0):.3f}"
            )
        click.echo(payload.get("instructions", ""))
        answer = click.prompt(
            "Your call [continue/stop/<redirect note>]",
            default="continue", show_default=True,
        )
        result = graph.invoke(Command(resume=answer), invoke_config)
    return result


@click.command()
@click.option(
    "--objective", "-o",
    required=True,
    help="Research objective or question to investigate.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["interactive", "autonomous", "innovation", "fast"]),
    default="autonomous",
    help="Operation mode: interactive, autonomous, innovation, or fast (single-pass).",
)
@click.option(
    "--max-iterations", "-n",
    type=int,
    default=None,
    help="Maximum number of research iterations (overrides config).",
)
@click.option(
    "--session-id", "-s",
    type=str,
    default=None,
    help="Session ID (generated if not provided). Doubles as the checkpoint thread id.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume an interrupted run from its checkpoint (requires --session-id).",
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
    session_id: str,
    resume: bool,
    verbose: bool,
    model: str,
    budget: float,
):
    """
    ARO — Autonomous Research Operator

    A LangGraph multi-agent research engine capable of:
    - Assisting interactive research (real human-in-the-loop interrupts)
    - Replacing early-stage research loops
    - Generating patent-grade architectural proposals
    """
    setup_logging(verbose)
    logger = logging.getLogger("aro.main")

    config = AROConfig()
    if max_iterations is not None:
        config.max_iterations = max_iterations
    if budget is not None:
        config.budget_cap_usd = budget
    if model:
        config.default_model = model
        for agent_config in config.agent_models.values():
            agent_config.model_id = model

    fake_mode = os.getenv("ARO_FAKE_MODEL", "").strip() in ("1", "true", "yes")
    if not config.openrouter_api_key and not fake_mode \
            and os.getenv("ARO_MODEL_PROVIDER", "openrouter") == "openrouter":
        click.echo(
            "ERROR: OPENROUTER_API_KEY not set. "
            "Set it in .env or as an environment variable "
            "(or run offline with ARO_FAKE_MODEL=1).",
            err=True,
        )
        sys.exit(1)

    if resume and not session_id:
        click.echo("ERROR: --resume requires --session-id.", err=True)
        sys.exit(1)

    sid = session_id or f"session_{uuid.uuid4().hex[:12]}"

    logger.info("=" * 60)
    logger.info("ARO — Autonomous Research Operator (LangGraph engine)")
    logger.info("=" * 60)
    logger.info("Objective: %s", objective)
    logger.info("Mode: %s%s", mode, " (resuming)" if resume else "")
    logger.info("Max Iterations: %d", config.max_iterations)
    logger.info("Session: %s", sid)
    logger.info("=" * 60)

    logs_root = os.path.join(BASE_DIR, config.log_dir)
    memory = MemoryService(
        db_path=os.path.join(BASE_DIR, config.db_path),
        session_id=sid,
        vector_store_path=os.path.join(BASE_DIR, config.vector_store_path),
        enable_cross_session_memory=config.enable_cross_session_memory,
    )
    session_logger = SessionLogger(log_dir=logs_root, session_id=sid, mode=config.mode)
    services = GraphServices(config=config, memory=memory, session_logger=session_logger)

    checkpointer = get_checkpointer(base_dir=BASE_DIR)
    invoke_config = {
        "configurable": {"thread_id": sid},
        "recursion_limit": 600,
        "run_name": f"aro-{mode}",
    }

    try:
        if mode == "fast":
            graph = build_fast_graph(services, checkpointer=checkpointer)
            initial = None if resume else {
                "objective": objective,
                "tokens_used": 0,
                "started_at": time.time(),
            }
            result = graph.invoke(initial, invoke_config)
        else:
            if not resume:
                memory.create_session(objective, mode)
            graph = build_research_graph(services, checkpointer=checkpointer)
            initial = None if resume else {
                "objective": objective,
                "mode": mode,
                "hitl": mode == "interactive",
                "iteration": 1,
                "tokens_used": 0,
                "last_token_snapshot": 0,
            }
            result = graph.invoke(initial, invoke_config)
            result = _handle_interrupts(graph, result, invoke_config)

        report = result.get("final_report")
        if report is None:
            raise RuntimeError("Run ended without a final report (check logs).")

        click.echo("\n" + "=" * 60)
        click.echo("RESEARCH COMPLETE")
        click.echo("=" * 60)
        click.echo(f"\n{report.executive_summary}")
        click.echo(f"\nTotal Iterations: {report.total_iterations}")
        click.echo(f"Total Tokens: {report.total_tokens_used}")
        click.echo(f"Execution Time: {report.total_execution_time_seconds:.1f}s")
        click.echo(f"Termination: {report.termination_reason}")
        click.echo("\nFinal Scores:")
        click.echo(f"  Confidence: {report.final_hypothesis_confidence:.4f}")
        click.echo(f"  Risk:       {report.final_epistemic_risk:.4f}")
        click.echo(f"  Novelty:    {report.final_novelty_score:.4f}")

        if report.innovation_proposals:
            click.echo(f"\nInnovation Proposals: {len(report.innovation_proposals)}")
            for p in report.innovation_proposals:
                click.echo(f"  - [{p.novelty_interpretation}] {p.title}")

        report_path = os.path.join(BASE_DIR, "logs", sid, "final_report.json")
        click.echo(f"\nReport path: {report_path}")
        click.echo("=" * 60)

    except KeyboardInterrupt:
        click.echo("\nResearch interrupted by user.")
        click.echo(
            f"Resume it anytime with:\n"
            f"  python main.py -o \"{objective}\" -m {mode} -s {sid} --resume"
        )
        memory.update_session_status("interrupted")
    except Exception as exc:
        logger.exception("Fatal error during research")
        click.echo(f"\nERROR: {exc}", err=True)
        memory.update_session_status("error")
        sys.exit(1)
    finally:
        memory.close()


if __name__ == "__main__":
    main()
