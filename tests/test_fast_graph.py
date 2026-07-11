"""Single-pass fast graph (offline fake model)."""

import time

from graph.graph import build_fast_graph


def _fast_state(objective="Fast test objective"):
    return {"objective": objective, "tokens_used": 0, "started_at": time.time()}


def test_fast_run_produces_final_report(services, checkpointer, invoke_config):
    graph = build_fast_graph(services, checkpointer=checkpointer)
    result = graph.invoke(_fast_state(), invoke_config)

    report = result["final_report"]
    assert report is not None
    assert report.mode == "fast"
    assert report.termination_reason == "fast_mode_complete"
    assert report.total_iterations == 1
    assert report.conclusion
    assert 0.0 <= report.final_hypothesis_confidence <= 1.0
    # risk is the complement of confidence in fast mode
    assert abs(
        report.final_epistemic_risk - (1.0 - report.final_hypothesis_confidence)
    ) < 1e-9


def test_fast_graph_runs_seed_search_and_plan_in_parallel(
    services, checkpointer, invoke_config
):
    graph = build_fast_graph(services, checkpointer=checkpointer)
    graph.invoke(_fast_state(), invoke_config)

    types = services.events.types()
    assert "phase_start" in types
    assert "complete" in types
    agents = services.events.agents_started()
    assert "planner" in agents
    assert "fast_synthesis" in agents


def test_fast_report_saved_to_session_logs(services, checkpointer, invoke_config, tmp_path):
    graph = build_fast_graph(services, checkpointer=checkpointer)
    graph.invoke(_fast_state(), invoke_config)

    report_file = tmp_path / "logs" / "session_test00000000" / "final_report.json"
    assert report_file.exists()
