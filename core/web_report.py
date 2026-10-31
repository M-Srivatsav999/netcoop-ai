"""Standalone Interactive HTML Executive Incident Report Generator.

Renders modern NOC-themed single-file offline visual dashboard (Page 3 & Page 5 of NetCoop AI spec).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.orchestrator import OrchestrationResult
from core.remediation import SimulationResult


class HTMLReportGenerator:
    """Generates self-contained, responsive HTML reports for network incident briefings."""

    @classmethod
    def generate_html(
        cls,
        result: OrchestrationResult,
        remediation_sim: Optional[SimulationResult] = None
    ) -> str:
        report = result.report
        conf_pct = round(report.confidence * 100, 1)

        conf_color = "#10b981" if report.confidence >= 0.75 else "#f59e0b" if report.confidence >= 0.45 else "#ef4444"
        status_badge_bg = "#065f46" if report.status == "diagnosed" else "#78350f"
        status_badge_text = "#34d399" if report.status == "diagnosed" else "#fbbf24"

        # Evidence table rows
        evidence_rows = ""
        for ev in report.supporting_evidence:
            evidence_rows += f"""
            <tr>
                <td class="metric-cell">{ev.metric}</td>
                <td class="value-cell"><code>{ev.value}</code></td>
                <td>{ev.interpretation}</td>
            </tr>
            """
        if not evidence_rows:
            evidence_rows = "<tr><td colspan='3' style='text-align:center;'>No active fault evidence registered.</td></tr>"

        # Actions list
        actions_list = ""
        for idx, act in enumerate(report.recommended_actions, 1):
            actions_list += f"<li><strong>Step {idx}:</strong> {act}</li>"

        # Affected devices pills
        dev_pills = ""
        if report.affected_devices:
            for dev in report.affected_devices:
                dev_pills += f"<span class='badge dev-badge'>{dev}</span> "
        else:
            dev_pills = "<span class='badge' style='background:#1e293b; color:#94a3b8;'>None (Nominal Network Baseline)</span>"

        # Evidence sources pills
        source_pills = ""
        for src in report.evidence_sources:
            source_pills += f"<span class='badge src-badge'>{src}</span> "

        # Remediation block
        remediation_html = ""
        if remediation_sim:
            sim_actions = ""
            for act in remediation_sim.actions:
                recovery_json = json.dumps(act.projected_recovery, indent=2)
                sim_actions += f"""
                <div class="sim-action-card">
                    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                        <span style="font-weight:700; color:#38bdf8;">{act.action_id} — {act.action_type}</span>
                        <span class="badge" style="background:#0369a1; color:#e0f2fe;">{act.safety_level}</span>
                    </div>
                    <div style="color:#94a3b8; font-size:0.9rem; margin-bottom:6px;">{act.rationale}</div>
                    <pre class="cli-box"><code>{act.simulated_cli_command}</code></pre>
                    <details style="margin-top:8px;">
                        <summary style="cursor:pointer; color:#a5b4fc; font-size:0.85rem;">View Projected KPI Delta</summary>
                        <pre class="cli-box" style="margin-top:4px;"><code>{recovery_json}</code></pre>
                    </details>
                </div>
                """
            remediation_html = f"""
            <div class="card" style="margin-top:24px;">
                <h2>Simulated Automated Remediation (Dry-Run Playbook)</h2>
                <p style="color:#94a3b8; font-size:0.9rem;">
                    Safety Status: <span style="color:#34d399; font-weight:600;">{remediation_sim.human_in_the_loop_status}</span> | 
                    Risk Assessment: <span style="color:#38bdf8; font-weight:600;">{remediation_sim.risk_level}</span>
                </p>
                <div style="margin-top:12px;">{sim_actions}</div>
                <div style="margin-top:12px; font-size:0.8rem; color:#64748b; font-style:italic;">
                    {remediation_sim.dry_run_disclaimer}
                </div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NetCoop AI — Incident Briefing {report.incident_id}</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #131b2e;
            --border: #23314f;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --font-mono: 'Consolas', 'Courier New', monospace;
        }}
        body {{
            background: var(--bg);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 32px 20px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            max-width: 1040px;
            width: 100%;
        }}
        .header {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }}
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 16px;
        }}
        .header-title {{
            font-size: 1.4rem;
            font-weight: 800;
            color: var(--accent);
            letter-spacing: -0.5px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-badge {{
            background: {status_badge_bg};
            color: {status_badge_text};
        }}
        .dev-badge {{
            background: #1e3a5f;
            color: #7dd3fc;
            border: 1px solid #0284c7;
        }}
        .src-badge {{
            background: #312e81;
            color: #c7d2fe;
            border: 1px solid #4f46e5;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
        }}
        .stat-label {{
            color: var(--text-muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .stat-val {{
            font-size: 1.5rem;
            font-weight: 700;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        h2 {{
            font-size: 1.15rem;
            margin-top: 0;
            margin-bottom: 16px;
            color: var(--accent);
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            color: var(--text-muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            background: rgba(15, 23, 42, 0.6);
        }}
        .metric-cell {{
            font-family: var(--font-mono);
            color: #38bdf8;
            font-weight: 600;
        }}
        .value-cell {{
            font-family: var(--font-mono);
            color: #fbbf24;
        }}
        ul, ol {{
            margin: 0;
            padding-left: 20px;
        }}
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        .sim-action-card {{
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .cli-box {{
            background: #020617;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 8px 12px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            color: #4ade80;
            overflow-x: auto;
            margin: 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div class="header-title">NetCoop AI — Multi-Agent Network Intelligence</div>
                <div>
                    <span class="badge status-badge">{report.status}</span>
                </div>
            </div>
            <div style="font-size:1.1rem; margin-bottom:12px;">
                Incident Target: <strong>{report.incident_id}</strong>
            </div>
            <div style="display:flex; gap:16px; color:var(--text-muted); font-size:0.85rem;">
                <div>Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
                <div>Trace: {result.arbitration_result.execution_trace_id}</div>
                <div>Execution Duration: {result.total_duration_ms} ms</div>
            </div>
        </div>

        <div class="grid">
            <div class="stat-card">
                <div class="stat-label">Suspected Root Cause</div>
                <div class="stat-val" style="color:#ef4444; font-size:1.25rem;">{report.suspected_root_cause}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Diagnostic Confidence</div>
                <div class="stat-val" style="color:{conf_color};">{conf_pct}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Telemetry Completeness</div>
                <div class="stat-val" style="color:#38bdf8;">{round(result.arbitration_result.evidence_completeness * 100, 1)}%</div>
            </div>
        </div>

        <div class="card">
            <h2>Affected Infrastructure Elements</h2>
            <div>{dev_pills}</div>
            <div style="margin-top:14px; color:var(--text-muted); font-size:0.85rem;">
                Evidence Reporting Sources: {source_pills}
            </div>
        </div>

        <div class="card">
            <h2>Structured Evidentiary Audit Trail (Page 5 Schema)</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width:25%;">Metric Key</th>
                        <th style="width:20%;">Observed Value</th>
                        <th style="width:55%;">Diagnostic Interpretation</th>
                    </tr>
                </thead>
                <tbody>
                    {evidence_rows}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Recommended Remediation Playbook</h2>
            <ol>
                {actions_list}
            </ol>
        </div>

        {remediation_html}

        <div class="card">
            <h2>Known Limitations & Uncertainty Factors</h2>
            <ul>
                {''.join(f'<li>{lim}</li>' for lim in report.limitations)}
            </ul>
        </div>
    </div>
</body>
</html>
"""
        return html
