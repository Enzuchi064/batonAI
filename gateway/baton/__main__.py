"""Punto de entrada: ``python -m baton`` o ``baton serve``."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from . import __version__
from .api import create_app
from .config import Settings


def _print_banner(settings: Settings, code: str) -> None:
    host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    print()
    print("  batonAI gateway " + __version__)
    print("  -----------------------------")
    print(f"  panel:         http://{host}:{settings.port}/")
    print(f"  websocket:     ws://{host}:{settings.port}/ws/control")
    print(f"  codigo de emparejamiento: {code}")
    print(f"  base de datos: {settings.db_path}")
    if settings.host in {"0.0.0.0", "::"}:
        print("  aviso: escuchando en toda la LAN; usa solo en una red de confianza")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="baton", description="Gateway de batonAI")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="arranca el gateway")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--fake", action="store_true", help="incluye agentes de demostración")
    serve.add_argument(
        "--no-fake",
        action="store_true",
        help="sin agentes de demostración (ya es el comportamiento por defecto)",
    )

    sub.add_parser("pair", help="genera un código de emparejamiento y sale")

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "pair":
        from .services import Services

        services = Services.build(settings, fake=False)
        print(f"codigo de emparejamiento: {services.pairing.code}")
        services.audit.close()
        return 0

    if args.command in (None, "serve"):
        if args.command == "serve":
            if args.host:
                settings.host = args.host
            if args.port:
                settings.port = args.port

        app = create_app(
            settings, fake=True if args.fake else False if args.no_fake else None
        )
        _print_banner(settings, app.state.services.pairing.code)
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
