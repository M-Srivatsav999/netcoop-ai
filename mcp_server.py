"""Model Context Protocol (MCP) Standard Server for NetCoop AI.

Exposes deterministic diagnostic tools, topology resources, and remediation simulations
to MCP-compliant agent clients over standard JSON-RPC 2.0 stdio (Page 3 of NetCoop AI spec).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import NetworkIntelligenceOrchestrator
from core.remediation import RemediationSimulator
from core.state_store import SessionStateStore
from core.topology import TopologyEngine


class NetCoopMCPServer:
    """Standard Model Context Protocol (MCP) Server implementing network diagnostic tools."""

    def __init__(self) -> None:
        self.orchestrator = NetworkIntelligenceOrchestrator()
        self.topology = TopologyEngine()
        self.state_store = SessionStateStore()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return MCP-compliant tool metadata."""
        return [
            {
                "name": "diagnose_telemetry",
                "description": "Analyze raw network telemetry across specialized agents and return a unified incident diagnosis.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "telemetry": {
                            "type": "string",
                            "description": "JSON string containing single device or batch campus telemetry records (Schema V1, V2, or V3)."
                        },
                        "incident_id": {
                            "type": "string",
                            "description": "Optional identifier for the incident."
                        }
                    },
                    "required": ["telemetry"]
                }
            },
            {
                "name": "get_blast_radius",
                "description": "Calculate downstream blast radius and affected device tier breakdown for a failing node.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device ID to inspect (e.g., 'BLDG-SW-HOSTEL-A' or 'IITBBS-SW-MHR')."
                        }
                    },
                    "required": ["device_id"]
                }
            },
            {
                "name": "simulate_remediation",
                "description": "Generate a dry-run corrective engineering simulation plan with projected before/after KPIs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "root_cause": {
                            "type": "string",
                            "description": "Diagnosed root cause (e.g., 'LINK_CONGESTION', 'HARDWARE_FAILURE', 'WEAK_WIFI')."
                        },
                        "affected_devices": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of affected device IDs."
                        }
                    },
                    "required": ["root_cause", "affected_devices"]
                }
            },
            {
                "name": "get_campus_topology",
                "description": "Retrieve the 5-tier hierarchical campus network topology nodes and adjacency links.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch and execute tool call."""
        if tool_name == "diagnose_telemetry":
            raw_input = arguments.get("telemetry", "")
            inc_id = arguments.get("incident_id")
            result = self.orchestrator.process(raw_input, incident_id=inc_id)
            return {
                "report": result.report.model_dump(),
                "duration_ms": result.total_duration_ms,
                "diagnosed_root_cause": result.report.suspected_root_cause,
                "confidence": result.report.confidence
            }
        elif tool_name == "get_blast_radius":
            dev = arguments.get("device_id", "")
            return self.topology.get_blast_radius(dev)
        elif tool_name == "simulate_remediation":
            cause = arguments.get("root_cause", "")
            devices = arguments.get("affected_devices", [])
            sim = RemediationSimulator.simulate_remediation(cause, devices)
            return sim.model_dump()
        elif tool_name == "get_campus_topology":
            return {
                "total_nodes": len(self.topology.nodes),
                "root_core_switch": self.topology.root_id,
                "nodes": [n.to_dict() for n in self.topology.nodes.values()]
            }
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def handle_json_rpc(self, request_str: str) -> str:
        """Handle JSON-RPC 2.0 protocol request."""
        try:
            req = json.loads(request_str)
            req_id = req.get("id")
            method = req.get("method")

            if method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": self.get_tool_definitions()}
                }
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                result_data = self.execute_tool(name, args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result_data, indent=2)}]}
                }
            elif method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "netcoop-ai-mcp", "version": "1.0.0"},
                        "capabilities": {"tools": {}}
                    }
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method {method} not found"}
                }
        except Exception as e:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal RPC error: {str(e)}"}
            }
        return json.dumps(resp)

    def run_stdio(self) -> None:
        """Run standard I/O communication loop for MCP clients."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            response = self.handle_json_rpc(line)
            sys.stdout.write(response + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    server = NetCoopMCPServer()
    # If run in test mode via argument
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        tools = server.get_tool_definitions()
        print(f"MCP Server initialized successfully with {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}: {t['description']}")
    else:
        server.run_stdio()
