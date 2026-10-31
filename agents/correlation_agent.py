"""CorrelationAgent: The Central Arbiter and primary intelligence component.

Aggregates structured agent findings, reconciles untrusted status labels, resolves
conflicts, calculates evidence-based confidence, and produces the final arbitration result.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from core.confidence_engine import ConfidenceConfig, ConfidenceEngine
from core.evidence_engine import EvidenceEngine
from core.rules import DiagnosticRuleEngine, MetricThresholds
from core.topology import TopologyEngine
from protocol.models import (
    AgentFinding,
    ArbitrationResult,
    CanonicalTelemetry,
    EvidenceItem,
    EvidencePolarity,
    HypothesisType,
    SeverityLevel,
    StructuredEvidence,
)


class CorrelationAgent:
    """The central intelligence arbiter responsible for evidence aggregation,

    conflict resolution, and definitive explainable root-cause diagnosis.
    """

    def __init__(
        self,
        topology_engine: Optional[TopologyEngine] = None,
        thresholds: Optional[MetricThresholds] = None,
        confidence_config: Optional[ConfidenceConfig] = None
    ) -> None:
        self.topology = topology_engine or TopologyEngine()
        self.rules = DiagnosticRuleEngine(thresholds)
        self.confidence_engine = ConfidenceEngine(confidence_config)
        self.evidence_engine = EvidenceEngine()

    def arbitrate(
        self,
        telemetry_records: List[CanonicalTelemetry],
        agent_findings: List[AgentFinding],
        cascade_evidence: Optional[List[EvidenceItem]] = None,
        staleness_seconds: float = 0.0
    ) -> ArbitrationResult:
        """Execute deterministic arbitration across all collected telemetry and agent findings."""
        trace_id = f"TRACE-{uuid.uuid4().hex[:8].upper()}"
        self.evidence_engine.clear()

        # 1. Harvest evidence items from individual agent findings
        for finding in agent_findings:
            self.evidence_engine.add_evidence(finding.evidence)

        # 2. Add cascading topology evidence if provided
        if cascade_evidence:
            self.evidence_engine.add_evidence(cascade_evidence)

        # 3. Reconcile untrusted generator-provided status labels
        reconciliation_items = self.evidence_engine.reconcile_untrusted_labels(telemetry_records)
        self.evidence_engine.add_evidence(reconciliation_items)

        # 4. Apply deterministic cross-metric conflict resolution rules
        conflict_items = self.evidence_engine.apply_conflict_resolution_rules(telemetry_records)
        self.evidence_engine.add_evidence(conflict_items)

        # 5. Evaluate all candidate hypotheses
        hypothesis_evals = self.evidence_engine.evaluate_hypotheses()

        # 6. Assess affected devices and topological consistency
        all_anomalous_devices: Set[str] = set()
        for rec in telemetry_records:
            m = rec.metrics
            if (
                (m.packet_loss_pct is not None and m.packet_loss_pct > 1.0) or
                (m.latency_ms is not None and m.latency_ms > 40.0) or
                (m.cpu_pct is not None and m.cpu_pct > 80.0) or
                (m.interface_errors is not None and m.interface_errors > 5) or
                (m.signal_strength_dbm is not None and m.signal_strength_dbm <= -75.0) or
                (m.dns_resolution_ms is not None and m.dns_resolution_ms >= 100.0) or
                (m.dhcp_lease_success is False)
            ):
                all_anomalous_devices.add(rec.device_id)

        topo_score, topo_explanation = self.topology.calculate_topology_consistency(list(all_anomalous_devices))

        # Check for Interoperability Schema Defect
        total_schema_warnings = sum(len(r.normalization_warnings) for r in telemetry_records)
        if total_schema_warnings >= 3:
            # Add explicit support for INTEROPERABILITY_SCHEMA_DEFECT
            ev_schema = EvidenceItem(
                evidence_id=f"SCHEMA-DEFECT-{trace_id}",
                source_agent="CorrelationAgent",
                device_id="INGESTION-PIPELINE",
                metric_name="normalization_warnings_count",
                observed_value=total_schema_warnings,
                threshold_reference=">= 3 normalization warnings",
                severity=SeverityLevel.WARNING,
                polarity=EvidencePolarity.SUPPORTS,
                hypothesis_target=HypothesisType.INTEROPERABILITY_SCHEMA_DEFECT.value,
                weight=0.90,
                description=f"Ingestion pipeline encountered {total_schema_warnings} schema coercion warnings across telemetry payloads."
            )
            self.evidence_engine.add_evidence([ev_schema])
            hypothesis_evals = self.evidence_engine.evaluate_hypotheses()

        # 7. Rank hypotheses by net score and calculate confidence
        ranked_hypotheses: List[Tuple[str, float, float, Dict[str, Any]]] = []
        for target, data in hypothesis_evals.items():
            if target in (HypothesisType.INSUFFICIENT_EVIDENCE.value,):
                continue

            conf, uncert, limits = self.confidence_engine.calculate_confidence(
                hypothesis_data=data,
                telemetry_records=telemetry_records,
                topology_consistency=topo_score,
                staleness_seconds=staleness_seconds
            )
            data["computed_confidence"] = conf
            data["uncertainty_factors"] = uncert
            data["limitations"] = limits
            ranked_hypotheses.append((target, data["net_score"], conf, data))

        # Sort hypotheses:
        # When anomalies are detected on the network, fault hypotheses with verified confidence take precedence over NORMAL_OPERATION.
        def hypothesis_rank_key(item: Tuple[str, float, float, Dict[str, Any]]) -> Tuple[int, float, float]:
            target, net_sc, conf, data = item
            is_normal = (target == HypothesisType.NORMAL_OPERATION.value)
            if all_anomalous_devices and is_normal:
                return (-1, 0.0, 0.0)
            return (1 if net_sc > 0 else 0, conf, net_sc)

        ranked_hypotheses.sort(key=hypothesis_rank_key, reverse=True)

        # 8. Arbiter Decision Selection
        top_target, top_net_score, top_confidence, top_data = ranked_hypotheses[0]

        # Calculate overall evidence completeness
        if telemetry_records:
            overall_completeness = sum(r.completeness_ratio() for r in telemetry_records) / len(telemetry_records)
        else:
            overall_completeness = 0.0

        # Insufficient Evidence Gatekeeper — ordered by severity:

        # 1. Critically stale: data > 7200s old with no detected anomalies.
        #    Asserting NORMAL from day-old data is worse than admitting uncertainty.
        STALE_THRESHOLD_S = 7200.0
        critically_stale = (staleness_seconds > STALE_THRESHOLD_S and not all_anomalous_devices)

        # 2. Critically sparse: < 20% completeness with no detected anomalies.
        critically_sparse = (overall_completeness < 0.20 and not all_anomalous_devices)

        is_normal_net = (top_target == HypothesisType.NORMAL_OPERATION.value and not all_anomalous_devices)

        uncertainties: List[str] = list(top_data.get("uncertainty_factors", []))
        limitations: List[str] = list(top_data.get("limitations", []))
        limitations.append(f"Topological context: {topo_explanation}")

        if critically_stale:
            primary_root_cause = HypothesisType.INSUFFICIENT_EVIDENCE.value
            confidence = top_confidence
            uncertainties.append(
                "Telemetry exceeds maximum freshness threshold (>2h) — "
                "asserting normal operation from historical telemetry is unreliable."
            )
            limitations.append(
                "Insufficient freshness: telemetry must be within 2 hours to assert NORMAL_OPERATION."
            )
        elif critically_sparse:
            primary_root_cause = HypothesisType.INSUFFICIENT_EVIDENCE.value
            confidence = top_confidence
            uncertainties.append(
                f"Critically sparse telemetry: only {round(overall_completeness * 100, 1)}% of metrics populated — cannot assert normal operation."
            )
            limitations.append("Insufficient data to diagnose or rule out faults; at least 20% metric coverage required.")
        elif not is_normal_net and (top_confidence < self.confidence_engine.config.min_confidence_threshold or top_net_score <= 0.0):
            primary_root_cause = HypothesisType.INSUFFICIENT_EVIDENCE.value
            confidence = top_confidence
            uncertainties.append(
                f"Confidence ({top_confidence}) did not meet minimum threshold ({self.confidence_engine.config.min_confidence_threshold})."
            )
            limitations.append("Diagnostics inconclusive; missing corroborating telemetry signals.")
        else:
            primary_root_cause = top_target
            confidence = top_confidence

        # If primary root cause is normal operation, clamp affected devices to empty
        if primary_root_cause == HypothesisType.NORMAL_OPERATION.value:
            affected_devices = []
        else:
            # Collect affected devices from top hypothesis or anomalous devices
            hyp_devices = top_data.get("affected_devices", [])
            affected_devices = sorted(list(set(hyp_devices).union(all_anomalous_devices)))
            if not affected_devices:
                affected_devices = [r.device_id for r in telemetry_records]

        # Expand blast radius if primary cause is an upstream switch
        if primary_root_cause == HypothesisType.UPSTREAM_SWITCH_FAILURE.value:
            for d in list(affected_devices):
                blast = self.topology.get_blast_radius(d)
                affected_devices = sorted(list(set(affected_devices).union(blast["downstream_device_ids"])))

        # Compile supporting and contradictory evidence strings
        supporting_strings = [
            f"[{item.source_agent}] {item.description}"
            for item in top_data.get("supporting_items", [])
        ]
        contradictory_strings = [
            f"[{item.source_agent}] {item.description}"
            for item in top_data.get("contradicting_items", [])
        ]

        # Explicitly incorporate untrusted label reconciliation overrides
        for item in reconciliation_items:
            rec_str = f"[{item.source_agent}] {item.description}"
            if rec_str not in contradictory_strings:
                contradictory_strings.append(rec_str)

        # Structured evidence conforming to Page 5 schema
        structured_items = [
            StructuredEvidence(
                metric=item.metric_name,
                value=item.observed_value,
                interpretation=item.description
            )
            for item in top_data.get("supporting_items", [])
        ]
        evidence_sources = sorted(list({
            item.source_agent.lower().replace("agent", "_agent") if not item.source_agent.endswith("_agent") else item.source_agent.lower()
            for item in top_data.get("supporting_items", [])
        }))
        if not evidence_sources and agent_findings:
            evidence_sources = sorted(list({f.agent_name.lower().replace("agent", "_agent") for f in agent_findings}))

        # Alternative hypotheses
        alternatives = []
        for target, net_sc, conf, data in ranked_hypotheses[1:]:
            if data["support_weight"] > 0:
                alternatives.append({
                    "hypothesis": target,
                    "confidence": conf,
                    "net_score": net_sc,
                    "supporting_signals": data["supporting_count"],
                    "contradictory_signals": data["contradicting_count"],
                })

        # Recommended actions
        recommended_actions = self.rules.get_playbook_recommendations(
            primary_root_cause,
            affected_devices
        )

        # Multi-Incident Partitioning (Topology & Fault Domain Grouping)
        # Groups anomalous devices by independent root causes and topology domains.
        # Downstream cascades sharing the same fault are MERGED into a single incident.
        # Only truly independent faults across distinct zones produce multiple co-occurring incidents.
        co_occurring: List[IncidentSummary] = []
        if len(all_anomalous_devices) > 0 and primary_root_cause != HypothesisType.NORMAL_OPERATION.value:
            from protocol.models import IncidentSummary

            # Step A: Determine dominant fault hypothesis for each anomalous device
            dev_fault_map: Dict[str, Tuple[str, List[EvidenceItem]]] = {}
            for dev_id in all_anomalous_devices:
                dev_findings = [f for f in agent_findings if f.device_id == dev_id]
                dev_ev_items = [
                    item for f in dev_findings
                    for item in f.evidence
                    if item.polarity == EvidencePolarity.SUPPORTS and item.hypothesis_target != HypothesisType.NORMAL_OPERATION.value
                ]
                conflict_for_dev = [
                    item for item in conflict_items
                    if item.device_id == dev_id and item.polarity == EvidencePolarity.SUPPORTS
                ]
                dev_ev_items.extend(conflict_for_dev)

                target_weights: Dict[str, float] = {}
                for item in dev_ev_items:
                    target_weights[item.hypothesis_target] = target_weights.get(item.hypothesis_target, 0.0) + item.weight

                if target_weights:
                    # Specific root-causes (HARDWARE_FAILURE, WEAK_WIFI, DNS_DHCP_FAILURE) take precedence over generic LINK_CONGESTION
                    def fault_priority(target_pair: Tuple[str, float]) -> Tuple[int, float]:
                        target, weight = target_pair
                        priority = 2 if target in (HypothesisType.HARDWARE_FAILURE.value,
                                                   HypothesisType.WEAK_WIFI.value,
                                                   HypothesisType.DNS_DHCP_FAILURE.value) else 1
                        return (priority, weight)

                    best_target = max(target_weights.items(), key=fault_priority)[0]
                    dev_fault_map[dev_id] = (best_target, [e for e in dev_ev_items if e.hypothesis_target == best_target])
                else:
                    dev_fault_map[dev_id] = (primary_root_cause, [])

            # Step B: Group devices by (fault_type, topology_domain)
            clusters: Dict[str, Dict[str, Any]] = {}
            for dev_id, (fault_type, ev_list) in dev_fault_map.items():
                upstream_path = self.topology.get_upstream_path(dev_id)
                merged = False
                # Step B: Topology & Explicit Service-Dependency Clustering
                # Devices merge if:
                # 1. They have identical fault_type AND
                # 2. EITHER:
                #    a) Direct physical hierarchy (Building Switch -> AP/Host)
                #    b) Immediate building distribution parent (not campus core)
                #    c) Explicit Service Dependency mapping (Client mapped directly to designated Server)
                for cluster_key, cluster_data in clusters.items():
                    if cluster_data["fault_type"] == fault_type:
                        existing_devs = cluster_data["devices"]
                        # Direct physical hierarchy check:
                        is_direct_hierarchy = any(
                            ed in upstream_path or dev_id in self.topology.get_upstream_path(ed)
                            for ed in existing_devs
                        )
                        # Immediate common ancestor (exclude root core switches from merging disconnected buildings)
                        lca = self.topology.find_common_ancestor([dev_id] + existing_devs)
                        lca_is_local = lca is not None and not lca.startswith("CORE-") and not lca.startswith("IITBBS-CORE")

                        # Explicit Logical Service Dependency: Client is explicitly mapped to the server in this cluster
                        is_service_dependency = any(
                            self.topology.is_service_dependent(dev_id, ed) or self.topology.is_service_dependent(ed, dev_id)
                            for ed in existing_devs
                        )

                        if is_direct_hierarchy or lca_is_local or is_service_dependency:
                            cluster_data["devices"].append(dev_id)
                            cluster_data["evidence"].extend(ev_list)
                            merged = True
                            break

                if not merged:
                    clusters[f"{fault_type}_{dev_id}"] = {
                        "fault_type": fault_type,
                        "devices": [dev_id],
                        "evidence": list(ev_list),
                    }

            # Step C: Each distinct topology cluster generates its own IncidentSummary
            # If there is truly only 1 cluster, it matches the primary incident exactly.
            # If multiple clusters exist (even with the same fault type in separate locations),
            # they are faithfully preserved as separate independent incidents!
            for c in clusters.values():
                c_fault = c["fault_type"]
                c_devs = sorted(list(set(c["devices"])))
                c_records = [r for r in telemetry_records if r.device_id in c_devs]

                # Compute incident-level calibrated confidence from this specific cluster's evidence
                cluster_hyp_data = {
                    "support_weight": sum(e.weight for e in c["evidence"]),
                    "contra_weight": 0.0,
                    "supporting_agents": list({e.source_agent for e in c["evidence"]}),
                }
                c_topo_score, _ = self.topology.calculate_topology_consistency(c_devs)
                c_conf, _, _ = self.confidence_engine.calculate_confidence(
                    hypothesis_data=cluster_hyp_data,
                    telemetry_records=c_records,
                    topology_consistency=c_topo_score,
                    staleness_seconds=staleness_seconds
                )

                # AIOps Root-Cause vs Symptom-Receiver Localization:
                # Upstream switches causing downstream symptom cascades MUST be ranked higher than the edge devices
                # receiving the propagated symptoms. Distinguishes causal origins (queue drops, link saturation,
                # service authority) from downstream symptom receivers (propagated latency/jitter).
                def score_origin_candidate(candidate_id: str) -> Tuple[int, int, float, int]:
                    # 1. Downstream devices explained (causal tree propagation or service dependency)
                    downstream_explained = sum(
                        1 for other_id in c_devs
                        if other_id != candidate_id and (
                            candidate_id in self.topology.get_upstream_path(other_id) or
                            self.topology.is_service_dependent(other_id, candidate_id)
                        )
                    )
                    # 2. Causal metric indicators (buffer saturation, queue drops, saturated link vs propagated latency)
                    candidate_records = [r for r in c_records if r.device_id == candidate_id]
                    has_causal_symptom = 0
                    for r in candidate_records:
                        m = r.metrics
                        if (m.queue_drops and m.queue_drops > 100) or (m.link_utilization_pct and m.link_utilization_pct > 80.0) or (m.interface_errors and m.interface_errors > 50):
                            has_causal_symptom = 1
                            break
                    # 3. Direct evidence weight on this device:
                    direct_ev_weight = sum(e.weight for e in c["evidence"] if e.device_id == candidate_id)
                    # 4. Topological seniority: shorter path to core breaks tie
                    seniority = -len(self.topology.get_upstream_path(candidate_id))
                    return (downstream_explained, has_causal_symptom, direct_ev_weight, seniority)

                root_cause_dev = max(c_devs, key=score_origin_candidate)

                c_ev_struct = [
                    (e.device_id, StructuredEvidence(metric=e.metric_name, value=e.observed_value, interpretation=e.description))
                    for e in c["evidence"]
                ]
                seen_ev = set()
                unique_ev = []
                for dev_src, ev in c_ev_struct:
                    # Deduplicate with full device identity so separate devices are preserved
                    k = (dev_src, ev.metric, str(ev.value))
                    if k not in seen_ev:
                        seen_ev.add(k)
                        unique_ev.append(ev)

                co_occurring.append(
                    IncidentSummary(
                        root_cause=c_fault,
                        confidence=round(c_conf, 3),
                        root_cause_device=root_cause_dev,
                        affected_devices=c_devs,
                        supporting_evidence=unique_ev[:8]
                    )
                )

        return ArbitrationResult(
            primary_root_cause=primary_root_cause,
            confidence=confidence,
            affected_devices=affected_devices,
            supporting_evidence=supporting_strings,
            structured_evidence=structured_items,
            contradictory_evidence=contradictory_strings,
            alternative_hypotheses=alternatives[:4],  # Top 4 alternatives
            evidence_sources=evidence_sources,
            evidence_completeness=round(overall_completeness, 3),
            uncertainty_factors=uncertainties,
            limitations=limitations,
            recommended_actions=recommended_actions,
            execution_trace_id=trace_id,
            co_occurring_incidents=co_occurring
        )
