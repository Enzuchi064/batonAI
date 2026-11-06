from baton.audit import AuditLog
from baton.usage import UsageTracker


def test_audit_stores_and_reads_risk_details(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.record_approval(
        approval_id="apr_1",
        agent_id="opencode:ses_1",
        kind="bash",
        title="Limpiar build",
        command="git clean -fdx",
        cwd="C:\\dev\\baton",
        risk="high",
        created_at="2026-11-06T10:00:00Z",
        expires_at="2026-11-06T10:01:00Z",
        risk_details=["Borra archivos que no están en Git."],
    )

    rows = log.recent_approvals(1)
    assert rows[0]["risk_details"] == [
        "Borra archivos que no están en Git."
    ]
    log.close()


def test_usage_tracker_accumulates_and_survives_restart(tmp_path):
    path = tmp_path / "usage.db"
    log = AuditLog(path)
    tracker = UsageTracker(log)

    tracker.record("agent-1", 100)
    tracker.record("agent-1", 150)
    tracker.record("agent-1", 120)  # reinicio de sesión
    tracker.record("agent-1", 200)

    assert tracker.used("agent-1", "daily") == 350
    log.close()

    log = AuditLog(path)
    tracker = UsageTracker(log)
    tracker.record("agent-1", 250)
    assert tracker.used("agent-1", "daily") == 400
    log.close()


def test_period_start_uses_week_and_month():
    from datetime import date

    from baton.usage import period_start

    day = date(2026, 11, 6)  # viernes
    assert period_start("daily", day) == "2026-11-06"
    assert period_start("weekly", day) == "2026-11-02"
    assert period_start("monthly", day) == "2026-11-01"
