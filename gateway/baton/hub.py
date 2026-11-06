"""Registro de dispositivos conectados y envío de mensajes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from .util import iso


@dataclass(slots=True)
class DeviceConnection:
    device_id: str
    name: str
    websocket: Any
    connected_at: str = field(default_factory=iso)


class DeviceHub:
    def __init__(self) -> None:
        self._devices: dict[str, DeviceConnection] = {}

    @property
    def connections(self) -> list[DeviceConnection]:
        return list(self._devices.values())

    @property
    def device_ids(self) -> list[str]:
        return list(self._devices)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._devices

    async def register(self, connection: DeviceConnection) -> None:
        previous = self._devices.get(connection.device_id)
        self._devices[connection.device_id] = connection
        if previous is not None:
            # Un mismo dispositivo abriendo dos conexiones: gana la última.
            try:
                await previous.websocket.close(code=4409, reason="replaced")
            except Exception:
                pass

    def unregister(self, device_id: str, websocket: Any | None = None) -> None:
        current = self._devices.get(device_id)
        if current is None:
            return
        if websocket is not None and current.websocket is not websocket:
            return
        self._devices.pop(device_id, None)

    async def send(self, connection: DeviceConnection, payload: dict[str, Any]) -> bool:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        try:
            await asyncio.wait_for(connection.websocket.send_text(text), timeout=2.0)
            return True
        except Exception:
            self.unregister(connection.device_id, connection.websocket)
            return False

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self._devices:
            return
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        results = await asyncio.gather(
            *(self._send_text(conn, text) for conn in list(self._devices.values())),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                continue

    async def _send_text(self, connection: DeviceConnection, text: str) -> None:
        try:
            await asyncio.wait_for(connection.websocket.send_text(text), timeout=2.0)
        except Exception:
            self.unregister(connection.device_id, connection.websocket)

    async def close_all(self) -> None:
        for connection in list(self._devices.values()):
            try:
                await connection.websocket.close(code=1001, reason="gateway shutdown")
            except Exception:
                pass
        self._devices.clear()

    async def disconnect(
        self, device_id: str, code: int = 4401, reason: str = "unpaired"
    ) -> bool:
        connection = self._devices.pop(device_id, None)
        if connection is None:
            return False
        try:
            await connection.websocket.close(code=code, reason=reason)
        except Exception:
            pass
        return True
