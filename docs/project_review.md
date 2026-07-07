# ARO — Project Review & Improvement Plan

**Review date:** July 2026
**Scope:** Full codebase — orchestration, agents, memory, evaluation, tools, web server, UI build, deployment.

This document records a full audit of the ARO codebase: what the project is, confirmed bugs (with file/line references), design flaws, security observations, and a prioritized list of improvements and upgrades.

---

## 1. Project Understanding

ARO (Autonomous Research Operator) is a multi-agent research engine. A deterministic **Orchestrator** (`agents/orchestrator.py`) runs an iterative loop — Plan → Web Search → Research → Claim Extraction → Skeptic ‖ Synthesis → [Innovation] ‖ Reflection → metrics → termination check — over 7 LLM agents that talk to OpenRouter through a schema-validating **ModelGateway** (`runtime/model_gateway.py`). State is persisted in a three-tier memory: SQLite (claims/hypotheses/sources/gaps, session-scoped composite PKs), ChromaDB (cross-session semantic index), and in-process TTL caches. Mathematical scoring (`evaluation/`) produces per-iteration confidence, epistemic risk, and novelty. A Flask app (`app.py`) exposes the pipeline over a REST + SSE API and serves a React dashboard. A `FastOrchestrator` provides a single-pass "fast mode".

The architecture is genuinely well thought out: strict Pydantic I/O contracts per agent, guardrails at the memory facade, deterministic termination separated from LLM "advisory" signals, and session-scoped composite keys with a careful in-place migration (`memory/db.py`). The issues below are mostly in the *wiring* — several advertised mechanisms are dead code or never close the loop.

---

## 2. Confirmed Bugs

### Critical

#### 2.1 `max_iterations` is never enforced — the research loop can run unbounded
`evaluation/termination.py:54-90` — `should_terminate()` checks the budget cap, `min_iterations`, risk convergence, and novelty plateau, but **never compares `current_iteration` against `self.max_iterations`**, even though the value is stored (`termination.py:28`). The orchestrator loop is `while True:` (`agents/orchestrator.py:138`) with no other ceiling. The `--max-iterations` CLI flag and the clamped `max_iterations` in `/api/run` therefore do nothing. If risk stays high and novelty oscillates by more than 0.03, the loop never stops.

**Compounding it:** the budget condition is also dead. `TerminationChecker.record_iteration()` is called without `iteration_cost_usd` (`orchestrator.py:344-348`), so `budget_used` stays `0.0` forever and the `budget_cap_usd` check can never fire.

**Fix:** add `if current_iteration >= self.max_iterations: return True, "max_iterations reached"` as the first structural check, and derive an estimated cost from token usage (or drop the budget check honestly).

#### 2.2 Invalid f-string crashes the conclusion fallback path
`agents/orchestrator.py:1080`:

```python
f"{last_metrics.epistemic_risk:.1% if last_metrics else 'unknown'}"
```

The conditional is inside the *format spec*, not a nested replacement field. Verified: this raises `ValueError: Invalid format specifier` at runtime. So whenever the primary LLM conclusion call fails **and** hypotheses exist, the fallback itself throws, the exception propagates out of `_generate_conclusion`'s first `except` block… except it doesn't — it's raised *inside* the handler, so the whole report generation crashes after a full (potentially multi-minute) research run. Additionally, if `last_metrics` is `None`, `last_metrics.epistemic_risk` would raise `AttributeError` before the format spec is even applied, and the second `except Exception` block at `orchestrator.py:1084-1086` is unreachable dead code.

**Fix:** compute the risk string outside the f-string; delete the duplicate `except`.

#### 2.3 Production Docker deployment breaks SSE/session APIs (4 workers × in-memory state)
`app.py:38-39` keeps `_progress_queues` and `_session_status` in process memory, but the shipped `Dockerfile` runs `gunicorn -w 4`. `POST /api/run` lands on worker A; the subsequent `GET /api/stream/<id>` has a 75% chance of hitting a worker that has never heard of the session and returns 404 (`app.py:279-281`). `/api/health` similarly undercounts active sessions, and the `MAX_CONCURRENT_SESSIONS` cap is effectively 4× the configured value.

**Fix:** either run a single worker (`-w 1 --threads N` — the workload is I/O-bound anyway), or move session state to a shared store (Redis, or SQLite-backed status table).

