"""Auditoría persistente en SQLite.

Guarda lo mínimo para poder responder a "¿quién aprobó qué y cuándo?" sin
convertirse en un log de prompts ni de secretos:

* ``devices``   — dispositivos emparejados (token hasheado, nunca en claro).
* ``approvals`` — una fila por petición, con su resultado.
* ``events``    — eventos de ciclo de vida y mensajes de error.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .util import iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    command     TEXT NOT NULL,
    cwd         TEXT NOT NULL,
    risk        TEXT NOT NULL,
    risk_details TEXT,
    status      TEXT NOT NULL,
    option_id   TEXT,
    source      TEXT,
    device_id   TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    agent_id    TEXT,
    approval_id TEXT,
    device_id   TEXT,
    payload     TEXT
);

CREATE TABLE IF NOT EXISTS agent_visibility (
    agent_id   TEXT PRIMARY KEY,
    hidden     INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_pins (
    agent_id  TEXT PRIMARY KEY,
    pinned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_limits (
    agent_id      TEXT PRIMARY KEY,
    daily_tokens  INTEGER NOT NULL DEFAULT 0,
    weekly_tokens INTEGER NOT NULL DEFAULT 0,
    monthly_tokens INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_usage_daily (
    agent_id TEXT NOT NULL,
    day      TEXT NOT NULL,
    tokens   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(agent_id, day)
);

CREATE TABLE IF NOT EXISTS agent_usage_state (
    agent_id TEXT PRIMARY KEY,
    tokens   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_approvals_created ON approvals(created_at);
"""


