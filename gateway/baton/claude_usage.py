"""Límites reales de Claude Code.

Claude Code guarda el token OAuth en ``~/.claude/.credentials.json``
(``claudeAiOauth.accessToken``) o en ``CLAUDE_CODE_OAUTH_TOKEN``. Con ese token
se consulta el mismo endpoint que usa la app de Claude para el plan:

    GET https://api.anthropic.com/api/oauth/usage

La respuesta trae ``five_hour`` y ``seven_day`` con ``utilization`` (porcentaje
usado) y ``resets_at``.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .limits import BaseLimitSource

DEFAULT_HOST = "https://api.anthropic.com"
ENDPOINT = "/api/oauth/usage"
WINDOWS = (
    ("five_hour", "rolling", "Rolling", 300),
    ("seven_day", "weekly", "Semanal", 10_080),
)
EXTRA_WINDOWS = (
    ("seven_day_sonnet", "weekly", "Semanal · Sonnet", 10_080),
    ("seven_day_opus", "weekly", "Semanal · Opus", 10_080),
)


def _claude_home() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def _credentials_file() -> Path:
    return _claude_home() / ".credentials.json"


def _token() -> str | None:
    env = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if env and env.strip():
        return env.strip()
    try:
        data = json.loads(_credentials_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth")
    if isinstance(oauth, dict):
        value = oauth.get("accessToken")
        if isinstance(value, str) and value:
            return value
    value = data.get("accessToken")
    return value if isinstance(value, str) and value else None


def _installed() -> bool:
    if _token():
        return True
    if _claude_home().exists():
        return True
    return bool(shutil.which("claude"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            pass
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    number = _number(value)
    if number is None or number <= 0:
        return None
    return int(number / 1000) if number > 10_000_000_000 else int(number)


def _percent(value: Any) -> int:
    number = _number(value)
    if number is None:
        number = 0
    return max(0, min(100, int(round(number))))


def _window(
    entry: Any,
    *,
    window_id: str,
    label: str,
    duration: int,
) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    utilization = entry.get("utilization")
    if utilization is None:
        return None
    used = _percent(utilization)
    return {
        "id": window_id,
        "label": label,
        "used_percent": used,
        "remaining_percent": 100 - used,
        "resets_at": _seconds(entry.get("resets_at")),
        "duration_minutes": duration,
    }


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_response", "windows": []}

    windows: list[dict[str, Any]] = []
    for key, window_id, label, duration in WINDOWS:
        window = _window(
            payload.get(key),
            window_id=window_id,
            label=label,
            duration=duration,
        )
        if window:
            windows.append(window)

    for key, window_id, label, duration in EXTRA_WINDOWS:
        window = _window(
            payload.get(key),
            window_id=window_id,
            label=label,
            duration=duration,
        )
        if window:
            windows.append(window)

    # Algunas cuentas devuelven límites semanales por modelo en ``limits``.
    for item in payload.get("limits") or []:
        if not isinstance(item, dict) or item.get("kind") != "weekly_scoped":
            continue
        scope = item.get("scope")
        model = scope.get("model") if isinstance(scope, dict) else None
        name = model.get("display_name") if isinstance(model, dict) else None
        label = f"Semanal · {name}" if isinstance(name, str) and name else "Semanal"
        window = _window(
            item,
            window_id="weekly",
            label=label,
            duration=10_080,
        )
        if window:
            windows.append(window)

    deduped: list[dict[str, Any]] = []
    for window in windows:
        if not any(
            other["label"] == window["label"]
            and other["resets_at"] == window["resets_at"]
            for other in deduped
        ):
            deduped.append(window)

    return {
        "ok": True,
        "error": None,
        "plan": None,
        "workspace": None,
        "windows": deduped,
        "budgets": [],
        "read_at": datetime.now(timezone.utc).isoformat(),
    }


def query(*, timeout: float = 10.0) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "error": "not_authenticated", "windows": []}
    host = os.environ.get("BATON_CLAUDE_API_HOST", DEFAULT_HOST).rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "batonAI/0.1",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{host}{ENDPOINT}", headers=headers)
    except httpx.HTTPError:
        return {"ok": False, "error": "unreachable", "windows": []}
    if response.status_code == 401:
        return {"ok": False, "error": "token_expired", "windows": []}
    try:
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError:
        return {"ok": False, "error": "http_error", "windows": []}
    except ValueError:
        return {"ok": False, "error": "invalid_response", "windows": []}
    return normalize(payload)


class ClaudeLimitsSource(BaseLimitSource):
    id = "claude"
    label = "Claude Code"

    def __init__(self, poll_s: float = 120.0) -> None:
        super().__init__(poll_s)

    def refresh(self) -> dict[str, Any]:
        installed = _installed()
        if not installed:
            return self.empty("not_installed", installed=False)
        result = query()
        result.update(id=self.id, label=self.label, installed=True)
        result.setdefault("plan", None)
        result.setdefault("workspace", None)
        result.setdefault("budgets", [])
        return result
