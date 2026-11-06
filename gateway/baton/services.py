"""Ensamblaje de servicios y manejo de mensajes del dispositivo."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from .adapters.base import AgentAdapter
from .adapters.fake import FakeAgentAdapter
from .adapters.supervisor import AgentSupervisor
from .audit import AuditLog
from .broker import ApprovalBroker
from .claude_usage import ClaudeLimitsSource
from .codex_usage import CodexLimitsSource, find_codex_executable
from .config import Settings
from .lan_discovery import DiscoveryResponder
from .limits import LimitsService
from .opencode_usage import OpenCodeLimitsSource
from .discovery import OpenCodeDiscovery
from .hub import DeviceConnection, DeviceHub
from .local_agents import LocalAgentDiscovery
from .pairing import PairingManager
from .usage import UsageTracker
from .virtual_device import VirtualDevice
from .protocol import (
    AckMessage,
    ApprovalResponse,
    ApprovalResultMessage,
    AudioEnd,
    AudioStart,
    ErrorMessage,
    InjectText,
    InterruptRequest,
    Ping,
    PinnedMessage,
    VisibilityMessage,
    dump,
)
from .state import StateStore
from .util import iso

MAX_PINNED = 2


class PinLimit(Exception):
    """No se pueden fijar más de dos agentes a la vez."""

# Tres agentes de demostración con perfiles distintos: la rejilla del dashboard
# necesita más de uno para que el encoder tenga algo que recorrer.
FAKE_AGENTS: list[dict] = [
    {
        "agent_id": "claude-code",
        "name": "Auth refactor",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "cwd": r"C:\dev\baton-demo",
        "idle_delay": 8.0,
        "task_offset": 0,
    },
    {
        "agent_id": "codex",
        "name": "API parser",
        "provider": "openai",
        "model": "gpt-5-codex",
        "cwd": r"C:\dev\baton-api",
        "idle_delay": 11.0,
        "task_offset": 1,
    },
    {
        "agent_id": "antigravity",
        "name": "Landing page",
        "provider": "antigravity",
        "model": "gemini-3-pro",
        "cwd": r"C:\dev\baton-web",
        "idle_delay": 15.0,
        "task_offset": 2,
    },
]


@dataclass
class Services:
    settings: Settings
    audit: AuditLog
    store: StateStore
    broker: ApprovalBroker
    pairing: PairingManager
    hub: DeviceHub
    supervisor: AgentSupervisor
    discovery: OpenCodeDiscovery | None = None
    local_discovery: LocalAgentDiscovery | None = None
    virtual_device: VirtualDevice | None = None
    provider_budgets: dict[str, int] = field(default_factory=dict)
    usage: UsageTracker | None = None
    ticker_period: str = "all"
    ticker_providers: list[str] | None = None
    ticker_windows: list[str] | None = None
    limits_view: str = "remaining"
    limits: LimitsService | None = None
    remote_token: str = ""
    lan_discovery: DiscoveryResponder | None = None
    started_at: float = field(default_factory=time.monotonic)

    # -- construcción -----------------------------------------------------

    @classmethod
    def build(
        cls, settings: Settings | None = None, *, fake: bool | None = None
    ) -> "Services":
        settings = settings or Settings.from_env()
        settings.ensure_dirs()

        audit = AuditLog(settings.db_path)
        usage = UsageTracker(audit)
        remote_token = audit.get_setting("remote_token") or ""
        if not remote_token:
            remote_token = secrets.token_urlsafe(24)
            audit.set_setting("remote_token", remote_token)
        ticker_period = audit.get_setting("ticker_period", "all") or "all"
        if ticker_period == "daily":
            ticker_period = "rolling"
        if ticker_period not in {"rolling", "weekly", "monthly", "all"}:
            ticker_period = "all"
        ticker_providers: list[str] | None = None
        saved_providers = audit.get_setting("ticker_providers")
        if saved_providers:
            try:
                data = json.loads(saved_providers)
                if isinstance(data, list):
                    ticker_providers = [
                        str(item).strip()
                        for item in data
                        if str(item).strip()
                    ]
            except (ValueError, TypeError):
                ticker_providers = None
        ticker_windows: list[str] | None = None
        saved_windows = audit.get_setting("ticker_windows")
        if saved_windows:
            try:
                data = json.loads(saved_windows)
                if isinstance(data, list):
                    ticker_windows = [
                        str(item).strip()
                        for item in data
                        if str(item).strip()
                    ]
            except (ValueError, TypeError):
                ticker_windows = None
        saved_view = audit.get_setting("limits_view")
        limits_view = saved_view or settings.limits_view
        if limits_view not in {"remaining", "used"}:
            limits_view = "remaining"
        saved_rest = audit.get_setting("rest_after_s")
        if saved_rest is not None:
            try:
                settings.rest_after_s = max(0, min(int(saved_rest), 3600))
            except ValueError:
                pass
        provider_budgets: dict[str, int] = {}
        saved_budgets = audit.get_setting("provider_budgets")
        if saved_budgets:
            try:
                data = json.loads(saved_budgets)
                if isinstance(data, dict):
                    provider_budgets = {
                        str(key): max(0, int(value))
                        for key, value in data.items()
                        if str(key).strip()
                    }
            except (ValueError, TypeError):
                provider_budgets = {}
        store = StateStore(log_buffer=settings.log_buffer, log_tail=settings.log_tail)
        broker = ApprovalBroker(audit, timeout_s=settings.approval_timeout_s)
        pairing = PairingManager(audit)
        hub = DeviceHub()
        supervisor = AgentSupervisor(
            store, broker, hub, audit, settings, usage=usage
        )

        use_fake = settings.fake_autostart if fake is None else fake
        if use_fake:
            count = max(1, min(settings.fake_agents, len(FAKE_AGENTS)))
            for config in FAKE_AGENTS[:count]:
                supervisor.register(
                    FakeAgentAdapter(auto_approvals=settings.fake_approvals, **config)
                )

        discovery = (
            OpenCodeDiscovery(
                settings,
                store,
                audit,
                supervisor.request_broadcast,
                register_adapter=supervisor.register,
                unregister_adapter=supervisor.unregister,
                on_approval=supervisor.raise_approval,
                record_usage=usage.record,
            )
            if settings.opencode_enabled
            else None
        )
        local_discovery = (
            LocalAgentDiscovery(
                settings, store, audit, supervisor.request_broadcast
            )
            if settings.local_agents_enabled
            else None
        )

        virtual_device = (
            VirtualDevice.create(
                audit,
                pairing,
                settings.db_path.parent / "virtual_device.json",
            )
            if settings.dev_mode
            else None
        )

        sources = []
        if settings.opencode_limits_enabled:
            sources.append(
                OpenCodeLimitsSource(settings, poll_s=settings.limits_poll_s)
            )
        if settings.codex_usage_enabled:
            sources.append(
                CodexLimitsSource(
                    find_codex_executable(),
                    poll_s=settings.codex_usage_poll_s,
                )
            )
        if settings.claude_limits_enabled:
            sources.append(
                ClaudeLimitsSource(poll_s=max(60.0, settings.limits_poll_s))
            )
        limits = LimitsService(sources) if settings.limits_enabled else None
        if limits is not None:
            known = set(limits.provider_ids())
            if ticker_providers is not None:
                ticker_providers = [
                    item for item in ticker_providers if item in known
                ]
            if ticker_windows is not None:
                ticker_windows = [
                    item
                    for item in ticker_windows
                    if item.split(":", 1)[0] in known
                ]

        lan_discovery = (
            DiscoveryResponder(
                settings.port,
                virtual_device.device_id if virtual_device else "",
            )
            if settings.host in {"0.0.0.0", "::"}
            else None
        )

        return cls(
            settings=settings,
            audit=audit,
            store=store,
            broker=broker,
            pairing=pairing,
            hub=hub,
            supervisor=supervisor,
            discovery=discovery,
            local_discovery=local_discovery,
            virtual_device=virtual_device,
            provider_budgets=provider_budgets,
            usage=usage,
            ticker_period=ticker_period,
            ticker_providers=ticker_providers,
            ticker_windows=ticker_windows,
            limits_view=limits_view,
            limits=limits,
            remote_token=remote_token,
            lan_discovery=lan_discovery,
        )

    async def start(self) -> None:
        await self.supervisor.start()
        if self.discovery is not None:
            await self.discovery.start()
        if self.local_discovery is not None:
            await self.local_discovery.start()
        if self.lan_discovery is not None:
            self.lan_discovery.start()

    async def stop(self) -> None:
        if self.lan_discovery is not None:
            self.lan_discovery.stop()
        if self.local_discovery is not None:
            await self.local_discovery.stop()
        if self.discovery is not None:
            await self.discovery.stop()
        await self.supervisor.stop()
        await self.hub.close_all()
        self.audit.close()

    # -- mensajes del dispositivo ----------------------------------------

    async def handle_client_message(
        self, connection: DeviceConnection, message: Any
    ) -> None:
        if isinstance(message, ApprovalResponse):
            result = await self.supervisor.resolve(
                message.approval_id,
                message.option_id,
                source=message.source,
                device_id=connection.device_id,
            )
            ok = result.status not in {"unknown", "invalid_option"}
            if result.duplicate:
                # Idempotencia explícita: el dispositivo recibe el mismo
                # resultado que la primera vez, marcado como duplicado.
                await self.hub.send(
                    connection,
                    dump(
                        ApprovalResultMessage(
                            approval_id=result.approval_id,
                            status=result.status,
                            accepted=result.accepted,
                            option_id=result.option_id,
                            reason=result.reason,
                            duplicate=True,
                        )
                    ),
                )
            await self.hub.send(
                connection,
                dump(AckMessage(ref="approval_response", ok=ok, detail=result.reason)),
            )
            if not ok:
                await self.hub.send(
                    connection,
                    dump(
                        ErrorMessage(
                            code=result.status,
                            message=result.reason,
                            retryable=result.status == "unknown",
                        )
                    ),
                )

        elif isinstance(message, InterruptRequest):
            ok = await self.supervisor.interrupt(message.agent_id)
            await self.hub.send(
                connection,
                dump(
                    AckMessage(
                        ref="interrupt",
                        ok=ok,
                        detail="" if ok else "agente desconocido",
                    )
                ),
            )

        elif isinstance(message, InjectText):
            if not message.confirm:
                await self.hub.send(
                    connection,
                    dump(
                        ErrorMessage(
                            code="confirmation_required",
                            message="el texto debe confirmarse antes de inyectarse",
                        )
                    ),
                )
                return
            ok = await self.supervisor.send_text(message.agent_id, message.text)
            await self.hub.send(
                connection,
                dump(
                    AckMessage(
                        ref="inject_text",
                        ok=ok,
                        detail="" if ok else "agente desconocido",
                    )
                ),
            )

        elif isinstance(message, Ping):
            await self.supervisor.handle_ping(connection, message.seq)

        elif isinstance(message, (AudioStart, AudioEnd)):
            await self.hub.send(
                connection,
                dump(
                    ErrorMessage(
                        code="wrong_socket",
                        message="el audio va por /ws/audio",
                    )
                ),
            )

    # -- acciones de desarrollo ------------------------------------------

    def fake_adapter(self) -> AgentAdapter | None:
        return self.supervisor.adapter("claude-code")

    def force_approval(self, risk: str = "normal") -> bool:
        adapter = self.fake_adapter()
        trigger = getattr(adapter, "force_approval", None)
        if trigger is None:
            return False
        return bool(trigger(risk))

    def snapshot(self) -> dict[str, Any]:
        return dump(self.store.snapshot())

    # -- visibilidad ------------------------------------------------------

    def hidden_agents(self) -> list[str]:
        return self.audit.hidden_agents()

    async def set_visibility(self, agent_id: str, hidden: bool) -> list[str] | None:
        if self.store.maybe_get(agent_id) is None:
            return None

        hidden_agents = self.audit.set_hidden(agent_id, hidden)
        self.audit.add_event(
            "visibility_changed",
            agent_id=agent_id,
            payload={"hidden": bool(hidden), "hidden_agents": hidden_agents},
        )
        await self.hub.broadcast(
            dump(VisibilityMessage(hidden_agents=hidden_agents, ts=iso()))
        )
        return hidden_agents

    # -- fijados ----------------------------------------------------------

    def pinned_agents(self) -> list[str]:
        # Se conservan aunque la sesión desaparezca: si vuelve, sigue fijada.
        return self.audit.pinned_agents()

    async def set_pinned(self, agent_id: str, pinned: bool) -> list[str] | None:
        if self.store.maybe_get(agent_id) is None:
            return None

        current = [
            pinned_id
            for pinned_id in self.pinned_agents()
            if self.store.maybe_get(pinned_id) is not None
        ]
        if pinned and agent_id not in current and len(current) >= MAX_PINNED:
            raise PinLimit()

        self.audit.set_pinned(agent_id, pinned)
        pinned_agents = self.pinned_agents()
        self.audit.add_event(
            "pin_changed",
            agent_id=agent_id,
            payload={"pinned": bool(pinned), "pinned_agents": pinned_agents},
        )
        await self.hub.broadcast(
            dump(PinnedMessage(pinned_agents=pinned_agents, ts=iso()))
        )
        return pinned_agents
