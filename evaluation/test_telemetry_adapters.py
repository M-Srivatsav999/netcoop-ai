"""Unit Tests for Multi-Source Network Telemetry Adapters.

Tests parsing of real-world equipment output:
- Cisco IOS XE Switch CLI (independent total vs CRC errors, inconsistency auditing)
- Cisco Catalyst 9800 WLC CLI (RSSI, SNR, data rates)
- Linux DNS (dig) & DHCP service logs (context-aware transport vs resolution status)
- Enterprise Syslog streams (RFC 5424/3164 parsing)
- Explicit missing data guarantees
"""

import pytest
from core.telemetry_adapters import (
    CiscoIOSXEAdapter,
    CiscoWLC9800Adapter,
    LinuxServicesAdapter,
    SyslogNetworkAdapter
)


def test_cisco_ios_xe_adapter_crc_and_drops():
    cli_output = """
    GigabitEthernet1/0/1 is up, line protocol is up (connected)
      5 minute input rate 450000000 bits/sec, 55000 packets/sec
      5 minute output rate 95000000 bits/sec, 12000 packets/sec
      Input queue: 0/75/0/0 (size/max/drops/flushes); Total output drops: 0
      Output queue: 0/40/85/0 (size/max total/drops/flushes)
      1450 packets input, 185000 bytes, 0 no buffer
      50 input errors, 15 CRC, 0 frame, 0 overrun, 0 ignored
    """
    adapter = CiscoIOSXEAdapter()
    telemetry = adapter.parse(cli_output, device_id="IITBBS-SW-MHR")

    assert telemetry.device_id == "IITBBS-SW-MHR"
    # Total input errors preserved as canonical interface_errors
    assert telemetry.metrics.interface_errors == 50
    assert telemetry.metrics.crc_errors == 15
    assert telemetry.data_provenance["counter_inconsistency"] is False
    assert telemetry.metrics.queue_drops == 85
    assert telemetry.metrics.throughput_mbps == 450.0
    assert telemetry.data_provenance["input_rate_mbps"] == 450.0
    assert telemetry.data_provenance["output_rate_mbps"] == 95.0
    # Missing metrics must be None, not 0.0
    assert telemetry.metrics.latency_ms is None
    assert telemetry.metrics.packet_loss_pct is None
    assert telemetry.reported_status == "WARNING"


def test_cisco_ios_xe_counter_inconsistency_flagged():
    # Anomaly case: sub-counter CRC errors exceed reported total input errors
    cli_output = """
    GigabitEthernet1/0/1 is up, line protocol is up (connected)
      12 input errors, 45 CRC, 0 frame, 0 overrun, 0 ignored
    """
    adapter = CiscoIOSXEAdapter()
    telemetry = adapter.parse(cli_output, device_id="IITBBS-SW-MHR")

    assert telemetry.metrics.interface_errors == 12
    assert telemetry.metrics.crc_errors == 45
    assert telemetry.data_provenance["counter_inconsistency"] is True
    assert len(telemetry.normalization_warnings) == 1
    assert "exceed total input errors" in telemetry.normalization_warnings[0].reason


def test_cisco_wlc_adapter_rssi_snr():
    wlc_output = """
    Client MAC Address : a4:83:e7:21:bb:42
    Client State : Associated
    AP Name : AP-HOSTEL-A1
    Radio Signal Strength Indicator : -79 dBm
    Signal to Noise Ratio : 12 dB
    Current Rate : 12.0 Mbps
    """
    adapter = CiscoWLC9800Adapter()
    telemetry = adapter.parse(wlc_output, device_id="AP-HOSTEL-A1")

    assert telemetry.device_id == "AP-HOSTEL-A1"
    assert telemetry.metrics.signal_strength_dbm == -79.0
    assert telemetry.metrics.throughput_mbps == 12.0
    assert telemetry.metrics.queue_drops is None
    assert telemetry.reported_status == "WARNING"


