"""Automated Remediation Simulator.

Simulates corrective engineering actions for diagnosed root causes in a safe sandbox/dry-run environment,
projecting before/after network KPIs without touching live infrastructure (Page 3 of NetCoop AI spec).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from protocol.models import CanonicalTelemetry, HypothesisType


class RemediationAction(BaseModel):
    """Specific simulated corrective engineering step."""
    action_id: str
    target_device: str
    action_type: str
    simulated_cli_command: str
    rationale: str
    projected_recovery: Dict[str, Any]
    safety_level: str = "SAFE_NON_DESTRUCTIVE"
    operator_approval_required: bool = True


class SimulationResult(BaseModel):
    """Complete dry-run remediation simulation plan."""
    simulation_id: str
    suspected_root_cause: str
    affected_devices: List[str]
    actions: List[RemediationAction]
    projected_network_status: str
    blast_radius_contained: bool
    risk_level: str
    human_in_the_loop_status: str
    dry_run_disclaimer: str = (
        "Dry-run simulation only. In compliance with NetCoop AI requirements, "
        "no commands are dispatched to live production infrastructure without explicit authorization."
    )


class RemediationSimulator:
    """Deterministic simulation engine generating targeted corrective playbooks with KPI projections."""

    @classmethod
    def simulate_remediation(
        cls,
        root_cause: str,
        affected_devices: List[str],
        telemetry_records: Optional[List[CanonicalTelemetry]] = None
    ) -> SimulationResult:
        """Generate a simulated remediation execution plan with before-and-after KPI projections."""
        sim_id = f"SIM-{abs(hash(root_cause + ''.join(affected_devices))) % 100000:05d}"
        actions: List[RemediationAction] = []
        projected_status = "STABILIZED"
        risk = "LOW"

        dev_list = affected_devices if affected_devices else ["CAMPUS_GATEWAY"]

        for idx, dev in enumerate(dev_list, 1):
            if root_cause == HypothesisType.LINK_CONGESTION.value:
                actions.append(RemediationAction(
                    action_id=f"ACT-QOS-{idx}",
                    target_device=dev,
                    action_type="APPLY_DSCP_QOS_POLICING",
                    simulated_cli_command=f"switch(config-if)# qos policy rate-limit 800mbps dscp-priority ef burst 64k",
                    rationale="Throttle non-essential bulk traffic and prioritize interactive voice/video queues to clear bufferbloat.",
                    projected_recovery={
                        "egress_queue_drops": {"before": 145, "projected_after": 0},
                        "round_trip_latency_ms": {"before": 185.0, "projected_after": 18.5},
                        "packet_loss_pct": {"before": 5.2, "projected_after": 0.0}
                    },
                    safety_level="SAFE_NON_DESTRUCTIVE",
                    operator_approval_required=True
                ))
            elif root_cause == HypothesisType.HARDWARE_FAILURE.value:
                actions.append(RemediationAction(
                    action_id=f"ACT-PHY-FAILOVER-{idx}",
                    target_device=dev,
                    action_type="FAILOVER_TO_STANDBY_OPTICAL_UPLINK",
                    simulated_cli_command=f"switch(config-if)# interface Te1/0/2; shutdown; interface Te1/0/3; no shutdown",
                    rationale="Isolate degraded optical transceiver with high CRC errors and migrate uplink traffic to standby redundant pair.",
                    projected_recovery={
                        "interface_crc_errors_rate": {"before": 740, "projected_after": 0},
                        "packet_loss_pct": {"before": 14.2, "projected_after": 0.0}
                    },
                    safety_level="CONTROLLED_FAILOVER",
                    operator_approval_required=True
                ))
                risk = "MEDIUM"
            elif root_cause == HypothesisType.WEAK_WIFI.value:
                actions.append(RemediationAction(
                    action_id=f"ACT-RF-TUNE-{idx}",
                    target_device=dev,
                    action_type="ADJUST_AP_TX_POWER_AND_CHANNEL_WIDTH",
                    simulated_cli_command=f"wlc(config-ap)# tx-power 20dbm; channel-width 40mhz; rrm-rebalance",
                    rationale="Increase transmit power by +4dBm and narrow channel from 80MHz to 40MHz to overcome RF attenuation.",
                    projected_recovery={
                        "signal_strength_rssi_dbm": {"before": -86.5, "projected_after": -62.0},
                        "wi-fi_retransmissions_pct": {"before": 18.2, "projected_after": 1.5},
                        "client_throughput_mbps": {"before": 3.5, "projected_after": 54.0}
                    },
                    safety_level="SAFE_NON_DESTRUCTIVE",
                    operator_approval_required=False
                ))
            elif root_cause == HypothesisType.DNS_DHCP_FAILURE.value:
                actions.append(RemediationAction(
                    action_id=f"ACT-SVC-RESTART-{idx}",
                    target_device=dev,
                    action_type="RESTART_RESOLVER_DAEMON_AND_PURGE_CACHE",
                    simulated_cli_command=f"systemctl restart named.service; unbound-control reload",
                    rationale="Clear memory leak on core resolver daemon and cycle stale connection pools.",
                    projected_recovery={
                        "dns_query_latency_ms": {"before": 2950.0, "projected_after": 6.2},
                        "dhcp_lease_success": {"before": False, "projected_after": True}
                    },
                    safety_level="SAFE_NON_DESTRUCTIVE",
                    operator_approval_required=True
                ))
            elif root_cause == HypothesisType.RESOURCE_EXHAUSTION.value:
                actions.append(RemediationAction(
                    action_id=f"ACT-CPU-RECLAIM-{idx}",
                    target_device=dev,
                    action_type="GRACEFUL_SUPERVISOR_ENGINE_FAILOVER",
                    simulated_cli_command=f"switch# redundancy force-switchover",
                    rationale="Gracefully failover control plane processing to standby supervisor to clear thread lock.",
                    projected_recovery={
                        "cpu_utilization_pct": {"before": 98.5, "projected_after": 24.0},
                        "memory_utilization_pct": {"before": 94.2, "projected_after": 38.0}
                    },
                    safety_level="CONTROLLED_FAILOVER",
                    operator_approval_required=True
                ))
                risk = "MEDIUM"
            else:
                actions.append(RemediationAction(
                    action_id=f"ACT-MONITOR-{idx}",
                    target_device=dev,
                    action_type="ENABLE_HIGH_FREQUENCY_TELEMETRY",
                    simulated_cli_command=f"switch# telemetry ietf subscription 101 encoding proto stream-rate 1s",
                    rationale="Maintain active telemetry stream monitoring for anomaly reoccurrence.",
                    projected_recovery={"status": {"before": "NOMINAL", "projected_after": "NOMINAL"}},
                    safety_level="SAFE_NON_DESTRUCTIVE",
                    operator_approval_required=False
                ))

        return SimulationResult(
            simulation_id=sim_id,
            suspected_root_cause=root_cause,
            affected_devices=affected_devices,
            actions=actions,
            projected_network_status=projected_status,
            blast_radius_contained=True,
            risk_level=risk,
            human_in_the_loop_status="PENDING_OPERATOR_CONFIRMATION"
        )
