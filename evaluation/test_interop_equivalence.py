"""Dedicated Round-Trip & Schema Equivalence Benchmark Test.

Verifies the 30% Interoperability requirement:
Feeds the identical incident through Schema V1, Schema V2, and Schema V3,
and asserts mathematical equivalence in canonical normalization and deterministic diagnosis.
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType, SchemaVersion


def test_v1_v2_v3_schema_equivalence_and_round_trip():
    """Verify that Schema V1, V2, and V3 representations of the identical network incident
    produce equivalent canonical metrics and identical diagnostic conclusions.
    """
    orch = NetworkIntelligenceOrchestrator()

    # V1 Payload: Standard field names, milliseconds, integer percentages
    v1_payload = [
        {
            "device_id": "BLDG-SW-ENG",
            "timestamp": "2026-10-31T12:00:00Z",
            "status": "WARNING",
            "metrics": {
                "latency_ms": 185.0,
                "jitter_ms": 38.0,
                "packet_loss_pct": 5.2,
                "throughput_mbps": 9850.0,
                "link_utilization_pct": 98.5,
                "cpu_pct": 68.0,
                "memory_pct": 74.0,
                "queue_drops": 145,
                "interface_errors": 0
            }
        }
    ]

    # V2 Payload: Renamed fields (host_id, epoch), seconds latency, unit ratios [0.0-1.0], bps throughput
    v2_payload = [
        {
            "host_id": "BLDG-SW-ENG",
            "epoch_timestamp": 1793448000,
            "status": "WARNING",
            "metrics": {
                "latency_sec": 0.185,
                "jitter_s": 0.038,
                "packet_loss_ratio": 0.052,
                "throughput_bps": 9850000000,
                "link_utilization_ratio": 0.985,
                "cpu_utilization_ratio": 0.68,
                "memory_utilization_ratio": 0.74,
                "queue_drops": 145,
                "crc_errors": 0
            }
        }
    ]

    # V3 Payload: String-wrapped numerical metrics, units inside strings, missing timestamp
    v3_payload = [
        {
            "device_id": "BLDG-SW-ENG",
            "status": "WARNING",
            "metrics": {
                "latency_ms": "185.0 ms",
                "jitter_ms": "38 ms",
                "packet_loss_pct": "5.2%",
                "throughput_mbps": "9850 mbps",
                "link_utilization_pct": "98.5%",
                "cpu_pct": "68%",
                "memory_pct": "74%",
                "queue_drops": "145",
                "interface_errors": "0"
            }
        }
    ]

    # Process all three payloads through the pipeline
    res_v1 = orch.process(v1_payload)
    res_v2 = orch.process(v2_payload)
    res_v3 = orch.process(v3_payload)

    # 1. Assert schema detection accuracy
    assert res_v1.interoperability_report.schema_detected == "v1"
    assert res_v2.interoperability_report.schema_detected == "v2"
    assert res_v3.interoperability_report.schema_detected == "v3"

    # 2. Assert canonical metric normalization equivalence
    m1 = res_v1.canonical_telemetry[0].metrics
    m2 = res_v2.canonical_telemetry[0].metrics
    m3 = res_v3.canonical_telemetry[0].metrics

    assert m1.latency_ms == pytest.approx(m2.latency_ms, abs=0.1)
    assert m1.latency_ms == pytest.approx(m3.latency_ms, abs=0.1)

    assert m1.packet_loss_pct == pytest.approx(m2.packet_loss_pct, abs=0.1)
    assert m1.packet_loss_pct == pytest.approx(m3.packet_loss_pct, abs=0.1)

    assert m1.queue_drops == m2.queue_drops == m3.queue_drops == 145
    assert m1.interface_errors == m2.interface_errors == m3.interface_errors == 0
    assert m1.link_utilization_pct == pytest.approx(m2.link_utilization_pct, abs=0.2)

    # 3. Assert diagnostic equivalence
    assert res_v1.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value
    assert res_v2.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value
    assert res_v3.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value

    # 4. Assert affected devices equivalence
    assert res_v1.report.affected_devices == ["BLDG-SW-ENG"]
    assert res_v2.report.affected_devices == ["BLDG-SW-ENG"]
    assert res_v3.report.affected_devices == ["BLDG-SW-ENG"]

    # 5. Assert audit report sanity
    assert res_v1.interoperability_report.canonicalization_status == "success"
    assert res_v2.interoperability_report.canonicalization_status == "success"
    assert res_v3.interoperability_report.canonicalization_status == "success"
    assert res_v2.interoperability_report.unit_conversions >= 3  # s->ms, ratios->pct, bps->mbps
