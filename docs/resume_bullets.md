# Resume bullets this project supports

Metric-anchored bullets, each backed by verifiable code in this repo.
(Numbers marked ✎ should be re-measured after your first real runs.)

## For the "LangChain / LangGraph" line

- Architected a 7-agent research engine on **LangGraph**: a 13-node
  `StateGraph` with parallel skeptic/synthesis fan-out, conditional
  innovation branching, and deterministic termination — migrated from a
  1,086-line hand-rolled orchestrator with zero prompt/schema changes.
- Implemented **durable execution**: full typed-state checkpointing
  (SQLite → RDS Postgres) after every node; crashed research runs
  resume from the exact node boundary (`--resume`).
- Built real **human-in-the-loop** research: `interrupt()`-based
  iteration gates where a reviewer can continue, stop, or redirect the
  investigation mid-run — the pause persists in the checkpoint store
  across processes.

## For the "MLOps / LLMOps" line

- Built an **eval-gated CI/CD pipeline**: a LangSmith eval suite
  (LLM-as-judge faithfulness/coverage + programmatic calibration
  evaluators derived from the system's epistemic-risk math) runs on
  every PR touching prompts or graph topology and **blocks merge when
  any quality metric regresses >0.05** against the committed baseline.
- Instrumented full **LLM observability** with LangSmith tracing —
  per-node, per-retry, per-token — plus a 41-test offline suite driven
  by a deterministic fake model (CI needs no API keys and never flakes).
- Enforced hard cost/quality invariants in production code: exact
  token-accounting reconciliation (run aborts on drift) and
  reasoning-trace leak guards.

## For the "Cloud / AWS" line

- Provisioned the full stack with **Terraform on AWS**: ALB fronting
  two ECS Fargate services (web + remote MCP), RDS Postgres for
  durable graph checkpoints, S3, ECR with lifecycle policies, Secrets
  Manager, CloudWatch dashboards/alarms — cost-engineered to
  ~$25–40/month (no NAT gateway, free-tier RDS) with one-command
  teardown.
- Wired **GitHub Actions CD**: Docker build → ECR push → ECS rolling
  deploy on merge, dormant-until-secrets so the pipeline is safe in a
  public repo.
- Pluggable **AWS Bedrock** model provider (env-switchable) alongside
  OpenRouter.

## For the "MCP" line

- Shipped a production **MCP server** (stdio + streamable HTTP) exposing
  the research engine as tools (`deep_research`, `fast_research`) and
  resources to Claude Desktop / Claude Code / Cursor; deployed remotely
  behind an ALB.

## Interview talking points

- Why parallel branches are pure functions over snapshots (SQLite
  thread-safety + write-ordering) — `docs/langgraph_migration.md`.
- The three real bugs the migration surfaced (max_iterations never
  enforced; model-echoed objectives; thread-bound DB connection).
- Why termination stayed mathematical instead of agent-decided.
- Why structured output uses prompt-contract + correction retries
  instead of tool calling (free-model reality vs. fashion).
