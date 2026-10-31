"""Comprehensive Competition-Readiness Verification & Acceptance Suite for NetCoop AI.

Executes and audits the entire platform end-to-end:
1. Pytest Unit & Regression Suite (65 tests)
2. Scenario Reproducibility Suite (15 scenarios) with strict pass_rate == 100%
3. Organizer Generator Check (150 cases, 0 dropped fields)
4. Scientific 700-Case Evaluation Lab & PAVA Isotonic Calibration with strict numerical thresholds:
   - accuracy >= 98.0%
   - macro_f1 >= 0.95
   - top_label_brier_score <= 0.05
   - multiclass_brier_score <= 0.05
   - expected_calibration_error <= 0.10
   - total cases == 700
5. Held-Out Generalization Lab across Unseen Topologies (210 cases) with strict numerical thresholds:
   - held_out_accuracy >= 95.0%
   - held_out_macro_f1 >= 0.95
   - total cases == 210
6. Model Context Protocol (MCP) JSON-RPC 2.0 Interface validation
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f" {title.upper()}")
    print("=" * 80)


def run_cmd(cmd: str, desc: str) -> bool:
    print(f"\n[RUNNING] {desc}...")
    t0 = time.time()
    res = subprocess.run([sys.executable] + cmd.split()[1:], cwd=PROJECT_ROOT, capture_output=True, text=True)
    dur = time.time() - t0
    if res.returncode == 0:
        print(f"[PASS] {desc} (completed in {dur:.2f}s)")
        return True
    else:
        print(f"[FAIL] {desc} (failed after {dur:.2f}s)")
        print(res.stdout)
        print(res.stderr)
        return False


def verify_numerical_thresholds() -> Tuple[bool, List[Tuple[str, str, str, bool]]]:
    """Audit persisted machine-readable JSON reports against strict numerical criteria."""
    audit_results: List[Tuple[str, str, str, bool]] = []
    all_ok = True

    # 1. 15 Scenarios report
    eval_json_path = PROJECT_ROOT / "evaluation_results.json"
    if eval_json_path.exists():
        try:
            with open(eval_json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            total_scenarios = d.get("total_scenarios", 0)
            pass_rate = d.get("pass_rate", 0.0)
            failed = d.get("failed", -1)

            ok_scen = (total_scenarios == 15 and pass_rate == 100.0 and failed == 0)
            audit_results.append((
                "15 Scenarios Pass Rate",
                "== 100.0%",
                f"{pass_rate}% ({total_scenarios} total, {failed} failed)",
                ok_scen
            ))
            if not ok_scen:
                all_ok = False
        except Exception as e:
            audit_results.append(("15 Scenarios JSON Audit", "valid JSON", f"Error: {e}", False))
            all_ok = False
    else:
        audit_results.append(("15 Scenarios JSON Audit", "file exists", "Missing evaluation_results.json", False))
        all_ok = False

    # 2. 700-Case Scientific Benchmark report
    bm_json_path = PROJECT_ROOT / "evaluation" / "benchmark_report.json"
    if bm_json_path.exists():
        try:
            with open(bm_json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            cases = d.get("total_scenarios_evaluated", 0)
            acc = d.get("overall_accuracy", 0.0)
            f1 = d.get("macro_f1_score", 0.0)
            top_brier = d.get("top_label_brier_score", 1.0)
            mc_brier = d.get("multiclass_brier_score", 1.0)
            ece = d.get("expected_calibration_error", 1.0)

            ok_cases = (cases == 700)
            audit_results.append(("Benchmark Sample Volume", "== 700 cases", f"{cases} cases", ok_cases))
            if not ok_cases:
                all_ok = False

            ok_acc = (acc >= 98.0)
            audit_results.append(("Benchmark Overall Accuracy", ">= 98.0%", f"{acc:.2f}%", ok_acc))
            if not ok_acc:
                all_ok = False

            ok_f1 = (f1 >= 0.95)
            audit_results.append(("Benchmark Macro-F1", ">= 0.9500", f"{f1:.4f}", ok_f1))
            if not ok_f1:
                all_ok = False

            ok_top_brier = (top_brier <= 0.05)
            audit_results.append(("Top-Label Brier Score", "<= 0.0500", f"{top_brier:.4f}", ok_top_brier))
            if not ok_top_brier:
                all_ok = False

            ok_mc_brier = (mc_brier <= 0.05)
            audit_results.append(("Multiclass Brier Score", "<= 0.0500", f"{mc_brier:.4f}", ok_mc_brier))
            if not ok_mc_brier:
                all_ok = False

            ok_ece = (ece <= 0.10)
            audit_results.append(("Expected Calibration Error (ECE)", "<= 0.1000", f"{ece:.4f}", ok_ece))
            if not ok_ece:
                all_ok = False

        except Exception as e:
            audit_results.append(("Benchmark JSON Audit", "valid JSON", f"Error: {e}", False))
            all_ok = False
    else:
        audit_results.append(("Benchmark JSON Audit", "file exists", "Missing benchmark_report.json", False))
        all_ok = False

    # 3. Held-Out Generalization Benchmark report
    ho_json_path = PROJECT_ROOT / "evaluation" / "held_out_benchmark_report.json"
    if ho_json_path.exists():
        try:
            with open(ho_json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            ho_cases = d.get("held_out_scenarios_evaluated", 0)
            ho_acc = d.get("overall_accuracy", 0.0)
            ho_f1 = d.get("macro_f1_score", 0.0)

            ok_ho_cases = (ho_cases == 210)
            audit_results.append(("Held-Out Sample Volume", "== 210 cases", f"{ho_cases} cases", ok_ho_cases))
            if not ok_ho_cases:
                all_ok = False

            ok_ho_acc = (ho_acc >= 95.0)
            audit_results.append(("Held-Out Generalization Accuracy", ">= 95.0%", f"{ho_acc:.2f}%", ok_ho_acc))
            if not ok_ho_acc:
                all_ok = False

            ok_ho_f1 = (ho_f1 >= 0.95)
            audit_results.append(("Held-Out Macro-F1", ">= 0.9500", f"{ho_f1:.4f}", ok_ho_f1))
            if not ok_ho_f1:
                all_ok = False

        except Exception as e:
            audit_results.append(("Held-Out JSON Audit", "valid JSON", f"Error: {e}", False))
            all_ok = False
    else:
        audit_results.append(("Held-Out JSON Audit", "file exists", "Missing held_out_benchmark_report.json", False))
        all_ok = False

    return all_ok, audit_results


def main() -> int:
    start_total = time.time()
    print_header("NetCoop AI — Grand Finale Verification & Acceptance Audit")
    print("IIT Bhubaneswar Campus Network Multi-Agent Fault Diagnosis System\n")

    step_results = []

    # 1. Pytest Suite
    ok1 = run_cmd("python -m pytest evaluation/ -v", "Full Pytest Suite (65 tests)")
    step_results.append(("Pytest Test Suite (Agents, Ledger, Adapters, Robustness)", "65/65 Tests", ok1))

    # 2. 15-Scenario Reproducibility
    ok2 = run_cmd("python evaluation/run_evaluation.py", "15 Scenario Reproducibility Benchmark")
    step_results.append(("15-Scenario Reproducibility Benchmark", "15/15 Scenarios", ok2))

    # 3. Organizer Telemetry Generator
    ok3 = run_cmd("python organizer_generator_check.py", "Organizer Telemetry Generator Check")
    step_results.append(("Organizer Telemetry Generator Check", "150/150 Batches", ok3))

    # 4. 700-Case Scientific Benchmark
    ok4 = run_cmd("python evaluation/benchmark_runner.py", "700-Case Scientific Benchmark Lab")
    step_results.append(("700-Case Scientific Benchmark Lab", "700 Synthetic Cases", ok4))

    # 5. Held-Out Generalization Benchmark
    ok5 = run_cmd("python evaluation/held_out_benchmark.py", "Held-Out Generalization Benchmark (seed=9999)")
    step_results.append(("Held-Out Generalization Benchmark (Unseen Topologies)", "210 Unseen Cases", ok5))

    # 6. MCP Server Self-Test
    ok6 = run_cmd("python mcp_server.py --test", "Model Context Protocol (MCP) Stdio Test")
    step_results.append(("Model Context Protocol (MCP) JSON-RPC 2.0 Integration", "Tools & Resources Active", ok6))

    # Summary Execution Table
    print_header("Pipeline Stage Execution Summary")
    print(f"{'Verification Category':<54} | {'Target Scope':<20} | Status")
    print("-" * 84)
    all_steps_ok = True
    for item, metric, status in step_results:
        status_str = "PASS [OK]" if status else "FAIL [X]"
        if not status:
            all_steps_ok = False
        print(f"{item:<54} | {metric:<20} | {status_str}")
    print("=" * 84)

    # Numerical Metrics Audit Table
    thresholds_ok, audit_results = verify_numerical_thresholds()

    print_header("Strict Numerical Acceptance Thresholds Audit")
    print(f"{'Metric Audited':<36} | {'Requirement':<16} | {'Observed Value':<18} | Verdict")
    print("-" * 84)
    for metric, req, obs, status in audit_results:
        verdict = "PASS [OK]" if status else "FAIL [VIOLATION]"
        print(f"{metric:<36} | {req:<16} | {obs:<18} | {verdict}")
    print("=" * 84)

    total_duration = time.time() - start_total
    print(f"Total Audit Execution Time: {total_duration:.2f} seconds")

    if all_steps_ok and thresholds_ok:
        print("\n>>> ALL ACCEPTANCE CRITERIA VERIFIED: SYSTEM MEETS COMPETITION THRESHOLDS <<<")
        print(">>> 65 Pytests, 15 Scenarios, 700 Benchmark & 210 Held-Out Cases Statistically Verified <<<\n")
        return 0
    else:
        print("\n>>> CRITICAL WARNING: ONE OR MORE CHECKS OR ACCEPTANCE THRESHOLDS FAILED <<<")
        print(">>> Please review the audit table above and correct any violations. <<<\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
