"""Dedicated tests for multi-incident clustering, false-splitting prevention, and dynamic agent disagreement."""

import json
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType


def test_false_incident_splitting_prevention():
    """Verify that a single upstream congestion incident affecting both a building switch

    and its downstream access point is MERGED into exactly 1 incident record,
    rather than being falsely split into two separate incidents.
    """
    orch = NetworkIntelligenceOrchestrator()
    sc_path = PROJECT_ROOT / "data" / "scenarios" / "scenario_2_congestion.json"
    with open(sc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    res = orch.process(data.get("telemetry", data))
    
    # Must be 1 merged incident
    assert len(res.report.incidents) == 1
    inc = res.report.incidents[0]
    assert inc.root_cause == HypothesisType.LINK_CONGESTION.value
    # Both upstream switch and downstream AP must be grouped in this single incident
    assert "BLDG-SW-ENG" in inc.affected_devices
    assert "AP-ENG-01" in inc.affected_devices


def test_multi_incident_independent_fault_domain_separation():
    """Verify that when genuinely independent faults happen in different campus zones

    (e.g. Wi-Fi attenuation in Hostel B and Link Congestion in Engineering),
    the system correctly emits two distinct incidents, each with its own affected devices
    and independent, dedicated confidence calculation.
    """
    orch = NetworkIntelligenceOrchestrator()
    sc_path = PROJECT_ROOT / "data" / "scenarios" / "scenario_edge_multiple_incidents.json"
    with open(sc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    res = orch.process(data.get("telemetry", data))

    # Must produce exactly 2 distinct incidents
    assert len(res.report.incidents) == 2

    # Find the two specific incidents
    causes = {inc.root_cause: inc for inc in res.report.incidents}
    assert HypothesisType.LINK_CONGESTION.value in causes
    assert HypothesisType.WEAK_WIFI.value in causes

    # Congestion incident must only affect Engineering switch
    cong_inc = causes[HypothesisType.LINK_CONGESTION.value]
    assert cong_inc.affected_devices == ["BLDG-SW-ENG"]
    assert cong_inc.confidence > 0.70  # Solid evidence: queue drops + high latency

    # Wi-Fi incident must only affect Hostel B AP
    wifi_inc = causes[HypothesisType.WEAK_WIFI.value]
    assert wifi_inc.affected_devices == ["AP-HOSTEL-B1"]
    assert wifi_inc.confidence > 0.50

    # Confidences must be independently calculated, not identical copies
    assert cong_inc.confidence != wifi_inc.confidence


def test_dynamic_agent_disagreement_message_payload():
    """Verify that when a status label contradicts empirical metrics, the orchestrator

    generates an AGENT_DISAGREEMENT message populated with dynamic findings
    (not static placeholder strings).
    """
    orch = NetworkIntelligenceOrchestrator()
    sc_path = PROJECT_ROOT / "data" / "scenarios" / "scenario_edge_conflicting_labels.json"
    with open(sc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    res = orch.process(data.get("telemetry", data))

    disagree_msgs = [m for m in res.agent_messages if m.message_type == "AGENT_DISAGREEMENT"]
    assert len(disagree_msgs) >= 1

    payload = disagree_msgs[0].payload
    assert payload["device_id"] == "DIST-SW-SOUTH"
    assert payload["reported_generator_claim"] == "HEALTHY"
    assert "PACKET_LOSS" in payload["telemetry_agent_findings"]
    assert "INTERFACE_ERRORS" in payload["infrastructure_agent_findings"]
    assert payload["resolution_strategy"] == "DETERMINISTIC_METRIC_SUPREMACY"
    assert len(payload["competing_evidence"]) >= 2


def test_same_fault_separate_location_independent_separation():
    """Verify that two independent hardware failures occurring in geographically distinct

    campus zones (e.g. Hostel A Building Switch and Engineering Building Switch)
    are NOT falsely merged into a single incident just because their root cause is identical.
    They must be emitted as TWO distinct incident records.
    """
    orch = NetworkIntelligenceOrchestrator()
    same_fault_payload = [
        {
            "device_id": "BLDG-SW-HOSTEL-A",
            "timestamp": "2026-10-31T12:00:00Z",
            "status": "CRITICAL",
            "metrics": {"interface_errors": 450, "packet_loss_pct": 18.0, "latency_ms": 120.0}
        },
        {
            "device_id": "BLDG-SW-ENG",
            "timestamp": "2026-10-31T12:00:00Z",
            "status": "CRITICAL",
            "metrics": {"interface_errors": 520, "packet_loss_pct": 22.0, "latency_ms": 140.0}
        }
    ]

    res = orch.process(same_fault_payload)

    # Must be 2 distinct incidents, NOT merged into 1
    assert len(res.report.incidents) == 2

    dev_sets = [set(inc.affected_devices) for inc in res.report.incidents]
    assert {"BLDG-SW-HOSTEL-A"} in dev_sets
    assert {"BLDG-SW-ENG"} in dev_sets

    # Both incidents must be HARDWARE_FAILURE with their respective evidence
    for inc in res.report.incidents:
        assert inc.root_cause == HypothesisType.HARDWARE_FAILURE.value
        assert len(inc.supporting_evidence) >= 1


def test_service_dependency_propagation_single_incident():
    """Verify that a centralized service failure (such as DNS/DHCP outage on SRV-DNS-01

    causing downstream name resolution failure on client CLIENT-HA-101)
    is properly grouped as ONE unified service failure incident, with SRV-DNS-01
    localized as the root-cause device and CLIENT-HA-101 as the affected device.
    """
    orch = NetworkIntelligenceOrchestrator()
    sc_path = PROJECT_ROOT / "data" / "scenarios" / "scenario_5_dns_dhcp_failure.json"
    with open(sc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    res = orch.process(data.get("telemetry", data))

    # Must be grouped into exactly 1 unified incident
    assert len(res.report.incidents) == 1
    inc = res.report.incidents[0]
    assert inc.root_cause == HypothesisType.DNS_DHCP_FAILURE.value
    assert inc.root_cause_device == "SRV-DNS-01"
    assert "SRV-DNS-01" in inc.affected_devices
    assert "CLIENT-HA-101" in inc.affected_devices
    assert len(inc.supporting_evidence) >= 2


def test_upstream_congestion_root_cause_localization():
    """Verify that in link congestion cascades affecting both an upstream switch and downstream APs,
    the causal upstream bottleneck switch (BLDG-SW-ENG) is correctly localized as the root_cause_device,
    rather than a downstream symptom receiver (AP-ENG-01).
    """
    orch = NetworkIntelligenceOrchestrator()
    sc_path = PROJECT_ROOT / "data" / "scenarios" / "scenario_2_congestion.json"
    with open(sc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    res = orch.process(data.get("telemetry", data))
    assert len(res.report.incidents) == 1
    inc = res.report.incidents[0]
    assert inc.root_cause == HypothesisType.LINK_CONGESTION.value
    # Must correctly identify upstream bottleneck switch as origin
    assert inc.root_cause_device == "BLDG-SW-ENG"


def test_service_dependency_validation_and_engine_integrity():
    """Verify that TopologyEngine validates service dependency mappings against registered topology
    nodes and ensures referenced servers exist.
    """
    from core.topology import TopologyEngine
    topo = TopologyEngine()
    
    # Verify service dependencies are loaded and validated
    assert len(topo.service_dependencies) > 0
    assert "CLIENT-HA-101" in topo.service_dependencies
    
    # All referenced servers must actually exist in registered nodes
    for client_id, srv_map in topo.service_dependencies.items():
        for s_type, srv_id in srv_map.items():
            assert srv_id in topo.nodes
            assert topo.nodes[srv_id].type == "server"

    # Test is_service_dependent query
    assert topo.is_service_dependent("CLIENT-HA-101", "SRV-DNS-01") is True
    assert topo.is_service_dependent("CLIENT-HA-101", "NON-EXISTENT-SERVER") is False

