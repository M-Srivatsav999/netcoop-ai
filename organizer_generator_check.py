"""Run the ORGANIZERS' Colab generator through NetCoop AI and summarize the results.

Put this file in the repo root (next to main.py) and run:  python organizer_generator_check.py
It prints, per fault type: the distribution of diagnosed root causes, mean confidence,
and which organizer fields were silently dropped by the normalizer.
"""
import json
import random
from collections import Counter
from datetime import datetime, timezone

from core.orchestrator import NetworkIntelligenceOrchestrator


# ---- Organizer's generator (copied from the Colab; only utcnow() made timezone-aware) ----
def generate_telemetry(fault_type="normal"):
    data = {
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "device_id": f"SW_CAMPUS_{random.randint(1, 10)}",
        "metrics": {},
    }
    if fault_type == "latency_spike":
        data["metrics"] = {
            "cpu_utilization_pct": round(random.uniform(40, 70), 2),
            "link_utilization_pct": round(random.uniform(60, 85), 2),
            "packet_loss_pct": round(random.uniform(0.1, 1.5), 2),
            "latency_ms": round(random.uniform(150, 400), 2),
            "jitter_ms": round(random.uniform(30, 80), 2),
            "queue_drops": random.randint(0, 50),
        }
        data["status"] = "Warning"
    elif fault_type == "hardware_failure":
        data["metrics"] = {
            "cpu_utilization_pct": 99.9,
            "link_utilization_pct": 100.0,
            "packet_loss_pct": round(random.uniform(15, 30), 2),
            "latency_ms": round(random.uniform(500, 1000), 2),
            "queue_drops": random.randint(5000, 15000),
            "interface_errors": random.randint(100, 500),
        }
        data["status"] = "Critical"
    else:
        data["metrics"] = {
            "cpu_utilization_pct": round(random.uniform(10, 35), 2),
            "link_utilization_pct": round(random.uniform(20, 50), 2),
            "packet_loss_pct": 0.0,
            "latency_ms": round(random.uniform(5, 20), 2),
            "jitter_ms": round(random.uniform(1, 5), 2),
            "queue_drops": 0,
        }
        data["status"] = "Healthy"
    return data
# ------------------------------------------------------------------------------------------

RUNS = 50
EXPECTED = {
    "normal": {"NORMAL_OPERATION"},
    "latency_spike": {"LINK_CONGESTION"},
    "hardware_failure": {"HARDWARE_FAILURE"},
}


def main() -> None:
    random.seed(7)
    orch = NetworkIntelligenceOrchestrator()
    for fault, expected in EXPECTED.items():
        causes, confs, statuses = Counter(), [], Counter()
        dropped = Counter()
        crashes = 0
        for _ in range(RUNS):
            raw = generate_telemetry(fault)
            try:
                res = orch.process(raw)
            except Exception as exc:  # a crash on organizer data is the worst outcome
                crashes += 1
                print(f"  CRASH on {fault}: {exc!r}")
                continue
            causes[res.report.suspected_root_cause] += 1
            statuses[res.report.status] += 1
            confs.append(res.report.confidence)
            metrics = res.canonical_telemetry[0].metrics
            org_to_canon = {
                "cpu_utilization_pct": "cpu_pct",
                "link_utilization_pct": "link_utilization_pct",
                "packet_loss_pct": "packet_loss_pct",
                "latency_ms": "latency_ms",
                "jitter_ms": "jitter_ms",
                "queue_drops": "queue_drops",
                "interface_errors": "interface_errors",
            }
            for org_field in raw["metrics"]:
                canon = org_to_canon.get(org_field)
                if canon is None:
                    dropped[org_field] += 1  # no canonical equivalent at all
                elif getattr(metrics, canon, None) is None:
                    dropped[org_field] += 1  # present in input, lost by the normalizer
        ok = sum(n for c, n in causes.items() if c in expected)
        mean_conf = sum(confs) / len(confs) if confs else 0.0
        print(f"\n=== {fault} (expected {sorted(expected)}) ===")
        print(f"  correct: {ok}/{RUNS}   crashes: {crashes}   mean confidence: {mean_conf:.2f}")
        print(f"  root causes: {dict(causes)}")
        print(f"  statuses:    {dict(statuses)}")
        if dropped:
            print(f"  organizer fields NOT making it into the canonical message: {dict(dropped)}")
    # One full report so you can eyeball the output format
    print("\n--- sample hardware_failure report ---")
    print(json.dumps(orch.process(generate_telemetry("hardware_failure")).report.model_dump(), indent=2, default=str)[:2500])


if __name__ == "__main__":
    main()
