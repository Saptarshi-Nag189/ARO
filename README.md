# ARO — Autonomous Research Operator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade, multi-agent research engine built with Google ADK and OpenRouter. ARO autonomously plans research strategies, performs **real web searches** across 5 free engines, extracts verifiable claims, debates contradictions, synthesizes hypotheses, and generates innovation proposals — all with mathematical confidence scoring.

## How It Works

ARO runs an iterative research loop where 7 specialized AI agents collaborate:

1. **Planner Agent** breaks down your research question into sub-questions with search strategies
2. **Web Search Engine** queries DuckDuckGo, Semantic Scholar, arXiv, OpenAlex & Wikipedia in parallel
3. **Research Agent** analyzes the real search results and structures findings with source metadata
4. **Claim Extraction Agent** extracts atomic, verifiable claims — each tagged with source provenance (web-sourced vs training-knowledge)
5. **Skeptic Agent** identifies contradictions between sources, challenges credibility, and flags knowledge gaps
6. **Synthesis Agent** forms hypotheses from validated claims, resolving cross-source conflicts
7. **Reflection Agent** evaluates progress and adjusts strategy for the next iteration

Each iteration refines the knowledge base until termination conditions are met (convergence, max iterations, or budget).

## Architecture

```text
┌──────────────────────── Root Orchestrator (ADK) ────────────────────────┐
│                                                                         │
│   Plan → Web Search → Research → Extract → Skeptic → Synthesize →      │
│          [Innovate] → Reflect                                           │
│                                                                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│   │ Planner  │  │ Research │  │  Claim   │  │ Skeptic  │              │
│   │  Agent   │  │  Agent   │  │ Extract  │  │  Agent   │              │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                            │
│   │Synthesis │  │Innovation│  │Reflection│                            │
│   │  Agent   │  │  Agent   │  │  Agent   │                            │
│   └──────────┘  └──────────┘  └──────────┘                            │
│                                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│   │Model Gateway │  │Memory Service│  │ Eval Engine  │                │
│   │ (OpenRouter) │  │(SQLite+Graph)│  │(Conf/Risk/   │                │
│   │              │  │              │  │ Novelty)     │                │
│   └──────────────┘  └──────────────┘  └──────────────┘                │
│                                                                         │
│   ┌──────────────────────────────────────────────────┐                │
│   │           Web Search Engine (5 sources)           │                │
│   │  DuckDuckGo · Semantic Scholar · arXiv ·          │                │
│   │  OpenAlex · Wikipedia · trafilatura               │                │
│   └──────────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
```

## ✨ Key Features

