"""NetCoop AI Active Diagnostic Investigation & Safe Operational Remediation Engine.

Implements mathematically rigorous Shannon Information Gain:
    IG(S, C) = H(S) - H(S | C)
to rank follow-up diagnostic measurements across competing hypotheses,
maps commands to target device platforms (Cisco Catalyst IOS XE, Catalyst 9800 WLC, Linux Services),
and structures human-authorized remediation playbooks with explicit verification and rollback.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from protocol.models import HypothesisType


class DiagnosticCheck(BaseModel):
    """An active follow-up measurement recommended to disambiguate competing causes."""
    check_id: str = Field(default_factory=lambda: f"CHK-{uuid.uuid4().hex[:6].upper()}")
    target_device: str
    target_platform: str = Field(description="Cisco Catalyst IOS XE | Cisco 9800 WLC | Linux Core Services")
    command_or_metric: str
    rationale: str
    information_gain_bits: float = Field(ge=0.0, description="Measured Shannon Information Gain in bits")
    diagnostic_value: float = Field(ge=0.0, le=1.0, description="Normalized information gain [0.0, 1.0]")
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
    """Computes true Shannon Information Gain and generates platform-aware safe operational plans."""

    @classmethod
    def calculate_shannon_entropy(cls, probabilities: List[float]) -> float:
        """Calculate Shannon entropy H(S) = -sum(p * log2(p))."""
        ent = 0.0
        for p in probabilities:
            if p > 1e-9:
                ent -= (p * math.log2(p))
        return ent

    @classmethod
    def calculate_information_gain(
        cls,
        prior_probs: Dict[str, float],
        partition_a: List[str],
        partition_b: List[str]
    ) -> Tuple[float, float]:
        """Compute true Shannon Information Gain for a binary diagnostic test.
        
        Returns:
            (information_gain_bits, normalized_gain_ratio)
        """
        total_p = sum(prior_probs.values())
        if total_p <= 0.0:
            return 0.0, 0.0

        # Normalize prior probabilities
        norm_p = {k: v / total_p for k, v in prior_probs.items()}
        h_prior = cls.calculate_shannon_entropy(list(norm_p.values()))
        if h_prior <= 1e-9:
            return 0.0, 0.0

        p_a = sum(norm_p.get(k, 0.0) for k in partition_a)
        p_b = sum(norm_p.get(k, 0.0) for k in partition_b)

        # Conditional entropy given test outcome
        h_given_a = 0.0
        if p_a > 1e-9:
            cond_a = [norm_p.get(k, 0.0) / p_a for k in partition_a]
            h_given_a = cls.calculate_shannon_entropy(cond_a)

        h_given_b = 0.0
        if p_b > 1e-9:
            cond_b = [norm_p.get(k, 0.0) / p_b for k in partition_b]
            h_given_b = cls.calculate_shannon_entropy(cond_b)

        h_conditional = (p_a * h_given_a) + (p_b * h_given_b)
        ig_bits = max(0.0, h_prior - h_conditional)
        norm_gain = min(1.0, ig_bits / h_prior) if h_prior > 0 else 0.0

        return round(ig_bits, 4), round(norm_gain, 3)

    @classmethod
    def generate_investigation_plan(
        cls,
        root_cause: str,
        competing_hypotheses: List[str],
        affected_devices: List[str]
    ) -> List[DiagnosticCheck]:
        """Generate active diagnostic checks with true Shannon Information Gain."""
        checks: List[DiagnosticCheck] = []
        target = affected_devices[0] if affected_devices else "IITBBS-CORE-SW-01"

        # Determine target platform
        platform = "Cisco Catalyst IOS XE"
        if "AP-" in target or "WIFI" in target:
            platform = "Cisco Catalyst 9800 WLC"
        elif "SRV-" in target or "SERVER" in target:
            platform = "Linux Core Services"

        # Construct candidate hypothesis probability distribution
        # Derive prior probabilities directly from empirical hypothesis confidences
        raw_priors: Dict[str, float] = {root_cause: 1.0}
        for h in competing_hypotheses:
            if isinstance(h, dict):
                h_name = str(h.get("hypothesis", ""))
                conf = float(h.get("confidence", 0.35))
                if h_name and h_name != root_cause:
                    raw_priors[h_name] = max(0.05, conf)
            else:
                h_name = str(h)
                if h_name and h_name != root_cause:
                    raw_priors[h_name] = 0.30

        all_candidates = list(raw_priors.keys())
        if len(all_candidates) == 1:
            raw_priors["NORMAL_OPERATION"] = 0.20
            all_candidates.append("NORMAL_OPERATION")

        total_weight = sum(raw_priors.values())
        prior_probs: Dict[str, float] = {k: v / total_weight for k, v in raw_priors.items()}
        parsed_competing = [c for c in all_candidates if c != root_cause]

        # 1. Congestion vs Hardware Physical Check
        if root_cause == HypothesisType.LINK_CONGESTION.value or "HARDWARE_FAILURE" in parsed_competing:
            part_a = [HypothesisType.HARDWARE_FAILURE.value]
            part_b = [c for c in all_candidates if c not in part_a]
            ig_bits, norm_val = cls.calculate_information_gain(prior_probs, partition_a=part_a, partition_b=part_b)
            cmd = "show interface <port> counters errors | include CRC" if "WLC" not in platform else "show ap auto-rf stats"
            checks.append(DiagnosticCheck(
                target_device=target,
                target_platform=platform,
                command_or_metric=cmd,
                rationale="Audit hardware FCS/CRC error trends over 5-minute window to disambiguate physical transceiver defect from bufferbloat.",
                information_gain_bits=ig_bits,
                diagnostic_value=round(norm_val, 3),
                operational_cost="LOW",
                distinguishes_between=["HARDWARE_FAILURE", "LINK_CONGESTION"]
            ))

            part_a_q = [HypothesisType.LINK_CONGESTION.value]
            part_b_q = [c for c in all_candidates if c not in part_a_q]
            ig_bits_q, norm_val_q = cls.calculate_information_gain(prior_probs, partition_a=part_a_q, partition_b=part_b_q)
            checks.append(DiagnosticCheck(
                target_device=target,
                target_platform=platform,
                command_or_metric="show platform hardware fed switch active qos queue stats",
                rationale="Inspect egress ASIC buffer queue utilization and tail-drop counters to measure active queue congestion.",
                information_gain_bits=ig_bits_q,
                diagnostic_value=round(norm_val_q, 3),
                operational_cost="LOW",
                distinguishes_between=["LINK_CONGESTION", "HARDWARE_FAILURE"]
            ))

        # 2. Hardware Failure DOM Optical Check
        if root_cause == HypothesisType.HARDWARE_FAILURE.value:
            part_a = [HypothesisType.HARDWARE_FAILURE.value]
            part_b = [c for c in all_candidates if c not in part_a]
            ig_bits, norm_val = cls.calculate_information_gain(prior_probs, partition_a=part_a, partition_b=part_b)
            checks.append(DiagnosticCheck(
                target_device=target,
                target_platform=platform,
                command_or_metric="show interfaces transceiver detail",
                rationale="Query Digital Optical Monitoring (DOM) Rx/Tx optical power dBm levels to verify fiber patch integrity.",
                information_gain_bits=ig_bits,
                diagnostic_value=round(norm_val, 3),
                operational_cost="LOW",
                distinguishes_between=["HARDWARE_FAILURE", "LINK_CONGESTION"]
            ))

        # 3. Wireless RF Attenuation Check
        if root_cause == HypothesisType.WEAK_WIFI.value or "WEAK_WIFI" in parsed_competing:
            part_a = [HypothesisType.WEAK_WIFI.value]
            part_b = [c for c in all_candidates if c not in part_a]
            ig_bits, norm_val = cls.calculate_information_gain(prior_probs, partition_a=part_a, partition_b=part_b)
            checks.append(DiagnosticCheck(
                target_device=target,
                target_platform="Cisco Catalyst 9800 WLC",
                command_or_metric="show wireless client mac <client> detail | include SNR|RSSI",
                rationale="Measure client RF Signal-to-Noise Ratio (SNR), negotiation MCS index, and retransmissions.",
                information_gain_bits=ig_bits,
                diagnostic_value=round(norm_val, 3),
                operational_cost="LOW",
                distinguishes_between=["WEAK_WIFI", "LINK_CONGESTION"]
            ))

        # 4. Centralized DNS/DHCP Service Outage Check
        if root_cause == HypothesisType.DNS_DHCP_FAILURE.value or "DNS_DHCP_FAILURE" in parsed_competing:
            part_a = [HypothesisType.DNS_DHCP_FAILURE.value]
            part_b = [c for c in all_candidates if c not in part_a]
            ig_bits, norm_val = cls.calculate_information_gain(prior_probs, partition_a=part_a, partition_b=part_b)
            checks.append(DiagnosticCheck(
                target_device=target,
                target_platform="Linux Core Services",
                command_or_metric="dig @10.0.10.1 www.iitbbs.ac.in +time=2 +tries=1",
                rationale="Probe DNS authoritative server directly to determine if outage is application socket deadlock vs transport.",
                information_gain_bits=ig_bits,
                diagnostic_value=round(norm_val, 3),
                operational_cost="LOW",
                distinguishes_between=["DNS_DHCP_FAILURE", "LINK_CONGESTION"]
            ))

        # Sort checks by information gain bits descending
        checks.sort(key=lambda x: x.information_gain_bits, reverse=True)
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
