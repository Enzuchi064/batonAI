"""Agente falso para la Fase A.

No habla con ningún LLM: reproduce un guion verosímil (trabaja, pide permiso,
termina, vuelve a idle) para poder validar todo el flujo sin hardware ni
credenciales. Implementa la misma interfaz que los adaptadores reales.
"""

from __future__ import annotations

import asyncio
import secrets

from ..protocol import AgentStatus, Risk
from ..risk import classify
from .base import AgentAdapter, AgentEvent, EventKind, Sink

TASKS = [
    "Refactorizar el middleware de autenticación",
    "Añadir tests para el parser de configuración",
    "Revisar el manejo de errores del endpoint /login",
    "Migrar el cliente HTTP a la nueva API",
]

LOG_LINES = [
    "→ leyendo src/auth/middleware.py",
    "→ aplicando cambios en 3 archivos",
    "→ ejecutando linter",
    "→ 14 tests en verde",
]

SCENARIOS = [
    {
        "kind": "bash",
        "title": "Ejecutar la suite de tests",
        "command": "npm run test -- --coverage",
        "after_allow": "✓ tests completados: 42 pasan, 0 fallan",
        "after_deny": "✗ tests omitidos a petición del usuario",
    },
    {
        "kind": "bash",
        "title": "Limpiar artefactos de build",
        "command": "rm -rf build/ dist/ .cache/",
        "after_allow": "✓ artefactos eliminados",
        "after_deny": "✗ limpieza cancelada",
    },
    {
        "kind": "bash",
        "title": "Publicar cambios en remoto",
        "command": "git push --force origin main",
        "after_allow": "✓ push completado",
        "after_deny": "✗ push cancelado",
    },
]

APPROVAL_WAIT_S = 90.0


def scenario_for_risk(risk: str) -> dict:
    """Elige un escenario cuyo riesgo real (clasificado) coincida."""
    wanted = Risk(risk)
    for scenario in SCENARIOS:
        if classify(scenario["command"], scenario["kind"]).risk is wanted:
            return scenario
    return SCENARIOS[0] if wanted in (Risk.LOW, Risk.NORMAL) else SCENARIOS[1]


