"""Descubrimiento de agentes locales a partir de sus datos en disco.

OpenCode tiene una API HTTP (``discovery.py``); el resto deja rastro en archivos
o SQLite:

* **Claude Code**: transcripciones JSONL en ``~/.claude/projects``.
* **Codex**: catálogo SQLite en ``~/.codex/sqlite`` y, como respaldo,
  ``state_5.sqlite`` y rollouts JSONL en ``~/.codex/sessions``.
* **Gemini CLI**: sesiones JSON en ``~/.gemini/tmp``.
* **Antigravity**: ``conversation_summaries.db`` bajo ``~/.gemini/antigravity``.
* **GitHub Copilot CLI**: JSON de sesión bajo ``~/.copilot`` (best effort).

Todas las fuentes son de solo lectura, tolerantes a formatos incompletos y no
bloquean el bucle de eventos: el gestor las ejecuta en un hilo. Si una fuente no
existe, devuelve una lista vacía; no es un error.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .audit import AuditLog
from .config import Settings
from .discovery import DetectedSession, mark_offline, sync_detected
from .protocol import AgentStatus
from .state import StateStore

OFFLINE_AFTER_FAILURES = 3
MAX_FILE_BYTES = 12 * 1024 * 1024


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ms_from_value(value: Any) -> int:
    """Normaliza segundos, milisegundos, ISO 8601 y datetime de SQLite a ms."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        number = float(value)
        if number <= 0:
            return 0
        # 10_000_000_000 ms = año 2286; los segundos actuales son ~1.7e9.
        return int(number) if number > 10_000_000_000 else int(number * 1000)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            return _ms_from_value(float(text))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    return 0


def _clean_text(value: Any, limit: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>\n]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].strip()


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
    return ""


def _status_for(updated_ms: int, now_ms: int, active_s: float) -> AgentStatus:
    if updated_ms > 0 and now_ms - updated_ms <= active_s * 1000:
        return AgentStatus.RUNNING
    return AgentStatus.IDLE


def _session(
    session_id: str,
    name: str,
    model: str,
    cwd: str,
    updated_ms: int,
    *,
    provider: str,
    now_ms: int,
    active_s: float,
    cost: float = 0.0,
    tokens: int = 0,
    output: str = "",
    forced_status: AgentStatus | None = None,
) -> DetectedSession:
    return DetectedSession(
        session_id=session_id,
        name=name or session_id,
        model=model or "unknown",
        cwd=cwd or "",
        updated_ms=updated_ms,
        busy_ms=0,
        idle_ms=0,
        cost=cost,
        tokens=tokens,
        provider=provider,
        forced_status=forced_status or _status_for(updated_ms, now_ms, active_s),
        output=output,
    )


def _uri_to_path(value: Any) -> str:
    if isinstance(value, list) and value:
        value = value[0]
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if text.startswith("file:"):
        parsed = urlparse(text)
        path = unquote(parsed.path or "")
        # file:///C:/... -> /C:/...; en Windows sobra la barra inicial.
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return path.replace("/", "\\") if os.name == "nt" else path
    return text


def _tokens_from(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, dict):
        return 0
    total = _int(value.get("total")) or _int(value.get("total_tokens"))
    if total:
        return total
    return sum(
        _int(value.get(key))
        for key in (
            "input",
            "output",
            "input_tokens",
            "output_tokens",
            "reasoning",
            "thoughts",
            "reasoning_output_tokens",
        )
    )


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------


class LocalSource:
    provider = "unknown"
    label = "Agente"

    @property
    def key(self) -> str:
        return f"{self.provider}:{type(self).__name__}"

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        return []


