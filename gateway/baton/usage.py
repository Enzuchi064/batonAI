"""Contabilidad de tokens por agente y periodo.

El estado solo guarda los tokens de la sesión actual. Para poder mostrar
límites diarios, semanales y mensuales hay que acumular los incrementos en
buckets diarios y recordar el último valor visto por agente.

Si el gateway se reinicia, ``agent_usage_state`` evita volver a contar toda la
sesión. Si una sesión se reinicia (los tokens bajan), se toma el nuevo valor como
base y se cuenta a partir de ahí.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta

from .audit import AuditLog

PERIODS = ("daily", "weekly", "monthly")


def period_start(period: str, today: date | None = None) -> str:
    current = today or date.today()
    if period == "weekly":
        current = current - timedelta(days=current.weekday())
    elif period == "monthly":
        current = current.replace(day=1)
    return current.isoformat()


class UsageTracker:
    def __init__(self, audit: AuditLog) -> None:
        self.audit = audit
        self._last = audit.usage_state()
        self._lock = threading.Lock()

    def record(self, agent_id: str, tokens_session: int | None) -> None:
        if tokens_session is None:
            return
        tokens = max(0, int(tokens_session))

        with self._lock:
            previous = self._last.get(agent_id)
            if previous is None or tokens < previous:
                delta = tokens
            else:
                delta = tokens - previous
            self._last[agent_id] = tokens
            self.audit.set_usage_state(agent_id, tokens)
            if delta > 0:
                self.audit.add_agent_usage(
                    agent_id, date.today().isoformat(), delta
                )

    def used(self, agent_id: str, period: str) -> int:
        return self.audit.agent_usage_since(agent_id, period_start(period))