#### 2.4 Novelty score is permanently capped at 0.5 — "patent-grade" is unreachable
`agents/orchestrator.py:242-250` computes iteration metrics with `has_innovations=False` *before* the Innovation agent runs (the value is needed for the reflection prompt). `_compute_iteration_metrics` then applies `novelty = min(novelty, 0.5)` (`orchestrator.py:836-837`). After innovation runs, `has_innovations` is computed (`orchestrator.py:289-291`) but **the metric is never recomputed** — `has_innovations_for_metrics` (`orchestrator.py:239`) is assigned and never used. Result: even in innovation mode with proposals generated, `novelty_score` can never exceed 0.5, so the `> 0.75` "patent-grade" interpretation for the session score is unreachable, and the novelty-plateau termination check operates on distorted values.

**Fix:** recompute (or at least re-apply the cap decision to) the novelty score after the innovation step, before recording metrics.

#### 2.5 Contradictions can never be resolved; knowledge gaps can never be resolved
Two counters/state transitions have no writer anywhere in the codebase:

- `self.resolved_contradictions` is initialized (`orchestrator.py:100`) and read (`orchestrator.py:765,822`) but **never incremented**. Once the Skeptic reports any contradiction, `contradiction_resolution_score` drops to 0 permanently (novelty ↓) and the unresolved-contradiction term of epistemic risk grows monotonically. The README's "cross-source contradictions detected **and resolved**" is only half true.
- `MemoryService.resolve_knowledge_gap()` (`memory/memory_service.py:207`) is **never called**. Gaps only accumulate, so `knowledge_gap_coverage` is always 0 (`orchestrator.py:826-827`) and the gap-severity term of risk never decreases.

Together with 2.4, this means two of the four novelty components are structurally frozen and risk is biased upward the longer a session runs — directly affecting termination behavior.

**Fix:** give the Skeptic/Synthesis outputs a way to mark contradictions resolved and gaps addressed (e.g. IDs in `SynthesisOutput`), and wire the orchestrator to apply them.

#### 2.6 Session-state memory leak: successful sessions are never evicted
`_evict_old_sessions()` (`app.py:394-405`) only evicts entries whose `completed_at` is older than the cutoff — but `completed_at` is **only set on the error path** (`app.py:215-218`). Successful runs just set `{"status": "complete"}` (`app.py:210`), so `s.get("completed_at", float("inf"))` is always `inf` and they are never evicted. `_session_status` (and, for clients that never open the SSE stream, `_progress_queues`) grow without bound.

**Fix:** set `completed_at` on every terminal transition.

#### 2.7 No `.dockerignore` — secrets and local state are baked into the image
The `Dockerfile` does `COPY . .` and the repository has **no `.dockerignore`**. A `docker build` from a working developer checkout copies `.env` (OpenRouter API keys), `aro_memory.db`, `logs/`, `vector_store/`, and `.git/` into the image. Anyone with access to the image gets the keys. (`.gitignore` does not affect docker build context.)

**Fix:** add a `.dockerignore` covering at least `.env*`, `*.db*`, `logs/`, `vector_store/`, `.git/`, `ui/node_modules/`, `venv/`.

#### 2.8 Log-handler leak duplicates session logs and leaks file descriptors
`SessionLogger._setup_python_logger()` (`runtime/logger.py:135-144`) adds a new `FileHandler` to the shared `"aro"` logger on every construction and never removes it, and forces the logger to `DEBUG`. In the web server, each research session adds another handler, so session N's log lines are appended to the files of **all previous sessions**, log volume grows quadratically, and file descriptors leak until the process dies.

**Fix:** deduplicate/remove handlers (`removeHandler` on close, or one handler per session attached to a session-specific logger name).

### High

#### 2.9 Cross-session memory is write-only — the flagship feature never influences research
Claims and hypotheses are indexed into ChromaDB on write (`memory/memory_service.py:104-113,149-157`), but the read APIs `get_prior_knowledge()` / `get_prior_hypotheses()` (`memory_service.py:271-287`) are **never called by any orchestrator, agent, or endpoint**. The `vector_store.py` docstring says "before each research iteration, the orchestrator queries for relevant prior findings" — that query does not exist. The README's "Cross-session memory — ChromaDB vector store remembers findings across research sessions" is inaccurate: it remembers, but never recalls.

**Fix:** inject `get_prior_knowledge(objective)` results into the planner/research prompts at iteration 1.

