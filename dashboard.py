"""Rich-powered Interactive Terminal Dashboard.

Renders live-demonstration visual diagnostics for hackathon judges and network engineers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from core.orchestrator import OrchestrationResult
from protocol.models import SeverityLevel


class NetworkIntelligenceDashboard:
    """Renders comprehensive, explainable visual telemetry and multi-agent arbitration diagnostics."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    def render(self, result: OrchestrationResult) -> None:
        """Render the complete dashboard to the terminal."""
        self._render_header(result)
        self._render_ingestion_and_normalization(result)
        self._render_multi_agent_findings(result)
        self._render_inter_agent_messages(result)
        self._render_evidence_and_conflict_resolution(result)
        self._render_confidence_breakdown(result)
        self._render_final_report_panel(result)

    def _render_header(self, result: OrchestrationResult) -> None:
        header_text = Text()
        header_text.append("NETCOOP AI GRAND FINALE — PRODUCTION-GRADE NETWORK INTELLIGENCE\n", style="bold cyan")
        header_text.append(f"Incident ID: {result.report.incident_id}  |  ", style="bold yellow")
        header_text.append(f"Trace ID: {result.arbitration_result.execution_trace_id}  |  ", style="white")
        header_text.append(f"Execution Duration: {result.total_duration_ms} ms  |  ", style="green")
        header_text.append("Deterministic Multi-Agent Engine", style="dim italic")

        self.console.print(Panel(
            header_text,
            border_style="cyan",
            box=box.DOUBLE
        ))

    def _render_ingestion_and_normalization(self, result: OrchestrationResult) -> None:
        table = Table(
            title="1. Telemetry Ingestion & Canonical Normalization (CIM)",
            box=box.ROUNDED,
            header_style="bold magenta",
            expand=True
        )
        table.add_column("Device ID", style="cyan", no_wrap=True)
        table.add_column("Schema Detected", style="yellow")
        table.add_column("Reported Status", style="blue")
        table.add_column("Metrics Populated", justify="center")
        table.add_column("Completeness", justify="center")
        table.add_column("Normalization Warnings", style="dim")

        for r in result.canonical_telemetry:
            comp_pct = f"{round(r.completeness_ratio() * 100, 1)}%"
            status_style = "green" if r.reported_status == "HEALTHY" else "red" if r.reported_status in ("CRITICAL", "ERROR") else "yellow"
            status_text = Text(r.reported_status or "NONE", style=status_style)

            warn_count = len(r.normalization_warnings)
            warn_str = f"{warn_count} warning(s)" if warn_count > 0 else "Clean (0)"

            metrics_summary = []
            if r.metrics.latency_ms is not None:
                metrics_summary.append(f"lat:{r.metrics.latency_ms}ms")
            if r.metrics.packet_loss_pct is not None:
                metrics_summary.append(f"loss:{r.metrics.packet_loss_pct}%")
            if r.metrics.cpu_pct is not None:
                metrics_summary.append(f"cpu:{r.metrics.cpu_pct}%")
            if r.metrics.interface_errors is not None:
                metrics_summary.append(f"errs:{r.metrics.interface_errors}")

            table.add_row(
                r.device_id,
                r.schema_version_detected.value,
                status_text,
                ", ".join(metrics_summary) if metrics_summary else "No valid metrics",
                comp_pct,
                warn_str
            )

        self.console.print(table)

    def _render_multi_agent_findings(self, result: OrchestrationResult) -> None:
        table = Table(
            title="2. Specialized Multi-Agent Parallel Analysis",
            box=box.ROUNDED,
            header_style="bold blue",
            expand=True
        )
        table.add_column("Specialized Agent", style="bold white", no_wrap=True)
        table.add_column("Device ID", style="cyan")
        table.add_column("Overall Severity", justify="center")
        table.add_column("Suspected Issues", style="yellow")
        table.add_column("Evidence Count", justify="center")
        table.add_column("Missing Metrics Handled", style="dim")

        sev_styles = {
            SeverityLevel.HEALTHY: "bold green",
            SeverityLevel.WARNING: "bold yellow",
            SeverityLevel.CRITICAL: "bold red",
            SeverityLevel.INFO: "bold cyan",
            SeverityLevel.UNKNOWN: "dim white",
        }

        for f in result.agent_findings:
            sev_style = sev_styles.get(f.overall_severity, "white")
            sev_text = Text(f.overall_severity.value, style=sev_style)
            issues_str = ", ".join(f.suspected_issues) if f.suspected_issues else "None (Nominal)"
            missing_str = ", ".join(f.missing_metrics) if f.missing_metrics else "None"

            table.add_row(
                f.agent_name,
                f.device_id,
                sev_text,
                issues_str,
                str(len(f.evidence)),
                missing_str
            )

        self.console.print(table)

    def _render_inter_agent_messages(self, result: OrchestrationResult) -> None:
        table = Table(
            title="3. Inter-Agent Typed Messaging Contract Log",
            box=box.SIMPLE_HEAD,
            header_style="bold cyan",
            expand=True
        )
        table.add_column("Sender", style="green", no_wrap=True)
        table.add_column("Recipient", style="yellow", no_wrap=True)
        table.add_column("Message Type", style="bold magenta")
        table.add_column("Payload Details", style="white")

        for msg in result.agent_messages:
            payload_str = ", ".join(f"{k}: {v}" for k, v in msg.payload.items())
            table.add_row(msg.sender, msg.recipient, msg.message_type, payload_str)

        self.console.print(table)

    def _render_evidence_and_conflict_resolution(self, result: OrchestrationResult) -> None:
        table = Table(
            title="4. Central Evidence Aggregation & Conflict Resolution",
            box=box.ROUNDED,
            header_style="bold yellow",
            expand=True
        )
        table.add_column("Polarity", justify="center", no_wrap=True)
        table.add_column("Diagnostic Evidence Description", style="white")

        for sup in result.arbitration_result.supporting_evidence:
            table.add_row(Text("SUPPORTS", style="bold green"), sup)

        for contra in result.arbitration_result.contradictory_evidence:
            table.add_row(Text("CONTRADICTS", style="bold red"), contra)

        if not result.arbitration_result.supporting_evidence and not result.arbitration_result.contradictory_evidence:
            table.add_row(Text("NEUTRAL", style="dim"), "No active fault evidence registered.")

        self.console.print(table)

    def _render_confidence_breakdown(self, result: OrchestrationResult) -> None:
        conf = result.report.confidence
        conf_pct = round(conf * 100, 1)

        if conf >= 0.75:
            conf_color = "bold green"
            status_desc = "High Confidence — Evidence strongly corroborates single root cause"
        elif conf >= 0.45:
            conf_color = "bold yellow"
            status_desc = "Moderate Confidence — Corroborated with minor data gaps or alternative signals"
        else:
            conf_color = "bold red"
            status_desc = "Low / Inconclusive — Insufficient telemetry signals or heavy contradiction"

        content = Text()
        content.append(f"Confidence Score: {conf} ({conf_pct}%)\n", style=conf_color)
        content.append(f"Assessment: {status_desc}\n", style="white")
        content.append(f"Evidence Completeness: {round(result.arbitration_result.evidence_completeness * 100, 1)}%\n", style="cyan")

        if result.arbitration_result.uncertainty_factors:
            content.append("\nUncertainty Factors / Penalties Applied:\n", style="bold yellow")
            for u in result.arbitration_result.uncertainty_factors:
                content.append(f"  • {u}\n", style="yellow")

        if result.arbitration_result.alternative_hypotheses:
            content.append("\nAlternative Hypotheses Evaluated:\n", style="bold cyan")
            for alt in result.arbitration_result.alternative_hypotheses:
                content.append(
                    f"  • {alt['hypothesis']}: confidence {round(alt['confidence'], 3)}, "
                    f"signals: {alt['supporting_signals']}\n",
                    style="dim"
                )

        self.console.print(Panel(
            content,
            title="5. Deterministic Confidence & Arbitration Breakdown",
            border_style="magenta",
            box=box.ROUNDED
        ))

    def _render_final_report_panel(self, result: OrchestrationResult) -> None:
        report = result.report
        rep_text = Text()

        rep_text.append(f"INCIDENT STATUS: ", style="bold white")
        rep_text.append(f"{report.status.upper()}\n", style="bold green" if report.status == "diagnosed" else "bold yellow")
        rep_text.append(f"DIAGNOSED ROOT CAUSE: ", style="bold white")
        rep_text.append(f"{report.suspected_root_cause}\n", style="bold underline red" if report.suspected_root_cause != "NORMAL_OPERATION" else "bold green")
        rep_text.append(f"CONFIDENCE: {round(report.confidence * 100, 1)}%\n", style="bold cyan")
        
        aff_str = ", ".join(report.affected_devices) if report.affected_devices else "None (Nominal Operation)"
        rep_text.append(f"AFFECTED INFRASTRUCTURE: {aff_str}\n", style="yellow")
        rep_text.append(f"EVIDENCE SOURCES: {', '.join(report.evidence_sources)}\n\n", style="dim cyan")

        rep_text.append("RECOMMENDED REMEDIATION ACTIONS:\n", style="bold green")
        for idx, act in enumerate(report.recommended_actions, 1):
            rep_text.append(f"  {idx}. {act}\n", style="white")

        self.console.print(Panel(
            rep_text,
            title="6. Final Unified Incident Report (Page 5 Schema)",
            border_style="green" if report.suspected_root_cause == "NORMAL_OPERATION" else "red",
            box=box.DOUBLE
        ))
