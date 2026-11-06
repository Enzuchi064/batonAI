"""Adaptador de OpenCode: permisos, prompts e interrupciones.

OpenCode expone permisos pendientes por sesión y acepta respuestas
``once``/``always``/``reject``. El panel usa dos opciones (permitir/denegar),
así que ``allow`` se traduce a ``once`` y ``deny`` a ``reject``.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

import httpx

from ..audit import AuditLog
from .base import AgentAdapter, Sink

Endpoint = Callable[[], tuple[str, dict[str, str]]]

_ACCEPT = {"allow", "yes", "approve", "accepted", "A"}


class OpenCodeClient:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        *,
        timeout: float = 6.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.timeout = timeout

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.request(
                    method,
                    self.base_url + path,
                    headers=self.headers,
                    json=body,
                )
        except httpx.HTTPError:
            return None

    async def reply_permission(
        self, session_id: str, request_id: str, decision: str
    ) -> bool:
        path = (
            f"/api/session/{quote(session_id, safe='')}"
            f"/permission/{quote(request_id, safe='')}/reply"
        )
        response = await self._request(
            "POST", path, {"decision": decision}
        )
        return response is not None and response.status_code in (200, 204)

    async def prompt(self, session_id: str, text: str) -> bool:
        path = f"/api/session/{quote(session_id, safe='')}/prompt"
        response = await self._request("POST", path, {"text": text})
        return response is not None and response.status_code in (200, 201)

    async def interrupt(self, session_id: str) -> bool:
        path = f"/api/session/{quote(session_id, safe='')}/interrupt"
        response = await self._request("POST", path)
        return response is not None and response.status_code in (200, 204)


class OpenCodeAdapter(AgentAdapter):
    provider = "opencode"

    def __init__(
        self,
        *,
        session_id: str,
        name: str,
        model: str,
        cwd: str,
        endpoint: Endpoint,
        audit: AuditLog | None = None,
    ) -> None:
        self.id = f"opencode:{session_id}"
        self.session_id = session_id
        self.name = name
        self.model = model
        self.cwd = cwd
        self._endpoint = endpoint
        self._audit = audit

    # -- ciclo de vida ----------------------------------------------------

    async def start(self, sink: Sink) -> None:
        # El descubrimiento ya mantiene el estado; el adaptador solo actúa
        # cuando el dispositivo responde o dicta.
        return None

    async def stop(self) -> None:
        return None

    # -- acciones ---------------------------------------------------------

    def _client(self) -> OpenCodeClient:
        base_url, headers = self._endpoint()
        return OpenCodeClient(base_url, headers)

    async def respond(self, approval_id: str, option_id: str) -> None:
        request_id = (
            approval_id[3:] if approval_id.startswith("oc_") else approval_id
        )
        decision = "once" if option_id in _ACCEPT else "reject"
        ok = await self._client().reply_permission(
            self.session_id, request_id, decision
        )
        if self._audit:
            self._audit.add_event(
                "opencode_permission_reply",
                agent_id=self.id,
                payload={
                    "request_id": request_id,
                    "decision": decision,
                    "ok": ok,
                },
            )

    async def notify_expired(self, approval_id: str) -> None:
        # No auto-aprobar ni denegar: el prompt nativo sigue esperando en el PC.
        return None

    async def send_text(self, text: str) -> bool:
        ok = await self._client().prompt(self.session_id, text)
        if self._audit:
            self._audit.add_event(
                "opencode_prompt_sent",
                agent_id=self.id,
                payload={"chars": len(text), "ok": ok},
            )
        return ok

    async def interrupt(self) -> bool:
        ok = await self._client().interrupt(self.session_id)
        if self._audit:
            self._audit.add_event(
                "opencode_interrupted",
                agent_id=self.id,
                payload={"ok": ok},
            )
        return ok
