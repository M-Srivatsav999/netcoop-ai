"""Unit tests for multi-schema normalization and data sanitization."""

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.models import SchemaVersion
from protocol.validator import TelemetryNormalizer


def test_v1_baseline_normalization():
    v1_raw = {
        "device_id": "CORE-SW-01",
        "timestamp": "2026-10-31T10:00:00Z",
        "status": "HEALTHY",
        "metrics": {
            "latency_ms": 15.2,
            "jitter_ms": 2.1,
            "packet_loss_pct": 0.0,
            "throughput_mbps": 950.0,
            "cpu_pct": 24.0,
            "memory_pct": 45.0,
            "queue_drops": 0,
            "interface_errors": 0
        }
    }
    cim = TelemetryNormalizer.normalize_single(v1_raw)
    assert cim.device_id == "CORE-SW-01"
    assert cim.schema_version_detected == SchemaVersion.V1
    assert cim.metrics.latency_ms == 15.2
    assert cim.metrics.packet_loss_pct == 0.0
    assert cim.metrics.cpu_pct == 24.0
    assert cim.metrics.queue_drops == 0
    assert cim.metrics.interface_errors == 0
    assert cim.timestamp == datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc)
    assert len(cim.normalization_warnings) == 0


def test_v2_unit_conversions_and_renamed_fields():
    v2_raw = {
        "host_id": "BLDG-SW-ENG",
        "epoch_timestamp": 1793448000,
        "status": "WARNING",
        "metrics": {
            "latency_sec": 0.045,          # Should convert to 45.0 ms
            "jitter_s": 0.003,             # Should convert to 3.0 ms
            "packet_loss_ratio": 0.025,    # Should convert to 2.5 %
            "throughput_bps": 50000000,    # 50 Mbps
            "cpu_utilization_ratio": 0.82, # 82.0 %
            "memory_utilization_ratio": 0.75,
            "crc_errors": 15
        }
    }
    cim = TelemetryNormalizer.normalize_single(v2_raw)
    assert cim.device_id == "BLDG-SW-ENG"
    assert cim.schema_version_detected == SchemaVersion.V2
    assert cim.metrics.latency_ms == 45.0
    assert cim.metrics.jitter_ms == 3.0
    assert cim.metrics.packet_loss_pct == 2.5
    assert cim.metrics.throughput_mbps == 50.0
    assert cim.metrics.cpu_pct == 82.0
    assert cim.metrics.memory_pct == 75.0
    assert cim.metrics.interface_errors == 15
    assert len(cim.normalization_warnings) > 0


def test_v3_string_coercion_and_unit_stripping():
    v3_raw = {
        "device": "AP-HOSTEL-A1",
        "status": "CRITICAL",
        "metrics": {
            "latency_ms": "125.4 ms",
            "jitter_ms": "14.2 ms",
            "packet_loss": "8.5%",
            "throughput": "15.0 Mbps",
            "cpu": "91%",
            "memory": "88.0%",
            "queue_drops": "42",
            "interface_errors": "0",
            "signal": "-78.5 dBm"
        }
    }
    cim = TelemetryNormalizer.normalize_single(v3_raw)
    assert cim.device_id == "AP-HOSTEL-A1"
    assert cim.schema_version_detected == SchemaVersion.V3
    assert cim.metrics.latency_ms == 125.4
    assert cim.metrics.jitter_ms == 14.2
    assert cim.metrics.packet_loss_pct == 8.5
    assert cim.metrics.cpu_pct == 91.0
    assert cim.metrics.queue_drops == 42
    assert cim.metrics.signal_strength_dbm == -78.5


def test_missing_values_mapped_strictly_to_none():
    sparse_raw = {
        "device_id": "SPARSE-01",
        "metrics": {
            "latency_ms": 22.0
        }
    }
    cim = TelemetryNormalizer.normalize_single(sparse_raw)
    # Must explicitly be None, NEVER defaulted to 0
    assert cim.metrics.latency_ms == 22.0
    assert cim.metrics.packet_loss_pct is None
    assert cim.metrics.cpu_pct is None
    assert cim.metrics.queue_drops is None
    assert cim.metrics.interface_errors is None
    assert "packet_loss_pct" in cim.missing_metrics_list()
    assert cim.is_metric_present("packet_loss_pct") is False


def test_invalid_values_rejection():
    corrupt_raw = {
        "device_id": "BAD-01",
        "metrics": {
            "latency_ms": "NaN",
            "packet_loss_pct": "unknown_string",
            "queue_drops": "corrupt_data",
            "cpu_pct": math.inf
        }
    }
    cim = TelemetryNormalizer.normalize_single(corrupt_raw)
    assert cim.metrics.latency_ms is None
    assert cim.metrics.packet_loss_pct is None
    assert cim.metrics.queue_drops is None
    assert cim.metrics.cpu_pct is None
    assert len(cim.normalization_warnings) >= 4
