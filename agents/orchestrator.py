"""
Root Orchestrator Agent
=======================
The ADK entry point and master execution controller.
ONLY this agent controls:
  - Loop execution flow
  - Agent invocation order
  - Termination decisions
  - Mode-specific behavior (Interactive / Autonomous / Innovation)
  - Guardrail enforcement

No other agent controls the loop or modifies global state.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from config import AROConfig
from memory.memory_service import MemoryService
from runtime.model_gateway import ModelGateway
from runtime.logger import SessionLogger, IterationLog
from evaluation.confidence import compute_hypothesis_confidence, compute_effective_confidence
from evaluation.risk import compute_epistemic_risk, compute_average_uncertainty
from evaluation.novelty import (
    compute_novelty_score,
    interpret_novelty,
    compute_contradiction_resolution_score,
    compute_knowledge_gap_coverage,
)
from evaluation.termination import TerminationChecker
from agents.planner_agent import PlannerAgent
from agents.research_agent import ResearchAgent
from agents.claim_extraction_agent import ClaimExtractionAgent
from agents.skeptic_agent import SkepticAgent
from agents.synthesis_agent import SynthesisAgent
from agents.innovation_agent import InnovationAgent
from agents.reflection_agent import ReflectionAgent
from tools.prior_art_tool import PriorArtTool
from tools.web_search import run_web_research
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.sources import Source
from schemas.knowledge_gaps import KnowledgeGap
from schemas.reports import FinalReport, IterationMetrics, InnovationProposal

logger = logging.getLogger("aro.orchestrator")


class Orchestrator:
    """
    Root Orchestrator — controls all execution flow.

    Execution pipeline per iteration:
        Plan → Research → Extract Claims → Skeptic Review →
        Synthesize → [Innovate (if innovation mode)] →
        Reflect → Evaluate → Terminate?
    """

    def __init__(
        self,
        config: AROConfig,
        memory: MemoryService,
        gateway: ModelGateway,
        session_logger: SessionLogger,
    ):
        self.config = config
        self.memory = memory
        self.gateway = gateway
        self.session_logger = session_logger

        # Initialize all agents
        self.planner = PlannerAgent(gateway)
        self.researcher = ResearchAgent(gateway)
        self.claim_extractor = ClaimExtractionAgent(gateway)
        self.skeptic = SkepticAgent(gateway)
        self.synthesizer = SynthesisAgent(gateway)
        self.innovator = InnovationAgent(gateway)
        self.reflector = ReflectionAgent(gateway)

        # Tools
        self.prior_art_tool = PriorArtTool()

        # Termination checker
        self.termination = TerminationChecker(
            min_iterations=config.min_iterations,
            max_iterations=config.max_iterations,
            budget_cap_usd=config.budget_cap_usd,
            risk_threshold=config.risk_threshold,
            novelty_plateau_delta=config.novelty_plateau_delta,
            novelty_plateau_window=config.novelty_plateau_window,
            stale_iteration_window=config.stale_iteration_window,
        )

        # Metrics history
        self.iteration_metrics: List[IterationMetrics] = []
        self.total_contradictions = 0
        self.resolved_contradictions = 0
        self.contradiction_cycle_count = 0
        self.skeptic_detected_gap_count = 0

    def run(
        self,
        research_objective: str,
        mode: str = "autonomous",
    ) -> FinalReport:
        """
        Execute the full research loop.

        Args:
            research_objective: The research question/objective.
            mode: 'interactive', 'autonomous', or 'innovation'.

        Returns:
            FinalReport with all findings, scores, and proposals.
        """
        logger.info(
            "=== ARO Starting ===\n  Objective: %s\n  Mode: %s\n  Max Iterations: %d",
            research_objective, mode, self.config.max_iterations,
        )

        # Create session
        self.memory.create_session(research_objective, mode)
        start_time = time.time()

        # Phase 1: Initial planning
        pre_loop_tokens_before = self.gateway.total_tokens_used
        plan = self._run_planner(research_objective)
        pre_loop_planner_tokens = self.gateway.total_tokens_used - pre_loop_tokens_before

        # Main research loop
        iteration = 0
        termination_reason = "unknown"
        latest_innovation_output = None

        while True:
            iteration += 1
            iter_start = time.time()
            iter_log = self.session_logger.create_iteration_log(iteration)

            logger.info("=== Iteration %d ===", iteration)
            tokens_before = self.gateway.total_tokens_used

            # --- Step 1: Web Research + LLM Analysis ---
            # First, run real web searches based on planner sub-questions
            logger.info("Running web research for iteration %d...", iteration)
            try:
                web_context = run_web_research(
                    plan.sub_questions,
                    objective=research_objective,
                )
                logger.info("Web research returned %d chars of context", len(web_context))
            except Exception as e:
                logger.warning("Web research failed, proceeding without: %s", e)
                web_context = ""

            research_prompt = self._build_research_prompt(
                research_objective, plan, iteration, web_context=web_context
            )
            research_output = self._run_agent_logged(
                self.researcher, research_prompt, iter_log,
                context={"plan": plan},
            )

            # --- Step 2: Register Sources & Extract Claims ---
            sources = self._register_sources(research_output)
            claims_output = self._run_agent_logged(
                self.claim_extractor,
                self._build_extraction_prompt(research_output, sources),
                iter_log,
            )

            # Persist claims through memory service (with guardrails)
            new_claims = self._persist_claims(claims_output, sources)
            new_high_confidence = sum(
                1 for c in new_claims if c.confidence_estimate >= 0.7
            )

            # --- Step 3: Skeptic Review ---
            gap_count_before = len(self.memory.get_all_knowledge_gaps())
            all_claims = self.memory.get_all_claims()
            all_hypotheses = self.memory.get_all_hypotheses()
            skeptic_output = self._run_agent_logged(
                self.skeptic,
                self._build_skeptic_prompt(all_claims, all_hypotheses),
                iter_log,
            )

            # Process skeptic findings
            positive_contradictions = self._process_skeptic_output(skeptic_output)
            gap_count_after = len(self.memory.get_all_knowledge_gaps())

            # --- Step 4: Synthesis ---
            all_claims = self.memory.get_all_claims()
            synthesis_output = self._run_agent_logged(
                self.synthesizer,
                self._build_synthesis_prompt(all_claims, all_hypotheses),
                iter_log,
            )

            # Persist hypotheses (with guardrails)
            self._persist_hypotheses(synthesis_output, all_claims)
            if positive_contradictions:
                self._apply_contradiction_influence(positive_contradictions)
                self.contradiction_cycle_count += 1

            # --- Step 5: Innovation (if innovation mode) ---
            innovation_output = None
            prior_art_similarity = 0.5
            if mode == "innovation":
                # GUARDRAIL: Prior art scan required before innovation
                prior_art = self.prior_art_tool.scan(
                    research_objective,
                    synthesis_output.narrative_summary,
                )
                prior_art_similarity = prior_art.get(
                    "estimated_prior_art_similarity", 0.5
                )
                innovation_output = self._run_agent_logged(
                    self.innovator,
                    self._build_innovation_prompt(
                        synthesis_output, prior_art,
                        self.memory.get_unresolved_gaps(),
                    ),
                    iter_log,
                )
            latest_innovation_output = innovation_output
            has_innovations = bool(
                innovation_output and innovation_output.proposals
            )

            # --- Step 6: Compute Metrics ---
            metrics = self._compute_iteration_metrics(
                iteration=iteration,
                prior_art_similarity=prior_art_similarity,
                gap_count_before=gap_count_before,
                gap_count_after=gap_count_after,
                tokens_this_iter=0,
                has_innovations=has_innovations,
                new_claims_count=len(new_claims),
            )

            # --- Step 7: Reflection ---
            reflection_output = self._run_agent_logged(
                self.reflector,
                self._build_reflection_prompt(
                    research_objective, metrics, iteration
                ),
                iter_log,
            )

            if reflection_output.advisory_should_stop:
                logger.info(
                    "Reflection advisory stop requested (advisory only): %s",
                    reflection_output.advisory_reason,
                )
            else:
                logger.info(
                    "Reflection advisory continue: %s",
                    reflection_output.advisory_reason,
                )

            # --- Step 8: Update plan for next iteration ---
            if reflection_output.strategy_adjustments:
                plan = self._run_planner(
                    research_objective,
                    context={
                        "iteration": iteration,
                        "strategy_adjustments": [
                            a.model_dump() for a in reflection_output.strategy_adjustments
                        ],
                        "current_gaps": [
                            g.description for g in self.memory.get_unresolved_gaps()
                        ],
                    },
                )

            # --- Step 9: Finalize iteration token/accounting snapshot ---
            tokens_this_iter = self.gateway.total_tokens_used - tokens_before
            if iteration == 1:
                tokens_this_iter += pre_loop_planner_tokens
            metrics.token_usage = tokens_this_iter
            metrics.execution_time_seconds = round(time.time() - iter_start, 3)
            self.iteration_metrics.append(metrics)

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
            self.session_logger.save_iteration_log(iter_log)

            # --- Step 10: Check deterministic termination ---
            self.termination.record_iteration(
                epistemic_risk=metrics.epistemic_risk,
                novelty_score=metrics.novelty_score,
                new_high_confidence_claims=new_high_confidence,
            )

            should_stop, reason = self.termination.should_terminate(iteration)

            # Interactive mode: give human a chance to override
            if mode == "interactive" and not should_stop:
                logger.info(
                    "Interactive mode — iteration %d complete. "
                    "Continuing automatically (override not connected).",
                    iteration,
                )

            if should_stop:
                termination_reason = reason
                logger.info("Terminating: %s", reason)
                break

        # --- Generate Final Report ---
        if self.skeptic_detected_gap_count > 0 and not self.memory.get_all_knowledge_gaps():
            raise RuntimeError(
                "CRITICAL: Skeptic detected one or more knowledge gaps but none persisted."
            )
        self._assert_token_accounting()

        total_time = time.time() - start_time
        report = self._generate_final_report(
            research_objective=research_objective,
            mode=mode,
            termination_reason=termination_reason,
            total_iterations=iteration,
            total_time=total_time,
            innovation_output=latest_innovation_output,
        )
        self._assert_no_reasoning_artifacts(
            report.model_dump(),
            context="final report payload",
        )

        # Save report
        self.session_logger.save_final_report(report)
        self.memory.update_session_status("completed")

        logger.info(
            "=== ARO Complete ===\n  Iterations: %d\n  "
            "Risk: %.3f\n  Novelty: %.3f\n  Reason: %s",
            iteration,
            report.final_epistemic_risk,
            report.final_novelty_score,
            termination_reason,
        )

        return report

    # ─── Agent Invocation Helpers ─────────────────────────────────────────

    def _run_agent_logged(
        self, agent, prompt: str, iter_log: IterationLog,
        context: Optional[Dict] = None,
    ):
        """Run an agent and log the call."""
        start = time.time()
        tokens_before = self.gateway.total_tokens_used

        result = agent.run(prompt, context)

        elapsed = time.time() - start
        tokens_used = self.gateway.total_tokens_used - tokens_before

        iter_log.log_agent_call(
            agent_name=agent.name,
            inputs=prompt[:500],
            outputs=result,
            token_usage=tokens_used,
            execution_time=elapsed,
        )
        return result

    def _run_planner(
        self, objective: str, context: Optional[Dict] = None
    ):
        """Run the planner agent."""
        prompt = (
            f"Research Objective: {objective}\n\n"
            f"Create a detailed research plan with sub-questions, "
            f"search strategies, and iteration targets."
        )
        if context:
            prompt += f"\n\nContext from previous iterations:\n{json.dumps(context, indent=2)}"
        return self.planner.run(prompt, context)

    # ─── Prompt Builders ──────────────────────────────────────────────────

    def _build_research_prompt(self, objective, plan, iteration, web_context=""):
        sub_questions = "\n".join(
            f"  {i+1}. [{sq.priority}] {sq.question} (strategy: {sq.search_strategy})"
            for i, sq in enumerate(plan.sub_questions)
        )

        prompt = (
            f"Research Objective: {objective}\n\n"
            f"Iteration: {iteration}\n\n"
            f"Sub-questions to investigate:\n{sub_questions}\n\n"
            f"Iteration targets: {', '.join(plan.iteration_targets)}\n\n"
        )

        if web_context:
            prompt += (
                f"\n{web_context}\n\n"
                "IMPORTANT INSTRUCTIONS:\n"
                "1. The web search results above are REAL sources from the internet.\n"
                "2. Use them as your PRIMARY evidence — cite their actual URLs.\n"
                "3. DO NOT invent or hallucinate any sources or URLs.\n"
                "4. If a finding comes from a web result, use its exact title and URL.\n"
                "5. You may supplement with your training knowledge, but clearly\n"
                "   distinguish between web-sourced and knowledge-sourced findings.\n"
                "6. Rate web-sourced findings with higher credibility (0.7-0.95).\n\n"
            )
        else:
            prompt += (
                "Note: No web search results available for this iteration.\n"
                "Use your training knowledge to provide findings.\n\n"
            )

        prompt += "Conduct thorough research and return structured findings with source metadata."
        return prompt

    def _build_extraction_prompt(self, research_output, sources):
        findings_text = "\n\n".join(
            f"Finding {i+1} (source: {f.source_title}, "
            f"credibility: {f.credibility_estimate}):\n{f.content}"
            for i, f in enumerate(research_output.findings)
        )
        source_map = "\n".join(
            f"  {s.id}: {s.title}" for s in sources
        )
        return (
            f"Extract atomic claims from the following research findings.\n\n"
            f"Available source IDs:\n{source_map}\n\n"
            f"Findings:\n{findings_text}"
        )

    def _build_skeptic_prompt(self, claims, hypotheses):
        claims_text = "\n".join(
            f"  [{c.id}] {c.subject} --{c.relation}--> {c.object} "
            f"(confidence: {c.confidence_estimate}, credibility: {c.credibility_weight})"
            for c in claims
        )
        hyp_text = "\n".join(
            f"  [{h.id}] {h.statement} (confidence: {h.confidence}, status: {h.status})"
            for h in hypotheses
        ) if hypotheses else "  (No hypotheses yet)"

        return (
            f"Critically evaluate the following claims and hypotheses.\n\n"
            f"Claims:\n{claims_text}\n\n"
            f"Hypotheses:\n{hyp_text}\n\n"
            f"Identify contradictions, credibility issues, and knowledge gaps."
        )

    def _build_synthesis_prompt(self, claims, existing_hypotheses):
        max_claims = 60
        max_existing_hypotheses = 30
        selected_claims = sorted(
            claims,
            key=lambda c: c.confidence_estimate,
            reverse=True,
        )[:max_claims]
        selected_hypotheses = (
            existing_hypotheses[-max_existing_hypotheses:]
            if existing_hypotheses else []
        )

        claims_text = "\n".join(
            f"  [{c.id}] {c.subject} --{c.relation}--> {c.object} "
            f"(confidence: {c.confidence_estimate})"
            for c in selected_claims
        )
        existing = "\n".join(
            f"  [{h.id}] {h.statement} (status: {h.status})"
            for h in selected_hypotheses
        ) if selected_hypotheses else "  (No existing hypotheses)"

        return (
            f"Synthesize the following claims into coherent hypotheses.\n\n"
            f"Context limits:\n"
            f"- Claims shown: {len(selected_claims)} of {len(claims)}\n"
            f"- Existing hypotheses shown: {len(selected_hypotheses)} "
            f"of {len(existing_hypotheses)}\n\n"
            f"Current claims:\n{claims_text}\n\n"
            f"Existing hypotheses:\n{existing}\n\n"
            "Form new hypotheses or update existing ones. Reference claim IDs.\n\n"
            "Strict output constraints:\n"
            "- Return at most 8 hypotheses.\n"
            "- Return at most 20 merged_claims.\n"
            "- Return at most 12 relationships.\n"
            "- relationships must be a JSON LIST of objects.\n"
            "- Each relationship object must have ONLY these string keys:\n"
            "  source_hypothesis_id, target_hypothesis_id, relationship_type.\n"
            "- Keep narrative_summary <= 180 words."
        )

    def _build_innovation_prompt(self, synthesis, prior_art, gaps):
        gaps_text = "\n".join(
            f"  [{g.id}] {g.description} (severity: {g.severity})"
            for g in gaps
        ) if gaps else "  (No unresolved gaps)"

        return (
            f"Generate innovation proposals based on the research synthesis.\n\n"
            f"Synthesis Summary:\n{synthesis.narrative_summary}\n\n"
            f"Prior Art Scan:\n{json.dumps(prior_art, indent=2)}\n\n"
            f"Unresolved Knowledge Gaps:\n{gaps_text}\n\n"
            f"Propose novel innovations that differentiate from prior art "
            f"and address knowledge gaps."
        )

    def _build_reflection_prompt(self, objective, metrics, iteration):
        return (
            f"Reflect on the current state of research.\n\n"
            f"Research Objective: {objective}\n"
            f"Iteration: {iteration}\n\n"
            f"Current Metrics:\n"
            f"  Hypothesis Confidence: {metrics.hypothesis_confidence:.4f}\n"
            f"  Epistemic Risk: {metrics.epistemic_risk:.4f}\n"
            f"  Novelty Score: {metrics.novelty_score:.4f}\n"
            f"  Total Claims: {metrics.total_claims_count}\n"
            f"  Total Sources: {metrics.total_sources_count}\n"
            f"  Unresolved Gaps: {metrics.unresolved_gaps_count}\n\n"
            f"Provide meta-analysis, trend assessment, and strategy "
            f"recommendations."
        )

    # ─── Data Processing ──────────────────────────────────────────────────

    def _register_sources(self, research_output):
        """Register all sources from research findings."""
        sources = []
        for finding in research_output.findings:
            source = self.memory.add_source(Source(
                title=finding.source_title,
                url=finding.source_url,
                credibility_score=finding.credibility_estimate,
                content_summary=finding.content[:200],
            ))
            sources.append(source)
        return sources

    def _persist_claims(self, claims_output, sources):
        """Persist extracted claims through memory service."""
        persisted = []
        source_ids = [s.id for s in sources]

        for claim in claims_output.claims:
            # Map source_id to an actual registered source
            if claim.source_id not in source_ids:
                # Use the first available source as fallback
                if source_ids:
                    claim.source_id = source_ids[0]
                else:
                    logger.warning(
                        "Skipping claim without valid source: %s", claim.subject
                    )
                    continue
            try:
                persisted_claim = self.memory.add_claim(claim)
                persisted.append(persisted_claim)
            except ValueError as e:
                logger.warning("Guardrail blocked claim: %s", e)

        return persisted

    def _process_skeptic_output(self, skeptic_output):
        """
        Process skeptic findings — update credibility and persist gaps.

        Returns:
            List of contradiction tuples (claim_id_a, claim_id_b) where severity > 0.
        """
        positive_contradictions = [
            (c.claim_id_a, c.claim_id_b)
            for c in skeptic_output.contradictions
            if c.severity > 0
        ]
        self.total_contradictions += len(positive_contradictions)

        # Apply credibility challenges
        for challenge in skeptic_output.credibility_challenges:
            try:
                current_source = self.memory.get_source(challenge.target_id)
                if current_source:
                    new_score = max(
                        0.0,
                        current_source.credibility_score + challenge.suggested_adjustment,
                    )
                    self.memory.update_source_credibility(
                        challenge.target_id, new_score
                    )
            except Exception as e:
                logger.debug("Could not apply credibility challenge: %s", e)

        # Add new knowledge gaps
        for gap in skeptic_output.knowledge_gaps:
            self.skeptic_detected_gap_count += 1
            try:
                self.memory.add_knowledge_gap(gap)
            except Exception:
                logger.critical(
                    "CRITICAL: Failed to persist skeptic knowledge gap. "
                    "Aborting run for data integrity."
                )
                raise

        return positive_contradictions

    def _apply_contradiction_influence(
        self,
        contradiction_pairs: List[tuple],
    ) -> None:
        """
        Map contradiction pairs into opposing evidence on supported hypotheses.
        """
        if not contradiction_pairs:
            return

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

    def _persist_hypotheses(self, synthesis_output, all_claims):
        """Persist hypotheses from synthesis output."""
        claim_ids = {c.id for c in all_claims}

        for hyp in synthesis_output.hypotheses:
            # Filter to only existing claim IDs
            valid_supporting = [
                cid for cid in hyp.supporting_claim_ids if cid in claim_ids
            ]
            valid_opposing = [
                cid for cid in hyp.opposing_claim_ids if cid in claim_ids
            ]

            if not valid_supporting:
                # Try to assign at least one claim
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
            except ValueError as e:
                logger.warning("Guardrail blocked hypothesis: %s", e)

    # ─── Metrics Computation ──────────────────────────────────────────────

    def _compute_iteration_metrics(
        self,
        iteration: int,
        prior_art_similarity: float = 0.5,
        gap_count_before: int = 0,
        gap_count_after: int = 0,
        tokens_this_iter: int = 0,
        has_innovations: bool = False,
        new_claims_count: int = 0,
    ) -> IterationMetrics:
        """Compute all metrics for an iteration."""
        all_claims = self.memory.get_all_claims()
        all_hypotheses = self.memory.get_all_hypotheses()
        unresolved_gaps = self.memory.get_unresolved_gaps()

        # Hard guard: ensure no reasoning traces leaked into structured memory.
        self._assert_no_reasoning_artifacts(
            [c.model_dump() for c in all_claims],
            context="claims snapshot before scoring",
        )
        self._assert_no_reasoning_artifacts(
            [h.model_dump() for h in all_hypotheses],
            context="hypotheses snapshot before scoring",
        )
        self._assert_no_reasoning_artifacts(
            [g.model_dump() for g in unresolved_gaps],
            context="knowledge gaps snapshot before scoring",
        )

        # 1. Epistemic risk (computed first for effective confidence)
        avg_uncertainty = compute_average_uncertainty(all_claims)
        normalized_gap_severity = self.memory.get_normalized_gap_severity()
        source_cred_variance = self.memory.get_source_credibility_variance()

        epistemic_risk = compute_epistemic_risk(
            average_uncertainty=avg_uncertainty,
            unresolved_contradictions=max(
                0, self.total_contradictions - self.resolved_contradictions
            ),
            total_claims=len(all_claims) if all_claims else 1,
            normalized_gap_severity=normalized_gap_severity,
            source_credibility_variance=source_cred_variance,
            risk_floor=self.config.risk_floor,
        )
        risk_floor_applied = epistemic_risk == self.config.risk_floor

        # 2. Hypothesis confidence & Effective confidence
        avg_raw_confidence = 0.0
        avg_effective_confidence = 0.0
        if all_hypotheses:
            raw_confidences = []
            effective_confidences = []
            for hyp in all_hypotheses:
                supporting = [
                    c for c in all_claims if c.id in hyp.supporting_claim_ids
                ]
                opposing = [
                    c for c in all_claims if c.id in hyp.opposing_claim_ids
                ]
                
                raw_conf = compute_hypothesis_confidence(
                    supporting, opposing, self.config.epsilon
                )
                eff_conf = compute_effective_confidence(
                    raw_confidence=raw_conf,
                    epistemic_risk=epistemic_risk,
                    supporting_claim_count=len(supporting),
                    opposing_claim_count=len(opposing),
                    contradiction_cycle_count=self.contradiction_cycle_count,
                )

                # Single-source guardrail: multiple supporting claims from one
                # source are still single-source evidence.
                unique_support_sources = {
                    claim.source_id for claim in supporting
                }
                if len(unique_support_sources) < 2:
                    eff_conf = min(eff_conf, 0.85)

                # Update hypothesis confidence in memory
                hyp.confidence = eff_conf
                try:
                    self.memory.update_hypothesis(hyp)
                except Exception:
                    pass
                raw_confidences.append(raw_conf)
                effective_confidences.append(eff_conf)

            avg_raw_confidence = sum(raw_confidences) / len(raw_confidences)
            avg_effective_confidence = sum(effective_confidences) / len(effective_confidences)

        # Novelty score
        graph_bridge = self.memory.get_graph_bridge_score()
        contradiction_resolution = compute_contradiction_resolution_score(
            self.total_contradictions, self.resolved_contradictions
        )
        all_gaps = self.memory.get_all_knowledge_gaps()
        total_gaps = len(all_gaps)
        addressed_gaps = sum(1 for g in all_gaps if g.resolved)
        gap_coverage = compute_knowledge_gap_coverage(total_gaps, addressed_gaps)

        novelty = compute_novelty_score(
            graph_bridge_score=graph_bridge,
            contradiction_resolution_score=contradiction_resolution,
            prior_art_similarity=prior_art_similarity,
            knowledge_gap_coverage=gap_coverage,
        )

        if not has_innovations:
            novelty = min(novelty, 0.5)

        return IterationMetrics(
            iteration=iteration,
            hypothesis_confidence=round(avg_effective_confidence, 6),
            raw_confidence=round(avg_raw_confidence, 6),
            epistemic_risk=epistemic_risk,
            risk_floor_applied=risk_floor_applied,
            novelty_score=novelty,
            new_claims_count=new_claims_count,
            total_claims_count=len(all_claims),
            total_sources_count=self.memory.source_registry.count_sources(),
            unresolved_gaps_count=len(unresolved_gaps),
            gap_count_before=gap_count_before,
            gap_count_after=gap_count_after,
            contradiction_cycle_count=self.contradiction_cycle_count,
            token_usage=tokens_this_iter,
        )

    # ─── Report Generation ────────────────────────────────────────────────

    def _assert_no_reasoning_artifacts(
        self,
        payload: Any,
        context: str,
    ) -> None:
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

    def _assert_token_accounting(self) -> None:
        """Ensure iteration token deltas reconcile exactly with session total."""
        iteration_token_sum = sum(m.token_usage for m in self.iteration_metrics)
        if iteration_token_sum != self.gateway.total_tokens_used:
            raise RuntimeError(
                "CRITICAL: Token accounting mismatch. "
                f"sum(iteration token_usage)={iteration_token_sum} "
                f"!= total_tokens_used={self.gateway.total_tokens_used}"
            )

    def _generate_final_report(
        self,
        research_objective: str,
        mode: str,
        termination_reason: str,
        total_iterations: int,
        total_time: float,
        innovation_output=None,
    ) -> FinalReport:
        """Generate the final structured report."""
        all_claims = self.memory.get_all_claims()
        all_hypotheses = self.memory.get_all_hypotheses()
        all_gaps = self.memory.get_all_knowledge_gaps()
        self._assert_no_reasoning_artifacts(
            [c.model_dump() for c in all_claims],
            context="claims at final report generation",
        )
        self._assert_no_reasoning_artifacts(
            [h.model_dump() for h in all_hypotheses],
            context="hypotheses at final report generation",
        )
        self._assert_no_reasoning_artifacts(
            [g.model_dump() for g in all_gaps],
            context="knowledge gaps at final report generation",
        )

        # Build innovation proposals
        proposals = []
        if innovation_output:
            for p in innovation_output.proposals:
                novelty_val = p.estimated_novelty
                proposals.append(InnovationProposal(
                    title=p.title,
                    description=p.description,
                    differentiation_summary=p.differentiation,
                    novelty_score=novelty_val,
                    novelty_interpretation=interpret_novelty(novelty_val),
                    prior_art_references=p.prior_art_references,
                    addressed_knowledge_gaps=p.addressed_gaps,
                ))

        # Sort claims by confidence
        key_claims = sorted(
            all_claims, key=lambda c: c.confidence_estimate, reverse=True
        )[:20]

        # Build executive summary
        last_metrics = self.iteration_metrics[-1] if self.iteration_metrics else None
        summary = (
            f"Research on '{research_objective}' completed in "
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
        summary += f"Termination reason: {termination_reason}"

        # Generate conclusion via LLM
        conclusion = self._generate_conclusion(
            research_objective, all_hypotheses, key_claims, all_gaps, last_metrics
        )

        return FinalReport(
            session_id=self.memory.session_id,
            research_objective=research_objective,
            executive_summary=summary,
            conclusion=conclusion,
            mode=mode,
            hypotheses=all_hypotheses,
            key_claims=key_claims,
            knowledge_gaps=all_gaps,
            final_epistemic_risk=last_metrics.epistemic_risk if last_metrics else 1.0,
            final_novelty_score=last_metrics.novelty_score if last_metrics else 0.0,
            final_hypothesis_confidence=last_metrics.hypothesis_confidence if last_metrics else 0.0,
            innovation_proposals=proposals,
            iteration_metrics=self.iteration_metrics,
            total_iterations=total_iterations,
            total_tokens_used=self.gateway.total_tokens_used,
            total_execution_time_seconds=round(total_time, 2),
            termination_reason=termination_reason,
        )

    def _generate_conclusion(
        self,
        research_objective: str,
        hypotheses: list,
        key_claims: list,
        knowledge_gaps: list,
        last_metrics,
    ) -> str:
        """Use the LLM to generate a clear, direct conclusion."""
        try:
            # Build hypothesis summaries
            hyp_lines = []
            for h in hypotheses[:8]:
                status = h.status if hasattr(h, 'status') else 'unknown'
                conf = h.confidence if hasattr(h, 'confidence') else 0
                supporting = len(h.supporting_claim_ids) if hasattr(h, 'supporting_claim_ids') else 0
                opposing = len(h.opposing_claim_ids) if hasattr(h, 'opposing_claim_ids') else 0
                hyp_lines.append(
                    f"- [{status}, confidence={conf:.2f}, "
                    f"supporting={supporting}, opposing={opposing}] "
                    f"{h.statement}"
                )
            hyp_text = "\n".join(hyp_lines) if hyp_lines else "No hypotheses formed."

            # Top claims
            claim_lines = []
            for c in key_claims[:10]:
                claim_lines.append(f"- {c.subject} {c.relation} {c.object} (confidence: {c.confidence_estimate:.2f})")
            claims_text = "\n".join(claim_lines) if claim_lines else "No claims."

            # Gaps
            gap_lines = []
            for g in knowledge_gaps[:5]:
                gap_lines.append(f"- {g.description} (severity: {g.severity:.2f})")
            gaps_text = "\n".join(gap_lines) if gap_lines else "No major gaps."

            risk = last_metrics.epistemic_risk if last_metrics else 1.0
            confidence = last_metrics.hypothesis_confidence if last_metrics else 0.0

            prompt = (
                f"You are a senior research analyst. Based on the following research findings, "
                f"write a CLEAR, DIRECT, and CONCLUSIVE answer to the research question.\n\n"
                f"RESEARCH QUESTION: {research_objective}\n\n"
                f"HYPOTHESES:\n{hyp_text}\n\n"
                f"KEY EVIDENCE:\n{claims_text}\n\n"
                f"UNRESOLVED GAPS:\n{gaps_text}\n\n"
                f"OVERALL CONFIDENCE: {confidence:.3f} | EPISTEMIC RISK: {risk:.3f}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Start with a direct, one-sentence answer to the research question\n"
                f"2. Explain the key evidence supporting this conclusion (2-3 sentences)\n"
                f"3. Acknowledge any important caveats or nuances (1-2 sentences)\n"
                f"4. End with an overall confidence assessment\n\n"
                f"Be specific, cite findings, and give a definitive answer. "
                f"Do NOT be vague or hedge excessively. The user wants a clear conclusion.\n\n"
                f"Write ONLY the conclusion text, no JSON, no headers, no formatting."
            )

            from schemas.agent_io import ReflectionOutput
            # Use a simple raw LLM call for conclusion (not schema-validated)
            from config import ModelConfig
            model_config = self.config.get_model_config("synthesis")

            messages = [{"role": "user", "content": prompt}]

            # Direct API call for plain text
            headers = {
                "Authorization": f"Bearer {self.config.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model_config.model_id,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 800,
            }
            import requests as req
            response = req.post(
                self.config.openrouter_base_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            conclusion = result["choices"][0]["message"]["content"].strip()

            logger.info("Generated conclusion (%d chars)", len(conclusion))
            return conclusion

        except Exception as exc:
            logger.warning("Failed to generate conclusion: %s", exc)
            # Fallback: build a basic conclusion from hypotheses
            if hypotheses:
                best = max(hypotheses, key=lambda h: getattr(h, 'confidence', 0))
                return (
                    f"Based on the analysis of {len(key_claims)} claims across "
                    f"multiple sources, the strongest finding is: {best.statement} "
                    f"(confidence: {best.confidence:.1%}). "
                    f"This conclusion carries an epistemic risk of "
                    f"{last_metrics.epistemic_risk:.1% if last_metrics else 'unknown'}."
                )
            return "Insufficient evidence to draw a definitive conclusion."

        except Exception as exc:
            logger.warning("Failed to generate conclusion: %s", exc)
            return "Insufficient evidence to draw a definitive conclusion."