#### 2.10 `_generate_conclusion` bypasses the ModelGateway and uses the wrong API key
`agents/orchestrator.py:1046-1065` makes a raw `requests.post` to OpenRouter, violating the project's own rule ("All agents must use this gateway. No direct API calls allowed", `model_gateway.py:13`). Consequences: (a) it always uses `config.openrouter_api_key` even though the model is the synthesis model (GPT-OSS) which may have a dedicated key via `get_api_key_for_model` — with split keys the call 401s and users silently get the fallback conclusion; (b) tokens are not counted in `total_tokens_used`; (c) no retry/backoff. There are also unused imports there (`ReflectionOutput`, `ModelConfig`).

**Fix:** add a `call_text()` (plain-text, non-schema) method to `ModelGateway` and use it.

#### 2.11 The prior-art "guardrail" is a stub — it never scans anything
`tools/prior_art_tool.py:48-83` returns a canned dict with `estimated_prior_art_similarity = 0.5` and an empty `prior_art_references` list. No patent/scholar search happens, despite the repo having 5 working search engines in `tools/web_search.py`. So the guardrail "No innovation without prior-art scan" is nominally satisfied by a no-op, and the `(1 − PriorArtSimilarity)` novelty term is the constant 0.15. Similarly, `tools/search_tool.py` is a placeholder that fabricates `search.example.com` URLs — dangerous if ever wired into an agent, since fake URLs would enter the source registry.

**Fix:** implement `PriorArtTool.scan` on top of `search_semantic_scholar`/`search_openalex` (patent search via free APIs like PatentsView is also an option); delete or clearly quarantine `search_tool.py`.

#### 2.12 Guardrail workarounds fabricate evidence
- `_persist_claims` (`orchestrator.py:601-605`): if the LLM emits an unknown `source_id`, the claim is silently reattributed to the **first** registered source. That misattributes provenance — the exact thing the guardrail exists to prevent.
- `_persist_hypotheses` (`orchestrator.py:703-706`): a hypothesis with no valid supporting claims gets `all_claims[0]` attached as "support". This fabricates evidence and defeats "no hypothesis without supporting claims"; combined with the confidence formula it can yield a confident hypothesis supported by an unrelated claim.

**Fix:** drop the claim/hypothesis (log it) instead of inventing linkage, or route it back to the model as a validation retry.

#### 2.13 Enabling `ARO_API_KEY` breaks the shipped UI
`app.py:52-64` requires `X-API-Key` on all `/api/` routes, but the React app never sends that header for `fetch` calls, and the SSE client uses `EventSource`, which **cannot send custom headers at all**. Setting the documented `ARO_API_KEY` makes the dashboard fully non-functional.

**Fix:** support a token query parameter or cookie for `/api/stream`, add the header to UI fetches, and document it.

#### 2.14 Claim/source bookkeeping distorts the evidence model
- **Sources are never deduplicated**: `_register_sources` (`orchestrator.py:582-593`) inserts a new `src_…` row for every finding every iteration, so the same URL appears many times. This inflates `total_sources_count`, skews `source_credibility_variance` (a risk input), and makes the Skeptic's per-source credibility adjustments hit only one duplicate.
- **Claim merging erases corroboration**: `ClaimStore._merge_claims` (`memory/claim_store.py:55-101`) keeps the original `source_id` and doesn't record the new claim's source, so a claim confirmed by 3 different sources still looks single-source. The single-source confidence cap (`orchestrator.py:800-806`) then wrongly clamps genuinely corroborated hypotheses to ≤ 0.85. Also, the `merged_from` list appends the *incoming* model-supplied ID (usually meaningless) rather than anything traceable.

**Fix:** dedupe sources by normalized URL; track a `source_ids` set (or use `merged_from` to store source IDs) on merge and use it in the single-source check.

#### 2.15 API `mode` is not validated; interactive mode doesn't exist
`app.py:246` passes any string as `mode`. Anything that isn't `"fast"` runs the standard pipeline, where only `"innovation"` and `"interactive"` are special-cased — so `mode: "bananas"` silently behaves like autonomous, and is recorded as such in the DB/report. Meanwhile "interactive" mode — advertised in the README table and CLI — is a no-op: `orchestrator.py:353-359` just logs "override not connected". 

**Fix:** validate mode against the known set (400 otherwise); either implement the interactive pause (the SSE channel + a `/api/sessions/<id>/continue` endpoint would do) or stop advertising it.

### Medium

