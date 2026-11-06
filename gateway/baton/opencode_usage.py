"""Límites reales de OpenCode.

OpenCode Desktop arranca un servidor local con Basic auth (usuario
``opencode`` y la contraseña de ``~/.config/opencode/service.json``). Ese
servidor expone las ventanas del plan en:

    GET /api/experimental/usage/limits

La respuesta trae ``go.rolling``, ``go.weekly`` y ``go.monthly`` con
``percent``, ``limited`` y ``resetsAt`` en milisegundos, además de posibles
presupuestos de Console.
"""

from __future__ import annotations

import base64
import json
import shutil
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings
from .discovery import SERVICE_FILE, opencode_ports
from .limits import BaseLimitSource

ENDPOINT = "/api/experimental/usage/limits"
DEFAULT_URL = "http://127.0.0.1:28894"
WINDOWS = (
    ("rolling", "Rolling", 300),
    ("weekly", "Semanal", 10_080),
    ("monthly", "Mensual", 43_200),
)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _seconds(value: Any) -> int | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return int(number / 1000) if number > 10_000_000_000 else int(number)


def _percent(value: Any) -> int:
    number = _number(value) or 0
    return max(0, min(100, int(round(number))))


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {
            "ok": False,
            "error": "not_signed_in",
            "plan": None,
            "workspace": None,
            "windows": [],
            "budgets": [],
            "read_at": None,
        }

    workspace = data.get("workspace")
    workspace_name = (
        workspace.get("name") if isinstance(workspace, dict) else None
    )
    go = data.get("go") if isinstance(data.get("go"), dict) else {}

    windows: list[dict[str, Any]] = []
    for key, label, duration in WINDOWS:
        meter = go.get(key)
        if not isinstance(meter, dict):
            continue
        used = _percent(meter.get("percent"))
        windows.append(
            {
                "id": key,
                "label": label,
                "used_percent": used,
                "remaining_percent": 100 - used,
                "resets_at": _seconds(meter.get("resetsAt")),
                "duration_minutes": duration,
                "limited": bool(meter.get("limited")),
            }
        )

    budgets: list[dict[str, Any]] = []
    for item in data.get("budgets") or []:
        if not isinstance(item, dict):
            continue
        limit = _number(item.get("limit"))
        spent = _number(item.get("spent"))
        if limit is None or limit <= 0:
            continue
        spent = max(0.0, spent or 0.0)
        used = max(0, min(100, int(round(spent / limit * 100))))
        models = [
            str(model.get("name") or model.get("modelID") or "")
            for model in item.get("models") or []
            if isinstance(model, dict)
        ]
        models = [name for name in models if name]
        budgets.append(
            {
                "id": str(item.get("id") or "budget"),
                "label": models[0] if models else "Presupuesto",
                "used_percent": used,
                "remaining_percent": 100 - used,
                "resets_at": _seconds(item.get("resetsAt")),
                "limit_usd": round(limit, 4),
                "spent_usd": round(spent, 4),
                "models": models,
            }
        )

    if windows:
        plan = "Go"
    elif budgets:
        plan = "Console"
    else:
        plan = "OpenCode"

    return {
        "ok": True,
        "error": None,
        "plan": plan,
        "workspace": workspace_name,
        "windows": windows,
        "budgets": budgets,
        "read_at": datetime.now(timezone.utc).isoformat(),
    }


def _password(settings: Settings) -> str:
    if settings.opencode_password:
        return settings.opencode_password
    try:
        data = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    value = data.get("password")
    return value if isinstance(value, str) else ""


def _headers(settings: Settings) -> dict[str, str]:
    password = _password(settings)
    if not password:
        return {}
    raw = f"opencode:{password}".encode("utf-8")
    return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}


def _candidate_urls(settings: Settings) -> list[str]:
    if settings.opencode_url:
        return [settings.opencode_url.rstrip("/")]
    urls = [f"http://127.0.0.1:{port}" for port in opencode_ports()]
    if DEFAULT_URL not in urls:
        urls.append(DEFAULT_URL)
    return urls


def _installed(settings: Settings) -> bool:
    if settings.opencode_url:
        return True
    if shutil.which("opencode"):
        return True
    return bool(opencode_ports())


def query(settings: Settings, *, timeout: float = 4.0) -> dict[str, Any]:
    headers = _headers(settings)
    last_error = "not_running"
    for url in _candidate_urls(settings):
        try:
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                response = client.get(f"{url}{ENDPOINT}", headers=headers)
        except httpx.HTTPError:
            last_error = "unreachable"
            continue
        if response.status_code == 401:
            return {"ok": False, "error": "auth_failed", "windows": [], "budgets": []}
        if response.status_code == 404:
            last_error = "not_running"
            continue
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            last_error = "invalid_response"
            continue
        return normalize(payload)
    return {"ok": False, "error": last_error, "windows": [], "budgets": []}


class OpenCodeLimitsSource(BaseLimitSource):
    id = "opencode"
    label = "OpenCode"

    def __init__(self, settings: Settings, poll_s: float = 60.0) -> None:
        super().__init__(poll_s)
        self.settings = settings

    def refresh(self) -> dict[str, Any]:
        installed = _installed(self.settings)
        if not installed:
            return self.empty("not_installed", installed=False)
        result = query(self.settings)
        result.update(id=self.id, label=self.label, installed=True)
        result.setdefault("plan", None)
        result.setdefault("workspace", None)
        result.setdefault("budgets", [])
        return result
