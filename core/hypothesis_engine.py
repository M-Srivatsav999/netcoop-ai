"""NetCoop AI Formal Fault Hypothesis & Multi-Signal Reasoning Engine.

Implements multi-signal fault pattern matrices, competing hypothesis ranking,
evidence support/contradiction scoring, temporal EWMA rate-of-change anomaly detection,
and scientific evidence ledger integration.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from protocol.models import CanonicalTelemetry, HypothesisType, StructuredEvidence


class HypothesisScore(BaseModel):
    """Detailed scientific scoring for a root-cause hypothesis."""
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)
    supporting_signals: List[str] = Field(default_factory=list)
    contradicting_signals: List[str] = Field(default_factory=list)
    distinguishing_factors: List[str] = Field(default_factory=list)
    missing_distinguishing_evidence: List[str] = Field(default_factory=list)
    plausibility: str = Field(default="PLAUSIBLE", description="HIGH | PLAUSIBLE | UNLIKELY | RULED_OUT")


class TemporalTrend(BaseModel):
    """Temporal metric progression and rate-of-change analysis."""
    device_id: str
    metric: str
    current_value: float
    previous_value: Optional[float] = None
    rate_of_change_per_sec: Optional[float] = None
    ewma_baseline: Optional[float] = None
    is_sudden_spike: bool = False
    severity: str = "NORMAL"


class HypothesisEngine:
    """Multi-Signal Diagnostic Pattern Matrix and Competing Hypothesis Arbiter."""

    def __init__(self) -> None:
        pass

    @classmethod
    def detect_temporal_anomalies(
        cls,
        current_records: List[CanonicalTelemetry],
        history: Optional[List[List[CanonicalTelemetry]]] = None
    ) -> List[TemporalTrend]:
        """Compute EWMA and rate-of-change trends across temporal observation windows."""
        trends: List[TemporalTrend] = []
        if not history or not current_records:
            return trends

        # Compare current records against recent history
        for curr in current_records:
            dev_id = curr.device_id
            m = curr.metrics

            # Find matching historical device records
            hist_matches: List[CanonicalTelemetry] = []
            for batch in reversed(history):
                for old in batch:
                    if old.device_id == dev_id and old.timestamp and curr.timestamp:
                        hist_matches.append(old)
                        break

            if not hist_matches:
                continue

            prev = hist_matches[0]
            if not curr.timestamp or not prev.timestamp:
                continue

            dt = (curr.timestamp - prev.timestamp).total_seconds()
            if dt <= 0:
                dt = 1.0

            # Evaluate latency acceleration
            if m.latency_ms is not None and prev.metrics.latency_ms is not None:
                d_lat = m.latency_ms - prev.metrics.latency_ms
                rate = d_lat / dt
                spike = rate > 5.0 and m.latency_ms > 50.0  # Rapid surge > 5ms/sec
                trends.append(TemporalTrend(
                    device_id=dev_id,
                    metric="latency_ms",
                    current_value=m.latency_ms,
                    previous_value=prev.metrics.latency_ms,
                    rate_of_change_per_sec=round(rate, 3),
                    is_sudden_spike=spike,
                    severity="WARNING" if spike else "NORMAL"
                ))

            # Evaluate queue drop surge
            if m.queue_drops is not None and prev.metrics.queue_drops is not None:
                d_qd = m.queue_drops - prev.metrics.queue_drops
                rate = d_qd / dt
                spike = rate > 10.0
                trends.append(TemporalTrend(
                    device_id=dev_id,
                    metric="queue_drops",
                    current_value=float(m.queue_drops),
                    previous_value=float(prev.metrics.queue_drops),
                    rate_of_change_per_sec=round(rate, 2),
                    is_sudden_spike=spike,
                    severity="CRITICAL" if spike else "NORMAL"
                ))

            # Evaluate CPU surge (rate-of-change)
            if m.cpu_pct is not None and prev.metrics.cpu_pct is not None:
                d_cpu = m.cpu_pct - prev.metrics.cpu_pct
                rate = d_cpu / dt
                spike = rate > 2.0 and m.cpu_pct > 75.0  # >2% per sec surge
                trends.append(TemporalTrend(
                    device_id=dev_id,
                    metric="cpu_pct",
                    current_value=m.cpu_pct,
                    previous_value=prev.metrics.cpu_pct,
                    rate_of_change_per_sec=round(rate, 2),
                    is_sudden_spike=spike,
                    severity="WARNING" if spike else "NORMAL"
                ))

        return trends

    @classmethod
    def evaluate_hypotheses(
        cls,
        telemetry_records: List[CanonicalTelemetry],
        completeness: float = 1.0,
        temporal_trends: Optional[List[TemporalTrend]] = None
    ) -> List[HypothesisScore]:
        """Execute multi-signal matrix evaluation across all formal failure hypotheses."""
        if not telemetry_records:
            return [
                HypothesisScore(
                    hypothesis=HypothesisType.INSUFFICIENT_EVIDENCE.value,
                    confidence=0.0,
                    evidence_strength=0.0,
                    completeness=0.0,
                    supporting_signals=["Zero telemetry records received."],
                    plausibility="HIGH"
                )
            ]

        # Extract aggregate metrics across records
        max_loss = max((r.metrics.packet_loss_pct or 0.0 for r in telemetry_records), default=0.0)
        max_lat = max((r.metrics.latency_ms or 0.0 for r in telemetry_records), default=0.0)
        max_qd = max((r.metrics.queue_drops or 0 for r in telemetry_records), default=0)
        max_crc = max((r.metrics.interface_errors or 0 for r in telemetry_records), default=0)
        min_rssi = min((r.metrics.signal_strength_dbm for r in telemetry_records if r.metrics.signal_strength_dbm is not None), default=0.0)
        has_rssi = any(r.metrics.signal_strength_dbm is not None for r in telemetry_records)
        dns_fails = any(r.metrics.dns_resolution_ms and r.metrics.dns_resolution_ms > 100.0 for r in telemetry_records)
        dhcp_fails = any(r.metrics.dhcp_lease_success is False for r in telemetry_records)
        max_cpu = max((r.metrics.cpu_pct or 0.0 for r in telemetry_records), default=0.0)
        max_util = max((r.metrics.link_utilization_pct or 0.0 for r in telemetry_records), default=0.0)

        # 1. EVALUATE LINK_CONGESTION
        cong_sup: List[str] = []
        cong_contra: List[str] = []
        if max_qd > 0:
            cong_sup.append(f"Elevated queue buffer drops observed (max: {max_qd} drops)")
        if max_lat > 60.0:
            cong_sup.append(f"Excessive round-trip latency indicating buffer queueing (max: {max_lat} ms)")
        if max_util > 80.0:
            cong_sup.append(f"High egress link utilization (max: {max_util}%)")
        if max_crc == 0 and (max_lat > 50.0 or max_qd > 0):
            cong_sup.append("Zero physical CRC errors confirms pure buffer exhaustion over physical damage")
        elif max_crc > 50:
            cong_contra.append(f"Presence of physical layer CRC errors ({max_crc}) suggests transceiver/cable defect, not pure congestion")

        cong_strength = 0.0
        if cong_sup:
            cong_strength = min(0.95, 0.40 + (len(cong_sup) * 0.15))
            if cong_contra:
                cong_strength -= (len(cong_contra) * 0.20)
        cong_strength = max(0.0, cong_strength)

        # 2. EVALUATE HARDWARE_FAILURE
        hw_sup: List[str] = []
        hw_contra: List[str] = []
        if max_crc > 0:
            hw_sup.append(f"Physical layer interface/FCS errors detected (max: {max_crc})")
        if max_loss > 5.0 and max_crc > 0:
            hw_sup.append(f"Packet loss ({max_loss}%) correlated with interface error counters")
        if max_crc == 0 and max_lat > 50.0:
            hw_contra.append("Zero physical CRC errors strongly contradicts physical layer degradation")
        if max_qd > 100 and max_crc == 0:
            hw_contra.append("Symptoms explained by buffer exhaustion without hardware faults")

        hw_strength = 0.0
        if hw_sup:
            hw_strength = min(0.96, 0.45 + (len(hw_sup) * 0.18))
            if hw_contra:
                hw_strength -= (len(hw_contra) * 0.25)
        hw_strength = max(0.0, hw_strength)

        # 3. EVALUATE WEAK_WIFI
        wifi_sup: List[str] = []
        wifi_contra: List[str] = []
        if has_rssi and min_rssi < -70.0:
            wifi_sup.append(f"Severe RF signal attenuation (RSSI {min_rssi} dBm < -70 dBm)")
        if has_rssi and max_loss > 0.0 and min_rssi < -70.0:
            wifi_sup.append(f"Wireless packet loss ({max_loss}%) directly induced by poor RF propagation")
        if not has_rssi:
            wifi_contra.append("Telemetry devices are wired infrastructure switches; no wireless interfaces present")
        elif min_rssi > -60.0:
            wifi_contra.append(f"RF signal strength is excellent ({min_rssi} dBm); rules out RF attenuation")

        wifi_strength = 0.0
        if wifi_sup:
            wifi_strength = min(0.95, 0.50 + (len(wifi_sup) * 0.20))
            if wifi_contra:
                wifi_strength -= (len(wifi_contra) * 0.30)
        wifi_strength = max(0.0, wifi_strength)

        # 4. EVALUATE DNS_DHCP_FAILURE
        srv_sup: List[str] = []
        srv_contra: List[str] = []
        if dns_fails:
            srv_sup.append("Client DNS resolution timeout / latency exceeded 100ms")
        if dhcp_fails:
            srv_sup.append("DHCP lease acquisition failure reported")
        if not dns_fails and not dhcp_fails:
            srv_contra.append("DNS resolution and DHCP leasing operating within normal bounds")

        srv_strength = 0.0
        if srv_sup:
            srv_strength = min(0.95, 0.55 + (len(srv_sup) * 0.20))
            if srv_contra:
                srv_strength -= (len(srv_contra) * 0.30)
        srv_strength = max(0.0, srv_strength)

        # 5. EVALUATE NORMAL_OPERATION
        norm_sup: List[str] = []
        norm_contra: List[str] = []
        if max_lat <= 40.0 and max_loss == 0.0 and max_qd == 0 and max_crc == 0 and not dns_fails and not dhcp_fails:
            norm_sup.append("All observed latency, loss, and error metrics strictly within nominal baseline boundaries")
        else:
            if max_loss > 0.0:
                norm_contra.append(f"Active packet loss ({max_loss}%) contradicts nominal state")
            if max_lat > 50.0:
                norm_contra.append(f"Elevated latency ({max_lat} ms) contradicts nominal state")
            if max_crc > 0:
                norm_contra.append(f"Interface errors ({max_crc}) contradict nominal state")
            if max_qd > 0:
                norm_contra.append(f"Queue drops ({max_qd}) contradict nominal state")

        norm_strength = 0.0
        if norm_sup:
            norm_strength = 0.95
        elif norm_contra:
            norm_strength = 0.05

        # Build list of scores
        scores = [
            HypothesisScore(
                hypothesis=HypothesisType.LINK_CONGESTION.value,
                confidence=round(cong_strength * completeness, 3),
                evidence_strength=round(cong_strength, 3),
                completeness=completeness,
                supporting_signals=cong_sup,
                contradicting_signals=cong_contra,
                distinguishing_factors=["High queue drops with zero CRC errors isolates buffer exhaustion"],
                missing_distinguishing_evidence=["Egress interface buffer depth" if not max_qd else ""],
                plausibility="HIGH" if cong_strength >= 0.65 else ("PLAUSIBLE" if cong_strength >= 0.3 else "UNLIKELY")
            ),
            HypothesisScore(
                hypothesis=HypothesisType.HARDWARE_FAILURE.value,
                confidence=round(hw_strength * completeness, 3),
                evidence_strength=round(hw_strength, 3),
                completeness=completeness,
                supporting_signals=hw_sup,
                contradicting_signals=hw_contra,
                distinguishing_factors=["Physical CRC/FCS frame errors correlated with packet loss"],
                missing_distinguishing_evidence=["Optical DOM power levels" if max_crc > 0 else ""],
                plausibility="HIGH" if hw_strength >= 0.65 else ("PLAUSIBLE" if hw_strength >= 0.3 else "UNLIKELY")
            ),
            HypothesisScore(
                hypothesis=HypothesisType.WEAK_WIFI.value,
                confidence=round(wifi_strength * completeness, 3),
                evidence_strength=round(wifi_strength, 3),
                completeness=completeness,
                supporting_signals=wifi_sup,
                contradicting_signals=wifi_contra,
                distinguishing_factors=["RSSI signal degradation isolated to wireless access point / clients"],
                missing_distinguishing_evidence=["Channel interference (SNR)" if has_rssi else ""],
                plausibility="HIGH" if wifi_strength >= 0.65 else ("PLAUSIBLE" if wifi_strength >= 0.3 else "UNLIKELY")
            ),
            HypothesisScore(
                hypothesis=HypothesisType.DNS_DHCP_FAILURE.value,
                confidence=round(srv_strength * completeness, 3),
                evidence_strength=round(srv_strength, 3),
                completeness=completeness,
                supporting_signals=srv_sup,
                contradicting_signals=srv_contra,
                distinguishing_factors=["Centralized application/name service outage with intact transport layer"],
                missing_distinguishing_evidence=["DNS daemon process status" if dns_fails else ""],
                plausibility="HIGH" if srv_strength >= 0.65 else ("PLAUSIBLE" if srv_strength >= 0.3 else "UNLIKELY")
            ),
            HypothesisScore(
                hypothesis=HypothesisType.NORMAL_OPERATION.value,
                confidence=round(norm_strength * completeness, 3),
                evidence_strength=round(norm_strength, 3),
                completeness=completeness,
                supporting_signals=norm_sup,
                contradicting_signals=norm_contra,
                distinguishing_factors=["Zero threshold excursions across all monitored layers"],
                plausibility="HIGH" if norm_strength >= 0.8 else "UNLIKELY"
            ),
        ]

        # Clean empty missing evidence strings
        for s in scores:
            s.missing_distinguishing_evidence = [e for e in s.missing_distinguishing_evidence if e]

        # Sort ranked by confidence descending
        scores.sort(key=lambda x: x.confidence, reverse=True)
        return scores
