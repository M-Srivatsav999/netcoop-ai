"""Telemetry normalization and schema validation engine.

Converts multi-version heterogeneous raw telemetry payloads into strict CanonicalTelemetry instances.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from protocol.models import (
    CanonicalMetrics,
    CanonicalTelemetry,
    NormalizationWarning,
    SchemaVersion,
)


class TelemetryNormalizer:
    """Deterministic normalizer supporting Schema V1, V2, and V3 payloads."""

    # Regex patterns for unit stripping
    _NUMERIC_PATTERN = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(?:ms|s|sec|mbps|kbps|bps|%|dbm)?\s*$", re.IGNORECASE)

    @classmethod
    def detect_schema_version(cls, raw: Dict[str, Any]) -> SchemaVersion:
        """Deterministically detect schema version based on key names, value types, and structure."""
        if not isinstance(raw, dict):
            return SchemaVersion.UNKNOWN

        # V2 markers: renamed fields with alternative units
        v2_markers = {
            "latency_sec", "jitter_s", "packet_loss_ratio", "throughput_bps",
            "throughput_kbps", "cpu_utilization_ratio", "memory_utilization_ratio",
            "crc_errors", "epoch_timestamp", "host_id", "utilization_ratio"
        }
        raw_keys = set(raw.keys())
        metrics_dict = raw.get("metrics")
        if isinstance(metrics_dict, dict):
            raw_keys.update(metrics_dict.keys())

        if any(marker in raw_keys for marker in v2_markers):
            return SchemaVersion.V2

        # Check for V3 markers: string numerical values, missing timestamps, or flattened messy fields
        v3_string_numbers = False
        all_values = list(raw.values())
        if isinstance(metrics_dict, dict):
            all_values.extend(metrics_dict.values())

        for v in all_values:
            if isinstance(v, str) and cls._is_potential_numeric_string(v):
                v3_string_numbers = True
                break

        if v3_string_numbers or ("timestamp" not in raw and "time" not in raw):
            return SchemaVersion.V3

        # V1 baseline: standard fields present and well-typed
        v1_markers = {"device_id", "latency_ms", "packet_loss_pct", "cpu_pct"}
        if any(m in raw_keys for m in v1_markers):
            return SchemaVersion.V1

        return SchemaVersion.V3

    @classmethod
    def _is_potential_numeric_string(cls, val: str) -> bool:
        """Check if string contains a numeric value with optional unit suffix."""
        stripped = val.strip()
        if stripped.lower() in {"healthy", "warning", "critical", "unknown", "error", "ok", "true", "false"}:
            return False
        return bool(cls._NUMERIC_PATTERN.match(stripped))

    @classmethod
    def _parse_float(
        cls,
        val: Any,
        field_name: str,
        warnings: List[NormalizationWarning],
        allow_none: bool = True
    ) -> Optional[float]:
        """Safely convert value to float, handling units, strings, and invalid tokens."""
        if val is None:
            return None

        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                warnings.append(NormalizationWarning(
                    field=field_name,
                    original_value=val,
                    action_taken="mapped_to_none",
                    reason="Non-finite numerical value (NaN or Inf)"
                ))
                return None
            return float(val)

        if isinstance(val, str):
            clean = val.strip()
            if not clean or clean.lower() in {"none", "null", "n/a", "na", "nan", "unknown", "missing"}:
                warnings.append(NormalizationWarning(
                    field=field_name,
                    original_value=val,
                    action_taken="mapped_to_none",
                    reason="Missing-value placeholder string"
                ))
                return None

            match = cls._NUMERIC_PATTERN.match(clean)
            if match:
                num_str = match.group(1)
                try:
                    parsed = float(num_str)
                    warnings.append(NormalizationWarning(
                        field=field_name,
                        original_value=val,
                        action_taken=f"coerced_string_to_float({parsed})",
                        reason="Parsed numerical string and stripped unit"
                    ))
                    return parsed
                except ValueError:
                    pass

        warnings.append(NormalizationWarning(
            field=field_name,
            original_value=val,
            action_taken="mapped_to_none",
            reason=f"Invalid unparseable value for numerical field {field_name}"
        ))
        return None

    @classmethod
    def _parse_int(
        cls,
        val: Any,
        field_name: str,
        warnings: List[NormalizationWarning]
    ) -> Optional[int]:
        """Safely parse integer metrics (e.g. queue drops, interface errors)."""
        f = cls._parse_float(val, field_name, warnings)
        if f is None:
            return None
        return int(round(f))

    @classmethod
    def _parse_timestamp(
        cls,
        val: Any,
        warnings: List[NormalizationWarning]
    ) -> Optional[datetime]:
        """Deterministically parse timestamp supporting ISO8601 strings and UNIX epochs."""
        if val is None:
            warnings.append(NormalizationWarning(
                field="timestamp",
                original_value=None,
                action_taken="set_to_none",
                reason="Timestamp missing in payload"
            ))
            return None

        if isinstance(val, (int, float)):
            # Epoch timestamp (check if seconds or milliseconds)
            try:
                epoch = float(val)
                if epoch > 1e11:  # Milliseconds epoch
                    epoch = epoch / 1000.0
                dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
                warnings.append(NormalizationWarning(
                    field="timestamp",
                    original_value=val,
                    action_taken=f"converted_epoch_to_iso8601({dt.isoformat()})",
                    reason="Parsed UNIX timestamp"
                ))
                return dt
            except Exception as e:
                warnings.append(NormalizationWarning(
                    field="timestamp",
                    original_value=val,
                    action_taken="set_to_none",
                    reason=f"Failed to parse epoch timestamp: {e}"
                ))
                return None

        if isinstance(val, str):
            clean = val.strip()
            # Standard ISO formats
            for fmt in (
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(clean, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

            # Fallback to fromisoformat
            try:
                dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

        warnings.append(NormalizationWarning(
            field="timestamp",
            original_value=val,
            action_taken="set_to_none",
            reason=f"Unrecognized timestamp format: {val}"
        ))
        return None

    @classmethod
    def normalize_single(
        cls,
        raw: Dict[str, Any],
        explicit_version: Optional[SchemaVersion] = None
    ) -> CanonicalTelemetry:
        """Normalize a single device telemetry record into CanonicalTelemetry."""
        if not isinstance(raw, dict):
            raise ValueError(f"TelemetryNormalizer expects dictionary input, got {type(raw)}")

        warnings: List[NormalizationWarning] = []
        detected_version = explicit_version or cls.detect_schema_version(raw)

        # 1. Extract device ID (supporting device_id, host_id, device, name)
        device_id = raw.get("device_id") or raw.get("host_id") or raw.get("device") or raw.get("name")
        if not device_id or not isinstance(device_id, str):
            device_id = f"UNKNOWN-DEVICE-{abs(hash(str(raw))) % 10000}"
            warnings.append(NormalizationWarning(
                field="device_id",
                original_value=raw.get("device_id"),
                action_taken=f"assigned_synthetic_id({device_id})",
                reason="Device identifier missing or non-string"
            ))

        # 2. Extract timestamp
        raw_ts = raw.get("timestamp") or raw.get("epoch_timestamp") or raw.get("time") or raw.get("ts")
        timestamp = cls._parse_timestamp(raw_ts, warnings)

        # 3. Extract reported status label (untrusted)
        reported_status = raw.get("status") or raw.get("reported_status") or raw.get("state")
        if reported_status is not None:
            reported_status = str(reported_status).upper().strip()

        # 4. Flatten metric sources (metrics sub-dict or root-level keys)
        metric_source: Dict[str, Any] = {}
        if isinstance(raw.get("metrics"), dict):
            metric_source.update(raw["metrics"])
        for k, v in raw.items():
            if k not in {"metrics", "device_id", "host_id", "device", "name", "timestamp", "epoch_timestamp", "status", "reported_status"}:
                metric_source.setdefault(k, v)

        # 5. Extract and normalize canonical metrics
        # Latency
        latency_val = None
        if "latency_ms" in metric_source:
            latency_val = cls._parse_float(metric_source["latency_ms"], "latency_ms", warnings)
        elif "latency_sec" in metric_source or "latency_s" in metric_source:
            raw_s = metric_source.get("latency_sec", metric_source.get("latency_s"))
            sec_val = cls._parse_float(raw_s, "latency_sec", warnings)
            if sec_val is not None:
                latency_val = round(sec_val * 1000.0, 3)
                warnings.append(NormalizationWarning(
                    field="latency",
                    original_value=raw_s,
                    action_taken=f"converted_seconds_to_ms({latency_val})",
                    reason="V2 unit conversion: seconds to milliseconds"
                ))
        elif "latency" in metric_source:
            parsed = cls._parse_float(metric_source["latency"], "latency", warnings)
            if parsed is not None:
                # Infer unit: if < 1.0, likely seconds; if >= 1.0, likely ms
                if parsed < 1.0 and parsed > 0.0:
                    latency_val = round(parsed * 1000.0, 3)
                    warnings.append(NormalizationWarning(
                        field="latency",
                        original_value=parsed,
                        action_taken=f"inferred_seconds_converted_to_ms({latency_val})",
                        reason="Value < 1.0 inferred as seconds"
                    ))
                else:
                    latency_val = parsed

        # Jitter
        jitter_val = None
        if "jitter_ms" in metric_source:
            jitter_val = cls._parse_float(metric_source["jitter_ms"], "jitter_ms", warnings)
        elif "jitter_s" in metric_source or "jitter_sec" in metric_source:
            raw_j = metric_source.get("jitter_s", metric_source.get("jitter_sec"))
            sec_j = cls._parse_float(raw_j, "jitter_s", warnings)
            if sec_j is not None:
                jitter_val = round(sec_j * 1000.0, 3)
                warnings.append(NormalizationWarning(
                    field="jitter",
                    original_value=raw_j,
                    action_taken=f"converted_seconds_to_ms({jitter_val})",
                    reason="V2 unit conversion: seconds to milliseconds"
                ))
        elif "jitter" in metric_source:
            parsed_j = cls._parse_float(metric_source["jitter"], "jitter", warnings)
            if parsed_j is not None:
                if parsed_j < 0.5 and parsed_j > 0.0:
                    jitter_val = round(parsed_j * 1000.0, 3)
                else:
                    jitter_val = parsed_j

        # Packet Loss (0.0 to 100.0%)
        packet_loss_val = None
        if "packet_loss_pct" in metric_source:
            packet_loss_val = cls._parse_float(metric_source["packet_loss_pct"], "packet_loss_pct", warnings)
        elif "packet_loss_ratio" in metric_source or "loss_ratio" in metric_source:
            raw_loss = metric_source.get("packet_loss_ratio", metric_source.get("loss_ratio"))
            ratio_val = cls._parse_float(raw_loss, "packet_loss_ratio", warnings)
            if ratio_val is not None:
                packet_loss_val = round(ratio_val * 100.0, 3)
                warnings.append(NormalizationWarning(
                    field="packet_loss",
                    original_value=raw_loss,
                    action_taken=f"converted_ratio_to_percentage({packet_loss_val})",
                    reason="V2 unit conversion: ratio [0,1] to percentage [0,100]"
                ))
        elif "packet_loss" in metric_source or "loss" in metric_source:
            raw_l = metric_source.get("packet_loss", metric_source.get("loss"))
            p_l = cls._parse_float(raw_l, "packet_loss", warnings)
            if p_l is not None:
                # If strictly <= 1.0 and originally specified as fractional ratio
                if isinstance(raw_l, str) and "%" in raw_l:
                    packet_loss_val = p_l
                elif p_l <= 1.0 and p_l > 0.0:
                    packet_loss_val = round(p_l * 100.0, 3)
                    warnings.append(NormalizationWarning(
                        field="packet_loss",
                        original_value=raw_l,
                        action_taken=f"inferred_ratio_converted_to_percentage({packet_loss_val})",
                        reason="Fractional value <= 1.0 inferred as ratio"
                    ))
                else:
                    packet_loss_val = p_l

        # Throughput (Mbps)
        throughput_val = None
        if "throughput_mbps" in metric_source:
            throughput_val = cls._parse_float(metric_source["throughput_mbps"], "throughput_mbps", warnings)
        elif "throughput_bps" in metric_source or "bandwidth_bps" in metric_source:
            raw_bps = metric_source.get("throughput_bps", metric_source.get("bandwidth_bps"))
            bps_val = cls._parse_float(raw_bps, "throughput_bps", warnings)
            if bps_val is not None:
                throughput_val = round(bps_val / 1_000_000.0, 3)
                warnings.append(NormalizationWarning(
                    field="throughput",
                    original_value=raw_bps,
                    action_taken=f"converted_bps_to_mbps({throughput_val})",
                    reason="Unit conversion: bps to Mbps"
                ))
        elif "throughput_kbps" in metric_source:
            raw_kbps = metric_source["throughput_kbps"]
            kbps_val = cls._parse_float(raw_kbps, "throughput_kbps", warnings)
            if kbps_val is not None:
                throughput_val = round(kbps_val / 1000.0, 3)
                warnings.append(NormalizationWarning(
                    field="throughput",
                    original_value=raw_kbps,
                    action_taken=f"converted_kbps_to_mbps({throughput_val})",
                    reason="Unit conversion: kbps to Mbps"
                ))
        elif "throughput" in metric_source or "bandwidth" in metric_source:
            raw_tp = metric_source.get("throughput", metric_source.get("bandwidth"))
            throughput_val = cls._parse_float(raw_tp, "throughput", warnings)

        # Link Utilization (%)
        link_util_val = None
        if "link_utilization_pct" in metric_source:
            link_util_val = cls._parse_float(metric_source["link_utilization_pct"], "link_utilization_pct", warnings)
        elif any(k in metric_source for k in ("link_utilization", "link_util_pct", "link_utilization_ratio", "link_ratio", "link_util")):
            raw_lu = next(metric_source[k] for k in ("link_utilization", "link_util_pct", "link_utilization_ratio", "link_ratio", "link_util") if k in metric_source)
            p_lu = cls._parse_float(raw_lu, "link_utilization", warnings)
            if p_lu is not None:
                if p_lu <= 1.0 and p_lu > 0.0:
                    link_util_val = round(p_lu * 100.0, 2)
                    warnings.append(NormalizationWarning(
                        field="link_utilization_pct",
                        original_value=raw_lu,
                        action_taken=f"converted_ratio_to_percentage({link_util_val})",
                        reason="Link utilization ratio to percentage"
                    ))
                else:
                    link_util_val = p_lu

        # CPU Utilization (%)
        cpu_val = None
        if "cpu_pct" in metric_source:
            cpu_val = cls._parse_float(metric_source["cpu_pct"], "cpu_pct", warnings)
        elif "cpu_utilization_pct" in metric_source:
            raw_cpu = metric_source["cpu_utilization_pct"]
            cpu_val = cls._parse_float(raw_cpu, "cpu_utilization_pct", warnings)
            warnings.append(NormalizationWarning(
                field="cpu_pct",
                original_value=raw_cpu,
                action_taken=f"mapped_cpu_utilization_pct_to_cpu_pct({cpu_val})",
                reason="Organizer schema alias: cpu_utilization_pct -> cpu_pct"
            ))
        elif "cpu_utilization_ratio" in metric_source or "utilization_ratio" in metric_source:
            raw_cpu = metric_source.get("cpu_utilization_ratio", metric_source.get("utilization_ratio"))
            ratio_cpu = cls._parse_float(raw_cpu, "cpu_utilization_ratio", warnings)
            if ratio_cpu is not None:
                cpu_val = round(ratio_cpu * 100.0, 2)
                warnings.append(NormalizationWarning(
                    field="cpu",
                    original_value=raw_cpu,
                    action_taken=f"converted_ratio_to_percentage({cpu_val})",
                    reason="V2 unit conversion: CPU ratio to percentage"
                ))
        elif "cpu" in metric_source or "cpu_usage" in metric_source:
            raw_c = metric_source.get("cpu", metric_source.get("cpu_usage"))
            p_c = cls._parse_float(raw_c, "cpu", warnings)
            if p_c is not None:
                if isinstance(raw_c, str) and "%" in raw_c:
                    cpu_val = p_c
                elif p_c <= 1.0 and p_c > 0.0:
                    cpu_val = round(p_c * 100.0, 2)
                else:
                    cpu_val = p_c

        # Memory Utilization (%)
        mem_val = None
        if "memory_pct" in metric_source or "mem_pct" in metric_source:
            mem_val = cls._parse_float(metric_source.get("memory_pct", metric_source.get("mem_pct")), "memory_pct", warnings)
        elif "memory_utilization_ratio" in metric_source or "mem_ratio" in metric_source:
            raw_mem = metric_source.get("memory_utilization_ratio", metric_source.get("mem_ratio"))
            ratio_mem = cls._parse_float(raw_mem, "memory_utilization_ratio", warnings)
            if ratio_mem is not None:
                mem_val = round(ratio_mem * 100.0, 2)
                warnings.append(NormalizationWarning(
                    field="memory",
                    original_value=raw_mem,
                    action_taken=f"converted_ratio_to_percentage({mem_val})",
                    reason="V2 unit conversion: Memory ratio to percentage"
                ))
        elif "memory" in metric_source or "mem" in metric_source:
            raw_m = metric_source.get("memory", metric_source.get("mem"))
            p_m = cls._parse_float(raw_m, "memory", warnings)
            if p_m is not None:
                if isinstance(raw_m, str) and "%" in raw_m:
                    mem_val = p_m
                elif p_m <= 1.0 and p_m > 0.0:
                    mem_val = round(p_m * 100.0, 2)
                else:
                    mem_val = p_m

        # Queue Drops
        queue_drops_val = None
        if "queue_drops" in metric_source:
            queue_drops_val = cls._parse_int(metric_source["queue_drops"], "queue_drops", warnings)
        elif "drops" in metric_source:
            queue_drops_val = cls._parse_int(metric_source["drops"], "drops", warnings)

        # Interface Errors
        interface_errors_val = None
        if "interface_errors" in metric_source:
            interface_errors_val = cls._parse_int(metric_source["interface_errors"], "interface_errors", warnings)
        elif "crc_errors" in metric_source:
            interface_errors_val = cls._parse_int(metric_source["crc_errors"], "crc_errors", warnings)
            warnings.append(NormalizationWarning(
                field="interface_errors",
                original_value=metric_source["crc_errors"],
                action_taken=f"mapped_crc_errors_to_interface_errors({interface_errors_val})",
                reason="V2 field mapping: crc_errors -> interface_errors"
            ))
        elif "rx_tx_errors" in metric_source or "errors" in metric_source:
            interface_errors_val = cls._parse_int(
                metric_source.get("rx_tx_errors", metric_source.get("errors")),
                "interface_errors",
                warnings
            )

        # Signal Strength (dBm)
        signal_val = None
        if "signal_strength_dbm" in metric_source:
            signal_val = cls._parse_float(metric_source["signal_strength_dbm"], "signal_strength_dbm", warnings)
        elif "rssi_dbm" in metric_source or "rssi" in metric_source:
            raw_rssi = metric_source.get("rssi_dbm", metric_source.get("rssi"))
            signal_val = cls._parse_float(raw_rssi, "rssi_dbm", warnings)
            warnings.append(NormalizationWarning(
                field="signal_strength_dbm",
                original_value=raw_rssi,
                action_taken=f"mapped_rssi_to_signal_strength({signal_val})",
                reason="Mapped rssi to signal_strength_dbm"
            ))
        elif "signal" in metric_source:
            signal_val = cls._parse_float(metric_source["signal"], "signal", warnings)

        # DNS Resolution (ms)
        dns_val = None
        if "dns_resolution_ms" in metric_source:
            dns_val = cls._parse_float(metric_source["dns_resolution_ms"], "dns_resolution_ms", warnings)
        elif "dns_latency_sec" in metric_source:
            raw_dns_s = metric_source["dns_latency_sec"]
            sec_dns = cls._parse_float(raw_dns_s, "dns_latency_sec", warnings)
            if sec_dns is not None:
                dns_val = round(sec_dns * 1000.0, 2)
                warnings.append(NormalizationWarning(
                    field="dns_resolution_ms",
                    original_value=raw_dns_s,
                    action_taken=f"converted_seconds_to_ms({dns_val})",
                    reason="Unit conversion: DNS latency seconds to ms"
                ))
        elif "dns_ms" in metric_source or "dns_time" in metric_source:
            dns_val = cls._parse_float(metric_source.get("dns_ms", metric_source.get("dns_time")), "dns_ms", warnings)

        # DHCP Lease Success (bool)
        dhcp_val = None
        if "dhcp_lease_success" in metric_source:
            raw_dhcp = metric_source["dhcp_lease_success"]
            if isinstance(raw_dhcp, bool):
                dhcp_val = raw_dhcp
            elif isinstance(raw_dhcp, str):
                dhcp_val = raw_dhcp.strip().lower() in {"true", "1", "yes", "ok", "success"}
                warnings.append(NormalizationWarning(
                    field="dhcp_lease_success",
                    original_value=raw_dhcp,
                    action_taken=f"coerced_string_to_bool({dhcp_val})",
                    reason="Parsed string to boolean"
                ))
            elif isinstance(raw_dhcp, (int, float)):
                dhcp_val = bool(raw_dhcp)
        elif "dhcp_success" in metric_source or "dhcp_ok" in metric_source:
            raw_dhcp = metric_source.get("dhcp_success", metric_source.get("dhcp_ok"))
            dhcp_val = bool(raw_dhcp) if raw_dhcp is not None else None

        canonical_metrics = CanonicalMetrics(
            latency_ms=latency_val,
            jitter_ms=jitter_val,
            packet_loss_pct=packet_loss_val,
            throughput_mbps=throughput_val,
            link_utilization_pct=link_util_val,
            cpu_pct=cpu_val,
            memory_pct=mem_val,
            queue_drops=queue_drops_val,
            interface_errors=interface_errors_val,
            signal_strength_dbm=signal_val,
            dns_resolution_ms=dns_val,
            dhcp_lease_success=dhcp_val,
        )

        return CanonicalTelemetry(
            device_id=device_id,
            timestamp=timestamp,
            reported_status=reported_status,
            metrics=canonical_metrics,
            schema_version_detected=detected_version,
            normalization_warnings=warnings,
            raw_payload_preserved=raw,
            data_provenance={
                "normalized_at": datetime.now(timezone.utc).isoformat(),
                "original_keys_count": len(raw),
                "warnings_count": len(warnings),
            }
        )

    @classmethod
    def normalize_batch(
        cls,
        raw_input: Union[List[Dict[str, Any]], Dict[str, Any]],
        explicit_version: Optional[SchemaVersion] = None
    ) -> List[CanonicalTelemetry]:
        """Normalize batch or individual telemetry payload into a list of CanonicalTelemetry."""
        if isinstance(raw_input, list):
            items = raw_input
        elif isinstance(raw_input, dict):
            # Check for container keys: "telemetry", "devices", "records", "data"
            for container_key in ("telemetry", "devices", "records", "data", "items"):
                if container_key in raw_input and isinstance(raw_input[container_key], list):
                    items = raw_input[container_key]
                    break
            else:
                items = [raw_input]
        else:
            raise ValueError(f"Unsupported payload input type: {type(raw_input)}")

        results: List[CanonicalTelemetry] = []
        for item in items:
            if isinstance(item, dict):
                results.append(cls.normalize_single(item, explicit_version=explicit_version))
            elif isinstance(item, CanonicalTelemetry):
                results.append(item)
            else:
                # Malformed item in list
                synth_item = CanonicalTelemetry(
                    device_id="CORRUPT-RECORD",
                    schema_version_detected=SchemaVersion.UNKNOWN,
                    normalization_warnings=[
                        NormalizationWarning(
                            field="payload",
                            original_value=str(item),
                            action_taken="created_placeholder_record",
                            reason="Payload record was not a dictionary"
                        )
                    ]
                )
                results.append(synth_item)

        return results
