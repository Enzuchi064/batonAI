"""Entrada del ejecutable empaquetado del gateway."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# El ejecutable instalado escucha en LAN para el modo remoto. Las peticiones
# remotas siguen requiriendo el token de control; el loopback no.
os.environ.setdefault("BATON_HOST", "0.0.0.0")

# En un ejecutable --windowed no hay stdout/stderr. Se redirigen a un log
# persistente para que el gateway pueda arrancar y dejar rastro de errores.
if sys.stdout is None or sys.stderr is None:
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "batonAI"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(
        log_dir / "gateway.log",
        "a",
        encoding="utf-8",
        buffering=1,
    )
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream

from baton.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", "--port", "8770"]))
