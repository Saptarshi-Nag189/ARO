# CLAUDE.md — ARO (Autonomous Research Operator)

Context for AI-assisted sessions working on this repo. Last updated: July 2026 (post-LangGraph v3 rewrite + post-audit cleanup).

## What this project is

Multi-agent AI research engine, **v3 = LangGraph execution core**. Every run is a checkpointed `StateGraph` execution: Plan → Web Search → Research → Claim Extraction → (Skeptic ‖ Synthesis) → integrate → [Innovation ‖ Reflection] → metrics → deterministic termination check. Seven agents in `agents/` are now pure *specifications* (name + system prompt + Pydantic output schema); execution lives in `graph/`:

- `graph/graph.py` — StateGraph assembly (research + fast graphs); `graph/state.py` — typed checkpointable state with reducers; `graph/nodes.py` — node implementations (single-writer discipline: only fan-in nodes touch the DB); `graph/fast_nodes.py` — single-pass fast mode; `graph/models.py` — model factory (OpenRouter / Bedrock / `ARO_FAKE_MODEL=1` deterministic offline fake); `graph/structured.py` — schema-validated invocation with correction retries; `graph/prompts.py` — all prompts (eval-gated in CI); `graph/checkpoint.py` — SqliteSaver (default `data/aro_checkpoints.db`) / PostgresSaver via `ARO_CHECKPOINT_URI`.
- **Interactive mode is a real LangGraph `interrupt()`** — continue / stop / redirect from the CLI (`main.py: _handle_interrupts`); `--resume --session-id X` resumes any run from its checkpoint.
- **Memory**: SQLite via `memory/memory_service.py` facade (guardrails: no claim without source, no unsupported hypothesis; source dedup by URL; claim merges track `corroborating_source_ids`); default DB `data/aro_memory.db`; ChromaDB vector store for cross-session recall (read path injects prior knowledge into planner/research prompts); composite PKs `(session_id, id)` with in-place migration in `memory/db.py`.
- **Scoring**: `evaluation/` — confidence, risk, novelty + `TerminationChecker` (max-iterations ceiling checked first; LLM reflection is advisory only).
- **Entry points**: `main.py` (CLI), `app.py` (Flask + SSE + React `ui/`), `mcp_server/` (ARO as MCP tools `deep_research`/`fast_research`, stdio + HTTP), `evals/` (LangSmith eval suite, gates CI), `infra/terraform/` (optional AWS stack).
- **Search**: `tools/web_search.py` — 5 free engines, SSRF-guarded (resolve-then-verify); `tools/prior_art_tool.py` — real Semantic Scholar + OpenAlex scan with lexical-overlap similarity.

## History / audit trail

- `docs/project_review.md` — full July 2026 audit of v2 with fix status (all findings closed; some fixes later superseded by the v3 rewrite, which ported the important ones: contradiction dedupe + resolution, novelty recompute, guardrail no-fabrication, source dedup/corroboration).
- `docs/langgraph_migration.md` — the v2 → v3 story.
- Review artifact (phone-friendly): https://claude.ai/code/artifact/9e00955a-e836-479d-b64b-040ca8d2c187

## Post-rewrite cleanup already done (this branch)

- Deleted dead modules: `runtime/event_bus.py`, `evaluation/metrics_engine.py`, `tools/search_tool.py` (placeholder that fabricated example.com URLs), the unused async search wrappers in `web_search.py`, and the unused `embedding_cache`/`llm_response_cache` singletons. `schemas/search_result.py` is ALIVE (registered with the checkpoint serde) — don't delete it.
- Skeptic credibility challenges fixed (old finding 3.4): the skeptic prompt now lists source IDs alongside claim IDs, and `graph/nodes.py: integrate` applies `target_id` to whichever it matches (`MemoryService.update_claim_credibility` added for the claim path).
- `datetime.utcnow()` fully swept to `datetime.now(timezone.utc)` (schemas, memory, logger). New timestamps are timezone-aware ISO strings; old rows may be naive — don't compare parsed datetimes across that boundary without normalizing.
- Both SQLite files live under `data/` (gitignored, volume-mounted as `aro_data` in docker-compose; dirs auto-created).
- `/api/run` has a per-IP sliding-window rate limit (`ARO_RATE_LIMIT_PER_MIN`, default 5/min) on top of the concurrency cap.
- `TTLCache` is thread-safe (lock) — it's shared across search worker threads.
- README has a Privacy section (maintainer's voice, deliberately lighthearted) — keep its tone if editing.

## Gotchas

- `app.py` session progress state (`_progress_queues`, `_session_status`) is **in-process** → gunicorn must stay `-w 1` (Dockerfile is set up that way on purpose).
- `ARO_FAKE_MODEL=1` drives the entire graph offline and deterministically — use it for tests/demos; CI relies on it.
- Web UI auth: `ARO_API_KEY` + `localStorage.setItem('aro_api_key', …)`; SSE uses an `api_key` query param (EventSource can't send headers).
- The eval gate (`evals/`, `eval-gate.yml`) can fail PRs on answer-quality regressions when LangSmith secrets are configured; `deploy.yml` self-skips without AWS secrets.
- Interactive mode via the web API behaves like autonomous (HITL interrupts are CLI-only for now).

## Conventions & verification

- Agents never touch the DB; all mutations go through `MemoryService`, and only single-writer graph nodes call it.
- All model calls go through `graph/models.py` + `graph/structured.py` — never raw HTTP.
- Verify with `ARO_FAKE_MODEL=1 python -m pytest -q` (offline, no keys). The LangGraph stack (`langgraph`, `langchain-core`, `langgraph-checkpoint-sqlite`) must be installed; chromadb optional.
- Development branch: `claude/project-review-docs-pzlbnk`.
