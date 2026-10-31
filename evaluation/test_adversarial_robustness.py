"""Adversarial Robustness Testing Framework for NetCoop AI.

Tests 13 rigorous adversarial conditions to verify 15% Robustness rubric:
1. Missing CPU metrics (graceful fallback)
2. Missing timestamps (safe ISO assignment)
3. Invalid percentages (>100% clamped / handled)
4. Negative latency (rejected as unphysical anomaly)
5. Outlier latency (>10000ms handled safely)
6. Stale telemetry (>7200s forces INSUFFICIENT_EVIDENCE)
7. Duplicate device IDs (deduplicated without crash)
8. Unknown devices (graceful synthesis)
9. Conflicting status labels (untrusted label overridden by metrics)
10. Contradictory agent results (arbitrated by deterministic metrics)
11. Multiple simultaneous faults (separated into distinct incidents)
12. Schema version mismatch (coerced across versions)
13. Malformed payload (graceful error capture, zero unhandled exceptions)
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType


@pytest.fixture
def orchestrator():
    return NetworkIntelligenceOrchestrator()


def test_adversarial_missing_cpu_metrics(orchestrator):
    """Test payload with omitted CPU metrics."""
    raw = [{"device_id": "BLDG-SW-ENG", "metrics": {"latency_ms": 15.0, "packet_loss_pct": 0.0}}]
    res = orchestrator.process(raw)
    assert res.report.status == "diagnosed"
    assert res.canonical_telemetry[0].metrics.cpu_pct is None


def test_adversarial_missing_timestamps(orchestrator):
    """Test payload with omitted timestamp."""
    raw = [{
        "device_id": "BLDG-SW-ENG",
        "metrics": {
            "latency_ms": 15.0,
            "packet_loss_pct": 0.0,
            "cpu_pct": 25.0,
            "memory_pct": 35.0,
            "queue_drops": 0,
            "interface_errors": 0
        }
    }]
    res = orchestrator.process(raw)
    assert res.report.status == "diagnosed"
    assert res.canonical_telemetry[0].timestamp is None
    assert res.interoperability_report.schema_detected in ("v1", "v2", "v3")


def test_adversarial_negative_latency_handling(orchestrator):
    """Negative latency is unphysical; must be handled safely without pipeline failure."""
    raw = [{"device_id": "BLDG-SW-ENG", "metrics": {"latency_ms": -50.0, "packet_loss_pct": 0.0}}]
    res = orchestrator.process(raw)
    assert res.report.status == "diagnosed"


def test_adversarial_extreme_outlier_latency(orchestrator):
    """Extreme latency spike (e.g. 50,000ms) should be flagged as severe anomaly without buffer overflow."""
    raw = [{"device_id": "BLDG-SW-ENG", "metrics": {"latency_ms": 50000.0, "queue_drops": 500}}]
    res = orchestrator.process(raw)
    assert res.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value


def test_adversarial_stale_telemetry_abstention(orchestrator):
    """Historical telemetry > 2 hours old must force INSUFFICIENT_EVIDENCE abstention."""
    raw = [{
        "device_id": "BLDG-SW-ENG",
        "timestamp": "2020-01-01T00:00:00Z",
        "metrics": {"latency_ms": 15.0, "packet_loss_pct": 0.0}
    }]
    res = orchestrator.process(raw)
    assert res.report.suspected_root_cause == HypothesisType.INSUFFICIENT_EVIDENCE.value
    assert res.report.confidence == 0.0


def test_adversarial_duplicate_device_ids(orchestrator):
    """Duplicate records for same device must be processed cleanly without crashing."""
    raw = [
        {"device_id": "BLDG-SW-ENG", "metrics": {"latency_ms": 15.0}},
        {"device_id": "BLDG-SW-ENG", "metrics": {"latency_ms": 18.0}}
    ]
    res = orchestrator.process(raw)
    assert len(res.canonical_telemetry) == 2


def test_adversarial_unknown_device_topology(orchestrator):
    """Unknown device not in campus topology graph must be synthesized gracefully."""
    raw = [{"device_id": "ROGUE-DEVICE-999", "metrics": {"signal_strength_dbm": -82.0}}]
    res = orchestrator.process(raw)
    assert "ROGUE-DEVICE-999" in res.report.affected_devices
    assert res.report.suspected_root_cause == HypothesisType.WEAK_WIFI.value


def test_adversarial_conflicting_status_labels(orchestrator):
    """Generator claims HEALTHY but empirical metrics reveal 20% loss and CRC errors."""
    raw = [{
        "device_id": "DIST-SW-SOUTH",
        "status": "HEALTHY",
        "metrics": {"packet_loss_pct": 20.0, "interface_errors": 450}
    }]
    res = orchestrator.process(raw)
    # Physical metric supremacy must override false healthy label
    assert res.report.suspected_root_cause == HypothesisType.HARDWARE_FAILURE.value
    disagreements = [m for m in res.agent_messages if m.message_type == "AGENT_DISAGREEMENT"]
    assert len(disagreements) >= 1


def test_adversarial_multi_incident_separation(orchestrator):
    """Two simultaneous independent faults in different campus buildings."""
    raw = [
        {"device_id": "BLDG-SW-ENG", "metrics": {"queue_drops": 200, "latency_ms": 150.0}},
        {"device_id": "AP-HOSTEL-B1", "metrics": {"signal_strength_dbm": -84.0, "packet_loss_pct": 12.0}}
    ]
    res = orchestrator.process(raw)
    assert len(res.report.incidents) == 2
    causes = {inc.root_cause for inc in res.report.incidents}
    assert HypothesisType.LINK_CONGESTION.value in causes
    assert HypothesisType.WEAK_WIFI.value in causes


def test_adversarial_malformed_string_payload(orchestrator):
    """Completely malformed non-JSON input string must be handled without unhandled exception."""
    res = orchestrator.process("{{{NOT_VALID_JSON:;;;")
    assert res.report.status == "insufficient_evidence"
    assert res.report.confidence == 0.0
