"""API HTTP + WebSocket del gateway.

Superficie:

* ``/`` y ``/static/*``          — panel web (simulador de dispositivo).
* ``/ws/control``                — estado y aprobaciones (JSON).
* ``/ws/audio``                  — PCM 16 kHz mono (binario) + ciclo de vida.
* ``/api/pair``                  — emparejamiento con código de 6 dígitos.
* ``/api/dev/*``, ``/api/audit`` — administración, solo desde loopback.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .config import Settings
from .hub import DeviceConnection
from .pairing import PairingError
from .protocol import (
    AckMessage,
    ApprovalResponse,
    AudioEnd,
    AudioStart,
    ErrorMessage,
    Hello,
    InterruptRequest,
    PROTO_VERSION,
    PongMessage,
    Welcome,
    dump,
    parse_client_message,
)
from .services import MAX_PINNED, PinLimit, Services
from .virtual_device import VirtualPairingError

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    device_name: str = Field(default="dispositivo", max_length=64)


class ForceApprovalRequest(BaseModel):
    risk: Literal["low", "normal", "high", "critical"] = "normal"


class VisibilityUpdate(BaseModel):
    hidden: bool


class PinnedUpdate(BaseModel):
    pinned: bool


class VirtualPairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    pc_name: str = Field(default="DESKTOP", max_length=64)


class VirtualConfirmRequest(BaseModel):
    pair_id: str = Field(min_length=4, max_length=128)


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RestConfigUpdate(BaseModel):
    rest_after_s: int = Field(ge=0, le=3600)


class ProviderBudgetsUpdate(BaseModel):
    budgets: dict[str, int] = Field(default_factory=dict)


class LimitsPeriodUpdate(BaseModel):
    period: Literal["rolling", "weekly", "monthly", "all"] | None = None
    providers: list[str] | None = None
    windows: list[str] | None = None
    view: Literal["remaining", "used"] | None = None


class AgentLimitsUpdate(BaseModel):
    daily: int = Field(ge=0, le=10**12)
    weekly: int = Field(ge=0, le=10**12)
    monthly: int = Field(ge=0, le=10**12)


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="admin_only")


def _require_control(request: Request) -> None:
    """Loopback siempre; LAN solo con el token de control."""
    host = request.client.host if request.client else ""
    if host in LOCAL_HOSTS:
        return
    services = getattr(request.app.state, "services", None)
    token = getattr(services, "remote_token", "") if services else ""
    header = request.headers.get("authorization", "")
    if (
        token
        and header.startswith("Bearer ")
        and secrets.compare_digest(header[7:], token)
    ):
        return
    raise HTTPException(status_code=403, detail="control_token_required")


def create_app(
    settings: Settings | None = None, *, fake: bool | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    services = Services.build(settings, fake=fake)
    session_id = secrets.token_hex(8)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await services.start()
        try:
            yield
        finally:
            await services.stop()

    app = FastAPI(
        title="batonAI gateway",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.services = services
    app.state.session_id = session_id

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # -- panel ------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def panel() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        snapshot = services.store.snapshot()
        return {
            "ok": True,
            "version": __version__,
            "proto": PROTO_VERSION,
            "hostname": socket.gethostname(),
            "agents": len(snapshot.agents),
            "waiting": snapshot.system.waiting_agents,
            "devices_connected": len(services.hub.connections),
        }

    # -- emparejamiento ---------------------------------------------------

    @app.post("/api/pair")
    async def pair(body: PairRequest) -> dict[str, str]:
        try:
            return services.pairing.pair(body.code, body.device_name)
        except PairingError as exc:
            raise HTTPException(status_code=401, detail=exc.code) from exc

    # -- administración local ---------------------------------------------

    @app.get("/api/dev/bootstrap", dependencies=[Depends(_require_loopback)])
    async def bootstrap(device_id: str | None = None) -> dict[str, Any]:
        if not settings.dev_mode:
            raise HTTPException(status_code=404, detail="dev_mode_disabled")
        issued = services.pairing.bootstrap(device_id)
        return {
            **issued,
            "pairing_code": services.pairing.code,
            "state": services.snapshot(),
        }

    @app.get("/api/dev/pairing", dependencies=[Depends(_require_loopback)])
    async def pairing_code() -> dict[str, str]:
        if not settings.dev_mode:
            raise HTTPException(status_code=404, detail="dev_mode_disabled")
        return {"code": services.pairing.code}

    @app.get("/api/state", dependencies=[Depends(_require_control)])
    async def state() -> dict[str, Any]:
        return services.snapshot()

    @app.get("/api/info", dependencies=[Depends(_require_control)])
    async def info() -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        if services.discovery is not None:
            sources.append(
                {"id": "opencode", "label": "OpenCode", "enabled": True}
            )
        if services.local_discovery is not None:
            for source in services.local_discovery.sources:
                sources.append(
                    {
                        "id": source.provider,
                        "label": source.label,
                        "enabled": True,
                    }
                )
        return {
            "version": __version__,
            "proto": PROTO_VERSION,
            "opencode_enabled": settings.opencode_enabled,
            "local_agents_enabled": settings.local_agents_enabled,
            "max_pinned": MAX_PINNED,
            "rest_after_s": settings.rest_after_s,
            "provider_budgets": services.provider_budgets,
            "ticker_period": services.ticker_period,
            "ticker_providers": services.ticker_providers,
            "ticker_windows": services.ticker_windows,
            "limits_view": services.limits_view,
            "approval_timeout_s": settings.approval_timeout_s,
            "heartbeat_s": settings.heartbeat_s,
            "fake_autostart": settings.fake_autostart,
            "dev_mode": settings.dev_mode,
            "opencode_recency_s": settings.opencode_recency_s,
            "opencode_max_sessions": settings.opencode_max_sessions,
            "opencode_poll_s": settings.opencode_poll_s,
            "local_agents_recency_s": settings.local_agents_recency_s,
            "local_agents_max_sessions": settings.local_agents_max_sessions,
            "local_agents_poll_s": settings.local_agents_poll_s,
            "local_agents_active_s": settings.local_agents_active_s,
            "agents": len(services.store.agents),
            "connected_devices": len(services.hub.connections),
            "hidden_agents": services.hidden_agents(),
            "pinned_agents": services.pinned_agents(),
            "sources": sources,
        }

    @app.get("/api/config/remote", dependencies=[Depends(_require_loopback)])
    async def remote_control_config() -> dict[str, Any]:
        urls: list[dict[str, str]] = []
        try:
            import psutil

            for name, addresses in psutil.net_if_addrs().items():
                for address in addresses:
                    if address.family != socket.AF_INET:
                        continue
                    if address.address.startswith(("127.", "169.254.")):
                        continue
                    url = f"http://{address.address}:{settings.port}"
                    if not any(item["url"] == url for item in urls):
                        urls.append({"interface": name, "url": url})
        except Exception:
            pass

        primary = None
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            primary = f"http://{probe.getsockname()[0]}:{settings.port}"
            probe.close()
        except OSError:
            primary = None
        if primary and not any(item["url"] == primary for item in urls):
            urls.insert(0, {"interface": "principal", "url": primary})

        return {
            "ok": True,
            "token": services.remote_token,
            "url": primary,
            "urls": urls,
            "lan": settings.host in {"0.0.0.0", "::"},
            "host": settings.host,
            "port": settings.port,
        }

    @app.post("/api/agents/{agent_id}/interrupt", dependencies=[Depends(_require_control)])
    async def interrupt_agent(agent_id: str) -> dict[str, Any]:
        if services.store.maybe_get(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        ok = await services.supervisor.interrupt(agent_id)
        if not ok:
            raise HTTPException(status_code=409, detail="agent_unsupported")
        return {"ok": True, "agent_id": agent_id}

    @app.post("/api/agents/{agent_id}/message", dependencies=[Depends(_require_control)])
    async def message_agent(agent_id: str, body: AgentMessageRequest) -> dict[str, Any]:
        if services.store.maybe_get(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="empty_text")
        ok = await services.supervisor.send_text(agent_id, text)
        if not ok:
            raise HTTPException(status_code=409, detail="agent_unsupported")
        return {"ok": True, "agent_id": agent_id, "chars": len(text)}

    @app.get("/api/config/visibility", dependencies=[Depends(_require_control)])
    async def get_visibility() -> dict[str, Any]:
        return {"hidden_agents": services.hidden_agents()}

    @app.patch("/api/config/visibility/{agent_id}", dependencies=[Depends(_require_control)])
    async def set_visibility(agent_id: str, body: VisibilityUpdate) -> dict[str, Any]:
        hidden_agents = await services.set_visibility(agent_id, body.hidden)
        if hidden_agents is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return {"hidden_agents": hidden_agents}

    @app.get("/api/config/pins", dependencies=[Depends(_require_control)])
    async def get_pins() -> dict[str, Any]:
        return {"pinned_agents": services.pinned_agents()}

    @app.get("/api/config/rest", dependencies=[Depends(_require_control)])
    async def get_rest_config() -> dict[str, int]:
        return {"rest_after_s": settings.rest_after_s}

    @app.patch("/api/config/rest", dependencies=[Depends(_require_control)])
    async def set_rest_config(body: RestConfigUpdate) -> dict[str, int]:
        settings.rest_after_s = int(body.rest_after_s)
        services.audit.set_setting("rest_after_s", str(settings.rest_after_s))
        services.audit.add_event(
            "rest_config_changed",
            payload={"rest_after_s": settings.rest_after_s},
        )
        return {"rest_after_s": settings.rest_after_s}

    @app.get("/api/config/budgets", dependencies=[Depends(_require_control)])
    async def get_budgets() -> dict[str, dict[str, int]]:
        return {"budgets": dict(services.provider_budgets)}

    @app.patch("/api/config/budgets", dependencies=[Depends(_require_control)])
    async def set_budgets(body: ProviderBudgetsUpdate) -> dict[str, dict[str, int]]:
        clean: dict[str, int] = {}
        for key, value in body.budgets.items():
            provider = key.strip()[:40]
            if not provider or value < 0 or value > 10**12:
                raise HTTPException(status_code=422, detail="invalid_budget")
            clean[provider] = int(value)
        services.provider_budgets = clean
        services.audit.set_setting(
            "provider_budgets", json.dumps(clean, ensure_ascii=False)
        )
        services.audit.add_event(
            "provider_budgets_changed", payload={"budgets": clean}
        )
        return {"budgets": clean}

    @app.get("/api/config/limits", dependencies=[Depends(_require_control)])
    async def get_limits() -> dict[str, Any]:
        limits = services.audit.agent_limits()
        period = services.ticker_period
        agents: list[dict[str, Any]] = []
        for agent in services.store.agents:
            usage = {
                key: (
                    services.usage.used(agent.id, key)
                    if services.usage is not None
                    else 0
                )
                for key in ("daily", "weekly", "monthly")
            }
            agents.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "provider": agent.provider,
                    "limits": limits.get(agent.id, {}),
                    "usage": usage,
                }
            )
        return {"period": period, "agents": agents}

    @app.get("/api/limits", dependencies=[Depends(_require_control)])
    def limits() -> dict[str, Any]:
        if services.limits is None:
            return {
                "ok": False,
                "error": "disabled",
                "period": services.ticker_period,
                "selected_providers": services.ticker_providers,
                "providers": [],
            }
        return services.limits.snapshot(
            period=services.ticker_period,
            selected=services.ticker_providers,
            selected_windows=services.ticker_windows,
            view=services.limits_view,
        )

    @app.get("/api/codex/limits", dependencies=[Depends(_require_control)])
    def codex_limits() -> dict[str, Any]:
        if services.limits is None:
            return {
                "ok": False,
                "error": "disabled",
                "windows": [],
                "period": services.ticker_period,
            }
        snapshot = services.limits.snapshot(
            period=services.ticker_period,
            selected=services.ticker_providers,
            selected_windows=services.ticker_windows,
            view=services.limits_view,
        )
        provider = next(
            (
                item
                for item in snapshot["providers"]
                if item["id"] == "codex"
            ),
            None,
        )
        if provider is None:
            return {
                "ok": False,
                "error": "not_configured",
                "windows": [],
                "period": services.ticker_period,
            }
        return {**provider, "period": services.ticker_period}

    @app.patch("/api/config/limits", dependencies=[Depends(_require_control)])
    async def set_limits_period(body: LimitsPeriodUpdate) -> dict[str, Any]:
        result: dict[str, Any] = {"period": services.ticker_period}
        if body.period is not None:
            services.ticker_period = body.period
            services.audit.set_setting("ticker_period", body.period)
            services.audit.add_event(
                "ticker_period_changed", payload={"period": body.period}
            )
            result["period"] = body.period

        if "providers" in body.model_fields_set:
            if body.providers is None:
                clean: list[str] | None = None
            else:
                known = (
                    set(services.limits.provider_ids())
                    if services.limits is not None
                    else set()
                )
                clean = []
                for item in body.providers:
                    if item not in known:
                        raise HTTPException(
                            status_code=422, detail="invalid_provider"
                        )
                    if item not in clean:
                        clean.append(item)
            services.ticker_providers = clean
            services.audit.set_setting(
                "ticker_providers",
                "" if clean is None else json.dumps(clean, ensure_ascii=False),
            )
            services.audit.add_event(
                "ticker_providers_changed",
                payload={"providers": clean},
            )
            result["providers"] = clean

        if "windows" in body.model_fields_set:
            if body.windows is None:
                clean_windows: list[str] | None = None
            else:
                known = (
                    set(services.limits.provider_ids())
                    if services.limits is not None
                    else set()
                )
                clean_windows = []
                for item in body.windows:
                    provider_id = item.split(":", 1)[0] if ":" in item else ""
                    if provider_id not in known:
                        raise HTTPException(
                            status_code=422, detail="invalid_window"
                        )
                    if item not in clean_windows:
                        clean_windows.append(item)
            services.ticker_windows = clean_windows
            services.audit.set_setting(
                "ticker_windows",
                ""
                if clean_windows is None
                else json.dumps(clean_windows, ensure_ascii=False),
            )
            services.audit.add_event(
                "ticker_windows_changed",
                payload={"windows": clean_windows},
            )
            result["windows"] = clean_windows

        if body.view is not None:
            services.limits_view = body.view
            services.audit.set_setting("limits_view", body.view)
            services.audit.add_event(
                "limits_view_changed", payload={"view": body.view}
            )
            result["view"] = body.view

        result["selected_providers"] = services.ticker_providers
        result["selected_windows"] = services.ticker_windows
        result["limits_view"] = services.limits_view
        return result

    @app.patch(
        "/api/config/limits/{agent_id}", dependencies=[Depends(_require_control)]
    )
    async def set_agent_limits(
        agent_id: str, body: AgentLimitsUpdate
    ) -> dict[str, Any]:
        services.audit.set_agent_limits(
            agent_id, body.daily, body.weekly, body.monthly
        )
        services.audit.add_event(
            "agent_limits_changed",
            agent_id=agent_id,
            payload={
                "daily": body.daily,
                "weekly": body.weekly,
                "monthly": body.monthly,
            },
        )
        return {
            "agent_id": agent_id,
            "limits": {
                "daily": body.daily,
                "weekly": body.weekly,
                "monthly": body.monthly,
            },
        }

    @app.patch("/api/config/pins/{agent_id}", dependencies=[Depends(_require_control)])
    async def set_pin(agent_id: str, body: PinnedUpdate) -> dict[str, Any]:
        try:
            pinned_agents = await services.set_pinned(agent_id, body.pinned)
        except PinLimit as exc:
            raise HTTPException(status_code=409, detail="pin_limit") from exc
        if pinned_agents is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return {"pinned_agents": pinned_agents}

    @app.post("/api/dev/approval", dependencies=[Depends(_require_loopback)])
    async def force_approval(body: ForceApprovalRequest) -> dict[str, Any]:
        if not settings.dev_mode:
            raise HTTPException(status_code=404, detail="dev_mode_disabled")
        if not services.force_approval(body.risk):
            raise HTTPException(status_code=409, detail="fake_agent_busy_or_disabled")
        return {"ok": True, "queued": body.risk}

    @app.post("/api/dev/interrupt", dependencies=[Depends(_require_loopback)])
    async def interrupt() -> dict[str, Any]:
        if not settings.dev_mode:
            raise HTTPException(status_code=404, detail="dev_mode_disabled")
        ok = await services.supervisor.interrupt("claude-code")
        return {"ok": ok}

    # -- dispositivo virtual (F0) -----------------------------------------

    def _virtual():
        if not settings.dev_mode or services.virtual_device is None:
            raise HTTPException(status_code=404, detail="dev_mode_disabled")
        return services.virtual_device

    @app.get("/api/dev/virtual", dependencies=[Depends(_require_control)])
    async def virtual_info() -> dict[str, Any]:
        return _virtual().info(include_code=True)

    @app.post("/api/dev/virtual/pair", dependencies=[Depends(_require_control)])
    async def virtual_pair(body: VirtualPairRequest) -> dict[str, Any]:
        device = _virtual()
        try:
            result = device.pair(body.code, body.pc_name)
        except VirtualPairingError as exc:
            status = 429 if exc.code in {"rate_limited", "replay"} else 401
            raise HTTPException(status_code=status, detail=exc.code) from exc
        if result.get("status") == "paired":
            # Reemplazo: el panel anterior debe reconectar con el token nuevo.
            await services.hub.disconnect(device.device_id, 4401, "replaced")
        return result

    @app.post("/api/dev/virtual/confirm", dependencies=[Depends(_require_control)])
    async def virtual_confirm(body: VirtualConfirmRequest) -> dict[str, Any]:
        device = _virtual()
        try:
            result = device.confirm(body.pair_id)
        except VirtualPairingError as exc:
            status = 410 if exc.code == "expired" else 409
            raise HTTPException(status_code=status, detail=exc.code) from exc
        await services.hub.disconnect(device.device_id, 4401, "paired")
        return result

    @app.post("/api/dev/virtual/unpair", dependencies=[Depends(_require_control)])
    async def virtual_unpair() -> dict[str, Any]:
        device = _virtual()
        result = device.unpair()
        await services.hub.disconnect(device.device_id, 4401, "unpaired")
        return result

    @app.post("/api/dev/virtual/cancel", dependencies=[Depends(_require_control)])
    async def virtual_cancel() -> dict[str, Any]:
        return _virtual().cancel()

    @app.get("/api/dev/virtual/panel-token", dependencies=[Depends(_require_loopback)])
    async def virtual_panel_token() -> dict[str, str]:
        try:
            return _virtual().panel_token()
        except VirtualPairingError as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

    @app.post("/api/dev/virtual/reset", dependencies=[Depends(_require_control)])
    async def virtual_reset() -> dict[str, Any]:
        device = _virtual()
        previous_id = device.device_id
        result = device.reset()
        await services.hub.disconnect(previous_id, 4401, "reset")
        return result

    @app.get("/api/devices", dependencies=[Depends(_require_control)])
    async def devices() -> list[dict[str, Any]]:
        devices = services.audit.list_devices()
        connected = set(services.hub.device_ids)
        virtual_id = (
            services.virtual_device.device_id
            if services.virtual_device is not None
            else None
        )
        for device in devices:
            device["connected"] = device["device_id"] in connected
            if virtual_id and device["device_id"] == virtual_id:
                device["virtual"] = True
        return devices

    @app.post("/api/devices/{device_id}/revoke", dependencies=[Depends(_require_control)])
    async def revoke(device_id: str) -> dict[str, Any]:
        return {"ok": services.audit.revoke_device(device_id)}

    @app.get("/api/audit", dependencies=[Depends(_require_control)])
    async def audit(limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(limit, 500))
        return {
            "approvals": services.audit.recent_approvals(limit),
            "events": services.audit.recent_events(limit),
        }

    # -- WebSocket de control ---------------------------------------------

    async def _handshake(ws: WebSocket) -> DeviceConnection | None:
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        except (asyncio.TimeoutError, TimeoutError):
            await ws.close(code=4408, reason="hello_timeout")
            return None
        except (WebSocketDisconnect, RuntimeError):
            return None

        try:
            message = parse_client_message(raw)
        except ValidationError:
            await ws.send_text(
                json.dumps(
                    dump(
                        ErrorMessage(
                            code="invalid_hello",
                            message="se esperaba un mensaje hello válido",
                        )
                    )
                )
            )
            await ws.close(code=4400, reason="invalid_hello")
            return None

        if not isinstance(message, Hello):
            await ws.close(code=4400, reason="hello_required")
            return None
        if message.proto != PROTO_VERSION:
            await ws.send_text(
                json.dumps(
                    dump(
                        ErrorMessage(
                            code="proto_mismatch",
                            message=f"el gateway habla proto {PROTO_VERSION}",
                            retryable=False,
                        )
                    )
                )
            )
            await ws.close(code=4426, reason="proto_mismatch")
            return None

        device = services.pairing.verify(message.token)
        if device is None:
            await ws.close(code=4401, reason="invalid_token")
            return None

        return DeviceConnection(
            device_id=device["device_id"],
            name=device["name"],
            websocket=ws,
        )

    @app.websocket("/ws/control")
    async def ws_control(ws: WebSocket) -> None:
        await ws.accept()
        connection = await _handshake(ws)
        if connection is None:
            return

        await services.hub.register(connection)
        await ws.send_text(
            json.dumps(
                dump(
                    Welcome(
                        session_id=session_id,
                        server_time=services.store.snapshot().ts,
                        device_id=connection.device_id,
                        config={
                            "heartbeat_s": settings.heartbeat_s,
                            "approval_timeout_s": settings.approval_timeout_s,
                            "rest_after_s": settings.rest_after_s,
                            "provider_budgets": services.provider_budgets,
                            "ticker_period": services.ticker_period,
                            "hidden_agents": services.hidden_agents(),
                            "pinned_agents": services.pinned_agents(),
                        },
                    )
                )
            )
        )
        await services.supervisor.publish_state(connection)
        # Re-sincronización: un dispositivo que se reconecta (o recarga) no
        # puede quedarse con WAITING_INPUT sin la petición que lo explica.
        for approval in services.broker.pending:
            await services.hub.send(connection, dump(approval.to_message()))

        try:
            while True:
                raw = await ws.receive_text()
                if len(raw.encode("utf-8")) > settings.max_json_bytes:
                    await services.supervisor.handle_error(
                        connection, "frame_too_large", "mensaje JSON demasiado grande"
                    )
                    continue
                try:
                    message = parse_client_message(raw)
                except ValidationError:
                    await services.supervisor.handle_error(
                        connection, "invalid_message", "mensaje no válido"
                    )
                    continue
                await services.handle_client_message(connection, message)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            services.hub.unregister(connection.device_id, ws)

    @app.websocket("/ws/audio")
    async def ws_audio(ws: WebSocket) -> None:
        await ws.accept()
        connection = await _handshake(ws)
        if connection is None:
            return

        await ws.send_text(
            json.dumps(dump(AckMessage(ref="audio_ready", ok=True, detail="stt pendiente")))
        )

        frames = 0
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                payload = message.get("bytes")
                text = message.get("text")
                if payload is not None:
                    if len(payload) > settings.max_audio_frame_bytes:
                        await ws.send_text(
                            json.dumps(
                                dump(
                                    ErrorMessage(
                                        code="frame_too_large",
                                        message="frame de audio demasiado grande",
                                    )
                                )
                            )
                        )
                        break
                    frames += 1
                    continue
                if text is None:
                    continue
                try:
                    inbound = parse_client_message(text)
                except ValidationError:
                    await ws.send_text(
                        json.dumps(
                            dump(
                                ErrorMessage(
                                    code="invalid_message",
                                    message="mensaje de audio no válido",
                                )
                            )
                        )
                    )
                    continue
                if isinstance(inbound, AudioStart):
                    frames = 0
                    await ws.send_text(json.dumps(dump(AckMessage(ref="audio_start"))))
                elif isinstance(inbound, AudioEnd):
                    # Fase A: no hay STT todavía. Se responde con un error
                    # explícito en vez de inventar una transcripción.
                    await ws.send_text(
                        json.dumps(
                            dump(
                                ErrorMessage(
                                    code="stt_not_configured",
                                    message="la transcripción llega en la fase 0.5",
                                    retryable=False,
                                )
                            )
                        )
                    )
                else:
                    await ws.send_text(
                        json.dumps(dump(PongMessage(seq=getattr(inbound, "seq", 0))))
                    )
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            services.hub.unregister(connection.device_id, ws)

    return app