#### 2.16 ~800 lines of dead or duplicated code that will drift
- `agents/prompt_builder.py` (288 lines), `agents/data_processor.py` (185), `evaluation/metrics_engine.py` (208) are refactored copies of orchestrator internals — **never imported anywhere**. They are already drifting (PromptBuilder has extra instructions the live prompts lack). The orchestrator remains a 1,086-line god class.
- `runtime/event_bus.py` has **zero subscribers** in the codebase; `FastOrchestrator._emit` events go nowhere (fast-mode users get no live progress at all — the UI only receives the terminal `complete` event).
- `ModelGateway.call_async_stream` (`model_gateway.py:250-309`) is never called — the README's "Response streaming — token-by-token streaming via SSE" does not exist in any endpoint.
- `runtime/cache.py`: `llm_response_cache` and `embedding_cache` are never used; `tools/web_search.py:533` `run_web_research_async` (and the five `*_async` engine wrappers it depends on) are never used by the standard pipeline.
- `schemas/search_result.py` `SearchResult` is imported by `fast_orchestrator.py` but never instantiated (searches pass raw dicts around).

**Fix:** either finish the refactor (make the orchestrator use PromptBuilder/DataProcessor/MetricsEngine — recommended, it shrinks the god class) or delete the copies. Wire the EventBus into `app.py` instead of monkey-patching (see 3.1).

