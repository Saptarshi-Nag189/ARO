# CLAUDE.md — ARO (Autonomous Research Operator)

Context for AI-assisted sessions working on this repo. Last updated: July 2026, on branch `claude/project-review-docs-pzlbnk`.

## What this project is

Multi-agent AI research engine. A deterministic **Orchestrator** (`agents/orchestrator.py`, ~1,100 lines — the god class) runs an iterative loop: Plan → Web Search → Research → Claim Extraction → Skeptic ‖ Synthesis → [Innovation] ‖ Reflection → metrics → termination check. Seven LLM agents (subclasses of `agents/base_agent.py`) call OpenRouter free-tier models through `runtime/model_gateway.py` (`ModelGateway`), which enforces Pydantic-schema JSON output with retry-with-correction, per-model API-key routing (`config.py: get_api_key_for_model`), and token accounting.

- **Memory**: SQLite via `memory/memory_service.py` facade (guardrails: no claim without source, no hypothesis without supporting claims); composite PKs `(session_id, id)` with in-place legacy migration in `memory/db.py`; ChromaDB vector store for cross-session memory; TTL caches in `runtime/cache.py`.
- **Scoring**: `evaluation/` — hypothesis confidence, epistemic risk, novelty; `TerminationChecker` decides loop exit deterministically (LLM reflection is advisory only).
- **Entry points**: `main.py` (CLI, click), `app.py` (Flask + SSE + React dashboard in `ui/`, built with Vite/Tailwind), `agents/fast_orchestrator.py` (single-pass "fast mode").
- **Search**: `tools/web_search.py` — 5 free engines (DDG, Semantic Scholar, arXiv, OpenAlex, Wikipedia), no keys needed.

## Key facts / gotchas learned in the July 2026 review

Full audit with file/line references: **`docs/project_review.md`** — read it before making significant changes. Highlights:

- `app.py` monkey-patches `Orchestrator._run_agent_logged` for SSE events; session progress state (`_progress_queues`, `_session_status`) is **in-process**, so gunicorn must stay at `-w 1` (Dockerfile is configured that way deliberately).
- `agents/prompt_builder.py`, `agents/data_processor.py`, `evaluation/metrics_engine.py` are **dead code** — refactored copies of orchestrator internals, never imported, already drifting. Adopt-or-delete. Same for `runtime/event_bus.py` (zero subscribers), `ModelGateway.call_async_stream`, the async search wrappers in `web_search.py`, `llm_response_cache`/`embedding_cache`, and `tools/search_tool.py` (placeholder that fabricates example.com URLs — do not wire into agents).
- Cross-session ChromaDB memory is **write-only**: `MemoryService.get_prior_knowledge()`/`get_prior_hypotheses()` have no callers. The README feature claim is aspirational.
- `tools/prior_art_tool.py` is a **stub** (always returns similarity 0.5, empty references).
- `resolved_contradictions` counter and `resolve_knowledge_gap()` have **no writers/callers** — contradiction/gap resolution never happens, biasing risk up and novelty down (open finding 2.5; fixing it requires agent-contract/schema changes).
- Interactive mode is a no-op (logs "override not connected").
- `requirements.txt` pins `google-adk` and `sqlalchemy` which are **never imported**; `pytest==7.0` with **zero tests in the repo**; GitHub Dependabot reports ~13 vulnerabilities (2 critical) on main.
- Skeptic `CredibilityChallenge.target_id` is only looked up as a *source*, but the skeptic prompt only shows *claim* IDs, so most challenges are silently dropped (finding 3.4).

## Fixes already applied (branch `claude/project-review-docs-pzlbnk`, commits `53d140f` + `b752d97`)

- `max_iterations` enforced as first check in `TerminationChecker.should_terminate()` (loop previously unbounded; budget check is still effectively dead — cost never recorded).
- Fixed `ValueError` f-string crash + duplicate `except` in `Orchestrator._generate_conclusion` fallback.
- Added `ModelGateway.call_text()` (plain-text, key routing, retries, token accounting); conclusion generation now goes through the gateway instead of raw `requests.post` with the default key.
- Novelty recomputed after Innovation runs (`Orchestrator._compute_novelty`); was permanently capped at 0.5.
- Guardrails no longer fabricate evidence: unknown-source claims and unsupported hypotheses are dropped with warnings (previously reattributed to first source / first claim).
- `completed_at` set on successful sessions → `_evict_old_sessions` works; `mode`/`runtime_mode` validated in `POST /api/run`.
- `SessionLogger.close()` added and called from `app.py`/`main.py` (was leaking a FileHandler per session on the shared `"aro"` logger, duplicating logs across session files).
- Added `.dockerignore` (previously `.env`, `*.db`, `logs/`, `.git` were baked into images via `COPY . .`); Dockerfile now runs as non-root user `aro`, gunicorn `-w 1 --threads 16`.

## Top remaining work (prioritized in docs/project_review.md §6)

1. Wire contradiction resolution + knowledge-gap resolution end-to-end (needs `SynthesisOutput`/prompt changes) — finding 2.5.
2. Read path for cross-session memory (inject `get_prior_knowledge(objective)` into planner/research prompts) — 2.9.
3. Real prior-art scan using the existing scholarly search engines — 2.11.
4. Source dedup by URL + preserve multi-source evidence through claim merges (single-source cap currently misfires) — 2.14.
5. UI support for `ARO_API_KEY` (fetch header + token param for EventSource; enabling auth currently breaks the dashboard) — 2.13.
6. Test suite + CI: none exists. Highest-value first targets: `TerminationChecker`, `evaluation/*` pure functions, `ClaimStore` dedup, `MemoryService` guardrails, `ModelGateway._parse_and_validate`, Flask API via `test_client()`.
7. Dependency cleanup: drop `google-adk`/`sqlalchemy`, migrate `duckduckgo-search`→`ddgs`, refresh pins (Dependabot criticals).

## Conventions & verification

- Python 3.10+; no formatter/linter configured; `datetime.utcnow()` still used widely (deprecated — new code should use `datetime.now(timezone.utc)`).
- All LLM calls must go through `ModelGateway` (use `call`, `call_async`, or `call_text`) — never raw HTTP.
- All DB mutations go through `MemoryService` — agents never touch SQLite directly.
- No test suite yet: verify changes with targeted inline scripts (install `pydantic requests networkx python-dotenv click flask flask-cors`; note the container's system `blinker` may need `pip install --ignore-installed blinker`). `python -m py_compile` for syntax.
- Development branch for the review/fix work: `claude/project-review-docs-pzlbnk` (pushed; no PR opened yet — do not create one unless asked).
