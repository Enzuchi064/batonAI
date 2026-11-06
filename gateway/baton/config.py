from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _default_db_path() -> Path:
    """En el ejecutable empaquetado, los datos viven en LOCALAPPDATA."""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "batonAI"
        return base / "baton.db"
    return BASE_DIR / "var" / "baton.db"


def _env_str(name: str, default: str) -> str:
    return os.environ.get(f"BATON_{name}", default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(f"BATON_{name}", default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(f"BATON_{name}", default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"BATON_{name}")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """Configuración del gateway. Todo se puede sobreescribir con BATON_*."""

    host: str = "127.0.0.1"
    port: int = 8765
    db_path: Path = field(default_factory=_default_db_path)

    # Aprobaciones
    approval_timeout_s: float = 60.0

    # Protocolo
    heartbeat_s: int = 10
    max_json_bytes: int = 8 * 1024
    max_audio_frame_bytes: int = 4 * 1024

    # UI
    log_tail: int = 5
    log_buffer: int = 50
    rest_after_s: int = 300

    # Desarrollo
    fake_autostart: bool = False
    fake_agents: int = 3
    fake_approvals: bool = False
    dev_mode: bool = True

    # Descubrimiento de agentes locales (OpenCode)
    opencode_enabled: bool = True
    opencode_url: str = ""
    opencode_password: str = ""
    opencode_recency_s: float = 6 * 3600
    opencode_max_sessions: int = 8
    opencode_poll_s: float = 5.0

    # Descubrimiento por archivos y SQLite (Claude Code, Codex, Gemini, ...)
    local_agents_enabled: bool = True
    local_agents_recency_s: float = 12 * 3600
    local_agents_max_sessions: int = 8
    local_agents_poll_s: float = 10.0
    local_agents_active_s: float = 120.0

    # Límites reales de las IAs instaladas
    limits_enabled: bool = True
    limits_poll_s: float = 60.0
    limits_view: str = "remaining"
    opencode_limits_enabled: bool = True
    claude_limits_enabled: bool = True
    codex_usage_enabled: bool = True
    codex_usage_poll_s: float = 120.0

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)
        self.rest_after_s = max(0, min(int(self.rest_after_s), 3600))

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            host=_env_str("HOST", defaults.host),
            port=_env_int("PORT", defaults.port),
            db_path=Path(_env_str("DB_PATH", str(defaults.db_path))),
            approval_timeout_s=_env_float(
                "APPROVAL_TIMEOUT_S", defaults.approval_timeout_s
            ),
            heartbeat_s=_env_int("HEARTBEAT_S", defaults.heartbeat_s),
            max_json_bytes=_env_int("MAX_JSON_BYTES", defaults.max_json_bytes),
            max_audio_frame_bytes=_env_int(
                "MAX_AUDIO_FRAME_BYTES", defaults.max_audio_frame_bytes
            ),
            log_tail=_env_int("LOG_TAIL", defaults.log_tail),
            log_buffer=_env_int("LOG_BUFFER", defaults.log_buffer),
            rest_after_s=_env_int("REST_AFTER_S", defaults.rest_after_s),
            fake_autostart=_env_bool("FAKE_AUTOSTART", defaults.fake_autostart),
            fake_agents=_env_int("FAKE_AGENTS", defaults.fake_agents),
            fake_approvals=_env_bool("FAKE_APPROVALS", defaults.fake_approvals),
            dev_mode=_env_bool("DEV_MODE", defaults.dev_mode),
            opencode_enabled=_env_bool(
                "OPENCODE_ENABLED", defaults.opencode_enabled
            ),
            opencode_url=_env_str("OPENCODE_URL", defaults.opencode_url),
            opencode_password=_env_str(
                "OPENCODE_PASSWORD", defaults.opencode_password
            ),
            opencode_recency_s=_env_float(
                "OPENCODE_RECENCY_S", defaults.opencode_recency_s
            ),
            opencode_max_sessions=_env_int(
                "OPENCODE_MAX_SESSIONS", defaults.opencode_max_sessions
            ),
            opencode_poll_s=_env_float("OPENCODE_POLL_S", defaults.opencode_poll_s),
            local_agents_enabled=_env_bool(
                "LOCAL_AGENTS_ENABLED", defaults.local_agents_enabled
            ),
            local_agents_recency_s=_env_float(
                "LOCAL_AGENTS_RECENCY_S", defaults.local_agents_recency_s
            ),
            local_agents_max_sessions=_env_int(
                "LOCAL_AGENTS_MAX_SESSIONS", defaults.local_agents_max_sessions
            ),
            local_agents_poll_s=_env_float(
                "LOCAL_AGENTS_POLL_S", defaults.local_agents_poll_s
            ),
            local_agents_active_s=_env_float(
                "LOCAL_AGENTS_ACTIVE_S", defaults.local_agents_active_s
            ),
            limits_enabled=_env_bool(
                "LIMITS_ENABLED", defaults.limits_enabled
            ),
            limits_poll_s=_env_float(
                "LIMITS_POLL_S", defaults.limits_poll_s
            ),
            limits_view=_env_str("LIMITS_VIEW", defaults.limits_view),
            opencode_limits_enabled=_env_bool(
                "OPENCODE_LIMITS_ENABLED", defaults.opencode_limits_enabled
            ),
            claude_limits_enabled=_env_bool(
                "CLAUDE_LIMITS_ENABLED", defaults.claude_limits_enabled
            ),
            codex_usage_enabled=_env_bool(
                "CODEX_USAGE_ENABLED", defaults.codex_usage_enabled
            ),
            codex_usage_poll_s=_env_float(
                "CODEX_USAGE_POLL_S", defaults.codex_usage_poll_s
            ),
        )

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
