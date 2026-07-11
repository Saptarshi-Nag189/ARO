"""
Fast-Mode Nodes
===============
Single-pass speculative pipeline (v2 FastOrchestrator, re-expressed as
graph nodes). The seed search and the planner run in the same parallel
superstep — the "fire search before the plan exists" trick — then a
targeted search fills the gaps and one mega-prompt synthesizes the
report. Target: 15-30 seconds.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from agents.planner_agent import PlannerAgent
from graph import prompts
from graph.models import use_fake_model
from graph.services import GraphServices
from graph.state import FastState
from graph.structured import invoke_structured
from runtime.cache import search_cache
from schemas.knowledge_gaps import KnowledgeGap
from schemas.reports import FastReport, FinalReport

logger = logging.getLogger("aro.graph.fast")


class FastNodes:
    """Node functions for the single-pass fast graph."""

    def __init__(self, services: GraphServices):
        self.services = services
        self.config = services.config
        self.memory = services.memory
        self._planner = PlannerAgent(None)

    # ─── Phase 1a: speculative seed search (parallel with planning) ──

    def seed_search(self, state: FastState) -> Dict[str, Any]:
        objective = state["objective"]
        self.services.safe_emit("phase_start", {"phase": "seed_search"})

        if use_fake_model():
            return {"seed_results": [{"text": "(offline mode: no seed search)",
                                      "source": "seed_search"}]}

        cache_key = search_cache.hash_key("seed", objective)
        cached = search_cache.get(cache_key)
        if cached:
            logger.info("Seed search cache hit")
            return {"seed_results": cached}

        try:
            from tools.web_search import run_web_research
            results_text = run_web_research(sub_questions=[], objective=objective)
            results = [{"text": results_text, "source": "seed_search"}]
            search_cache.set(cache_key, results)
            return {"seed_results": results}
        except Exception as exc:
            logger.warning("Speculative search failed: %s", exc)
            return {"seed_results": []}

    # ─── Phase 1b: quick plan (parallel with seed search) ────────────

    def fast_plan(self, state: FastState) -> Dict[str, Any]:
        self.services.safe_emit("agent_start", {"agent": "planner", "iteration": 1})
        try:
            model = self.services.model_for("planner")
            plan, tokens = invoke_structured(
                model=model,
                agent_name="planner",
                system_prompt=self._planner.get_system_prompt(),
                user_message=(
                    f"You are a research planner. Break this objective into "
                    f"3-5 focused sub-questions with search strategies.\n\n"
                    f"Objective: {state['objective']}"
                ),
                schema=self._planner.get_output_schema(),
                max_retries=self.config.max_retries,
            )
            self.services.safe_emit("agent_done", {"agent": "planner"})
            return {
                "plan_dict": {
                    "sub_questions": [sq.model_dump() for sq in plan.sub_questions],
                    "iteration_targets": plan.iteration_targets,
                },
                "tokens_used": tokens,
            }
        except Exception as exc:
            logger.warning("Planner failed, proceeding with seed search only: %s", exc)
            self.services.safe_emit("agent_done", {"agent": "planner"})
            return {"plan_dict": {"sub_questions": [], "iteration_targets": []}}

    # ─── Phase 2: targeted search ────────────────────────────────────

    def targeted_search(self, state: FastState) -> Dict[str, Any]:
        self.services.safe_emit("phase_start", {"phase": "targeted_search"})
        seed = state.get("seed_results", [])
        sub_questions = state.get("plan_dict", {}).get("sub_questions", [])

        targeted: List[dict] = []
        if sub_questions and not use_fake_model():
            queries = [
                sq.get("question", str(sq)) if isinstance(sq, dict) else str(sq)
                for sq in sub_questions[: self.config.fast_mode_max_search_queries]
            ]
            targeted = self._search_parallel(queries)

        merged = self._merge_results(seed, targeted)
        self.services.safe_emit("phase_complete", {
            "phase": "targeted_search", "total_results": len(merged),
        })
        return {"search_results": merged}

    def _search_parallel(self, queries: List[str]) -> List[dict]:
        from tools.web_search import _search_single_query

        def _one(query: str) -> List[dict]:
            cache_key = search_cache.hash_key("targeted", query)
            cached = search_cache.get(cache_key)
            if cached:
                return cached
            try:
                raw = _search_single_query(query)
                search_cache.set(cache_key, raw)
                return raw
            except Exception as exc:
                logger.warning("Targeted search failed for '%s': %s", query[:50], exc)
                return []

        flat: List[dict] = []
        with ThreadPoolExecutor(max_workers=max(1, len(queries))) as pool:
            for result in pool.map(_one, queries):
                if isinstance(result, list):
                    flat.extend(result)
                elif isinstance(result, dict):
                    flat.append(result)
        return flat

    @staticmethod
    def _merge_results(seed: List[dict], targeted: List[dict]) -> List[dict]:
        seen = set()
        merged = []
        for r in seed + targeted:
            key = str(r.get("url", r.get("text", id(r))))
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged

    # ─── Phase 3: single-pass synthesis ──────────────────────────────

    def fast_synthesize(self, state: FastState) -> Dict[str, Any]:
        self.services.safe_emit("agent_start", {"agent": "fast_synthesis", "iteration": 1})
        context = self._format_context(state.get("search_results", []))
        mega_prompt = prompts.build_fast_synthesis_prompt(state["objective"], context)

        model = self.services.model_for("fast_synthesis")
        fast_report, tokens = invoke_structured(
            model=model,
            agent_name="fast_synthesis",
            system_prompt="",
            user_message=mega_prompt,
            schema=FastReport,
            max_retries=self.config.max_retries,
        )
        self.services.safe_emit("agent_done", {"agent": "fast_synthesis"})

        elapsed = time.time() - state.get("started_at", time.time())
        fast_report.execution_time_seconds = round(elapsed, 2)
        fast_report.sources_consulted = len(state.get("search_results", []))

        final_report = self._to_final_report(fast_report, state, tokens)
        if self.services.session_logger:
            self.services.session_logger.save_final_report(final_report)

        self.services.safe_emit("complete", {
            "report": final_report.model_dump(mode="json"),
        })
        logger.info(
            "Fast mode complete in %.1fs (%d sources)",
            elapsed, fast_report.sources_consulted,
        )
        return {
            "fast_report": fast_report,
            "final_report": final_report,
            "tokens_used": tokens,
        }

    @staticmethod
    def _format_context(results: List[dict]) -> str:
        parts = []
        for i, r in enumerate(results[:20]):
            if isinstance(r, dict):
                text = r.get("text", r.get("snippet", str(r)))
                source = r.get("source", r.get("url", f"source_{i}"))
                parts.append(f"[Source {i+1}: {source}]\n{str(text)[:2000]}\n")
            else:
                parts.append(f"[Source {i+1}]\n{str(r)[:2000]}\n")
        return "\n".join(parts) if parts else "(No search results available)"

    def _to_final_report(
        self, fast: FastReport, state: FastState, tokens: int
    ) -> FinalReport:
        gaps = [
            KnowledgeGap(id=f"gap_{i+1}", description=g, severity=0.5)
            for i, g in enumerate(fast.knowledge_gaps or [])
        ]
        return FinalReport(
            session_id=self.memory.session_id,
            research_objective=fast.research_objective,
            executive_summary=fast.executive_summary,
            conclusion=fast.conclusion,
            mode="fast",
            knowledge_gaps=gaps,
            total_iterations=1,
            total_tokens_used=state.get("tokens_used", 0) + tokens,
            total_execution_time_seconds=fast.execution_time_seconds,
            termination_reason="fast_mode_complete",
            final_hypothesis_confidence=fast.confidence_score,
            final_epistemic_risk=1.0 - fast.confidence_score,
            final_novelty_score=0.0,
        )
