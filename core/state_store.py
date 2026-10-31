"""Persistent Workflow State and Pause/Resume Session Store.

Provides durable checkpointing, recovery, and resumable diagnostic investigations (Page 3 of NetCoop AI spec).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowCheckpoint(BaseModel):
    """Atomic serialized snapshot of an in-flight diagnostic investigation."""
    session_id: str
    phase: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_paused: bool = False
    telemetry_count: int = 0
    findings_count: int = 0
    arbitration_decision: Optional[str] = None
    state_payload: Dict[str, Any] = Field(default_factory=dict)


class SessionStateStore:
    """Manages filesystem-backed durable diagnostic session checkpoints."""

    DEFAULT_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"

    def __init__(self, store_dir: Optional[Path | str] = None) -> None:
        self.store_dir = Path(store_dir or self.DEFAULT_STORE_DIR)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        sanitized = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return self.store_dir / f"session_{sanitized}.json"

    def save_checkpoint(
        self,
        session_id: str,
        phase: str,
        state_payload: Dict[str, Any],
        is_paused: bool = False,
        telemetry_count: int = 0,
        findings_count: int = 0,
        arbitration_decision: Optional[str] = None
    ) -> WorkflowCheckpoint:
        """Atomically persist investigation checkpoint to disk."""
        checkpoint = WorkflowCheckpoint(
            session_id=session_id,
            phase=phase,
            is_paused=is_paused,
            telemetry_count=telemetry_count,
            findings_count=findings_count,
            arbitration_decision=arbitration_decision,
            state_payload=state_payload
        )
        filepath = self._get_path(session_id)
        temp_file = filepath.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(checkpoint.model_dump_json(indent=2))
        temp_file.replace(filepath)
        return checkpoint

    def pause_session(self, session_id: str, current_state: Dict[str, Any]) -> WorkflowCheckpoint:
        """Mark session as paused with frozen state data."""
        return self.save_checkpoint(
            session_id=session_id,
            phase="PAUSED_FOR_OPERATOR_REVIEW",
            state_payload=current_state,
            is_paused=True
        )

    def resume_session(self, session_id: str) -> Optional[WorkflowCheckpoint]:
        """Load and resume paused checkpoint from durable store."""
        filepath = self._get_path(session_id)
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        checkpoint = WorkflowCheckpoint(**data)
        checkpoint.is_paused = False
        checkpoint.phase = "RESUMED_IN_FLIGHT"
        return checkpoint

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Enumerate all persisted sessions in store."""
        sessions = []
        for f in self.store_dir.glob("session_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    sessions.append({
                        "session_id": data.get("session_id"),
                        "phase": data.get("phase"),
                        "is_paused": data.get("is_paused"),
                        "created_at": data.get("created_at"),
                        "arbitration_decision": data.get("arbitration_decision")
                    })
            except Exception:
                continue
        return sessions
