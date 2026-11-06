"""Broker de aprobaciones.

Cada petición tiene identidad propia (``approval_id``), caducidad y un
resultado idempotente. Las reglas que hacen que un mando físico sea seguro
viven aquí, no en la pantalla:

* responder dos veces devuelve el mismo resultado, no una segunda aprobación;
* responder a un id caducado, ya resuelto o ajeno no aprueba nada;
* si el agente deja de esperar, la petición pasa a ``stale``;
* una petición nueva del mismo agente invalida la anterior.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .audit import AuditLog
from .protocol import (
    ApprovalOption,
    ApprovalRequestMessage,
    ApprovalStatus,
    Risk,
)
from .risk import hold_ms_for
from .util import iso, utcnow

DEFAULT_OPTIONS = [
    ApprovalOption(id="allow", label="Permitir", key="A"),
    ApprovalOption(id="deny", label="Denegar", key="B"),
]

_ACCEPT_IDS = {"allow", "yes", "approve", "A"}


class DuplicateApproval(ValueError):
    pass


@dataclass(slots=True)
class Approval:
    approval_id: str
    agent_id: str
    kind: str
    title: str
    command: str
    cwd: str
    risk: Risk
    options: list[ApprovalOption]
    created_at: datetime
    expires_at: datetime
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    option_id: str | None = None
    source: str | None = None
    device_id: str | None = None
    resolved_at: datetime | None = None

    @property
    def hold_ms(self) -> int:
        return hold_ms_for(self.risk)

    @property
    def expired(self) -> bool:
        return utcnow() >= self.expires_at

    def to_message(self) -> ApprovalRequestMessage:
        return ApprovalRequestMessage(
            approval_id=self.approval_id,
            agent_id=self.agent_id,
            kind=self.kind,
            title=self.title,
            command=self.command,
            cwd=self.cwd,
            risk=self.risk,
            expires_at=iso(self.expires_at),
            options=self.options,
            hold_ms=self.hold_ms,
            reasons=self.reasons,
            details=self.details,
        )


@dataclass(slots=True)
class Resolution:
    approval_id: str
    status: str  # accepted | rejected | expired | stale | unknown | invalid_option
    accepted: bool
    option_id: str | None = None
    reason: str = ""
    duplicate: bool = False


class ApprovalBroker:
    def __init__(
        self,
        audit: AuditLog | None = None,
        *,
        timeout_s: float = 60.0,
        history_size: int = 200,
    ) -> None:
        self._audit = audit
        self._timeout_s = timeout_s
        self._pending: dict[str, Approval] = {}
        self._history: deque[Approval] = deque(maxlen=history_size)

    # -- consulta ---------------------------------------------------------

    @property
    def pending(self) -> list[Approval]:
        return list(self._pending.values())

    def get(self, approval_id: str) -> Approval | None:
        found = self._pending.get(approval_id)
        if found:
            return found
        for approval in self._history:
            if approval.approval_id == approval_id:
                return approval
        return None

    def pending_for(self, agent_id: str) -> Approval | None:
        for approval in self._pending.values():
            if approval.agent_id == agent_id:
                return approval
        return None

    # -- creación ---------------------------------------------------------

    def create(
        self,
        *,
        approval_id: str,
        agent_id: str,
        kind: str,
        title: str,
        command: str,
        cwd: str,
        risk: Risk,
        options: list[ApprovalOption] | None = None,
        reasons: list[str] | None = None,
        details: list[str] | None = None,
        ttl_s: float | None = None,
    ) -> Approval:
        if approval_id in self._pending:
            raise DuplicateApproval(approval_id)

        # Una petición nueva del mismo agente deja obsoleta la anterior.
        self.supersede(agent_id, except_id=approval_id)

        now = utcnow()
        approval = Approval(
            approval_id=approval_id,
            agent_id=agent_id,
            kind=kind,
            title=title,
            command=command,
            cwd=cwd,
            risk=risk,
            options=options or list(DEFAULT_OPTIONS),
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_s or self._timeout_s),
            reasons=reasons or [],
            details=details or [],
        )
        self._pending[approval_id] = approval
        if self._audit:
            self._audit.record_approval(
                approval_id=approval_id,
                agent_id=agent_id,
                kind=kind,
                title=title,
                command=command,
                cwd=cwd,
                risk=risk.value,
                created_at=iso(now),
                expires_at=iso(approval.expires_at),
                risk_details=details,
            )
        return approval

    # -- resolución -------------------------------------------------------

    def resolve(
        self,
        approval_id: str,
        option_id: str,
        *,
        source: str = "button",
        device_id: str | None = None,
    ) -> Resolution:
        approval = self._pending.get(approval_id)
        if approval is None:
            return self._resolve_unknown(approval_id)

        if option_id not in {option.id for option in approval.options}:
            return Resolution(
                approval_id=approval_id,
                status="invalid_option",
                accepted=False,
                reason="opción no válida para esta petición",
            )

        if approval.expired:
            self._close(approval, ApprovalStatus.EXPIRED, None, source, device_id)
            return Resolution(
                approval_id=approval_id,
                status="expired",
                accepted=False,
                reason="la petición caducó antes de responder",
            )

        status = (
            ApprovalStatus.ACCEPTED
            if option_id in _ACCEPT_IDS
            else ApprovalStatus.REJECTED
        )
        self._close(approval, status, option_id, source, device_id)
        return Resolution(
            approval_id=approval_id,
            status=status.value,
            accepted=status is ApprovalStatus.ACCEPTED,
            option_id=option_id,
            reason="ok",
        )

    def _resolve_unknown(self, approval_id: str) -> Resolution:
        previous = self.get(approval_id)
        if previous is not None:
            return Resolution(
                approval_id=approval_id,
                status=previous.status.value,
                accepted=previous.status is ApprovalStatus.ACCEPTED,
                option_id=previous.option_id,
                reason=f"ya resuelta como {previous.status.value}",
                duplicate=True,
            )
        return Resolution(
            approval_id=approval_id,
            status="unknown",
            accepted=False,
            reason="approval_id desconocido",
        )

    def supersede(self, agent_id: str, except_id: str | None = None) -> list[Approval]:
        stale: list[Approval] = []
        for approval in list(self._pending.values()):
            if approval.agent_id == agent_id and approval.approval_id != except_id:
                self._close(approval, ApprovalStatus.STALE, None, None, None)
                stale.append(approval)
        return stale

    def expire_due(self, now: datetime | None = None) -> list[Approval]:
        now = now or utcnow()
        expired: list[Approval] = []
        for approval in list(self._pending.values()):
            if now >= approval.expires_at:
                self._close(approval, ApprovalStatus.EXPIRED, None, None, None)
                expired.append(approval)
        return expired

    def _close(
        self,
        approval: Approval,
        status: ApprovalStatus,
        option_id: str | None,
        source: str | None,
        device_id: str | None,
    ) -> None:
        approval.status = status
        approval.option_id = option_id
        approval.source = source
        approval.device_id = device_id
        approval.resolved_at = utcnow()
        self._pending.pop(approval.approval_id, None)
        self._history.append(approval)
        if self._audit:
            self._audit.update_approval(
                approval.approval_id,
                status=status.value,
                option_id=option_id,
                source=source,
                device_id=device_id,
                resolved_at=iso(approval.resolved_at),
            )
