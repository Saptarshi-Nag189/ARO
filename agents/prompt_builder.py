"""
Prompt Builder
==============
Dedicated service for constructing LLM prompts for each agent.
Contains the domain-specific logic to format state into readable strings,
with instructions explicitly optimized for comprehensive and detailed outputs.

Aligned with schemas: agent_io.py, claims.py, hypotheses.py, knowledge_gaps.py
"""

from typing import List, Dict, Any, Optional
from schemas.agent_io import (
    ResearchOutput, PlannerOutput, SkepticOutput, ResearchFinding,
)
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.reports import IterationMetrics


class PromptBuilder:
    """Constructs focused, context-rich prompts for the ARO agents."""

    # ─── Research Agent ───────────────────────────────────────────────────

    @staticmethod
    def build_research_prompt(
        objective: str,
        plan: PlannerOutput,
        iteration: int,
        web_context: str = "",
    ) -> str:
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
                "6. Rate web-sourced findings with higher credibility (0.7-0.95).\n"
                "7. Be EXTREMELY thorough. Extract every quantitative metric, technical\n"
                "   detail, and contextual nuance. Do NOT summarize — give full detail.\n\n"
            )
        else:
            prompt += (
                "Note: No web search results available for this iteration.\n"
                "Use your training knowledge to provide findings.\n\n"
            )

        prompt += (
            "Conduct thorough research and return structured findings with source metadata.\n"
            "Prioritize DEPTH over breadth — the user expects highly detailed, "
            "comprehensive results, not brief summaries."
        )
        return prompt

    # ─── Claim Extraction Agent ───────────────────────────────────────────

    @staticmethod
    def build_extraction_prompt(
        research_output: ResearchOutput,
        sources: list,
    ) -> str:
        """Build extraction prompt. `sources` is a list of Source objects."""
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
            f"Findings:\n{findings_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. Break complex sentences into MULTIPLE atomic claims.\n"
            "2. Preserve detailed technical specifics within the claim content.\n"
            "3. Each claim MUST reference an existing source_id from the list above.\n"
            "4. Estimate initial confidence (0.0 to 1.0) based on source credibility and definitiveness."
        )

    # ─── Skeptic Agent ────────────────────────────────────────────────────

    @staticmethod
    def build_skeptic_prompt(
        claims: List[Claim],
        hypotheses: List[Hypothesis],
    ) -> str:
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
            "Identify contradictions, credibility issues, and knowledge gaps.\n\n"
            "INSTRUCTIONS:\n"
            "1. Be specific about WHY each gap matters and WHAT exact data is missing.\n"
            "2. For each contradiction, explain the logical conflict in detail.\n"
            "3. Provide a comprehensive overall_assessment that synthesizes your analysis."
        )

    # ─── Synthesis Agent ──────────────────────────────────────────────────

    @staticmethod
    def build_synthesis_prompt(
        claims: List[Claim],
        existing_hypotheses: List[Hypothesis],
    ) -> str:
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
            "INSTRUCTIONS:\n"
            "- Each hypothesis 'statement' should be HIGHLY DESCRIPTIVE, capturing "
            "the nuance of the underlying claims — not just a one-sentence summary.\n"
            "- The narrative_summary should be comprehensive and insightful.\n\n"
            "Strict output constraints:\n"
            "- Return at most 8 hypotheses.\n"
            "- Return at most 20 merged_claims.\n"
            "- Return at most 12 relationships.\n"
            "- relationships must be a JSON LIST of objects.\n"
            "- Each relationship object must have ONLY these string keys:\n"
            "  source_hypothesis_id, target_hypothesis_id, relationship_type.\n"
            "- Keep narrative_summary <= 180 words."
        )

    # ─── Innovation Agent ─────────────────────────────────────────────────

    @staticmethod
    def build_innovation_prompt(
        synthesis_narrative: str,
        prior_art: dict,
        gaps: List[KnowledgeGap],
    ) -> str:
        gaps_text = "\n".join(
            f"  [{g.id}] {g.description} (severity: {g.severity})"
            for g in gaps
        ) if gaps else "  (No unresolved gaps)"

        return (
            f"Generate innovation proposals based on the research synthesis.\n\n"
            f"Synthesis Summary:\n{synthesis_narrative}\n\n"
            f"Prior Art Scan:\n{__import__('json').dumps(prior_art, indent=2)}\n\n"
            f"Unresolved Knowledge Gaps:\n{gaps_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. Generate highly detailed, comprehensive proposals.\n"
            "2. Explicitly outline how each proposal solves specific knowledge gaps.\n"
            "3. Provide a deep analysis of differentiation from existing paradigms.\n"
            "4. Estimate novelty (0.0 to 1.0) and categorize as incremental, derivative, or patent-grade.\n"
            "Propose novel innovations that differentiate from prior art "
            "and address knowledge gaps."
        )

    # ─── Reflection Agent ─────────────────────────────────────────────────

    @staticmethod
    def build_reflection_prompt(
        objective: str,
        metrics: IterationMetrics,
        iteration: int,
    ) -> str:
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
            "INSTRUCTIONS:\n"
            "1. Analyze convergence: Are confidence and risk stabilizing?\n"
            "2. Decide if another iteration will yield significant new information.\n"
            "3. Provide a highly detailed `detailed_reasoning` block explaining exactly "
            "which metrics drove your decision.\n"
            "4. If continuing, specify what the next iteration should focus on.\n"
            "Provide meta-analysis, trend assessment, and strategy recommendations."
        )

    # ─── Conclusion Generator ─────────────────────────────────────────────

    @staticmethod
    def build_conclusion_prompt(
        research_objective: str,
        hypotheses: List[Hypothesis],
        key_claims: List[Claim],
        knowledge_gaps: List[KnowledgeGap],
        last_metrics: Optional[IterationMetrics],
    ) -> str:
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

        claim_lines = [
            f"- {c.subject} {c.relation} {c.object} (confidence: {c.confidence_estimate:.2f})"
            for c in key_claims[:10]
        ]
        claims_text = "\n".join(claim_lines) if claim_lines else "No claims."

        gap_lines = [
            f"- {g.description} (severity: {g.severity:.2f})"
            for g in knowledge_gaps[:5]
        ]
        gaps_text = "\n".join(gap_lines) if gap_lines else "No major gaps."

        risk = last_metrics.epistemic_risk if last_metrics else 1.0
        confidence = last_metrics.hypothesis_confidence if last_metrics else 0.0

        return (
            f"You are a senior research analyst. Based on the following research findings, "
            f"write a CLEAR, DIRECT, COMPREHENSIVE, and CONCLUSIVE answer to the research question.\n\n"
            f"RESEARCH QUESTION: {research_objective}\n\n"
            f"HYPOTHESES:\n{hyp_text}\n\n"
            f"KEY EVIDENCE:\n{claims_text}\n\n"
            f"UNRESOLVED GAPS:\n{gaps_text}\n\n"
            f"OVERALL CONFIDENCE: {confidence:.3f} | EPISTEMIC RISK: {risk:.3f}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Start with a direct, one-sentence answer to the research question\n"
            f"2. Explain the key evidence supporting this conclusion IN DETAIL (3-5 sentences)\n"
            f"3. Acknowledge any important caveats or nuances (1-2 sentences)\n"
            f"4. End with an overall confidence assessment\n\n"
            f"Be specific, cite findings, and give a definitive answer. "
            f"Do NOT be vague or hedge excessively. The user wants a clear, detailed conclusion.\n\n"
            f"Write ONLY the conclusion text, no JSON, no headers, no formatting."
        )
