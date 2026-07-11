"""
ARO LangGraph Engine
====================
LangGraph-based execution core (v3). Replaces the hand-rolled
Orchestrator / FastOrchestrator loop with two StateGraphs:

- build_research_graph(): the iterative multi-agent research pipeline
  (plan -> search -> research -> claims -> skeptic ‖ synthesis ->
  [innovation ‖] reflection -> record -> loop / stop) with durable
  checkpointing and optional human-in-the-loop interrupts.
- build_fast_graph(): the single-pass speculative pipeline
  (seed search ‖ plan -> targeted search -> synthesis).
"""

from graph.services import GraphServices
from graph.graph import build_research_graph, build_fast_graph
from graph.checkpoint import get_checkpointer

__all__ = [
    "GraphServices",
    "build_research_graph",
    "build_fast_graph",
    "get_checkpointer",
]
