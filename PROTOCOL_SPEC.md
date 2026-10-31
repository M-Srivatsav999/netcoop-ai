# NetCoop AI — Protocol & Interoperability Specification (CIM)

**Technical Specification Document — NetCoop AI Multi-Agent Diagnostic Engine**  
*Document Version: 2.0 | Target Campus: IIT Bhubaneswar | Evaluation Criteria Weight: 30%*

---

## 1. Overview & Architectural Scope

The NetCoop AI system achieves **Agent Interoperability** by decoupling heterogeneous vendor telemetry schemas from diagnostic reasoning. All incoming telemetry payloads are transformed into a strictly typed **Canonical Internal Message (CIM)** backed by Pydantic V2 data validation models.

---

## 2. Canonical Telemetry Data Dictionary

The `CanonicalTelemetry` entity defines the canonical representation for any network entity (Core Switch, Distribution Node, Building Switch, Access Point, Server, or End Device).

### Core Envelope Attributes

| Field Name | Type | Required | Default | Semantic Description |
| :--- | :--- | :---: | :---: | :--- |
| `device_id` | `str` | Yes | — | Unique network entity identifier (e.g. `IITBBS-SW-MHR`, `AP-MHR-W1`). |
| `timestamp` | `datetime` | No | `None` | Standardized UTC timestamp formatted as ISO8601 (`YYYY-MM-DDTHH:MM:SSZ`). |
| `reported_status` | `str` | No | `None` | Untrusted generator-provided status label (`HEALTHY`, `WARNING`, `CRITICAL`). |
| `metrics` | `CanonicalMetrics` | Yes | `()` | Standardized physical, link, transport, and application metrics. |
| `schema_version_detected` | `SchemaVersion` | Yes | `UNKNOWN`| Inferred schema version (`V1`, `V2`, `V3`). |
| `normalization_warnings` | `List[Warning]` | Yes | `[]` | Audit trail of all unit conversions, string coercions, or value rejections. |
| `data_provenance` | `Dict[str, Any]` | Yes | `{}` | Ingestion timestamp, original key count, and source metadata. |

---

## 3. Canonical Metrics Specification & Standard Units

Missing metrics are explicitly recorded as `None`. **They are never silently converted to `0.0` or assumed to represent healthy performance.**

| Metric Key | Canonical Unit | Type | Physical Bounds | Interpretation Guidelines |
| :--- | :---: | :---: | :---: | :--- |
| `latency_ms` | Milliseconds (`ms`) | `float` | $[0.0, \infty)$ | Round-trip packet delay. Normal: $<35\text{ms}$; Critical: $>100\text{ms}$. |
| `jitter_ms` | Milliseconds (`ms`) | `float` | $[0.0, \infty)$ | Packet delay variance. Normal: $<10\text{ms}$; Critical: $>25\text{ms}$. |
| `packet_loss_pct` | Percentage (`%`) | `float` | $[0.0, 100.0]$ | Packet loss ratio. Normal: $0.0\%$; Critical: $>5.0\%$. |
| `throughput_mbps` | Megabits/sec (`Mbps`) | `float` | $[0.0, \infty)$ | Effective transfer rate. Normal: $>50\text{Mbps}$; Degraded: $<20\text{Mbps}$. |
| `cpu_pct` | Percentage (`%`) | `float` | $[0.0, 100.0]$ | Control plane processor load. Normal: $<75\%$; Saturation: $>90\%$. |
| `memory_pct` | Percentage (`%`) | `float` | $[0.0, 100.0]$ | RAM allocation. Normal: $<80\%$; Critical: $>92\%$. |
| `queue_drops` | Counter (`drops`) | `int` | $[0, \infty)$ | Egress switchport tail-drops. Normal: $0$; Saturation: $>50$. |
| `interface_errors` | Counter (`errors`) | `int` | $[0, \infty)$ | Physical layer CRC, FCS, alignment errors. Normal: $0$; Fault: $>10$. |
| `signal_strength_dbm` | Decibel-milliwatts | `float` | $(-\infty, 0.0]$ | Wi-Fi RSSI. Excellent: $>-60\text{dBm}$; Severe Attenuation: $\le-75\text{dBm}$. |
| `dns_resolution_ms` | Milliseconds (`ms`) | `float` | $[0.0, \infty)$ | Name resolution latency. Normal: $<100\text{ms}$; Outage: $\ge500\text{ms}$. |
| `dhcp_lease_success` | Boolean | `bool` | `{True, False}`| Client IP lease acquisition status. `False` indicates pool exhaustion. |

---

## 4. Multi-Schema Normalization Mapping Matrix

The `TelemetryNormalizer` automatically identifies and adapts multi-vendor schema discrepancies:

```
[ Incoming Raw Telemetry ]
           │
           ├── Has `latency_sec`, `packet_loss_ratio`, `throughput_bps`? ──> [ SCHEMA V2 ]
           │                                                                     │
           │                                                                     ▼
           │                                                             Multiply sec by 1000
           │                                                             Multiply ratio by 100
           │                                                             Divide bps by 1,000,000
           │                                                             Map crc_errors -> interface_errors
           │
           ├── Has string numbers ("125.4 ms", "11.5%"), missing timestamps? ──> [ SCHEMA V3 ]
           │                                                                        │
           │                                                                        ▼
           │                                                                Regex unit stripping
           │                                                                Safe numeric coercion
           │                                                                Record coercion warnings
           │
           └── Conforms to baseline keys (`latency_ms`, `cpu_pct`)? ────────> [ SCHEMA V1 ]
                                                                                   │
                                                                                   ▼
                                                                           Direct Type Validation
```

