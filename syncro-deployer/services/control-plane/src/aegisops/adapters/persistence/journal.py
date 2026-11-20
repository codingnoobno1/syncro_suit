"""SQLite WAL-mode persistent state journal for Syncro Deployer, idempotency keys & desktop agents."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SqliteStateJournal:
    """Thread-safe lightweight SQLite WAL journal ensuring deployment state & idempotency survive restarts."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            if self._db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS syncro_deployments (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    mode TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS syncro_agents (
                    agent_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_state (
                    k TEXT PRIMARY KEY,
                    v_json TEXT NOT NULL
                )
                """
            )

    def save_deployment(
        self,
        deployment_id: str,
        idempotency_key: str | None,
        mode: str,
        stage: str,
        payload: dict[str, Any],
        updated_at: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO syncro_deployments (id, idempotency_key, mode, stage, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    mode=excluded.mode,
                    stage=excluded.stage,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (deployment_id, idempotency_key, mode, stage, json.dumps(payload), updated_at),
            )

    def get_deployment_by_idempotency(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM syncro_deployments WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return dict(json.loads(row["payload_json"])) if row else None

    def get_deployment(self, deployment_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM syncro_deployments WHERE id = ?", (deployment_id,)
        ).fetchone()
        return dict(json.loads(row["payload_json"])) if row else None

    def list_deployments(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload_json FROM syncro_deployments ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(json.loads(r["payload_json"])) for r in rows]

    def save_agent(self, agent_id: str, payload: dict[str, Any], updated_at: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO syncro_agents (agent_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (agent_id, json.dumps(payload), updated_at),
            )

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload_json FROM syncro_agents ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(json.loads(r["payload_json"])) for r in rows]

    def stats(self) -> dict[str, Any]:
        dep_cnt = self._conn.execute("SELECT COUNT(*) FROM syncro_deployments").fetchone()[0]
        ag_cnt = self._conn.execute("SELECT COUNT(*) FROM syncro_agents").fetchone()[0]
        return {
            "backend": "sqlite-wal" if self._db_path != ":memory:" else "sqlite-memory",
            "db_path": self._db_path,
            "persisted_deployments": int(dep_cnt),
            "registered_desktop_agents": int(ag_cnt),
        }

    def close(self) -> None:
        self._conn.close()
