"""NetCoop AI Central Evidence Ledger & Cross-Agent Consensus Audit.

Implements an immutable ledger of findings, contradiction detection across agents,
correlation IDs, message integrity validation, and end-to-end orchestration tracing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from protocol.models import AgentFinding, AgentMessage, HypothesisType


class LedgerEntry(BaseModel):
    """Immutable entry in the central diagnostic evidence ledger."""
    entry_id: str = Field(default_factory=lambda: f"LEDGER-{uuid.uuid4().hex[:8].upper()}")
    correlation_id: str
    agent_id: str
    device_id: str
    metric_name: str
    observed_value: Any
    finding_summary: str
    polarity: str = Field(description="SUPPORTS | CONTRADICTS | NEUTRAL")
    target_hypothesis: str
    weight: float = 1.0
    recorded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContradictionRecord(BaseModel):
    """Explicit audit record of cross-agent metric/label contradictions."""
    contradiction_id: str = Field(default_factory=lambda: f"CONTRA-{uuid.uuid4().hex[:6].upper()}")
    device_id: str
    claim_a: Dict[str, Any]
    claim_b: Dict[str, Any]
    resolution_strategy: str
    resolution_winner: str
    justification: str


class EvidenceLedger:
    """Central ledger maintaining structured findings, audit traces, and conflict resolutions."""

    def __init__(self, correlation_id: Optional[str] = None) -> None:
        self.correlation_id = correlation_id or f"CORR-{uuid.uuid4().hex[:8].upper()}"
        self.entries: List[LedgerEntry] = []
        self.contradictions: List[ContradictionRecord] = []
        self._seen_messages: set = set()

    def record_agent_findings(self, agent_id: str, findings: List[AgentFinding]) -> int:
        """Ingest findings from a specialized agent into the central ledger."""
        added = 0
        for f in findings:
            for ev in f.evidence:
                target_hyp = getattr(ev, "hypothesis_target", getattr(ev, "hypothesis", None))
                if hasattr(target_hyp, "value"):
                    target_hyp = target_hyp.value
                entry = LedgerEntry(
                    correlation_id=self.correlation_id,
                    agent_id=agent_id,
                    device_id=f.device_id,
                    metric_name=ev.metric_name,
                    observed_value=ev.observed_value,
                    finding_summary=ev.description,
                    polarity=ev.polarity,
                    target_hypothesis=str(target_hyp or "UNKNOWN"),
                    weight=ev.weight
                )
                self.entries.append(entry)
                added += 1
        return added

    def detect_and_resolve_contradictions(
        self,
        messages: List[AgentMessage],
        conflicted_devices: List[str]
    ) -> List[ContradictionRecord]:
        """Detect and formally arbitrate contradictions between reported claims and empirical metrics."""
        records: List[ContradictionRecord] = []
        for dev_id in conflicted_devices:
            # Find evidence supporting fault on this device
            fault_entries = [e for e in self.entries if e.device_id == dev_id and e.polarity == "SUPPORTS"]
            rec = ContradictionRecord(
                device_id=dev_id,
                claim_a={
                    "source": "Reported Generator Label",
                    "claim": "HEALTHY",
                    "basis": "Untrusted status string in raw payload"
                },
                claim_b={
                    "source": "Empirical Multi-Agent Metrics",
                    "claim": "ANOMALOUS",
                    "basis": [f"{e.metric_name}={e.observed_value}" for e in fault_entries[:3]]
                },
                resolution_strategy="DETERMINISTIC_METRIC_SUPREMACY",
                resolution_winner="Empirical Multi-Agent Metrics",
                justification="Physical telemetry and interface error counters override untrusted status strings per Section 4.3 specification."
            )
            records.append(rec)
            self.contradictions.append(rec)
        return records

    def validate_message_integrity(self, message: AgentMessage) -> bool:
        """Validate agent message structure and guard against duplicate delivery."""
        msg_sig = (message.sender, message.recipient, message.message_type, str(message.payload))
        if msg_sig in self._seen_messages:
            return False  # Duplicate message detected
        self._seen_messages.add(msg_sig)
        return True

    def get_ledger_summary(self) -> Dict[str, Any]:
        """Return audit summary of ledger status."""
        return {
            "correlation_id": self.correlation_id,
            "total_entries": len(self.entries),
            "total_contradictions_resolved": len(self.contradictions),
            "participating_agents": list({e.agent_id for e in self.entries}),
            "monitored_devices": list({e.device_id for e in self.entries}),
        }
