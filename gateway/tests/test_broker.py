import asyncio

import pytest

from baton.audit import AuditLog
from baton.broker import ApprovalBroker
from baton.protocol import Risk


def _create(broker: ApprovalBroker, approval_id: str = "apr_1", **kwargs):
    return broker.create(
        approval_id=approval_id,
        agent_id=kwargs.pop("agent_id", "a1"),
        kind="bash",
        title="Test",
        command=kwargs.pop("command", "npm test"),
        cwd="C:/dev",
        risk=kwargs.pop("risk", Risk.NORMAL),
        **kwargs,
    )


@pytest.fixture
def broker(tmp_path):
    audit = AuditLog(tmp_path / "audit.db")
    yield ApprovalBroker(audit, timeout_s=10.0)
    audit.close()


def test_resolve_is_idempotent(broker):
    _create(broker)
    first = broker.resolve("apr_1", "allow", device_id="baton-1")
    second = broker.resolve("apr_1", "allow", device_id="baton-1")

    assert first.status == "accepted" and first.accepted
    assert second.duplicate and second.status == "accepted"
    assert len(broker.pending) == 0


def test_reject(broker):
    _create(broker, approval_id="apr_2")
    result = broker.resolve("apr_2", "deny")
    assert result.status == "rejected" and not result.accepted


def test_unknown_id_never_approves(broker):
    result = broker.resolve("apr_nope", "allow")
    assert result.status == "unknown"
    assert not result.accepted


def test_invalid_option_keeps_pending(broker):
    _create(broker, approval_id="apr_3")
    result = broker.resolve("apr_3", "rm -rf /")
    assert result.status == "invalid_option"
    assert broker.pending_for("a1") is not None


async def test_expired_cannot_be_approved(broker):
    _create(broker, approval_id="apr_4", ttl_s=0.01)
    await asyncio.sleep(0.03)
    result = broker.resolve("apr_4", "allow")
    assert result.status == "expired"
    assert not result.accepted


async def test_expire_due_closes(broker):
    _create(broker, approval_id="apr_5", ttl_s=0.01)
    await asyncio.sleep(0.03)
    expired = broker.expire_due()
    assert [a.approval_id for a in expired] == ["apr_5"]
    assert broker.get("apr_5").status.value == "expired"


def test_new_request_supersedes_previous(broker):
    _create(broker, approval_id="apr_6", command="npm test")
    _create(broker, approval_id="apr_7", command="rm -rf build", risk=Risk.HIGH)

    assert broker.get("apr_6").status.value == "stale"
    assert broker.pending_for("a1").approval_id == "apr_7"


def test_hold_ms_follows_risk(broker):
    assert _create(broker, approval_id="apr_8", risk=Risk.NORMAL).hold_ms == 0
    assert _create(broker, approval_id="apr_9", risk=Risk.HIGH).hold_ms == 1500
    assert _create(broker, approval_id="apr_10", risk=Risk.CRITICAL).hold_ms == 2500


def test_audit_records_result(tmp_path):
    audit = AuditLog(tmp_path / "audit2.db")
    broker = ApprovalBroker(audit, timeout_s=10.0)
    _create(broker, approval_id="apr_11")
    broker.resolve("apr_11", "deny", device_id="baton-9")

    rows = audit.recent_approvals()
    assert rows[0]["approval_id"] == "apr_11"
    assert rows[0]["status"] == "rejected"
    assert rows[0]["device_id"] == "baton-9"
    audit.close()