#### 2.17 Dependency issues (`requirements.txt`)
- `google-adk==1.25.1` and `sqlalchemy==2.0.46` are **never imported** anywhere — google-adk alone drags in a large dependency tree and inflates the Docker image (the README's "~250MB" is not achievable with it).
- `pytest==7.0` is pinned to a 2022 release — and there are no tests to run (see §5).
- `duckduckgo-search` was renamed upstream to `ddgs`; the code already prefers `from ddgs import DDGS` (`web_search.py:64-67`) but requirements still install the deprecated package.
- No lockfile/hash pinning; single flat file mixes prod and dev deps.

#### 2.18 Deprecated / fragile runtime patterns
- `datetime.utcnow()` used throughout (schemas, memory, logger, gateway) — deprecated since Python 3.12; switch to `datetime.now(timezone.utc)`.
- `asyncio.get_event_loop()` fallback dance (`orchestrator.py:191-196`) — deprecated pattern; the created loop is never closed. Use `asyncio.run()` per parallel section or hold one `asyncio.Runner`.
- The httpx `AsyncClient` is never closed in fast mode (`close_async` has no caller).
- arXiv Atom XML is parsed with regexes (`web_search.py:184-199`) — no HTML-entity unescaping (titles like `A &amp; B` come through encoded) and brittle to feed changes; `xml.etree.ElementTree` is stdlib.
- `TTLCache` is used from multiple threads with no lock (`runtime/cache.py`); the get-then-delete on expiry can race and `KeyError`.
- SSE stream cleanup pops the queue when a client disconnects (`app.py:294-296`); a browser refresh mid-run permanently orphans the still-running session's events, and a late `queue.put` writes into a queue nobody can ever read.

#### 2.19 Data-layer nits
- `ClaimStore.add_claim` loads **all** session claims and does O(n) `SequenceMatcher` comparisons per insert — O(n²) per iteration overall. Fine at ~100 claims, painful at thousands. The vector store could serve as the dedup index instead.
- Fast mode never calls `memory.create_session(...)`, so fast reports reference a `session_id` with no `sessions` row (only the JSON file on disk makes it visible in `/api/sessions`).
- `HypothesisGraph` mixes claim IDs and hypothesis IDs as nodes in one graph; `compute_graph_bridge_score` divides bridge *endpoints* (incl. claims) by total nodes — with the current mostly-tree structure nearly every edge is a bridge, so the score hovers near 1.0 and adds little signal.
- `db.py` migration is solid, but `PRAGMA foreign_keys=OFF`/`ON` inside an open transaction is a no-op in SQLite (FK pragma can't change mid-transaction) — it works today only because `executescript` committed beforehand; worth an explicit `commit()` before the pragma.

#### 2.20 Web-search/SSRF hardening is partial
`_is_safe_url` (`tools/web_search.py:40-56`) blocks literal private IPs and a hostname denylist, but: (a) a hostname that *resolves* to a private IP (DNS rebinding / internal DNS) passes; (b) redirects are followed by trafilatura after validation of only the initial URL; (c) decimal/octal IP encodings (`http://2130706433/`) bypass the string checks. Since fetched URLs come from third-party search results, resolve-then-verify (or a proxy with an egress policy) is the robust fix.

---

## 3. Design Flaws & Architecture Observations

### 3.1 SSE integration via monkey-patching
`app.py:134-153` rebinds `Orchestrator._run_agent_logged` at import time and smuggles a queue in as `orchestrator._sse_queue`. This is fragile (any signature change breaks it silently, and it patches the class globally for all sessions) — and ironic, because the codebase already contains a purpose-built `EventBus` that nothing uses. The orchestrator should accept an optional event callback/bus and emit `agent_start`/`agent_done`/`iteration_complete` itself.

### 3.2 Token accounting is an assertion away from crashing a whole run
`_assert_token_accounting` (`orchestrator.py:883-891`) demands *exact* equality between per-iteration deltas and the gateway total, and raises after the research is complete — destroying the session's results over a bookkeeping discrepancy. Any future code path that calls the gateway outside `_run_agent_logged`'s window (exactly what 2.10 does, saved only by running *after* the assert) will hard-fail runs. Prefer logging a warning with the delta.

### 3.3 Config duplication
`MAX_CONCURRENT_SESSIONS`, iteration ceilings, and host/port are read from env in `app.py` while everything else lives in `AROConfig`. `search_cache_ttl`/`enable_search_cache` exist in config but `runtime/cache.py` hardcodes its own TTLs and ignores both flags. Consolidate.

### 3.4 The Skeptic's credibility challenges mostly miss
`CredibilityChallenge.target_id` is described as "claim or source ID", but `_process_skeptic_output` (`orchestrator.py:634-646`) only ever looks it up as a **source**. The skeptic prompt shows the model claim IDs, not source IDs — so most challenges reference claims and are silently dropped (`get_source` returns None). Either give the skeptic the source map or handle claim IDs by adjusting `credibility_weight`.

### 3.5 Documentation overstates reality
README/docs claims vs. code: cross-session memory (write-only, 2.9), token streaming (unused, 2.16), interactive mode (no-op, 2.15), budget cap (dead, 2.1), "contradictions detected and resolved" (never resolved, 2.5), prior-art scan (stub, 2.11), "~250MB image" (unused heavy deps, 2.17). Bringing docs and code back into agreement — in whichever direction — should be part of any cleanup.

---

## 4. Security Review Summary

Done well: parameterized SQL everywhere + table-name allowlist (`db.py`), session-ID regex + normpath/startswith checks on both report and static routes (`app.py`), `hmac.compare_digest` for API-key comparison, security headers + CSP, concurrency cap, log truncation, sanitized error messages to clients, reasoning-trace hard guards.

Gaps, in priority order:
1. **Secrets in Docker image** — no `.dockerignore` (2.7). Highest practical risk.
2. **Container runs as root** — no `USER` directive in the Dockerfile; add a non-root user.
3. **SSRF partial** (2.20).
4. **Auth is off by default** and turning it on breaks the UI (2.13); `/api/run` consumes paid/rate-limited LLM quota, so unauthenticated deployments on `0.0.0.0` (the docker-compose default via gunicorn bind) are an open relay for someone's OpenRouter quota.
5. **No rate limiting** beyond the 3-session concurrency cap; `/api/sessions` and `/api/report` are unauthenticated-by-default reads of all research history.
6. `web_search` sends queries (which may contain sensitive research objectives) to 5 third-party services — worth a note in SECURITY.md.
7. `SECURITY.md` references `OPENROUTER_MGMT_KEY`, which appears nowhere in the code — stale doc.

---

## 5. Testing — the biggest single gap

There are **zero tests** in the repository (no `tests/` directory; `pytest` is pinned in requirements but has nothing to collect). For a system whose selling point is *deterministic, mathematically-scored orchestration*, the evaluation layer is exactly the kind of pure-function code that is trivial to test — and several of the bugs above (2.1, 2.2, 2.4, 2.5) would have been caught by the first afternoon of test-writing.

Recommended first test targets (highest value, no network needed):
1. `TerminationChecker` — would have caught the missing max-iterations check immediately.
2. `evaluation/confidence.py`, `risk.py`, `novelty.py` — pure functions.
3. `ClaimStore.add_claim` dedup/merge behavior.
4. `MemoryService` guardrails (claim without source, hypothesis without claims).
5. `ModelGateway._parse_and_validate` (fence stripping, retry correction path) with a mocked HTTP layer.
6. `db.py` legacy migration (create legacy schema → migrate → assert integrity).
7. Flask API tests with `app.test_client()` (validation, auth, path traversal).

Add a CI workflow (`ruff` + `pytest`) — the only current workflow is Microsoft Defender DevOps, which lints for security but runs no tests.

---

## 6. Prioritized Roadmap

### P0 — Correctness & safety (do first)
| # | Action | Ref |
|---|--------|-----|
| 1 | Enforce `max_iterations` in `TerminationChecker`; fix or remove the dead budget check | 2.1 |
| 2 | Fix the invalid f-string + duplicate `except` in `_generate_conclusion` | 2.2 |
| 3 | Add `.dockerignore`; add non-root `USER` to Dockerfile | 2.7, §4 |
| 4 | Set `completed_at` on all terminal session states | 2.6 |
| 5 | Fix the log-handler leak in `SessionLogger` | 2.8 |
| 6 | Document/enforce single-worker gunicorn, or move session state to a shared store | 2.3 |

### P1 — Make the scoring system honest
| # | Action | Ref |
|---|--------|-----|
| 7 | Recompute novelty after innovation runs | 2.4 |
| 8 | Wire contradiction resolution and gap resolution end-to-end | 2.5 |
| 9 | Stop fabricating source/claim linkage in `_persist_claims`/`_persist_hypotheses` | 2.12 |
| 10 | Dedupe sources by URL; preserve multi-source evidence through claim merges | 2.14 |
| 11 | Implement a real prior-art scan on top of the existing scholarly search engines | 2.11 |
| 12 | Route `_generate_conclusion` through the gateway (adds correct key routing + token accounting) | 2.10 |

### P2 — Ship the features the README already advertises
| # | Action | Ref |
|---|--------|-----|
| 13 | Read path for cross-session memory: inject prior knowledge into planner/research prompts | 2.9 |
| 14 | Replace app.py monkey-patching with the EventBus; emit fast-mode progress to SSE | 3.1, 2.16 |
| 15 | Either implement interactive mode (pause/continue endpoint) or remove it from docs/CLI | 2.15 |
| 16 | UI support for `ARO_API_KEY` (header on fetch, token param for EventSource) | 2.13 |
| 17 | Validate `mode` in `/api/run` | 2.15 |

### P3 — Health of the codebase
| # | Action | Ref |
|---|--------|-----|
| 18 | Test suite + CI (see §5) | §5 |
| 19 | Adopt-or-delete: PromptBuilder / DataProcessor / MetricsEngine / async search / caches / `search_tool.py` | 2.16 |
| 20 | Drop `google-adk` + `sqlalchemy`, migrate to `ddgs`, refresh `pytest`, split dev deps, add lockfile | 2.17 |
| 21 | `datetime.now(timezone.utc)`; modern asyncio patterns; close async clients | 2.18 |
| 22 | ElementTree for arXiv parsing; thread-safe TTLCache; SSE reconnect support | 2.18 |
| 23 | Resolve-then-verify SSRF protection | 2.20 |
| 24 | Persist SQLite DB on a Docker volume (currently only logs + vector store survive rebuilds) | — |
| 25 | Sync README/SECURITY.md with actual behavior | 3.5, §4 |

### Upgrade ideas (beyond fixes)
- **Structured outputs**: OpenRouter supports `response_format: {type: "json_schema", …}` on many models — stronger than embedding the schema in the prompt, and would cut retry loops.
- **Skeptic feedback into search**: knowledge-gap `suggested_queries` are stored but never fed back into the next iteration's web search — a one-line join with `run_web_research` would close that loop and materially improve iteration quality.
- **Per-hypothesis provenance in the UI**: the data model already links claims → sources; surfacing clickable source URLs per hypothesis would make reports auditable.
- **Cost/latency telemetry**: the gateway already counts tokens; break them down per agent/model in the report and dashboard.
- **Retry with model fallback**: free-tier OpenRouter models rate-limit aggressively; the gateway could fall back to a sibling model on 429 instead of failing the whole iteration.

---

## 7. What's Good (keep it)

- Clean layering: schemas / agents / memory / evaluation / runtime / tools have crisp boundaries; agents are model-agnostic and prompt-only.
- The ModelGateway retry-with-correction loop (feeding the validation error back to the model) is a solid pattern.
- Composite-PK session scoping with a defensive in-place migration and post-migration FK integrity checks (`memory/db.py`) is unusually careful for a project this size.
- Security posture in `app.py` (input validation, path-traversal defenses, headers, digest comparison) is above average.
- Evidence-hierarchy prompting is consistent across research, extraction, skeptic, and synthesis system prompts.
- The parallel Skeptic ‖ Synthesis and Innovation ‖ Reflection structure is a sensible, correctly-snapshotted concurrency win.
