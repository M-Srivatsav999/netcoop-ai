"""Unit tests for EvidenceEngine, ConfidenceEngine, and CorrelationAgent arbitration."""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.confidence_engine import ConfidenceConfig, ConfidenceEngine
from core.evidence_engine import EvidenceEngine
from core.topology import TopologyEngine
from agents.correlation_agent import CorrelationAgent
from protocol.models import (
    AgentFinding,
    CanonicalMetrics,
    CanonicalTelemetry,
    EvidenceItem,
    EvidencePolarity,
    HypothesisType,
    SchemaVersion,
    SeverityLevel,
)


def test_untrusted_status_label_reconciliation():
    engine = EvidenceEngine()
    # Device reported as HEALTHY but has 12% packet loss and 400 errors
    records = [
        CanonicalTelemetry(
            device_id="SW-01",
            reported_status="HEALTHY",
            metrics=CanonicalMetrics(
                packet_loss_pct=12.0,
                interface_errors=400
            ),
            schema_version_detected=SchemaVersion.V1
        )
    ]
    reconciliation = engine.reconcile_untrusted_labels(records)
    assert len(reconciliation) == 1
    assert reconciliation[0].polarity == EvidencePolarity.CONTRADICTS
    assert reconciliation[0].hypothesis_target == HypothesisType.NORMAL_OPERATION.value
    assert "Untrusted generator label 'HEALTHY' contradicted" in reconciliation[0].description


def test_conflict_resolution_congestion_vs_hardware():
    engine = EvidenceEngine()
    
    # Case A: High loss + zero errors + high latency -> Supports CONGESTION, Contradicts HARDWARE
    rec_congest = CanonicalTelemetry(
        device_id="SW-CONGEST",
        metrics=CanonicalMetrics(
            latency_ms=160.0,
            packet_loss_pct=5.0,
            interface_errors=0,
            queue_drops=100
        ),
        schema_version_detected=SchemaVersion.V1
    )
    res_a = engine.apply_conflict_resolution_rules([rec_congest])
    targets_a = [r.hypothesis_target for r in res_a]
    assert HypothesisType.LINK_CONGESTION.value in targets_a
    assert HypothesisType.HARDWARE_FAILURE.value in targets_a

    contra_hw = [r for r in res_a if r.hypothesis_target == HypothesisType.HARDWARE_FAILURE.value]
    assert contra_hw[0].polarity == EvidencePolarity.CONTRADICTS

    # Case B: High loss + high interface errors -> Supports HARDWARE, Contradicts CONGESTION
    rec_hw = CanonicalTelemetry(
        device_id="SW-HW",
        metrics=CanonicalMetrics(
            latency_ms=15.0,
            packet_loss_pct=15.0,
            interface_errors=500,
            queue_drops=0
        ),
        schema_version_detected=SchemaVersion.V1
    )
    res_b = engine.apply_conflict_resolution_rules([rec_hw])
    contra_congest = [r for r in res_b if r.hypothesis_target == HypothesisType.LINK_CONGESTION.value]
    assert contra_congest[0].polarity == EvidencePolarity.CONTRADICTS


def test_confidence_engine_penalties():
    conf_engine = ConfidenceEngine(ConfidenceConfig(target_signal_weight=2.0))

    # Complete telemetry
    telemetry_full = [
        CanonicalTelemetry(
            device_id="DEV-1",
            metrics=CanonicalMetrics(
                latency_ms=100.0,
                jitter_ms=20.0,
                packet_loss_pct=5.0,
                throughput_mbps=10.0,
                cpu_pct=50.0,
                memory_pct=50.0,
                queue_drops=10,
                interface_errors=0
            )
        )
    ]

    hyp_data_clean = {
        "support_weight": 2.5,
        "contra_weight": 0.0,
        "supporting_agents": ["TelemetryAgent", "InfrastructureAgent", "ConnectivityAgent"]
    }
    conf_clean, _, _ = conf_engine.calculate_confidence(hyp_data_clean, telemetry_full, topology_consistency=1.0)

    # Telemetry with contradictory evidence
    hyp_data_contra = {
        "support_weight": 2.5,
        "contra_weight": 2.0,
        "supporting_agents": ["TelemetryAgent", "InfrastructureAgent", "ConnectivityAgent"]
    }
    conf_contra, uncert, _ = conf_engine.calculate_confidence(hyp_data_contra, telemetry_full, topology_consistency=1.0)
    assert conf_contra < conf_clean
    assert any("Contradictory evidence detected" in u for u in uncert)

    # Sparse telemetry (only 1 metric populated)
    telemetry_sparse = [
        CanonicalTelemetry(
            device_id="DEV-2",
            metrics=CanonicalMetrics(latency_ms=100.0)
        )
    ]
    conf_sparse, uncert_sp, _ = conf_engine.calculate_confidence(hyp_data_clean, telemetry_sparse, topology_consistency=1.0)
    assert conf_sparse < conf_clean


def test_insufficient_evidence_detection():
    arbiter = CorrelationAgent()
    
    # Extremely sparse telemetry with low signals
    records = [
        CanonicalTelemetry(
            device_id="BLDG-SW-ENG",
            metrics=CanonicalMetrics(latency_ms=36.0),  # Very borderline latency
            schema_version_detected=SchemaVersion.V1
        )
    ]
    finding = AgentFinding(
        agent_name="TelemetryAgent",
        device_id="BLDG-SW-ENG",
        overall_severity=SeverityLevel.WARNING,
        evidence=[
            EvidenceItem(
                evidence_id="E1",
                source_agent="TelemetryAgent",
                device_id="BLDG-SW-ENG",
                metric_name="latency_ms",
                observed_value=36.0,
                severity=SeverityLevel.WARNING,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.LINK_CONGESTION.value,
                weight=0.2,
                description="Minor latency elevation"
            )
        ]
    )
    result = arbiter.arbitrate(telemetry_records=records, agent_findings=[finding])
    assert result.primary_root_cause == HypothesisType.INSUFFICIENT_EVIDENCE.value
    # Either critically sparse telemetry OR below confidence threshold triggers insufficient_evidence
    insuff_signals = (
        any("Confidence" in u and "did not meet minimum threshold" in u for u in result.uncertainty_factors) or
        any("sparse telemetry" in u.lower() for u in result.uncertainty_factors)
    )
    assert insuff_signals, f"Expected insufficient evidence signal in uncertainty_factors: {result.uncertainty_factors}"


def test_isotonic_calibrator_pava_fitting_and_monotonicity():
    from core.confidence_engine import IsotonicCalibrator

    # Deliberately construct observations with violations of monotonicity
    x_raw = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    y_raw = [0,   1,   0,   1,   1,   0,   1,   1,   1]

    calibrator = IsotonicCalibrator.fit_pava(x_raw, y_raw)

    # Output predictions must be strictly non-decreasing
    preds = [calibrator.predict(x) for x in x_raw]
    for i in range(len(preds) - 1):
        assert preds[i] <= preds[i + 1], f"Monotonicity violation at index {i}: {preds[i]} > {preds[i+1]}"

    # Default calibrator prediction bounds
    default_cal = IsotonicCalibrator()
    assert default_cal.predict(0.0) == 0.0
    assert default_cal.predict(0.35) == 0.50
    assert default_cal.predict(0.85) >= 0.94
    assert default_cal.predict(1.0) == 0.985

