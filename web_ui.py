"""NetCoop AI — Full Interactive Web NOC Dashboard.

Launches a local FastAPI web server providing an interactive visual dashboard
for live incident diagnosis, topology visualization, synthetic generation,
remediation simulation, and Page 5 JSON report export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.orchestrator import NetworkIntelligenceOrchestrator
from core.remediation import RemediationSimulator
from core.state_store import SessionStateStore
from core.topology import TopologyEngine
from data.generator import SyntheticTelemetryGenerator
from protocol.models import SchemaVersion

app = FastAPI(title="NetCoop AI — Campus Network Intelligence")

orchestrator = NetworkIntelligenceOrchestrator()
topology = TopologyEngine()
state_store = SessionStateStore()

SCENARIOS_DIR = Path(__file__).resolve().parent / "data" / "scenarios"


@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = Path(__file__).resolve().parent / "core" / "static" / "index.html"
    if html_file.exists():
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NetCoop AI Web Dashboard</h1>"


@app.get("/api/scenarios")
async def list_scenarios():
    """List available pre-built test scenarios."""
    scenarios = []
    for f in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                scenarios.append({
                    "filename": f.name,
                    "id": data.get("scenario_id", f.stem),
                    "description": data.get("description", "")
                })
        except Exception:
            continue
    return JSONResponse(content={"scenarios": scenarios})


@app.get("/api/scenario/{filename}")
async def get_scenario(filename: str):
    """Retrieve scenario payload."""
    filepath = SCENARIOS_DIR / filename
    if not filepath.exists():
        return JSONResponse(status_code=404, content={"error": "Not found"})
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@app.post("/api/diagnose")
async def diagnose(request: Request):
    """Run full multi-agent deterministic diagnosis on telemetry payload."""
    try:
        body = await request.json()
        raw_telemetry = body.get("telemetry", body)
        incident_id = body.get("incident_id")
        schema_ver_str = body.get("schema_version", "AUTO")

        explicit_version = None
        if schema_ver_str != "AUTO":
            try:
                explicit_version = SchemaVersion(schema_ver_str)
            except Exception:
                pass

        result = orchestrator.process(
            raw_input=raw_telemetry,
            incident_id=incident_id,
            explicit_version=explicit_version
        )

        remediation = RemediationSimulator.simulate_remediation(
            root_cause=result.report.suspected_root_cause,
            affected_devices=result.report.affected_devices,
            telemetry_records=result.canonical_telemetry
        )

        return JSONResponse(content={
            "report": result.report.model_dump(mode="json"),
            "markdown_summary": result.markdown_summary,
            "arbitration": result.arbitration_result.model_dump(mode="json"),
            "agent_findings": [f.model_dump(mode="json") for f in result.agent_findings],
            "agent_messages": [m.model_dump(mode="json") for m in result.agent_messages],
            "remediation_simulation": remediation.model_dump(mode="json"),
            "canonical_telemetry": [t.model_dump(mode="json") for t in result.canonical_telemetry],
            "execution_trace": result.execution_trace,
            "duration_ms": result.total_duration_ms
        })
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "traceback": traceback.format_exc()}
        )


@app.get("/api/topology")
async def get_topology():
    """Get IIT Bhubaneswar campus topology graph."""
    nodes = [n.to_dict() for n in topology.nodes.values()]
    return JSONResponse(content={
        "network_name": "IIT Bhubaneswar Campus Network (NetCoop AI)",
        "root_core_switch": topology.root_id,
        "total_nodes": len(nodes),
        "nodes": nodes
    })


@app.get("/api/blast-radius/{device_id}")
async def blast_radius(device_id: str):
    """Get blast radius for a device."""
    return JSONResponse(content=topology.get_blast_radius(device_id))


@app.get("/api/device-cli/{device_id}")
async def device_cli(device_id: str):
    """Generate realistic Cisco IOS CLI inspection for Cisco Packet Tracer style inspection."""
    node = topology.get_node(device_id)
    tier = node.tier.value if node else "UNKNOWN"
    
    # Realistic Cisco models
    if "CORE" in device_id:
        model = "Cisco Catalyst 9500-48Y4C (100G/40G Datacenter Core)"
        intf = "TenGigabitEthernet1/1/1"
        speed = "100000000 Kbit/sec"
    elif "DIST" in device_id:
        model = "Cisco Catalyst 9300-48UXM (40G Uplink Distribution)"
        intf = "TenGigabitEthernet1/0/1"
        speed = "40000000 Kbit/sec"
    elif "AP" in device_id:
        model = "Cisco Catalyst 9130AX Series Wi-Fi 6 AP"
        intf = "GigabitEthernet0"
        speed = "2500000 Kbit/sec"
    else:
        model = "Cisco Catalyst 9200-48P Enterprise Switch"
        intf = "GigabitEthernet1/0/1"
        speed = "1000000 Kbit/sec"

    # Contextual telemetry counters
    crc_errors = 740 if "MHR" in device_id else 0
    queue_drops = 145 if "MHR" in device_id else 0
    latency_val = 185.0 if "MHR" in device_id else 8.2

    cisco_interfaces = f"""{device_id}# show interfaces {intf}
{intf} is up, line protocol is up (connected)
  Hardware is Ethernet, address is 001a.a420.{abs(hash(device_id)) % 10000:04x} (bia 001a.a420.{abs(hash(device_id)) % 10000:04x})
  Description: NetCoop AI Monitored Uplink Interface
  MTU 1500 bytes, BW {speed}, DLY 10 usec,
     reliability 255/255, txload 185/255, rxload 140/255
  Encapsulation ARPA, loopback not set
  Keepalive set (10 sec)
  Full-duplex, 10Gb/s, media type is SFP-10G-SR
  output flow-control is on, input flow-control is on
  Queueing strategy: fifo
  Output queue: {queue_drops}/40 (size/max), {queue_drops} total drops
  5 minute input rate 45200000 bits/sec, 5840 packets/sec
  5 minute output rate 98400000 bits/sec, 12600 packets/sec
     14820921 packets input, 1289401290 bytes, 0 no buffer
     Received 0 broadcasts, 0 runts, 0 giants, 0 throttles
     {crc_errors} input errors, {crc_errors} CRC, 0 frame, 0 overrun, 0 ignored
     0 watchdog, 0 multicast, 0 pause input
     28401928 packets output, 2840192800 bytes, 0 underruns
     0 output errors, 0 collisions, 1 interface resets"""

    cisco_logging = f"""{device_id}# show logging | include {intf}
