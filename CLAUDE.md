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

## Fixes already applied (branch `claude/project-review-docs-pzlbnk`)

Commits `53d140f` + `b752d97` (P0 + safe P1):

- `max_iterations` enforced as first check in `TerminationChecker.should_terminate()` (loop previously unbounded; budget check is still effectively dead — cost never recorded).
- Fixed `ValueError` f-string crash + duplicate `except` in `Orchestrator._generate_conclusion` fallback.
- Added `ModelGateway.call_text()` (plain-text, key routing, retries, token accounting); conclusion generation now goes through the gateway instead of raw `requests.post` with the default key.
- Novelty recomputed after Innovation runs (`Orchestrator._compute_novelty`); was permanently capped at 0.5.
- Guardrails no longer fabricate evidence: unknown-source claims and unsupported hypotheses are dropped with warnings (previously reattributed to first source / first claim).
- `completed_at` set on successful sessions → `_evict_old_sessions` works; `mode`/`runtime_mode` validated in `POST /api/run`.
- `SessionLogger.close()` added and called from `app.py`/`main.py` (was leaking a FileHandler per session on the shared `"aro"` logger, duplicating logs across session files).
- Added `.dockerignore` (previously `.env`, `*.db`, `logs/`, `.git` were baked into images via `COPY . .`); Dockerfile now runs as non-root user `aro`, gunicorn `-w 1 --threads 16`.

Later commits (rest of P1 + P2/P3 highlights):

- **Contradiction/gap resolution wired end-to-end (2.5)**: `SynthesisOutput.resolved_contradictions` + `resolved_gap_ids`; orchestrator tracks `seen_contradiction_pairs`/`open_contradiction_pairs` (frozensets — dedupes skeptic re-reports), only accepts resolutions for pairs/IDs it actually showed the model; synthesis prompt lists open contradictions + unresolved gaps.
- **Cross-session memory read path (2.9)**: `Orchestrator._build_prior_knowledge_block()` injects vector-store matches into the planner context and iteration-1 research prompt.
- **Real prior-art scan (2.11)**: `PriorArtTool.scan` queries Semantic Scholar + OpenAlex, scores lexical overlap (top-3 mean, clamped to [0.15, 0.90]); falls back to neutral 0.5 offline.
- **Source dedup + corroboration (2.14)**: `SourceRegistry.add_source` dedupes by URL (title for URL-less); claims gained `corroborating_source_ids` (additive `_ensure_column` migration in `db.py`); merges record cross-source corroboration; single-source confidence cap counts corroborating sources.
- **UI auth (2.13)**: `ui/src/api.js` (`apiFetch`/`streamUrl`); key stored via `localStorage.setItem('aro_api_key', …)`; server accepts `api_key` query param (EventSource can't send headers).
- **Tests + CI**: `tests/` (65 tests, no network/chromadb needed) + `.github/workflows/ci.yml`. Run with `python -m pytest -q`.
- **Deps**: dropped `google-adk`/`sqlalchemy` (never imported), `duckduckgo-search`→`ddgs`, `pytest>=8`.
- **SSRF (2.20)**: `_is_safe_url` now resolves hostnames and requires every address to be public.

## Top remaining work (see docs/project_review.md fix-status note)

1. Interactive mode: implement pause/continue or remove from docs/CLI (currently a no-op).
2. Adopt-or-delete dead modules: `agents/prompt_builder.py`, `agents/data_processor.py`, `evaluation/metrics_engine.py`, `runtime/event_bus.py` (replace app.py monkey-patching), `ModelGateway.call_async_stream`, async search wrappers, unused caches, `tools/search_tool.py`.
3. Skeptic credibility challenges: `target_id` only looked up as a source but prompt shows claim IDs — most challenges silently dropped (finding 3.4).
4. `datetime.utcnow()` sweep (mind naive-vs-aware mixing with stored ISO strings), SQLite on a Docker volume, rate limiting, refresh remaining Dependabot pins.

## Conventions & verification

- Python 3.10+; no formatter/linter configured.
- All LLM calls must go through `ModelGateway` (use `call`, `call_async`, or `call_text`) — never raw HTTP.
- All DB mutations go through `MemoryService` — agents never touch SQLite directly.
- Verify with `python -m pytest -q` (works with just `pydantic requests networkx python-dotenv click flask flask-cors pytest`; chromadb optional — the container's system `blinker` may need `pip install --ignore-installed blinker`).
- Development branch: `claude/project-review-docs-pzlbnk`. Review artifact (phone-friendly): https://claude.ai/code/artifact/9e00955a-e836-479d-b64b-040ca8d2c187
