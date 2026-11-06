"""Protocolo v1 entre el dispositivo batonAI y el gateway.

Todos los mensajes son JSON con un campo ``type`` que actúa de discriminador.
El dispositivo solo entiende: estado, petición de aprobación, resultado,
transcripción, ack, error y pong.

Reglas de diseño:

* ``approval_id`` identifica cada petición. Una respuesta a un id caducado,
  resuelto o desconocido nunca aprueba nada.
* ``seq`` es monótono por sesión; el dispositivo descarta estados viejos.
* El riesgo y el tiempo de espera viajan en la petición: el dispositivo no
  decide cuánto hay que mantener pulsado, solo lo ejecuta.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTO_VERSION = 1


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    DONE = "DONE"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class Risk(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"


# --------------------------------------------------------------------------
# Entrante: dispositivo -> gateway
# --------------------------------------------------------------------------


class _Inbound(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hello(_Inbound):
    type: Literal["hello"]
    proto: int = PROTO_VERSION
    device_id: str = Field(min_length=1, max_length=64)
    fw: str = Field(default="unknown", max_length=32)
    token: str = Field(min_length=8, max_length=256)


class ApprovalResponse(_Inbound):
    type: Literal["approval_response"]
    approval_id: str = Field(min_length=1, max_length=128)
    option_id: str = Field(min_length=1, max_length=32)
    source: Literal["button", "voice"] = "button"
    transcript: str | None = Field(default=None, max_length=2000)


class InterruptRequest(_Inbound):
    type: Literal["interrupt"]
    agent_id: str = Field(min_length=1, max_length=64)


class InjectText(_Inbound):
    type: Literal["inject_text"]
    agent_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=2000)
    confirm: bool = False


class Ping(_Inbound):
    type: Literal["ping"]
    seq: int = 0


class AudioStart(_Inbound):
    type: Literal["audio_start"]
    agent_id: str = Field(min_length=1, max_length=64)
    sample_rate: int = 16000
    format: str = "s16le"
    channels: int = 1


class AudioEnd(_Inbound):
    type: Literal["audio_end"]
    seq: int = 0
    duration_ms: int = 0


ClientMessage = Annotated[
    Union[
        Hello,
        ApprovalResponse,
        InterruptRequest,
        InjectText,
        Ping,
        AudioStart,
        AudioEnd,
    ],
    Field(discriminator="type"),
]

CLIENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMessage:
    return CLIENT_ADAPTER.validate_json(raw)


# --------------------------------------------------------------------------
# Saliente: gateway -> dispositivo
# --------------------------------------------------------------------------


class _Outbound(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentView(_Outbound):
    id: str
    name: str
    provider: str = "unknown"
    model: str = "unknown"
    status: AgentStatus
    since: str
    last_event_at: str
    cwd: str = ""
    task: str = ""
    log_tail: list[str] = Field(default_factory=list)
    cost_turn: float = 0.0
    cost_session: float = 0.0
    tokens_session: int = 0
    approval_id: str | None = None
    prompt: str | None = None
    risk: Risk | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    risk_details: list[str] = Field(default_factory=list)


class SystemView(_Outbound):
    total_cost: float = 0.0
    total_tokens: int = 0
    active_agents: int = 0
    waiting_agents: int = 0


class Welcome(_Outbound):
    type: Literal["welcome"] = "welcome"
    proto: int = PROTO_VERSION
    session_id: str
    server_time: str
    device_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class StateMessage(_Outbound):
    type: Literal["state"] = "state"
    seq: int
    ts: str
    system: SystemView
    agents: list[AgentView]


class VisibilityMessage(_Outbound):
    type: Literal["visibility"] = "visibility"
    hidden_agents: list[str] = Field(default_factory=list)
    ts: str


class PinnedMessage(_Outbound):
    type: Literal["pinned"] = "pinned"
    pinned_agents: list[str] = Field(default_factory=list)
    ts: str


class ApprovalOption(_Outbound):
    id: str
    label: str
    key: str


class ApprovalRequestMessage(_Outbound):
    type: Literal["approval_request"] = "approval_request"
    approval_id: str
    agent_id: str
    kind: str
    title: str
    command: str
    cwd: str
    risk: Risk
    expires_at: str
    options: list[ApprovalOption]
    hold_ms: int = 0
    reasons: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class ApprovalResultMessage(_Outbound):
    type: Literal["approval_result"] = "approval_result"
    approval_id: str
    status: str
    accepted: bool
    option_id: str | None = None
    reason: str = ""
    duplicate: bool = False


class AckMessage(_Outbound):
    type: Literal["ack"] = "ack"
    ref: str
    ok: bool = True
    detail: str = ""


class ErrorMessage(_Outbound):
    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False


class PongMessage(_Outbound):
    type: Literal["pong"] = "pong"
    seq: int = 0


class TranscriptMessage(_Outbound):
    type: Literal["transcript"] = "transcript"
    text: str
    language: str = "es"
    confidence: float = 0.0
    final: bool = True


def dump(message: BaseModel) -> dict[str, Any]:
    return message.model_dump(mode="json", exclude_none=True)
