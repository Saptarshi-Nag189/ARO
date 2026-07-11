"""
Graph Assembly
==============
Wires the nodes into the two compiled StateGraphs.

Standard research graph:

    START → plan → web_search → research → extract_claims
              ┌──────────────┴──────────────┐
           skeptic                       synthesis        (parallel)
              └──────────────┬──────────────┘
                         integrate → compute_metrics
                        ┌────────────┴────────────┐
                 [innovation]                  reflection  (parallel, innovation
                        └────────────┬────────────┘         mode only on the left)
                                   record
                 ┌───────────────────┼───────────────────┐
             finalize           human_gate           plan / web_search
              (stop)         (interactive mode)        (next iteration)

Fast graph:

    START → seed_search ‖ fast_plan → targeted_search → fast_synthesize → END
"""

from typing import List, Optional, Union

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from graph.fast_nodes import FastNodes
from graph.nodes import ResearchNodes
from graph.services import GraphServices
from graph.state import FastState, ResearchState

# Each iteration traverses ~9 nodes; leave generous headroom for the
# maximum 50-iteration web runs.
DEFAULT_RECURSION_LIMIT = 600


def route_after_metrics(state: ResearchState) -> List[str]:
    """Innovation runs only in innovation mode, in parallel with reflection."""
    if state.get("mode") == "innovation":
        return ["innovation", "reflection"]
    return ["reflection"]


def route_after_record(state: ResearchState) -> str:
    if state.get("should_stop"):
        return "finalize"
    if state.get("hitl"):
        return "human_gate"
    return "plan" if state.get("need_replan") else "web_search"


def route_after_human(state: ResearchState) -> str:
    if state.get("should_stop"):
        return "finalize"
    return "plan" if state.get("need_replan") else "web_search"


def build_research_graph(
    services: GraphServices,
    checkpointer: Optional[BaseCheckpointSaver] = None,
):
    """Compile the iterative multi-agent research graph."""
    nodes = ResearchNodes(services)
    g: StateGraph = StateGraph(ResearchState)

    g.add_node("plan", nodes.plan)
    g.add_node("web_search", nodes.web_search)
    g.add_node("research", nodes.research)
    g.add_node("extract_claims", nodes.extract_claims)
    g.add_node("skeptic", nodes.skeptic)
    g.add_node("synthesis", nodes.synthesis)
    g.add_node("integrate", nodes.integrate)
    g.add_node("compute_metrics", nodes.compute_metrics)
    g.add_node("innovation", nodes.innovation)
    g.add_node("reflection", nodes.reflection)
    g.add_node("record", nodes.record)
    g.add_node("human_gate", nodes.human_gate)
    g.add_node("finalize", nodes.finalize)

    g.add_edge(START, "plan")
    g.add_edge("plan", "web_search")
    g.add_edge("web_search", "research")
    g.add_edge("research", "extract_claims")

    # Fan-out: skeptic ‖ synthesis run in the same superstep
    g.add_edge("extract_claims", "skeptic")
    g.add_edge("extract_claims", "synthesis")
    g.add_edge("skeptic", "integrate")
    g.add_edge("synthesis", "integrate")

    g.add_edge("integrate", "compute_metrics")

    # Fan-out: innovation (innovation mode only) ‖ reflection
    g.add_conditional_edges(
        "compute_metrics", route_after_metrics, ["innovation", "reflection"]
    )
    g.add_edge("innovation", "record")
    g.add_edge("reflection", "record")

    g.add_conditional_edges(
        "record", route_after_record,
        ["finalize", "human_gate", "plan", "web_search"],
    )
    g.add_conditional_edges(
        "human_gate", route_after_human,
        ["finalize", "plan", "web_search"],
    )
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


def build_fast_graph(
    services: GraphServices,
    checkpointer: Optional[BaseCheckpointSaver] = None,
):
    """Compile the single-pass fast graph."""
    nodes = FastNodes(services)
    g: StateGraph = StateGraph(FastState)

    g.add_node("seed_search", nodes.seed_search)
    g.add_node("fast_plan", nodes.fast_plan)
    g.add_node("targeted_search", nodes.targeted_search)
    g.add_node("fast_synthesize", nodes.fast_synthesize)

    # Speculative execution: search fires before the plan exists
    g.add_edge(START, "seed_search")
    g.add_edge(START, "fast_plan")
    g.add_edge("seed_search", "targeted_search")
    g.add_edge("fast_plan", "targeted_search")
    g.add_edge("targeted_search", "fast_synthesize")
    g.add_edge("fast_synthesize", END)

    return g.compile(checkpointer=checkpointer)