- **7 specialized AI agents** working in a structured, iterative pipeline
- **Real web search** — no hallucinated sources; every finding comes from actual web results
- **5 free search engines** (DuckDuckGo, Semantic Scholar, arXiv, OpenAlex, Wikipedia) — no API keys needed
- **Source provenance tracking** — every claim tagged as `web-sourced` or `training-knowledge`
- **Cross-source conflict resolution** — the Skeptic agent detects and resolves contradictions across sources
- **Evidence hierarchy** — peer-reviewed papers > preprints > Wikipedia > web articles > training knowledge
- **Mathematical scoring** — confidence, epistemic risk, and novelty computed per iteration
- **Modern React dashboard** — glassmorphism UI with live research feed, hypothesis deep-dive, agent network map, and report export
- **CLI + Web UI** — run from terminal or browser
- **Innovation mode** — prior-art scanning, novelty scoring, and patent-grade differentiation proposals

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for the dashboard UI)
- An [OpenRouter API key](https://openrouter.ai/keys) (provides access to 100+ LLMs)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Saptarshi-Nag189/ARO.git
cd ARO

# 2. Set up Python environment
python -m venv venv
source venv/bin/activate    # On Windows: venv\\Scripts\\activate
pip install -r requirements.txt

# 3. Configure your API key and Security Settings
cp .env.example .env
# Edit .env and add:
# - OPENROUTER_API_KEY: Your OpenRouter API key
# - ARO_API_KEY: A secure random string for authenticating API requests
# - ARO_HOST, ARO_PORT, ARO_MAX_CONCURRENT (optional overrides)

# 4. Build the dashboard UI
cd ui && npm install && npm run build && cd ..
```

### Running via CLI

```bash
# Autonomous research (default)
python main.py --objective "What are the latest advances in quantum error correction?" --mode autonomous

# Innovation mode (with prior-art scan and novelty scoring)
python main.py --objective "Novel approaches to protein folding prediction" --mode innovation --max-iterations 5

# Verbose logging
python main.py -o "Impact of LLMs on software engineering" -m autonomous -v
```

### Running via Web UI

```bash
python app.py
# Open http://localhost:5000
```

The dashboard provides:

- **Score cards** with confidence, risk, and novelty gauges
- **Hypothesis cards** with supporting/opposing evidence counts
- **Claims table** with source attribution and credibility scores
- **Knowledge gaps** with severity indicators
- **Live research feed** for monitoring active research sessions
- **Report export** in JSON, Markdown, and HTML formats

## Modes

| Mode          | Description                                                         |
| ------------- | ------------------------------------------------------------------- |
| `autonomous`  | Fully self-directed research loop                                   |
| `interactive` | Human override allowed (manual claim validation at each iteration)  |
| `innovation`  | Requires prior-art scan, computes NoveltyScore, outputs proposals   |

## CLI Options

```text
--objective, -o    Research question (required)
--mode, -m         autonomous / interactive / innovation (default: autonomous)
--max-iterations   Max iterations (default: 10)
--session-id       Custom session ID
--model, -M        Override model (e.g. 'anthropic/claude-3.5-sonnet')
--budget, -b       Budget cap in USD
--verbose, -v      Debug logging
```

## Web Search Sources

All free, no API keys required. Searches run in parallel for maximum speed.

| Source           | Type          | What it finds                                  |
| ---------------- | ------------- | ---------------------------------------------- |
| DuckDuckGo       | General web   | Articles, documentation, blog posts            |
| Semantic Scholar | Academic      | Peer-reviewed papers with citation counts      |
| arXiv            | Preprints     | Latest research papers with full abstracts     |
| OpenAlex         | Scholarly     | 250M+ works with abstracts and DOIs            |
| Wikipedia        | Encyclopedia  | Factual summaries with source links            |

Content extraction is handled by **trafilatura**, which cleanly extracts article text from fetched web pages (no raw HTML sent to the LLM).

## Agent Details

### Planner Agent

Breaks the research objective into prioritized sub-questions, each with a recommended search strategy. Re-plans after each iteration based on the Reflection Agent's strategy adjustments.

### Research Agent

Receives real web search results injected into its prompt. Analyzes and structures findings with exact source titles and URLs. Rates credibility based on source type (peer-reviewed: 0.85–0.95, arXiv: 0.7–0.85, Wikipedia: 0.6–0.75, web: 0.5–0.7, training knowledge: 0.3–0.5).

### Claim Extraction Agent

Parses research findings into atomic, verifiable claims (subject → relation → object). Tags each claim with source provenance (`web-sourced` or `training-knowledge`). Extracts both sides when sources conflict — never merges contradictory information.

### Skeptic Agent

Critically evaluates all claims and hypotheses. Identifies cross-source contradictions (e.g., a web article says X but an academic paper says Y). Applies an evidence hierarchy: peer-reviewed > preprints > Wikipedia > web > training knowledge. Suggests specific search queries to resolve knowledge gaps.

### Synthesis Agent

Forms hypotheses backed by multiple claims. Weighs web-sourced evidence higher. When sources conflict, creates hypotheses for both positions and notes the disagreement. Merges near-duplicate claims, preferring the version from the most credible source.

### Innovation Agent

(Innovation mode only) Generates patent-grade differentiation proposals by analyzing findings against prior art. Computes novelty scores and identifies unique angles.

### Reflection Agent

Meta-analyzes iteration progress. Advises whether to continue or stop. Suggests strategy adjustments (e.g., "focus on gap X" or "search for contradictory evidence on hypothesis Y").

## Project Structure

```text
aro/
├── agents/                    # AI Agent implementations
│   ├── base_agent.py             # Abstract base class (schema-validated, JSON-only)
│   ├── orchestrator.py           # Root orchestrator (pipeline controller)
│   ├── planner_agent.py          # Research planning with sub-questions
│   ├── research_agent.py         # Analyzes real web search results
│   ├── claim_extraction_agent.py # Extracts atomic claims with provenance
│   ├── skeptic_agent.py          # Cross-source conflict resolution
│   ├── synthesis_agent.py        # Hypothesis formation with evidence weighting
│   ├── innovation_agent.py       # Patent-grade proposals
│   └── reflection_agent.py       # Meta-analysis and strategy adjustment
├── tools/                     # External tool integrations
│   ├── web_search.py             # DuckDuckGo, Semantic Scholar, arXiv, OpenAlex, Wikipedia
│   ├── prior_art_tool.py         # Prior art scanning
│   └── search_tool.py            # Search abstraction layer
├── memory/                    # Persistent memory (SQLite + NetworkX)
│   ├── db.py                     # Schema & connection
│   ├── claim_store.py            # Claims CRUD + deduplication
│   ├── hypothesis_graph.py       # Hypothesis graph
│   ├── source_registry.py        # Source management
│   └── memory_service.py         # Unified facade
├── runtime/                   # Runtime services
│   ├── model_gateway.py          # OpenRouter API wrapper
│   └── logger.py                 # Structured JSON logging
├── evaluation/                # Mathematical scoring
│   ├── confidence.py             # HypothesisConfidence
│   ├── risk.py                   # EpistemicRisk
│   ├── novelty.py                # NoveltyScore
│   └── termination.py            # Termination conditions
├── schemas/                   # Pydantic models
│   ├── agent_io.py               # Agent input/output schemas
│   ├── claims.py                 # Claim data model
│   ├── hypotheses.py             # Hypothesis data model
│   ├── sources.py                # Source data model
│   ├── knowledge_gaps.py         # Knowledge gap data model
│   └── reports.py                # Final report structure
├── ui/                        # React + Vite + Tailwind CSS dashboard
│   └── src/
│       ├── App.jsx               # Main dashboard with sidebar navigation
│       ├── AgentNetworkMap.jsx    # Agent network visualization
│       ├── HypothesisDeepDive.jsx # Hypothesis detail view
│       ├── KnowledgeBase.jsx      # Cross-session search
│       ├── InteractiveCenter.jsx  # Live research terminal
│       └── ReportExport.jsx       # Export to JSON/Markdown/HTML
├── docs/                      # Documentation
│   ├── system_architecture.md
│   ├── mathematical_models.md
│   ├── agent_contracts.md
│   └── reasoning_mode.md
├── scripts/                   # CI/CD scripts
│   └── ci_self_audit_gate.py     # Self-audit gate for CI
├── app.py                     # Flask web server (UI + API)
├── main.py                    # CLI entry point
├── config.py                  # Configuration
├── requirements.txt           # Python dependencies
├── .env.example               # API key template
└── LICENSE                    # MIT License
```

## Guardrails

- ❌ No claim insertion without source attribution
- ❌ No hypothesis without supporting claims
- ❌ No innovation without prior-art scan
- ✅ Source provenance tracked (web-sourced vs training-knowledge)
- ✅ Cross-source contradictions detected and resolved
- ✅ Evidence hierarchy enforced across all agents
- ✅ MaxDocsPerIteration configurable
- ✅ MaxIterations configurable
- ✅ MaxTokensPerCall configurable
- ✅ Budget cap in USD

## Mathematical Models

ARO uses three core metrics computed at each iteration:

- **Hypothesis Confidence** — weighted average of supporting vs opposing evidence, factoring in source credibility
- **Epistemic Risk** — measures remaining uncertainty based on knowledge gaps and claim variance
- **Novelty Score** — how novel the findings are relative to prior art (innovation mode)

See [docs/mathematical_models.md](docs/mathematical_models.md) for the full formulas and derivations.

## Documentation

- [System Architecture](docs/system_architecture.md)
- [Mathematical Models](docs/mathematical_models.md)
- [Agent Contracts](docs/agent_contracts.md)
- [Reasoning Mode](docs/reasoning_mode.md)

## License

MIT License — see [LICENSE](LICENSE) for details.
