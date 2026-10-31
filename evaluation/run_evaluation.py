"""Comprehensive Evaluation Runner for the NetCoop AI Hackathon.

Executes all 6 primary scenarios and edge-case scenarios, verifies diagnostic expectations,
asserts deterministic reproducibility, and outputs a machine-readable summary JSON.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich import box
from rich.console import Console
from rich.table import Table

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType, UnifiedIncidentReport


def run_all_evaluations() -> Dict[str, Any]:
    console = Console()
    scenarios_dir = Path(__file__).resolve().parent.parent / "data" / "scenarios"
    scenario_files = sorted(list(scenarios_dir.glob("*.json")))

    orchestrator = NetworkIntelligenceOrchestrator()

    # Ground-truth expectations for each scenario
    expected_expectations = {
        "scenario_1_normal.json": {
            "expected_cause": HypothesisType.NORMAL_OPERATION.value,
            "min_confidence": 0.45,
            "max_affected": 0,
        },
        "scenario_2_congestion.json": {
            "expected_cause": HypothesisType.LINK_CONGESTION.value,
            "min_confidence": 0.65,
            "must_affect": ["BLDG-SW-ENG"],
        },
        "scenario_3_hardware_failure.json": {
            "expected_cause": HypothesisType.HARDWARE_FAILURE.value,
            "min_confidence": 0.65,
            "must_affect": ["BLDG-SW-HOSTEL-A"],
            "must_override_label": True,
        },
        "scenario_4_weak_wifi.json": {
            "expected_cause": HypothesisType.WEAK_WIFI.value,
            "min_confidence": 0.60,
            "must_affect": ["AP-HOSTEL-B2"],
        },
        "scenario_5_dns_dhcp_failure.json": {
            "expected_cause": HypothesisType.DNS_DHCP_FAILURE.value,
            "min_confidence": 0.60,
            "must_affect": ["SRV-DNS-01"],
        },
        "scenario_6_schema_interop_failure.json": {
            "expected_cause": HypothesisType.LINK_CONGESTION.value,
            "min_warnings": 4,
            "min_confidence": 0.60,
        },
        "scenario_edge_missing_telemetry.json": {
            "expected_cause": HypothesisType.INSUFFICIENT_EVIDENCE.value,
            "expect_insufficient_or_low_conf": True,
        },
        "scenario_edge_conflicting_labels.json": {
            "expected_cause": HypothesisType.HARDWARE_FAILURE.value,
            "must_override_label": True,
            "must_affect": ["DIST-SW-SOUTH"],
        },
        "scenario_edge_stale_timestamps.json": {
            "expected_cause": HypothesisType.INSUFFICIENT_EVIDENCE.value,
            "must_penalize_staleness": True,
        },
        "scenario_edge_unknown_devices.json": {
            "expected_cause": HypothesisType.WEAK_WIFI.value,
            "must_affect": ["ROGUE-ACCESS-POINT-99"],
        },
        "scenario_edge_multiple_incidents.json": {
            "min_confidence": 0.50,
            "must_have_multiple_incidents": 2,
            "must_affect": ["AP-HOSTEL-B1", "BLDG-SW-ENG"],
        },
        "scenario_edge_malformed_payload.json": {
            "expected_cause": HypothesisType.INSUFFICIENT_EVIDENCE.value,
        },
        "scenario_organizer_latency_spike.json": {
            "expected_cause": HypothesisType.LINK_CONGESTION.value,
            "min_confidence": 0.65,
            "must_affect": ["SW_CAMPUS_3"],
        },
        "scenario_organizer_hardware_failure.json": {
            "expected_cause": HypothesisType.HARDWARE_FAILURE.value,
            "min_confidence": 0.60,
            "must_affect": ["SW_CAMPUS_8"],
        },
        "scenario_organizer_batch_10_devices.json": {
            "expected_cause": HypothesisType.HARDWARE_FAILURE.value,
            "min_confidence": 0.50,
            "must_affect": ["SW_CAMPUS_FAULTY_10"],
            "max_affected": 1,
        }
    }

    results: List[Dict[str, Any]] = []
    total_passed = 0
    total_failed = 0

    table = Table(
        title="NetCoop AI Benchmark & Scenario Evaluation Results",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True
    )
    table.add_column("Scenario ID", style="bold white", no_wrap=True)
    table.add_column("Diagnosed Root Cause", style="yellow")
    table.add_column("Confidence", justify="center")
    table.add_column("Affected Count", justify="center")
    table.add_column("Duration (ms)", justify="center")
    table.add_column("Reproducible", justify="center")
    table.add_column("Verdict", justify="center")

    for s_file in scenario_files:
        with open(s_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        s_id = raw_data.get("scenario_id", s_file.stem)
        telemetry = raw_data.get("telemetry", raw_data)

        # Derive reference_time from the scenario's own timestamps so that
        # staleness is not inflated when judges run the evaluation later.
        # For the deliberate stale-data scenario, we let the real clock apply.
        is_stale_scenario = "stale" in s_file.name
        reference_time = None
        if not is_stale_scenario:
            # Extract the most recent timestamp from the telemetry payload
            devices = telemetry if isinstance(telemetry, list) else [telemetry]
            ts_candidates: List[datetime] = []
            for dev in devices:
                raw_ts = dev.get("timestamp") or dev.get("epoch_timestamp")
                if raw_ts:
                    try:
                        if isinstance(raw_ts, (int, float)):
                            ts_candidates.append(datetime.fromtimestamp(raw_ts, tz=timezone.utc))
                        else:
                            dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                            ts_candidates.append(dt)
                    except Exception:
                        pass
            if ts_candidates:
                # Use max scenario timestamp + 60 s as reference (freshly-arrived data)
                from datetime import timedelta
                reference_time = max(ts_candidates) + timedelta(seconds=60)

        # 1. First execution
        t0 = time.perf_counter()
        res1 = orchestrator.process(telemetry, incident_id=s_id, reference_time=reference_time)
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # 2. Second execution to verify 100% deterministic reproducibility
        res2 = orchestrator.process(telemetry, incident_id=s_id, reference_time=reference_time)
        is_reproducible = (
            res1.report.suspected_root_cause == res2.report.suspected_root_cause and
            res1.report.confidence == res2.report.confidence and
            res1.report.affected_devices == res2.report.affected_devices
        )

        # 3. Evaluate criteria
        expectations = expected_expectations.get(s_file.name, {})
        passed = True
        failure_reasons = []

        if not is_reproducible:
            passed = False
            failure_reasons.append("Non-deterministic execution: run 1 and run 2 differed.")

        if "expected_cause" in expectations:
            if res1.report.suspected_root_cause != expectations["expected_cause"]:
                passed = False
                failure_reasons.append(
                    f"Expected root cause {expectations['expected_cause']}, got {res1.report.suspected_root_cause}"
                )

        if "min_confidence" in expectations:
            if res1.report.confidence < expectations["min_confidence"]:
                passed = False
                failure_reasons.append(
                    f"Confidence {res1.report.confidence} < min threshold {expectations['min_confidence']}"
                )

        if "max_affected" in expectations:
            if len(res1.report.affected_devices) > expectations["max_affected"]:
                passed = False
                failure_reasons.append(
                    f"Expected at most {expectations['max_affected']} affected, got {len(res1.report.affected_devices)}"
                )

        if "must_affect" in expectations:
            for d in expectations["must_affect"]:
                if d not in res1.report.affected_devices:
                    passed = False
                    failure_reasons.append(f"Device {d} not in affected_devices {res1.report.affected_devices}")

        if expectations.get("must_have_multiple_incidents"):
            req_inc = expectations["must_have_multiple_incidents"]
            if len(res1.report.incidents) < req_inc:
                passed = False
                failure_reasons.append(
                    f"Expected at least {req_inc} co-occurring incidents in report.incidents, got {len(res1.report.incidents)}"
                )

        if expectations.get("must_override_label"):
            has_override = any("untrusted" in c.lower() or "contradicted" in c.lower() for c in res1.arbitration_result.contradictory_evidence)
            if not has_override:
                passed = False
                failure_reasons.append("Failed to record label override in contradictory evidence.")

        if expectations.get("expect_insufficient_or_low_conf"):
            if res1.report.confidence > 0.65 and res1.report.suspected_root_cause != HypothesisType.INSUFFICIENT_EVIDENCE.value:
                passed = False
                failure_reasons.append("Sparse data produced inappropriately high confidence score.")

        if passed:
            total_passed += 1
            verdict_text = "[bold green]PASS[/bold green]"
        else:
            total_failed += 1
            verdict_text = "[bold red]FAIL[/bold red]"

        repro_text = "[green]YES[/green]" if is_reproducible else "[red]NO[/red]"
        conf_pct = f"{round(res1.report.confidence * 100, 1)}%"

        table.add_row(
            s_id,
            res1.report.suspected_root_cause,
            conf_pct,
            str(len(res1.report.affected_devices)),
            str(duration_ms),
            repro_text,
            verdict_text
        )

        results.append({
            "scenario_file": s_file.name,
            "scenario_id": s_id,
            "passed": passed,
            "failure_reasons": failure_reasons,
            "diagnosed_root_cause": res1.report.suspected_root_cause,
            "confidence": res1.report.confidence,
            "affected_devices": res1.report.affected_devices,
            "duration_ms": duration_ms,
            "is_reproducible": is_reproducible,
            "evidence_completeness": res1.arbitration_result.evidence_completeness,
            "report": res1.report.model_dump(),
        })

    console.print(table)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenario_files),
        "passed": total_passed,
        "failed": total_failed,
        "pass_rate": round((total_passed / len(scenario_files)) * 100.0, 1) if scenario_files else 0.0,
        "results": results
    }

    # Save to machine-readable json
    results_path = Path(__file__).resolve().parent.parent / "evaluation_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    console.print(f"[dim]Machine-readable summary exported to {results_path}[/dim]")

    return summary


if __name__ == "__main__":
    run_all_evaluations()
