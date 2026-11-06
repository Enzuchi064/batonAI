"""Fuentes y agregación de límites reales de las IAs instaladas.

Cada fuente devuelve un snapshot con la misma forma:

```
{
  "id": "opencode",
  "label": "OpenCode",
  "installed": true,
  "ok": true,
  "plan": "Go",
  "workspace": "Personal",
  "windows": [...],
  "budgets": [...],
  "error": null,
  "read_at": "2026-11-06T..."
}
```

``LimitsService`` consulta cada fuente con su propia caché y añade el estado
``selected`` según la configuración del usuario. No lanza hilos: las fuentes se
refrescan cuando alguien pide ``GET /api/limits`` y ha pasado su intervalo.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Protocol


class LimitSource(Protocol):
    id: str
    label: str
    poll_s: float

    def snapshot(self) -> dict[str, Any]: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseLimitSource:
    """Caché común para una fuente de límites."""

    id = "base"
    label = "Base"
    poll_s = 60.0

    def __init__(self, poll_s: float | None = None) -> None:
        if poll_s is not None:
            self.poll_s = max(5.0, float(poll_s))
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._last_refresh = 0.0
        self._snapshot = self.empty("not_read", installed=True)

    def empty(
        self, error: str, *, installed: bool = True
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "installed": installed,
            "ok": False,
            "plan": None,
            "workspace": None,
            "windows": [],
            "budgets": [],
            "error": error,
            "read_at": None,
        }

    def refresh(self) -> dict[str, Any]:
        raise NotImplementedError

    def snapshot(self) -> dict[str, Any]:
        # Las peticiones simultáneas esperan a que termine la lectura en curso:
        # así ninguna recibe un snapshot vacío mientras otra refresca.
        with self._refresh_lock:
            with self._lock:
                now = time.monotonic()
                if now - self._last_refresh < self.poll_s:
                    return dict(self._snapshot)
                self._last_refresh = now
            try:
                fresh = self.refresh()
            except Exception as exc:  # pragma: no cover - depende de cada fuente
                fresh = self.empty(type(exc).__name__)
            with self._lock:
                self._snapshot = fresh
            return dict(fresh)


class LimitsService:
    def __init__(self, sources: list[LimitSource]) -> None:
        self.sources = list(sources)

    def provider_ids(self) -> list[str]:
        return [source.id for source in self.sources]

    def snapshot(
        self,
        *,
        period: str = "all",
        selected: list[str] | None = None,
        selected_windows: list[str] | None = None,
        view: str = "remaining",
    ) -> dict[str, Any]:
        selected_providers = set(selected) if selected is not None else None
        selected_set = (
            set(selected_windows)
            if selected_windows is not None
            else None
        )
        providers: list[dict[str, Any]] = []
        for source in self.sources:
            provider = source.snapshot()
            provider_allowed = bool(provider.get("installed")) and (
                selected_providers is None
                or provider["id"] in selected_providers
            )
            seen: dict[str, int] = {}
            for window in provider.get("windows") or []:
                base = f"{provider['id']}:{window.get('id') or 'window'}"
                key = base
                if key in seen:
                    seen[key] += 1
                    key = f"{base}#{seen[key]}"
                else:
                    seen[key] = 1
                window["key"] = key
                window["selected"] = provider_allowed and (
                    selected_set is None or key in selected_set
                )
            provider["selected"] = any(
                window.get("selected")
                for window in provider.get("windows") or []
            )
            providers.append(provider)

        installed = [item for item in providers if item.get("installed")]
        active = [item for item in installed if item.get("ok")]
        if view not in {"remaining", "used"}:
            view = "remaining"
        return {
            "ok": bool(active),
            "period": period,
            "view": view,
            "selected_providers": selected,
            "selected_windows": selected_windows,
            "providers": providers,
            "read_at": _now_iso(),
            "error": None if active else "no_sources",
        }
