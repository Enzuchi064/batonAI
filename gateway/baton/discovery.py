"""Descubrimiento de agentes locales: OpenCode.

OpenCode Desktop arranca un servidor HTTP en loopback (normalmente
``127.0.0.1:28894``) y expone sus sesiones en ``/api/session`` con Basic auth:
usuario ``opencode`` y la contraseña de ``~/.config/opencode/service.json``.

Este módulo no ejecuta nada sobre los agentes: solo refleja en el ``StateStore``
las sesiones recientes para que el panel y la app de control las vean. Las
aprobaciones reales llegarán con el adaptador de hooks (fase 0.5).

El puerto puede cambiar cuando OpenCode se reinicia, así que se descubre con
``psutil`` mirando los sockets en escucha del proceso ``opencode-cli``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

from .adapters.opencode import OpenCodeAdapter
from .audit import AuditLog
from .config import Settings
from .protocol import AgentStatus
from .risk import classify
from .state import InvalidTransition, StateStore

PROVIDER = "opencode"
DEFAULT_URL = "http://127.0.0.1:28894"
SERVICE_FILE = Path.home() / ".config" / "opencode" / "service.json"
OFFLINE_AFTER_FAILURES = 3


def agent_id_for(session_id: str, provider: str = PROVIDER) -> str:
    return f"{provider}:{session_id}"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def token_total(tokens: Any) -> int:
    """Suma los tokens facturables. La caché se omite a propósito."""
    if not isinstance(tokens, dict):
        return 0
    return sum(_int(tokens.get(key)) for key in ("input", "output", "reasoning"))


@dataclass(slots=True)
class DetectedSession:
    session_id: str
    name: str
    model: str
    cwd: str
    updated_ms: int
    busy_ms: int
    idle_ms: int
    cost: float
    tokens: int
    provider: str = PROVIDER
    forced_status: AgentStatus | None = None
    output: str = ""

    @property
    def agent_id(self) -> str:
        return agent_id_for(self.session_id, self.provider)

    @property
    def status(self) -> AgentStatus:
        if self.forced_status is not None:
            return self.forced_status
        # OpenCode marca el inicio del turno con ``busy`` y el final con
        # ``idle``. Si el último turno terminó, está en espera.
        return AgentStatus.RUNNING if self.busy_ms > self.idle_ms else AgentStatus.IDLE


def map_session(
    session: dict[str, Any], *, now_ms: int, recency_ms: int
) -> DetectedSession | None:
    """Convierte una sesión de OpenCode en un agente, o ``None`` si es vieja."""
    session_id = str(session.get("id") or "").strip()
    if not session_id:
        return None

    times = session.get("time")
    times = times if isinstance(times, dict) else {}
    updated = _int(times.get("updated"))
    if updated <= 0 or updated < now_ms - recency_ms:
        return None

    raw_model = session.get("model")
    if isinstance(raw_model, dict):
        model_id = str(raw_model.get("id") or "").strip()
    else:
        model_id = str(raw_model or "").strip()

    location = session.get("location")
    location = location if isinstance(location, dict) else {}

    title = str(session.get("title") or "").strip()
    name = title or f"OpenCode {session_id[-6:]}"

    return DetectedSession(
        session_id=session_id,
        name=name,
        model=model_id or "unknown",
        cwd=str(location.get("directory") or ""),
        updated_ms=updated,
        busy_ms=_int(times.get("busy")),
        idle_ms=_int(times.get("idle")),
        cost=_float(session.get("cost")),
        tokens=token_total(session.get("tokens")),
    )


def select_sessions(
    payload: Any, *, now_ms: int, recency_ms: int, limit: int
) -> list[DetectedSession]:
    """Normaliza la respuesta de ``/api/session`` y aplica recencia y tope."""
    if isinstance(payload, dict):
        items = payload.get("data") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    mapped: list[DetectedSession] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        session = map_session(item, now_ms=now_ms, recency_ms=recency_ms)
        if session is not None:
            mapped.append(session)

    mapped.sort(key=lambda session: session.updated_ms, reverse=True)
    if limit > 0:
        return mapped[:limit]
    return mapped


def opencode_ports() -> list[int]:
    """Puertos locales en escucha de procesos OpenCode, si ``psutil`` está."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - dependencia opcional
        return []

    ports: set[int] = set()
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "opencode" not in name and "opencode" not in cmdline:
            continue
        # Solo el servidor local, no la app Electron ni otros procesos con
        # "opencode" en el nombre: evita confundir un puerto cualquiera con la API.
        is_cli = "opencode-cli" in name or "opencode-cli" in cmdline
        is_server = " serve" in cmdline
        if not (is_cli or is_server):
            continue
        try:
            connections = proc.net_connections(kind="inet")
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
        for conn in connections:
            address = conn.laddr
            if conn.status != psutil.CONN_LISTEN or not address:
                continue
            if address.ip in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
                ports.add(int(address.port))
    return sorted(ports)


