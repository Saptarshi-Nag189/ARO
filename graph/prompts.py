"""
Prompt Construction
===================
The proven prompt builders from the v2 orchestrator, extracted as pure
functions so graph nodes stay thin. Changing anything in this file
should trigger the eval gate in CI — prompt edits are the most common
source of silent quality regressions.
"""

import json
from typing import Any, Dict, List, Optional


def build_planner_prompt(objective: str, context: Optional[Dict[str, Any]] = None) -> str:
    prompt = (
        f"Research Objective: {objective}\n\n"
        f"Create a detailed research plan with sub-questions, "
        f"search strategies, and iteration targets."
    )
    if context:
        prompt += f"\n\nContext from previous iterations:\n{json.dumps(context, indent=2, default=str)}"
    return prompt


def build_research_prompt(objective: str, plan, iteration: int, web_context: str = "") -> str:
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


def build_extraction_prompt(research_output, sources) -> str:
    findings_text = "\n\n".join(
        f"Finding {i+1} (source: {f.source_title}, "
        f"credibility: {f.credibility_estimate}):\n{f.content}"
        for i, f in enumerate(research_output.findings)
    )
    source_map = "\n".join(f"  {s.id}: {s.title}" for s in sources)
    return (
        f"Extract atomic claims from the following research findings.\n\n"
        f"Available source IDs:\n{source_map}\n\n"
        f"Findings:\n{findings_text}"
    )


def build_skeptic_prompt(claims, hypotheses) -> str:
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


def build_synthesis_prompt(claims, existing_hypotheses) -> str:
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


def build_innovation_prompt(synthesis, prior_art: Dict[str, Any], gaps) -> str:
    gaps_text = "\n".join(
        f"  [{g.id}] {g.description} (severity: {g.severity})"
        for g in gaps
    ) if gaps else "  (No unresolved gaps)"

    return (
        f"Generate innovation proposals based on the research synthesis.\n\n"
        f"Synthesis Summary:\n{synthesis.narrative_summary}\n\n"
        f"Prior Art Scan:\n{json.dumps(prior_art, indent=2, default=str)}\n\n"
        f"Unresolved Knowledge Gaps:\n{gaps_text}\n\n"
        f"Propose novel innovations that differentiate from prior art "
        f"and address knowledge gaps."
    )


def build_reflection_prompt(objective: str, metrics, iteration: int) -> str:
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


def build_conclusion_prompt(
    objective: str,
    hypotheses: List,
    key_claims: List,
    knowledge_gaps: List,
    confidence: float,
    risk: float,
) -> str:
    hyp_lines = []
    for h in hypotheses[:8]:
        status = getattr(h, "status", "unknown")
        conf = getattr(h, "confidence", 0)
        supporting = len(getattr(h, "supporting_claim_ids", []))
        opposing = len(getattr(h, "opposing_claim_ids", []))
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

    return (
        f"You are a senior research analyst. Based on the following research findings, "
        f"write a CLEAR, DIRECT, and CONCLUSIVE answer to the research question.\n\n"
        f"RESEARCH QUESTION: {objective}\n\n"
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


def build_fast_synthesis_prompt(objective: str, context: str) -> str:
    return (
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
