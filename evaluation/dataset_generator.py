"""Independent Benchmark Dataset Generator for NetCoop AI.

Procedurally synthesizes 700+ diverse, ground-truth-labeled telemetry cases across:
- Normal Operation (100 cases)
- Link Congestion (100 cases)
- Physical Hardware/Link Failure (100 cases)
- Weak Wi-Fi / RF Degradation (100 cases)
- DNS/DHCP Service Outage (100 cases)
- Resource Exhaustion / CPU-Memory Pressure (100 cases)
- Insufficient Evidence / Ambiguous / Sparse Telemetry (100 cases)

Encodes cases across heterogeneous schemas (V1, V2, V3) and independently asserts ground truth.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Tuple

from protocol.models import HypothesisType, SchemaVersion


FIXED_BENCHMARK_REFERENCE_TIME = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


class BenchmarkCase(NamedTuple):
    case_id: str
    ground_truth_root_cause: str
    telemetry_payload: List[Dict[str, Any]]
    schema_version: SchemaVersion
    expected_abstention: bool
    reference_time: datetime = FIXED_BENCHMARK_REFERENCE_TIME


class DatasetGenerator:
    """Independent procedural dataset generator with deterministic random seeding and fixed reference time."""

    CAMPUS_DEVICES = [
        "IITBBS-CORE-SW-01", "DIST-SW-NORTH", "DIST-SW-SOUTH",
        "BLDG-SW-ENG", "BLDG-SW-HOSTEL-A", "BLDG-SW-HOSTEL-B",
        "AP-ENG-01", "AP-ENG-02", "AP-HOSTEL-A1", "AP-HOSTEL-B1",
        "SRV-DNS-01", "SRV-DHCP-01", "CLIENT-HA-101", "LAB-PC-ENG-01"
    ]

    def __init__(self, seed: int = 42, reference_time: Optional[datetime] = None) -> None:
        self.rng = random.Random(seed)
        self.reference_time = reference_time or FIXED_BENCHMARK_REFERENCE_TIME

    def generate_full_benchmark_suite(self, cases_per_class: int = 100) -> List[BenchmarkCase]:
        """Generate complete 700-case evaluation corpus."""
        dataset: List[BenchmarkCase] = []
        classes = [
            (HypothesisType.NORMAL_OPERATION.value, self._gen_normal),
            (HypothesisType.LINK_CONGESTION.value, self._gen_congestion),
            (HypothesisType.HARDWARE_FAILURE.value, self._gen_hardware),
            (HypothesisType.WEAK_WIFI.value, self._gen_wifi),
            (HypothesisType.DNS_DHCP_FAILURE.value, self._gen_dns_dhcp),
            ("RESOURCE_EXHAUSTION", self._gen_resource_exhaustion),
            (HypothesisType.INSUFFICIENT_EVIDENCE.value, self._gen_insufficient_evidence)
        ]

        for cause_name, gen_fn in classes:
            for idx in range(cases_per_class):
                case_id = f"BM-{cause_name[:4]}-{idx+1:03d}"
                schema = self.rng.choice([SchemaVersion.V1, SchemaVersion.V2, SchemaVersion.V3])
                payload, abstention = gen_fn(case_id, schema)
                dataset.append(BenchmarkCase(
                    case_id=case_id,
                    ground_truth_root_cause=cause_name,
                    telemetry_payload=payload,
                    schema_version=schema,
                    expected_abstention=abstention,
                    reference_time=self.reference_time
                ))

        return dataset

    def _encode_device(
        self,
        dev_id: str,
        metrics: Dict[str, Any],
        schema: SchemaVersion,
        status: str = "WARNING"
    ) -> Dict[str, Any]:
        """Format metrics dict into specific schema format with deterministic timestamp."""
        now_dt = self.reference_time
        ts_iso = now_dt.isoformat()
        ts_epoch = int(now_dt.timestamp())

        if schema == SchemaVersion.V2:
            v2_m: Dict[str, Any] = {}
            if "latency_ms" in metrics:
                v2_m["latency_sec"] = metrics["latency_ms"] / 1000.0
            if "jitter_ms" in metrics:
                v2_m["jitter_s"] = metrics["jitter_ms"] / 1000.0
            if "packet_loss_pct" in metrics:
                v2_m["packet_loss_ratio"] = metrics["packet_loss_pct"] / 100.0
            if "throughput_mbps" in metrics:
                v2_m["throughput_bps"] = int(metrics["throughput_mbps"] * 1e6)
            if "link_utilization_pct" in metrics:
                v2_m["link_utilization_ratio"] = metrics["link_utilization_pct"] / 100.0
            if "cpu_pct" in metrics:
                v2_m["cpu_utilization_ratio"] = metrics["cpu_pct"] / 100.0
            if "memory_pct" in metrics:
                v2_m["memory_utilization_ratio"] = metrics["memory_pct"] / 100.0
            if "queue_drops" in metrics:
                v2_m["queue_drops"] = metrics["queue_drops"]
            if "interface_errors" in metrics:
                v2_m["crc_errors"] = metrics["interface_errors"]
            if "signal_strength_dbm" in metrics:
                v2_m["rssi_dbm"] = metrics["signal_strength_dbm"]
            if "dns_resolution_ms" in metrics:
                v2_m["dns_latency_sec"] = metrics["dns_resolution_ms"] / 1000.0
            if "dhcp_lease_success" in metrics:
                v2_m["dhcp_lease_success"] = metrics["dhcp_lease_success"]

            return {
                "host_id": dev_id,
                "epoch_timestamp": ts_epoch,
                "status": status,
                "metrics": v2_m
            }

        elif schema == SchemaVersion.V3:
            v3_m: Dict[str, Any] = {}
            if "latency_ms" in metrics:
                v3_m["latency_ms"] = f"{metrics['latency_ms']} ms"
            if "packet_loss_pct" in metrics:
                v3_m["packet_loss_pct"] = f"{metrics['packet_loss_pct']}%"
            if "throughput_mbps" in metrics:
                v3_m["throughput_mbps"] = f"{metrics['throughput_mbps']} mbps"
            if "cpu_pct" in metrics:
                v3_m["cpu_pct"] = f"{metrics['cpu_pct']}%"
            if "memory_pct" in metrics:
                v3_m["memory_pct"] = f"{metrics['memory_pct']}%"
            if "queue_drops" in metrics:
                v3_m["queue_drops"] = str(metrics["queue_drops"])
            if "interface_errors" in metrics:
                v3_m["interface_errors"] = str(metrics["interface_errors"])
            if "signal_strength_dbm" in metrics:
                v3_m["signal_strength_dbm"] = f"{metrics['signal_strength_dbm']} dbm"
            if "dns_resolution_ms" in metrics:
                v3_m["dns_resolution_ms"] = f"{metrics['dns_resolution_ms']} ms"
            if "dhcp_lease_success" in metrics:
                v3_m["dhcp_lease_success"] = str(metrics["dhcp_lease_success"])

            return {
                "device_id": dev_id,
                "status": status,
                "metrics": v3_m
            }

        # V1 Baseline
        return {
            "device_id": dev_id,
            "timestamp": ts_iso,
            "status": status,
            "metrics": metrics
        }

    def _gen_normal(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = self.rng.choice(self.CAMPUS_DEVICES)
        metrics = {
            "latency_ms": round(self.rng.uniform(5.0, 25.0), 1),
            "jitter_ms": round(self.rng.uniform(1.0, 5.0), 1),
            "packet_loss_pct": 0.0,
            "throughput_mbps": round(self.rng.uniform(100.0, 800.0), 1),
            "link_utilization_pct": round(self.rng.uniform(15.0, 45.0), 1),
            "cpu_pct": round(self.rng.uniform(10.0, 40.0), 1),
            "memory_pct": round(self.rng.uniform(20.0, 50.0), 1),
            "queue_drops": 0,
            "interface_errors": 0
        }
        return [self._encode_device(dev, metrics, schema, "HEALTHY")], False

    def _gen_congestion(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = self.rng.choice(["BLDG-SW-ENG", "BLDG-SW-HOSTEL-A", "DIST-SW-NORTH"])
        metrics = {
            "latency_ms": round(self.rng.uniform(120.0, 280.0), 1),
            "jitter_ms": round(self.rng.uniform(25.0, 65.0), 1),
            "packet_loss_pct": round(self.rng.uniform(3.0, 12.0), 2),
            "throughput_mbps": round(self.rng.uniform(9200.0, 9900.0), 1),
            "link_utilization_pct": round(self.rng.uniform(88.0, 99.0), 1),
            "cpu_pct": round(self.rng.uniform(55.0, 75.0), 1),
            "memory_pct": round(self.rng.uniform(60.0, 80.0), 1),
            "queue_drops": self.rng.randint(60, 400),
            "interface_errors": 0
        }
        return [self._encode_device(dev, metrics, schema, "WARNING")], False

    def _gen_hardware(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = self.rng.choice(["DIST-SW-SOUTH", "BLDG-SW-HOSTEL-B", "IITBBS-CORE-SW-01"])
        metrics = {
            "latency_ms": round(self.rng.uniform(40.0, 150.0), 1),
            "jitter_ms": round(self.rng.uniform(10.0, 35.0), 1),
            "packet_loss_pct": round(self.rng.uniform(10.0, 35.0), 2),
            "throughput_mbps": round(self.rng.uniform(200.0, 1500.0), 1),
            "link_utilization_pct": round(self.rng.uniform(20.0, 50.0), 1),
            "cpu_pct": round(self.rng.uniform(20.0, 45.0), 1),
            "memory_pct": round(self.rng.uniform(30.0, 55.0), 1),
            "queue_drops": 0,
            "interface_errors": self.rng.randint(80, 850)
        }
        return [self._encode_device(dev, metrics, schema, "CRITICAL")], False

    def _gen_wifi(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = self.rng.choice(["AP-ENG-01", "AP-ENG-02", "AP-HOSTEL-A1", "AP-HOSTEL-B1"])
        metrics = {
            "latency_ms": round(self.rng.uniform(80.0, 180.0), 1),
            "jitter_ms": round(self.rng.uniform(20.0, 45.0), 1),
            "packet_loss_pct": round(self.rng.uniform(8.0, 25.0), 2),
            "throughput_mbps": round(self.rng.uniform(5.0, 25.0), 1),
            "link_utilization_pct": round(self.rng.uniform(10.0, 30.0), 1),
            "cpu_pct": round(self.rng.uniform(25.0, 50.0), 1),
            "signal_strength_dbm": round(self.rng.uniform(-88.0, -74.0), 1),
            "queue_drops": 0,
            "interface_errors": 0
        }
        return [self._encode_device(dev, metrics, schema, "WARNING")], False

    def _gen_dns_dhcp(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        client = self.rng.choice(["CLIENT-HA-101", "LAB-PC-ENG-01"])
        srv = "SRV-DNS-01"
        c_metrics = {
            "latency_ms": 15.0,
            "packet_loss_pct": 0.0,
            "dns_resolution_ms": round(self.rng.uniform(250.0, 1200.0), 1),
            "dhcp_lease_success": self.rng.choice([True, False])
        }
        s_metrics = {
            "latency_ms": 10.0,
            "packet_loss_pct": 0.0,
            "cpu_pct": 88.0,
            "dns_resolution_ms": 950.0
        }
        return [
            self._encode_device(client, c_metrics, schema, "WARNING"),
            self._encode_device(srv, s_metrics, schema, "CRITICAL")
        ], False

    def _gen_resource_exhaustion(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = self.rng.choice(["IITBBS-CORE-SW-01", "DIST-SW-NORTH"])
        metrics = {
            "latency_ms": round(self.rng.uniform(30.0, 60.0), 1),
            "cpu_pct": round(self.rng.uniform(94.0, 99.5), 1),
            "memory_pct": round(self.rng.uniform(92.0, 98.5), 1),
            "queue_drops": 0,
            "interface_errors": 0,
            "link_utilization_pct": 35.0
        }
        return [self._encode_device(dev, metrics, schema, "WARNING")], False

    def _gen_insufficient_evidence(self, case_id: str, schema: SchemaVersion) -> Tuple[List[Dict[str, Any]], bool]:
        dev = "UNKNOWN-NODE-X"
        # Critically sparse metrics: only 1 metric present with no anomaly
        metrics = {
            "latency_ms": 18.0
        }
        return [self._encode_device(dev, metrics, schema, "UNKNOWN")], True
