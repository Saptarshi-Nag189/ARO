# System Architecture

## Overview

ARO is a multi-agent research engine with deterministic orchestration, model-agnostic LLM access, schema-enforced communication, and quantitative evaluation.

## Component Layers

### 1. Agent Layer

Eight specialized agents, each with strict I/O contracts:

| Agent | Input | Output | Temperature |
|-------|-------|--------|-------------|
| **Planner** | Research objective | Sub-questions, search strategies, iteration targets | 0.5 |
| **Research** | Research plan | Raw findings with source metadata | 0.7 |
| **Claim Extraction** | Raw findings | Atomic structured claims | 0.3 |
| **Skeptic** | Claims + hypotheses | Contradictions, credibility challenges, knowledge gaps | 0.6 |
| **Synthesis** | Validated claims | Hypotheses, merged conclusions, relationships | 0.6 |
| **Innovation** | Hypotheses + gaps + prior art | Innovation proposals with novelty assessment | 0.8 |
| **Reflection** | Full iteration state | Meta-analysis, strategy adjustments, continue/stop | 0.5 |
| **Orchestrator** | Research objective + mode | Final structured report | 0.4 |

### 2. Runtime Layer

- **ModelGateway**: Wraps OpenRouter API. Enforces JSON output, validates against Pydantic schemas, retries on malformed output (max 3), tracks token usage.
- **SessionLogger**: Structured JSON logs per iteration at `logs/{session_id}/iteration_X.json`.

### 3. Memory Layer

- **SQLite** database with 5 tables: Sessions, Sources, Claims, Hypotheses, KnowledgeGaps
- **NetworkX** in-memory directed graph for hypothesis-claim relationships
- **MemoryService** facade: single mutation point with guardrail enforcement
- **Claim deduplication**: subject/object similarity > 0.85 + identical relation → merge

### 4. Evaluation Engine

Three mathematical models computed each iteration:

- **HypothesisConfidence** — evidence-weighted support vs. opposition
- **EpistemicRisk** — uncertainty, contradictions, gaps, credibility variance
- **NoveltyScore** — graph bridges, contradiction resolution, prior art distance, gap coverage

### 5. Termination Controller

Four conditions, any triggers stop:

1. Risk converged + no new claims (2 iterations)
2. Novelty plateau (delta < 0.03 over 3 iterations)
3. Max iterations reached
4. Budget cap exceeded

## Execution Flow

```
User Input → Planner → Research → Claim Extraction → Skeptic →
    Synthesis → [Innovation] → Reflection → Evaluation →
    Termination Check → (loop or stop) → Final Report
```

## Data Flow Invariants

1. All agent output passes through ModelGateway with schema validation
2. All memory mutations pass through MemoryService
3. Only Orchestrator controls loop execution
4. No agent accesses the database directly
5. No agent modifies global state
