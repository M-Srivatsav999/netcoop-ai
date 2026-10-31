"""TelemetryAgent: Analyzes transport and network KPIs (latency, jitter, packet loss, throughput)."""

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


class TelemetryAgent:
    """Specialized agent responsible for end-to-end transport and network performance analysis."""

    def __init__(self, thresholds: MetricThresholds | None = None) -> None:
        self.rules = DiagnosticRuleEngine(thresholds)

    def analyze(self, telemetry: CanonicalTelemetry) -> AgentFinding:
        """Evaluate network transport KPIs and generate structured evidence."""
        m = telemetry.metrics
        dev = telemetry.device_id
        evidence: List[EvidenceItem] = []
        suspected_issues: List[str] = []
        missing_metrics: List[str] = []

        # 1. Latency Analysis
        lat_sev = self.rules.classify_latency(m.latency_ms)
        if m.latency_ms is None:
            missing_metrics.append("latency_ms")
        elif lat_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("HIGH_LATENCY")
            weight = 0.85 if lat_sev == SeverityLevel.CRITICAL else 0.50
            evidence.append(EvidenceItem(
                evidence_id=f"TEL-LAT-{dev}",
                source_agent="TelemetryAgent",
                device_id=dev,
                metric_name="latency_ms",
                observed_value=m.latency_ms,
                threshold_reference=f"warn={self.rules.thresholds.latency_warn_ms}ms, crit={self.rules.thresholds.latency_crit_ms}ms",
                severity=lat_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=weight,
                description=f"Elevated round-trip latency of {m.latency_ms}ms on {dev}."
            ))

        # 2. Jitter Analysis
        jit_sev = self.rules.classify_jitter(m.jitter_ms)
        if m.jitter_ms is None:
            missing_metrics.append("jitter_ms")
        elif jit_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("HIGH_JITTER")
            weight = 0.70 if jit_sev == SeverityLevel.CRITICAL else 0.40
            evidence.append(EvidenceItem(
                evidence_id=f"TEL-JIT-{dev}",
                source_agent="TelemetryAgent",
                device_id=dev,
                metric_name="jitter_ms",
                observed_value=m.jitter_ms,
                threshold_reference=f"warn={self.rules.thresholds.jitter_warn_ms}ms, crit={self.rules.thresholds.jitter_crit_ms}ms",
                severity=jit_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=weight,
                description=f"Packet transit time variance (jitter) elevated to {m.jitter_ms}ms on {dev}."
            ))

        # 3. Packet Loss Analysis
        loss_sev = self.rules.classify_packet_loss(m.packet_loss_pct)
        if m.packet_loss_pct is None:
            missing_metrics.append("packet_loss_pct")
        elif loss_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("PACKET_LOSS")
            weight = 0.95 if loss_sev == SeverityLevel.CRITICAL else 0.60
            evidence.append(EvidenceItem(
                evidence_id=f"TEL-LOSS-{dev}",
                source_agent="TelemetryAgent",
                device_id=dev,
                metric_name="packet_loss_pct",
                observed_value=m.packet_loss_pct,
                threshold_reference=f"warn={self.rules.thresholds.loss_warn_pct}%, crit={self.rules.thresholds.loss_crit_pct}%",
                severity=loss_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=weight,
                description=f"Packet loss rate at {m.packet_loss_pct}% on {dev}."
            ))

        # 4. Throughput Analysis
        tp_sev = self.rules.classify_throughput(m.throughput_mbps)
        if m.throughput_mbps is None and m.link_utilization_pct is None:
            missing_metrics.append("throughput_mbps")
        elif tp_sev in (SeverityLevel.WARNING, SeverityLevel.CRITICAL):
            suspected_issues.append("DEGRADED_THROUGHPUT")
            weight = 0.80 if tp_sev == SeverityLevel.CRITICAL else 0.45
            evidence.append(EvidenceItem(
                evidence_id=f"TEL-TP-{dev}",
                source_agent="TelemetryAgent",
                device_id=dev,
                metric_name="throughput_mbps",
                observed_value=m.throughput_mbps,
                threshold_reference=f"warn<={self.rules.thresholds.throughput_warn_mbps}Mbps, crit<={self.rules.thresholds.throughput_crit_mbps}Mbps",
                severity=tp_sev,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=weight,
                description=f"Throughput degraded to {m.throughput_mbps} Mbps on {dev}."
            ))

        # 5. Link Utilization Analysis
        lu_sev = SeverityLevel.UNKNOWN
        if m.link_utilization_pct is not None:
            if m.link_utilization_pct >= self.rules.thresholds.link_util_crit_pct:
                lu_sev = SeverityLevel.CRITICAL
                suspected_issues.append("SATURATED_LINK")
                evidence.append(EvidenceItem(
                    evidence_id=f"TEL-LINKUTIL-{dev}",
                    source_agent="TelemetryAgent",
                    device_id=dev,
                    metric_name="link_utilization_pct",
                    observed_value=m.link_utilization_pct,
                    threshold_reference=f">={self.rules.thresholds.link_util_crit_pct}%",
                    severity=lu_sev,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                    weight=0.90,
                    description=f"Link utilization critically saturated at {m.link_utilization_pct}% on {dev}."
                ))
            elif m.link_utilization_pct >= self.rules.thresholds.link_util_warn_pct:
                lu_sev = SeverityLevel.WARNING
                suspected_issues.append("HIGH_LINK_UTILIZATION")
                evidence.append(EvidenceItem(
                    evidence_id=f"TEL-LINKUTIL-{dev}",
                    source_agent="TelemetryAgent",
                    device_id=dev,
                    metric_name="link_utilization_pct",
                    observed_value=m.link_utilization_pct,
                    threshold_reference=f">={self.rules.thresholds.link_util_warn_pct}%",
                    severity=lu_sev,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                    weight=0.65,
                    description=f"Elevated link utilization at {m.link_utilization_pct}% on {dev}."
                ))
            else:
                lu_sev = SeverityLevel.HEALTHY

        # Nominal / Healthy Verification
        severities = [lat_sev, jit_sev, loss_sev, tp_sev, lu_sev]
        valid_sevs = [s for s in severities if s != SeverityLevel.UNKNOWN]

        if valid_sevs and all(s == SeverityLevel.HEALTHY for s in valid_sevs):
            overall_severity = SeverityLevel.HEALTHY
            evidence.append(EvidenceItem(
                evidence_id=f"TEL-HEALTHY-{dev}",
                source_agent="TelemetryAgent",
                device_id=dev,
                metric_name="network_kpis",
                observed_value={"loss": m.packet_loss_pct, "lat": m.latency_ms},
                threshold_reference="All KPIs within nominal baseline",
                severity=SeverityLevel.HEALTHY,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.NORMAL_OPERATION.value,
                weight=0.85,
                description=f"All monitored transport KPIs on {dev} are within healthy baselines."
            ))
        elif SeverityLevel.CRITICAL in severities:
            overall_severity = SeverityLevel.CRITICAL
        elif SeverityLevel.WARNING in severities:
            overall_severity = SeverityLevel.WARNING
        else:
            overall_severity = SeverityLevel.UNKNOWN

        return AgentFinding(
            agent_name="TelemetryAgent",
            device_id=dev,
            overall_severity=overall_severity,
            suspected_issues=suspected_issues,
            evidence=evidence,
            missing_metrics=missing_metrics,
            notes=f"Evaluated {len(valid_sevs)} valid network metrics ({len(missing_metrics)} missing)."
        )

    def analyze_batch(self, telemetry_batch: List[CanonicalTelemetry]) -> List[AgentFinding]:
        """Analyze a collection of canonical telemetry records."""
        return [self.analyze(record) for record in telemetry_batch]
