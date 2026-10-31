"""Pytest test suite for organizer-format telemetry and batch device isolation."""

import json
import random
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType, SchemaVersion
from protocol.validator import TelemetryNormalizer
from organizer_generator_check import generate_telemetry


def test_organizer_field_normalization_and_warnings():
    """Verify that organizer-specific fields (cpu_utilization_pct, link_utilization_pct)

    are correctly normalized into CanonicalMetrics with appropriate provenance warnings.
    """
    raw_payload = {
        "device_id": "SW_CAMPUS_1",
        "timestamp": "2026-10-31T12:00:00Z",
        "status": "Critical",
        "metrics": {
            "cpu_utilization_pct": 99.9,
            "link_utilization_pct": 94.5,
            "packet_loss_pct": 25.0,
            "latency_ms": 650.0,
            "queue_drops": 8000,
            "interface_errors": 250,
        }
    }

    canonical = TelemetryNormalizer.normalize_single(raw_payload)
    metrics = canonical.metrics

    # Check canonical values
    assert metrics.cpu_pct == 99.9
    assert metrics.link_utilization_pct == 94.5
    assert metrics.packet_loss_pct == 25.0
    assert metrics.latency_ms == 650.0
    assert metrics.queue_drops == 8000
    assert metrics.interface_errors == 250

    # Verify normalization warning for the cpu alias
    cpu_warn = any("cpu_utilization_pct" in w.action_taken for w in canonical.normalization_warnings)
    assert cpu_warn is True, "Expected normalization warning for cpu_utilization_pct alias"


def test_organizer_fault_types_mapping():
    """Verify that all 3 organizer fault types map cleanly to the expected hypotheses."""
    random.seed(123)
    orch = NetworkIntelligenceOrchestrator()

    # Normal
    res_normal = orch.process(generate_telemetry("normal"))
    assert res_normal.report.suspected_root_cause == HypothesisType.NORMAL_OPERATION.value
    assert res_normal.report.status == "diagnosed"

    # Latency spike -> Link Congestion
    res_spike = orch.process(generate_telemetry("latency_spike"))
    assert res_spike.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value
    assert res_spike.report.status == "diagnosed"

    # Hardware failure -> Hardware Failure
    res_hw = orch.process(generate_telemetry("hardware_failure"))
    assert res_hw.report.suspected_root_cause == HypothesisType.HARDWARE_FAILURE.value
    assert res_hw.report.status == "diagnosed"


def test_organizer_10_device_batch_isolation():
    """Verify that when 10 organizer devices are submitted in a batch (9 healthy, 1 faulty),

    the orchestrator isolates the incident strictly to the faulty device,
    without blaming any of the 9 healthy devices.
    """
    random.seed(42)
    orch = NetworkIntelligenceOrchestrator()

    # 9 healthy devices
    batch = []
    for i in range(1, 10):
        dev = generate_telemetry("normal")
        dev["device_id"] = f"SW_CAMPUS_{i}"
        batch.append(dev)

    # 1 faulty device
    faulty = generate_telemetry("hardware_failure")
    faulty["device_id"] = "SW_CAMPUS_FAULTY_10"
    batch.append(faulty)

    res = orch.process(batch)

    # Root cause must be HARDWARE_FAILURE
    assert res.report.suspected_root_cause == HypothesisType.HARDWARE_FAILURE.value
    assert res.report.status == "diagnosed"

    # The ONLY affected device must be the faulty device
    assert res.report.affected_devices == ["SW_CAMPUS_FAULTY_10"]

    # None of the 9 healthy campus switches may appear in affected_devices
    for i in range(1, 10):
        assert f"SW_CAMPUS_{i}" not in res.report.affected_devices
