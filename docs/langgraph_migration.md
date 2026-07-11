# The LangGraph Migration (v2 → v3)

ARO v2 ran on a hand-rolled orchestrator: a 1,086-line `Orchestrator`
class owning a `while True:` loop, manual `asyncio.gather` for the two
parallel stages, and no persistence of execution state. v3 re-expresses
the same pipeline as a compiled LangGraph `StateGraph`. This document is
the honest engineering record: what mapped cleanly, what LangGraph gave
us for free, what it forced us to fix, and what we deliberately kept.

## What mapped cleanly

The v2 design turned out to be *accidentally graph-shaped*, which made
the port mostly mechanical:

| v2 | v3 |
|---|---|
| `Orchestrator.run()` while-loop | `StateGraph` with a conditional back-edge from `record` |
| `asyncio.to_thread` + `gather` for Skeptic ‖ Synthesis | two plain edges out of `extract_claims` (native superstep parallelism) |
| `BaseAgent.run()` → `ModelGateway.call()` | agents became pure specs (prompt + Pydantic schema); execution moved to `graph/structured.py` over LangChain chat models |
| Gateway's JSON-retry-with-correction loop | ported verbatim onto `BaseChatModel.invoke` — free OpenRouter models still don't do reliable tool-calling, so prompt-enforced JSON + retry remains the right call |
| `TerminationChecker` | unchanged — but now replayed from checkpointed histories, making termination a pure function of state |
| Per-agent model routing in `config.py` | unchanged, consumed by the model factory (`graph/models.py`) |

The seven agent prompts and all Pydantic output schemas are **byte-for-byte
the same**. If answer quality changed, the eval suite would have caught
it — that's what it's for.

## What LangGraph gave us that v2 could not do

1. **Durable execution.** The full typed state is checkpointed after
   every node. v2 lost everything on a crash mid-run; v3 resumes from
   the last node boundary (`--resume`). In production the checkpointer
   is RDS Postgres, so runs survive deploys.

2. **Real human-in-the-loop.** v2's "interactive mode" was a stub — it
   logged *"Continuing automatically (override not connected)"*. v3
   parks the graph in an `interrupt()`; the human's answer (continue /
   stop / redirect) resumes it, even from a different process, hours
   later. The redirect path feeds a `human_directive` into a re-plan.

3. **Time travel.** `get_state_history()` exposes every checkpoint for
   inspection or forking. Debugging "why did confidence drop at
   iteration 3?" is now a data query, not printf archaeology.

4. **Observability.** With `LANGSMITH_TRACING=true` every node, agent
   call, retry, and token count is traced. v2 had structured JSON logs;
   v3 has those *plus* full traces that power the CI eval gate.

## What the migration forced us to fix

Porting is a code review. Three real defects surfaced:

1. **`max_iterations` was never enforced.** v2's `TerminationChecker`
   accepted the parameter and ignored it; the loop relied on the
   novelty plateau to stop. v3's `record` node enforces the ceiling
   (and a regression test now pins it).

2. **Fast-mode reports trusted the model's echo.** The final report's
   `research_objective` came from the LLM's restatement of the
   question, not the question itself — a hallucinated echo would
   mislabel the report. v3 stamps the user's actual objective.

3. **SQLite across threads.** v2 ran everything on one thread, hiding
   the fact that the memory connection was thread-bound. LangGraph
   executes parallel nodes on workers, which forced an explicit
   concurrency design instead of an accidental one: parallel branches
   (skeptic ‖ synthesis, innovation ‖ reflection) are **pure LLM calls
   over snapshots**; every database write lives in a single-writer node
   (`extract_claims`, `integrate`, `record`, `finalize`).

## Design decisions worth defending

- **Deterministic termination stayed deterministic.** It would have
  been fashionable to let the reflection agent decide when to stop.
  We kept v2's rule: agents advise, math decides. The reflection
  output's `advisory_should_stop` is logged and ignored, exactly as
  before.

- **Token accounting is an invariant, not a metric.** `finalize` raises
  if per-iteration token sums don't reconcile exactly with the run
  total. This caught two accounting bugs during the migration itself.

- **The interrupt node contains only the interrupt.** LangGraph
  re-executes a node from its start on resume, so any side effect
  before an `interrupt()` would replay. `record` (side effects) and
  `human_gate` (interrupt only) are separate nodes for exactly this
  reason.

- **Structured output by prompt contract, not tool calling.** The
  free-tier models this project deliberately targets don't do reliable
  function calling. The v2 retry-with-correction loop was kept and
  wrapped in LangChain messages so every failed attempt is visible in
  traces — pragmatism over fashion.

## What was deleted

- `agents/orchestrator.py` (1,086 lines) and `agents/fast_orchestrator.py`
  → `graph/` (nodes + assembly, ~1,100 lines, but now checkpointed,
  interruptible, traced, and tested)
- `runtime/model_gateway.py` (552 lines) → `graph/models.py` +
  `graph/structured.py` (~330 lines)
- The `app.py` monkey-patch that intercepted orchestrator internals for
  SSE → nodes emit events through an injected callback
- `google-adk` dependency (declared, never imported)

Net: the engine is roughly the same size, but ~40% of it is now
LangGraph-native capability (durability, interrupts, tracing) that v2
simply didn't have.

## Reference docs

`docs/mathematical_models.md` and `docs/agent_contracts.md` describe the
scoring math and agent I/O contracts — both unchanged in v3.
`docs/system_architecture.md` describes the v2 orchestrator and remains
useful for the memory/tooling layers; this document supersedes its
execution-flow sections.
