"""End-to-end tests for the iterative research graph (offline fake model)."""

from conftest import initial_state

from graph.graph import build_research_graph


def test_autonomous_run_completes_with_report(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(), invoke_config)

    report = result["final_report"]
    assert report is not None
    assert report.total_iterations >= services.config.min_iterations
    assert report.termination_reason not in ("", "unknown")
    assert report.hypotheses, "expected at least one persisted hypothesis"
    assert report.key_claims, "expected extracted claims in the report"
    assert 0.0 <= report.final_epistemic_risk <= 1.0
    assert 0.0 <= report.final_hypothesis_confidence <= 1.0


def test_token_accounting_reconciles_exactly(services, checkpointer, invoke_config):
    """finalize() raises if per-iteration sums drift from the run total."""
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(), invoke_config)

    report = result["final_report"]
    assert report.total_tokens_used == sum(
        m.token_usage for m in report.iteration_metrics
    )
    assert report.total_tokens_used > 0


def test_parallel_branches_both_execute(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    graph.invoke(initial_state(), invoke_config)

    agents = services.events.agents_started()
    assert "skeptic" in agents and "synthesis" in agents
    assert "reflection" in agents
    # Innovation must NOT run outside innovation mode
    assert "innovation" not in agents

    # Per iteration, skeptic and synthesis are dispatched from the same
    # fan-out; both must appear between consecutive claim extractions.
    first_claims = agents.index("claim_extraction")
    next_section = agents[first_claims:first_claims + 4]
    assert "skeptic" in next_section and "synthesis" in next_section


def test_innovation_mode_runs_innovation_branch(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(mode="innovation"), invoke_config)

    assert "innovation" in services.events.agents_started()
    report = result["final_report"]
    assert report.innovation_proposals, "innovation mode must produce proposals"
    assert report.innovation_proposals[0].novelty_interpretation


def test_max_iterations_is_enforced(services, checkpointer, invoke_config):
    """v2 had a latent bug where max_iterations never terminated the loop."""
    services.config.min_iterations = 1
    services.config.max_iterations = 1
    # Defeat the plateau condition so ONLY the max-iterations guard can fire
    services.config.novelty_plateau_window = 99
    services.config.stale_iteration_window = 99

    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(), invoke_config)

    report = result["final_report"]
    assert report.total_iterations == 1
    assert "Maximum iterations" in report.termination_reason


def test_iteration_events_reach_the_emitter(services, checkpointer, invoke_config):
    """The SSE contract: agent_start/agent_done/iteration_complete/complete."""
    graph = build_research_graph(services, checkpointer=checkpointer)
    graph.invoke(initial_state(), invoke_config)

    types = services.events.types()
    assert "agent_start" in types
    assert "agent_done" in types
    assert "iteration_complete" in types
    assert types.count("complete") == 1

    completes = [e for e in services.events.events if e["type"] == "complete"]
    assert completes[0]["report"]["research_objective"] == "Test objective"