def _desktop_running() -> bool:
    """¿Está abierta la app de escritorio de OpenCode?

    Sus pestañas solo son válidas mientras la app vive. Si no está, el gateway
    prefiere no filtrar y usar la recencia de la API (modo CLI).
    """
    try:
        import psutil
    except ImportError:  # pragma: no cover - dependencia opcional
        return True

    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "opencode" not in name and "opencode" not in exe:
            continue
        if "cli" in name or "cli" in exe or "server" in name:
            continue
        if "opencode" in name or "ai.opencode.desktop" in exe:
            return True
    return False


def _desktop_state_files() -> list[Path]:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(
            Path(appdata) / "ai.opencode.desktop" / "drafts.sqlite"
        )
    candidates.append(
        Path.home() / ".config" / "ai.opencode.desktop" / "drafts.sqlite"
    )
    candidates.append(
        Path.home()
        / "Library"
        / "Application Support"
        / "ai.opencode.desktop"
        / "drafts.sqlite"
    )
    return candidates


def _tabs_from_db(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT value FROM state"
            " WHERE key = 'tabs' AND name LIKE 'opencode.window.%.dat'"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return None
    if not rows:
        return None

    ids: set[str] = set()
    for (value,) in rows:
        try:
            items = json.loads(value)
        except (TypeError, ValueError):
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "session":
                continue
            session_id = item.get("sessionId")
            if isinstance(session_id, str) and session_id:
                ids.add(session_id)
    return ids


def open_tab_session_ids() -> set[str] | None:
    """Ids de las pestañas de sesión abiertas en la app de OpenCode.

    ``drafts.sqlite`` guarda en ``state`` la clave ``tabs`` por ventana. Devolver
    ``None`` significa "no hay información": el llamador debe caer a la recencia.
    Un conjunto vacío significa "no hay pestañas abiertas".
    """
    if not _desktop_running():
        return None

    for path in _desktop_state_files():
        ids = _tabs_from_db(path)
        if ids is not None:
            return ids
    return None


def _short_output(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def sync_detected(
    store: StateStore,
    audit: AuditLog,
    notify: Callable[[], None],
    managed: set[str],
    sessions: list[DetectedSession],
    provider: str,
    label: str,
) -> set[str]:
    """Vuelca sesiones detectadas al estado y retira las que ya no están.

    Devuelve el nuevo conjunto de ids gestionados por esta fuente. Solo toca
    agentes con id propio: los adaptadores y otras fuentes quedan intactos.
    """
    seen: set[str] = set()
    changed = False

    for session in sessions:
        agent_id = session.agent_id
        seen.add(agent_id)

        previous = store.maybe_get(agent_id)
        first = previous is None
        previous_status = previous.status if previous is not None else None

        if previous is not None and (
            previous.name != session.name
            or previous.model != session.model
            or previous.cwd != session.cwd
        ):
            changed = True
        if previous is not None and (
            previous.cost_session != session.cost
            or previous.tokens_session != session.tokens
        ):
            changed = True

        agent = store.register(
            agent_id,
            session.name,
            provider,
            session.model,
            session.cwd,
        )

        target = session.status
        if first or (previous_status is not None and previous_status is not target):
            try:
                store.set_status(agent_id, target, task=f"Sesión de {label}")
            except InvalidTransition:
                pass
            else:
                changed = True
                if first:
                    store.log(agent_id, f"→ sesión detectada en {label}")
                elif target is AgentStatus.RUNNING:
                    store.log(agent_id, "→ trabajando")
                else:
                    store.log(agent_id, "✓ inactiva")

        if previous is None or (
            previous.cost_session != session.cost
            or previous.tokens_session != session.tokens
        ):
            store.set_usage(
                agent_id,
                cost_session=session.cost,
                tokens_session=session.tokens,
            )

        if session.output:
            task = _short_output(session.output, 160)
            if agent.task != task:
                store.set_task(agent_id, task)
                changed = True
            if not agent.logs or agent.logs[-1] != session.output:
                store.log(agent_id, session.output)
                changed = True

    for stale in managed - seen:
        if store.remove(stale):
            changed = True
            audit.add_event(
                "agent_removed",
                agent_id=stale,
                payload={"source": provider},
            )

    if changed:
        notify()
    return seen


def mark_offline(
    store: StateStore,
    notify: Callable[[], None],
    managed: set[str],
    reason: str,
) -> None:
    changed = False
    for agent_id in list(managed):
        agent = store.maybe_get(agent_id)
        if agent is None or agent.status is AgentStatus.OFFLINE:
            continue
        try:
            store.set_status(agent_id, AgentStatus.OFFLINE)
        except InvalidTransition:
            continue
        store.log(agent_id, f"✗ {reason}")
        changed = True
    if changed:
        notify()


OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _clean_output(value: object, limit: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _tool_output(block: dict) -> str:
    name = str(block.get("name") or "tool")
    state = block.get("state")
    state = state if isinstance(state, dict) else {}
    data = state.get("input")
    data = data if isinstance(data, dict) else {}
    detail = (
        data.get("command")
        or data.get("path")
        or data.get("pattern")
        or data.get("url")
        or data.get("code")
        or data.get("description")
        or ""
    )
    detail = _clean_output(detail, 100)
    return f"→ {name}" + (f": {detail}" if detail else "")


def _message_output(data: dict) -> tuple[str, str]:
    content = data.get("content")
    if not isinstance(content, list):
        return "", ""
    text = ""
    tool = ""
    for block in reversed(content):
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text" and not text:
            text = _clean_output(block.get("text"))
        elif kind == "tool" and not tool:
            tool = _tool_output(block)
    return text, tool


def opencode_output(session_id: str, db_path: Path | None = None) -> str:
    """Última salida visible del agente: texto o acción de herramienta.

    Prefiere el último texto del asistente (la respuesta legible) y, si no hay,
    la última acción de herramienta. Lee la base local de OpenCode con el índice
    por sesión y tipo, sin descargar páginas enteras de mensajes por HTTP.
    """
    path = db_path or OPENCODE_DB
    if not path.is_file():
        return ""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT data FROM session_message"
            " WHERE session_id = ? AND type = 'assistant'"
            " ORDER BY seq DESC LIMIT 6",
            (session_id,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return ""

    fallback = ""
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        text, tool = _message_output(data)
        if text:
            return text
        if tool and not fallback:
            fallback = tool
    return fallback


class OpenCodeDiscovery:
    """Sincroniza las sesiones recientes de OpenCode con el estado del gateway."""

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        audit: AuditLog,
        notify: Callable[[], None],
        *,
        register_adapter: Callable[[OpenCodeAdapter], None] | None = None,
        unregister_adapter: Callable[[str], None] | None = None,
        on_approval: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        record_usage: Callable[[str, int], None] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.audit = audit
        self._notify = notify
        self._register_adapter = register_adapter
        self._unregister_adapter = unregister_adapter
        self._on_approval = on_approval
        self._record_usage = record_usage
        self._managed: set[str] = set()
        self._registered: set[str] = set()
        self._seen_permissions: dict[str, set[str]] = {}
        self._task: asyncio.Task | None = None
        self._url: str | None = None
        self._failures = 0
        self._last_error: str | None = None
        self._reported_error: str | None = None

    # -- ciclo de vida ----------------------------------------------------

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="opencode-discovery")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        poll = max(1.0, float(self.settings.opencode_poll_s))
        async with httpx.AsyncClient(timeout=2.5) as client:
            while True:
                try:
                    await self._poll(client)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # un fallo del sondeo no debe matar el bucle
                    self._failures += 1
                    error = f"{type(exc).__name__}: {exc}"
                    if error != self._reported_error:
                        self._reported_error = error
                        self.audit.add_event(
                            "discovery_error",
                            payload={"source": PROVIDER, "error": error},
                        )
                await asyncio.sleep(poll)

    # -- sondeo -----------------------------------------------------------

    async def _poll(self, client: httpx.AsyncClient) -> None:
        sessions = await self._fetch(client)
        if sessions is None:
            self._failures += 1
            error = self._last_error or "unreachable"
            if error != self._reported_error:
                self._reported_error = error
                self.audit.add_event(
                    "discovery_error",
                    payload={"source": PROVIDER, "error": error},
                )
            if self._failures >= OFFLINE_AFTER_FAILURES:
                self._mark_offline()
            return

        if self._reported_error is not None:
            self.audit.add_event(
                "discovery_recovered", payload={"source": PROVIDER}
            )
            self._reported_error = None
        self._failures = 0
        self._sync(sessions)

    async def _fetch(
        self, client: httpx.AsyncClient
    ) -> list[DetectedSession] | None:
        error: str | None = None
        for base in self._candidate_urls():
            try:
                response = await client.get(
                    f"{base}/api/session", headers=self._headers()
                )
            except httpx.HTTPError as exc:
                error = type(exc).__name__
                continue
            if response.status_code == 401:
                error = "unauthorized"
                continue
            if response.status_code >= 400:
                error = f"http_{response.status_code}"
                continue
            try:
                payload = response.json()
            except ValueError:
                error = "invalid_json"
                continue

            self._url = base
            self._last_error = None
            now_ms = int(time.time() * 1000)
            tabs = open_tab_session_ids()
            if tabs is None:
                selected = select_sessions(
                    payload,
                    now_ms=now_ms,
                    recency_ms=int(self.settings.opencode_recency_s * 1000),
                    limit=self.settings.opencode_max_sessions,
                )
            else:
                # Con la app de escritorio abierta, la fuente de verdad son sus
                # pestañas: una sesión cerrada desaparece aunque siga en el
                # historial.
                sessions = select_sessions(
                    payload,
                    now_ms=now_ms,
                    recency_ms=365 * 24 * 3600 * 1000,
                    limit=0,
                )
                selected = [
                    session for session in sessions if session.session_id in tabs
                ][: self.settings.opencode_max_sessions]

            if selected:
                outputs = await asyncio.to_thread(
                    lambda: {
                        session.session_id: opencode_output(session.session_id)
                        for session in selected
                    }
                )
                for session in selected:
                    session.output = outputs.get(session.session_id, "")

            if self._on_approval is not None:
                for session in selected:
                    await self._poll_permissions(client, base, session)
            return selected

        self._last_error = error or "unreachable"
        self._url = None
        return None

    def _candidate_urls(self) -> list[str]:
        if self.settings.opencode_url:
            url = self.settings.opencode_url.rstrip("/")
            return [url] if not self._url or self._url == url else [self._url, url]
        if self._url:
            return [self._url]

        urls = [f"http://127.0.0.1:{port}" for port in opencode_ports()]
        if DEFAULT_URL not in urls:
            urls.append(DEFAULT_URL)
        return urls

    def _headers(self) -> dict[str, str]:
        password = self._password()
        if not password:
            return {}
        raw = f"opencode:{password}".encode("utf-8")
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}

    def _password(self) -> str:
        if self.settings.opencode_password:
            return self.settings.opencode_password
        try:
            data = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        value = data.get("password")
        return value if isinstance(value, str) else ""

    # -- sincronización ---------------------------------------------------

    def _endpoint(self) -> tuple[str, dict[str, str]]:
        return (self._url or DEFAULT_URL, self._headers())

    def _sync(self, sessions: list[DetectedSession]) -> None:
        self._managed = sync_detected(
            self.store,
            self.audit,
            self._notify,
            self._managed,
            sessions,
            PROVIDER,
            "OpenCode",
        )
        if self._record_usage is not None:
            for session in sessions:
                self._record_usage(session.agent_id, session.tokens)

        if self._register_adapter is not None:
            for session in sessions:
                if session.agent_id in self._registered:
                    continue
                adapter = OpenCodeAdapter(
                    session_id=session.session_id,
                    name=session.name,
                    model=session.model,
                    cwd=session.cwd,
                    endpoint=self._endpoint,
                    audit=self.audit,
                )
                self._register_adapter(adapter)
                self._registered.add(session.agent_id)

        if self._unregister_adapter is not None:
            for agent_id in self._registered - self._managed:
                self._unregister_adapter(agent_id)
            self._registered &= self._managed

    def _approval_payload(
        self, request: dict[str, Any], session: DetectedSession
    ) -> dict[str, Any]:
        action = str(request.get("action") or "tool")
        resources = [
            str(item)
            for item in (request.get("resources") or [])
            if isinstance(item, str) and item
        ]
        command = "\n".join(resources) or str(request.get("message") or action)
        title = _short_output(str(request.get("message") or ""), 120)
        if not title:
            title = f"Permiso para {action}"
        assessment = classify(command, action)
        return {
            "approval_id": f"oc_{request.get('id')}",
            "kind": action,
            "title": title,
            "command": command,
            "cwd": session.cwd,
            "risk": assessment.risk.value,
            "reasons": assessment.reasons,
            "details": assessment.details,
        }

    async def _poll_permissions(
        self,
        client: httpx.AsyncClient,
        base: str,
        session: DetectedSession,
    ) -> None:
        if self._on_approval is None:
            return
        path = (
            f"{base}/api/session/{quote(session.session_id, safe='')}"
            "/permission"
        )
        try:
            response = await client.get(path, headers=self._headers())
        except httpx.HTTPError:
            return
        if response.status_code >= 400:
            return
        try:
            payload = response.json()
        except ValueError:
            return

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return
        pending = {
            str(item.get("id"))
            for item in items
            if isinstance(item, dict) and item.get("id")
        }
        seen = self._seen_permissions.setdefault(session.session_id, set())
        seen.intersection_update(pending)
        if not items:
            self._seen_permissions.pop(session.session_id, None)
            return

        # Solo la primera petición pendiente: el broker invalida la anterior
        # del mismo agente, así que no conviene adelantar la siguiente.
        first = items[0]
        if not isinstance(first, dict):
            return
        request_id = str(first.get("id") or "")
        if not request_id or request_id in seen:
            return
        seen.add(request_id)
        await self._on_approval(
            session.agent_id, self._approval_payload(first, session)
        )

    def _mark_offline(self) -> None:
        mark_offline(
            self.store,
            self._notify,
            self._managed,
            "sin conexión con OpenCode",
        )
