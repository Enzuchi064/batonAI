"""Dispositivo virtual para probar el emparejamiento TOTP sin hardware.

Imita lo mínimo del ESP32: guarda un ``device_id`` y un secreto TOTP, pinta el
QR, verifica el código y recuerda a qué PC está emparejado. La app habla con él
a través de la API local, igual que lo hará con el dispositivo real.

El secreto se persiste en ``var/virtual_device.json`` para no tener que volver a
escanear el QR cada vez que se reinicia el gateway.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import totp
from .audit import AuditLog
from .pairing import PairingManager

try:  # segno es puro Python; si falta, el QR se sirve como URI
    import segno
except ImportError:  # pragma: no cover - depende del entorno
    segno = None  # type: ignore[assignment]


class VirtualPairingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _Pending:
    pair_id: str
    pc_name: str
    sas: str
    step: int
    created_at: float


@dataclass
class VirtualDevice:
    audit: AuditLog
    pairing: PairingManager
    path: Path
    device_id: str = ""
    secret: str = ""
    paired_to: str | None = None
    paired_at: str | None = None
    token: str | None = None
    attempts: int = 0
    failures: int = 0
    locked_until: float = 0.0
    last_step: int | None = None
    pending: _Pending | None = None
    opened_at: float = field(default_factory=time.time)

    # -- construcción y persistencia --------------------------------------

    @classmethod
    def create(
        cls, audit: AuditLog, pairing: PairingManager, path: Path
    ) -> "VirtualDevice":
        device = cls(audit=audit, pairing=pairing, path=path)
        device._load()
        if not device.device_id or not device.secret:
            device._regenerate()
            device._save()
        return device

    def _regenerate(self) -> None:
        self.device_id = f"baton-{secrets.token_hex(4)}"
        self.secret = totp.generate_secret()
        self.paired_to = None
        self.paired_at = None
        self.token = None
        self.attempts = 0
        self.failures = 0
        self.locked_until = 0.0
        self.last_step = None
        self.pending = None
        self.opened_at = time.time()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.device_id = str(data.get("device_id", ""))
        self.secret = str(data.get("secret", ""))
        paired_to = data.get("paired_to")
        self.paired_to = str(paired_to) if paired_to else None
        paired_at = data.get("paired_at")
        self.paired_at = str(paired_at) if paired_at else None
        token = data.get("token")
        self.token = str(token) if token else None

    def _save(self) -> None:
        payload = {
            "device_id": self.device_id,
            "secret": self.secret,
            "paired_to": self.paired_to,
            "paired_at": self.paired_at,
            "token": self.token,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:  # pragma: no cover - disco lleno o permisos
            pass

    # -- información -------------------------------------------------------

    @property
    def short(self) -> str:
        return self.device_id.removeprefix("baton-").upper()

    @property
    def uri(self) -> str:
        return totp.otpauth_uri(self.secret, self.device_id)

    @property
    def sas(self) -> str | None:
        return self.pending.sas if self.pending else None

    def info(self, *, include_code: bool = False) -> dict[str, Any]:
        svg = ""
        if segno is not None:
            qr = segno.make(self.uri, error="m")
            svg = qr.svg_inline(scale=3, border=2)
        return {
            "device_id": self.device_id,
            "short": self.short,
            "name": "Dispositivo virtual",
            "paired": self.paired_to is not None,
            "paired_to": self.paired_to,
            "paired_at": self.paired_at,
            "sas": self.sas,
            "needs_confirm": bool(self.pending),
            "pair_id": self.pending.pair_id if self.pending else None,
            "pending_pc": self.pending.pc_name if self.pending else None,
            "token_ready": bool(self.token),
            "qr_svg": svg,
            "otpauth": self.uri,
            "code": totp.totp(self.secret) if include_code else None,
            "code_expires_in": 30 - int(time.time()) % 30,
            "virtual": True,
        }

    # -- emparejamiento ----------------------------------------------------

    def _sas_for(self, step: int) -> str:
        digest = hashlib.sha256(f"{self.device_id}:{step}".encode("utf-8")).digest()
        return str(int.from_bytes(digest[:4], "big") % 10_000).zfill(4)

    def _check_code(self, code: str) -> int:
        now = time.time()
        if now < self.locked_until:
            raise VirtualPairingError(
                "rate_limited",
                f"espera {int(self.locked_until - now) + 1} s antes de reintentar",
            )

        step = totp.verify(self.secret, code, window=1)
        if step is None:
            self.attempts += 1
            self.failures += 1
            if self.attempts >= 5:
                self.attempts = 0
                self.locked_until = now + 60.0
            self.audit.add_event(
                "pair_failed", device_id=self.device_id, payload={"reason": "bad_code"}
            )
            raise VirtualPairingError("bad_code", "código incorrecto")

        if self.last_step is not None and step <= self.last_step:
            raise VirtualPairingError("replay", "ese código ya se ha usado")
        return step

    def pair(self, code: str, pc_name: str) -> dict[str, Any]:
        """Valida el código.

        Si es el primer emparejamiento, deja un ``pending`` que exige confirmar
        (la A del dispositivo). Si ya estaba emparejado, reemplaza el PC al
        instante, como hará el hardware.
        """

        step = self._check_code(code)
        pc = (pc_name.strip() or "DESKTOP")[:64]

        if self.paired_to is None:
            self.pending = _Pending(
                pair_id=secrets.token_urlsafe(12),
                pc_name=pc,
                sas=self._sas_for(step),
                step=step,
                created_at=time.time(),
            )
            self.attempts = 0
            self.audit.add_event(
                "pair_confirm_required",
                device_id=self.device_id,
                payload={"pc": pc, "virtual": True},
            )
            return {
                "status": "needs_confirm",
                "pair_id": self.pending.pair_id,
                "sas": self.pending.sas,
                "pc_name": pc,
            }

        self._bind(pc, step)
        return {"status": "paired", "sas": self._sas_for(step), "pc_name": pc}

    def confirm(self, pair_id: str) -> dict[str, Any]:
        now = time.time()
        pending = self.pending
        if pending is None or pending.pair_id != pair_id:
            raise VirtualPairingError("unknown_pair", "no hay emparejamiento pendiente")
        if now - pending.created_at > 60:
            self.pending = None
            raise VirtualPairingError("expired", "la confirmación ha caducado")

        self._bind(pending.pc_name, pending.step)
        return {"status": "paired", "sas": pending.sas, "pc_name": pending.pc_name}

    def _bind(self, pc_name: str, step: int) -> None:
        issued = self.pairing.issue_for(self.device_id, "Dispositivo virtual")
        self.token = issued["token"]
        self.paired_to = pc_name
        self.paired_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.last_step = step
        self.pending = None
        self.attempts = 0
        self._save()
        self.audit.add_event(
            "device_paired",
            device_id=self.device_id,
            payload={"name": pc_name, "virtual": True, "token": issued["token"][:6]},
        )

    def unpair(self) -> dict[str, Any]:
        if self.paired_to is None:
            return {"status": "already_unpaired", "device_id": self.device_id}
        previous = self.paired_to
        self.paired_to = None
        self.paired_at = None
        self.token = None
        self.pending = None
        self.last_step = None
        self._save()
        self.audit.delete_device(self.device_id)
        self.audit.add_event(
            "device_unpaired",
            device_id=self.device_id,
            payload={"pc": previous, "virtual": True},
        )
        return {"status": "unpaired", "device_id": self.device_id}

    def reset(self) -> dict[str, Any]:
        """Borrado de fábrica: id y secreto nuevos, QR nuevo."""

        previous = self.paired_to
        self.audit.delete_device(self.device_id)
        self._regenerate()
        self._save()
        self.audit.add_event(
            "device_reset",
            device_id=self.device_id,
            payload={"previous_pc": previous, "virtual": True},
        )
        return self.info(include_code=True)

    def cancel(self) -> dict[str, Any]:
        """Cancela la confirmación pendiente (botón B del dispositivo)."""

        self.pending = None
        self.attempts = 0
        self.audit.add_event(
            "pair_cancelled", device_id=self.device_id, payload={"virtual": True}
        )
        return {"status": "cancelled", "device_id": self.device_id}

    def panel_token(self) -> dict[str, str]:
        """Token para que el panel simulado abra el WebSocket tras emparejar.

        Solo lo expone la API de desarrollo en loopback. En el hardware real el
        token se queda en NVS y nunca viaja al navegador.
        """

        if self.paired_to is None or not self.token:
            raise VirtualPairingError("not_paired", "el dispositivo no está emparejado")
        return {"device_id": self.device_id, "token": self.token}
