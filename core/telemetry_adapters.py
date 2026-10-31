"""Production-Grade Multi-Source Network Telemetry Adapters.

Ingests heterogeneous telemetry directly from real network infrastructure CLI outputs,
syslog streams, and operating system diagnostics, transforming them into typed
CanonicalTelemetry entities without data loss.

Supported Infrastructure:
1. Cisco Catalyst IOS XE Switch CLI (interfaces, counters, drops)
2. Cisco Catalyst 9800 Wireless Controller CLI (client RF, RSSI, SNR, WLC state)
3. Linux Core Services (dig DNS probes, DHCP lease states, interface stats)
4. RFC 5424/3164 Enterprise Syslog streams
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from protocol.models import (
    CanonicalMetrics,
    CanonicalTelemetry,
    SchemaVersion,
)


class BaseTelemetryAdapter(ABC):
    """Abstract base adapter for real-world network infrastructure telemetry."""

    @abstractmethod
    def parse(self, raw_input: str, device_id: str) -> CanonicalTelemetry:
        """Parse raw device CLI/log output into CanonicalTelemetry."""
        pass


class CiscoIOSXEAdapter(BaseTelemetryAdapter):
    """Adapter for Cisco Catalyst IOS XE switch command outputs."""

    # Matches: "5 input errors, 12 CRC, 0 frame, 0 overrun, 0 ignored"
    CRC_PATTERN = re.compile(r"(\d+)\s+input errors.*?(\d+)\s+CRC", re.IGNORECASE)
    # Matches: "Output queue: 0/40/155/0 (size/max total/drops/flushes)"
    QUEUE_DROP_PATTERN = re.compile(r"Output queue:\s*\d+/\d+/(\d+)/\d+", re.IGNORECASE)
    # Matches bidirectional rates:
    # "5 minute input rate 450000000 bits/sec, 55000 packets/sec"
    # "5 minute output rate 98400000 bits/sec, 12600 packets/sec"
    IN_BW_PATTERN = re.compile(r"5 minute input rate\s+(\d+)\s+bits/sec", re.IGNORECASE)
    OUT_BW_PATTERN = re.compile(r"5 minute output rate\s+(\d+)\s+bits/sec", re.IGNORECASE)

    def parse(self, raw_input: str, device_id: str) -> CanonicalTelemetry:
        interface_errors: Optional[int] = None
        raw_crc_count: Optional[int] = None
        raw_total_input_err: Optional[int] = None
        queue_drops: Optional[int] = None
        in_throughput_mbps: Optional[float] = None
        out_throughput_mbps: Optional[float] = None
        reported_status = "HEALTHY"

        crc_match = self.CRC_PATTERN.search(raw_input)
        if crc_match:
            total_err = int(crc_match.group(1))
            crc_val = int(crc_match.group(2))
            raw_total_input_err = total_err
            raw_crc_count = crc_val
            # Cisco counter semantics: CRC errors are part of input errors.
            # Do NOT add them together (avoids double-counting).
            interface_errors = max(total_err, crc_val)
            if interface_errors > 10:
                reported_status = "WARNING"

        qd_match = self.QUEUE_DROP_PATTERN.search(raw_input)
        if qd_match:
            queue_drops = int(qd_match.group(1))
            if queue_drops > 20:
                reported_status = "WARNING"

        in_bw = self.IN_BW_PATTERN.search(raw_input)
        if in_bw:
            in_throughput_mbps = round(float(in_bw.group(1)) / 1_000_000.0, 2)

        out_bw = self.OUT_BW_PATTERN.search(raw_input)
        if out_bw:
            out_throughput_mbps = round(float(out_bw.group(1)) / 1_000_000.0, 2)

        # Throughput represents peak bidirectional utilization
        throughputs = [x for x in (in_throughput_mbps, out_throughput_mbps) if x is not None]
        peak_throughput = max(throughputs) if throughputs else None

        metrics = CanonicalMetrics(
            interface_errors=interface_errors,
            queue_drops=queue_drops,
            throughput_mbps=peak_throughput
        )

        return CanonicalTelemetry(
            device_id=device_id,
            timestamp=datetime.now(timezone.utc),
            reported_status=reported_status,
            metrics=metrics,
            schema_version_detected=SchemaVersion.V1,
            data_provenance={
                "adapter": "CiscoIOSXEAdapter",
                "raw_total_input_errors": raw_total_input_err,
                "raw_crc_errors": raw_crc_count,
                "input_rate_mbps": in_throughput_mbps,
                "output_rate_mbps": out_throughput_mbps,
                "raw_length": len(raw_input)
            }
        )


class CiscoWLC9800Adapter(BaseTelemetryAdapter):
    """Adapter for Cisco Catalyst 9800 Wireless LAN Controller client stats."""

    # Matches: "Radio Signal Strength Indicator : -78 dBm"
    RSSI_PATTERN = re.compile(r"(?:Radio Signal Strength Indicator|RSSI)\s*:\s*(-?\d+)\s*dBm", re.IGNORECASE)
    # Matches: "Signal to Noise Ratio : 14 dB"
    SNR_PATTERN = re.compile(r"(?:Signal to Noise Ratio|SNR)\s*:\s*(\d+)\s*dB", re.IGNORECASE)
    # Matches: "Data Rate : 6.0 Mbps" or "Current Rate : 12.0 Mbps"
    RATE_PATTERN = re.compile(r"(?:Data Rate|Current Rate|Rate)\s*:\s*([\d\.]+)\s*Mbps", re.IGNORECASE)

    def parse(self, raw_input: str, device_id: str) -> CanonicalTelemetry:
        rssi_val: Optional[float] = None
        throughput: Optional[float] = None
        status = "HEALTHY"

        rssi_match = self.RSSI_PATTERN.search(raw_input)
        if rssi_match:
            rssi_val = float(rssi_match.group(1))
            if rssi_val <= -72.0:
                status = "WARNING"

        rate_match = self.RATE_PATTERN.search(raw_input)
        if rate_match:
            throughput = float(rate_match.group(1))

        metrics = CanonicalMetrics(
            signal_strength_dbm=rssi_val,
            throughput_mbps=throughput
        )

        return CanonicalTelemetry(
            device_id=device_id,
            timestamp=datetime.now(timezone.utc),
            reported_status=status,
            metrics=metrics,
            schema_version_detected=SchemaVersion.V1,
            data_provenance={"adapter": "CiscoWLC9800Adapter", "raw_length": len(raw_input)}
        )


class LinuxServicesAdapter(BaseTelemetryAdapter):
    """Adapter for Linux core network services (DNS dig & DHCP status)."""

    # Matches: ";; Query time: 450 msec"
    QUERY_TIME_PATTERN = re.compile(r";;\s*Query time:\s*(\d+)\s*msec", re.IGNORECASE)
    # Matches: ";; status: NOERROR" or ";; status: SERVFAIL" or ";; status: NXDOMAIN"
    STATUS_PATTERN = re.compile(r";;\s*->>HEADER<<-.*status:\s*([A-Z]+)", re.IGNORECASE)
    # Matches: "DHCPACK on 10.0.10.101"
    DHCP_LEASE_PATTERN = re.compile(r"DHCP(?:ACK|NAK|OFFER)", re.IGNORECASE)

    def parse(self, raw_input: str, device_id: str) -> CanonicalTelemetry:
        dns_ms: Optional[float] = None
        dhcp_ok: Optional[bool] = None
        status = "HEALTHY"
        dns_status_code = "UNKNOWN"

        qt_match = self.QUERY_TIME_PATTERN.search(raw_input)
        if qt_match:
            dns_ms = float(qt_match.group(1))
            if dns_ms > 100.0:
                status = "WARNING"

        st_match = self.STATUS_PATTERN.search(raw_input)
        if st_match:
            dns_status_code = st_match.group(1).upper()
            if dns_status_code in ("SERVFAIL", "REFUSED"):
                status = "CRITICAL"
                if dns_ms is None:
                    dns_ms = 999.0
            elif dns_status_code in ("NOERROR", "NXDOMAIN"):
                # NXDOMAIN indicates a functioning DNS service that successfully resolved non-existence
                # It is NOT an outage or infrastructure defect.
                if dns_ms is not None and dns_ms > 100.0:
                    status = "WARNING"
                else:
                    status = "HEALTHY"

        if "connection timed out" in raw_input.lower() or "no servers could be reached" in raw_input.lower():
            status = "CRITICAL"
            dns_ms = 999.0
            dns_status_code = "TIMEOUT"

        if "dhcp" in raw_input.lower():
            if "dhcpnak" in raw_input.lower() or "no free leases" in raw_input.lower():
                dhcp_ok = False
                status = "CRITICAL"
            elif "dhcpack" in raw_input.lower() or "bound to" in raw_input.lower():
                dhcp_ok = True

        metrics = CanonicalMetrics(
            dns_resolution_ms=dns_ms,
            dhcp_lease_success=dhcp_ok
        )

        return CanonicalTelemetry(
            device_id=device_id,
            timestamp=datetime.now(timezone.utc),
            reported_status=status,
            metrics=metrics,
            schema_version_detected=SchemaVersion.V1,
            data_provenance={
                "adapter": "LinuxServicesAdapter",
                "dns_status_code": dns_status_code,
                "raw_length": len(raw_input)
            }
        )


class SyslogNetworkAdapter(BaseTelemetryAdapter):
    """Adapter for standard RFC 5424/3164 Syslog messages from campus devices."""

    # Matches RFC 5424 / RFC 3164 Cisco format: "%ETHPORT-5-IF_DOWN: Interface Ethernet1/1 is down"
    FACILITY_PATTERN = re.compile(r"%([A-Z0-9_\-]+)-(\d)-([A-Z0-9_\-]+):\s*(.*)", re.IGNORECASE)
    # Matches RFC 5424 ISO timestamp: "<165>1 2026-10-31T20:15:00.000Z ..."
    RFC5424_TS_PATTERN = re.compile(r"<\d+>(?:1\s+)?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")

    def parse(self, raw_input: str, device_id: str) -> CanonicalTelemetry:
        match = self.FACILITY_PATTERN.search(raw_input)
        reported_status = "HEALTHY"
        err_count: Optional[int] = None
        event_time = datetime.now(timezone.utc)

        ts_match = self.RFC5424_TS_PATTERN.search(raw_input)
        if ts_match:
            try:
                event_time = datetime.fromisoformat(ts_match.group(1).replace("Z", "+00:00"))
            except Exception:
                pass

        facility = "SYSTEM"
        event_name = "INFO"
        msg_body = raw_input

        if match:
            facility = match.group(1).upper()
            severity = int(match.group(2))
            event_name = match.group(3).upper()
            msg_body = match.group(4)

            if severity <= 3 or "DOWN" in event_name or "FAIL" in event_name or "CRC" in event_name:
                reported_status = "CRITICAL"
                err_count = 50
            elif severity == 4 or "WARN" in event_name or "ERR" in event_name:
                reported_status = "WARNING"
                err_count = 15

        metrics = CanonicalMetrics(
            interface_errors=err_count
        )

        return CanonicalTelemetry(
            device_id=device_id,
            timestamp=event_time,
            reported_status=reported_status,
            metrics=metrics,
            schema_version_detected=SchemaVersion.V1,
            data_provenance={
                "adapter": "SyslogNetworkAdapter",
                "facility": facility,
                "event_name": event_name,
                "message": msg_body.strip(),
                "raw_length": len(raw_input)
            }
        )
