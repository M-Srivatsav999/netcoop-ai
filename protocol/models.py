"""Protocol models defining the Canonical Internal Message (CIM),

evidence structures, inter-agent messages, and final reporting schemas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SeverityLevel(str, Enum):
    """Deterministic severity classifications."""
    HEALTHY = "HEALTHY"
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class SchemaVersion(str, Enum):
    """Supported telemetry input schema versions."""
    V1 = "V1"  # Organizer-provided baseline
    V2 = "V2"  # Unit changed & renamed fields (seconds, ratios, bps)
    V3 = "V3"  # Inconsistent types, string numerics, missing timestamps
    UNKNOWN = "UNKNOWN"


class HypothesisType(str, Enum):
    """Deterministic diagnostic hypothesis types."""
    NORMAL_OPERATION = "NORMAL_OPERATION"
    LINK_CONGESTION = "LINK_CONGESTION"
    HARDWARE_FAILURE = "HARDWARE_FAILURE"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    WEAK_WIFI = "WEAK_WIFI"
    DNS_DHCP_FAILURE = "DNS_DHCP_FAILURE"
    UPSTREAM_SWITCH_FAILURE = "UPSTREAM_SWITCH_FAILURE"
    INTEROPERABILITY_SCHEMA_DEFECT = "INTEROPERABILITY_SCHEMA_DEFECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidencePolarity(str, Enum):
    """Polarity of an evidence item relative to a hypothesis."""
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class NormalizationWarning(BaseModel):
    """Structured audit trail for schema coercion and normalization actions."""
    field: str
    original_value: Any
    action_taken: str
    reason: str


class CanonicalMetrics(BaseModel):
    """Strict canonical representation of all telemetry measurements.
    
    Missing metrics are explicitly None and MUST NEVER be silently converted to 0.0.
    All metric units are standardized:
      - Latency: milliseconds (ms)
      - Jitter: milliseconds (ms)
      - Packet Loss: percentage (0.0 to 100.0)
      - Throughput: Megabits per second (Mbps)
      - CPU Utilization: percentage (0.0 to 100.0)
      - Memory Utilization: percentage (0.0 to 100.0)
      - Queue Drops: integer count
      - Interface Errors: integer count
      - Signal Strength: decibel-milliwatts (dBm, usually negative)
      - DNS Resolution: milliseconds (ms)
      - DHCP Lease Success: boolean flag
    """
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    throughput_mbps: Optional[float] = None
    cpu_pct: Optional[float] = None
    memory_pct: Optional[float] = None
    queue_drops: Optional[int] = None
    interface_errors: Optional[int] = None
    signal_strength_dbm: Optional[float] = None
    dns_resolution_ms: Optional[float] = None
    dhcp_lease_success: Optional[bool] = None

    @field_validator("packet_loss_pct", "cpu_pct", "memory_pct")
    @classmethod
    def validate_percentages(cls, value: Optional[float]) -> Optional[float]:
        if value is not None:
            if value < 0.0 or value > 100.0:
                # Clamp within reasonable physical bounds rather than crashing
                return max(0.0, min(100.0, value))
        return value


class CanonicalTelemetry(BaseModel):
    """The Canonical Internal Message (CIM) representing normalized telemetry for a single device."""
    device_id: str
    timestamp: Optional[datetime] = None
    reported_status: Optional[str] = None
    metrics: CanonicalMetrics = Field(default_factory=CanonicalMetrics)
    schema_version_detected: SchemaVersion = SchemaVersion.UNKNOWN
    normalization_warnings: List[NormalizationWarning] = Field(default_factory=list)
    raw_payload_preserved: Dict[str, Any] = Field(default_factory=dict)
    data_provenance: Dict[str, Any] = Field(default_factory=dict)

    def is_metric_present(self, metric_name: str) -> bool:
        """Return True if the specified metric has an explicitly recorded value."""
        val = getattr(self.metrics, metric_name, None)
        return val is not None

    def missing_metrics_list(self) -> List[str]:
        """Return list of all metrics that are None in this payload."""
        fields = [
            "latency_ms", "jitter_ms", "packet_loss_pct", "throughput_mbps",
            "cpu_pct", "memory_pct", "queue_drops", "interface_errors",
            "signal_strength_dbm", "dns_resolution_ms", "dhcp_lease_success"
        ]
        return [f for f in fields if getattr(self.metrics, f) is None]

    def completeness_ratio(self) -> float:
        """Fraction of available metrics that are populated (0.0 to 1.0)."""
        fields = [
            "latency_ms", "jitter_ms", "packet_loss_pct", "throughput_mbps",
            "cpu_pct", "memory_pct", "queue_drops", "interface_errors"
        ]
        present = sum(1 for f in fields if getattr(self.metrics, f) is not None)
        return round(present / len(fields), 4)


class EvidenceItem(BaseModel):
    """Structured atomic unit of diagnostic evidence generated by an agent."""
    evidence_id: str
    source_agent: str
    device_id: str
    metric_name: str
    observed_value: Any
    threshold_reference: Optional[str] = None
    severity: SeverityLevel
    polarity: EvidencePolarity
    hypothesis_target: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    timestamp: Optional[datetime] = None


class AgentFinding(BaseModel):
    """Structured analysis produced by an individual specialized agent for a device."""
    agent_name: str
    device_id: str
    overall_severity: SeverityLevel
    suspected_issues: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    missing_metrics: List[str] = Field(default_factory=list)
    notes: str = ""


class AgentMessage(BaseModel):
    """Explicit typed message passed between agents and orchestrator."""
    sender: str
    recipient: str
    message_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HypothesisEvaluation(BaseModel):
    """Evaluation breakdown for an individual candidate hypothesis."""
    hypothesis: str
    score: float
    supporting_signals: int
    contradictory_signals: int
    confidence: float
    explanation: str


class ArbitrationResult(BaseModel):
    """Central arbitration decision produced by the CorrelationAgent."""
    primary_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_devices: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    structured_evidence: List[StructuredEvidence] = Field(default_factory=list)
    contradictory_evidence: List[str] = Field(default_factory=list)
    alternative_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    uncertainty_factors: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    execution_trace_id: str = ""


class StructuredEvidence(BaseModel):
    """Structured evidence item conforming to Page 5 of the NetCoop AI specification."""
    metric: str
    value: Any
    interpretation: str


class IncidentSummary(BaseModel):
    """Summary of a single diagnosed incident within a multi-incident report."""
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_devices: List[str] = Field(default_factory=list)
    supporting_evidence: List[StructuredEvidence] = Field(default_factory=list)


class UnifiedIncidentReport(BaseModel):
    """The required hackathon unified report structure matching Page 5 of the specification.

    Includes explicit 'status', structured 'supporting_evidence', string 'alternative_causes',
    and explicit 'evidence_sources' agent attribution list.
    'incidents' is an optional list capturing all co-occurring fault diagnoses.
    """
    incident_id: str
    status: str = "diagnosed"  # "diagnosed" or "insufficient_evidence"
    suspected_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_devices: List[str]
    supporting_evidence: List[StructuredEvidence] = Field(default_factory=list)
    alternative_causes: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    incidents: List[IncidentSummary] = Field(
        default_factory=list,
        description="All co-occurring incidents detected (populated when multiple faults present)"
    )