class ClaudeCodeSource(LocalSource):
    provider = "anthropic"
    label = "Claude Code"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / ".claude" / "projects")
        self._cache: dict[str, tuple[int, int, DetectedSession]] = {}

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        if not self.root.is_dir():
            return []

        candidates: list[tuple[int, int, int, Path]] = []
        try:
            for path in self.root.rglob("*.jsonl"):
                if "subagents" in path.parts or path.name.startswith("agent-"):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                mtime_ms = int(stat.st_mtime * 1000)
                if mtime_ms < now_ms - recency_ms:
                    continue
                candidates.append((mtime_ms, stat.st_mtime_ns, stat.st_size, path))
        except OSError:
            pass
        candidates.sort(key=lambda item: item[0], reverse=True)

        sessions: list[DetectedSession] = []
        for _, mtime_ns, size, path in candidates:
            session = self._read(path, mtime_ns, size, now_ms, active_s)
            if session is not None:
                sessions.append(session)
            if len(sessions) >= limit:
                break
        return sessions

    def _read(
        self,
        path: Path,
        mtime_ns: int,
        size: int,
        now_ms: int,
        active_s: float,
    ) -> DetectedSession | None:
        cached = self._cache.get(str(path))
        if cached and cached[0] == mtime_ns and cached[1] == size:
            base = cached[2]
            return replace(
                base,
                forced_status=_status_for(base.updated_ms, now_ms, active_s),
            )

        session_id = path.stem
        cwd = ""
        model = ""
        title = ""
        tokens = 0
        output = ""
        updated = int(mtime_ns / 1_000_000)

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if len(line) > 1_000_000:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(item, dict):
                        continue

                    candidate_id = item.get("sessionId")
                    if isinstance(candidate_id, str) and candidate_id:
                        session_id = candidate_id
                    candidate_cwd = item.get("cwd")
                    if isinstance(candidate_cwd, str) and candidate_cwd:
                        cwd = candidate_cwd

                    timestamp = _ms_from_value(item.get("timestamp"))
                    if timestamp:
                        updated = max(updated, timestamp)

                    kind = item.get("type")
                    if kind == "summary" and not title:
                        title = _clean_text(item.get("summary"))
                    message = item.get("message")
                    if kind == "user" and not title and isinstance(message, dict):
                        title = _clean_text(_content_text(message.get("content")))
                    if isinstance(message, dict):
                        candidate_model = message.get("model")
                        if isinstance(candidate_model, str) and candidate_model:
                            model = candidate_model
                        if kind == "assistant":
                            text = _content_text(message.get("content"))
                            if text:
                                output = _clean_text(text, 240)
                        usage = message.get("usage")
                        if isinstance(usage, dict):
                            tokens += _int(usage.get("input_tokens")) + _int(
                                usage.get("output_tokens")
                            )
        except OSError:
            return None

        name = title or f"Claude Code {session_id[-6:]}"
        session = _session(
            session_id,
            name,
            model or "claude",
            cwd,
            updated,
            provider=self.provider,
            now_ms=now_ms,
            active_s=active_s,
            tokens=tokens,
            output=output,
        )
        self._cache[str(path)] = (
            mtime_ns,
            size,
            replace(session, forced_status=None),
        )
        return session


