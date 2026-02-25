# Reasoning Trace Mode Isolation

The ARO system implements a **Reasoning Trace Mode** specifically designed to support the `audit` mode while maintaining absolute epistemic hygiene in `production`. This document outlines the rationale, rules, and architecture of the isolation.

## Rationale for Complete Isolation

OpenRouter and newer LLMs provide `reasoning_traces` which contain raw, introspective, out-of-band "thoughts" preceding the final output. While useful for debugging and audit logging, passing these into the system's memory poses significant risks:

1. **Epistemic Contamination:** Reasoning traces often contain unverified leaps of logic, contradictory statements, or discarded hypotheses. Allowing these into the persistent `MemoryService` pollutes the structured epistemology of the system.
2. **Scoring Distortion:** The mathematical scoring engine relies on atomic, verified claims. Reasoning traces are unstructured blobs that would artificially inflate source volume without adding verifiability.
3. **Agent Cross-Talk:** If an agent sees another agent's unstructured reasoning trace, it encourages "hallucination bridging," where subsequent agents treat the implicit thought process as canonical proven fact.

## How Isolation is Enforced

The isolation is enforced at four distinct layers, creating an airtight seal against leakage:

### 1. The Gateway Guard

The `ModelGateway` handles the OpenRouter request. If `mode == "production"`, reasoning traces are entirely disabled in the API payload. If OpenRouter mistakenly returns a reasoning trace in production, a `HARD GUARD VIOLATION` error is aggressively thrown to halt execution.

### 2. The Disk Isolation

If `mode == "audit"`, the `reasoning_details` are surgically extracted during the validated parsing phase and written directly to a standalone debug directory (`logs/{session_id}/reasoning_traces/`). They are **removed completely** before the `gateway.call()` returns the Pydantic schema to the calling Agent.

### 3. The Object Sanitization

Agents (and consequently the `MemoryService`) only ever receive the validated Pydantic object. Pydantic's strict parsing ensures that any unstructured json keys are discarded, making it impossible for reasoning traces to enter the formal iteration cycle natively.

### 4. The Runtime Snapshot Verification

Right before the Orchestrator calculates the `HypothesisConfidence`, `EpistemicRisk`, and `NoveltyScore` at the end of every iteration, it performs a full validation loop over the entire `MemoryService` snapshot of claims, hypotheses, and knowledge gaps. If the `reasoning_details` key is detected, a `HARD GUARD VIOLATION` is triggered.

## Audit Mode Behavior

In `'audit'` mode, reasoning traces are enabled so humans can review the raw logic paths of the agents. However, the exact same isolation rules apply. The **only** behavioral difference allowed is that the `ReflectionAgent` prompt is slightly appended to let the model know it may internally *use* its own tracing logic safely, so long as it respects the exact same structured JSON output constraints.

```bash
# Running in Audit Mode
python main.py --objective "Your research query" --mode audit
```
