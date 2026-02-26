"""
Fast Orchestrator
=================
Single-pass research pipeline for speed — Grok-style speculative execution.

Architecture (per audit §4.3.6):
  Phase 1: Fire speculative web search + planner concurrently (<2s)
  Phase 2: Targeted search for planner sub-questions not covered by seed
  Phase 3: Single-pass LLM synthesis (research + extract + synthesize in one call)

Target: 15-30 seconds vs 2-5+ minutes for standard mode.
Trade-off: No skeptic review, no multi-iteration refinement.
"""

import asyncio
import logging
import time
from typing import List

from schemas.reports import FastReport, FinalReport
from schemas.search_result import SearchResult
from runtime.cache import search_cache

logger = logging.getLogger("aro.fast_orchestrator")


class FastOrchestrator:
    """Single-pass research for speed. No iteration loop, no skeptic review."""

    def __init__(self, config, memory, gateway, event_bus=None):
        self.config = config
        self.memory = memory
        self.gateway = gateway
        self.event_bus = event_bus

    def _emit(self, event_type: str, data: dict = None):
        """Emit event if bus is connected."""
        if self.event_bus:
            self.event_bus.emit(event_type, data or {})

    async def run(self, objective: str) -> FinalReport:
        """
        Execute single-pass fast research.

        Flow:
          1. Speculative search + planner run concurrently
          2. Targeted search for gaps
          3. Single-pass mega-prompt synthesis
        """
        start_time = time.time()
        self._emit("fast_mode_start", {"objective": objective})

        # ─── Phase 1: Parallel seed search + planner ──────────────────
        self._emit("phase_start", {"phase": "seed_search_and_planning"})

        seed_task = asyncio.create_task(
            self._speculative_search(objective)
        )
        plan_task = asyncio.create_task(
            self._run_planner(objective)
        )
        seed_results, plan = await asyncio.gather(seed_task, plan_task)

        self._emit("phase_complete", {
            "phase": "seed_search_and_planning",
            "seed_results_count": len(seed_results),
            "sub_questions_count": len(plan.get("sub_questions", [])),
        })

        # ─── Phase 2: Targeted search for sub-questions ───────────────
        self._emit("phase_start", {"phase": "targeted_search"})
        targeted = await self._targeted_search(plan, seed_results)
        all_results = self._merge_results(seed_results, targeted)
        self._emit("phase_complete", {
            "phase": "targeted_search",
            "total_results": len(all_results),
        })

        # ─── Phase 3: Single-pass synthesis ───────────────────────────
        self._emit("phase_start", {"phase": "synthesis"})
        fast_report = await self._single_pass_synthesis(objective, all_results)
        elapsed = time.time() - start_time
        fast_report.execution_time_seconds = round(elapsed, 2)
        fast_report.sources_consulted = len(all_results)

        self._emit("complete", {
            "execution_time": elapsed,
            "sources": len(all_results),
        })

        logger.info(
            "Fast mode complete in %.1fs (%d sources)",
            elapsed, len(all_results),
        )

        return self._to_final_report(fast_report)

    # ─── Phase 1: Speculative Search ──────────────────────────────────

    async def _speculative_search(self, objective: str) -> List[dict]:
        """
        Fire web search from raw objective BEFORE planner output is ready.
        This is the key insight from Grok's architecture.
        """
        cache_key = search_cache.hash_key("seed", objective)
        cached = search_cache.get(cache_key)
        if cached:
            logger.info("Seed search cache hit")
            return cached

        try:
            from tools.web_search import run_web_research
            # Use the existing sync search but run in thread to not block
            results_text = await asyncio.to_thread(
                run_web_research,
                sub_questions=[],
                objective=objective,
            )
            results = [{"text": results_text, "source": "seed_search"}]
            search_cache.set(cache_key, results)
            return results
        except Exception as e:
            logger.warning("Speculative search failed: %s", e)
            return []

    async def _run_planner(self, objective: str) -> dict:
        """Run planner agent to get sub-questions."""
        try:
            from schemas.agent_io import PlannerOutput
            plan = await self.gateway.call_async(
                agent_name="planner",
                messages=[{
                    "role": "user",
                    "content": (
                        f"You are a research planner. Break this objective into "
                        f"3-5 focused sub-questions with search strategies.\n\n"
                        f"Objective: {objective}"
                    ),
                }],
                response_schema=PlannerOutput,
            )
            return {
                "sub_questions": plan.sub_questions,
                "iteration_targets": plan.iteration_targets,
            }
        except Exception as e:
            logger.warning("Planner failed, proceeding with seed search only: %s", e)
            return {"sub_questions": [], "iteration_targets": []}

    # ─── Phase 2: Targeted Search ─────────────────────────────────────

    async def _targeted_search(
        self, plan: dict, seed_results: List[dict]
    ) -> List[dict]:
        """Search planner sub-questions, skip if seed already covers them."""
        sub_questions = plan.get("sub_questions", [])
        if not sub_questions:
            return []

        max_queries = self.config.fast_mode_max_search_queries
        tasks = []

        for sq in sub_questions[:max_queries]:
            q = sq.question if hasattr(sq, 'question') else str(sq)
            cache_key = search_cache.hash_key("targeted", q)
            cached = search_cache.get(cache_key)
            if cached:
                tasks.append(asyncio.coroutine(lambda c=cached: c)())
            else:
                tasks.append(self._search_single_async(q))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        flat = []
        for r in results:
            if isinstance(r, list):
                flat.extend(r)
            elif isinstance(r, dict):
                flat.append(r)
        return flat

    async def _search_single_async(self, query: str) -> List[dict]:
        """Run a single search query asynchronously."""
        try:
            from tools.web_search import _search_single_query, _format_results
            raw = await asyncio.to_thread(_search_single_query, query)
            cache_key = search_cache.hash_key("targeted", query)
            search_cache.set(cache_key, raw)
            return raw
        except Exception as e:
            logger.warning("Targeted search failed for '%s': %s", query[:50], e)
            return []

    # ─── Phase 3: Single-Pass Synthesis ───────────────────────────────

    async def _single_pass_synthesis(
        self, objective: str, all_results: List[dict]
    ) -> FastReport:
        """
        One LLM call that does research + extraction + synthesis.
        Combines 3 agent prompts into one mega-prompt for speed.
        """
        context = self._format_context(all_results)

        mega_prompt = (
            f"You are a senior research analyst. Conduct comprehensive research "
            f"on the following objective and produce a complete analysis.\n\n"
            f"RESEARCH OBJECTIVE: {objective}\n\n"
            f"AVAILABLE SOURCES AND CONTEXT:\n{context}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Analyze ALL available sources thoroughly\n"
            f"2. Extract key findings with specific details, numbers, and evidence\n"
            f"3. Synthesize findings into a comprehensive executive summary\n"
            f"4. Provide a direct, definitive conclusion to the research question\n"
            f"5. Estimate your overall confidence (0.0 to 1.0)\n"
            f"6. Note any significant knowledge gaps\n\n"
            f"Be EXTREMELY detailed and comprehensive. The user expects an in-depth "
            f"analysis, not a surface-level summary. Include specific data points, "
            f"statistics, technical details, and nuanced insights.\n\n"
            f"Return a JSON object with these fields:\n"
            f"- research_objective (string)\n"
            f"- executive_summary (detailed string, 200+ words)\n"
            f"- key_findings (list of detailed strings, 5-10 items)\n"
            f"- conclusion (direct answer, 50+ words)\n"
            f"- confidence_score (float 0-1)\n"
            f"- knowledge_gaps (list of strings)"
        )

        fast_report = await self.gateway.call_async(
            agent_name="fast_synthesis",
            messages=[{"role": "user", "content": mega_prompt}],
            response_schema=FastReport,
        )
        return fast_report

    # ─── Helpers ──────────────────────────────────────────────────────

    def _merge_results(
        self, seed: List[dict], targeted: List[dict]
    ) -> List[dict]:
        """Merge and deduplicate search results."""
        seen = set()
        merged = []
        for r in seed + targeted:
            key = str(r.get("url", r.get("text", id(r))))
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged

    def _format_context(self, results: List[dict]) -> str:
        """Format search results into prompt context."""
        parts = []
        for i, r in enumerate(results[:20]):  # Cap at 20 results
            if isinstance(r, dict):
                text = r.get("text", r.get("snippet", str(r)))
                source = r.get("source", r.get("url", f"source_{i}"))
                parts.append(f"[Source {i+1}: {source}]\n{text[:2000]}\n")
            else:
                parts.append(f"[Source {i+1}]\n{str(r)[:2000]}\n")
        return "\n".join(parts) if parts else "(No search results available)"

    def _to_final_report(self, fast: FastReport) -> FinalReport:
        """Convert FastReport to FinalReport structure for API compatibility."""
        return FinalReport(
            research_objective=fast.research_objective,
            executive_summary=fast.executive_summary,
            conclusion=fast.conclusion,
            total_iterations=1,
            total_tokens_used=self.gateway.total_tokens_used,
            total_execution_time_seconds=fast.execution_time_seconds,
            termination_reason="fast_mode_complete",
            final_hypothesis_confidence=fast.confidence_score,
            final_epistemic_risk=1.0 - fast.confidence_score,
            final_novelty_score=0.0,
        )