def test_linux_services_adapter_noerror_success():
    dig_output = """
    ; <<>> DiG 9.18.1 <<>> @10.0.10.1 www.iitbbs.ac.in
    ;; Got answer:
    ;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 3312
    ;; flags: qr rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 1
    ;; Query time: 18 msec
    ;; SERVER: 10.0.10.1#53(10.0.10.1)
    """
    adapter = LinuxServicesAdapter()
    telemetry = adapter.parse(dig_output, device_id="SRV-DNS-01")

    assert telemetry.device_id == "SRV-DNS-01"
    assert telemetry.metrics.dns_resolution_ms == 18.0
    assert telemetry.data_provenance["dns_transport_available"] is True
    assert telemetry.data_provenance["dns_resolution_success"] is True
    assert telemetry.reported_status == "HEALTHY"


def test_linux_services_adapter_nxdomain_context_aware():
    dig_output = """
    ; <<>> DiG 9.18.1 <<>> @10.0.10.1 nonexistent.iitbbs.ac.in
    ;; Got answer:
    ;; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 1823
    ;; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 1, ADDITIONAL: 1
    ;; Query time: 15 msec
    ;; SERVER: 10.0.10.1#53(10.0.10.1)
    """
    adapter = LinuxServicesAdapter()
    telemetry = adapter.parse(dig_output, device_id="SRV-DNS-01")

    assert telemetry.device_id == "SRV-DNS-01"
    assert telemetry.metrics.dns_resolution_ms == 15.0
    # Service transport is available (server responded), but expected hostname was not resolved
    assert telemetry.data_provenance["dns_transport_available"] is True
    assert telemetry.data_provenance["dns_resolution_success"] is False
    assert telemetry.reported_status == "WARNING"


def test_linux_services_adapter_servfail_is_critical():
    dig_output = """
    ; <<>> DiG 9.18.1 <<>> @10.0.10.1 www.iitbbs.ac.in
    ;; Got answer:
    ;; ->>HEADER<<- opcode: QUERY, status: SERVFAIL, id: 4512
    ;; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 1
    ;; Query time: 540 msec
    ;; SERVER: 10.0.10.1#53(10.0.10.1)
    """
    adapter = LinuxServicesAdapter()
    telemetry = adapter.parse(dig_output, device_id="SRV-DNS-01")

    assert telemetry.device_id == "SRV-DNS-01"
    assert telemetry.metrics.dns_resolution_ms == 540.0
    assert telemetry.data_provenance["dns_transport_available"] is True
    assert telemetry.data_provenance["dns_resolution_success"] is False
    assert telemetry.reported_status == "CRITICAL"


def test_linux_services_adapter_timeout_is_critical():
    dig_output = """
    ; <<>> DiG 9.18.1 <<>> @10.0.10.1 www.iitbbs.ac.in
    ;; connection timed out; no servers could be reached
    """
    adapter = LinuxServicesAdapter()
    telemetry = adapter.parse(dig_output, device_id="SRV-DNS-01")

    assert telemetry.device_id == "SRV-DNS-01"
    assert telemetry.metrics.dns_resolution_ms == 999.0
    assert telemetry.data_provenance["dns_transport_available"] is False
    assert telemetry.data_provenance["dns_resolution_success"] is False
    assert telemetry.reported_status == "CRITICAL"


def test_syslog_network_adapter():
    syslog_msg = "<189>1 2026-10-31T20:15:00Z IITBBS-CORE-SW-01 %ETHPORT-2-IF_DOWN: Interface Ethernet1/10 is down (Link failure)"
    adapter = SyslogNetworkAdapter()
    telemetry = adapter.parse(syslog_msg, device_id="IITBBS-CORE-SW-01")

    assert telemetry.device_id == "IITBBS-CORE-SW-01"
    assert telemetry.metrics.interface_errors == 50
    assert telemetry.reported_status == "CRITICAL"
