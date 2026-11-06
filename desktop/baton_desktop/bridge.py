"""Puente entre la interfaz web y el gateway.

La vista HTML no habla con el gateway: llama a estos métodos a través de
``window.pywebview.api``. Así no hay CORS y los errores, timeouts y el estado
viven en Python.

La visibilidad se guarda en el gateway (SQLite) mediante la API de configuración;
este puente ya no mantiene una copia local.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_GATEWAY = "http://127.0.0.1:8770"
_LOCAL_APP_DATA = (
    Path(os.environ["LOCALAPPDATA"])
    if os.environ.get("LOCALAPPDATA")
    else Path.home()
)
CONTROL_CONFIG = _LOCAL_APP_DATA / "batonAI" / "control.json"


def _load_control_config() -> dict[str, Any]:
    try:
        data = json.loads(CONTROL_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_control_config(gateway_url: str, gateway_token: str) -> None:
    CONTROL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_CONFIG.write_text(
        json.dumps(
            {
                "gateway_url": gateway_url,
                "gateway_token": gateway_token,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_gateway(
    gateway_url: str | None = None,
) -> tuple[str, str]:
    config = _load_control_config()
    url = (
        gateway_url
        or os.environ.get("BATON_GATEWAY_URL")
        or config.get("gateway_url")
        or DEFAULT_GATEWAY
    )
    token = (
        os.environ.get("BATON_GATEWAY_TOKEN")
        or config.get("gateway_token")
        or ""
    )
    return str(url).rstrip("/"), str(token)


class Bridge:
    def __init__(self, gateway_url: str | None = None) -> None:
        self.gateway_url, self.gateway_token = resolve_gateway(gateway_url)

    # -- helpers ----------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {}
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"
        try:
            with httpx.Client(base_url=self.gateway_url, timeout=2.5) as client:
                response = client.request(method, path, headers=headers, json=body)
                if response.status_code == 404:
                    return {"ok": False, "error": "agent_not_found"}
                if 400 <= response.status_code < 500:
                    try:
                        detail = response.json().get("detail", "request_failed")
                    except ValueError:
                        detail = "request_failed"
                    return {
                        "ok": False,
                        "error": str(detail),
                        "status": response.status_code,
                    }
                response.raise_for_status()
                return {"ok": True, "data": response.json()}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": type(exc).__name__}
        except ValueError:
            return {"ok": False, "error": "invalid_response"}

    # -- API expuesta a JS ------------------------------------------------

    def gateway_status(self) -> dict[str, Any]:
        result = self._request("GET", "/api/health")
        if not result["ok"]:
            return {
                "ok": False,
                "gateway": self.gateway_url,
                "error": result["error"],
            }
        data = result["data"]
        return {
            "ok": True,
            "gateway": self.gateway_url,
            "version": str(data.get("version", "")),
            "hostname": str(data.get("hostname", "")),
            "waiting": int(data.get("waiting", 0)),
        }

    def list_agents(self) -> dict[str, Any]:
        result = self._request("GET", "/api/state")
        if not result["ok"]:
            return {
                "ok": False,
                "gateway": self.gateway_url,
                "error": result["error"],
            }

        agents = result["data"].get("agents", [])
        views = [
            {
                "id": str(agent.get("id", "")),
                "name": str(agent.get("name", "")),
                "provider": str(agent.get("provider", "")),
                "model": str(agent.get("model", "")),
                "status": str(agent.get("status", "")).lower(),
                "since": str(agent.get("since", "")),
                "last_event_at": str(agent.get("last_event_at", "")),
                "cwd": str(agent.get("cwd", "")),
                "task": str(agent.get("task", "")),
                "log_tail": [str(line) for line in agent.get("log_tail", [])],
                "cost_turn": float(agent.get("cost_turn", 0) or 0),
                "cost_session": float(agent.get("cost_session", 0) or 0),
                "tokens_session": int(agent.get("tokens_session", 0) or 0),
                "approval_id": agent.get("approval_id"),
                "prompt": agent.get("prompt"),
                "risk": agent.get("risk"),
                "risk_reasons": list(agent.get("risk_reasons") or []),
                "risk_details": list(agent.get("risk_details") or []),
            }
            for agent in agents
            if agent.get("id")
        ]
        views.sort(key=lambda agent: agent["name"].lower())

        visibility = self._request("GET", "/api/config/visibility")
        hidden = (
            list(visibility["data"].get("hidden_agents", []))
            if visibility["ok"]
            else []
        )
        pins = self._request("GET", "/api/config/pins")
        pinned = (
            list(pins["data"].get("pinned_agents", []))
            if pins["ok"]
            else []
        )

        return {
            "ok": True,
            "agents": views,
            "system": result["data"].get("system", {}),
            "hidden": hidden,
            "pinned": pinned,
            "persisted": True,
        }

    def set_visibility(self, agent_id: str, hidden: bool) -> dict[str, Any]:
        if not isinstance(agent_id, str) or not agent_id:
            return {"ok": False, "error": "invalid_agent"}

        result = self._request(
            "PATCH",
            f"/api/config/visibility/{quote(agent_id, safe='')}",
            {"hidden": bool(hidden)},
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}

        return {
            "ok": True,
            "hidden": list(result["data"].get("hidden_agents", [])),
            "persisted": True,
        }

    def set_pinned(self, agent_id: str, pinned: bool) -> dict[str, Any]:
        if not isinstance(agent_id, str) or not agent_id:
            return {"ok": False, "error": "invalid_agent"}

        result = self._request(
            "PATCH",
            f"/api/config/pins/{quote(agent_id, safe='')}",
            {"pinned": bool(pinned)},
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}

        return {
            "ok": True,
            "pinned": list(result["data"].get("pinned_agents", [])),
            "persisted": True,
        }

    # -- acciones sobre agentes -------------------------------------------

    def interrupt_agent(self, agent_id: str) -> dict[str, Any]:
        if not isinstance(agent_id, str) or not agent_id:
            return {"ok": False, "error": "invalid_agent"}
        result = self._request(
            "POST", f"/api/agents/{quote(agent_id, safe='')}/interrupt"
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True}

    def send_agent_text(self, agent_id: str, text: str) -> dict[str, Any]:
        if not isinstance(agent_id, str) or not agent_id:
            return {"ok": False, "error": "invalid_agent"}
        message = str(text or "").strip()
        if not message:
            return {"ok": False, "error": "empty_text"}
        result = self._request(
            "POST",
            f"/api/agents/{quote(agent_id, safe='')}/message",
            {"text": message[:4000]},
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "chars": int(result["data"].get("chars", 0))}

    def open_folder(self, path: str) -> dict[str, Any]:
        if not isinstance(path, str) or not path:
            return {"ok": False, "error": "invalid_path"}
        target = Path(path)
        if not target.is_dir():
            return {"ok": False, "error": "not_a_directory"}
        try:
            if os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:  # pragma: no cover - depende del SO
            return {"ok": False, "error": type(exc).__name__}
        return {"ok": True, "path": str(target)}

    # -- hardware y ajustes ------------------------------------------------

    def gateway_info(self) -> dict[str, Any]:
        result = self._request("GET", "/api/info")
        if not result["ok"]:
            return {
                "ok": False,
                "gateway": self.gateway_url,
                "error": result["error"],
            }
        return {"ok": True, "gateway": self.gateway_url, **result["data"]}

    def connection_config(self) -> dict[str, Any]:
        return {
            "ok": True,
            "gateway_url": self.gateway_url,
            "token": self.gateway_token,
        }

    def set_connection_config(
        self, gateway_url: str, token: str = ""
    ) -> dict[str, Any]:
        url = str(gateway_url or "").strip()
        if not url:
            return {"ok": False, "error": "empty_url"}
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        url = url.rstrip("/")
        clean_token = str(token or "").strip()
        try:
            _save_control_config(url, clean_token)
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__}
        self.gateway_url = url
        self.gateway_token = clean_token
        return {"ok": True, "gateway_url": url, "token": clean_token}

    def remote_config(self) -> dict[str, Any]:
        result = self._request("GET", "/api/config/remote")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def pairing_code(self) -> dict[str, Any]:
        result = self._request("GET", "/api/dev/pairing")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "code": str(result["data"].get("code", ""))}

    def rest_config(self) -> dict[str, Any]:
        result = self._request("GET", "/api/config/rest")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "rest_after_s": int(result["data"].get("rest_after_s", 300)),
        }

    def set_rest_config(self, rest_after_s: int) -> dict[str, Any]:
        seconds = int(rest_after_s)
        if seconds < 0 or seconds > 3600:
            return {"ok": False, "error": "invalid_rest_after"}
        result = self._request(
            "PATCH", "/api/config/rest", {"rest_after_s": seconds}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "rest_after_s": int(result["data"].get("rest_after_s", seconds)),
        }

    def set_limit_period(self, period: str) -> dict[str, Any]:
        if period not in {"rolling", "weekly", "monthly", "all"}:
            return {"ok": False, "error": "invalid_period"}
        result = self._request(
            "PATCH", "/api/config/limits", {"period": period}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "period": result["data"].get("period", period)}

    def limits(self) -> dict[str, Any]:
        result = self._request("GET", "/api/limits")
        if not result["ok"]:
            return {
                "ok": False,
                "error": result["error"],
                "providers": [],
                "period": "all",
                "selected_providers": None,
            }
        return {"ok": True, **result["data"]}

    def codex_limits(self) -> dict[str, Any]:
        result = self._request("GET", "/api/codex/limits")
        if not result["ok"]:
            return {"ok": False, "error": result["error"], "windows": []}
        return {"ok": True, **result["data"]}

    def set_limit_windows(
        self, windows: list[str] | None
    ) -> dict[str, Any]:
        if windows is not None:
            if not isinstance(windows, list):
                return {"ok": False, "error": "invalid_windows"}
            clean: list[str] = []
            for item in windows:
                window = str(item).strip()
                if ":" not in window:
                    return {"ok": False, "error": "invalid_window"}
                if window not in clean:
                    clean.append(window)
            windows = clean
        result = self._request(
            "PATCH", "/api/config/limits", {"windows": windows}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "selected_windows": result["data"].get(
                "selected_windows", windows
            ),
        }

    def set_limits_view(self, view: str) -> dict[str, Any]:
        if view not in {"remaining", "used"}:
            return {"ok": False, "error": "invalid_view"}
        result = self._request(
            "PATCH", "/api/config/limits", {"view": view}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "limits_view": result["data"].get("view", view),
        }

    def set_limit_providers(
        self, providers: list[str] | None
    ) -> dict[str, Any]:
        if providers is not None:
            if not isinstance(providers, list):
                return {"ok": False, "error": "invalid_providers"}
            clean: list[str] = []
            for item in providers:
                provider = str(item).strip()
                if not provider or provider not in {"opencode", "codex", "claude"}:
                    return {"ok": False, "error": "invalid_provider"}
                if provider not in clean:
                    clean.append(provider)
            providers = clean
        result = self._request(
            "PATCH", "/api/config/limits", {"providers": providers}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "selected_providers": result["data"].get(
                "selected_providers", providers
            ),
        }

    # -- dispositivo virtual (prueba del QR) ------------------------------

    def virtual_device(self) -> dict[str, Any]:
        result = self._request("GET", "/api/dev/virtual")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def virtual_pair(self, code: str, pc_name: str = "DESKTOP") -> dict[str, Any]:
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "error": "empty_code"}
        result = self._request(
            "POST",
            "/api/dev/virtual/pair",
            {"code": code, "pc_name": str(pc_name or "DESKTOP")[:64]},
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def virtual_confirm(self, pair_id: str) -> dict[str, Any]:
        if not isinstance(pair_id, str) or not pair_id:
            return {"ok": False, "error": "invalid_pair"}
        result = self._request(
            "POST", "/api/dev/virtual/confirm", {"pair_id": pair_id}
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def virtual_unpair(self) -> dict[str, Any]:
        result = self._request("POST", "/api/dev/virtual/unpair")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def virtual_reset(self) -> dict[str, Any]:
        result = self._request("POST", "/api/dev/virtual/reset")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, **result["data"]}

    def devices(self) -> dict[str, Any]:
        result = self._request("GET", "/api/devices")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        devices = result["data"] if isinstance(result["data"], list) else []
        return {"ok": True, "devices": devices}

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        if not isinstance(device_id, str) or not device_id:
            return {"ok": False, "error": "invalid_device"}
        result = self._request(
            "POST", f"/api/devices/{quote(device_id, safe='')}/revoke"
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "revoked": bool(result["data"].get("ok"))}

    def audit(self, limit: int = 40) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        result = self._request("GET", f"/api/audit?limit={limit}")
        if not result["ok"]:
            return {"ok": False, "error": result["error"]}
        return {
            "ok": True,
            "approvals": list(result["data"].get("approvals", [])),
            "events": list(result["data"].get("events", [])),
        }

    def open_panel(self) -> dict[str, Any]:
        url = f"{self.gateway_url}/"
        try:
            opened = webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - depende del SO
            return {"ok": False, "error": type(exc).__name__, "url": url}
        return {"ok": bool(opened), "url": url}