class FakeAgentAdapter(AgentAdapter):
    id = "claude-code"
    name = "Claude Code"
    provider = "anthropic"
    model = "claude-sonnet-4-5"

    def __init__(
        self,
        *,
        agent_id: str = "claude-code",
        name: str = "Claude Code",
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-5",
        cwd: str = r"C:\dev\baton-demo",
        idle_delay: float = 8.0,
        task_offset: int = 0,
        auto_approvals: bool = False,
    ) -> None:
        self.id = agent_id
        self.name = name
        self.provider = provider
        self.model = model
        self.cwd = cwd
        self._idle_delay = idle_delay
        self._task_offset = task_offset
        self._auto_approvals = auto_approvals
        self._sink: Sink | None = None
        self._control: asyncio.Queue[dict | None] = asyncio.Queue()
        self._runner: asyncio.Task | None = None
        self._current: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._decision: asyncio.Event | None = None
        self._decision_value: str | None = None
        self._approval_id: str | None = None
        self._interrupting = False
        self._force_queued = False
        self._cycle_n = 0
        self._spent = 0.0
        self._tokens = 0

    # -- ciclo de vida ----------------------------------------------------

    async def start(self, sink: Sink) -> None:
        self._sink = sink
        self._runner = asyncio.create_task(self._run(), name="fake-agent")

    async def stop(self) -> None:
        self._stop.set()
        if self._current and not self._current.done():
            self._current.cancel()
        self._control.put_nowait(None)
        if self._runner:
            try:
                await asyncio.wait_for(self._runner, timeout=3.0)
            except (asyncio.TimeoutError, TimeoutError):
                self._runner.cancel()
            except asyncio.CancelledError:
                pass

    # -- bucle principal --------------------------------------------------

    async def _run(self) -> None:
        await self._status(AgentStatus.IDLE, task="")
        while not self._stop.is_set():
            command = await self._next_command()
            if command is None or self._stop.is_set():
                break
            self._current = asyncio.create_task(self._run_command(command))
            try:
                await self._current
            except asyncio.CancelledError:
                if self._stop.is_set():
                    break
                if self._interrupting:
                    await self._emit(EventKind.LOG, line="⏹ interrumpido desde el dispositivo")
                    await self._status(AgentStatus.IDLE, task="")
            except Exception as exc:  # un adaptador roto no debe tumbar el gateway
                await self._emit(EventKind.ERROR, message=f"{type(exc).__name__}: {exc}")
            finally:
                self._interrupting = False
                self._current = None

    async def _next_command(self) -> dict | None:
        try:
            return await asyncio.wait_for(self._control.get(), timeout=self._idle_delay)
        except (asyncio.TimeoutError, TimeoutError):
            return {"kind": "cycle"}

    async def _run_command(self, command: dict) -> None:
        kind = command.get("kind")
        if kind == "cycle":
            await self._cycle()
        elif kind == "approval":
            self._force_queued = False
            await self._forced_approval(command.get("risk", Risk.NORMAL.value))

    # -- guion ------------------------------------------------------------

    async def _cycle(self) -> None:
        self._cycle_n += 1
        offset = self._cycle_n - 1 + self._task_offset
        task = TASKS[offset % len(TASKS)]
        await self._status(AgentStatus.RUNNING, task=task)

        for line in LOG_LINES:
            await asyncio.sleep(1.0)
            await self._emit(EventKind.LOG, line=line)

        self._spent += 0.031
        self._tokens += 1840
        await self._emit(
            EventKind.USAGE,
            cost_turn=0.031,
            cost_session=round(self._spent, 4),
            tokens_session=self._tokens,
        )

        scenario = SCENARIOS[offset % len(SCENARIOS)]

        # Por defecto no pide permiso solo: en el banco de pruebas la hoja
        # taparía la UI. Se fuerza desde «simular permiso».
        if self._auto_approvals and (self._cycle_n + self._task_offset) % 2 == 1:
            decision = await self._request(scenario)
            if decision == "allow":
                await self._emit(EventKind.LOG, line=scenario["after_allow"])
                await asyncio.sleep(0.8)
                await self._status(AgentStatus.DONE, task=task)
                await asyncio.sleep(1.6)
                await self._status(AgentStatus.IDLE, task="")
            else:
                await self._emit(EventKind.LOG, line=scenario["after_deny"])
                await self._status(AgentStatus.IDLE, task="")
        else:
            await self._emit(EventKind.LOG, line="✓ turno completado sin permisos")
            await self._status(AgentStatus.DONE, task=task)
            await asyncio.sleep(1.4)
            await self._status(AgentStatus.IDLE, task="")

    async def _forced_approval(self, risk: str) -> None:
        scenario = scenario_for_risk(risk)
        await self._status(AgentStatus.RUNNING, task="Revisión solicitada desde el panel")
        await asyncio.sleep(0.4)
        decision = await self._request(scenario)
        await self._emit(
            EventKind.LOG,
            line=scenario["after_allow"] if decision == "allow" else scenario["after_deny"],
        )
        await self._status(AgentStatus.IDLE, task="")

    async def _request(self, scenario: dict) -> str:
        assessment = classify(scenario["command"], scenario["kind"])
        risk = assessment.risk

        self._approval_id = f"apr_{secrets.token_hex(6)}"
        self._decision = asyncio.Event()
        self._decision_value = None

        await self._status(AgentStatus.WAITING_INPUT, task=scenario["title"])
        await self._emit(
            EventKind.APPROVAL,
            approval_id=self._approval_id,
            kind=scenario["kind"],
            title=scenario["title"],
            command=scenario["command"],
            cwd=self.cwd,
            risk=risk.value,
            reasons=assessment.reasons,
            details=assessment.details,
        )

        try:
            await asyncio.wait_for(self._decision.wait(), timeout=APPROVAL_WAIT_S)
        except (asyncio.TimeoutError, TimeoutError):
            self._decision_value = "expire"

        value = self._decision_value or "expire"
        self._approval_id = None
        self._decision = None
        return value

    # -- acciones desde el gateway ---------------------------------------

    async def respond(self, approval_id: str, option_id: str) -> None:
        if approval_id != self._approval_id or self._decision is None:
            return
        self._decision_value = option_id
        self._decision.set()

    async def notify_expired(self, approval_id: str) -> None:
        if approval_id != self._approval_id or self._decision is None:
            return
        self._decision_value = "expire"
        self._decision.set()

    async def send_text(self, text: str) -> None:
        await self._emit(EventKind.LOG, line=f"⌨ {text}")
        await self._emit(EventKind.LOG, line=f"↳ recibido: {text}")

    async def interrupt(self) -> None:
        if self._current and not self._current.done():
            self._interrupting = True
            self._current.cancel()

    # -- utilidades -------------------------------------------------------

    def force_approval(self, risk: str = Risk.NORMAL.value) -> bool:
        # No encolar dos peticiones seguidas: la hoja se quedaría abierta
        # detrás de la siguiente y parecería que no se puede cerrar.
        if self._force_queued or self._approval_id is not None:
            return False
        self._force_queued = True
        self._control.put_nowait({"kind": "approval", "risk": risk})
        return True

    async def _status(self, status: AgentStatus, **payload) -> None:
        await self._emit(EventKind.STATUS, status=status.value, **payload)

    async def _emit(self, event_kind: EventKind, **payload) -> None:
        if self._sink is None:
            return
        await self._sink(AgentEvent(kind=event_kind, agent_id=self.id, payload=payload))
