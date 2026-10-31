"""Unit tests for individual specialized diagnostic agents."""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.telemetry_agent import TelemetryAgent
from agents.infrastructure_agent import InfrastructureAgent
from agents.connectivity_agent import ConnectivityAgent
from core.topology import TopologyEngine
from protocol.models import (
    CanonicalMetrics,
    CanonicalTelemetry,
    SchemaVersion,
    SeverityLevel,
)


def test_telemetry_agent_analysis():
    agent = TelemetryAgent()
    # High latency and packet loss
    rec = CanonicalTelemetry(
        device_id="SW-01",
        metrics=CanonicalMetrics(
            latency_ms=150.0,
            jitter_ms=30.0,
            packet_loss_pct=6.0,
            throughput_mbps=10.0
        ),
        schema_version_detected=SchemaVersion.V1
    )
    finding = agent.analyze(rec)
    assert finding.overall_severity == SeverityLevel.CRITICAL
    assert "HIGH_LATENCY" in finding.suspected_issues
    assert "PACKET_LOSS" in finding.suspected_issues
    assert len(finding.evidence) >= 3


def test_telemetry_agent_healthy():
    agent = TelemetryAgent()
    rec = CanonicalTelemetry(
        device_id="SW-01",
        metrics=CanonicalMetrics(
            latency_ms=10.0,
            jitter_ms=1.5,
            packet_loss_pct=0.0,
            throughput_mbps=100.0
        ),
        schema_version_detected=SchemaVersion.V1
    )
    finding = agent.analyze(rec)
    assert finding.overall_severity == SeverityLevel.HEALTHY
    assert len(finding.suspected_issues) == 0


def test_infrastructure_agent_analysis():
    agent = InfrastructureAgent()
    # High CPU and interface errors
    rec = CanonicalTelemetry(
        device_id="DIST-SW-NORTH",
        metrics=CanonicalMetrics(
            cpu_pct=95.0,
            memory_pct=92.0,
            queue_drops=120,
            interface_errors=85
        ),
        schema_version_detected=SchemaVersion.V1
    )
    finding = agent.analyze(rec)
    assert finding.overall_severity == SeverityLevel.CRITICAL
    assert "HIGH_CPU" in finding.suspected_issues
    assert "HIGH_MEMORY" in finding.suspected_issues
    assert "QUEUE_DROPS" in finding.suspected_issues
    assert "INTERFACE_ERRORS" in finding.suspected_issues


def test_connectivity_agent_topology_and_unknown_device():
    topo = TopologyEngine()
    agent = ConnectivityAgent(topo)

    # Test known device with weak wifi
    rec_known = CanonicalTelemetry(
        device_id="AP-HOSTEL-A1",
        metrics=CanonicalMetrics(signal_strength_dbm=-85.0),
        schema_version_detected=SchemaVersion.V1
    )
    finding_known = agent.analyze(rec_known)
    assert finding_known.overall_severity == SeverityLevel.CRITICAL
    assert "CRITICAL_WEAK_SIGNAL" in finding_known.suspected_issues

    # Test unknown device handling without crashing
    rec_unknown = CanonicalTelemetry(
        device_id="ROGUE-AP-XYZ",
        metrics=CanonicalMetrics(signal_strength_dbm=-60.0),
        schema_version_detected=SchemaVersion.V1
    )
    finding_unknown = agent.analyze(rec_unknown)
    assert finding_unknown.overall_severity == SeverityLevel.HEALTHY
    assert "known=False" in finding_unknown.notes
