"""Comprehensive Evaluation Laboratory & Benchmark Runner for NetCoop AI.

Executes a 700-case scientific benchmark evaluating:
- Multi-class diagnostic accuracy
- Per-class Precision, Recall, and Macro-F1
- Confusion Matrix
- Brier Score and Expected Calibration Error (ECE)
- Abstention Quality on incomplete telemetry
- Interoperability equivalence rate across schemas
- Processing latency percentiles
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.confidence_engine import ConfidenceEngine
from core.orchestrator import NetworkIntelligenceOrchestrator
from evaluation.dataset_generator import DatasetGenerator
from protocol.models import HypothesisType


class BenchmarkRunner:
    """Scientific benchmarking laboratory engine."""

    def __init__(self, cases_per_class: int = 100) -> None:
        self.cases_per_class = cases_per_class
        self.orchestrator = NetworkIntelligenceOrchestrator()
        self.generator = DatasetGenerator(seed=1337)

    def run_full_benchmark(self) -> Dict[str, Any]:
        """Execute full benchmark cycle across all synthetic cases."""
        print(f"Generating synthetic benchmark suite ({self.cases_per_class} cases per class)...")
        dataset = self.generator.generate_full_benchmark_suite(cases_per_class=self.cases_per_class)
        total_cases = len(dataset)
        print(f"Executing {total_cases} benchmark scenarios through NetCoop AI Orchestrator...")

        start_time = time.time()
        latencies: List[float] = []

        # Tracking structures
        confusion_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        all_classes = set()
        correct_predictions = 0

        # Calibration tracking (Top-label & Multiclass Brier score & ECE)
        brier_sum = 0.0
        multiclass_brier_sum = 0.0
        diagnosed_cases = 0
        calibration_bins: Dict[int, List[Tuple[float, int]]] = defaultdict(list)  # bin_idx -> [(confidence, is_correct)]

        # Abstention tracking
        expected_abstentions = 0
        actual_abstentions = 0
        correct_abstentions = 0

        for case in dataset:
            all_classes.add(case.ground_truth_root_cause)
            t0 = time.time()
            res = self.orchestrator.process(
                raw_input=case.telemetry_payload,
                incident_id=case.case_id,
                reference_time=case.reference_time
            )
            dur_ms = (time.time() - t0) * 1000.0
            latencies.append(dur_ms)

            predicted = res.report.suspected_root_cause
            confidence = res.report.confidence
            gt = case.ground_truth_root_cause

            is_correct = (predicted == gt)
            if is_correct:
                correct_predictions += 1

            confusion_matrix[gt][predicted] += 1

            # Brier Score & ECE computation on diagnosed (non-abstention) cases
            # Abstention cases are evaluated separately via Abstention Precision & Recall
            if gt != HypothesisType.INSUFFICIENT_EVIDENCE.value:
                diagnosed_cases += 1
                # res.report.confidence is already calibrated by CorrelationAgent; avoids double-calibration
                cal_conf = confidence
                brier_sum += (cal_conf - (1.0 if is_correct else 0.0)) ** 2

                # Multiclass probability distribution across all non-abstention classes
                rem_prob = (1.0 - cal_conf) / 5.0  # 6 active fault classes total
                mc_case_err = (cal_conf - (1.0 if is_correct else 0.0)) ** 2
                for other_c in [c for c in all_classes if c not in (predicted, HypothesisType.INSUFFICIENT_EVIDENCE.value)]:
                    is_other_gt = 1.0 if other_c == gt else 0.0
                    mc_case_err += (rem_prob - is_other_gt) ** 2
                multiclass_brier_sum += mc_case_err

                bin_idx = min(9, int(cal_conf * 10))
                calibration_bins[bin_idx].append((cal_conf, 1 if is_correct else 0))

            # Abstention tracking
            if case.expected_abstention:
                expected_abstentions += 1
                if predicted == HypothesisType.INSUFFICIENT_EVIDENCE.value:
                    correct_abstentions += 1
            if predicted == HypothesisType.INSUFFICIENT_EVIDENCE.value:
                actual_abstentions += 1

        total_time = time.time() - start_time

        # Compute per-class precision, recall, F1
        per_class_metrics: Dict[str, Dict[str, float]] = {}
        f1_list: List[float] = []

        for c in sorted(all_classes):
            # True Positives
            tp = confusion_matrix[c][c]
            # False Positives
            fp = sum(confusion_matrix[other][c] for other in all_classes if other != c)
            # False Negatives
            fn = sum(confusion_matrix[c][other] for other in all_classes if other != c)

            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

            per_class_metrics[c] = {
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
                "support": sum(confusion_matrix[c].values())
            }
            f1_list.append(f1)

        macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0.0
        accuracy = correct_predictions / total_cases
        top_brier_score = brier_sum / diagnosed_cases if diagnosed_cases > 0 else 0.0
        multiclass_brier = multiclass_brier_sum / diagnosed_cases if diagnosed_cases > 0 else 0.0

        # Calculate Expected Calibration Error (ECE) and compile 10-bin reliability diagram
        ece = 0.0
        reliability_diagram: List[Dict[str, Any]] = []
        for b_idx in range(10):
            items = calibration_bins[b_idx]
            cnt = len(items)
            if cnt > 0:
                avg_conf = sum(x[0] for x in items) / cnt
                avg_acc = sum(x[1] for x in items) / cnt
                weight = cnt / diagnosed_cases
                ece += weight * abs(avg_acc - avg_conf)
                reliability_diagram.append({
                    "bin": f"{b_idx * 0.1:.1f} - {(b_idx + 1) * 0.1:.1f}",
                    "sample_count": cnt,
                    "mean_predicted_confidence": round(avg_conf, 3),
                    "empirical_accuracy": round(avg_acc, 3),
                    "calibration_gap": round(abs(avg_acc - avg_conf), 3)
                })
            else:
                reliability_diagram.append({
                    "bin": f"{b_idx * 0.1:.1f} - {(b_idx + 1) * 0.1:.1f}",
                    "sample_count": 0,
                    "mean_predicted_confidence": 0.0,
                    "empirical_accuracy": 0.0,
                    "calibration_gap": 0.0
                })

        # Abstention precision & recall
        abstention_prec = correct_abstentions / actual_abstentions if actual_abstentions > 0 else 1.0
        abstention_rec = correct_abstentions / expected_abstentions if expected_abstentions > 0 else 1.0

        latencies.sort()
        mean_lat = sum(latencies) / len(latencies) if latencies else 0.0
        p50_lat = latencies[len(latencies) // 2] if latencies else 0.0
        p95_lat = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_scenarios_evaluated": total_cases,
            "overall_accuracy": round(accuracy * 100.0, 2),
            "macro_f1_score": round(macro_f1, 4),
            "top_label_brier_score": round(top_brier_score, 4),
            "multiclass_brier_score": round(multiclass_brier, 4),
            "expected_calibration_error": round(ece, 4),
            "abstention_quality": {
                "precision": round(abstention_prec, 4),
                "recall": round(abstention_rec, 4),
                "expected": expected_abstentions,
                "actual": actual_abstentions
            },
            "reliability_diagram": reliability_diagram,
            "latency_metrics_ms": {
                "mean": round(mean_lat, 2),
                "p50": round(p50_lat, 2),
                "p95": round(p95_lat, 2),
                "total_run_time_sec": round(total_time, 2)
            },
            "per_class_metrics": per_class_metrics,
            "confusion_matrix": {k: dict(v) for k, v in confusion_matrix.items()}
        }

        # Save to disk
        out_path = PROJECT_ROOT / "evaluation" / "benchmark_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        self._print_summary(report)
        return report

    def _print_summary(self, rep: Dict[str, Any]) -> None:
        """Render clean terminal summary table."""
        print("\n" + "=" * 78)
        print("        NetCoop AI — Comprehensive Scientific Benchmark Report")
        print("=" * 78)
        print(f"Total Scenarios Evaluated: {rep['total_scenarios_evaluated']}")
        print(f"Overall Accuracy:          {rep['overall_accuracy']}%")
        print(f"Macro-F1 Score:            {rep['macro_f1_score']}")
        print(f"Top-Label Brier Score:     {rep['top_label_brier_score']} (0.0 = perfect calibration)")
        print(f"Multiclass Brier Score:    {rep['multiclass_brier_score']}")
        print(f"Expected Calibration Error:{rep['expected_calibration_error']}")
        print(f"Abstention Quality:        Prec: {rep['abstention_quality']['precision']*100}% | Rec: {rep['abstention_quality']['recall']*100}%")
        print(f"Latency:                   Mean: {rep['latency_metrics_ms']['mean']}ms | P95: {rep['latency_metrics_ms']['p95']}ms")
        print("-" * 78)
        print(f"{'Root Cause Class':<30} | {'Prec':<8} | {'Recall':<8} | {'F1-Score':<8} | {'Support'}")
        print("-" * 78)
        for c_name, m in rep["per_class_metrics"].items():
            print(f"{c_name:<30} | {m['precision']:<8.3f} | {m['recall']:<8.3f} | {m['f1_score']:<8.3f} | {m['support']}")
        print("-" * 78)
        print(f"{'Confidence Bin':<16} | {'Samples':<8} | {'Avg Conf':<10} | {'Accuracy':<10} | {'Gap'}")
        print("-" * 78)
        for row in rep["reliability_diagram"]:
            if row["sample_count"] > 0:
                print(f"{row['bin']:<16} | {row['sample_count']:<8} | {row['mean_predicted_confidence']:<10.3f} | {row['empirical_accuracy']:<10.3f} | {row['calibration_gap']:<8.3f}")
        print("=" * 78)
        print(f"Report exported to: evaluation/benchmark_report.json\n")


if __name__ == "__main__":
    cases = 50 if "--quick" in sys.argv else 100
    runner = BenchmarkRunner(cases_per_class=cases)
    runner.run_full_benchmark()
