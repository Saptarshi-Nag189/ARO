"""Durable execution: interrupts, resume, and human-in-the-loop redirects."""

from langgraph.types import Command

from conftest import initial_state

from graph.graph import build_research_graph


def test_interactive_mode_interrupts_after_each_iteration(
    services, checkpointer, invoke_config
):
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(hitl=True), invoke_config)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "iteration_review"
    assert payload["completed_iteration"] == 1
    assert "metrics" in payload


def test_human_stop_terminates_with_reason(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(hitl=True), invoke_config)
    assert "__interrupt__" in result

    result = graph.invoke(Command(resume="stop"), invoke_config)
    report = result["final_report"]
    assert report.termination_reason == "Stopped by human reviewer"
    assert report.total_iterations == 1


def test_human_continue_runs_next_iteration(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    result = graph.invoke(initial_state(hitl=True), invoke_config)

    result = graph.invoke(Command(resume="continue"), invoke_config)
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["completed_iteration"] == 2

    result = graph.invoke(Command(resume="stop"), invoke_config)
    assert result["final_report"].total_iterations == 2


def test_human_redirect_triggers_replan(services, checkpointer, invoke_config):
    graph = build_research_graph(services, checkpointer=checkpointer)
    graph.invoke(initial_state(hitl=True), invoke_config)

    planner_runs_before = services.events.agents_started().count("planner")
    result = graph.invoke(
        Command(resume="focus on security implications"), invoke_config
    )
    planner_runs_after = services.events.agents_started().count("planner")

    # A redirect must route through the planner again
    assert planner_runs_after == planner_runs_before + 1
    assert "__interrupt__" in result
    graph.invoke(Command(resume="stop"), invoke_config)


def test_resume_from_checkpoint_with_fresh_graph_instance(
    services, checkpointer, invoke_config
):
    """Simulates a crash: a brand-new graph object picks up the same thread."""
    graph1 = build_research_graph(services, checkpointer=checkpointer)
    result = graph1.invoke(initial_state(hitl=True), invoke_config)
    assert "__interrupt__" in result

    # "Process restart": new compiled graph, same checkpointer + thread id
    graph2 = build_research_graph(services, checkpointer=checkpointer)
    result = graph2.invoke(Command(resume="stop"), invoke_config)

    report = result["final_report"]
    assert report is not None
    assert report.termination_reason == "Stopped by human reviewer"


def test_state_snapshot_is_inspectable(services, checkpointer, invoke_config):
    """Time-travel debugging: checkpoints expose full typed state history."""
    graph = build_research_graph(services, checkpointer=checkpointer)
    graph.invoke(initial_state(hitl=True), invoke_config)

    snapshot = graph.get_state(invoke_config)
    # One iteration recorded; the counter already points at the next one
    assert snapshot.values["iteration"] == 2
    assert snapshot.values["objective"] == "Test objective"
    assert len(snapshot.values["iteration_metrics"]) == 1

    history = list(graph.get_state_history(invoke_config))
    assert len(history) > 5, "expected a checkpoint per superstep"
    graph.invoke(Command(resume="stop"), invoke_config)
