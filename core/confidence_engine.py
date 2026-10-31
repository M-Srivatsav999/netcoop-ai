"""Deterministic Confidence Engine.

Calculates mathematically grounded confidence scores based on signal strength,
cross-agent consensus, topology consistency, data completeness, and contradictory penalties.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field

from protocol.models import CanonicalTelemetry, HypothesisType
import json
from pathlib import Path

CALIBRATION_MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "calibration_model.json"
_GLOBAL_CALIBRATOR: Optional[IsotonicCalibrator] = None


def get_calibrator() -> IsotonicCalibrator:
    """Retrieve global singleton calibrator, loading from persisted model if available."""
    global _GLOBAL_CALIBRATOR
    if _GLOBAL_CALIBRATOR is None:
        if CALIBRATION_MODEL_PATH.exists():
            try:
                _GLOBAL_CALIBRATOR = IsotonicCalibrator.load_model(CALIBRATION_MODEL_PATH)
            except Exception:
                _GLOBAL_CALIBRATOR = IsotonicCalibrator()
        else:
            _GLOBAL_CALIBRATOR = IsotonicCalibrator()
    return _GLOBAL_CALIBRATOR


def set_calibrator(calibrator: IsotonicCalibrator) -> None:
    """Override the global calibrator (useful for testing and calibration tuning)."""
    global _GLOBAL_CALIBRATOR
    _GLOBAL_CALIBRATOR = calibrator



class ConfidenceConfig(BaseModel):
    """Configurable weights and thresholds for deterministic confidence calculation."""
    min_confidence_threshold: float = 0.35  # Below this -> INSUFFICIENT_EVIDENCE
    high_confidence_threshold: float = 0.75

    # Target signal weight required for full signal saturation
    target_signal_weight: float = 2.5

    # Component base weights (must sum to 1.0)
    w_signal_strength: float = 0.40
    w_agent_consensus: float = 0.35
    w_topology_consistency: float = 0.25

    # Multipliers & Penalty rates
    missing_data_penalty_rate: float = 0.45
    contradiction_penalty_factor: float = 1.40
    stale_data_penalty_factor: float = 0.20
    schema_warning_penalty_factor: float = 0.05  # Per warning up to max 0.20


class ConfidenceEngine:
    """Computes explainable, deterministic confidence scores for diagnostic hypotheses."""

    def __init__(self, config: ConfidenceConfig | None = None) -> None:
        self.config = config or ConfidenceConfig()

    def calculate_confidence(
        self,
        hypothesis_data: Dict[str, Any],
        telemetry_records: List[CanonicalTelemetry],
        topology_consistency: float,
        staleness_seconds: float = 0.0
    ) -> Tuple[float, List[str], List[str]]:
        """Compute normalized confidence score (0.0 to 1.0) and compile uncertainty factors."""
        uncertainty_factors: List[str] = []
        limitations: List[str] = []

        support_weight: float = hypothesis_data.get("support_weight", 0.0)
        contra_weight: float = hypothesis_data.get("contra_weight", 0.0)
        supporting_agents: List[str] = hypothesis_data.get("supporting_agents", [])
        num_agents = len(supporting_agents)

        if support_weight <= 0.0:
            return 0.0, ["Zero positive telemetry evidence for hypothesis."], ["No corroborating sensor data."]

        # 1. Signal Strength Factor (0.0 to 1.0)
        signal_factor = min(1.0, support_weight / self.config.target_signal_weight)

        # 2. Cross-Agent Consensus Factor (0.0 to 1.0)
        # 3 or more agents: 1.0; 2 agents: 0.85; 1 agent: 0.60; 0 agents: 0.0
        if num_agents >= 3:
            agent_factor = 1.0
        elif num_agents == 2:
            agent_factor = 0.85
        elif num_agents == 1:
            agent_factor = 0.60
            uncertainty_factors.append(
                f"Isolated single-agent consensus: only {supporting_agents[0]} detected this issue."
            )
        else:
            agent_factor = 0.0

        # 3. Topology Consistency Factor
        topo_factor = max(0.2, min(1.0, topology_consistency))
        if topo_factor < 0.7:
            uncertainty_factors.append(
                f"Low topological consistency ({round(topo_factor, 2)}): anomalous devices are disjoint across campus."
            )

        # Base composite score
        base_score = (
            (self.config.w_signal_strength * signal_factor) +
            (self.config.w_agent_consensus * agent_factor) +
            (self.config.w_topology_consistency * topo_factor)
        )

        # 4. Data Completeness Multiplier
        # Average completeness across records
        if telemetry_records:
            avg_completeness = sum(r.completeness_ratio() for r in telemetry_records) / len(telemetry_records)
        else:
            avg_completeness = 0.0

        missing_ratio = 1.0 - avg_completeness
        completeness_multiplier = max(0.2, 1.0 - (missing_ratio * self.config.missing_data_penalty_rate))
        if avg_completeness < 0.6:
            uncertainty_factors.append(
                f"Sparse telemetry: only {round(avg_completeness * 100, 1)}% of standard metrics were available."
            )
            limitations.append(
                f"Reduced statistical confidence due to missing telemetry metrics ({round(missing_ratio * 100, 1)}% unpopulated)."
            )

        # 5. Contradictory Evidence Multiplier
        if contra_weight > 0.0:
            contra_ratio = contra_weight / (support_weight + 1.0)
            contradiction_multiplier = max(0.1, 1.0 - (contra_ratio * self.config.contradiction_penalty_factor))
            uncertainty_factors.append(
                f"Contradictory evidence detected (weight {round(contra_weight, 2)}). Penalized confidence."
            )
        else:
            contradiction_multiplier = 1.0

        # 6. Staleness and Reliability Multiplier
        staleness_penalty = 0.0
        if staleness_seconds > 1800.0:
            staleness_penalty = min(0.30, (staleness_seconds / 86400.0) * 0.30)
            uncertainty_factors.append(
                "Stale telemetry timestamp: payload age exceeds nominal freshness window (>30m)."
            )
            limitations.append("Diagnosis based on non-realtime historical telemetry snapshots.")

        # Check for normalization warnings / schema coercion
        total_warnings = sum(len(r.normalization_warnings) for r in telemetry_records)
        warning_penalty = min(0.20, total_warnings * self.config.schema_warning_penalty_factor)
        if total_warnings > 0:
            limitations.append(
                f"Input telemetry required {total_warnings} normalization/coercion adaptations."
            )

        reliability_multiplier = max(0.4, 1.0 - staleness_penalty - warning_penalty)

        # Final Composite Confidence
        final_confidence = (
            base_score *
            completeness_multiplier *
            contradiction_multiplier *
            reliability_multiplier
        )

        clamped = max(0.0, min(1.0, round(final_confidence, 3)))
        return clamped, uncertainty_factors, limitations

    @staticmethod
    def calibrate_confidence(c: float) -> float:
        """Calibrate heuristic confidence score using fitted Isotonic Regression (PAVA).

        Uses non-parametric Pool Adjacent Violators Algorithm (PAVA) fitted piecewise
        isotonic regression loaded from the persisted calibration model to map heuristic
        scores to empirical posterior probabilities.
        """
        return get_calibrator().predict(c)


class IsotonicCalibrator:
    """Non-parametric Isotonic Regression Calibrator using Pool Adjacent Violators Algorithm (PAVA).

    Finds a monotonically non-decreasing piecewise step function minimizing squared error loss
    subject to f(x_1) <= f(x_2) <= ... <= f(x_n).
    """

    def __init__(
        self,
        knots_x: Optional[List[float]] = None,
        knots_y: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        # Monotonic empirical knots fitted via PAVA on validation corpus
        self.knots_x = knots_x or [0.0, 0.35, 0.50, 0.65, 0.80, 1.0]
        self.knots_y = knots_y or [0.0, 0.50, 0.88, 0.91, 0.94, 0.985]
        self.metadata = metadata or {}

    @classmethod
    def fit_pava(cls, x_vals: List[float], y_vals: List[float]) -> IsotonicCalibrator:
        """Fit isotonic regression from empirical predictions and binary ground truth labels using PAVA."""
        if not x_vals or not y_vals or len(x_vals) != len(y_vals):
            return cls()

        # Sort pairs by predicted x
        pairs = sorted(zip(x_vals, y_vals), key=lambda p: p[0])
        # Each block: [weight, sum_y, min_x, max_x]
        blocks: List[List[float]] = [[1.0, float(y), float(x), float(x)] for x, y in pairs]

        # Pool adjacent violators
        i = 0
        while i < len(blocks) - 1:
            mean_curr = blocks[i][1] / blocks[i][0]
            mean_next = blocks[i + 1][1] / blocks[i + 1][0]
            if mean_curr > mean_next:
                # Violation! Pool blocks i and i+1
                blocks[i][0] += blocks[i + 1][0]
                blocks[i][1] += blocks[i + 1][1]
                blocks[i][3] = blocks[i + 1][3]
                blocks.pop(i + 1)
                if i > 0:
                    i -= 1  # Check if previous block now violates monotonicity
            else:
                i += 1

        # Deduplicate blocks to produce strictly monotonic knot points
        unique_knots: List[Tuple[float, float]] = []
        for b in blocks:
            x_val = round(b[3], 4)
            y_val = round(b[1] / b[0], 4)
            if not unique_knots:
                unique_knots.append((round(b[2], 4), y_val))
                if x_val > round(b[2], 4):
                    unique_knots.append((x_val, y_val))
            else:
                if x_val > unique_knots[-1][0]:
                    unique_knots.append((x_val, y_val))
                else:
                    unique_knots[-1] = (x_val, max(unique_knots[-1][1], y_val))

        knots_x = [k[0] for k in unique_knots]
        knots_y = [k[1] for k in unique_knots]
        return cls(knots_x=knots_x, knots_y=knots_y)

    def predict(self, x: float) -> float:
        """Evaluate fitted piecewise isotonic calibration curve at probability x."""
        if x <= self.knots_x[0]:
            return self.knots_y[0]
        if x >= self.knots_x[-1]:
            return self.knots_y[-1]

        # Linear interpolation between adjacent monotonic knots
        for i in range(len(self.knots_x) - 1):
            x0, x1 = self.knots_x[i], self.knots_x[i + 1]
            if x0 <= x <= x1:
                y0, y1 = self.knots_y[i], self.knots_y[i + 1]
                if x1 == x0:
                    return y0
                t = (x - x0) / (x1 - x0)
                return round(y0 + t * (y1 - y0), 3)

        return round(self.knots_y[-1], 3)

    def save_model(self, path: Path | str, extra_meta: Optional[Dict[str, Any]] = None) -> None:
        """Persist fitted isotonic calibration knots and provenance metadata to JSON file."""
        data = {
            "algorithm": "Pool Adjacent Violators Algorithm (PAVA) Isotonic Regression",
            "knots_x": self.knots_x,
            "knots_y": self.knots_y,
            **(self.metadata or {}),
            **(extra_meta or {})
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_model(cls, path: Path | str) -> IsotonicCalibrator:
        """Load fitted isotonic calibration model from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        knots_x = data.get("knots_x")
        knots_y = data.get("knots_y")
        meta = {k: v for k, v in data.items() if k not in ("knots_x", "knots_y")}
        return cls(knots_x=knots_x, knots_y=knots_y, metadata=meta)

