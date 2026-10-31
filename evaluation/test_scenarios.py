"""Integration tests for all 6 primary scenarios and edge-case scenarios."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import HypothesisType

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"


def load_scenario(filename: str):
    with open(SCENARIOS_DIR / filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("telemetry", data), data.get("scenario_id", filename)


def scenario_reference_time(telemetry, is_stale: bool = False) -> datetime | None:
    """Return a fixed reference_time derived from the scenario's own timestamps.

    This ensures tests are not sensitive to when they are run — staleness is
    computed relative to the scenario data, not the system clock.
    For the deliberate stale-data scenario, we return None so the real clock applies.
    """
    if is_stale:
        return None  # Let real clock make data look stale — that is the point
    devices = telemetry if isinstance(telemetry, list) else [telemetry]
    candidates: list[datetime] = []
    for dev in devices:
        raw = dev.get("timestamp") or dev.get("epoch_timestamp")
        if raw:
            try:
                if isinstance(raw, (int, float)):
                    candidates.append(datetime.fromtimestamp(raw, tz=timezone.utc))
                else:
                    candidates.append(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
            except Exception:
                pass
    if candidates:
        return max(candidates) + timedelta(seconds=60)
    return None


def test_scenario_1_normal():
    telemetry, s_id = load_scenario("scenario_1_normal.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    assert result.report.suspected_root_cause == HypothesisType.NORMAL_OPERATION.value
    assert len(result.report.affected_devices) == 0
    assert result.report.confidence >= 0.50


def test_scenario_2_congestion():
    telemetry, s_id = load_scenario("scenario_2_congestion.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    assert result.report.status == "diagnosed"
    assert result.report.suspected_root_cause == HypothesisType.LINK_CONGESTION.value
    assert "BLDG-SW-ENG" in result.report.affected_devices
    assert result.report.confidence >= 0.70
    assert len(result.report.evidence_sources) >= 2
    assert len(result.report.supporting_evidence) >= 1
    # Verify Page 5 structured evidence schema
    first_ev = result.report.supporting_evidence[0]
    assert hasattr(first_ev, "metric")
    assert hasattr(first_ev, "value")
    assert hasattr(first_ev, "interpretation")
    # Verify alternative causes are string list
    assert isinstance(result.report.alternative_causes, list)
    if result.report.alternative_causes:
        assert isinstance(result.report.alternative_causes[0], str)


def test_scenario_3_hardware_failure():
    telemetry, s_id = load_scenario("scenario_3_hardware_failure.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    assert result.report.suspected_root_cause == HypothesisType.HARDWARE_FAILURE.value
    assert "BLDG-SW-HOSTEL-A" in result.report.affected_devices
    # Contradictory evidence must identify that the generator's reported HEALTHY label was contradicted
    assert any("HEALTHY" in item and "contradicted" in item.lower() for item in result.arbitration_result.contradictory_evidence)


def test_scenario_4_weak_wifi():
    telemetry, s_id = load_scenario("scenario_4_weak_wifi.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    assert result.report.suspected_root_cause == HypothesisType.WEAK_WIFI.value
    assert "AP-HOSTEL-B2" in result.report.affected_devices


def test_scenario_5_dns_dhcp_failure():
    telemetry, s_id = load_scenario("scenario_5_dns_dhcp_failure.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    assert result.report.suspected_root_cause == HypothesisType.DNS_DHCP_FAILURE.value
    assert "SRV-DNS-01" in result.report.affected_devices


def test_scenario_6_schema_interop_failure():
    telemetry, s_id = load_scenario("scenario_6_schema_interop_failure.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    # Ingestion must not crash, must record normalization warnings
    total_warnings = sum(len(r.normalization_warnings) for r in result.canonical_telemetry)
    assert total_warnings >= 5
    assert result.report.suspected_root_cause in (
        HypothesisType.INTEROPERABILITY_SCHEMA_DEFECT.value,
        HypothesisType.LINK_CONGESTION.value,
        HypothesisType.RESOURCE_EXHAUSTION.value
    )


def test_edge_missing_telemetry():
    telemetry, s_id = load_scenario("scenario_edge_missing_telemetry.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    # Missing metrics must trigger insufficient evidence or heavy confidence penalty
    assert result.report.confidence < 0.60 or result.report.suspected_root_cause == HypothesisType.INSUFFICIENT_EVIDENCE.value
    assert any("missing" in lim.lower() for lim in result.report.limitations)


def test_edge_conflicting_labels():
    telemetry, s_id = load_scenario("scenario_edge_conflicting_labels.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    # Must override false HEALTHY label and identify hardware failure
    assert result.report.suspected_root_cause == HypothesisType.HARDWARE_FAILURE.value
    assert any("Untrusted generator label" in c for c in result.arbitration_result.contradictory_evidence)


def test_edge_unknown_devices():
    telemetry, s_id = load_scenario("scenario_edge_unknown_devices.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id,
                          reference_time=scenario_reference_time(telemetry))

    # Handled without crashing
    assert "ROGUE-ACCESS-POINT-99" in result.report.affected_devices
    assert result.report.suspected_root_cause == HypothesisType.WEAK_WIFI.value


def test_edge_malformed_payload():
    telemetry, s_id = load_scenario("scenario_edge_malformed_payload.json")
    orch = NetworkIntelligenceOrchestrator()
    result = orch.process(raw_input=telemetry, incident_id=s_id)

    # Must safely sanitize and complete without throwing exceptions
    assert result.report.suspected_root_cause == HypothesisType.INSUFFICIENT_EVIDENCE.value


def test_remediation_simulation():
    from core.remediation import RemediationSimulator
    sim = RemediationSimulator.simulate_remediation(
        root_cause=HypothesisType.LINK_CONGESTION.value,
        affected_devices=["BLDG-SW-ENG"]
    )
    assert len(sim.actions) >= 1
    assert sim.actions[0].action_type == "APPLY_DSCP_QOS_POLICING"
    assert "egress_queue_drops" in sim.actions[0].projected_recovery
    assert sim.actions[0].rollback_cli_command != ""
    assert sim.blast_radius_contained is True
    assert sim.lifecycle_state == "SIMULATED"

    # Test recovery verification loop
    verification = RemediationSimulator.verify_simulated_recovery(sim)
    assert verification.recovery_verified is True
    assert verification.lifecycle_state == "SIMULATED_RECOVERY_VERIFIED"
    assert len(verification.kpi_deltas) > 0
    # Latency recovery delta calculation
    lat_delta = verification.kpi_deltas.get("BLDG-SW-ENG_round_trip_latency_ms")
    assert lat_delta is not None
    assert lat_delta["improvement_pct"] == 90.0
    assert verification.rollback_recommended is False


def test_session_state_store_pause_resume(tmp_path):
    from core.state_store import SessionStateStore
    store = SessionStateStore(store_dir=tmp_path)
    chk = store.pause_session("SESS-TEST", {"diagnosed": "LINK_CONGESTION"})
    assert chk.is_paused is True
    resumed = store.resume_session("SESS-TEST")
    assert resumed is not None
    assert resumed.is_paused is False
    assert resumed.state_payload["diagnosed"] == "LINK_CONGESTION"


def test_mcp_server_diagnose_tool():
    from mcp_server import NetCoopMCPServer
    server = NetCoopMCPServer()
    tools = server.get_tool_definitions()
    assert len(tools) == 4
    tool_names = [t["name"] for t in tools]
    assert "diagnose_telemetry" in tool_names
    assert "simulate_remediation" in tool_names
    # Test tool execution
    res = server.execute_tool(
        "simulate_remediation",
        {"root_cause": "WEAK_WIFI", "affected_devices": ["AP-MHR-W1"]}
    )
    assert res["suspected_root_cause"] == "WEAK_WIFI"
    assert len(res["actions"]) >= 1
