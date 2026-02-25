#!/usr/bin/env python3
"""Strict CI gate for post-hardening self-audit repeatability."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_TRUE_KEYS = [
    "reflection_authority_fixed",
    "minimum_iterations_enforced",
    "gap_persistence_safe",
    "confidence_damping_active",
    "novelty_gating_active",
    "token_accounting_corrected",
    "skeptic_integration_effective",
    "reasoning_isolation_active",
    "production_mode_clean",
    "audit_mode_reasoning_logged",
]


def _extract_last_json_object(text: str) -> Dict[str, Any]:
    decoder = json.JSONDecoder()
    last_obj: Optional[Dict[str, Any]] = None
    idx = 0
    while idx < len(text):
        if text[idx] != "{":
            idx += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            last_obj = obj
        idx = end

    if last_obj is None:
        raise ValueError("No JSON object found in stdout.")
    return last_obj


def _validate_report(report: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    for key in REQUIRED_TRUE_KEYS:
        if report.get(key) is not True:
            errors.append(f"{key} is not true")

    critical_findings = report.get("critical_findings")
    if not isinstance(critical_findings, list):
        errors.append("critical_findings is not a list")
    elif critical_findings:
        errors.append(f"critical_findings is not empty ({len(critical_findings)} found)")

    if report.get("remaining_overconfidence_risk") != "low":
        errors.append("remaining_overconfidence_risk is not 'low'")

    if report.get("system_integrity_score") != 100:
        errors.append("system_integrity_score is not 100")

    return errors


def _run_once(
    *,
    run_index: int,
    python_bin: str,
    audit_script: Path,
    objective: str,
    project_root: Path,
    output_dir: Path,
    timeout_seconds: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cmd = [python_bin, str(audit_script), "--objective", objective]
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    elapsed = round(time.time() - start, 3)

    stdout_path = output_dir / f"run_{run_index:02d}.stdout.log"
    stderr_path = output_dir / f"run_{run_index:02d}.stderr.log"
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    run_errors: List[str] = []
    report: Dict[str, Any] = {}

    if proc.returncode != 0:
        run_errors.append(f"verify_reasoning_mode.py exited with code {proc.returncode}")

    try:
        report = _extract_last_json_object(proc.stdout or "")
    except Exception as exc:  # fail loud in summary
        run_errors.append(f"failed to parse JSON output: {exc}")

    if report:
        run_errors.extend(_validate_report(report))

    run_summary = {
        "run": run_index,
        "return_code": proc.returncode,
        "duration_seconds": elapsed,
        "stdout_log": str(stdout_path.relative_to(project_root)),
        "stderr_log": str(stderr_path.relative_to(project_root)),
        "errors": run_errors,
    }
    if report:
        run_summary["reported_overconfidence_risk"] = report.get(
            "remaining_overconfidence_risk"
        )
        run_summary["reported_integrity_score"] = report.get("system_integrity_score")
        run_summary["reported_critical_findings"] = len(
            report.get("critical_findings") or []
        )

    return run_summary, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run verify_reasoning_mode.py repeatedly and fail on any invariant break."
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of consecutive runs.")
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to run verify_reasoning_mode.py.",
    )
    parser.add_argument(
        "--audit-script",
        default="verify_reasoning_mode.py",
        help="Path to verify_reasoning_mode.py relative to project root.",
    )
    parser.add_argument(
        "--objective",
        default="What are the key advantages and limitations of transformer architecture in NLP?",
        help="Objective passed through to verify_reasoning_mode.py.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=10800,
        help="Per-run timeout in seconds.",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/ci_self_audit",
        help="Directory for CI logs and summary, relative to project root.",
    )
    args = parser.parse_args()

    if args.runs < 1:
        raise ValueError("--runs must be at least 1")

    project_root = Path(__file__).resolve().parents[1]
    audit_script = Path(args.audit_script)
    if not audit_script.is_absolute():
        audit_script = project_root / audit_script
    audit_script = audit_script.resolve()
    if not audit_script.exists():
        raise FileNotFoundError(f"audit script not found: {audit_script}")

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        summary = {
            "strict_gate_passed": False,
            "runs_requested": args.runs,
            "runs_passed": 0,
            "runs_failed": args.runs,
            "errors": ["OPENROUTER_API_KEY is not set"],
        }
        print(json.dumps(summary, indent=2))
        return 2

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_summaries: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []

    for run_index in range(1, args.runs + 1):
        run_summary, report = _run_once(
            run_index=run_index,
            python_bin=args.python_bin,
            audit_script=audit_script,
            objective=args.objective,
            project_root=project_root,
            output_dir=output_dir,
            timeout_seconds=args.timeout_seconds,
        )
        run_summaries.append(run_summary)
        reports.append(report)

    failed_runs = [item for item in run_summaries if item["errors"]]
    summary = {
        "strict_gate_passed": len(failed_runs) == 0,
        "runs_requested": args.runs,
        "runs_passed": args.runs - len(failed_runs),
        "runs_failed": len(failed_runs),
        "run_summaries": run_summaries,
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if summary["strict_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