class CodexSource(LocalSource):
    provider = "openai"
    label = "Codex"

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or (Path.home() / ".codex")

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        if not self.home.is_dir():
            return []

        models, token_counts = self._thread_meta()
        sessions: dict[str, DetectedSession] = {}

        for name in ("codex.db", "codex-dev.db"):
            for session in self._scan_catalog(
                self.home / "sqlite" / name,
                models,
                token_counts,
                now_ms,
                recency_ms,
                active_s,
            ):
                current = sessions.get(session.session_id)
                if current is None or session.updated_ms > current.updated_ms:
                    sessions[session.session_id] = session

        for session in self._scan_state(
            models, token_counts, now_ms, recency_ms, active_s
        ):
            sessions.setdefault(session.session_id, session)

        for session in self._scan_rollouts(now_ms, recency_ms, active_s):
            sessions.setdefault(session.session_id, session)

        ordered = sorted(
            sessions.values(), key=lambda item: item.updated_ms, reverse=True
        )
        return ordered[:limit]

    def _thread_meta(self) -> tuple[dict[str, str], dict[str, int]]:
        path = self.home / "state_5.sqlite"
        if not path.is_file():
            return {}, {}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, model, tokens_used FROM threads"
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return {}, {}
        models = {
            str(row["id"]): str(row["model"])
            for row in rows
            if row["id"] and row["model"]
        }
        tokens = {
            str(row["id"]): _int(row["tokens_used"])
            for row in rows
            if row["id"]
        }
        return models, tokens

    def _scan_catalog(
        self,
        path: Path,
        models: dict[str, str],
        token_counts: dict[str, int],
        now_ms: int,
        recency_ms: int,
        active_s: float,
    ) -> list[DetectedSession]:
        if not path.is_file():
            return []
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT thread_id, display_title, source_created_at,"
                " source_updated_at, cwd, source_kind, host_id"
                " FROM local_thread_catalog"
                " WHERE IFNULL(missing_candidate, 0) = 0"
                " AND (host_id = 'local' OR IFNULL(source_kind, '') <> 'chatgpt')"
                " ORDER BY source_updated_at DESC"
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return []

        sessions: list[DetectedSession] = []
        for row in rows:
            thread_id = str(row["thread_id"] or "")
            if not thread_id:
                continue
            updated = _ms_from_value(
                row["source_updated_at"] or row["source_created_at"]
            )
            if updated < now_ms - recency_ms:
                continue
            title = _clean_text(row["display_title"])
            sessions.append(
                _session(
                    thread_id,
                    title or f"Codex {thread_id[-6:]}",
                    models.get(thread_id, "codex"),
                    str(row["cwd"] or ""),
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                    tokens=token_counts.get(thread_id, 0),
                )
            )
        return sessions

    def _scan_state(
        self,
        models: dict[str, str],
        token_counts: dict[str, int],
        now_ms: int,
        recency_ms: int,
        active_s: float,
    ) -> list[DetectedSession]:
        path = self.home / "state_5.sqlite"
        if not path.is_file():
            return []
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, name, preview, cwd, model,"
                " updated_at_ms, updated_at, tokens_used"
                " FROM threads WHERE IFNULL(archived, 0) = 0"
                " ORDER BY COALESCE(updated_at_ms, updated_at * 1000) DESC"
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return []

        sessions: list[DetectedSession] = []
        for row in rows:
            thread_id = str(row["id"] or "")
            if not thread_id:
                continue
            updated = _ms_from_value(row["updated_at_ms"]) or _ms_from_value(
                row["updated_at"]
            )
            if updated < now_ms - recency_ms:
                continue
            title = _clean_text(row["title"] or row["name"] or row["preview"])
            sessions.append(
                _session(
                    thread_id,
                    title or f"Codex {thread_id[-6:]}",
                    str(row["model"] or models.get(thread_id) or "codex"),
                    str(row["cwd"] or ""),
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                    tokens=_int(row["tokens_used"]) or token_counts.get(thread_id, 0),
                )
            )
        return sessions

    def _scan_rollouts(
        self, now_ms: int, recency_ms: int, active_s: float
    ) -> list[DetectedSession]:
        root = self.home / "sessions"
        if not root.is_dir():
            return []

        candidates: list[tuple[int, Path]] = []
        try:
            for path in root.rglob("*.jsonl"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                mtime_ms = int(stat.st_mtime * 1000)
                if mtime_ms < now_ms - recency_ms:
                    continue
                candidates.append((mtime_ms, path))
        except OSError:
            pass
        candidates.sort(key=lambda item: item[0], reverse=True)

        sessions: list[DetectedSession] = []
        for mtime_ms, path in candidates[:20]:
            parsed = self._read_rollout(path, mtime_ms)
            if parsed is None:
                continue
            session_id, cwd, model, tokens, updated = parsed
            sessions.append(
                _session(
                    session_id,
                    f"Codex {session_id[-6:]}",
                    model or "codex",
                    cwd,
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                    tokens=tokens,
                )
            )
        return sessions

    def _read_rollout(
        self, path: Path, mtime_ms: int
    ) -> tuple[str, str, str, int, int] | None:
        session_id = ""
        cwd = ""
        model = ""
        tokens = 0
        updated = mtime_ms
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index > 4000 or len(line) > 1_000_000:
                        break
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    timestamp = _ms_from_value(item.get("timestamp"))
                    if timestamp:
                        updated = max(updated, timestamp)
                    payload = item.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    if item.get("type") == "session_meta":
                        session_id = str(payload.get("id") or session_id)
                        cwd = str(payload.get("cwd") or cwd)
                    elif item.get("type") == "turn_context":
                        model = str(payload.get("model") or model)
                    elif item.get("type") == "event_msg":
                        info = payload.get("info")
                        if isinstance(info, dict):
                            usage = info.get("total_token_usage")
                            if isinstance(usage, dict):
                                tokens = max(tokens, _tokens_from(usage))
        except OSError:
            return None
        if not session_id:
            return None
        return session_id, cwd, model, tokens, updated


class GeminiSource(LocalSource):
    provider = "google"
    label = "Gemini"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / ".gemini" / "tmp")

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        if not self.root.is_dir():
            return []

        candidates: list[tuple[int, Path]] = []
        try:
            for path in self.root.rglob("session-*.json"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                mtime_ms = int(stat.st_mtime * 1000)
                if mtime_ms < now_ms - recency_ms:
                    continue
                candidates.append((mtime_ms, path))
        except OSError:
            pass
        candidates.sort(key=lambda item: item[0], reverse=True)

        sessions: list[DetectedSession] = []
        for mtime_ms, path in candidates:
            data = _read_json(path)
            if not isinstance(data, dict):
                continue
            session_id = str(
                data.get("sessionId")
                or data.get("session_id")
                or path.stem.removeprefix("session-")
            )
            updated = max(
                _ms_from_value(data.get("lastUpdated")),
                _ms_from_value(data.get("last_updated")),
                _ms_from_value(data.get("startTime")),
                mtime_ms,
            )
            title = ""
            model = ""
            tokens = 0
            output = ""
            messages = data.get("messages")
            if isinstance(messages, list):
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    role = message.get("type") or message.get("role")
                    if role in ("user", "human") and not title:
                        title = _clean_text(_content_text(message.get("content")))
                    if role in ("gemini", "assistant", "model"):
                        text = _content_text(message.get("content"))
                        if text:
                            output = _clean_text(text, 240)
                    candidate_model = message.get("model")
                    if isinstance(candidate_model, str) and candidate_model:
                        model = candidate_model
                    timestamp = _ms_from_value(message.get("timestamp"))
                    if timestamp:
                        updated = max(updated, timestamp)
                    tokens = max(tokens, _tokens_from(message.get("tokens")))

            if updated < now_ms - recency_ms:
                continue

            cwd = (
                str(data.get("cwd") or data.get("projectRoot") or "")
                or self._project_root(path)
            )
            sessions.append(
                _session(
                    session_id,
                    title or f"Gemini {session_id[-6:]}",
                    model or "gemini",
                    cwd,
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                    tokens=tokens,
                    output=output,
                )
            )
            if len(sessions) >= limit:
                break
        return sessions

    def _project_root(self, path: Path) -> str:
        for candidate in (path.parent.parent / ".project_root", path.parent / ".project_root"):
            try:
                if candidate.is_file():
                    text = candidate.read_text(encoding="utf-8", errors="replace").strip()
                    if text:
                        return text
            except OSError:
                continue
        return ""


class AntigravitySource(LocalSource):
    provider = "antigravity"
    label = "Antigravity"

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (
            Path.home() / ".gemini" / "antigravity" / "conversation_summaries.db"
        )

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        if not self.db_path.is_file():
            return []
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT conversation_id, title, preview, last_modified_time,"
                " workspace_uris, status, agent_name, parent_conversation_id,"
                " not_fully_idle, killed, last_user_input_time"
                " FROM conversation_summaries"
                " WHERE parent_conversation_id IS NULL"
                " ORDER BY last_modified_time DESC"
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return []

        sessions: list[DetectedSession] = []
        for row in rows:
            conversation_id = str(row["conversation_id"] or "")
            if not conversation_id or _int(row["killed"]):
                continue
            updated = _ms_from_value(
                row["last_modified_time"]
            ) or _ms_from_value(row["last_user_input_time"])
            if updated < now_ms - recency_ms:
                continue

            status_text = str(row["status"] or "").lower()
            active = bool(row["not_fully_idle"]) or status_text in {
                "running",
                "active",
                "busy",
                "in_progress",
            }
            forced = AgentStatus.RUNNING if active else None

            title = _clean_text(row["title"] or row["preview"])
            sessions.append(
                _session(
                    conversation_id,
                    title or f"Antigravity {conversation_id[-6:]}",
                    str(row["agent_name"] or "gemini"),
                    _workspace_path(row["workspace_uris"]),
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                    forced_status=forced,
                )
            )
            if len(sessions) >= limit:
                break
        return sessions


def _workspace_path(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return _uri_to_path(value)
    return _uri_to_path(value)


class CursorSource(LocalSource):
    provider = "cursor"
    label = "Cursor"

    def __init__(self, db_path: Path | None = None) -> None:
        appdata = os.environ.get("APPDATA")
        if appdata:
            default = (
                Path(appdata)
                / "Cursor"
                / "User"
                / "globalStorage"
                / "state.vscdb"
            )
        else:
            default = (
                Path.home()
                / "AppData"
                / "Roaming"
                / "Cursor"
                / "User"
                / "globalStorage"
                / "state.vscdb"
            )
        self.db_path = db_path or default

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        if not self.db_path.is_file():
            return []
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return []

        try:
            db_mtime = int(self.db_path.stat().st_mtime * 1000)
            sessions = self._composers(
                conn, now_ms, recency_ms, active_s, db_mtime
            )
            sessions.extend(self._chats(conn, now_ms, recency_ms, active_s, db_mtime))
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        merged: dict[str, DetectedSession] = {}
        for session in sessions:
            current = merged.get(session.session_id)
            if current is None or session.updated_ms > current.updated_ms:
                merged[session.session_id] = session
        ordered = sorted(
            merged.values(), key=lambda item: item.updated_ms, reverse=True
        )
        return ordered[:limit]

    def _value(self, conn: sqlite3.Connection, key: str) -> str | None:
        for table in ("ItemTable", "cursorDiskKV"):
            try:
                row = conn.execute(
                    f'SELECT value FROM "{table}" WHERE key = ?', (key,)
                ).fetchone()
            except sqlite3.Error:
                continue
            if not row or row[0] is None:
                continue
            value = row[0]
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if isinstance(value, str):
                return value
        return None

    def _json(self, conn: sqlite3.Connection, key: str) -> Any:
        value = self._value(conn, key)
        if not isinstance(value, str):
            return None
        try:
            return json.loads(value)
        except ValueError:
            return None

    def _composers(
        self,
        conn: sqlite3.Connection,
        now_ms: int,
        recency_ms: int,
        active_s: float,
        db_mtime: int,
    ) -> list[DetectedSession]:
        data = self._json(conn, "composer.composerData")
        if not isinstance(data, dict):
            return []
        items = data.get("allComposers") or data.get("composers") or []
        if not isinstance(items, list):
            return []

        sessions: list[DetectedSession] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            composer_id = str(item.get("composerId") or item.get("id") or "")
            if not composer_id:
                continue
            updated = (
                _ms_from_value(item.get("lastUpdatedAt"))
                or _ms_from_value(item.get("updatedAt"))
                or _ms_from_value(item.get("createdAt"))
                or db_mtime
            )
            if updated < now_ms - recency_ms:
                continue
            title = _clean_text(
                item.get("name") or item.get("title") or item.get("subtitle")
            )
            model = str(item.get("model") or item.get("modelName") or "cursor")
            sessions.append(
                _session(
                    composer_id,
                    title or f"Cursor {composer_id[-6:]}",
                    model,
                    _cursor_workspace(item),
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                )
            )
        return sessions

    def _chats(
        self,
        conn: sqlite3.Connection,
        now_ms: int,
        recency_ms: int,
        active_s: float,
        db_mtime: int,
    ) -> list[DetectedSession]:
        data = self._json(
            conn, "workbench.panel.aichat.view.aichat.chatdata"
        )
        if not isinstance(data, dict):
            return []
        tabs = data.get("tabs") or data.get("chats") or []
        if not isinstance(tabs, list):
            return []

        sessions: list[DetectedSession] = []
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            tab_id = str(tab.get("tabId") or tab.get("chatId") or tab.get("id") or "")
            if not tab_id:
                continue
            updated = (
                _ms_from_value(tab.get("lastSendTime"))
                or _ms_from_value(tab.get("lastUpdated"))
                or _ms_from_value(tab.get("timestamp"))
                or db_mtime
            )
            if updated < now_ms - recency_ms:
                continue
            title = _clean_text(
                tab.get("chatTitle") or tab.get("title") or tab.get("name")
            )
            model = str(tab.get("model") or "cursor")
            bubbles = tab.get("bubbles")
            if isinstance(bubbles, list):
                for bubble in reversed(bubbles):
                    if isinstance(bubble, dict):
                        candidate = bubble.get("modelType") or bubble.get("model")
                        if isinstance(candidate, str) and candidate:
                            model = candidate
                            break
            sessions.append(
                _session(
                    tab_id,
                    title or f"Cursor {tab_id[-6:]}",
                    model,
                    _cursor_workspace(tab),
                    updated,
                    provider=self.provider,
                    now_ms=now_ms,
                    active_s=active_s,
                )
            )
        return sessions


def _cursor_workspace(item: dict[str, Any]) -> str:
    workspace = (
        item.get("workspaceIdentifier")
        or item.get("workspace")
        or item.get("workspaceUri")
        or ""
    )
    if isinstance(workspace, dict):
        workspace = workspace.get("uri") or workspace.get("configPath") or ""
    return _uri_to_path(workspace)


class CopilotSource(LocalSource):
    provider = "github"
    label = "GitHub Copilot"

    def __init__(self, roots: list[Path] | None = None) -> None:
        base = Path.home() / ".copilot"
        self.roots = roots or [base / "session-state", base / "sessions"]

    def scan(
        self, *, now_ms: int, recency_ms: int, limit: int, active_s: float
    ) -> list[DetectedSession]:
        seen: set[str] = set()
        sessions: list[DetectedSession] = []

        for root in self.roots:
            if not root.is_dir():
                continue
            try:
                paths = list(root.rglob("*.json"))
            except OSError:
                continue
            for path in paths:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size > 2 * 1024 * 1024:
                    continue
                mtime_ms = int(stat.st_mtime * 1000)
                if mtime_ms < now_ms - recency_ms:
                    continue
                data = _read_json(path)
                if not isinstance(data, dict):
                    continue

                session_id = str(
                    data.get("sessionId")
                    or data.get("session_id")
                    or data.get("id")
                    or ""
                )
                if not session_id:
                    continue
                if session_id in seen:
                    continue
                if not any(
                    key in data
                    for key in ("messages", "turns", "conversation", "sessionId", "session_id")
                ) and "session" not in path.name.lower():
                    continue

                updated = (
                    _ms_from_value(data.get("updatedAt"))
                    or _ms_from_value(data.get("updated_at"))
                    or _ms_from_value(data.get("lastUpdated"))
                    or mtime_ms
                )
                if updated < now_ms - recency_ms:
                    continue

                title = _clean_text(
                    data.get("title")
                    or data.get("name")
                    or data.get("summary")
                    or data.get("description")
                )
                cwd = str(
                    data.get("cwd")
                    or data.get("workspace")
                    or data.get("workingDirectory")
                    or data.get("projectPath")
                    or ""
                )
                cwd = _uri_to_path(cwd) if cwd else ""
                tokens = _tokens_from(data.get("tokens") or data.get("usage"))
                seen.add(session_id)
                sessions.append(
                    _session(
                        session_id,
                        title or f"Copilot {session_id[-6:]}",
                        str(data.get("model") or data.get("modelId") or "copilot"),
                        cwd,
                        updated,
                        provider=self.provider,
                        now_ms=now_ms,
                        active_s=active_s,
                        tokens=tokens,
                    )
                )
                if len(sessions) >= limit:
                    return sessions
        return sessions


def default_sources() -> list[LocalSource]:
    return [
        ClaudeCodeSource(),
        CodexSource(),
        GeminiSource(),
        AntigravitySource(),
        CursorSource(),
        CopilotSource(),
    ]


# ---------------------------------------------------------------------------
# Gestor
# ---------------------------------------------------------------------------


class LocalAgentDiscovery:
    """Sondea las fuentes locales y sincroniza sus agentes con el estado."""

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        audit: AuditLog,
        notify: Callable[[], None],
        sources: list[LocalSource] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.audit = audit
        self._notify = notify
        self.sources = list(sources) if sources is not None else default_sources()
        self._managed: dict[str, set[str]] = {
            source.key: set() for source in self.sources
        }
        self._failures: dict[str, int] = {
            source.key: 0 for source in self.sources
        }
        self._reported: dict[str, str | None] = {
            source.key: None for source in self.sources
        }
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="local-agent-discovery")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        poll = max(2.0, float(self.settings.local_agents_poll_s))
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # defensivo: una fuente no debe tumbar el bucle
                self.audit.add_event(
                    "discovery_error",
                    payload={
                        "source": "local",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
            await asyncio.sleep(poll)

    async def _poll(self) -> None:
        now_ms = int(time.time() * 1000)
        recency_ms = int(self.settings.local_agents_recency_s * 1000)
        limit = self.settings.local_agents_max_sessions
        active_s = self.settings.local_agents_active_s

        for source in self.sources:
            key = source.key
            try:
                sessions = await asyncio.to_thread(
                    source.scan,
                    now_ms=now_ms,
                    recency_ms=recency_ms,
                    limit=limit,
                    active_s=active_s,
                )
            except Exception as exc:
                self._failures[key] += 1
                error = f"{type(exc).__name__}: {exc}"
                if error != self._reported[key]:
                    self._reported[key] = error
                    self.audit.add_event(
                        "discovery_error",
                        payload={"source": source.provider, "error": error},
                    )
                if self._failures[key] >= OFFLINE_AFTER_FAILURES:
                    mark_offline(
                        self.store,
                        self._notify,
                        self._managed[key],
                        f"sin datos de {source.label}",
                    )
                continue

            if self._reported[key] is not None:
                self.audit.add_event(
                    "discovery_recovered", payload={"source": source.provider}
                )
                self._reported[key] = None
            self._failures[key] = 0
            self._managed[key] = sync_detected(
                self.store,
                self.audit,
                self._notify,
                self._managed[key],
                sessions,
                source.provider,
                source.label,
            )
