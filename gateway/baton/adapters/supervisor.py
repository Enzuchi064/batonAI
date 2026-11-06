"""Orquestación entre adaptadores, estado, broker y dispositivos.

El supervisor es el único que escribe en el ``StateStore``. Los adaptadores
solo emiten hechos; aquí se validan, se persisten y se publican.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..audit import AuditLog
from ..broker import Approval, ApprovalBroker, Resolution
from ..config import Settings
from ..hub import DeviceConnection, DeviceHub
from ..protocol import (
    AgentStatus,
    ApprovalResultMessage,
    ErrorMessage,
    PongMessage,
    Risk,
    dump,
)
from ..state import InvalidTransition, StateStore
from ..usage import UsageTracker
from .base import AgentAdapter, AgentEvent, EventKind


class AgentSupervisor:
    def __init__(
        self,
        store: StateStore,
        broker: ApprovalBroker,
        hub: DeviceHub,
        audit: AuditLog,
        settings: Settings,
        usage: UsageTracker | None = None,
    ) -> None:
        self.store = store
        self.broker = broker
        self.hub = hub
        self.audit = audit
        self.settings = settings
        self.usage = usage
        self._adapters: dict[str, AgentAdapter] = {}
        self._dirty = False
        self._flush_task: asyncio.Task | None = None
        self._expiry_task: asyncio.Task | None = None
        self._broadcasting = asyncio.Lock()

    # -- registro ---------------------------------------------------------

    def register(self, adapter: AgentAdapter) -> None:
        self._adapters[adapter.id] = adapter
        self.store.register(
            adapter.id,
            adapter.name,
            adapter.provider,
            adapter.model,
            adapter.cwd,
        )

    def adapter(self, agent_id: str) -> AgentAdapter | None:
        return self._adapters.get(agent_id)

    def unregister(self, agent_id: str) -> None:
        """Retira un adaptador dinámico (por ejemplo, una pestaña cerrada)."""
        self._adapters.pop(agent_id, None)

    async def raise_approval(
        self, agent_id: str, payload: dict[str, Any]
    ) -> None:
        """Permite a un descubridor externo publicar una aprobación."""
        await self._sink(AgentEvent(EventKind.APPROVAL, agent_id, payload))

    @property
    def adapters(self) -> list[AgentAdapter]:
        return list(self._adapters.values())

    # -- ciclo de vida ----------------------------------------------------

    async def start(self) -> None:
        for adapter in self._adapters.values():
            await adapter.start(self._sink)
        self._flush_task = asyncio.create_task(self._flush_loop(), name="state-flush")
        self._expiry_task = asyncio.create_task(self._expiry_loop(), name="approval-expiry")

    async def stop(self) -> None:
        for task in (self._flush_task, self._expiry_task):
            if task and not task.done():
                task.cancel()
        for adapter in self._adapters.values():
            await adapter.stop()

    # -- entrada desde adaptadores ---------------------------------------

    async def _sink(self, event: AgentEvent) -> None:
        try:
            await self._apply(event)
        except InvalidTransition as exc:
            self.audit.add_event(
                "invalid_transition",
                agent_id=event.agent_id,
                payload={"error": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - defensivo
            self.audit.add_event(
                "sink_error",
                agent_id=event.agent_id,
                payload={"error": f"{type(exc).__name__}: {exc}"},
            )

    async def _apply(self, event: AgentEvent) -> None:
        agent_id = event.agent_id
        payload = event.payload

        if event.kind is EventKind.STATUS:
            status = AgentStatus(payload["status"])
            previous = self.store.get(agent_id).status
            self.store.set_status(agent_id, status, task=payload.get("task"))
            if previous is AgentStatus.WAITING_INPUT and status is not AgentStatus.WAITING_INPUT:
                for stale in self.broker.supersede(agent_id):
                    await self._publish_result(stale)
            self._schedule_broadcast()

        elif event.kind is EventKind.LOG:
            self.store.log(agent_id, str(payload.get("line", "")))
            self._schedule_broadcast()

        elif event.kind is EventKind.USAGE:
            self.store.set_usage(
                agent_id,
                cost_turn=payload.get("cost_turn"),
                cost_session=payload.get("cost_session"),
                tokens_session=payload.get("tokens_session"),
            )
            if self.usage is not None and payload.get("tokens_session") is not None:
                self.usage.record(agent_id, payload.get("tokens_session"))
            self._schedule_broadcast()

        elif event.kind is EventKind.APPROVAL:
            if self.store.get(agent_id).status is not AgentStatus.WAITING_INPUT:
                try:
                    self.store.set_status(
                        agent_id,
                        AgentStatus.WAITING_INPUT,
                        task=payload.get("title", ""),
                    )
                except InvalidTransition:
                    pass
            approval = self.broker.create(
                approval_id=payload["approval_id"],
                agent_id=agent_id,
                kind=payload.get("kind", "bash"),
                title=payload.get("title", "Permiso requerido"),
                command=payload.get("command", ""),
                cwd=payload.get("cwd", self.store.get(agent_id).cwd),
                risk=Risk(payload.get("risk", Risk.NORMAL.value)),
                reasons=payload.get("reasons"),
                details=payload.get("details"),
            )
            self.store.attach_approval(
                agent_id,
                approval.approval_id,
                approval.command,
                approval.risk,
                approval.reasons,
                approval.details,
            )
            self.audit.add_event(
                "approval_created",
                agent_id=agent_id,
                approval_id=approval.approval_id,
                payload={"command": approval.command, "risk": approval.risk.value},
            )
            await self.hub.broadcast(dump(approval.to_message()))
            self._schedule_broadcast()

        elif event.kind is EventKind.ERROR:
            self.store.log(agent_id, f"✗ {payload.get('message', 'error')}")
            self.store.set_status(agent_id, AgentStatus.ERROR)
            self.audit.add_event(
                "agent_error", agent_id=agent_id, payload=payload
            )
            self._schedule_broadcast()

    # -- entrada desde dispositivos --------------------------------------

    async def resolve(
        self,
        approval_id: str,
        option_id: str,
        *,
        source: str = "button",
        device_id: str | None = None,
    ) -> Resolution:
        approval = self.broker.get(approval_id)
        result = self.broker.resolve(
            approval_id, option_id, source=source, device_id=device_id
        )
        if approval is None or result.duplicate or result.status in {"unknown", "invalid_option"}:
            return result
        await self._after_resolution(approval, result.status)
        return result

    async def _after_resolution(self, approval: Approval, status: str) -> None:
        adapter = self._adapters.get(approval.agent_id)
        agent_id = approval.agent_id

        if status == "accepted":
            self.store.clear_approval(agent_id, AgentStatus.RUNNING)
        elif status in {"rejected", "expired"}:
            self.store.clear_approval(agent_id, AgentStatus.IDLE)
        else:  # stale
            self.store.clear_approval(agent_id)

        if adapter is not None:
            if status == "expired":
                await adapter.notify_expired(approval.approval_id)
            elif status in {"accepted", "rejected"}:
                await adapter.respond(approval.approval_id, approval.option_id or "deny")

        self.audit.add_event(
            "approval_resolved",
            agent_id=agent_id,
            approval_id=approval.approval_id,
            device_id=approval.device_id,
            payload={"status": status, "option_id": approval.option_id},
        )
        await self._publish_result(approval)
        self._schedule_broadcast(immediate=True)

    async def interrupt(self, agent_id: str) -> bool:
        adapter = self._adapters.get(agent_id)
        if adapter is None:
            return False
        result = await adapter.interrupt()
        self.audit.add_event("agent_interrupted", agent_id=agent_id)
        return result is not False

    async def send_text(self, agent_id: str, text: str) -> bool:
        adapter = self._adapters.get(agent_id)
        if adapter is None:
            return False
        result = await adapter.send_text(text)
        self.audit.add_event(
            "text_injected", agent_id=agent_id, payload={"chars": len(text)}
        )
        return result is not False

    # -- publicación ------------------------------------------------------

    def request_broadcast(self) -> None:
        """Hook público para fuentes externas (descubrimiento de agentes)."""
        self._schedule_broadcast()

    def _schedule_broadcast(self, immediate: bool = False) -> None:
        self._dirty = True

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(0.08)
            if not self._dirty:
                continue
            async with self._broadcasting:
                self._dirty = False
                await self.hub.broadcast(dump(self.store.snapshot()))

    async def publish_state(self, connection: DeviceConnection | None = None) -> None:
        message = dump(self.store.snapshot())
        if connection is None:
            await self.hub.broadcast(message)
        else:
            await self.hub.send(connection, message)

    async def _publish_result(self, approval: Approval) -> None:
        await self.hub.broadcast(
            dump(
                ApprovalResultMessage(
                    approval_id=approval.approval_id,
                    status=approval.status.value,
                    accepted=approval.status.value == "accepted",
                    option_id=approval.option_id,
                    reason=approval.status.value,
                )
            )
        )

    async def _expiry_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            for approval in self.broker.expire_due():
                self.store.clear_approval(approval.agent_id)
                await self._after_resolution(approval, "expired")

    # -- utilidades -------------------------------------------------------

    async def handle_ping(self, connection: DeviceConnection, seq: int) -> None:
        await self.hub.send(connection, dump(PongMessage(seq=seq)))

    async def handle_error(
        self, connection: DeviceConnection, code: str, message: str
    ) -> None:
        await self.hub.send(
            connection, dump(ErrorMessage(code=code, message=message))
        )

    def status_summary(self) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        return dump(snapshot)
