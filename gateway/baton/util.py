from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    """ISO 8601 UTC con milisegundos, terminado en Z."""
    dt = dt or utcnow()
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds_since(value: str) -> float:
    return max(0.0, (utcnow() - parse_iso(value)).total_seconds())
