"""Deterministic diagnostic rules, configurable thresholds, hypothesis definitions,

and actionable recommendation playbooks.
"""

from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field

from protocol.models import HypothesisType, SeverityLevel


class MetricThresholds(BaseModel):
    """Deterministic, configurable thresholds for network and system KPIs."""
    
    # Latency (ms)
    latency_warn_ms: float = 35.0
    latency_crit_ms: float = 100.0

    # Jitter (ms)
    jitter_warn_ms: float = 10.0
    jitter_crit_ms: float = 25.0

    # Packet Loss (%)
    loss_warn_pct: float = 1.0
    loss_crit_pct: float = 5.0

    # Throughput (Mbps)
    throughput_warn_mbps: float = 20.0
    throughput_crit_mbps: float = 5.0

    # Link Utilization (%)
    link_util_warn_pct: float = 70.0
    link_util_crit_pct: float = 90.0

    # CPU Utilization (%)
    cpu_warn_pct: float = 75.0
    cpu_crit_pct: float = 90.0

    # Memory Utilization (%)
    memory_warn_pct: float = 80.0
    memory_crit_pct: float = 92.0

    # Queue Drops (counts)
    queue_drops_warn: int = 1
    queue_drops_crit: int = 50

    # Interface Errors (counts)
    interface_errors_warn: int = 1
    interface_errors_crit: int = 10

    # Signal Strength (dBm)
    signal_warn_dbm: float = -72.0
    signal_crit_dbm: float = -80.0

    # DNS Resolution (ms)
    dns_warn_ms: float = 100.0
    dns_crit_ms: float = 500.0


class DiagnosticRuleEngine:
    """Central repository of diagnostic rules, conflict resolution logic, and recommendation playbooks."""

    def __init__(self, thresholds: MetricThresholds | None = None) -> None:
        self.thresholds = thresholds or MetricThresholds()

    def classify_latency(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.latency_crit_ms:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.latency_warn_ms:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_jitter(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.jitter_crit_ms:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.jitter_warn_ms:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_packet_loss(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.loss_crit_pct:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.loss_warn_pct:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_throughput(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val <= self.thresholds.throughput_crit_mbps:
            return SeverityLevel.CRITICAL
        if val <= self.thresholds.throughput_warn_mbps:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_cpu(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.cpu_crit_pct:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.cpu_warn_pct:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_memory(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.memory_crit_pct:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.memory_warn_pct:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_queue_drops(self, val: int | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.queue_drops_crit:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.queue_drops_warn:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_interface_errors(self, val: int | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.interface_errors_crit:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.interface_errors_warn:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_signal_strength(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        # Signal is negative: e.g. -85 dBm is worse than -60 dBm
        if val <= self.thresholds.signal_crit_dbm:
            return SeverityLevel.CRITICAL
        if val <= self.thresholds.signal_warn_dbm:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    def classify_dns(self, val: float | None) -> SeverityLevel:
        if val is None:
            return SeverityLevel.UNKNOWN
        if val >= self.thresholds.dns_crit_ms:
            return SeverityLevel.CRITICAL
        if val >= self.thresholds.dns_warn_ms:
            return SeverityLevel.WARNING
        return SeverityLevel.HEALTHY

    @staticmethod
    def get_playbook_recommendations(root_cause: str, affected_devices: List[str]) -> List[str]:
        """Provide concrete, actionable engineering steps for the diagnosed root cause."""
        devices_str = ", ".join(affected_devices[:4]) if affected_devices else "affected nodes"
        
        playbooks: Dict[str, List[str]] = {
            HypothesisType.LINK_CONGESTION.value: [
                f"Engage Quality of Service (QoS) rate limiting and DSCP queue prioritization on {devices_str}.",
                "Inspect traffic flow distribution (NetFlow/sFlow) to identify top-talker endpoints or runaway transfer streams.",
                "Verify if link aggregation (LACP) can be provisioned or if traffic should be rerouted to redundant distribution links.",
                "Temporarily throttle non-essential bulk traffic or p2p services across the congested segment."
            ],
            HypothesisType.HARDWARE_FAILURE.value: [
                f"Dispatch field technician to inspect physical cable, transceiver, and optical power levels on {devices_str}.",
                "Review interface FCS, CRC error counters, and runt/giant packet statistics on switch ports.",
                "Execute clean cable swap or migrate uplink to alternate transceiver/port pair.",
                "Verify switch backplane error logs and run self-diagnostic test suite (POST/BIST)."
            ],
            HypothesisType.RESOURCE_EXHAUSTION.value: [
                f"Isolate high-consuming process threads on {devices_str} via administrative CLI.",
                "Inspect memory leak signatures or control plane buffer allocation exhaustion.",
                "Schedule immediate restart of control plane daemon or graceful failover to redundant supervisor module.",
                "Review recent routing table churn (BGP/OSPF flaps) causing CPU spike."
            ],
            HypothesisType.WEAK_WIFI.value: [
                f"Inspect RF environment around {devices_str} for co-channel interference and rogue access points.",
                "Adjust AP transmit power (Tx) and channel width (consider dropping from 80MHz to 40MHz/20MHz) to mitigate interference.",
                "Evaluate client-to-AP density ratio and reposition directional antennas or add supplemental micro-cell AP.",
                "Enforce minimum RSSI threshold to steer fringe clients to neighboring access points."
            ],
            HypothesisType.DNS_DHCP_FAILURE.value: [
                f"Verify operational status of DNS resolver and DHCP daemon on {devices_str}.",
                "Check DHCP lease pool scope utilization for pool exhaustion.",
                "Restart DHCP helper/relay agents on intermediate distribution switches.",
                "Validate upstream DNS forwarder reachability and test local name query response times."
            ],
            HypothesisType.UPSTREAM_SWITCH_FAILURE.value: [
                f"Initiate urgent out-of-band management console check on upstream switch {devices_str}.",
                "Confirm power supply unit (PSU) redundancy status and thermal sensor readings.",
                "Inspect spanning tree protocol (STP) state changes to ensure topology loop or root bridge re-election did not isolate the segment.",
                "Failover traffic to standby distribution switch or redundant link path."
            ],
            HypothesisType.INTEROPERABILITY_SCHEMA_DEFECT.value: [
                "Audit telemetry collection agent configuration on endpoints for schema version mismatch.",
                "Deploy schema validation shim on telemetry ingestion pipeline to enforce standard units.",
                "Update collection daemon to avoid string-encoded numeric metrics and ensure ISO8601 UTC timestamps.",
                "Verify ingestion queue buffer and check for data truncation or field corruption."
            ],
            HypothesisType.NORMAL_OPERATION.value: [
                "No remediation required; all telemetry metrics conform to nominal operating parameters.",
                "Maintain baseline continuous telemetry monitoring.",
                "Keep existing alerting thresholds active."
            ],
            HypothesisType.INSUFFICIENT_EVIDENCE.value: [
                f"Telemetry for {devices_str} is sparse, contradictory, or missing critical indicators.",
                "Deploy targeted synthetic active probes (ICMP ping, HTTP traceroute, SNMP poll) to collect missing KPIs.",
                "Check endpoint telemetry agent connectivity and verify log exporter health.",
                "Re-evaluate diagnosis once at least 70% of standard telemetry metrics are populated."
            ]
        }
        return playbooks.get(root_cause, [
            f"Perform manual triage on {devices_str}.",
            "Inspect syslog and snmp trap logs on affected devices."
        ])
