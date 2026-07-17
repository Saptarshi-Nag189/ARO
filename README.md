# ARO — Autonomous Research Operator

[![CI](https://github.com/Saptarshi-Nag189/ARO/actions/workflows/ci.yml/badge.svg)](https://github.com/Saptarshi-Nag189/ARO/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/engine-LangGraph-1C3C3C.svg)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/MCP-server-7C3AED.svg)](#-mcp-server--plug-aro-into-claude--cursor)
[![Docker Ready](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

A multi-agent AI research engine that autonomously plans research strategies, searches the web across 5 free engines, extracts verifiable claims, debates contradictions, synthesizes hypotheses, and generates innovation proposals — with mathematical confidence scoring on every iteration.

**v3** rebuilds the execution core on **LangGraph**: every run is a checkpointed, resumable graph execution with real human-in-the-loop interrupts, full **LangSmith** observability, an **eval-gated CI/CD pipeline** that blocks merges when answer quality regresses, an **MCP server** that plugs ARO into Claude or Cursor as a tool, and a pluggable one-command **AWS deployment**.

---

## Table of contents

- [Why ARO is interesting](#why-aro-is-interesting)
- [Quick start](#quick-start)
- [How it works — the research graph](#how-it-works--the-research-graph)
- [Durable execution & human-in-the-loop](#durable-execution--human-in-the-loop)
- [LLMOps: tracing, evals, and the quality gate](#llmops-tracing-evals-and-the-quality-gate)
- [MCP server — plug ARO into Claude / Cursor](#-mcp-server--plug-aro-into-claude--cursor)
- [AWS deployment (pluggable)](#aws-deployment-pluggable)
- [Modes, CLI, configuration](#modes-cli-configuration)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Guardrails](#guardrails)
- [Privacy](#privacy)

---

## Why ARO is interesting

Most "research agent" demos are a prompt in a loop. ARO is an **engineered system** with opinions:

1. **Deterministic control, probabilistic workers.** LLM agents produce claims, critiques, and hypotheses — but loop control, termination, and scoring are *mathematical*, not vibes. Epistemic risk, hypothesis confidence, and novelty are computed each iteration from claim/source statistics (see [`docs/mathematical_models.md`](docs/mathematical_models.md)), and the run stops when the numbers say so: risk convergence, novelty plateau, budget cap, or iteration ceiling.

2. **Adversarial by construction.** A Skeptic agent runs *in parallel* with the Synthesis agent every iteration, hunting contradictions, challenging source credibility, and filing knowledge gaps. Contradictions are mapped into opposing evidence on affected hypotheses — confidence goes *down* when sources disagree.

3. **Every run is durable.** The graph checkpoints its full typed state after every node (SQLite locally, Postgres in production). Kill the process mid-run and resume it from the exact node boundary with `--resume`. Interactive mode is a real `interrupt()` — the graph parks *in the checkpoint store* until a human says continue, stop, or "focus on X instead".

4. **Quality is regression-tested.** Prompts and graph topology are covered by a LangSmith eval suite (LLM-as-judge + programmatic evaluators built from ARO's own epistemic math). A PR that makes answers worse **fails CI** before it can merge.

5. **It's a tool, not just an app.** The MCP server exposes `deep_research` / `fast_research` to any MCP client — your ARO instance becomes a research tool *inside* Claude Desktop, Claude Code, or Cursor.

---

## Quick start

### 1. Clone & install

```bash
git clone https://github.com/Saptarshi-Nag189/ARO.git
cd ARO

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Try it with zero setup (offline demo mode)

No API keys, no network — the deterministic fake model exercises the entire graph:

```bash
ARO_FAKE_MODEL=1 python main.py -o "Anything you like" -m autonomous
```

### 3. Configure real models

```bash
cp .env.example .env
```

Edit `.env` with your [OpenRouter API keys](https://openrouter.ai/keys) — ARO's default agents run on **free** OpenRouter models:

| Variable | Model | Used by |
|---|---|---|
| `OPENROUTER_API_KEY` | Trinity Large Preview | research, innovation |
| `OPENROUTER_API_KEY_STEP` | Step 3.5 Flash | planner, claim extraction |
| `OPENROUTER_API_KEY_GPT_OSS` | GPT-OSS-120B | skeptic, synthesis, reflection |

> One key is enough — the others fall back to `OPENROUTER_API_KEY`. Set `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` too and every agent call, retry, and token count appears in [LangSmith](https://smith.langchain.com) automatically.

### 4. Run

```bash
# Standard research (2–5 min, iterative)
python main.py -o "What are the latest advances in quantum error correction?" -m autonomous

# Fast mode (~30 s, single pass, speculative search)
python main.py -o "Impact of LLMs on software engineering" -m fast

# Innovation mode (prior-art scan + novelty-scored proposals)
python main.py -o "Novel approaches to protein folding prediction" -m innovation -n 5

# Interactive mode (the graph pauses for YOU after each iteration)
python main.py -o "Your question" -m interactive
```

**Web dashboard** (glassmorphism React UI with live agent map):

```bash
cd ui && npm install && npm run build && cd ..
python app.py            # → http://localhost:5000
```

**Docker** (web app + MCP server):

```bash
docker compose up --build
# Web UI → http://localhost:5000   |   MCP → http://localhost:8001/mcp
```

---

## How it works — the research graph

The engine is a compiled **LangGraph `StateGraph`** over a single typed state (`graph/state.py`). Seven specialized agents — each just a system prompt + a strict Pydantic output schema (`agents/`) — run as nodes, with genuine parallel fan-outs where the pipeline allows it:

```mermaid
flowchart TB
    START((START)) --> plan[plan<br/><i>Step 3.5 Flash</i>]
    plan --> web[web_search<br/><i>5 engines, parallel</i>]
    web --> research[research<br/><i>Trinity Large</i>]
    research --> extract[extract_claims<br/><i>Step 3.5 Flash</i>]
    extract --> skeptic[skeptic<br/><i>GPT-OSS-120B</i>]
    extract --> synthesis[synthesis<br/><i>GPT-OSS-120B</i>]
    skeptic --> integrate[integrate<br/><i>single writer</i>]
    synthesis --> integrate
    integrate --> metrics[compute_metrics<br/><i>risk · confidence · novelty</i>]
    metrics -->|innovation mode| innovation[innovation<br/><i>Trinity Large</i>]
    metrics --> reflection[reflection<br/><i>GPT-OSS-120B</i>]
    innovation --> record
    reflection --> record[record<br/><i>log · terminate?</i>]
    record -->|stop| finalize[finalize<br/><i>report + conclusion</i>]
    record -->|interactive| gate{{"human_gate<br/>interrupt()"}}
    record -->|replan| plan
    record -->|next iteration| web
    gate -->|continue / redirect| web
    gate -->|stop| finalize
    finalize --> END((END))
```

Design rules that keep it correct under concurrency:

- **Parallel branches are pure.** `skeptic ‖ synthesis` and `innovation ‖ reflection` operate on snapshots taken by the preceding node — they never touch the database concurrently. All writes happen in single-writer nodes (`extract_claims`, `integrate`, `record`, `finalize`).
- **Termination is a pure function of checkpointed state.** Risk/novelty/claim histories live in the state; the checker replays them, so a resumed run makes the same decision it would have made originally.
- **Token accounting must reconcile exactly.** `finalize` raises if per-iteration token sums drift from the run total — no silent cost leaks.

### Per-agent model routing

Each agent gets the model suited to its job (configured in `config.py`, overridable per-run with `--model`):

| Agent | Role | Default model |
|---|---|---|
| **Planner** | Decomposes the objective into prioritized sub-questions | Step 3.5 Flash |
| **Research** | Grounds findings in real web search results | Trinity Large Preview |
| **Claim Extraction** | Atomic, source-attributed claims | Step 3.5 Flash |
| **Skeptic** | Contradictions, credibility challenges, knowledge gaps | GPT-OSS-120B |
| **Synthesis** | Hypotheses with supporting/opposing claim links | GPT-OSS-120B |
| **Innovation** | Prior-art-scanned, novelty-scored proposals | Trinity Large Preview |
| **Reflection** | Meta-analysis + strategy adjustments (advisory only) | GPT-OSS-120B |

Set `ARO_MODEL_PROVIDER=bedrock` to route every agent through **AWS Bedrock** instead (`pip install langchain-aws`).

### Three-tier memory

| Tier | Store | Contents |
|---|---|---|
| Structured | SQLite (WAL) | sessions, claims, hypotheses, sources, knowledge gaps — guardrail-enforced facade (`memory/`) |
| Semantic | ChromaDB | cross-session claim/hypothesis retrieval |
| Durable execution | SQLite / Postgres | **full graph state after every node** (LangGraph checkpointer) |

---

## Durable execution & human-in-the-loop

Every invocation carries a `thread_id` (the session id). The checkpointer persists the complete typed state at every node boundary, which buys three things:

**1. Crash-safe resume.** Kill the process anywhere — mid-iteration, mid-LLM-call — and continue from the last completed node:

```bash
python main.py -o "same objective" -m autonomous -s session_ab12cd34ef56 --resume
```

**2. Real human-in-the-loop.** Interactive mode parks the graph in an `interrupt()` after each iteration. The CLI shows the iteration's confidence/risk/novelty and asks:

```
Iteration 2 complete.
  Confidence: 0.791 | Risk: 0.168 | Novelty: 0.500
Your call [continue/stop/<redirect note>]:
```

Type `continue`, `stop` (report now), or *anything else* — e.g. `focus on the security implications` — and the graph re-plans around your directive. The pause lives in the checkpoint store, so you can answer tomorrow, or from a different process.

**3. Time-travel debugging.** `graph.get_state_history()` exposes every checkpoint — inspect exactly what the skeptic saw at iteration 3, or fork a run from any point.

Backend selection is one env var:

```bash
# local default: aro_checkpoints.db (SQLite)
ARO_CHECKPOINT_URI=postgresql://user:pass@host:5432/aro   # production (RDS)
```

---

## LLMOps: tracing, evals, and the quality gate

The part that makes this production software rather than a demo:

```mermaid
flowchart LR
    subgraph PR["Every PR"]
        CI["ci.yml<br/>ruff + 41 offline tests<br/>(fake model, no keys)"]
    end
    subgraph Gate["PRs touching graph/ agents/ schemas/ evals/"]
        EG["eval-gate.yml<br/>LangSmith eval suite vs<br/>evals/baseline.json"]
    end
    subgraph Main["Merge to main"]
        CD["deploy.yml<br/>Docker → ECR → ECS roll<br/>(dormant until AWS secrets exist)"]
    end
    CI --> EG -->|"quality holds"| Main
    EG -.->|"score drops > 0.05"| BLOCKED["❌ merge blocked"]
```

- **Tracing:** with `LANGSMITH_TRACING=true`, every node, agent call, structured-output retry, and token count is traced in LangSmith — per-run, per-agent, per-prompt.
- **The eval suite** (`evals/`): a 15-question research dataset with reference key points, scored by
  - *LLM-as-judge evaluators* — `faithfulness` (does the answer contradict the references?) and `coverage` (how many key points does it address?), and
  - *programmatic evaluators* built from ARO's own epistemic math — `risk_calibration`, `confidence_honesty` (high confidence + high risk = miscalibration), `report_completeness`. Zero tokens, zero flakes.
- **The gate:** `python -m evals.run_evals` runs the pipeline over the dataset, aggregates scores, and **exits non-zero if any metric drops more than 0.05 below the committed baseline** (`evals/baseline.json`). In CI this means *a prompt tweak that quietly degrades answer quality cannot merge*. Deliberate improvements re-set the baseline with `--update-baseline`.

```bash
python -m evals.run_evals --limit 5        # smoke run
python -m evals.run_evals                  # full run + regression gate
python -m evals.run_evals --update-baseline
```

---

## 🔌 MCP server — plug ARO into Claude / Cursor

ARO ships an [MCP](https://modelcontextprotocol.io) server (`mcp_server/`), so any MCP client can call the research engine as a tool.

**Local (stdio):**

```bash
claude mcp add aro -- python -m mcp_server.server
```

**Remote (streamable HTTP — via Docker or the AWS stack):**

```bash
claude mcp add --transport http aro http://<host>:8001/mcp
```

Then just ask Claude: *"Use the aro tools to deep-research the state of solid-state batteries."*

| Tool | What it does |
|---|---|
| `fast_research(question)` | ~30 s single-pass, web-grounded answer |
| `deep_research(question, mode, max_iterations)` | full iterative pipeline with confidence/risk scores; `mode="innovation"` adds proposals |
| `list_research_sessions()` | past sessions + final scores |
| `get_research_report(session_id)` | full structured report (hypotheses, claims, gaps, metrics) |

Past reports are also exposed as MCP **resources** at `aro://reports/{session_id}`.

---

## AWS deployment (pluggable)

The cloud layer is **opt-in** — nothing in the local workflow depends on it. When you want a public URL:

```bash
cd infra/terraform && terraform apply     # VPC, ALB, 2× Fargate services,
                                          # RDS Postgres (checkpoints), S3,
                                          # ECR, Secrets Manager, CloudWatch
```

- ~**$25–40/month** while up (cost-trimmed: no NAT gateway, free-tier RDS), and `terraform destroy` returns to $0.
- `deploy.yml` turns into a full CD pipeline the moment `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets are added to the repo — until then it self-skips.
- Durable checkpoints move to RDS via one secret (`ARO_CHECKPOINT_URI`), so production runs survive deploys and crashes.

Full walkthrough, cost table, and teardown: [`docs/deployment_aws.md`](docs/deployment_aws.md).

---

## Modes, CLI, configuration

| Mode | Description | Speed |
|---|---|---|
| `autonomous` | Fully self-directed iterative research loop | 2–5 min |
| `fast` | Single-pass speculative research (seed search ‖ planning) | 15–30 s |
| `interactive` | Real `interrupt()` after each iteration — continue / stop / redirect | as fast as you type |
| `innovation` | Prior-art scan, novelty scoring, patent-grade proposals | 3–7 min |

```
--objective, -o    Research question (required)
--mode, -m         autonomous / interactive / innovation / fast
--max-iterations   Max research iterations (default: 10)
--session-id, -s   Session ID (doubles as the checkpoint thread id)
--resume           Resume an interrupted run from its checkpoint
--model, -M        Override every agent's model
--budget, -b       Budget cap in USD
--verbose, -v      Debug logging
```

| Env var | Purpose |
|---|---|
| `OPENROUTER_API_KEY` (+`_STEP`, `_GPT_OSS`) | model access (free models) |
| `ARO_FAKE_MODEL=1` | offline deterministic mode (demos, CI) |
| `ARO_MODEL_PROVIDER=bedrock` | route agents through AWS Bedrock |
| `ARO_CHECKPOINT_URI` | Postgres checkpointer (default: SQLite) |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | full observability |
| `ARO_API_KEY` | protect the web API (dashboard: `localStorage.setItem('aro_api_key', '<key>')`; SSE passes it as an `api_key` query param) |
| `ARO_CHECKPOINT_SQLITE` | checkpoint DB path (default `data/aro_checkpoints.db` — volume-mounted in Docker, next to `data/aro_memory.db`) |
| `ARO_RATE_LIMIT_PER_MIN` | max research launches per IP per minute on `/api/run` (default 5) |
| `ARO_HOST` / `ARO_PORT` / `ARO_MAX_CONCURRENT` | server tuning |

---

## Testing

```bash
ARO_FAKE_MODEL=1 pytest tests/ -v
```

**41 tests, fully offline** — the deterministic fake model drives the *entire* graph, so CI needs no keys and never flakes:

- end-to-end autonomous + innovation runs, report integrity
- parallel fan-out coverage (skeptic ‖ synthesis, innovation ‖ reflection)
- exact token-accounting reconciliation
- interrupt → continue / stop / redirect flows; crash-resume with a fresh graph instance; checkpoint state history
- structured-output correction retries; evaluation math; MCP tools via an in-process client

---

## Project structure

```
aro/
├── graph/                     # ★ LangGraph execution core (v3)
│   ├── graph.py                  # StateGraph assembly (research + fast)
│   ├── state.py                  # typed, checkpointable state + reducers
│   ├── nodes.py                  # node implementations (single-writer discipline)
│   ├── fast_nodes.py             # speculative single-pass pipeline
│   ├── models.py                 # model factory: OpenRouter / Bedrock / offline fake
│   ├── structured.py             # schema-validated invocation w/ correction retries
│   ├── checkpoint.py             # SqliteSaver / PostgresSaver factory
│   ├── prompts.py                # all agent prompts (eval-gated in CI)
│   └── services.py               # non-serializable deps (memory, logger, emitter)
├── agents/                    # Agent specs: system prompt + Pydantic schema
├── evals/                     # ★ LangSmith dataset, evaluators, regression gate
├── mcp_server/                # ★ MCP server (stdio + streamable HTTP)
├── infra/terraform/           # ★ pluggable AWS stack (ALB, Fargate, RDS, S3, ECR)
├── memory/                    # SQLite facade + ChromaDB cross-session memory
├── evaluation/                # confidence / risk / novelty math, termination
├── tools/                     # 5-engine web search, prior-art scan
├── schemas/                   # strict Pydantic contracts for everything
├── runtime/                   # TTL cache, structured session logs
├── tests/                     # 41 offline tests (fake model)
├── ui/                        # React + Vite dashboard (live agent map)
├── .github/workflows/         # ci.yml · eval-gate.yml · deploy.yml
├── app.py                     # Flask web server (SSE streaming)
├── main.py                    # CLI (incl. --resume, interactive HITL)
└── docs/                      # architecture, math, migration story, AWS runbook
```

---

## Guardrails

- ❌ No claim insertion without source attribution
- ❌ No hypothesis without supporting claims
- ❌ No innovation without a prior-art scan
- ❌ No reasoning traces in structured memory or reports (hard guard, run-aborting)
- ❌ No token-accounting drift (finalize reconciles or raises)
- ✅ Source provenance tracked (web-sourced vs training-knowledge)
- ✅ Cross-source contradictions become opposing evidence on hypotheses
- ✅ Single-source hypotheses capped at 0.85 confidence
- ✅ Termination is deterministic — agents only ever *advise* stopping
- ✅ A Skeptic agent is employed full-time to disagree with everyone (it is very good at its job)

---

## Privacy

Short version: **I am not interested in you or your data. You can keep it with yourself. And I can't host a server.**

Slightly longer version:

- Everything runs on your machine. Sessions, claims, hypotheses, checkpoints — all of it lives in local SQLite files (`data/`), a local ChromaDB folder (`vector_store/`), and `logs/`. Delete those and ARO forgets you ever met.
- No telemetry, no accounts, no analytics, no phoning home. There is no home to phone (see: "I can't host a server").
- The only things that leave your machine are the model calls to OpenRouter (or Bedrock, if you wired that up yourself) and web-search queries to the five public engines in `tools/web_search.py`. If your research objective is confidential, remember you are literally asking the internet about it.
- Default models are OpenRouter's free tier — so even your billing data stays boring.

---

## Documentation

- [LangGraph Migration — the v2 → v3 story](docs/langgraph_migration.md)
- [AWS Deployment Runbook](docs/deployment_aws.md)
- [System Architecture](docs/system_architecture.md)
- [Mathematical Models](docs/mathematical_models.md)
- [Agent Contracts](docs/agent_contracts.md)
- [Reasoning Mode](docs/reasoning_mode.md)
- [Project Review & Improvement Plan](docs/project_review.md)
- [Security Policy](SECURITY.md)

## License

MIT License — see [LICENSE](LICENSE) for details.
