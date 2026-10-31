"""NetCoop AI Cryptographically Protected Central Evidence Ledger.

Implements a tamper-evident, cryptographically chained audit ledger (Merkle-style SHA-256 hash chain),
frozen immutable Pydantic entries, canonical JSON message serialization, and cross-agent contradiction resolution.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

from protocol.models import AgentFinding, AgentMessage, HypothesisType


class LedgerEntry(BaseModel):
    """Cryptographically chained immutable entry in the diagnostic evidence ledger."""
    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(default_factory=lambda: f"LEDGER-{uuid.uuid4().hex[:8].upper()}")
    correlation_id: str
    prev_hash: str = Field(description="SHA-256 hash of previous ledger entry, ensuring immutability")
    entry_hash: str = Field(description="SHA-256 signature of this entry's canonical payload")
    agent_id: str
    device_id: str
    metric_name: str
    observed_value: Any
    finding_summary: str
    polarity: str = Field(description="SUPPORTS | CONTRADICTS | NEUTRAL")
    target_hypothesis: str
    weight: float = 1.0
    recorded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        correlation_id: str,
        prev_hash: str,
        agent_id: str,
        device_id: str,
        metric_name: str,
        observed_value: Any,
        finding_summary: str,
        polarity: str,
        target_hypothesis: str,
        weight: float = 1.0,
        recorded_at: Optional[str] = None
    ) -> LedgerEntry:
        """Construct a cryptographically signed immutable ledger entry."""
        rec_time = recorded_at or datetime.now(timezone.utc).isoformat()
        # Compute canonical hash payload preserving native JSON typing
        canonical_dict = {
            "correlation_id": correlation_id,
            "prev_hash": prev_hash,
            "agent_id": agent_id,
            "device_id": device_id,
            "metric_name": metric_name,
            "observed_value": observed_value,
            "finding_summary": finding_summary,
            "polarity": polarity,
            "target_hypothesis": target_hypothesis,
            "weight": weight,
            "recorded_at": rec_time
        }
        canonical_str = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':'), default=str)
        computed_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return cls(
            correlation_id=correlation_id,
            prev_hash=prev_hash,
            entry_hash=computed_hash,
            agent_id=agent_id,
            device_id=device_id,
            metric_name=metric_name,
            observed_value=observed_value,
            finding_summary=finding_summary,
            polarity=polarity,
            target_hypothesis=target_hypothesis,
            weight=weight,
            recorded_at=rec_time
        )


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
    """Tamper-evident, cryptographically chained evidence ledger with integrity verification."""

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, correlation_id: Optional[str] = None) -> None:
        self.correlation_id = correlation_id or f"CORR-{uuid.uuid4().hex[:8].upper()}"
        self.entries: List[LedgerEntry] = []
        self.contradictions: List[ContradictionRecord] = []
        self._seen_messages: set = set()
        self._last_hash: str = self.GENESIS_HASH

    def record_agent_findings(self, agent_id: str, findings: List[AgentFinding]) -> int:
        """Ingest findings from a specialized agent into the cryptographically chained ledger."""
        added = 0
        for f in findings:
            for ev in f.evidence:
                target_hyp = getattr(ev, "hypothesis_target", getattr(ev, "hypothesis", None))
                if hasattr(target_hyp, "value"):
                    target_hyp = target_hyp.value

                entry = LedgerEntry.create(
                    correlation_id=self.correlation_id,
                    prev_hash=self._last_hash,
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
                self._last_hash = entry.entry_hash
                added += 1
        return added

    def append_entry(
        self,
        correlation_id: str,
        agent_id: str,
        device_id: str,
        metric_name: str,
        observed_value: Any,
        finding_summary: str,
        polarity: str,
        target_hypothesis: str,
        weight: float = 1.0,
        recorded_at: Optional[str] = None
    ) -> LedgerEntry:
        """Manually append a single validated entry to the ledger hash chain."""
        entry = LedgerEntry.create(
            correlation_id=correlation_id or self.correlation_id,
            prev_hash=self._last_hash,
            agent_id=agent_id,
            device_id=device_id,
            metric_name=metric_name,
            observed_value=observed_value,
            finding_summary=finding_summary,
            polarity=polarity,
            target_hypothesis=target_hypothesis,
            weight=weight,
            recorded_at=recorded_at
        )
        self.entries.append(entry)
        self._last_hash = entry.entry_hash
        return entry

    def verify_chain_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic hash chain across all entries in the ledger.
        
        Returns:
            (is_valid, error_explanation)
        """
        expected_prev = self.GENESIS_HASH
        for idx, entry in enumerate(self.entries):
            # Check previous hash pointer
            if entry.prev_hash != expected_prev:
                return False, f"Broken hash chain at entry {idx} ({entry.entry_id}): expected prev_hash {expected_prev}, got {entry.prev_hash}"

            # Recompute canonical hash to detect in-memory tampering
            canonical_dict = {
                "correlation_id": entry.correlation_id,
                "prev_hash": entry.prev_hash,
                "agent_id": entry.agent_id,
                "device_id": entry.device_id,
                "metric_name": entry.metric_name,
                "observed_value": entry.observed_value,
                "finding_summary": entry.finding_summary,
                "polarity": entry.polarity,
                "target_hypothesis": entry.target_hypothesis,
                "weight": entry.weight,
                "recorded_at": entry.recorded_at
            }
            canonical_str = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':'), default=str)
            computed = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            if computed != entry.entry_hash:
                return False, f"Tampered entry detected at index {idx} ({entry.entry_id}): signature mismatch."

            expected_prev = entry.entry_hash

        return True, None

    def detect_and_resolve_contradictions(
        self,
        messages: List[AgentMessage],
        conflicted_devices: List[str]
    ) -> List[ContradictionRecord]:
        """Detect and formally arbitrate contradictions between reported claims and empirical metrics."""
        records: List[ContradictionRecord] = []
        for dev_id in conflicted_devices:
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

    def validate_message_integrity(self, message: AgentMessage | Any) -> bool:
        """Validate agent message structure and guard against duplicate delivery using cryptographic hashing."""
        if hasattr(message, "message_id"):
            canonical_msg = json.dumps({
                "message_id": getattr(message, "message_id"),
                "incident_id": getattr(message, "incident_id"),
                "agent_id": getattr(message, "agent_id"),
                "finding_type": getattr(message, "finding_type"),
                "device_id": getattr(message, "device_id")
            }, sort_keys=True, separators=(',', ':'))
        else:
            canonical_msg = json.dumps({
                "sender": getattr(message, "sender", "UNKNOWN"),
                "recipient": getattr(message, "recipient", "UNKNOWN"),
                "message_type": getattr(message, "message_type", "UNKNOWN"),
                "payload": getattr(message, "payload", {})
            }, sort_keys=True, separators=(',', ':'))
        msg_hash = hashlib.sha256(canonical_msg.encode("utf-8")).hexdigest()

        if msg_hash in self._seen_messages:
            return False  # Duplicate message detected
        self._seen_messages.add(msg_hash)
        return True

    def get_ledger_summary(self) -> Dict[str, Any]:
        """Return audit summary of ledger status and cryptographic health."""
        valid, err = self.verify_chain_integrity()
        return {
            "correlation_id": self.correlation_id,
            "total_entries": len(self.entries),
            "cryptographic_chain_valid": valid,
            "chain_root_hash": self.GENESIS_HASH,
            "chain_tip_hash": self._last_hash,
            "total_contradictions_resolved": len(self.contradictions),
            "participating_agents": sorted(list({e.agent_id for e in self.entries})),
            "monitored_devices": sorted(list({e.device_id for e in self.entries})),
        }
