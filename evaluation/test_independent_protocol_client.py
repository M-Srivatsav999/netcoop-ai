"""Independent Protocol Client Test for NetCoop AI.

Tests external interoperability by implementing an independent third-party client
that communicates via the JSON-RPC 2.0 MCP interface:
1. Tool discovery (tools/list)
2. Execution of diagnose_telemetry with real payloads
3. Execution of get_blast_radius
4. Execution of simulate_remediation
5. Error handling for unknown methods and malformed JSON-RPC requests
"""

import json
import pytest
from typing import Any, Dict
from mcp_server import NetCoopMCPServer


class ExternalMonitoringProtocolClient:
    """Simulates an external, independently authored monitoring client communicating via JSON-RPC 2.0."""

    def __init__(self, server: NetCoopMCPServer) -> None:
        self.server = server
        self.next_req_id = 1

    def send_request(self, method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        req_id = self.next_req_id
        self.next_req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        raw_response = self.server.handle_json_rpc(json.dumps(payload))
        return json.loads(raw_response)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call tool and unwrap standard MCP content payload."""
        resp = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        if "error" in resp:
            return resp
        raw_text = resp["result"]["content"][0]["text"]
        return json.loads(raw_text)


def test_independent_client_tool_discovery():
    """External client discovers all available NetCoop AI diagnostic tools."""
    server = NetCoopMCPServer()
    client = ExternalMonitoringProtocolClient(server)

    resp = client.send_request("tools/list")
    assert resp.get("jsonrpc") == "2.0"
    assert "result" in resp
    tools = resp["result"].get("tools", [])
    tool_names = [t["name"] for t in tools]

    assert "diagnose_telemetry" in tool_names
    assert "get_blast_radius" in tool_names
    assert "simulate_remediation" in tool_names
    assert "get_campus_topology" in tool_names


def test_independent_client_diagnose_telemetry():
    """External client submits raw telemetry payload and verifies Page 5 compliant diagnosis."""
    server = NetCoopMCPServer()
    client = ExternalMonitoringProtocolClient(server)

    telemetry_payload = json.dumps([
        {
            "device_id": "IITBBS-SW-MHR",
            "timestamp": "2026-10-31T20:00:00Z",
            "status": "WARNING",
            "metrics": {
                "latency_ms": 175.0,
                "packet_loss_pct": 5.0,
                "queue_drops": 90,
                "interface_errors": 0
            }
        }
    ])

    data = client.call_tool("diagnose_telemetry", {
        "telemetry": telemetry_payload,
        "incident_id": "EXT-CLIENT-INC-1"
    })

    assert data.get("diagnosed_root_cause") == "LINK_CONGESTION"
    assert data.get("confidence", 0.0) >= 0.70
    report = data.get("report", {})
    assert report.get("incident_id") == "EXT-CLIENT-INC-1"
    assert "IITBBS-SW-MHR" in report.get("affected_devices", [])


def test_independent_client_blast_radius():
    """External client calculates downstream impact for a building switch."""
    server = NetCoopMCPServer()
    client = ExternalMonitoringProtocolClient(server)

    data = client.call_tool("get_blast_radius", {"device_id": "IITBBS-SW-MHR"})

    assert data.get("root_device_id") == "IITBBS-SW-MHR"
    assert data.get("total_downstream_count") >= 2
    assert "AP-MHR-W1" in data.get("downstream_device_ids", [])


def test_independent_client_remediation_simulation():
    """External client simulates automated remediation dry-run."""
    server = NetCoopMCPServer()
    client = ExternalMonitoringProtocolClient(server)

    data = client.call_tool("simulate_remediation", {
        "root_cause": "HARDWARE_FAILURE",
        "affected_devices": ["IITBBS-SW-MHR"]
    })

    assert data.get("suspected_root_cause") == "HARDWARE_FAILURE"
    assert len(data.get("actions", [])) >= 1
    # Check that safety boundaries are respected
    for act in data.get("actions", []):
        assert act.get("target_device") == "IITBBS-SW-MHR"
        assert "CLI" in act.get("simulated_cli_command", "") or "interface" in act.get("simulated_cli_command", "")


def test_independent_client_malformed_rpc_error_handling():
    """External client sends unknown method and invalid params; server responds with JSON-RPC error."""
    server = NetCoopMCPServer()
    client = ExternalMonitoringProtocolClient(server)

    # 1. Unknown method
    resp1 = client.send_request("non_existent_method")
    assert "error" in resp1
    assert resp1["error"]["code"] == -32601

    # 2. Unknown tool name
    resp2 = client.send_request("tools/call", {"name": "invalid_tool", "arguments": {}})
    assert "error" in resp2
