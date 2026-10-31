"""Synthetic Telemetry Generator for NetCoop AI.

Generates realistic campus network telemetry with configurable noise, missing metrics,
and multi-version schema encoding (Page 4 of NetCoop AI spec).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class SyntheticTelemetryGenerator:
    """Generates synthetic campus network telemetry for testing and validation."""

    DEFAULT_DEVICES = [
        "IITBBS-CORE-SW-01",
        "IITBBS-DIST-ACADEMIC",
        "IITBBS-DIST-HOSTELS",
        "IITBBS-SW-MHR",
        "IITBBS-SW-SES",
        "AP-MHR-W1",
        "CLIENT-MHR-101"
    ]

    @classmethod
    def generate_scenario(
        cls,
        scenario_type: str = "normal",
        schema_version: str = "V1",
        noise_level: float = 0.05,
        missing_rate: float = 0.0
    ) -> Dict[str, Any]:
        """Generate a complete synthetic scenario payload."""
        now_iso = datetime.now(timezone.utc).isoformat()
        records: List[Dict[str, Any]] = []

        scenario_type = scenario_type.lower()
        schema_version = schema_version.upper()

        for dev in cls.DEFAULT_DEVICES:
            # Baseline nominal metrics
            lat_ms = round(random.uniform(5.0, 20.0) + (noise_level * 10), 2)
            jit_ms = round(random.uniform(0.5, 3.0), 2)
            loss_pct = 0.0
            tp_mbps = round(random.uniform(100.0, 950.0), 1)
            cpu = round(random.uniform(15.0, 35.0), 1)
            mem = round(random.uniform(25.0, 45.0), 1)
            drops = 0
            errs = 0
            signal = -58.0 if "AP" in dev or "CLIENT" in dev else None
            dns_ms = 12.0
            dhcp_ok = True
            status = "HEALTHY"

            # Inject fault signatures
            if scenario_type == "congestion" and ("SW-MHR" in dev or "MHR" in dev):
                lat_ms = round(random.uniform(160.0, 240.0), 1)
                jit_ms = round(random.uniform(25.0, 45.0), 1)
                loss_pct = round(random.uniform(4.0, 8.5), 2)
                drops = random.randint(80, 220)
                errs = 0  # Crucial: zero physical errors distinguishes congestion
                status = "WARNING"

            elif scenario_type == "hardware_failure" and "SW-MHR" in dev:
                loss_pct = round(random.uniform(12.0, 18.0), 2)
                errs = random.randint(450, 1200)  # High CRC errors
                lat_ms = 18.0
                status = "HEALTHY"  # Intentionally untrusted generator status

            elif scenario_type == "weak_wifi" and ("AP" in dev or "CLIENT" in dev):
                signal = round(random.uniform(-88.0, -82.0), 1)  # Weak RF
                lat_ms = round(random.uniform(85.0, 120.0), 1)
                loss_pct = round(random.uniform(8.0, 15.0), 2)
                status = "DEGRADED"

            elif scenario_type == "dns_dhcp_failure" and "CORE" in dev:
                dns_ms = round(random.uniform(2500.0, 4000.0), 1)
                dhcp_ok = False
                cpu = 96.5
                status = "CRITICAL"

            # Apply Schema Transformations
            rec: Dict[str, Any] = {}
            if schema_version == "V2":
                # V2: Renamed fields & units in seconds and ratios
                metrics_v2: Dict[str, Any] = {
                    "latency_sec": round(lat_ms / 1000.0, 4),
                    "jitter_s": round(jit_ms / 1000.0, 4),
                    "packet_loss_ratio": round(loss_pct / 100.0, 4),
                    "throughput_bps": int(tp_mbps * 1_000_000),
                    "cpu_utilization_ratio": round(cpu / 100.0, 2),
                    "memory_utilization_ratio": round(mem / 100.0, 2),
                    "queue_drops": drops,
                    "crc_errors": errs
                }
                if signal is not None:
                    metrics_v2["rssi_dbm"] = signal
                rec = {
                    "host_id": dev,
                    "epoch_timestamp": int(datetime.now(timezone.utc).timestamp()),
                    "status": status,
                    "metrics": metrics_v2
                }
            elif schema_version == "V3":
                # V3: String numbers with unit suffixes, missing timestamps
                metrics_v3: Dict[str, Any] = {
                    "latency_ms": f"{lat_ms} ms",
                    "jitter_ms": f"{jit_ms} ms",
                    "packet_loss": f"{loss_pct}%",
                    "throughput": f"{tp_mbps} Mbps",
                    "cpu": f"{cpu}%",
                    "memory": f"{mem}%",
                    "queue_drops": str(drops),
                    "interface_errors": str(errs)
                }
                if signal is not None:
                    metrics_v3["signal"] = f"{signal} dBm"
                rec = {
                    "device": dev,
                    "status": status,
                    "metrics": metrics_v3
                }
            else:
                # V1: Standard baseline schema
                metrics_v1: Dict[str, Any] = {
                    "latency_ms": lat_ms,
                    "jitter_ms": jit_ms,
                    "packet_loss_pct": loss_pct,
                    "throughput_mbps": tp_mbps,
                    "cpu_pct": cpu,
                    "memory_pct": mem,
                    "queue_drops": drops,
                    "interface_errors": errs
                }
                if signal is not None:
                    metrics_v1["signal_strength_dbm"] = signal
                if scenario_type == "dns_dhcp_failure":
                    metrics_v1["dns_resolution_ms"] = dns_ms
                    metrics_v1["dhcp_lease_success"] = dhcp_ok

                # Random missing metrics injection
                if missing_rate > 0.0:
                    for k in list(metrics_v1.keys()):
                        if random.random() < missing_rate:
                            metrics_v1[k] = None

                rec = {
                    "device_id": dev,
                    "timestamp": now_iso,
                    "status": status,
                    "metrics": metrics_v1
                }

            records.append(rec)

        return {
            "scenario_id": f"SYNTHETIC_{scenario_type.upper()}_{schema_version}",
            "generated_at": now_iso,
            "scenario_type": scenario_type,
            "schema_version": schema_version,
            "telemetry": records
        }


def main():
    parser = argparse.ArgumentParser(description="NetCoop AI Synthetic Telemetry Generator")
    parser.add_argument("--scenario", choices=["normal", "congestion", "hardware_failure", "weak_wifi", "dns_dhcp_failure"], default="congestion")
    parser.add_argument("--schema", choices=["V1", "V2", "V3"], default="V1")
    parser.add_argument("--noise", type=float, default=0.05)
    parser.add_argument("--missing", type=float, default=0.0)
    parser.add_argument("--output", type=str, help="Save to JSON file")

    args = parser.parse_args()
    data = SyntheticTelemetryGenerator.generate_scenario(
        scenario_type=args.scenario,
        schema_version=args.schema,
        noise_level=args.noise,
        missing_rate=args.missing
    )

    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Generated synthetic telemetry saved to {p}")
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
