"""Main entry point for the NetCoop AI Network Intelligence System.

Provides CLI interface for running live incident diagnosis, viewing the Rich dashboard,
exporting evaluation artifacts, and running the evaluation suite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.orchestrator import NetworkIntelligenceOrchestrator
from core.remediation import RemediationSimulator
from core.state_store import SessionStateStore
from core.web_report import HTMLReportGenerator
from dashboard import NetworkIntelligenceDashboard
from protocol.models import SchemaVersion


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NetCoop AI Grand Finale — Production-Grade Network Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--scenario",
        type=str,
        help="Path to scenario JSON file (e.g. data/scenarios/scenario_2_congestion.json)."
    )
    parser.add_argument(
        "--raw-json",
        type=str,
        help="Raw telemetry JSON payload string or '-' to read from standard input."
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Render rich interactive terminal dashboard."
    )
    parser.add_argument(
        "--simulate-remediation",
        action="store_true",
        help="Execute automated remediation simulation (dry-run) projecting recovered KPIs."
    )
    parser.add_argument(
        "--export-json",
        type=str,
        help="Path to export the final UnifiedIncidentReport JSON."
    )
    parser.add_argument(
        "--export-markdown",
        type=str,
        help="Path to export the executive Markdown summary."
    )
    parser.add_argument(
        "--export-html",
        type=str,
        help="Path to export the interactive standalone HTML report."
    )
    parser.add_argument(
        "--pause-session",
        type=str,
        help="Session ID to checkpoint and freeze investigation to durable state store."
    )
    parser.add_argument(
        "--resume-session",
        type=str,
        help="Session ID to resume a previously paused investigation from checkpoint."
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="Enumerate all persisted investigation sessions in store."
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        choices=["V1", "V2", "V3", "AUTO"],
        default="AUTO",
        help="Enforce a specific telemetry schema version or AUTO detect."
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the interactive Web NOC Dashboard server on http://127.0.0.1:8000."
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Execute the complete evaluation suite across all hackathon scenarios."
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Execute the 700-case scientific benchmark with multiclass Brier score and reliability diagram."
    )
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="Execute the 210-case held-out generalization benchmark across unseen campus topologies."
    )
    parser.add_argument(
        "--verify-all",
        action="store_true",
        help="Execute comprehensive end-to-end competition audit across all test suites and benchmarks."
    )

    args = parser.parse_args()

    state_store = SessionStateStore()

    # Handle session management commands
    if args.list_sessions:
        sessions = state_store.list_sessions()
        print(f"Total Persisted Diagnostic Sessions: {len(sessions)}")
        for s in sessions:
            print(f"  - Session: {s['session_id']} | Phase: {s['phase']} | Paused: {s['is_paused']} | Decision: {s.get('arbitration_decision')}")
        return 0

    if args.resume_session:
        checkpoint = state_store.resume_session(args.resume_session)
        if not checkpoint:
            sys.stderr.write(f"Error: Session '{args.resume_session}' not found in state store.\n")
            return 1
        print(f"Resumed session '{args.resume_session}' from phase: {checkpoint.phase}")
        print(json.dumps(checkpoint.state_payload, indent=2))
        return 0

    # If --ui is requested, launch the interactive web NOC dashboard
    if args.ui:
        from web_ui import start_server
        start_server()
        return 0

    # If --evaluate is requested, trigger the evaluation harness
    if args.evaluate:
        from evaluation.run_evaluation import run_all_evaluations
        summary = run_all_evaluations()
        print("\n=== Evaluation Suite Completed ===")
        print(f"Total Scenarios Tested: {summary['total_scenarios']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Pass Rate: {summary['pass_rate']}%")
        return 0 if summary["failed"] == 0 else 1

    if args.benchmark:
        from evaluation.benchmark_runner import BenchmarkRunner
        runner = BenchmarkRunner(cases_per_class=100)
        runner.run_full_benchmark()
        return 0

    if args.held_out:
        from evaluation.held_out_benchmark import HeldOutBenchmarkRunner
        runner = HeldOutBenchmarkRunner(cases_per_class=30)
        runner.run_held_out_benchmark()
        return 0

    if args.verify_all:
        import verify_all
        return verify_all.main()

    # Ingestion source
    raw_payload = None
    incident_id = None

    if args.scenario:
        scenario_path = Path(args.scenario)
        if not scenario_path.exists():
            sys.stderr.write(f"Error: Scenario file '{args.scenario}' not found.\n")
            return 1
        with open(scenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            incident_id = data.get("scenario_id")
            raw_payload = data.get("telemetry", data)
    elif args.raw_json:
        if args.raw_json == "-":
            raw_content = sys.stdin.read()
        else:
            raw_content = args.raw_json
        try:
            raw_payload = json.loads(raw_content)
        except Exception:
            # Resilient fallback for Windows PowerShell / shell quote stripping
            import ast
            try:
                raw_payload = ast.literal_eval(raw_content)
            except Exception:
                try:
                    raw_payload = json.loads(raw_content.replace("'", '"'))
                except Exception as e:
                    sys.stderr.write(f"Error: Failed to parse input JSON: {e}\n")
                    return 1
    else:
        # Default to Scenario 2 Congestion for quick interactive demonstration
        default_scenario = Path(__file__).resolve().parent / "data" / "scenarios" / "scenario_2_congestion.json"
        if default_scenario.exists():
            with open(default_scenario, "r", encoding="utf-8") as f:
                data = json.load(f)
                incident_id = data.get("scenario_id")
                raw_payload = data.get("telemetry", data)
        else:
            parser.print_help()
            return 1

    # Schema version setting
    explicit_version = None
    if args.schema_version != "AUTO":
        explicit_version = SchemaVersion(args.schema_version)

    # Determine reference_time if timestamps are present in historical scenario payloads
    reference_time = None
    if isinstance(raw_payload, list):
        from datetime import datetime, timezone, timedelta
        ts_candidates = []
        for item in raw_payload:
            if isinstance(item, dict):
                raw_ts = item.get("timestamp") or item.get("epoch_timestamp") or item.get("ts")
                if raw_ts is not None:
                    try:
                        if isinstance(raw_ts, (int, float)):
                            ts_candidates.append(datetime.fromtimestamp(raw_ts, tz=timezone.utc))
                        else:
                            dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                            ts_candidates.append(dt)
                    except Exception:
                        pass
        if ts_candidates:
            reference_time = max(ts_candidates) + timedelta(seconds=60)

    # Initialize and execute orchestrator
    orchestrator = NetworkIntelligenceOrchestrator()
    result = orchestrator.process(
        raw_input=raw_payload,
        incident_id=incident_id,
        explicit_version=explicit_version,
        reference_time=reference_time
    )

    # Optional automated remediation simulation (Page 3 of spec)
    remediation_sim = None
    if args.simulate_remediation:
        remediation_sim = RemediationSimulator.simulate_remediation(
            root_cause=result.report.suspected_root_cause,
            affected_devices=result.report.affected_devices,
            telemetry_records=result.canonical_telemetry
        )

    # Optional checkpoint persistence (Page 3 of spec)
    if args.pause_session:
        state_store.pause_session(
            session_id=args.pause_session,
            current_state={
                "incident_id": result.report.incident_id,
                "diagnosed_root_cause": result.report.suspected_root_cause,
                "confidence": result.report.confidence,
                "affected_devices": result.report.affected_devices,
                "report": result.report.model_dump()
            }
        )
        sys.stderr.write(f"Investigation session '{args.pause_session}' persisted & paused in state store.\n")

    # Render dashboard if requested
    if args.dashboard:
        dashboard = NetworkIntelligenceDashboard()
        dashboard.render(result)
        if remediation_sim:
            from rich.panel import Panel
            from rich import box
            sim_text = f"SIMULATED ACTIONS ({len(remediation_sim.actions)} steps):\n"
            for act in remediation_sim.actions:
                sim_text += f"  • [{act.action_id}] {act.action_type} on {act.target_device}\n    CLI: {act.simulated_cli_command}\n"
            dashboard.console.print(Panel(sim_text, title="Automated Remediation Simulation (Dry-Run)", border_style="cyan", box=box.ROUNDED))
    else:
        # Print JSON report to stdout
        print(result.report.model_dump_json(indent=2))

    # Export artifacts if specified
    if args.export_json:
        export_path = Path(args.export_json)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(result.report.model_dump_json(indent=2))
        sys.stderr.write(f"Report exported to {export_path}\n")

    if args.export_markdown:
        export_md_path = Path(args.export_markdown)
        export_md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_md_path, "w", encoding="utf-8") as f:
            f.write(result.markdown_summary)
        sys.stderr.write(f"Markdown summary exported to {export_md_path}\n")

    if args.export_html:
        export_html_path = Path(args.export_html)
        export_html_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = HTMLReportGenerator.generate_html(result, remediation_sim=remediation_sim)
        with open(export_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        sys.stderr.write(f"Interactive HTML report exported to {export_html_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
