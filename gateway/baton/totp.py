"""TOTP mínimo (RFC 6238) sin dependencias externas.

Se usa para el emparejamiento del hardware: el dispositivo genera un secreto,
lo pinta en un QR ``otpauth://`` y verifica el código de 6 dígitos que el
usuario introduce en la app. El gateway también lo usa para el dispositivo
virtual de desarrollo.

No guarda secretos ni los registra. Solo calcula y compara.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DEFAULT_DIGITS = 6
DEFAULT_PERIOD = 30
DEFAULT_WINDOW = 1


def generate_secret(length: int = 20) -> str:
    """Secreto aleatorio en base32 sin relleno (160 bits por defecto)."""

    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def normalize_secret(secret: str) -> str:
    """Acepta secretos con espacios, minúsculas o relleno."""

    cleaned = "".join(secret.split()).upper().rstrip("=")
    if not cleaned:
        raise ValueError("empty_secret")
    padding = "=" * (-len(cleaned) % 8)
    # Valida el alfabeto base32 antes de decodificar.
    base64.b32decode(cleaned + padding, casefold=True)
    return cleaned


def _decode_secret(secret: str) -> bytes:
    normalized = normalize_secret(secret)
    padding = "=" * (-len(normalized) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def hotp(secret: str, counter: int, *, digits: int = DEFAULT_DIGITS) -> str:
    """HOTP (RFC 4226) con HMAC-SHA1."""

    if counter < 0:
        raise ValueError("negative_counter")
    key = _decode_secret(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    return str(code % (10**digits)).zfill(digits)


def time_step(at: float | None = None, period: int = DEFAULT_PERIOD) -> int:
    return int((time.time() if at is None else at) // period)


def totp(
    secret: str,
    at: float | None = None,
    *,
    digits: int = DEFAULT_DIGITS,
    period: int = DEFAULT_PERIOD,
) -> str:
    return hotp(secret, time_step(at, period), digits=digits)


def verify(
    secret: str,
    code: str,
    at: float | None = None,
    *,
    digits: int = DEFAULT_DIGITS,
    period: int = DEFAULT_PERIOD,
    window: int = DEFAULT_WINDOW,
) -> int | None:
    """Devuelve el ``step`` aceptado o ``None``.

    La ventana es simétrica: ``window=1`` acepta el paso anterior, el actual y
    el siguiente (±30 s con periodo de 30 s). La comparación es en tiempo
    constante para no filtrar información por temporización.
    """

    candidate = "".join(str(code).split())
    if len(candidate) != digits or not candidate.isdigit():
        return None

    current = time_step(at, period)
    matched: int | None = None
    for offset in range(-window, window + 1):
        step = current + offset
        if step < 0:
            continue
        expected = hotp(secret, step, digits=digits)
        if hmac.compare_digest(candidate, expected):
            matched = step
    return matched


def otpauth_uri(
    secret: str,
    label: str,
    *,
    issuer: str = "batonAI",
    digits: int = DEFAULT_DIGITS,
    period: int = DEFAULT_PERIOD,
) -> str:
    """URI estándar que entienden Google Authenticator y compatibles."""

    account = f"{issuer}:{label}"
    query = (
        f"secret={normalize_secret(secret)}"
        f"&issuer={quote(issuer)}"
        f"&algorithm=SHA1"
        f"&digits={digits}"
        f"&period={period}"
    )
    return f"otpauth://totp/{quote(account, safe='')}?{query}"
