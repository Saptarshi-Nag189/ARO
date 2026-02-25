# Agent Contracts

Every agent accepts structured input and returns Pydantic-validated JSON.

## Planner Agent

**Input**: Research objective (string) + optional iteration context  
**Output**: `PlannerOutput`

```json
{
  "research_objective_summary": "Restated objective",
  "sub_questions": [
    {
      "question": "What is X?",
      "priority": 1,
      "search_strategy": "academic"
    }
  ],
  "iteration_targets": ["target1", "target2"],
  "recommended_sources": ["source1"]
}
```

---

## Research Agent

**Input**: Research plan with sub-questions  
**Output**: `ResearchOutput`

```json
{
  "findings": [
    {
      "content": "Raw finding text",
      "source_title": "Paper Title",
      "source_url": "https://...",
      "credibility_estimate": 0.85,
      "relevance": 0.9
    }
  ],
  "sources_consulted": 5,
  "search_queries_used": ["query1", "query2"]
}
```

---

## Claim Extraction Agent

**Input**: Raw research findings + source ID mapping  
**Output**: `ClaimExtractionOutput`

```json
{
  "claims": [
    {
      "subject": "Transformer",
      "relation": "outperforms",
      "object": "LSTM",
      "qualifiers": ["on NLP benchmarks"],
      "source_id": "src_abc123",
      "confidence_estimate": 0.9,
      "credibility_weight": 0.85
    }
  ],
  "extraction_notes": "Some claims were ambiguous"
}
```

---

## Skeptic Agent

**Input**: All claims + all hypotheses  
**Output**: `SkepticOutput`

```json
{
  "contradictions": [
    {
      "claim_id_a": "claim_001",
      "claim_id_b": "claim_005",
      "description": "Conflicting results",
      "severity": 0.7
    }
  ],
  "credibility_challenges": [
    {
      "target_id": "src_003",
      "reason": "Blog post without citations",
      "suggested_adjustment": -0.3
    }
  ],
  "knowledge_gaps": [
    {
      "description": "No data on long-term effects",
      "severity": 0.8,
      "suggested_queries": ["long-term effects of X"]
    }
  ],
  "overall_assessment": "Evidence is strong but lacks diversity"
}
```

---

## Synthesis Agent

**Input**: Validated claims + existing hypotheses  
**Output**: `SynthesisOutput`

```json
{
  "hypotheses": [
    {
      "statement": "X improves Y by mechanism Z",
      "supporting_claim_ids": ["claim_001", "claim_003"],
      "opposing_claim_ids": ["claim_005"],
      "status": "supported"
    }
  ],
  "merged_claims": ["claim_002"],
  "narrative_summary": "The evidence suggests...",
  "relationships": [
    {"from": "hyp_001", "to": "hyp_002", "type": "extends"}
  ]
}
```

---

## Innovation Agent

**Input**: Synthesis + prior art scan + knowledge gaps  
**Output**: `InnovationOutput`

```json
{
  "proposals": [
    {
      "title": "Novel Approach to X",
      "description": "Detailed description...",
      "differentiation": "Unlike prior art, this...",
      "prior_art_references": ["Patent US123"],
      "estimated_novelty": 0.78,
      "addressed_gaps": ["gap_001"]
    }
  ],
  "prior_art_summary": "Existing work covers...",
  "overall_novelty_assessment": "High potential"
}
```

---

## Reflection Agent

**Input**: Full iteration state + metrics  
**Output**: `ReflectionOutput`

```json
{
  "meta_analysis": "Research is converging on...",
  "confidence_trend": "Increasing steadily",
  "gap_assessment": "2 critical gaps remain",
  "strategy_adjustments": [
    {
      "area": "Source diversity",
      "current_approach": "General web search",
      "suggested_change": "Add academic sources",
      "rationale": "Current sources lack peer review"
    }
  ],
  "should_continue": true,
  "continuation_rationale": "Unresolved gaps warrant more investigation"
}
```
