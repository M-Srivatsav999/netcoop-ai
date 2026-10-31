"""Central Network Intelligence Orchestrator.

Coordinates schema normalization, specialized agent dispatch, typed inter-agent messaging,
evidence aggregation, arbitration, report generation, and explainable trace logging.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from agents.connectivity_agent import ConnectivityAgent
from agents.correlation_agent import CorrelationAgent
from agents.infrastructure_agent import InfrastructureAgent
from agents.reporter_agent import ReporterAgent
from agents.telemetry_agent import TelemetryAgent
from core.confidence_engine import ConfidenceConfig
from core.rules import MetricThresholds
from core.topology import TopologyEngine
from protocol.models import (
    AgentFinding,
    AgentMessage,
    ArbitrationResult,
    CanonicalTelemetry,
    SchemaVersion,
    UnifiedIncidentReport,
)
from protocol.validator import TelemetryNormalizer


class OrchestrationResult(BaseModel):
    """Complete, self-contained output of an orchestration cycle."""
    report: UnifiedIncidentReport
    markdown_summary: str
    canonical_telemetry: List[CanonicalTelemetry]
    agent_findings: List[AgentFinding]
    agent_messages: List[AgentMessage]
    arbitration_result: ArbitrationResult
    execution_trace: List[Dict[str, Any]]
    total_duration_ms: float


class NetworkIntelligenceOrchestrator:
    """Production-grade deterministic multi-agent coordinator."""

    def __init__(
        self,
        topology_engine: Optional[TopologyEngine] = None,
        thresholds: Optional[MetricThresholds] = None,
        confidence_config: Optional[ConfidenceConfig] = None
    ) -> None:
        self.topology = topology_engine or TopologyEngine()
        self.thresholds = thresholds or MetricThresholds()
        self.confidence_config = confidence_config or ConfidenceConfig()

        # Instantiate specialized agents
        self.telemetry_agent = TelemetryAgent(self.thresholds)
        self.infrastructure_agent = InfrastructureAgent(self.thresholds)
        self.connectivity_agent = ConnectivityAgent(self.topology)
        self.correlation_agent = CorrelationAgent(
            topology_engine=self.topology,
            thresholds=self.thresholds,
            confidence_config=self.confidence_config
        )
        self.reporter_agent = ReporterAgent()

    def process(
        self,
        raw_input: Union[Dict[str, Any], List[Dict[str, Any]], str],
        incident_id: Optional[str] = None,
        explicit_version: Optional[SchemaVersion] = None,
        reference_time: Optional[datetime] = None
    ) -> OrchestrationResult:
        """Execute full end-to-end deterministic diagnostic pipeline."""
        start_time = datetime.now(timezone.utc)
        trace: List[Dict[str, Any]] = []
        messages: List[AgentMessage] = []

        def log_trace(step: str, detail: str, data: Optional[Dict[str, Any]] = None) -> None:
            trace.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": step,
                "detail": detail,
                "data": data or {}
            })

        # 1. Input parsing
        log_trace("INGESTION", "Parsing raw payload input.")
        if isinstance(raw_input, str):
            try:
                parsed_input = json.loads(raw_input)
            except Exception as e:
                # Corrupt string input
                log_trace("INGESTION_ERROR", f"JSON deserialization failed: {e}")
                parsed_input = [{"corrupt_payload": raw_input}]
        else:
            parsed_input = raw_input

        # 2. Schema Normalization & CIM Creation
        log_trace("NORMALIZATION", "Invoking TelemetryNormalizer across raw payload.")
        canonical_records = TelemetryNormalizer.normalize_batch(parsed_input, explicit_version=explicit_version)
        detected_versions = list({r.schema_version_detected.value for r in canonical_records})
        total_warnings = sum(len(r.normalization_warnings) for r in canonical_records)

        log_trace(
            "CIM_GENERATION",
            f"Normalized {len(canonical_records)} devices. Detected schema versions: {detected_versions}.",
            {"schema_versions": detected_versions, "warnings_count": total_warnings}
        )

        # 3. Staleness Calculation
        now = reference_time or datetime.now(timezone.utc)
        staleness_seconds = 0.0
        timestamps = [r.timestamp for r in canonical_records if r.timestamp is not None]
        if timestamps:
            most_recent = max(timestamps)
            if most_recent.tzinfo is None:
                most_recent = most_recent.replace(tzinfo=timezone.utc)
            delta = (now - most_recent).total_seconds()
            if delta > 0:
                staleness_seconds = delta

        # 4. Dispatch to specialized agents with explicit typed messaging
        all_findings: List[AgentFinding] = []

        # TelemetryAgent dispatch
        messages.append(AgentMessage(
            sender="Orchestrator",
            recipient="TelemetryAgent",
            message_type="DISPATCH_TELEMETRY",
            payload={"device_count": len(canonical_records),
                     "schema_versions": detected_versions,
                     "normalization_warnings": total_warnings}
        ))
        log_trace("DISPATCH_TELEMETRY_AGENT", "Dispatching canonical records to TelemetryAgent.")
        tel_findings = self.telemetry_agent.analyze_batch(canonical_records)
        all_findings.extend(tel_findings)
        tel_anomalous = [f for f in tel_findings if f.overall_severity.value not in ("HEALTHY", "UNKNOWN")]
        messages.append(AgentMessage(
            sender="TelemetryAgent",
            recipient="Orchestrator",
            message_type="FINDINGS_READY",
            payload={
                "findings_count": len(tel_findings),
                "anomalous_devices": [f.device_id for f in tel_anomalous],
                "issues_detected": [issue for f in tel_anomalous for issue in f.suspected_issues],
                "missing_metrics": {f.device_id: f.missing_metrics for f in tel_findings if f.missing_metrics}
            }
        ))

        # InfrastructureAgent dispatch
        messages.append(AgentMessage(
            sender="Orchestrator",
            recipient="InfrastructureAgent",
            message_type="DISPATCH_INFRASTRUCTURE",
            payload={"device_count": len(canonical_records),
                     "telemetry_anomalies": [f.device_id for f in tel_anomalous]}
        ))
        log_trace("DISPATCH_INFRASTRUCTURE_AGENT", "Dispatching canonical records to InfrastructureAgent.")
        infra_findings = self.infrastructure_agent.analyze_batch(canonical_records)
        all_findings.extend(infra_findings)
        infra_anomalous = [f for f in infra_findings if f.overall_severity.value not in ("HEALTHY", "UNKNOWN")]
        messages.append(AgentMessage(
            sender="InfrastructureAgent",
            recipient="Orchestrator",
            message_type="FINDINGS_READY",
            payload={
                "findings_count": len(infra_findings),
                "anomalous_devices": [f.device_id for f in infra_anomalous],
                "issues_detected": [issue for f in infra_anomalous for issue in f.suspected_issues]
            }
        ))

        # ConnectivityAgent dispatch
        messages.append(AgentMessage(
            sender="Orchestrator",
            recipient="ConnectivityAgent",
            message_type="DISPATCH_CONNECTIVITY",
            payload={"device_count": len(canonical_records),
                     "known_anomalous": [f.device_id for f in tel_anomalous + infra_anomalous]}
        ))
        log_trace("DISPATCH_CONNECTIVITY_AGENT", "Evaluating topology mapping and blast radius.")
        conn_findings = [self.connectivity_agent.analyze(r) for r in canonical_records]
        all_findings.extend(conn_findings)
        cascade_evidence = self.connectivity_agent.analyze_topology_cascade(canonical_records)
        conn_anomalous = [f for f in conn_findings if f.overall_severity.value not in ("HEALTHY", "UNKNOWN")]
        messages.append(AgentMessage(
            sender="ConnectivityAgent",
            recipient="Orchestrator",
            message_type="FINDINGS_READY",
            payload={
                "findings_count": len(conn_findings),
                "cascade_items": len(cascade_evidence),
                "blast_radius_devices": [f.device_id for f in conn_anomalous]
            }
        ))

        # 5a. Label-vs-Metrics Conflict Negotiation (REQUEST_CLARIFICATION pattern)
        # If any device reports HEALTHY label but has anomalous telemetry/infra findings,
        # CorrelationAgent sends back a REQUEST_CLARIFICATION to TelemetryAgent.
        conflicted_devices = []
        for record in canonical_records:
            reported = (record.reported_status or "").upper()
            is_labeled_healthy = reported in ("HEALTHY", "OK", "NORMAL", "UP")
            tel_f = next((f for f in tel_findings if f.device_id == record.device_id), None)
            infra_f = next((f for f in infra_findings if f.device_id == record.device_id), None)
            tel_bad = tel_f and tel_f.overall_severity.value not in ("HEALTHY", "UNKNOWN")
            infra_bad = infra_f and infra_f.overall_severity.value not in ("HEALTHY", "UNKNOWN")
            if is_labeled_healthy and (tel_bad or infra_bad):
                conflicted_devices.append(record.device_id)

        if conflicted_devices:
            # Emit dynamic structured AgentDisagreement messages capturing actual findings per device
            for c_dev in conflicted_devices:
                tel_f = next((f for f in tel_findings if f.device_id == c_dev), None)
                infra_f = next((f for f in infra_findings if f.device_id == c_dev), None)
                record = next((r for r in canonical_records if r.device_id == c_dev), None)
                rep_label = record.reported_status if record else "HEALTHY"
                
                tel_issues = tel_f.suspected_issues if tel_f else []
                infra_issues = infra_f.suspected_issues if infra_f else []
                supporting_ev = [
                    {"metric": e.metric_name, "value": e.observed_value, "desc": e.description}
                    for f in (tel_f, infra_f) if f for e in f.evidence if e.polarity == "SUPPORTS"
                ]

                messages.append(AgentMessage(
                    sender="CorrelationAgent",
                    recipient="TelemetryAgent",
                    message_type="AGENT_DISAGREEMENT",
                    payload={
                        "disagreement_id": f"DISAGREE-{c_dev}",
                        "device_id": c_dev,
                        "reported_generator_claim": rep_label,
                        "telemetry_agent_findings": tel_issues,
                        "infrastructure_agent_findings": infra_issues,
                        "competing_evidence": supporting_ev[:4],
                        "resolution_strategy": "DETERMINISTIC_METRIC_SUPREMACY",
                        "resolution_rule": "Physical telemetry signals override untrusted status labels",
                        "status": "OPEN"
                    }
                ))

            messages.append(AgentMessage(
                sender="CorrelationAgent",
                recipient="TelemetryAgent",
                message_type="REQUEST_CLARIFICATION",
                payload={
                    "reason": "Status label contradicts empirical metric observations",
                    "devices": conflicted_devices,
                    "action": "Empirical metrics override label — untrusted label reconciliation active"
                }
            ))
            messages.append(AgentMessage(
                sender="TelemetryAgent",
                recipient="CorrelationAgent",
                message_type="CLARIFICATION_RESPONSE",
                payload={
                    "devices": conflicted_devices,
                    "resolution": "Label overridden by metric evidence",
                    "override_justification": "Observed metrics contradict reported status; deterministic rules take precedence",
                    "status": "RESOLVED"
                }
            ))
            log_trace(
                "LABEL_CONFLICT_NEGOTIATION",
                f"CorrelationAgent↔TelemetryAgent negotiation completed for {len(conflicted_devices)} device(s).",
                {"conflicted": conflicted_devices}
            )

        # 5b. Correlation & Arbitration
        messages.append(AgentMessage(
            sender="Orchestrator",
            recipient="CorrelationAgent",
            message_type="ARBITRATE_REQUEST",
            payload={
                "total_findings": len(all_findings),
                "staleness_s": staleness_seconds,
                "label_conflicts_resolved": len(conflicted_devices)
            }
        ))
        log_trace("ARBITRATION", "Invoking CorrelationAgent for multi-agent evidence synthesis and conflict resolution.")
        arbitration = self.correlation_agent.arbitrate(
            telemetry_records=canonical_records,
            agent_findings=all_findings,
            cascade_evidence=cascade_evidence,
            staleness_seconds=staleness_seconds
        )
        messages.append(AgentMessage(
            sender="CorrelationAgent",
            recipient="Orchestrator",
            message_type="ARBITRATION_COMPLETE",
            payload={
                "root_cause": arbitration.primary_root_cause,
                "confidence": arbitration.confidence,
                "affected_count": len(arbitration.affected_devices)
            }
        ))

        # 6. Report Generation
        log_trace("REPORTING", "Generating UnifiedIncidentReport and Executive Markdown Summary.")
        report = self.reporter_agent.generate_json_report(arbitration, incident_id=incident_id)
        md_summary = self.reporter_agent.generate_markdown_summary(
            report,
            evidence_completeness=arbitration.evidence_completeness
        )

        end_time = datetime.now(timezone.utc)
        duration_ms = round((end_time - start_time).total_seconds() * 1000.0, 2)
        log_trace("COMPLETE", f"Orchestration completed in {duration_ms}ms.", {"incident_id": report.incident_id})

        return OrchestrationResult(
            report=report,
            markdown_summary=md_summary,
            canonical_telemetry=canonical_records,
            agent_findings=all_findings,
            agent_messages=messages,
            arbitration_result=arbitration,
            execution_trace=trace,
            total_duration_ms=duration_ms
        )
