"""Descubrimiento del gateway en la red local.

El gateway responde a un pequeño broadcast UDP. La app del otro PC lo usa para
encontrar el dispositivo y luego vincularse con el código de Google
Authenticator, sin tener que escribir la URL ni el token.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from typing import Any

import psutil

from . import __version__

DISCOVERY_PORT = 8766
DISCOVERY_MESSAGE = b"BATONAI_DISCOVER_V1"


def lan_urls(port: int) -> list[dict[str, str]]:
    urls: list[dict[str, str]] = []
    try:
        for name, addresses in psutil.net_if_addrs().items():
            for address in addresses:
                if address.family != socket.AF_INET:
                    continue
                if address.address.startswith(("127.", "169.254.")):
                    continue
                url = f"http://{address.address}:{port}"
                if not any(item["url"] == url for item in urls):
                    urls.append({"interface": name, "url": url})
    except Exception:
        pass

    primary = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        primary = f"http://{probe.getsockname()[0]}:{port}"
        probe.close()
    except OSError:
        primary = None
    if primary:
        urls = [item for item in urls if item["url"] != primary]
        urls.insert(0, {"interface": "principal", "url": primary})
    return urls


def broadcast_addresses() -> list[str]:
    addresses = {"255.255.255.255", "127.0.0.1"}
    try:
        for addresses_for_if in psutil.net_if_addrs().values():
            for address in addresses_for_if:
                if address.family != socket.AF_INET:
                    continue
                if not address.netmask or address.address.startswith("127."):
                    continue
                try:
                    network = ipaddress.IPv4Network(
                        f"{address.address}/{address.netmask}", strict=False
                    )
                except ValueError:
                    continue
                addresses.add(str(network.broadcast_address))
    except Exception:
        pass
    return sorted(addresses)


class DiscoveryResponder:
    def __init__(self, port: int, device_id: str) -> None:
        self.port = port
        self.device_id = device_id
        self.hostname = socket.gethostname()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="baton-discovery", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _payload(self) -> dict[str, Any]:
        return {
            "service": "batonai",
            "version": __version__,
            "hostname": self.hostname,
            "device_id": self.device_id,
            "urls": [item["url"] for item in lan_urls(self.port)],
        }

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(("0.0.0.0", DISCOVERY_PORT))
        except OSError:
            sock.close()
            return
        try:
            while not self._stop.is_set():
                try:
                    data, address = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data.strip() != DISCOVERY_MESSAGE:
                    continue
                try:
                    sock.sendto(
                        json.dumps(self._payload(), ensure_ascii=False).encode(
                            "utf-8"
                        ),
                        address,
                    )
                except OSError:
                    continue
        finally:
            sock.close()


def discover(timeout: float = 2.0) -> list[dict[str, Any]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)
    try:
        for address in broadcast_addresses():
            try:
                sock.sendto(DISCOVERY_MESSAGE, (address, DISCOVERY_PORT))
            except OSError:
                continue
        deadline = time.monotonic() + max(0.5, timeout)
        found: dict[str, dict[str, Any]] = {}
        while time.monotonic() < deadline:
            try:
                data, address = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                payload = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if payload.get("service") != "batonai":
                continue
            urls = payload.get("urls") or []
            if not urls:
                continue
            key = str(urls[0])
            found[key] = {
                "url": urls[0],
                "urls": [str(url) for url in urls],
                "hostname": str(payload.get("hostname") or ""),
                "device_id": str(payload.get("device_id") or ""),
                "version": str(payload.get("version") or ""),
                "address": address[0],
                "local": payload.get("hostname") == socket.gethostname(),
            }
        return list(found.values())
    finally:
        sock.close()