### Detailed Coercion Rules:

1. **Schema V2 Conversions**:
   $$\text{latency\_ms} = \text{latency\_sec} \times 1000.0$$
   $$\text{jitter\_ms} = \text{jitter\_s} \times 1000.0$$
   $$\text{packet\_loss\_pct} = \text{packet\_loss\_ratio} \times 100.0$$
   $$\text{throughput\_mbps} = \frac{\text{throughput\_bps}}{1{,}000{,}000.0}$$
   $$\text{cpu\_pct} = \text{cpu\_utilization\_ratio} \times 100.0$$
   $$\text{interface\_errors} = \text{crc\_errors}$$

2. **Schema V3 Sanitization**:
   - Strips unit tokens (`"ms"`, `"s"`, `"sec"`, `"mbps"`, `"kbps"`, `"bps"`, `"%"`, `"dbm"`).
   - Rejects non-finite or corrupted values (`"NaN"`, `"Infinity"`, `"corrupt"`) and records a `NormalizationWarning` without crashing.

---

## 5. Inter-Agent Communication Envelopes

Agents exchange strictly typed contracts:

### 1. `AgentMessage`
```json
{
  "sender": "TelemetryAgent",
  "recipient": "Orchestrator",
  "message_type": "FINDINGS_READY",
  "payload": {
    "device_count": 4,
    "findings_count": 4
  },
  "timestamp": "2026-10-31T12:00:01.124Z"
}
```

### 2. `EvidenceItem`
```json
{
  "evidence_id": "TEL-LAT-IITBBS-SW-MHR",
  "source_agent": "TelemetryAgent",
  "device_id": "IITBBS-SW-MHR",
  "metric_name": "latency_ms",
  "observed_value": 185.0,
  "threshold_reference": "warn=35.0ms, crit=100.0ms",
  "severity": "CRITICAL",
  "polarity": "SUPPORTS",
  "hypothesis_target": "LINK_CONGESTION",
  "weight": 0.85,
  "description": "Elevated round-trip latency of 185.0ms on IITBBS-SW-MHR."
}
```

---

## 6. Official Output JSON Specification (Page 5)

Every diagnosis terminates in the unified schema required by Page 5:

```json
{
  "incident_id": "INC-41D80AF3",
  "status": "diagnosed",
  "suspected_root_cause": "LINK_CONGESTION",
  "confidence": 0.80,
  "affected_devices": [
    "AP-MHR-W1",
    "IITBBS-SW-MHR"
  ],
  "supporting_evidence": [
    {
      "metric": "latency_ms",
      "value": 185.0,
      "interpretation": "Elevated round-trip latency of 185.0ms on IITBBS-SW-MHR."
    },
    {
      "metric": "queue_drops",
      "value": 145,
      "interpretation": "Switch egress buffer overflow causing 145 tail drops on IITBBS-SW-MHR."
    }
  ],
  "alternative_causes": [
    "Possible upstream switch failure"
  ],
  "recommended_actions": [
    "Engage Quality of Service (QoS) rate limiting and DSCP queue prioritization on AP-MHR-W1, IITBBS-SW-MHR."
  ],
  "evidence_sources": [
    "telemetry_agent",
    "infrastructure_agent"
  ],
  "limitations": [
    "Topological context: Localized failure under IITBBS-SW-MHR."
  ]
}
```

---

## 7. Tamper-Evident Merkle Evidence Ledger

To guarantee auditability and prevent post-hoc evidence tampering across distributed agents, every collected piece of evidence is appended to an immutable, cryptographically chained ledger (`core/evidence_ledger.py`):

- **Cryptographic Hash Chaining**: Each entry stores `prev_hash` (the SHA-256 hash of the previous ledger block, initialized to `"0"*64` for the genesis block) and computes its own `entry_hash = SHA256(prev_hash + canonical_json(entry))`.
- **Immutable Entry Records**: `LedgerEntry` models enforce `model_config = ConfigDict(frozen=True)` preventing in-memory mutation.
- **Runtime Integrity Verification**: Calling `ledger.verify_chain_integrity()` traverses all blocks from genesis to head, recomputes canonical hashes, and verifies that no intermediate evidence was modified or omitted.

---

## 8. Information-Theoretic Investigation Plan (Shannon Entropy)

Active troubleshooting follow-up checks are ranked by true **Shannon Information Gain** (`core/investigation_engine.py`):

$$H(S) = -\sum_{i=1}^{K} p_i \log_2(p_i)$$

Given a binary diagnostic check $C$ that splits hypotheses into candidate partitions $A$ and $B$:

$$IG(S, C) = H(S) - \left[ P(A) \cdot H(A) + P(B) \cdot H(B) \right]$$

Checks with higher information gain bits ($>0.5\text{ bits}$) are prioritized at the top of `investigation_plan`, targeting platform-specific commands across **Cisco Catalyst IOS XE**, **Cisco Catalyst 9800 WLC**, and **Linux Core Services**.

