import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def current_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = workspace_dir or os.getcwd()
        aidlc_dir = os.path.join(self.workspace_dir, ".aidlc")
        os.makedirs(aidlc_dir, exist_ok=True)
        self.db_path = os.path.join(aidlc_dir, "state.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    story_id TEXT,
                    current_phase TEXT,
                    current_status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    state_json TEXT
                );

                CREATE TABLE IF NOT EXISTS phase_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    phase TEXT,
                    attempt INTEGER,
                    status TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    artifact_ids TEXT,
                    findings TEXT,
                    cost TEXT,
                    digest_artifact_id TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    type TEXT,
                    logical_name TEXT,
                    phase TEXT,
                    version INTEGER,
                    content_uri TEXT,
                    checksum TEXT,
                    verdict TEXT,
                    metadata_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    phase TEXT,
                    severity TEXT,
                    category TEXT,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    finding_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );
                """
            )

    def get_active_run_id(self) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", ("active_run_id",))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_active_run_id(self, run_id: str) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("active_run_id", run_id),
            )

    def create_run(
        self,
        project_id: str = "default-project",
        story_id: str = "default-story",
        custom_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = current_iso_timestamp()
        run_id = custom_run_id or f"run_{int(time.time() * 1000)}_{os.urandom(3).hex()}"

        initial_state: Dict[str, Any] = {
            "run_id": run_id,
            "project_id": project_id,
            "story_id": story_id,
            "phase": {
                "current": "intake",
                "status": "pending",
            },
            "phase_history": [],
            "artifacts": {},
            "git": {
                "changed_files": [],
                "active_conflicts": [],
            },
            "budget": {
                "cap": 100.0,
                "estimated": 0.0,
                "actual": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "tool_cost": 0.0,
            },
            "gates": {
                "required": [],
                "approved": [],
            },
            "findings": {
                "open": [],
                "resolved": [],
                "accepted_risk": [],
            },
            "metadata": {
                "actor": os.getenv("USER", "local-developer"),
                "environment": "local",
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        }

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO runs (run_id, project_id, story_id, current_phase, current_status, created_at, updated_at, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    story_id,
                    initial_state["phase"]["current"],
                    initial_state["phase"]["status"],
                    timestamp,
                    timestamp,
                    json.dumps(initial_state),
                ),
            )

        self.set_active_run_id(run_id)
        return initial_state

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT state_json FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["state_json"])

    def get_active_run(self) -> Optional[Dict[str, Any]]:
        active_id = self.get_active_run_id()
        if not active_id:
            return None
        return self.get_run(active_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT run_id, project_id, story_id, current_phase, current_status, created_at, updated_at
            FROM runs ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def save_run_state(self, state: Dict[str, Any]) -> None:
        state["metadata"]["updated_at"] = current_iso_timestamp()
        with self.conn:
            self.conn.execute(
                """
                UPDATE runs
                SET current_phase = ?, current_status = ?, updated_at = ?, state_json = ?
                WHERE run_id = ?
                """,
                (
                    state["phase"]["current"],
                    state["phase"]["status"],
                    state["metadata"]["updated_at"],
                    json.dumps(state),
                    state["run_id"],
                ),
            )

    def start_phase(self, run_id: str, phase: str) -> Tuple[Dict[str, Any], int]:
        state = self.get_run(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found")

        previous_attempts = sum(1 for h in state["phase_history"] if h["phase"] == phase)
        attempt = previous_attempts + 1
        started_at = current_iso_timestamp()

        state["phase"] = {
            "current": phase,
            "status": "running",
        }

        history_entry = {
            "phase": phase,
            "attempt": attempt,
            "status": "running",
            "started_at": started_at,
            "artifact_ids": [],
            "findings": [],
            "cost": {},
            "digest_artifact_id": None,
        }

        state["phase_history"].append(history_entry)
        self.save_run_state(state)

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO phase_history (run_id, phase, attempt, status, started_at, artifact_ids, findings, cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    phase,
                    attempt,
                    "running",
                    started_at,
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps({}),
                ),
            )

        return state, attempt

    def record_phase_completion(
        self,
        run_id: str,
        phase: str,
        attempt: int,
        status: str,
        artifact_ids: List[str],
        findings: List[Dict[str, Any]],
        cost: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = self.get_run(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found")

        completed_at = current_iso_timestamp()

        target_entry = None
        for h in state["phase_history"]:
            if h["phase"] == phase and h["attempt"] == attempt:
                target_entry = h
                break

        if target_entry:
            target_entry["status"] = status
            target_entry["completed_at"] = completed_at
            target_entry["artifact_ids"] = artifact_ids
            target_entry["findings"] = findings
            target_entry["cost"] = cost
        else:
            state["phase_history"].append(
                {
                    "phase": phase,
                    "attempt": attempt,
                    "status": status,
                    "started_at": completed_at,
                    "completed_at": completed_at,
                    "artifact_ids": artifact_ids,
                    "findings": findings,
                    "cost": cost,
                    "digest_artifact_id": None,
                }
            )

        state["phase"]["status"] = status

        if cost.get("inputTokens"):
            state["budget"]["tokens_in"] += cost["inputTokens"]
        if cost.get("outputTokens"):
            state["budget"]["tokens_out"] += cost["outputTokens"]
        if cost.get("cost"):
            state["budget"]["actual"] += cost["cost"]

        for f in findings:
            if f.get("status") == "open":
                if not any(of.get("id") == f.get("id") for of in state["findings"]["open"]):
                    state["findings"]["open"].append(f)

        self.save_run_state(state)

        with self.conn:
            self.conn.execute(
                """
                UPDATE phase_history
                SET status = ?, completed_at = ?, artifact_ids = ?, findings = ?, cost = ?
                WHERE run_id = ? AND phase = ? AND attempt = ?
                """,
                (
                    status,
                    completed_at,
                    json.dumps(artifact_ids),
                    json.dumps(findings),
                    json.dumps(cost),
                    run_id,
                    phase,
                    attempt,
                ),
            )

        return state

    def add_artifact(self, run_id: str, artifact: Dict[str, Any]) -> None:
        state = self.get_run(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found")

        key = artifact.get("logical_name") or artifact.get("type", "unknown")
        state["artifacts"][key] = artifact
        self.save_run_state(state)

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO artifacts (id, run_id, type, logical_name, phase, version, content_uri, checksum, verdict, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content_uri = excluded.content_uri,
                    checksum = excluded.checksum,
                    verdict = excluded.verdict,
                    metadata_json = excluded.metadata_json
                """,
                (
                    artifact["id"],
                    run_id,
                    artifact["type"],
                    artifact.get("logical_name", key),
                    artifact["phase"],
                    artifact["version"],
                    artifact["content_uri"],
                    artifact["checksum"],
                    artifact.get("verdict", "info"),
                    json.dumps(artifact),
                    artifact["created_at"],
                ),
            )

    def add_finding(self, run_id: str, finding: Dict[str, Any]) -> None:
        state = self.get_run(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found")

        if not any(of.get("id") == finding.get("id") for of in state["findings"]["open"]):
            state["findings"]["open"].append(finding)
            self.save_run_state(state)

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO findings (id, run_id, phase, severity, category, title, description, status, finding_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    finding_json = excluded.finding_json
                """,
                (
                    finding["id"],
                    run_id,
                    finding["phase"],
                    finding["severity"],
                    finding.get("category", "correctness"),
                    finding["title"],
                    finding.get("description", ""),
                    finding.get("status", "open"),
                    json.dumps(finding),
                    current_iso_timestamp(),
                ),
            )

    def get_phase_history(self, run_id: str) -> List[Dict[str, Any]]:
        state = self.get_run(run_id)
        return state["phase_history"] if state else []

    def close(self) -> None:
        self.conn.close()

