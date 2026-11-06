"""Punto de entrada de la app de escritorio: ``python -m baton_desktop``."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import webview

from .bridge import Bridge, resolve_gateway

UI_DIR = Path(__file__).resolve().parent / "ui"


def _gateway_alive(url: str) -> bool:
    try:
        response = httpx.get(f"{url.rstrip('/')}/api/health", timeout=0.6)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _gateway_executable() -> Path | None:
    configured = os.environ.get("BATON_GATEWAY_EXE")
    if configured and Path(configured).is_file():
        return Path(configured)
    executable = Path(sys.executable).resolve()
    candidates = [
        executable.with_name("batonAI-gateway.exe"),
        executable.parent.parent / "gateway" / "batonAI-gateway.exe",
        executable.parent.parent / "batonAI-gateway" / "batonAI-gateway.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _ensure_gateway(url: str) -> None:
    if _gateway_alive(url):
        return
    if "127.0.0.1" not in url and "localhost" not in url:
        return
    executable = _gateway_executable()
    if executable is None:
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            creationflags=flags,
        )
    except OSError:
        return
    deadline = time.time() + 12
    while time.time() < deadline:
        if _gateway_alive(url):
            return
        time.sleep(0.4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="baton-desktop")
    parser.add_argument("--gateway-url", default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    gateway_url, _ = resolve_gateway(args.gateway_url)
    _ensure_gateway(gateway_url)
    bridge = Bridge(gateway_url)
    webview.create_window(
        "batonAI · control",
        str(UI_DIR / "index.html"),
        js_api=bridge,
        width=1100,
        height=720,
        min_size=(900, 600),
        background_color="#151610",
    )
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
