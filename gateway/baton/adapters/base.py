"""Interfaz común de adaptadores de agente.

Un adaptador traduce entre el mundo de un agente concreto (hooks de Claude
Code, servidor de OpenCode, PTY de último recurso) y eventos normalizados.
El resto del gateway no sabe qué agente hay detrás.

Contrato:

* ``start(sink)`` arranca el adaptador y emite eventos por ``sink``.
* ``respond`` entrega la decisión de una aprobación concreta.
* ``notify_expired`` avisa de que la petición caducó: el adaptador debe
  dejar que el prompt nativo siga en el PC, nunca auto-aprobar.
* ``send_text`` inyecta texto ya confirmado por el usuario.
* ``interrupt`` detiene el trabajo en curso del agente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class EventKind(str, Enum):
    STATUS = "status"
    LOG = "log"
    APPROVAL = "approval"
    USAGE = "usage"
    ERROR = "error"


@dataclass(slots=True)
class AgentEvent:
    kind: EventKind
    agent_id: str
    payload: dict[str, Any] = field(default_factory=dict)


Sink = Callable[[AgentEvent], Awaitable[None]]


class AgentAdapter(ABC):
    id: str
    name: str
    provider: str = "unknown"
    model: str = "unknown"
    cwd: str = ""

    @abstractmethod
    async def start(self, sink: Sink) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def respond(self, approval_id: str, option_id: str) -> None: ...

    async def notify_expired(self, approval_id: str) -> None:
        """Por defecto, no hacer nada: el prompt nativo sigue esperando."""

    @abstractmethod
    async def send_text(self, text: str) -> None: ...

    @abstractmethod
    async def interrupt(self) -> None: ...
