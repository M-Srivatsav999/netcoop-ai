"""Unit Tests for Tamper-Evident SHA-256 Hash-Chained Evidence Ledger.

Validates:
- Cryptographic hash chaining (prev_hash -> entry_hash)
- Strict immutable entry protection
- Detection of payload tampering (value, polarity, hypothesis)
- Detection of linkage breakage (prev_hash corruption)
- Preserving JSON typed values (distinguishing 1 from "1")
"""

import pytest
from core.evidence_ledger import EvidenceLedger, LedgerEntry
from protocol.models import AgentFinding, EvidenceItem, EvidencePolarity, SeverityLevel


def test_evidence_ledger_chain_integrity_valid():
    ledger = EvidenceLedger()
    assert ledger.verify_chain_integrity() == (True, None)

    # Append 3 entries
    e1 = ledger.append_entry("INC-1", "TelemetryAgent", "SW-1", "latency_ms", 120.0, "High latency", "SUPPORTS", "LINK_CONGESTION")
    e2 = ledger.append_entry("INC-1", "InfrastructureAgent", "SW-1", "queue_drops", 45, "Buffer drops", "SUPPORTS", "LINK_CONGESTION")
    e3 = ledger.append_entry("INC-1", "ConnectivityAgent", "SW-1", "packet_loss_pct", 8.0, "Packet loss", "SUPPORTS", "LINK_CONGESTION")

    assert len(ledger.entries) == 3
    assert e1.prev_hash == "0" * 64
    assert e2.prev_hash == e1.entry_hash
    assert e3.prev_hash == e2.entry_hash

    is_valid, err = ledger.verify_chain_integrity()
    assert is_valid is True
    assert err is None


def test_evidence_ledger_tampering_detection_modified_value():
    ledger = EvidenceLedger()
    ledger.append_entry("INC-2", "TelemetryAgent", "SW-2", "latency_ms", 150.0, "Critical latency", "SUPPORTS", "LINK_CONGESTION")
    ledger.append_entry("INC-2", "InfrastructureAgent", "SW-2", "queue_drops", 90, "Drops", "SUPPORTS", "LINK_CONGESTION")

    # Deliberately modify an entry by replacing it with a mutated record
    tampered_entry = LedgerEntry(
        entry_id=ledger.entries[0].entry_id,
        correlation_id=ledger.entries[0].correlation_id,
        prev_hash=ledger.entries[0].prev_hash,
        entry_hash=ledger.entries[0].entry_hash,  # Kept old hash!
        agent_id=ledger.entries[0].agent_id,
        device_id=ledger.entries[0].device_id,
        metric_name=ledger.entries[0].metric_name,
        observed_value=25.0,  # TAMPERED: changed from 150.0 to 25.0
        finding_summary="Normal latency",
        polarity="SUPPORTS",
        target_hypothesis="LINK_CONGESTION",
        weight=1.0,
        recorded_at=ledger.entries[0].recorded_at
    )
    ledger.entries[0] = tampered_entry

    is_valid, err = ledger.verify_chain_integrity()
    assert is_valid is False
    assert "Tampered entry detected at index 0" in err
    assert "signature mismatch" in err


def test_evidence_ledger_tampering_detection_broken_chain():
    ledger = EvidenceLedger()
    e1 = ledger.append_entry("INC-3", "TelemetryAgent", "SW-3", "latency_ms", 150.0, "Critical latency", "SUPPORTS", "LINK_CONGESTION")
    e2 = ledger.append_entry("INC-3", "InfrastructureAgent", "SW-3", "queue_drops", 90, "Drops", "SUPPORTS", "LINK_CONGESTION")

    # Deliberately modify prev_hash of entry 1
    tampered_e2 = LedgerEntry(
        entry_id=e2.entry_id,
        correlation_id=e2.correlation_id,
        prev_hash="a" * 64,  # TAMPERED: invalid previous hash pointer
        entry_hash=e2.entry_hash,
        agent_id=e2.agent_id,
        device_id=e2.device_id,
        metric_name=e2.metric_name,
        observed_value=e2.observed_value,
        finding_summary=e2.finding_summary,
        polarity=e2.polarity,
        target_hypothesis=e2.target_hypothesis,
        weight=e2.weight,
        recorded_at=e2.recorded_at
    )
    ledger.entries[1] = tampered_e2

    is_valid, err = ledger.verify_chain_integrity()
    assert is_valid is False
    assert "Broken hash chain at entry 1" in err


def test_evidence_ledger_typed_canonical_hashing():
    # Demonstrates that integer 1 and string "1" produce different cryptographic hashes
    entry_num = LedgerEntry.create("INC-4", "0"*64, "AgentA", "D-1", "m", 1, "desc", "SUPPORTS", "H1")
    entry_str = LedgerEntry.create("INC-4", "0"*64, "AgentA", "D-1", "m", "1", "desc", "SUPPORTS", "H1")

    assert entry_num.entry_hash != entry_str.entry_hash
    assert entry_num.observed_value == 1
    assert entry_str.observed_value == "1"


def test_evidence_ledger_record_findings_integration():
    ledger = EvidenceLedger()
    finding = AgentFinding(
        agent_name="TelemetryAgent",
        device_id="SW-CORE",
        overall_severity=SeverityLevel.CRITICAL,
        evidence=[
            EvidenceItem(
                evidence_id="EV-01",
                source_agent="TelemetryAgent",
                device_id="SW-CORE",
                metric_name="packet_loss_pct",
                observed_value=12.5,
                severity=SeverityLevel.CRITICAL,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target="HARDWARE_FAILURE",
                weight=0.9,
                description="Severe packet loss"
            )
        ]
    )
    ledger.record_agent_findings("TelemetryAgent", [finding])
    assert len(ledger.entries) == 1
    assert ledger.entries[0].observed_value == 12.5
    assert ledger.entries[0].target_hypothesis == "HARDWARE_FAILURE"

    is_valid, err = ledger.verify_chain_integrity()
    assert is_valid is True
    assert err is None
