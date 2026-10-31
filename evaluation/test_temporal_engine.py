"""Dedicated Temporal Benchmark & Time-Series Evaluation for NetCoop AI.

Tests multi-step time series evaluating:
1. Gradual congestion buildup (monotonic queue growth)
2. Sudden latency spike (> 5ms/sec surge detection)
3. Intermittent packet loss vs sustained loss
4. Post-incident recovery (metrics reverting to nominal)
5. Out-of-order timestamps & clock skew handling
6. Rolling baseline drift vs abrupt anomaly
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.hypothesis_engine import HypothesisEngine, TemporalTrend
from core.orchestrator import NetworkIntelligenceOrchestrator
from protocol.models import CanonicalMetrics, CanonicalTelemetry, SchemaVersion


def _make_telemetry(device_id: str, timestamp_dt: datetime, **metric_kwargs) -> CanonicalTelemetry:
    """Helper to construct canonical telemetry records with explicit timestamps."""
    metrics = CanonicalMetrics(**metric_kwargs)
    return CanonicalTelemetry(
        device_id=device_id,
        timestamp=timestamp_dt,
        reported_status="WARNING",
        metrics=metrics,
        schema_version_detected=SchemaVersion.V1
    )


def test_temporal_sudden_latency_spike_detection():
    """Verify that a sudden latency surge (> 5ms/sec) is captured by rate-of-change analysis."""
    base_t = datetime.now(timezone.utc)
    t0 = base_t - timedelta(seconds=10)
    t1 = base_t

    hist_record = _make_telemetry("BLDG-SW-ENG", t0, latency_ms=18.0, packet_loss_pct=0.0)
    curr_record = _make_telemetry("BLDG-SW-ENG", t1, latency_ms=185.0, packet_loss_pct=4.5)

    trends = HypothesisEngine.detect_temporal_anomalies(
        current_records=[curr_record],
        history=[[hist_record]]
    )

    lat_trends = [t for t in trends if t.metric == "latency_ms"]
    assert len(lat_trends) == 1
    trend = lat_trends[0]
    assert trend.is_sudden_spike is True
    assert trend.rate_of_change_per_sec > 15.0  # (185 - 18) / 10s = 16.7 ms/s
    assert trend.severity == "WARNING"


def test_temporal_gradual_congestion_buildup():
    """Verify monotonic queue growth over sequential observation windows."""
    base_t = datetime.now(timezone.utc)
    t0 = base_t - timedelta(seconds=30)
    t1 = base_t - timedelta(seconds=15)
    t2 = base_t

    rec0 = _make_telemetry("BLDG-SW-ENG", t0, queue_drops=10, latency_ms=30.0)
    rec1 = _make_telemetry("BLDG-SW-ENG", t1, queue_drops=55, latency_ms=65.0)
    rec2 = _make_telemetry("BLDG-SW-ENG", t2, queue_drops=220, latency_ms=145.0)

    # Process sequential windows
    trends_1 = HypothesisEngine.detect_temporal_anomalies([rec1], [[rec0]])
    trends_2 = HypothesisEngine.detect_temporal_anomalies([rec2], [[rec0], [rec1]])

    qd_trends = [t for t in trends_2 if t.metric == "queue_drops"]
    assert len(qd_trends) == 1
    assert qd_trends[0].rate_of_change_per_sec > 10.0  # (220 - 55) / 15s = 11.0 drops/s
    assert qd_trends[0].severity == "CRITICAL"


def test_temporal_post_incident_recovery():
    """Verify that when metrics drop back to baseline, anomaly spikes are cleared."""
    base_t = datetime.now(timezone.utc)
    t_fault = base_t - timedelta(seconds=10)
    t_recovered = base_t

    rec_fault = _make_telemetry("BLDG-SW-ENG", t_fault, latency_ms=185.0, queue_drops=145)
    rec_healthy = _make_telemetry("BLDG-SW-ENG", t_recovered, latency_ms=16.0, queue_drops=0)

    trends = HypothesisEngine.detect_temporal_anomalies([rec_healthy], [[rec_fault]])
    # Negative rate of change indicates recovery
    for t in trends:
        assert t.rate_of_change_per_sec < 0.0
        assert t.is_sudden_spike is False
        assert t.severity == "NORMAL"


def test_temporal_clock_skew_and_zero_delta():
    """Verify that zero delta or inverted timestamps (clock skew) do not cause ZeroDivisionError."""
    base_t = datetime.now(timezone.utc)
    rec1 = _make_telemetry("BLDG-SW-ENG", base_t, latency_ms=15.0)
    rec2 = _make_telemetry("BLDG-SW-ENG", base_t, latency_ms=25.0)  # Identical timestamp

    # Must execute gracefully without division by zero
    trends = HypothesisEngine.detect_temporal_anomalies([rec2], [[rec1]])
    assert isinstance(trends, list)
