"""Lectura de los límites reales de uso de Codex.

Codex guarda la sesión en ``~/.codex`` y su app-server local expone el método
JSON-RPC ``account/rateLimits/read``. No hace falta ninguna API key adicional:
se reutiliza la sesión que ya tiene el usuario.

El gateway lanza ``codex app-server --listen stdio://`` en un subproceso, pide
los límites y lo cierra. El resultado se cachea para no repetir el proceso en
cada petición.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .limits import BaseLimitSource


def _candidate_executables() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("BATON_CODEX_EXE")
    if env:
        candidates.append(Path(env))

    which = shutil.which("codex")
    if which:
        candidates.append(Path(which))

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if local:
        candidates.extend(local.glob("OpenAI/Codex/bin/*/codex.exe"))
        candidates.extend(local.glob("Programs/*/codex.exe"))

    program_files = Path(os.environ.get("ProgramFiles", ""))
    if program_files:
        candidates.extend(
            program_files.glob("WindowsApps/OpenAI.Codex_*/app/resources/codex.exe")
        )

    return [path for path in candidates if path.is_file()]


def find_codex_executable() -> Path | None:
    candidates = _candidate_executables()
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


PERIOD_LABELS = {
    "rolling": "Rolling",
    "weekly": "Semanal",
    "monthly": "Mensual",
}

PERIOD_ORDER = {"rolling": 0, "weekly": 1, "monthly": 2, "other": 3}


def _period_id(minutes: int | None, fallback: str) -> str:
    if minutes is None:
        return fallback
    if minutes <= 360:
        return "rolling"
    if minutes <= 10_080:
        return "weekly"
    if minutes <= 43_200:
        return "monthly"
    return "other"


def _window(
    window: dict[str, Any] | None, fallback: str
) -> dict[str, Any] | None:
    if not isinstance(window, dict):
        return None
    used = max(0, min(100, int(window.get("usedPercent") or 0)))
    minutes = window.get("windowDurationMins")
    duration = int(minutes) if minutes else None
    period = _period_id(duration, fallback)
    label = (
        PERIOD_LABELS.get(period)
        or f"{max(1, round((duration or 0) / 60))} h"
    )
    return {
        "id": period,
        "label": label,
        "used_percent": used,
        "remaining_percent": max(0, 100 - used),
        "resets_at": window.get("resetsAt"),
        "duration_minutes": duration,
    }


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if "result" in payload else payload
    if not isinstance(result, dict):
        return {
            "ok": False,
            "error": "invalid_response",
            "windows": [],
            "spend_control": None,
        }

    rate = result.get("rateLimits")
    if not isinstance(rate, dict):
        return {
            "ok": False,
            "error": "invalid_response",
            "windows": [],
            "spend_control": None,
        }

    windows: list[dict[str, Any]] = []
    primary = _window(rate.get("primary"), "rolling")
    secondary = _window(rate.get("secondary"), "weekly")
    if primary:
        windows.append(primary)
    if secondary:
        windows.append(secondary)

    # Algunos planes tienen varios buckets. Se añaden los que no estén ya.
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict):
        for snapshot in by_id.values():
            if not isinstance(snapshot, dict):
                continue
            for part, fallback in (
                ("primary", "rolling"),
                ("secondary", "weekly"),
            ):
                extra = _window(snapshot.get(part), fallback)
                if extra:
                    windows.append(extra)

    # Deduplicar por periodo y reset, conservando el primero.
    deduped: list[dict[str, Any]] = []
    for item in windows:
        if not any(
            other["id"] == item["id"]
            and other["resets_at"] == item["resets_at"]
            for other in deduped
        ):
            deduped.append(item)

    deduped.sort(
        key=lambda item: (
            PERIOD_ORDER.get(item["id"], 9),
            item["duration_minutes"] or 0,
        )
    )

    # El control de gasto no es una ventana temporal: se expone aparte para
    # que no se confunda con el límite mensual.
    spend_control = None
    individual = rate.get("individualLimit")
    if isinstance(individual, dict):
        remaining = individual.get("remainingPercent")
        remaining = 0 if remaining is None else int(remaining)
        remaining = max(0, min(100, remaining))
        spend_control = {
            "remaining_percent": remaining,
            "used_percent": 100 - remaining,
            "limit": individual.get("limit"),
            "used": individual.get("used"),
            "resets_at": individual.get("resetsAt"),
        }

    return {
        "ok": True,
        "plan": rate.get("planType"),
        "account_id": result.get("accountId"),
        "windows": deduped,
        "spend_control": spend_control,
        "read_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }


def query_codex(exe: Path, timeout: float = 20.0) -> dict[str, Any]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [str(exe), "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        creationflags=flags,
    )
    lines: queue.Queue[str] = queue.Queue()

    def read(stream) -> None:
        for line in iter(stream.readline, ""):
            line = line.strip()
            if line:
                lines.put(line)

    threading.Thread(target=read, args=(proc.stdout,), daemon=True).start()
    threading.Thread(target=read, args=(proc.stderr,), daemon=True).start()

    def send(message: dict[str, Any]) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def wait_for(request_id: int, limit: float) -> dict[str, Any] | None:
        deadline = time.time() + limit
        while time.time() < deadline:
            try:
                line = lines.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if data.get("id") == request_id:
                return data
        return None

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "batonAI",
                        "title": "batonAI",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        if wait_for(1, timeout) is None:
            return {"ok": False, "error": "initialize_timeout", "windows": []}

        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "account/rateLimits/read",
                "params": {},
            }
        )
        response = wait_for(2, timeout)
        if response is None:
            return {"ok": False, "error": "limits_timeout", "windows": []}
        return normalize(response)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


class CodexLimitsSource(BaseLimitSource):
    """Límites reales de Codex vía ``codex app-server``."""

    id = "codex"
    label = "Codex"

    def __init__(self, exe: Path | None, poll_s: float = 120.0) -> None:
        super().__init__(poll_s)
        self.exe = exe

    def refresh(self) -> dict[str, Any]:
        if self.exe is None:
            return self.empty("not_installed", installed=False)
        try:
            result = query_codex(self.exe)
        except Exception as exc:  # pragma: no cover - depende del proceso
            result = {
                "ok": False,
                "error": type(exc).__name__,
                "windows": [],
                "spend_control": None,
                "plan": None,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        if not result.get("ok"):
            result["error"] = "unreachable"
        result.update(id=self.id, label=self.label, installed=True)
        result.setdefault("plan", None)
        result.setdefault("workspace", None)
        result.setdefault("budgets", [])
        result.setdefault("spend_control", None)
        result.setdefault("windows", [])
        return result
