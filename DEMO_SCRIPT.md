# NetCoop AI — 3-to-5 Minute Demo Video Script
**Hackathon Presentation & Video Recording Guide**  
*Project: NetCoop AI — Multi-Agent Network Fault Diagnosis and Interoperability*

---

## Video Quick Overview
- **Target Video Duration**: 3:45 to 4:15 (under the 5-minute hard limit).
- **Video Resolution**: 1080p (1920x1080) at 60fps or 30fps.
- **Tools Needed**: Terminal window (split or fullscreen, dark mode), Web browser tab (showing `report.html`).

---

## Segment 1: The Problem & Context (0:00 – 0:45)

### Visual on Screen:
Show the terminal with title banner or slide showing **"NetCoop AI — Multi-Agent Network Intelligence"** and **IIT Bhubaneswar Campus Topology**.

### Speaker Narration:
> *"Hello judges! Welcome to NetCoop AI, our production-grade multi-agent network fault diagnosis system built for the IIT Bhubaneswar campus network.*
>
> *At IIT Bhubaneswar, network issues like latency spikes in Mahanadi Hostel, packet drops in the School of Electrical Sciences, or DNS failures disrupt academic and residential life. Diagnosing these is notoriously difficult because telemetry arrives from heterogeneous vendors, in inconsistent units, with noisy or missing fields, and sometimes even deceptive status labels.*
>
> *To solve this, we engineered an explainable, 100% deterministic multi-agent expert system that operates completely offline with zero external LLM hallucinations, zero magic numbers, and strict Pydantic mathematical consensus."*

---

## Segment 2: Architecture & Inter-Agent Communication (0:45 – 1:30)

### Visual on Screen:
Show `README.md` architectural ASCII diagram or terminal command highlighting the 5 specialized agents.

### Speaker Narration:
> *"Our architecture features five specialized agents communicating over typed Pydantic contracts:*
>
> 1. *First, the **TelemetryNormalizer** unifies V1, V2, and V3 heterogeneous schemas into a strict Canonical Internal Message, mapping missing metrics to None rather than zero.*
> 2. *Second, our **Telemetry Agent** analyzes transport KPIs like latency, jitter, and packet loss.*
> 3. *Third, our **Infrastructure Agent** monitors CPU/memory saturation, tail-drops, and physical CRC errors.*
> 4. *Fourth, our **Connectivity Agent** traverses the 5-tier campus topology graph, measures Wi-Fi RSSI attenuation, and calculates downstream blast radius.*
> 5. *Fifth, the **Correlation Agent** acts as Central Arbiter, resolving conflicts between competing explanations and calculating calibrated confidence scores.*
> 6. *Finally, the **Reporter Agent** emits the unified JSON report conforming strictly to Page 5 of the NetCoop AI specification."*

---

## Segment 3: Live Incident Diagnosis & Interactive NOC UI (1:30 – 2:30)

### Action on Screen:
Launch the Web NOC Dashboard or Rich Terminal Dashboard:
```bash
python web_ui.py
# Or terminal: python main.py --scenario data/scenarios/scenario_3_hardware_failure.json --dashboard
```

### Visual on Screen:
Open `http://127.0.0.1:8000` in the browser (or show the Rich terminal). Click on `scenario_3_hardware_failure.json` and hit **"Run Multi-Agent Diagnosis"**. Show the 5-Tier Campus Topology, Agent Message contracts, and Page 5 JSON inspector.

### Speaker Narration:
> *"Let's run a live incident diagnosis. Here we pass Scenario 3: a physical link degradation on the Mahanadi Hostel building switch.*
>
> *Notice three critical capabilities on the dashboard:*
> *First: The generator untrusted label claimed this switch was 'HEALTHY'. Our Evidence Engine immediately detected 740 CRC errors, flagged the generator label as untrusted, and formally recorded a contradiction.*
> *Second: Look at the inter-agent message table and campus topology. The system mapped the failure directly to IITBBS-SW-MHR and isolated the blast radius to its connected APs in under 2 milliseconds.*
> *Third: Notice our deterministic conflict resolution. High packet loss with zero errors means Link Congestion, but high packet loss with CRC errors resolves definitively to Hardware Failure.*
> *The output JSON precisely matches Page 5 of the problem statement, including the status, affected devices, structured evidence, and attribution sources."*

---

## Segment 4: Optional Innovations — Remediation Simulator & MCP Server (2:30 – 3:15)

### Terminal Command to Run:
```bash
python main.py --scenario data/scenarios/scenario_2_congestion.json --simulate-remediation --export-html report.html
```

### Visual on Screen:
Switch to the browser and refresh `report.html` to show the modern Dark Mode NOC briefing, structured evidence table, and dry-run remediation preview.

### Speaker Narration:
> *"To address the optional enhancements on Page 3:*
>
> *1. **Automated Remediation Simulator**: We built a safe, dry-run remediation module that generates corrective CLI playbooks with projected KPI recovery deltas without modifying live infrastructure without human approval.*
> *2. **Model Context Protocol (MCP)**: By running `python mcp_server.py --test`, our system exposes diagnostic tools, topology resources, and remediation simulations directly to any MCP-compliant client or agent over JSON-RPC 2.0.*
> *3. **Durable State Store**: We provide investigation session checkpointing with pause and resume commands.*
> *4. **Interactive HTML Dashboard**: Operators receive this turnkey, offline executive dashboard."*

---

## Segment 5: 100% Evaluation Suite & Closing (3:15 – 3:45)

### Terminal Command to Run:
```bash
pytest -v
python main.py --evaluate
```

### Visual on Screen:
Show `26 passed in 1.2s` and the 12-scenario evaluation summary table showing `Pass Rate: 100.0%` with `Reproducible: YES` on all rows.

### Speaker Narration:
> *"Finally, reliability and reproducibility. As you can see, our automated test suite runs 26 unit tests in 1.2 seconds with a 100% pass rate.*
>
> *Our evaluation benchmark runs all six organizer scenarios and six real-world edge cases—including stale timestamps, sparse telemetry, corrupted payloads, and multiple simultaneous failures. In all cases, identical inputs yield 100% reproducible diagnostic outputs.*
>
> *NetCoop AI is deterministic, explainable, extensible, and production-ready for IIT Bhubaneswar. Thank you!"*