%LINK-3-UPDOWN: Interface {intf}, changed state to up
%LINEPROTO-5-UPDOWN: Line protocol on Interface {intf}, changed state to up
%ETH-5-TAIL_DROP: Output queue overflow detected on {intf}: {queue_drops} packets dropped
%SYS-4-CRC_ALERT: Physical layer CRC threshold exceeded on {intf}: {crc_errors} frame check errors"""

    cisco_traceroute = f"""{device_id}# traceroute IITBBS-CORE-SW-01
Type escape sequence to abort.
Tracing the route to IITBBS-CORE-SW-01 (10.0.0.1)
  1 {device_id} (Local Gateway) 0.812 msec
  2 IITBBS-DIST-HOSTELS (10.10.0.1) 3.421 msec
  3 IITBBS-CORE-SW-01 (10.0.0.1) {latency_val} msec [RTT Measured]"""

    cisco_version = f"""{device_id}# show version
Cisco IOS XE Software, Version 17.09.04a
Cisco IOS Software [Cupertino], Catalyst L3 Switch Software
Technical Support: http://www.cisco.com/techsupport
Compiled Fri 18-Aug-23 by prod_rel_team

ROM: IOS-XE ROMMON
{device_id} uptime is 42 days, 14 hours, 28 minutes
System returned to ROM by reload
System image file is "bootflash:packages.conf"
cisco {model} with 4194304K/2097152K bytes of memory.
Processor board ID FOC2419U09K"""

    return JSONResponse(content={
        "device_id": device_id,
        "model": model,
        "tier": tier,
        "interface_name": intf,
        "crc_errors": crc_errors,
        "queue_drops": queue_drops,
        "cli_output": {
            "show_interfaces": cisco_interfaces,
            "show_logging": cisco_logging,
            "show_version": cisco_version,
            "traceroute": cisco_traceroute
        }
    })


@app.post("/api/generate-synthetic")
async def generate_synthetic(request: Request):
    """Generate synthetic noisy multi-schema telemetry."""
    body = await request.json()
    scenario = body.get("scenario", "congestion")
    schema_ver = body.get("schema_version", "V1")
    noise = float(body.get("noise", 0.05))
    missing = float(body.get("missing", 0.0))

    data = SyntheticTelemetryGenerator.generate_scenario(
        scenario_type=scenario,
        schema_version=schema_ver,
        noise_level=noise,
        missing_rate=missing
    )
    return JSONResponse(content=data)


@app.get("/api/sessions")
async def get_sessions():
    """List persisted investigation sessions."""
    return JSONResponse(content={"sessions": state_store.list_sessions()})


@app.post("/api/sessions/pause")
async def pause_session(request: Request):
    """Pause and checkpoint an investigation."""
    try:
        body = await request.json()
        sess_id = body.get("session_id", "SESS-AUTO")
        payload = body.get("payload", {})
        chk = state_store.pause_session(sess_id, payload)
        return JSONResponse(content=chk.model_dump(mode="json"))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


def start_server(host: str = "127.0.0.1", port: int = 8000):
    print(f"\n=======================================================")
    print(f" NETCOOP AI — INTERACTIVE NOC WEB DASHBOARD")
    print(f" Access UI in browser at: http://{host}:{port}")
    print(f"=======================================================\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
