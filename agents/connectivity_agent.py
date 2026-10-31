"""ConnectivityAgent: Analyzes campus network topology, upstream dependencies, blast radius, and cascading failures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core.topology import TopologyEngine
from protocol.models import (
    AgentFinding,
    CanonicalTelemetry,
    EvidenceItem,
    EvidencePolarity,
    HypothesisType,
    SeverityLevel,
)


class ConnectivityAgent:
    """Specialized agent responsible for topological dependency analysis and blast-radius evaluation."""

    def __init__(self, topology_engine: TopologyEngine | None = None) -> None:
        self.topology = topology_engine or TopologyEngine()

    def analyze(self, telemetry: CanonicalTelemetry) -> AgentFinding:
        """Analyze topology role and local connectivity indicators for a single device."""
        dev = telemetry.device_id
        m = telemetry.metrics
        evidence: List[EvidenceItem] = []
        suspected_issues: List[str] = []
        missing_metrics: List[str] = []

        is_known = self.topology.is_device_known(dev)
        node = self.topology.get_node(dev)

        if not is_known:
            evidence.append(EvidenceItem(
                evidence_id=f"CONN-UNKNOWN-{dev}",
                source_agent="ConnectivityAgent",
                device_id=dev,
                metric_name="topology_membership",
                observed_value="UNREGISTERED",
                threshold_reference="Device must be registered in campus topology",
                severity=SeverityLevel.INFO,
                polarity=EvidencePolarity.NEUTRAL,
                hypothesis_target=HypothesisType.NORMAL_OPERATION.value,
                weight=0.3,
                description=f"Device {dev} not found in registered topology database; synthesized as {node.type}."
            ))

        # Check for Wi-Fi Signal Strength
        if m.signal_strength_dbm is not None:
            if m.signal_strength_dbm <= -80.0:
                suspected_issues.append("CRITICAL_WEAK_SIGNAL")
                evidence.append(EvidenceItem(
                    evidence_id=f"CONN-SIGNAL-CRIT-{dev}",
                    source_agent="ConnectivityAgent",
                    device_id=dev,
                    metric_name="signal_strength_dbm",
                    observed_value=m.signal_strength_dbm,
                    threshold_reference="<= -80 dBm",
                    severity=SeverityLevel.CRITICAL,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.WEAK_WIFI.value,
                    weight=0.95,
                    description=f"Severe RF signal attenuation ({m.signal_strength_dbm} dBm) at {dev}."
                ))
            elif m.signal_strength_dbm <= -72.0:
                suspected_issues.append("DEGRADED_SIGNAL")
                evidence.append(EvidenceItem(
                    evidence_id=f"CONN-SIGNAL-WARN-{dev}",
                    source_agent="ConnectivityAgent",
                    device_id=dev,
                    metric_name="signal_strength_dbm",
                    observed_value=m.signal_strength_dbm,
                    threshold_reference="<= -72 dBm",
                    severity=SeverityLevel.WARNING,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.WEAK_WIFI.value,
                    weight=0.60,
                    description=f"Degraded Wi-Fi RSSI ({m.signal_strength_dbm} dBm) on {dev}."
                ))
        else:
            if node.type in ("access_point", "end_device"):
                missing_metrics.append("signal_strength_dbm")

        # Check for DNS / DHCP services
        if m.dns_resolution_ms is not None:
            if m.dns_resolution_ms >= 500.0:
                suspected_issues.append("DNS_RESOLUTION_TIMEOUT")
                evidence.append(EvidenceItem(
                    evidence_id=f"CONN-DNS-TIMEOUT-{dev}",
                    source_agent="ConnectivityAgent",
                    device_id=dev,
                    metric_name="dns_resolution_ms",
                    observed_value=m.dns_resolution_ms,
                    threshold_reference=">= 500ms",
                    severity=SeverityLevel.CRITICAL,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.DNS_DHCP_FAILURE.value,
                    weight=0.95,
                    description=f"DNS query latency of {m.dns_resolution_ms}ms indicates resolver failure on {dev}."
                ))
            elif m.dns_resolution_ms >= 100.0:
                suspected_issues.append("DNS_LATENCY_ELEVATED")
                evidence.append(EvidenceItem(
                    evidence_id=f"CONN-DNS-WARN-{dev}",
                    source_agent="ConnectivityAgent",
                    device_id=dev,
                    metric_name="dns_resolution_ms",
                    observed_value=m.dns_resolution_ms,
                    threshold_reference=">= 100ms",
                    severity=SeverityLevel.WARNING,
                    polarity=EvidencePolarity.SUPPORTS,
                    hypothesis_target=HypothesisType.DNS_DHCP_FAILURE.value,
                    weight=0.50,
                    description=f"Elevated DNS query latency of {m.dns_resolution_ms}ms on {dev}."
                ))

        if m.dhcp_lease_success is not None and not m.dhcp_lease_success:
            suspected_issues.append("DHCP_LEASE_FAILURE")
            evidence.append(EvidenceItem(
                evidence_id=f"CONN-DHCP-FAIL-{dev}",
                source_agent="ConnectivityAgent",
                device_id=dev,
                metric_name="dhcp_lease_success",
                observed_value=False,
                threshold_reference="DHCP lease request failed",
                severity=SeverityLevel.CRITICAL,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.DNS_DHCP_FAILURE.value,
                weight=0.95,
                description=f"DHCP client request timed out with no lease granted on {dev}."
            ))

        # Determine overall severity
        if any(e.severity == SeverityLevel.CRITICAL for e in evidence):
            sev = SeverityLevel.CRITICAL
        elif any(e.severity == SeverityLevel.WARNING for e in evidence):
            sev = SeverityLevel.WARNING
        else:
            sev = SeverityLevel.HEALTHY

        return AgentFinding(
            agent_name="ConnectivityAgent",
            device_id=dev,
            overall_severity=sev,
            suspected_issues=suspected_issues,
            evidence=evidence,
            missing_metrics=missing_metrics,
            notes=f"Node type: {node.type}, known={is_known}."
        )

    def analyze_topology_cascade(
        self,
        telemetry_batch: List[CanonicalTelemetry]
    ) -> List[EvidenceItem]:
        """Examine cross-device failure patterns to detect common upstream root causes."""
        cascade_evidence: List[EvidenceItem] = []

        # Find devices showing serious anomalies (loss > 2% or latency > 80ms or errors > 10)
        anomalous_devices: List[str] = []
        for t in telemetry_batch:
            m = t.metrics
            is_anom = (
                (m.packet_loss_pct is not None and m.packet_loss_pct > 2.0) or
                (m.latency_ms is not None and m.latency_ms > 80.0) or
                (m.interface_errors is not None and m.interface_errors > 10)
            )
            if is_anom:
                anomalous_devices.append(t.device_id)

        if len(anomalous_devices) >= 2:
            lca = self.topology.find_common_ancestor(anomalous_devices)
            if lca:
                blast = self.topology.get_blast_radius(lca)
                lca_node = self.topology.get_node(lca)
                
                # If LCA is a switch and multiple children are anomalous
                if lca_node.type in ("core_switch", "dist_switch", "bldg_switch"):
                    cascade_evidence.append(EvidenceItem(
                        evidence_id=f"CONN-CASCADE-{lca}",
                        source_agent="ConnectivityAgent",
                        device_id=lca,
                        metric_name="downstream_anomaly_cluster",
                        observed_value={
                            "common_ancestor": lca,
                            "failing_nodes": anomalous_devices,
                            "blast_radius_count": blast["total_downstream_count"],
                        },
                        threshold_reference=">= 2 failing downstream nodes sharing switch",
                        severity=SeverityLevel.CRITICAL,
                        polarity=EvidencePolarity.SUPPORTS,
                        hypothesis_target=HypothesisType.UPSTREAM_SWITCH_FAILURE.value,
                        weight=0.90,
                        description=(
                            f"Multiple downstream nodes ({', '.join(anomalous_devices[:4])}) failing concurrently. "
                            f"Topology convergence pinpoints upstream switch {lca} ({lca_node.name}) as single point of failure."
                        )
                    ))

        return cascade_evidence
