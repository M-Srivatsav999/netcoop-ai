"""InfrastructureAgent: Analyzes node hardware and interface health (CPU, Memory, Queue Drops, Interface Errors)."""

from __future__ import annotations

from typing import List

from core.rules import DiagnosticRuleEngine, MetricThresholds
from protocol.models import (
    AgentFinding,
    CanonicalTelemetry,
    EvidenceItem,
    EvidencePolarity,
    HypothesisType,
    SeverityLevel,
)


class InfrastructureAgent:
    """Specialized agent responsible for hardware metrics, resource saturation, and interface errors."""

    def __init__(self, thresholds: MetricThresholds | None = None) -> None:
        self.rules = DiagnosticRuleEngine(thresholds)

    def analyze(self, telemetry: CanonicalTelemetry) -> AgentFinding:
        """Evaluate device infrastructure health and generate structured evidence."""
        m = telemetry.metrics
        dev = telemetry.device_id
        evidence: List[EvidenceItem] = []
        suspected_issues: List[str] = []
        missing_metrics: List[str] = []

        # 1. CPU Utilization
        cpu_sev = self.rules.classify_cpu(m.cpu_pct)
        if m.cpu_pct is None:
            missing_metrics.append("cpu_pct")
        elif cpu_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("HIGH_CPU")
            weight = 0.90 if cpu_sev == SeverityLevel.CRITICAL else 0.50
            evidence.append(EvidenceItem(
                evidence_id=f"INFRA-CPU-{dev}",
                source_agent="InfrastructureAgent",
                device_id=dev,
                metric_name="cpu_pct",
                observed_value=m.cpu_pct,
                threshold_reference=f"warn={self.rules.thresholds.cpu_warn_pct}%, crit={self.rules.thresholds.cpu_crit_pct}%",
                severity=cpu_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.RESOURCE_EXHAUSTION.value,
                weight=weight,
                description=f"Control plane processor utilization at {m.cpu_pct}% on {dev}."
            ))

        # 2. Memory Utilization
        mem_sev = self.rules.classify_memory(m.memory_pct)
        if m.memory_pct is None:
            missing_metrics.append("memory_pct")
        elif mem_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("HIGH_MEMORY")
            weight = 0.90 if mem_sev == SeverityLevel.CRITICAL else 0.50
            evidence.append(EvidenceItem(
                evidence_id=f"INFRA-MEM-{dev}",
                source_agent="InfrastructureAgent",
                device_id=dev,
                metric_name="memory_pct",
                observed_value=m.memory_pct,
                threshold_reference=f"warn={self.rules.thresholds.memory_warn_pct}%, crit={self.rules.thresholds.memory_crit_pct}%",
                severity=mem_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.RESOURCE_EXHAUSTION.value,
                weight=weight,
                description=f"RAM allocation exhaustion: {m.memory_pct}% on {dev}."
            ))

        # 3. Queue Drops (Buffer Exhaustion)
        drop_sev = self.rules.classify_queue_drops(m.queue_drops)
        if m.queue_drops is None:
            missing_metrics.append("queue_drops")
        elif drop_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("QUEUE_DROPS")
            weight = 0.85 if drop_sev == SeverityLevel.CRITICAL else 0.45
            # Queue drops can indicate either congestion or resource starvation
            evidence.append(EvidenceItem(
                evidence_id=f"INFRA-DROPS-{dev}",
                source_agent="InfrastructureAgent",
                device_id=dev,
                metric_name="queue_drops",
                observed_value=m.queue_drops,
                threshold_reference=f"warn={self.rules.thresholds.queue_drops_warn}, crit={self.rules.thresholds.queue_drops_crit}",
                severity=drop_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=weight,
                description=f"Switch egress buffer overflow causing {m.queue_drops} tail drops on {dev}."
            ))

        # 4. Interface Physical Errors (CRC/FCS/Alignment)
        err_sev = self.rules.classify_interface_errors(m.interface_errors)
        if m.interface_errors is None:
            missing_metrics.append("interface_errors")
        elif err_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("INTERFACE_ERRORS")
            weight = 0.95 if err_sev == SeverityLevel.CRITICAL else 0.60
            evidence.append(EvidenceItem(
                evidence_id=f"INFRA-ERR-{dev}",
                source_agent="InfrastructureAgent",
                device_id=dev,
                metric_name="interface_errors",
                observed_value=m.interface_errors,
                threshold_reference=f"warn={self.rules.thresholds.interface_errors_warn}, crit={self.rules.thresholds.interface_errors_crit}",
                severity=err_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.HARDWARE_FAILURE.value,
                weight=weight,
                description=f"Physical layer errors ({m.interface_errors}) detected on switchport interface for {dev}."
            ))

        # Healthy verification
        severities = [cpu_sev, mem_sev, drop_sev, err_sev]
        valid_sevs = [s for s in severities if s != SeverityLevel.UNKNOWN]

        if valid_sevs and all(s == SeverityLevel.HEALTHY for s in valid_sevs):
            overall_severity = SeverityLevel.HEALTHY
            evidence.append(EvidenceItem(
                evidence_id=f"INFRA-HEALTHY-{dev}",
                source_agent="InfrastructureAgent",
                device_id=dev,
                metric_name="hardware_health",
                observed_value={"cpu": m.cpu_pct, "errors": m.interface_errors},
                threshold_reference="All hardware KPIs within nominal bounds",
                severity=SeverityLevel.HEALTHY,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.NORMAL_OPERATION.value,
                weight=0.85,
                description=f"Hardware and line interface health on {dev} is fully nominal."
            ))
        elif SeverityLevel.CRITICAL in severities:
            overall_severity = SeverityLevel.CRITICAL
        elif SeverityLevel.WARNING in severities:
            overall_severity = SeverityLevel.WARNING
        else:
            overall_severity = SeverityLevel.UNKNOWN

        return AgentFinding(
            agent_name="InfrastructureAgent",
            device_id=dev,
            overall_severity=overall_severity,
            suspected_issues=suspected_issues,
            evidence=evidence,
            missing_metrics=missing_metrics,
            notes=f"Evaluated {len(valid_sevs)} infrastructure metrics ({len(missing_metrics)} missing)."
        )

    def analyze_batch(self, telemetry_batch: List[CanonicalTelemetry]) -> List[AgentFinding]:
        """Analyze a collection of canonical telemetry records."""
        return [self.analyze(record) for record in telemetry_batch]