class AuditLog:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            columns = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(approvals)").fetchall()
            }
            if "risk_details" not in columns:
                self._conn.execute(
                    "ALTER TABLE approvals ADD COLUMN risk_details TEXT"
                )
            # Al arrancar, ninguna aprobación puede seguir "pending": el broker
            # vive en memoria y las de la ejecución anterior ya no existen.
            self._conn.execute(
                "UPDATE approvals SET status = 'stale', resolved_at = ?"
                " WHERE status = 'pending'",
                (iso(),),
            )

    # -- dispositivos -----------------------------------------------------

    def add_device(
        self, device_id: str, name: str, token_hash: str
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO devices(device_id, name, token_hash, created_at, revoked)"
                " VALUES (?, ?, ?, ?, 0)",
                (device_id, name, token_hash, iso()),
            )

    def find_active_device_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT device_id, name FROM devices WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            ).fetchone()
        return dict(row) if row else None

    def touch_device(self, device_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE devices SET last_seen_at = ? WHERE device_id = ?",
                (iso(), device_id),
            )

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT device_id, name, created_at, last_seen_at, revoked FROM devices ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_device(self, device_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE devices SET revoked = 1 WHERE device_id = ?", (device_id,)
            )
        return cur.rowcount > 0

    def delete_device(self, device_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

    # -- aprobaciones -----------------------------------------------------

    def record_approval(
        self,
        *,
        approval_id: str,
        agent_id: str,
        kind: str,
        title: str,
        command: str,
        cwd: str,
        risk: str,
        created_at: str,
        expires_at: str,
        risk_details: list[str] | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO approvals("
                "approval_id, agent_id, kind, title, command, cwd, risk, risk_details,"
                " status, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    approval_id,
                    agent_id,
                    kind,
                    title,
                    command,
                    cwd,
                    risk,
                    json.dumps(risk_details, ensure_ascii=False)
                    if risk_details
                    else None,
                    created_at,
                    expires_at,
                ),
            )

    def update_approval(
        self,
        approval_id: str,
        *,
        status: str,
        option_id: str | None,
        source: str | None,
        device_id: str | None,
        resolved_at: str,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE approvals SET status = ?, option_id = ?, source = ?, device_id = ?,"
                " resolved_at = ? WHERE approval_id = ?",
                (status, option_id, source, device_id, resolved_at, approval_id),
            )

    def recent_approvals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            if item.get("risk_details"):
                try:
                    item["risk_details"] = json.loads(item["risk_details"])
                except json.JSONDecodeError:
                    item["risk_details"] = []
            else:
                item["risk_details"] = []
            out.append(item)
        return out

    # -- visibilidad ------------------------------------------------------

    def hidden_agents(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT agent_id FROM agent_visibility WHERE hidden = 1 ORDER BY agent_id"
            ).fetchall()
        return [row["agent_id"] for row in rows]

    def set_hidden(self, agent_id: str, hidden: bool) -> list[str]:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_visibility(agent_id, hidden, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(agent_id) DO UPDATE SET hidden = excluded.hidden,"
                " updated_at = excluded.updated_at",
                (agent_id, 1 if hidden else 0, iso()),
            )
        return self.hidden_agents()

    # -- fijados ----------------------------------------------------------

    def pinned_agents(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT agent_id FROM agent_pins ORDER BY pinned_at, agent_id"
            ).fetchall()
        return [row["agent_id"] for row in rows]

    def set_pinned(self, agent_id: str, pinned: bool) -> list[str]:
        with self._lock, self._conn:
            if pinned:
                self._conn.execute(
                    "INSERT INTO agent_pins(agent_id, pinned_at) VALUES (?, ?)"
                    " ON CONFLICT(agent_id) DO NOTHING",
                    (agent_id, iso()),
                )
            else:
                self._conn.execute(
                    "DELETE FROM agent_pins WHERE agent_id = ?", (agent_id,)
                )
        return self.pinned_agents()

    def remove_pin(self, agent_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM agent_pins WHERE agent_id = ?", (agent_id,)
            )

    # -- eventos ----------------------------------------------------------

    def add_event(
        self,
        kind: str,
        *,
        agent_id: str | None = None,
        approval_id: str | None = None,
        device_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO events(ts, kind, agent_id, approval_id, device_id, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    iso(),
                    kind,
                    agent_id,
                    approval_id,
                    device_id,
                    json.dumps(payload, ensure_ascii=False) if payload else None,
                ),
            )

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            if item.get("payload"):
                try:
                    item["payload"] = json.loads(item["payload"])
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    # -- configuración persistente ---------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                (key, str(value), iso()),
            )

    # -- límites y uso por agente -----------------------------------------

    def agent_limits(self) -> dict[str, dict[str, int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agent_limits ORDER BY agent_id"
            ).fetchall()
        return {
            str(row["agent_id"]): {
                "daily": int(row["daily_tokens"]),
                "weekly": int(row["weekly_tokens"]),
                "monthly": int(row["monthly_tokens"]),
            }
            for row in rows
        }

    def set_agent_limits(
        self, agent_id: str, daily: int, weekly: int, monthly: int
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_limits("
                "agent_id, daily_tokens, weekly_tokens, monthly_tokens, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(agent_id) DO UPDATE SET"
                " daily_tokens = excluded.daily_tokens,"
                " weekly_tokens = excluded.weekly_tokens,"
                " monthly_tokens = excluded.monthly_tokens,"
                " updated_at = excluded.updated_at",
                (agent_id, int(daily), int(weekly), int(monthly), iso()),
            )

    def add_agent_usage(self, agent_id: str, day: str, delta: int) -> None:
        if delta <= 0:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_usage_daily(agent_id, day, tokens)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(agent_id, day) DO UPDATE SET"
                " tokens = tokens + excluded.tokens",
                (agent_id, day, int(delta)),
            )

    def agent_usage_since(self, agent_id: str, since_day: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) AS total"
                " FROM agent_usage_daily WHERE agent_id = ? AND day >= ?",
                (agent_id, since_day),
            ).fetchone()
        return int(row["total"]) if row else 0

    def usage_state(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT agent_id, tokens FROM agent_usage_state"
            ).fetchall()
        return {str(row["agent_id"]): int(row["tokens"]) for row in rows}

    def set_usage_state(self, agent_id: str, tokens: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_usage_state(agent_id, tokens, updated_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(agent_id) DO UPDATE SET"
                " tokens = excluded.tokens, updated_at = excluded.updated_at",
                (agent_id, int(tokens), iso()),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
