"""NetCoop AI Active Diagnostic Investigation & Safe Operational Remediation Engine.

Implements active diagnostic next-step ranking (information gain vs cost),
competing root-cause disambiguation, and human-in-the-loop operational playbooks
with explicit verification and rollback procedures.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from protocol.models import HypothesisType


class DiagnosticCheck(BaseModel):
    """An active follow-up measurement recommended to disambiguate competing causes."""
    check_id: str = Field(default_factory=lambda: f"CHK-{uuid.uuid4().hex[:6].upper()}")
    target_device: str
    command_or_metric: str
    rationale: str
    diagnostic_value: float = Field(ge=0.0, le=1.0, description="Expected information gain")
    operational_cost: str = Field(description="LOW | MEDIUM | HIGH")
    distinguishes_between: List[str] = Field(default_factory=list)


class OperationalAction(BaseModel):
    """Safe, human-authorized remediation action with verification and rollback."""
    action_id: str = Field(default_factory=lambda: f"ACT-{uuid.uuid4().hex[:6].upper()}")
    priority: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    severity: str = Field(description="HIGH | MEDIUM | LOW")
    target_device: str
    recommended_action: str
    reason: str
    expected_impact: str
    operational_risk: str = Field(description="LOW | MEDIUM | HIGH")
    requires_approval: bool = True
    verification_procedure: str
    rollback_procedure: str


class InvestigationEngine:
    """Ranks active follow-up investigations and formats safe operational remediation plans."""

    @classmethod
    def generate_investigation_plan(
        cls,
        root_cause: str,
        competing_hypotheses: List[str],
        affected_devices: List[str]
    ) -> List[DiagnosticCheck]:
        """Generate ranked active diagnostic checks to disambiguate competing root causes."""
        checks: List[DiagnosticCheck] = []
        target = affected_devices[0] if affected_devices else "UNKNOWN"

        if root_cause == HypothesisType.LINK_CONGESTION.value or "HARDWARE_FAILURE" in competing_hypotheses:
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show interface <port> counters errors | include CRC",
                rationale="Audit hardware FCS/CRC error trends over 5-minute window to rule out physical transceiver degradation.",
                diagnostic_value=0.95,
                operational_cost="LOW",
                distinguishes_between=["LINK_CONGESTION", "HARDWARE_FAILURE"]
            ))
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show platform hardware fed switch active qos queue stats",
                rationale="Inspect egress ASIC buffer queue utilization and tail-drop counters to confirm bufferbloat.",
                diagnostic_value=0.90,
                operational_cost="LOW",
                distinguishes_between=["LINK_CONGESTION", "HARDWARE_FAILURE"]
            ))
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show flow monitor campus-flow cache",
                rationale="Sample top-talker flows traversing the congested link to identify bandwidth hogging applications.",
                diagnostic_value=0.82,
                operational_cost="MEDIUM",
                distinguishes_between=["LINK_CONGESTION", "NORMAL_OPERATION"]
            ))

        elif root_cause == HypothesisType.HARDWARE_FAILURE.value:
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show interfaces transceiver detail",
                rationale="Query Digital Optical Monitoring (DOM) Rx/Tx optical power dBm levels to verify cable/patch integrity.",
                diagnostic_value=0.96,
                operational_cost="LOW",
                distinguishes_between=["HARDWARE_FAILURE", "LINK_CONGESTION"]
            ))
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="diagnostic start switch 1 test PortAsicMem",
                rationale="Execute non-disruptive online diagnostic POST/BIST routines across switch ASIC backplane.",
                diagnostic_value=0.88,
                operational_cost="MEDIUM",
                distinguishes_between=["HARDWARE_FAILURE", "RESOURCE_EXHAUSTION"]
            ))

        elif root_cause == HypothesisType.WEAK_WIFI.value:
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show wireless client mac <client> detail",
                rationale="Inspect RF Signal-to-Noise Ratio (SNR), retransmission counts, and negotiation data rate MCS index.",
                diagnostic_value=0.92,
                operational_cost="LOW",
                distinguishes_between=["WEAK_WIFI", "LINK_CONGESTION"]
            ))
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show ap auto-rf 802.11a/n summary",
                rationale="Verify Radio Resource Management (RRM) Transmit Power Control (TPC) and Dynamic Channel Assignment (DCA).",
                diagnostic_value=0.85,
                operational_cost="LOW",
                distinguishes_between=["WEAK_WIFI", "HARDWARE_FAILURE"]
            ))

        elif root_cause == HypothesisType.DNS_DHCP_FAILURE.value:
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="dig @10.0.10.1 www.iitbbs.ac.in +time=2 +tries=1",
                rationale="Measure exact DNS resolver response latency and check whether authorative SOA responses arrive.",
                diagnostic_value=0.94,
                operational_cost="LOW",
                distinguishes_between=["DNS_DHCP_FAILURE", "LINK_CONGESTION"]
            ))
            checks.append(DiagnosticCheck(
                target_device=target,
                command_or_metric="show ip dhcp pool binding / systemctl status isc-dhcp-server",
                rationale="Verify DHCP address pool exhaustion and service daemon socket health.",
                diagnostic_value=0.91,
                operational_cost="LOW",
                distinguishes_between=["DNS_DHCP_FAILURE", "HARDWARE_FAILURE"]
            ))

        # Sort checks by diagnostic value descending
        checks.sort(key=lambda x: x.diagnostic_value, reverse=True)
        return checks

    @classmethod
    def generate_safe_remediation_actions(
        cls,
        root_cause: str,
        affected_devices: List[str]
    ) -> List[OperationalAction]:
        """Generate structured operational remediation playbooks with strict safety guarantees."""
        actions: List[OperationalAction] = []
        target = affected_devices[0] if affected_devices else "CAMPUS-SW"

        if root_cause == HypothesisType.LINK_CONGESTION.value:
            actions.append(OperationalAction(
                priority="HIGH",
                severity="MEDIUM",
                target_device=target,
                recommended_action="Apply rate-limiting policy and dynamically prioritize QoS interactive DSCP traffic.",
                reason="Buffer queue drops and high link utilization causing packet loss across link.",
                expected_impact="Alleviates buffer exhaustion, drops latency back to < 30ms, and eliminates queue packet loss.",
                operational_risk="LOW",
                requires_approval=True,
                verification_procedure="Verify queue drop counter stops incrementing with 'show platform hardware fed qos queue stats'.",
                rollback_procedure="Revert interface QoS service-policy to default policy-map profile."
            ))
            actions.append(OperationalAction(
                priority="MEDIUM",
                severity="LOW",
                target_device=target,
                recommended_action="Re-route non-critical bulk transfer VLANs to redundant distribution uplink.",
                reason="Load-balance congested distribution trunk link.",
                expected_impact="Reduces link utilization from >90% to nominal 45%.",
                operational_risk="MEDIUM",
                requires_approval=True,
                verification_procedure="Query link utilization on secondary trunk to verify traffic distribution.",
                rollback_procedure="Restore Spanning Tree / LACP trunk port-channel load-balancing weights."
            ))

        elif root_cause == HypothesisType.HARDWARE_FAILURE.value:
            actions.append(OperationalAction(
                priority="CRITICAL",
                severity="HIGH",
                target_device=target,
                recommended_action="Dispatch field technician for physical optical cable swap and SFP+ transceiver replacement.",
                reason="Active FCS/CRC physical layer framing errors degrading link integrity.",
                expected_impact="Eliminates physical bit errors and stops packet drops completely.",
                operational_risk="MEDIUM",
                requires_approval=True,
                verification_procedure="Monitor interface CRC counter across 5-minute interval to ensure 0 new errors.",
                rollback_procedure="Reconnect prior certified port or shift patch lead to redundant standby port."
            ))

        elif root_cause == HypothesisType.WEAK_WIFI.value:
            actions.append(OperationalAction(
                priority="HIGH",
                severity="MEDIUM",
                target_device=target,
                recommended_action="Trigger RRM (Radio Resource Management) Tx power increase (+3 dBm) and enable band-steering.",
                reason="Client RSSI < -70 dBm indicating weak RF signal coverage boundary.",
                expected_impact="Boosts signal coverage by 6 dB and steers capable clients to 5GHz spectrum.",
                operational_risk="LOW",
                requires_approval=True,
                verification_procedure="Check client RSSI in WLC controller to verify signal improves to > -65 dBm.",
                rollback_procedure="Restore AP radio transmit power to auto-RRM baseline."
            ))

        elif root_cause == HypothesisType.DNS_DHCP_FAILURE.value:
            actions.append(OperationalAction(
                priority="CRITICAL",
                severity="HIGH",
                target_device=target,
                recommended_action="Restart named/bind9 DNS service daemon and verify authoritative zone reload.",
                reason="Clients experiencing resolution timeouts while transport network remains healthy.",
                expected_impact="Restores campus name resolution latency to < 10ms.",
                operational_risk="LOW",
                requires_approval=True,
                verification_procedure="Execute local dig query against 127.0.0.1 and verify 0% SERVFAIL responses.",
                rollback_procedure="Roll back DNS zone configuration file to last known git version commit."
            ))

        return actions
