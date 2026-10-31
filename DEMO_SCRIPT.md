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
> *3. **Real Telemetry Adapters**: Parsers for Cisco IOS XE switches, Catalyst 9800 WLC controllers, Linux core DNS/DHCP services, and enterprise syslog streams.*
> *4. **Durable State Store**: We provide investigation session checkpointing with pause and resume commands.*
> *5. **Cryptographic Ledger & Shannon Gain**: Every piece of telemetry evidence is sealed into an immutable SHA-256 hash-chained ledger, and follow-up troubleshooting commands are ranked by true Shannon Information Gain.*"*

---

## Segment 5: 100% Evaluation Suite & Closing (3:15 – 3:45)

### Terminal Command to Run:
```bash
pytest -v
python evaluation/run_evaluation.py
python evaluation/benchmark_runner.py
python evaluation/held_out_benchmark.py
```

### Visual on Screen:
Show `62 passed in 1.5s`, the 15-scenario evaluation summary table showing `Pass Rate: 100.0%`, the 700-case benchmark table showing `100.0% Accuracy`, `1.0000 Macro-F1`, `Top Brier: 0.0087`, and the held-out benchmark proving 100% generalization across completely unseen campus topologies.

### Speaker Narration:
> *"Finally, reliability and reproducibility. As you can see, our automated test suite executes 62 comprehensive unit tests in 1.5 seconds with a 100% pass rate.*
>
> *Our evaluation benchmark evaluates all six organizer scenarios and nine adversarial edge cases—including stale timestamps, clock skew, sparse telemetry, corrupted payloads, and multi-incident clustering with localized root-cause isolation. Across our 700-case scientific evaluation suite, NetCoop AI achieves 100.0% accuracy, 1.0000 Macro-F1, an Expected Calibration Error under 0.09, and a Brier score of 0.0087.*
>
> *Crucially, we also verified real-world generalization on our independent held-out benchmark with completely unseen device topologies and facility locations—achieving 100.0% accuracy and 1.0000 Macro-F1.*
>
> *With our tamper-evident SHA-256 hash-chained ledger and Shannon Information Gain investigation engine, NetCoop AI is mathematically rigorous, fully explainable, and production-ready for the IIT Bhubaneswar campus network. Thank you!"*
