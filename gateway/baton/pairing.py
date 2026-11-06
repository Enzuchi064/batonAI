"""Emparejamiento y tokens de dispositivo.

El dispositivo no guarda ni conoce las API keys de los agentes; solo tiene un
token opaco emitido por el gateway. En la base de datos se guarda su hash,
nunca el token en claro.

El código de 6 dígitos caduca y rota. En producción se muestra en el propio
dispositivo o en el panel local; aquí se imprime en la consola del gateway.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time

from .audit import AuditLog


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PairingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PairingManager:
    def __init__(self, audit: AuditLog, *, code_ttl_s: float = 600.0) -> None:
        self._audit = audit
        self._ttl = code_ttl_s
        self._code: str | None = None
        self._code_expires_at = 0.0

    # -- código de emparejamiento ----------------------------------------

    def _rotate(self) -> str:
        self._code = f"{secrets.randbelow(1_000_000):06d}"
        self._code_expires_at = time.monotonic() + self._ttl
        return self._code

    @property
    def code(self) -> str:
        if self._code is None or time.monotonic() >= self._code_expires_at:
            return self._rotate()
        return self._code

    def pair(self, code: str, device_name: str) -> dict[str, str]:
        if not secrets.compare_digest(code.strip(), self.code):
            raise PairingError("invalid_code", "código de emparejamiento incorrecto")
        return self._issue(device_name.strip() or "dispositivo")

    # -- emisión de tokens ------------------------------------------------

    def _issue(self, device_name: str, device_id: str | None = None) -> dict[str, str]:
        device_id = device_id or f"baton-{secrets.token_hex(3)}"
        token = secrets.token_urlsafe(32)
        self._audit.delete_device(device_id)
        self._audit.add_device(device_id, device_name, hash_token(token))
        self._audit.add_event("device_paired", device_id=device_id, payload={"name": device_name})
        return {"device_id": device_id, "name": device_name, "token": token}

    def issue_for(self, device_id: str, name: str) -> dict[str, str]:
        """Emite un token para un dispositivo ya autenticado.

        Lo usa el flujo TOTP y el dispositivo virtual. El token se devuelve una
        sola vez; en la base de datos solo queda su hash.
        """

        return self._issue(name, device_id=device_id)

    def bootstrap(self, device_id: str | None = None) -> dict[str, str]:
        """Token de conveniencia para el panel web en localhost.

        Solo se expone desde la API de desarrollo escuchando en loopback. Cada
        pestaña puede traer su propio ``device_id`` para no rotar el token de
        las demás.
        """
        candidate = (device_id or "").strip()
        candidate = re.sub(r"[^A-Za-z0-9_-]", "", candidate)
        if not candidate.startswith("baton-web"):
            # Paneles antiguos que no envían id: cada uno recibe el suyo para
            # que no se roten el token entre pestañas.
            candidate = f"baton-web-{secrets.token_hex(4)}"
        return self._issue("Panel web (dev)", device_id=candidate[:64])

    def verify(self, token: str) -> dict[str, str] | None:
        found = self._audit.find_active_device_by_hash(hash_token(token))
        if not found:
            return None
        self._audit.touch_device(found["device_id"])
        return found
