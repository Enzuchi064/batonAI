"""Estado de los agentes: una sola fuente de verdad, en memoria.

El estado es efímero a propósito. Lo que sobrevive a un reinicio es la
auditoría (SQLite); el estado se reconstruye a partir de los adaptadores.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .protocol import (
    AgentStatus,
    AgentView,
    Risk,
    StateMessage,
    SystemView,
)
from .util import iso, utcnow

_ALLOWED: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.IDLE: frozenset(
        {AgentStatus.RUNNING, AgentStatus.WAITING_INPUT, AgentStatus.ERROR, AgentStatus.OFFLINE}
    ),
    AgentStatus.RUNNING: frozenset(
        {
            AgentStatus.WAITING_INPUT,
            AgentStatus.IDLE,
            AgentStatus.DONE,
            AgentStatus.ERROR,
            AgentStatus.OFFLINE,
        }
    ),
    AgentStatus.WAITING_INPUT: frozenset(
        {AgentStatus.RUNNING, AgentStatus.IDLE, AgentStatus.ERROR, AgentStatus.OFFLINE}
    ),
    AgentStatus.DONE: frozenset({AgentStatus.IDLE, AgentStatus.RUNNING, AgentStatus.OFFLINE}),
    AgentStatus.ERROR: frozenset({AgentStatus.IDLE, AgentStatus.RUNNING, AgentStatus.OFFLINE}),
    AgentStatus.OFFLINE: frozenset(
        {
            AgentStatus.IDLE,
            AgentStatus.RUNNING,
            AgentStatus.WAITING_INPUT,
            AgentStatus.DONE,
            AgentStatus.ERROR,
        }
    ),
}

_PRIORITY: dict[AgentStatus, int] = {
    AgentStatus.WAITING_INPUT: 0,
    AgentStatus.ERROR: 1,
    AgentStatus.RUNNING: 2,
    AgentStatus.DONE: 3,
    AgentStatus.IDLE: 4,
    AgentStatus.OFFLINE: 5,
}


class InvalidTransition(ValueError):
    def __init__(self, agent_id: str, current: AgentStatus, target: AgentStatus) -> None:
        super().__init__(f"{agent_id}: transición no válida {current.value} -> {target.value}")
        self.agent_id = agent_id
        self.current = current
        self.target = target


@dataclass(slots=True)
class AgentRuntime:
    id: str
    name: str
    provider: str = "unknown"
    model: str = "unknown"
    status: AgentStatus = AgentStatus.OFFLINE
    since: str = field(default_factory=iso)
    last_event_at: str = field(default_factory=iso)
    cwd: str = ""
    task: str = ""
    logs: deque[str] = field(default_factory=deque)
    cost_turn: float = 0.0
    cost_session: float = 0.0
    tokens_session: int = 0
    approval_id: str | None = None
    prompt: str | None = None
    risk: Risk | None = None
    risk_reasons: list[str] = field(default_factory=list)
    risk_details: list[str] = field(default_factory=list)

    def view(self, log_tail: int) -> AgentView:
        tail = list(self.logs)[-log_tail:] if log_tail > 0 else []
        return AgentView(
            id=self.id,
            name=self.name,
            provider=self.provider,
            model=self.model,
            status=self.status,
            since=self.since,
            last_event_at=self.last_event_at,
            cwd=self.cwd,
            task=self.task,
            log_tail=tail,
            cost_turn=round(self.cost_turn, 4),
            cost_session=round(self.cost_session, 4),
            tokens_session=self.tokens_session,
            approval_id=self.approval_id,
            prompt=self.prompt,
            risk=self.risk,
            risk_reasons=list(self.risk_reasons),
            risk_details=list(self.risk_details),
        )


class StateStore:
    def __init__(self, log_buffer: int = 50, log_tail: int = 5) -> None:
        self._agents: dict[str, AgentRuntime] = {}
        self._log_buffer = log_buffer
        self._log_tail = log_tail
        self._seq = 0

    # -- registro ---------------------------------------------------------

    def register(
        self,
        agent_id: str,
        name: str,
        provider: str = "unknown",
        model: str = "unknown",
        cwd: str = "",
    ) -> AgentRuntime:
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            agent.name = name
            agent.provider = provider
            agent.model = model
            if cwd:
                agent.cwd = cwd
            return agent
        agent = AgentRuntime(
            id=agent_id,
            name=name,
            provider=provider,
            model=model,
            cwd=cwd,
            logs=deque(maxlen=self._log_buffer),
        )
        self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> AgentRuntime:
        return self._agents[agent_id]

    def maybe_get(self, agent_id: str) -> AgentRuntime | None:
        return self._agents.get(agent_id)

    def remove(self, agent_id: str) -> bool:
        """Retira un agente del estado (por ejemplo, una sesión ya cerrada)."""
        return self._agents.pop(agent_id, None) is not None

    @property
    def agents(self) -> list[AgentRuntime]:
        return list(self._agents.values())

    # -- mutaciones -------------------------------------------------------

    def set_status(
        self,
        agent_id: str,
        status: AgentStatus,
        *,
        task: str | None = None,
        reason: str | None = None,
        allow_same: bool = True,
    ) -> AgentRuntime:
        agent = self.get(agent_id)
        if status is not agent.status:
            if status not in _ALLOWED[agent.status]:
                raise InvalidTransition(agent_id, agent.status, status)
            agent.status = status
            agent.since = iso()
            if status is not AgentStatus.WAITING_INPUT:
                agent.approval_id = None
                agent.prompt = None
                agent.risk = None
        elif not allow_same:
            raise InvalidTransition(agent_id, agent.status, status)
        if task is not None:
            agent.task = task
        agent.last_event_at = iso()
        return agent

    def log(self, agent_id: str, line: str) -> None:
        agent = self.get(agent_id)
        agent.logs.append(line)
        agent.last_event_at = iso()

    def set_usage(
        self,
        agent_id: str,
        *,
        cost_turn: float | None = None,
        cost_session: float | None = None,
        tokens_session: int | None = None,
    ) -> None:
        agent = self.get(agent_id)
        if cost_turn is not None:
            agent.cost_turn = cost_turn
        if cost_session is not None:
            agent.cost_session = cost_session
        if tokens_session is not None:
            agent.tokens_session = tokens_session
        agent.last_event_at = iso()

    def set_task(self, agent_id: str, task: str) -> None:
        """Actualiza lo que se muestra como tarea sin tocar el estado."""
        agent = self.get(agent_id)
        if agent.task != task:
            agent.task = task
            agent.last_event_at = iso()

    def attach_approval(
        self,
        agent_id: str,
        approval_id: str,
        prompt: str,
        risk: Risk,
        reasons: list[str] | None = None,
        details: list[str] | None = None,
    ) -> None:
        agent = self.get(agent_id)
        agent.approval_id = approval_id
        agent.prompt = prompt
        agent.risk = risk
        agent.risk_reasons = list(reasons or [])
        agent.risk_details = list(details or [])
        agent.last_event_at = iso()

    def clear_approval(
        self, agent_id: str, next_status: AgentStatus | None = None
    ) -> None:
        """Una aprobación pendiente es la razón de WAITING_INPUT.

        Si se retira sin decir a qué estado va el agente, el estado deja de ser
        creíble: pasamos a IDLE en lugar de mostrar una espera fantasma.
        """
        agent = self.get(agent_id)
        agent.approval_id = None
        agent.prompt = None
        agent.risk = None
        agent.risk_reasons = []
        agent.risk_details = []
        if next_status is not None:
            self.set_status(agent_id, next_status)
        elif agent.status is AgentStatus.WAITING_INPUT:
            self.set_status(agent_id, AgentStatus.IDLE)
        agent.last_event_at = iso()

    def mark_offline(self) -> None:
        for agent in self._agents.values():
            if agent.status is not AgentStatus.OFFLINE:
                self.set_status(agent.id, AgentStatus.OFFLINE)

    # -- vista ------------------------------------------------------------

    def snapshot(self) -> StateMessage:
        self._seq += 1
        agents = sorted(
            self._agents.values(),
            key=lambda a: (_PRIORITY[a.status], a.since),
        )
        views = [agent.view(self._log_tail) for agent in agents]
        system = SystemView(
            total_cost=round(sum(a.cost_session for a in agents), 4),
            total_tokens=sum(a.tokens_session for a in agents),
            active_agents=sum(
                1
                for a in agents
                if a.status in (AgentStatus.RUNNING, AgentStatus.WAITING_INPUT)
            ),
            waiting_agents=sum(1 for a in agents if a.status is AgentStatus.WAITING_INPUT),
        )
        return StateMessage(seq=self._seq, ts=iso(utcnow()), system=system, agents=views)
