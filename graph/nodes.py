"""
Graph Nodes
===========
Node implementations for the ARO research StateGraph. Ports the proven
pipeline logic from the v2 Orchestrator into discrete, checkpointable
steps. Design rules:

- Parallel branches (skeptic ‖ synthesis, innovation ‖ reflection) are
  PURE LLM calls operating on snapshots taken by the preceding
  single-writer node — they never touch the database concurrently.
- All database writes happen in single-writer nodes
  (extract_claims, integrate, record, finalize).
- The only side effect before an interrupt() is nothing at all: the
  human gate node contains ONLY the interrupt, so resuming re-executes
  it safely.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from langgraph.types import interrupt

from agents.claim_extraction_agent import ClaimExtractionAgent
from agents.innovation_agent import InnovationAgent
from agents.planner_agent import PlannerAgent
from agents.reflection_agent import ReflectionAgent
from agents.research_agent import ResearchAgent
from agents.skeptic_agent import SkepticAgent
from agents.synthesis_agent import SynthesisAgent
from evaluation.confidence import (
    compute_effective_confidence,
    compute_hypothesis_confidence,
)
from evaluation.novelty import (
    compute_contradiction_resolution_score,
    compute_knowledge_gap_coverage,
    compute_novelty_score,
    interpret_novelty,
)
from evaluation.risk import compute_average_uncertainty, compute_epistemic_risk
from evaluation.termination import TerminationChecker
from graph import prompts
from graph.models import use_fake_model
from graph.services import GraphServices
from graph.state import ResearchState
from graph.structured import invoke_plain, invoke_structured
from runtime.logger import IterationLog
from schemas.reports import FinalReport, InnovationProposal, IterationMetrics
from schemas.sources import Source
from tools.prior_art_tool import PriorArtTool

logger = logging.getLogger("aro.graph.nodes")


def assert_no_reasoning_artifacts(payload: Any, context: str) -> None:
    """Reject any reasoning_details fields in structured memory/report payloads."""
    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_path = f"{path}.{key}" if path else key
                if key == "reasoning_details":
                    raise RuntimeError(
                        f"HARD GUARD VIOLATION: reasoning_details found in {context} at {next_path}"
                    )
                _walk(value, next_path)
            return
        if isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, f"{path}[{idx}]")
            return
        if hasattr(node, "model_dump"):
            _walk(node.model_dump(), path)

    _walk(payload, "")


class ResearchNodes:
    """Node functions for the iterative research graph."""

    def __init__(self, services: GraphServices):
        self.services = services
        self.config = services.config
        self.memory = services.memory
        self.prior_art_tool = PriorArtTool()
        # Agent specs (system prompt + output schema) — reused from v2.
        self.agents = {
            "planner": PlannerAgent(None),
            "research": ResearchAgent(None),
            "claim_extraction": ClaimExtractionAgent(None),
            "skeptic": SkepticAgent(None),
            "synthesis": SynthesisAgent(None),
            "innovation": InnovationAgent(None),
            "reflection": ReflectionAgent(None),
        }

    # ─── Agent invocation helper ─────────────────────────────────────

    def _run_agent(
        self, agent_key: str, user_message: str, iteration: int
    ) -> Tuple[Any, int, dict]:
        agent = self.agents[agent_key]
        model = self.services.model_for(agent_key)
        self.services.safe_emit("agent_start", {"agent": agent_key, "iteration": iteration})

        start = time.time()
        output, tokens = invoke_structured(
            model=model,
            agent_name=agent_key,
            system_prompt=agent.get_system_prompt(),
            user_message=user_message,
            schema=agent.get_output_schema(),
            max_retries=self.config.max_retries,
        )
        elapsed = time.time() - start

        self.services.safe_emit("agent_done", {"agent": agent_key})
        call_entry = {
            "agent": agent_key,
            "inputs": user_message[:500],
            "outputs": output,
            "tokens": tokens,
            "elapsed": elapsed,
        }
        return output, tokens, call_entry

    # ─── Nodes ───────────────────────────────────────────────────────

    def plan(self, state: ResearchState) -> Dict[str, Any]:
        """(Re)plan the research: decompose the objective into sub-questions."""
        context: Optional[Dict[str, Any]] = None
        reflection = state.get("reflection_output")
        if state.get("need_replan") and reflection is not None:
            context = {
                "iteration": state.get("iteration", 1),
                "strategy_adjustments": [
                    a.model_dump() for a in reflection.strategy_adjustments
                ],
                "current_gaps": [
                    g.description for g in self.memory.get_unresolved_gaps()
                ],
            }
            if state.get("human_directive"):
                context["human_directive"] = state["human_directive"]

        prompt = prompts.build_planner_prompt(state["objective"], context)
        output, tokens, entry = self._run_agent(
            "planner", prompt, state.get("iteration", 1)
        )
        return {
            "plan": output,
            "tokens_used": tokens,
            "agent_calls": [entry],
            "need_replan": False,
            "human_directive": None,
        }

    def web_search(self, state: ResearchState) -> Dict[str, Any]:
        """Run real multi-engine web research for the current plan."""
        iteration = state.get("iteration", 1)
        self.services.safe_emit("phase_start", {"phase": "web_search", "iteration": iteration})

        web_context = ""
        if use_fake_model():
            web_context = "(offline mode: web search skipped)"
        else:
            try:
                from tools.web_search import run_web_research
                web_context = run_web_research(
                    state["plan"].sub_questions,
                    objective=state["objective"],
                )
                logger.info("Web research returned %d chars of context", len(web_context))
            except Exception as exc:
                logger.warning("Web research failed, proceeding without: %s", exc)
                web_context = ""

        self.services.safe_emit("phase_complete", {"phase": "web_search"})
        return {
            "web_context": web_context,
            "iteration_started_at": time.time(),
        }

    def research(self, state: ResearchState) -> Dict[str, Any]:
        """Analyze web results into structured findings."""
        prompt = prompts.build_research_prompt(
            state["objective"],
            state["plan"],
            state.get("iteration", 1),
            web_context=state.get("web_context", ""),
        )
        output, tokens, entry = self._run_agent(
            "research", prompt, state.get("iteration", 1)
        )
        return {
            "research_output": output,
            "tokens_used": tokens,
            "agent_calls": [entry],
        }

    def extract_claims(self, state: ResearchState) -> Dict[str, Any]:
        """Register sources, extract and persist atomic claims, snapshot memory."""
        research_output = state["research_output"]

        # Register sources
        sources = []
        for finding in research_output.findings:
            source = self.memory.add_source(Source(
                title=finding.source_title,
                url=finding.source_url,
                credibility_score=finding.credibility_estimate,
                content_summary=finding.content[:200],
            ))
            sources.append(source)

        prompt = prompts.build_extraction_prompt(research_output, sources)
        output, tokens, entry = self._run_agent(
            "claim_extraction", prompt, state.get("iteration", 1)
        )

        # Persist claims through memory service (with guardrails)
        persisted = []
        source_ids = [s.id for s in sources]
        for claim in output.claims:
            if claim.source_id not in source_ids:
                if source_ids:
                    claim.source_id = source_ids[0]
                else:
                    logger.warning("Skipping claim without valid source: %s", claim.subject)
                    continue
            try:
                persisted.append(self.memory.add_claim(claim))
            except ValueError as exc:
                logger.warning("Guardrail blocked claim: %s", exc)

        new_high_confidence = sum(
            1 for c in persisted if c.confidence_estimate >= 0.7
        )

        # Snapshot for the parallel skeptic ‖ synthesis branches
        return {
            "source_ids": source_ids,
            "new_claim_ids": [c.id for c in persisted],
            "new_high_confidence_claims": new_high_confidence,
            "gap_count_before": len(self.memory.get_all_knowledge_gaps()),
            "claims_snapshot": self.memory.get_all_claims(),
            "hypotheses_snapshot": self.memory.get_all_hypotheses(),
            "tokens_used": tokens,
            "agent_calls": [entry],
        }

    def skeptic(self, state: ResearchState) -> Dict[str, Any]:
        """Pure LLM branch: contradictions, credibility challenges, gaps."""
        prompt = prompts.build_skeptic_prompt(
            state["claims_snapshot"], state["hypotheses_snapshot"]
        )
        output, tokens, entry = self._run_agent(
            "skeptic", prompt, state.get("iteration", 1)
        )
        return {"skeptic_output": output, "tokens_used": tokens, "agent_calls": [entry]}

    def synthesis(self, state: ResearchState) -> Dict[str, Any]:
        """Pure LLM branch: hypotheses from the claims snapshot."""
        prompt = prompts.build_synthesis_prompt(
            state["claims_snapshot"], state["hypotheses_snapshot"]
        )
        output, tokens, entry = self._run_agent(
            "synthesis", prompt, state.get("iteration", 1)
        )
        return {"synthesis_output": output, "tokens_used": tokens, "agent_calls": [entry]}

    def integrate(self, state: ResearchState) -> Dict[str, Any]:
        """Fan-in: apply skeptic findings, persist hypotheses (single writer)."""
        skeptic_output = state["skeptic_output"]
        synthesis_output = state["synthesis_output"]

        # Process skeptic findings
        positive_contradictions = [
            (c.claim_id_a, c.claim_id_b)
            for c in skeptic_output.contradictions
            if c.severity > 0
        ]

        for challenge in skeptic_output.credibility_challenges:
            try:
                current_source = self.memory.get_source(challenge.target_id)
                if current_source:
                    new_score = max(
                        0.0,
                        current_source.credibility_score + challenge.suggested_adjustment,
                    )
                    self.memory.update_source_credibility(challenge.target_id, new_score)
            except Exception as exc:
                logger.debug("Could not apply credibility challenge: %s", exc)

        skeptic_detected = state.get("skeptic_detected_gap_count", 0)
        for gap in skeptic_output.knowledge_gaps:
            skeptic_detected += 1
            try:
                self.memory.add_knowledge_gap(gap)
            except Exception:
                logger.critical(
                    "CRITICAL: Failed to persist skeptic knowledge gap. "
                    "Aborting run for data integrity."
                )
                raise

        gap_count_after = len(self.memory.get_all_knowledge_gaps())

        # Persist hypotheses (re-fetch claims: skeptic may have updated credibility)
        all_claims = self.memory.get_all_claims()
        claim_ids = {c.id for c in all_claims}
        for hyp in synthesis_output.hypotheses:
            valid_supporting = [cid for cid in hyp.supporting_claim_ids if cid in claim_ids]
            valid_opposing = [cid for cid in hyp.opposing_claim_ids if cid in claim_ids]
            if not valid_supporting:
                if all_claims:
                    valid_supporting = [all_claims[0].id]
                else:
                    logger.warning(
                        "Skipping hypothesis without supporting claims: %s",
                        hyp.statement[:80],
                    )
                    continue
            hyp.supporting_claim_ids = valid_supporting
            hyp.opposing_claim_ids = valid_opposing
            try:
                existing = self.memory.get_hypothesis(hyp.id) if hyp.id else None
                if existing:
                    self.memory.update_hypothesis(hyp)
                else:
                    self.memory.add_hypothesis(hyp)
            except ValueError as exc:
                logger.warning("Guardrail blocked hypothesis: %s", exc)

        updates: Dict[str, Any] = {
            "gap_count_after": gap_count_after,
            "skeptic_detected_gap_count": skeptic_detected,
            "total_contradictions": (
                state.get("total_contradictions", 0) + len(positive_contradictions)
            ),
            "claims_snapshot": all_claims,
        }

        # Contradictions become opposing evidence on affected hypotheses
        if positive_contradictions:
            self._apply_contradiction_influence(positive_contradictions)
            updates["contradiction_cycle_count"] = (
                state.get("contradiction_cycle_count", 0) + 1
            )
        return updates

    def _apply_contradiction_influence(self, contradiction_pairs: List[tuple]) -> None:
        hypotheses = self.memory.get_all_hypotheses()
        for hyp in hypotheses:
            supporting_ids = set(hyp.supporting_claim_ids)
            opposing_ids = set(hyp.opposing_claim_ids)
            changed = False
            for claim_a, claim_b in contradiction_pairs:
                if claim_a in supporting_ids and claim_b not in opposing_ids:
                    opposing_ids.add(claim_b)
                    changed = True
                if claim_b in supporting_ids and claim_a not in opposing_ids:
                    opposing_ids.add(claim_a)
                    changed = True
            if changed:
                hyp.opposing_claim_ids = sorted(opposing_ids)
                self.memory.update_hypothesis(hyp)

    def compute_metrics(self, state: ResearchState) -> Dict[str, Any]:
        """Score the iteration; snapshot inputs for innovation ‖ reflection."""
        prior_art: Dict[str, Any] = {}
        prior_art_similarity = 0.5
        if state.get("mode") == "innovation":
            # GUARDRAIL: prior-art scan required before innovation
            prior_art = self.prior_art_tool.scan(
                state["objective"],
                state["synthesis_output"].narrative_summary,
            )
            prior_art_similarity = prior_art.get("estimated_prior_art_similarity", 0.5)

        metrics = self._compute_iteration_metrics(state, prior_art_similarity)

        return {
            "current_metrics": metrics,
            "prior_art": prior_art,
            "prior_art_similarity": prior_art_similarity,
            "gaps_snapshot": self.memory.get_unresolved_gaps(),
            "hypotheses_snapshot": self.memory.get_all_hypotheses(),
        }

    def _compute_iteration_metrics(
        self, state: ResearchState, prior_art_similarity: float
    ) -> IterationMetrics:
        all_claims = self.memory.get_all_claims()
        all_hypotheses = self.memory.get_all_hypotheses()
        unresolved_gaps = self.memory.get_unresolved_gaps()

        # Hard guard: no reasoning traces in structured memory
        assert_no_reasoning_artifacts(
            [c.model_dump() for c in all_claims], "claims snapshot before scoring"
        )
        assert_no_reasoning_artifacts(
            [h.model_dump() for h in all_hypotheses], "hypotheses snapshot before scoring"
        )
        assert_no_reasoning_artifacts(
            [g.model_dump() for g in unresolved_gaps], "knowledge gaps snapshot before scoring"
        )

        avg_uncertainty = compute_average_uncertainty(all_claims)
        epistemic_risk = compute_epistemic_risk(
            average_uncertainty=avg_uncertainty,
            unresolved_contradictions=max(
                0,
                state.get("total_contradictions", 0)
                - state.get("resolved_contradictions", 0),
            ),
            total_claims=len(all_claims) if all_claims else 1,
            normalized_gap_severity=self.memory.get_normalized_gap_severity(),
            source_credibility_variance=self.memory.get_source_credibility_variance(),
            risk_floor=self.config.risk_floor,
        )
        risk_floor_applied = epistemic_risk == self.config.risk_floor

        avg_raw_confidence = 0.0
        avg_effective_confidence = 0.0
        if all_hypotheses:
            raw_confidences = []
            effective_confidences = []
            for hyp in all_hypotheses:
                supporting = [c for c in all_claims if c.id in hyp.supporting_claim_ids]
                opposing = [c for c in all_claims if c.id in hyp.opposing_claim_ids]

                raw_conf = compute_hypothesis_confidence(
                    supporting, opposing, self.config.epsilon
                )
                eff_conf = compute_effective_confidence(
                    raw_confidence=raw_conf,
                    epistemic_risk=epistemic_risk,
                    supporting_claim_count=len(supporting),
                    opposing_claim_count=len(opposing),
                    contradiction_cycle_count=state.get("contradiction_cycle_count", 0),
                )

                # Single-source guardrail
                unique_support_sources = {claim.source_id for claim in supporting}
                if len(unique_support_sources) < 2:
                    eff_conf = min(eff_conf, 0.85)

                hyp.confidence = eff_conf
                try:
                    self.memory.update_hypothesis(hyp)
                except Exception:
                    pass
                raw_confidences.append(raw_conf)
                effective_confidences.append(eff_conf)

            avg_raw_confidence = sum(raw_confidences) / len(raw_confidences)
            avg_effective_confidence = sum(effective_confidences) / len(effective_confidences)

        all_gaps = self.memory.get_all_knowledge_gaps()
        novelty = compute_novelty_score(
            graph_bridge_score=self.memory.get_graph_bridge_score(),
            contradiction_resolution_score=compute_contradiction_resolution_score(
                state.get("total_contradictions", 0),
                state.get("resolved_contradictions", 0),
            ),
            prior_art_similarity=prior_art_similarity,
            knowledge_gap_coverage=compute_knowledge_gap_coverage(
                len(all_gaps), sum(1 for g in all_gaps if g.resolved)
            ),
        )
        # Metrics are computed before the innovation branch runs, so the
        # no-innovations novelty cap always applies here (v2 parity).
        novelty = min(novelty, 0.5)

        return IterationMetrics(
            iteration=state.get("iteration", 1),
            hypothesis_confidence=round(avg_effective_confidence, 6),
            raw_confidence=round(avg_raw_confidence, 6),
            epistemic_risk=epistemic_risk,
            risk_floor_applied=risk_floor_applied,
            novelty_score=novelty,
            new_claims_count=len(state.get("new_claim_ids", [])),
            total_claims_count=len(all_claims),
            total_sources_count=self.memory.source_registry.count_sources(),
            unresolved_gaps_count=len(unresolved_gaps),
            gap_count_before=state.get("gap_count_before", 0),
            gap_count_after=state.get("gap_count_after", 0),
            contradiction_cycle_count=state.get("contradiction_cycle_count", 0),
            token_usage=0,  # finalized in record()
        )

    def innovation(self, state: ResearchState) -> Dict[str, Any]:
        """Pure LLM branch (innovation mode only): patent-grade proposals."""
        prompt = prompts.build_innovation_prompt(
            state["synthesis_output"],
            state.get("prior_art", {}),
            state.get("gaps_snapshot", []),
        )
        output, tokens, entry = self._run_agent(
            "innovation", prompt, state.get("iteration", 1)
        )
        return {"innovation_output": output, "tokens_used": tokens, "agent_calls": [entry]}

    def reflection(self, state: ResearchState) -> Dict[str, Any]:
        """Pure LLM branch: meta-analysis and strategy adjustments."""
        prompt = prompts.build_reflection_prompt(
            state["objective"],
            state["current_metrics"],
            state.get("iteration", 1),
        )
        output, tokens, entry = self._run_agent(
            "reflection", prompt, state.get("iteration", 1)
        )
        if output.advisory_should_stop:
            logger.info(
                "Reflection advisory stop requested (advisory only): %s",
                output.advisory_reason,
            )
        return {"reflection_output": output, "tokens_used": tokens, "agent_calls": [entry]}

    def record(self, state: ResearchState) -> Dict[str, Any]:
        """Single writer: finalize metrics, log the iteration, check termination."""
        iteration = state.get("iteration", 1)
        metrics = state["current_metrics"].model_copy()
        tokens_total = state.get("tokens_used", 0)
        metrics.token_usage = tokens_total - state.get("last_token_snapshot", 0)
        metrics.execution_time_seconds = round(
            time.time() - state.get("iteration_started_at", time.time()), 3
        )

        iteration_metrics = list(state.get("iteration_metrics", [])) + [metrics]
        risk_history = list(state.get("risk_history", [])) + [metrics.epistemic_risk]
        novelty_history = list(state.get("novelty_history", [])) + [metrics.novelty_score]
        new_claims_history = list(state.get("new_claims_history", [])) + [
            state.get("new_high_confidence_claims", 0)
        ]

        # Persist the structured iteration log (same format as v2)
        if self.services.session_logger:
            iter_log = self.services.session_logger.create_iteration_log(iteration)
            for entry in state.get("agent_calls", []):
                iter_log.log_agent_call(
                    agent_name=entry["agent"],
                    inputs=entry["inputs"],
                    outputs=entry["outputs"],
                    token_usage=entry["tokens"],
                    execution_time=entry["elapsed"],
                )
            iter_log.set_metrics(
                hypothesis_confidence=metrics.hypothesis_confidence,
                raw_confidence=metrics.raw_confidence,
                epistemic_risk=metrics.epistemic_risk,
                risk_floor_applied=metrics.risk_floor_applied,
                novelty_score=metrics.novelty_score,
                total_claims=metrics.total_claims_count,
                total_sources=metrics.total_sources_count,
                unresolved_gaps=metrics.unresolved_gaps_count,
                gap_count_before=metrics.gap_count_before,
                gap_count_after=metrics.gap_count_after,
                contradiction_cycle_count=metrics.contradiction_cycle_count,
                total_tokens=metrics.token_usage,
            )
            self.services.session_logger.save_iteration_log(iter_log)

        self.services.safe_emit("iteration_complete", {
            "iteration": iteration,
            "metrics": metrics.model_dump(mode="json"),
        })

        # Deterministic termination — replay histories into the checker so
        # the decision is a pure function of checkpointed state.
        checker = TerminationChecker(
            min_iterations=self.config.min_iterations,
            max_iterations=self.config.max_iterations,
            budget_cap_usd=self.config.budget_cap_usd,
            risk_threshold=self.config.risk_threshold,
            novelty_plateau_delta=self.config.novelty_plateau_delta,
            novelty_plateau_window=self.config.novelty_plateau_window,
            stale_iteration_window=self.config.stale_iteration_window,
        )
        for risk, novelty, claims in zip(risk_history, novelty_history, new_claims_history):
            checker.record_iteration(
                epistemic_risk=risk,
                novelty_score=novelty,
                new_high_confidence_claims=claims,
            )
        should_stop, reason = checker.should_terminate(iteration)
        if not should_stop and iteration >= self.config.max_iterations:
            should_stop, reason = True, (
                f"Maximum iterations reached ({self.config.max_iterations})"
            )

        logger.info("Iteration %d recorded. Terminate=%s (%s)", iteration, should_stop, reason)

        updates: Dict[str, Any] = {
            "iteration_metrics": iteration_metrics,
            "risk_history": risk_history,
            "novelty_history": novelty_history,
            "new_claims_history": new_claims_history,
            "last_token_snapshot": tokens_total,
            "agent_calls": "__reset__",
            "should_stop": should_stop,
            "need_replan": bool(
                state.get("reflection_output")
                and state["reflection_output"].strategy_adjustments
            ),
        }
        if should_stop:
            updates["termination_reason"] = reason
        else:
            updates["iteration"] = iteration + 1
        return updates

    def human_gate(self, state: ResearchState) -> Dict[str, Any]:
        """Human-in-the-loop pause. This node contains ONLY the interrupt,
        so re-execution on resume is side-effect free."""
        metrics = state["iteration_metrics"][-1] if state.get("iteration_metrics") else None
        decision = interrupt({
            "type": "iteration_review",
            "completed_iteration": (state.get("iteration", 1) - 1),
            "metrics": metrics.model_dump(mode="json") if metrics else {},
            "instructions": (
                "Reply 'continue' to run the next iteration, 'stop' to finish "
                "with a report now, or any other text to redirect the research."
            ),
        })

        if isinstance(decision, dict):
            action = str(decision.get("action", "continue")).strip().lower()
            note = decision.get("note", "")
        else:
            text = str(decision).strip()
            action = text.lower()
            note = "" if action in ("continue", "stop") else text

        if action == "stop":
            return {
                "should_stop": True,
                "termination_reason": "Stopped by human reviewer",
            }
        if note:
            return {"need_replan": True, "human_directive": note}
        return {}

    def finalize(self, state: ResearchState) -> Dict[str, Any]:
        """Guards, conclusion generation, final report persistence."""
        # Data-integrity guard (v2 parity)
        if (
            state.get("skeptic_detected_gap_count", 0) > 0
            and not self.memory.get_all_knowledge_gaps()
        ):
            raise RuntimeError(
                "CRITICAL: Skeptic detected one or more knowledge gaps but none persisted."
            )

        # Token accounting must reconcile exactly
        iteration_token_sum = sum(m.token_usage for m in state.get("iteration_metrics", []))
        if iteration_token_sum != state.get("tokens_used", 0):
            raise RuntimeError(
                "CRITICAL: Token accounting mismatch. "
                f"sum(iteration token_usage)={iteration_token_sum} "
                f"!= tokens_used={state.get('tokens_used', 0)}"
            )

        report = self._generate_final_report(state)
        assert_no_reasoning_artifacts(report.model_dump(), "final report payload")

        if self.services.session_logger:
            self.services.session_logger.save_final_report(report)
        self.memory.update_session_status("completed")

        self.services.safe_emit("complete", {"report": report.model_dump(mode="json")})
        return {"final_report": report}

    def _generate_final_report(self, state: ResearchState) -> FinalReport:
        all_claims = self.memory.get_all_claims()
        all_hypotheses = self.memory.get_all_hypotheses()
        all_gaps = self.memory.get_all_knowledge_gaps()
        assert_no_reasoning_artifacts(
            [c.model_dump() for c in all_claims], "claims at final report generation"
        )
        assert_no_reasoning_artifacts(
            [h.model_dump() for h in all_hypotheses], "hypotheses at final report generation"
        )
        assert_no_reasoning_artifacts(
            [g.model_dump() for g in all_gaps], "knowledge gaps at final report generation"
        )

        proposals = []
        innovation_output = state.get("innovation_output")
        if innovation_output:
            for p in innovation_output.proposals:
                proposals.append(InnovationProposal(
                    title=p.title,
                    description=p.description,
                    differentiation_summary=p.differentiation,
                    novelty_score=p.estimated_novelty,
                    novelty_interpretation=interpret_novelty(p.estimated_novelty),
                    prior_art_references=p.prior_art_references,
                    addressed_knowledge_gaps=p.addressed_gaps,
                ))

        key_claims = sorted(
            all_claims, key=lambda c: c.confidence_estimate, reverse=True
        )[:20]

        iteration_metrics = state.get("iteration_metrics", [])
        last_metrics = iteration_metrics[-1] if iteration_metrics else None
        total_iterations = len(iteration_metrics)

        summary = (
            f"Research on '{state['objective']}' completed in "
            f"{total_iterations} iterations.\n\n"
            f"Key findings: {len(all_claims)} claims extracted from "
            f"{self.memory.source_registry.count_sources()} sources, "
            f"forming {len(all_hypotheses)} hypotheses.\n\n"
        )
        if last_metrics:
            summary += (
                f"Final scores — Confidence: {last_metrics.hypothesis_confidence:.3f}, "
                f"Risk: {last_metrics.epistemic_risk:.3f}, "
                f"Novelty: {last_metrics.novelty_score:.3f}.\n\n"
            )
        summary += f"Termination reason: {state.get('termination_reason', 'unknown')}"

        conclusion = self._generate_conclusion(
            state, all_hypotheses, key_claims, all_gaps, last_metrics
        )

        return FinalReport(
            session_id=self.memory.session_id,
            research_objective=state["objective"],
            executive_summary=summary,
            conclusion=conclusion,
            mode=state.get("mode", "autonomous"),
            hypotheses=all_hypotheses,
            key_claims=key_claims,
            knowledge_gaps=all_gaps,
            final_epistemic_risk=last_metrics.epistemic_risk if last_metrics else 1.0,
            final_novelty_score=last_metrics.novelty_score if last_metrics else 0.0,
            final_hypothesis_confidence=(
                last_metrics.hypothesis_confidence if last_metrics else 0.0
            ),
            innovation_proposals=proposals,
            iteration_metrics=iteration_metrics,
            total_iterations=total_iterations,
            total_tokens_used=state.get("tokens_used", 0),
            total_execution_time_seconds=round(
                sum(m.execution_time_seconds for m in iteration_metrics), 2
            ),
            termination_reason=state.get("termination_reason", "unknown"),
        )

    def _generate_conclusion(
        self, state, hypotheses, key_claims, knowledge_gaps, last_metrics
    ) -> str:
        try:
            prompt = prompts.build_conclusion_prompt(
                state["objective"],
                hypotheses,
                key_claims,
                knowledge_gaps,
                confidence=last_metrics.hypothesis_confidence if last_metrics else 0.0,
                risk=last_metrics.epistemic_risk if last_metrics else 1.0,
            )
            model = self.services.plain_model_for("synthesis")
            conclusion, _ = invoke_plain(model, prompt)
            logger.info("Generated conclusion (%d chars)", len(conclusion))
            return conclusion
        except Exception as exc:
            logger.warning("Failed to generate conclusion: %s", exc)
            if hypotheses:
                best = max(hypotheses, key=lambda h: getattr(h, "confidence", 0))
                risk_text = (
                    f"{last_metrics.epistemic_risk:.1%}" if last_metrics else "unknown"
                )
                return (
                    f"Based on the analysis of {len(key_claims)} claims across "
                    f"multiple sources, the strongest finding is: {best.statement} "
                    f"(confidence: {best.confidence:.1%}). "
                    f"This conclusion carries an epistemic risk of {risk_text}."
                )
            return "Insufficient evidence to draw a definitive conclusion."
