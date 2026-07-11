"""
Eval Runner + Regression Gate
=============================
Runs the ARO pipeline against the LangSmith dataset, scores every run
with the evaluator suite, and compares aggregate scores against the
committed baseline. Exits non-zero on regression — this is what makes
a prompt edit unable to silently degrade answer quality in CI.

Usage:
    python -m evals.run_evals                 # run + gate against baseline
    python -m evals.run_evals --update-baseline
    python -m evals.run_evals --mode fast     # (default) single-pass target
    python -m evals.run_evals --limit 5       # smoke subset

Requires: LANGSMITH_API_KEY, OPENROUTER_API_KEY.
"""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from pathlib import Path

BASELINE_PATH = Path(__file__).parent / "baseline.json"
DEFAULT_TOLERANCE = 0.05


def _make_target(mode: str):
    """Build a LangSmith target: question in -> answer + full report out."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import AROConfig
    from graph import GraphServices, build_fast_graph, build_research_graph
    from memory.memory_service import MemoryService

    def target(inputs: dict) -> dict:
        objective = inputs["question"]
        workdir = tempfile.mkdtemp(prefix="aro-eval-")
        config = AROConfig()
        config.max_iterations = 3
        memory = MemoryService(
            db_path=os.path.join(workdir, "memory.db"),
            session_id=f"session_{uuid.uuid4().hex[:12]}",
            enable_cross_session_memory=False,
        )
        services = GraphServices(config=config, memory=memory)
        try:
            if mode == "fast":
                graph = build_fast_graph(services)
                result = graph.invoke(
                    {"objective": objective, "tokens_used": 0, "started_at": time.time()},
                )
            else:
                memory.create_session(objective, "autonomous")
                graph = build_research_graph(services)
                result = graph.invoke(
                    {
                        "objective": objective, "mode": "autonomous",
                        "hitl": False, "iteration": 1,
                        "tokens_used": 0, "last_token_snapshot": 0,
                    },
                    {"recursion_limit": 600},
                )
            report = result["final_report"]
            return {
                "answer": report.conclusion or report.executive_summary,
                "report": report.model_dump(mode="json"),
            }
        finally:
            memory.close()

    return target


def _aggregate(results) -> dict:
    """Mean score per evaluator key across the experiment."""
    scores = defaultdict(list)
    for row in results:
        for eval_result in row["evaluation_results"]["results"]:
            if eval_result.score is not None:
                scores[eval_result.key].append(float(eval_result.score))
    return {key: round(sum(vals) / len(vals), 4) for key, vals in scores.items() if vals}


def main() -> int:
    parser = argparse.ArgumentParser(description="ARO eval runner + regression gate")
    parser.add_argument("--mode", choices=["fast", "standard"], default="fast")
    parser.add_argument("--limit", type=int, default=None,
                        help="Evaluate only the first N examples (smoke run)")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help="Allowed drop per metric before the gate fails")
    args = parser.parse_args()

    for var in ("LANGSMITH_API_KEY", "OPENROUTER_API_KEY"):
        if not os.getenv(var):
            print(f"ERROR: {var} is required to run evals.", file=sys.stderr)
            return 2

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "aro-evals")

    from langsmith import Client, evaluate

    from evals.dataset import DATASET_NAME, sync_to_langsmith
    from evals.evaluators import ALL_EVALUATORS

    sync_to_langsmith()

    client = Client()
    data = DATASET_NAME
    if args.limit:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        examples = list(client.list_examples(dataset_id=dataset.id))[: args.limit]
        data = examples

    print(f"Running {args.mode}-mode evals against '{DATASET_NAME}'...")
    results = evaluate(
        _make_target(args.mode),
        data=data,
        evaluators=ALL_EVALUATORS,
        experiment_prefix=f"aro-{args.mode}",
        max_concurrency=2,
        metadata={"engine": "langgraph-v3", "mode": args.mode},
    )

    aggregate = _aggregate(results)
    print("\n=== Aggregate scores ===")
    for key, val in sorted(aggregate.items()):
        print(f"  {key:22s} {val:.4f}")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(aggregate, indent=2) + "\n")
        print(f"\nBaseline updated: {BASELINE_PATH}")
        return 0

    if not BASELINE_PATH.exists():
        print("\nNo baseline committed yet — run with --update-baseline to create one.")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text())
    print("\n=== Regression gate ===")
    failures = []
    for key, base_val in baseline.items():
        current = aggregate.get(key)
        if current is None:
            failures.append(f"{key}: metric missing from this run (baseline {base_val})")
            continue
        delta = current - base_val
        status = "OK " if delta >= -args.tolerance else "FAIL"
        print(f"  [{status}] {key:22s} baseline={base_val:.4f} "
              f"current={current:.4f} delta={delta:+.4f}")
        if delta < -args.tolerance:
            failures.append(f"{key}: {base_val:.4f} -> {current:.4f} ({delta:+.4f})")

    if failures:
        print("\nQUALITY GATE FAILED — regressions detected:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
