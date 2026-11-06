import base64
import json
import sqlite3

from baton.audit import AuditLog
from baton.config import Settings
from baton.discovery import (
    DetectedSession,
    OpenCodeDiscovery,
    _tabs_from_db,
    agent_id_for,
    map_session,
    opencode_output,
    select_sessions,
    token_total,
)
from baton.protocol import AgentStatus
from baton.state import StateStore

NOW = 1_000_000_000_000
RECENCY = 60 * 60 * 1000


def session_payload(**overrides):
    payload = {
        "id": "ses_abc123",
        "title": "Refactor del parser",
        "model": {"id": "deepseek-v4.1-flash", "providerID": "opencode-go"},
        "cost": 0.42,
        "tokens": {
            "input": 120,
            "output": 30,
            "reasoning": 10,
            "cache": {"read": 999999, "write": 0},
        },
        "location": {"directory": r"C:\dev\baton"},
        "time": {
            "created": NOW - 90_000,
            "updated": NOW - 1_000,
            "busy": NOW - 500,
            "idle": NOW - 2_000,
        },
    }
    payload.update(overrides)
    return payload


def test_map_session_maps_fields():
    mapped = map_session(session_payload(), now_ms=NOW, recency_ms=RECENCY)

    assert mapped is not None
    assert mapped.session_id == "ses_abc123"
    assert mapped.agent_id == "opencode:ses_abc123"
    assert mapped.name == "Refactor del parser"
    assert mapped.model == "deepseek-v4.1-flash"
    assert mapped.cwd == r"C:\dev\baton"
    assert mapped.cost == 0.42
    assert mapped.tokens == 160
    assert mapped.status is AgentStatus.RUNNING


def test_map_session_skips_old_or_incomplete():
    old = session_payload(time={"updated": NOW - RECENCY - 1})
    assert map_session(old, now_ms=NOW, recency_ms=RECENCY) is None
    assert map_session({"title": "sin id"}, now_ms=NOW, recency_ms=RECENCY) is None
    assert map_session(
        {"id": "ses_x"}, now_ms=NOW, recency_ms=RECENCY
    ) is None


def test_status_follows_busy_and_idle():
    idle = map_session(
        session_payload(time={"updated": NOW, "busy": NOW - 5_000, "idle": NOW - 1_000}),
        now_ms=NOW,
        recency_ms=RECENCY,
    )
    assert idle is not None
    assert idle.status is AgentStatus.IDLE

    busy = map_session(
        session_payload(time={"updated": NOW, "busy": NOW - 1_000, "idle": NOW - 5_000}),
        now_ms=NOW,
        recency_ms=RECENCY,
    )
    assert busy is not None
    assert busy.status is AgentStatus.RUNNING


def test_model_as_string_and_fallback_name():
    mapped = map_session(
        {
            "id": "ses_zzzzzz",
            "model": "gpt-5-codex",
            "time": {"updated": NOW, "busy": 2, "idle": 1},
            "tokens": None,
        },
        now_ms=NOW,
        recency_ms=RECENCY,
    )
    assert mapped is not None
    assert mapped.model == "gpt-5-codex"
    assert mapped.name == "OpenCode zzzzzz"
    assert mapped.tokens == 0
    assert mapped.cwd == ""
    assert mapped.cost == 0.0


def test_token_total_ignores_cache():
    assert token_total({"input": 3, "output": 4, "reasoning": 5}) == 12
    assert token_total({"input": 3, "cache": {"read": 1000}}) == 3
    assert token_total(None) == 0


def test_select_sessions_sorts_and_limits():
    payload = {
        "data": [
            session_payload(id="ses_old", time={"updated": NOW - 50_000}),
            session_payload(id="ses_new", time={"updated": NOW - 1_000}),
            session_payload(id="ses_mid", time={"updated": NOW - 10_000}),
            {"id": "ses_ancient", "time": {"updated": NOW - RECENCY - 1}},
        ],
        "cursor": "next",
    }

    selected = select_sessions(
        payload, now_ms=NOW, recency_ms=RECENCY, limit=2
    )
    assert [session.session_id for session in selected] == ["ses_new", "ses_mid"]


def test_agent_id_prefix():
    assert agent_id_for("ses_abc") == "opencode:ses_abc"


def test_headers_use_basic_auth():
    settings = Settings(opencode_password="secreto")
    discovery = OpenCodeDiscovery(settings, StateStore(), None, lambda: None)  # type: ignore[arg-type]

    header = discovery._headers()["Authorization"]
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
    assert decoded == "opencode:secreto"


def test_sync_adds_updates_and_removes(tmp_path):
    settings = Settings(db_path=tmp_path / "discovery.db")
    audit = AuditLog(settings.db_path)
    store = StateStore()
    notifications: list[int] = []
    discovery = OpenCodeDiscovery(
        settings, store, audit, lambda: notifications.append(1)
    )

    alpha = DetectedSession(
        session_id="ses_a",
        name="Alpha",
        model="model-a",
        cwd=r"C:\dev\a",
        updated_ms=NOW,
        busy_ms=2,
        idle_ms=1,
        cost=0.1,
        tokens=10,
    )
    beta = DetectedSession(
        session_id="ses_b",
        name="Beta",
        model="model-b",
        cwd=r"C:\dev\b",
        updated_ms=NOW,
        busy_ms=1,
        idle_ms=2,
        cost=0.2,
        tokens=20,
    )

    try:
        discovery._sync([alpha])
        agent = store.get("opencode:ses_a")
        assert agent.status is AgentStatus.RUNNING
        assert agent.provider == "opencode"
        assert agent.cost_session == 0.1
        assert agent.tokens_session == 10
        assert notifications

        discovery._sync([beta])
        assert store.maybe_get("opencode:ses_a") is None
        agent = store.get("opencode:ses_b")
        assert agent.status is AgentStatus.IDLE
        assert agent.name == "Beta"

        updated_alpha = DetectedSession(
            session_id="ses_a",
            name="Alpha v2",
            model="model-a2",
            cwd=r"C:\dev\a",
            updated_ms=NOW + 1,
            busy_ms=1,
            idle_ms=2,
            cost=0.3,
            tokens=30,
        )
        discovery._sync([updated_alpha])
        agent = store.get("opencode:ses_a")
        assert agent.name == "Alpha v2"
        assert agent.model == "model-a2"
        assert agent.status is AgentStatus.IDLE
    finally:
        audit.close()


def test_sync_leaves_other_adapters_alone(tmp_path):
    settings = Settings(db_path=tmp_path / "others.db")
    audit = AuditLog(settings.db_path)
    store = StateStore()
    store.register("claude-code", "Agente falso", "anthropic", "claude-sonnet-4-5")
    discovery = OpenCodeDiscovery(settings, store, audit, lambda: None)

    session = DetectedSession(
        session_id="ses_tmp",
        name="Temporal",
        model="model",
        cwd="",
        updated_ms=NOW,
        busy_ms=1,
        idle_ms=2,
        cost=0.0,
        tokens=0,
    )

    try:
        discovery._sync([session])
        assert store.maybe_get("opencode:ses_tmp") is not None

        discovery._sync([])
        assert store.maybe_get("opencode:ses_tmp") is None
        assert store.maybe_get("claude-code") is not None
    finally:
        audit.close()


def test_mark_offline_after_failures(tmp_path):
    settings = Settings(db_path=tmp_path / "offline.db")
    audit = AuditLog(settings.db_path)
    store = StateStore()
    notifications: list[int] = []
    discovery = OpenCodeDiscovery(
        settings, store, audit, lambda: notifications.append(1)
    )

    session = DetectedSession(
        session_id="ses_off",
        name="Offline",
        model="model",
        cwd="",
        updated_ms=NOW,
        busy_ms=2,
        idle_ms=1,
        cost=0.0,
        tokens=0,
    )

    try:
        discovery._sync([session])
        notifications.clear()

        discovery._mark_offline()
        assert store.get("opencode:ses_off").status is AgentStatus.OFFLINE
        assert notifications

        notifications.clear()
        discovery._mark_offline()
        assert not notifications
    finally:
        audit.close()


def test_candidate_urls_prefer_cached_url(monkeypatch):
    discovery = OpenCodeDiscovery(
        Settings(), StateStore(), None, lambda: None  # type: ignore[arg-type]
    )
    discovery._url = "http://127.0.0.1:40000"

    def fail():
        raise AssertionError("no debería descubrir puertos si ya hay URL")

    monkeypatch.setattr("baton.discovery.opencode_ports", fail)
    assert discovery._candidate_urls() == ["http://127.0.0.1:40000"]


def _make_tabs_db(tmp_path, values):
    db = tmp_path / "drafts.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE state (name TEXT, key TEXT, value TEXT, updated_at INTEGER)"
    )
    for index, value in enumerate(values):
        conn.execute(
            "INSERT INTO state VALUES (?, ?, ?, ?)",
            (
                f"opencode.window.{index}.dat",
                "tabs",
                json.dumps(value),
                1,
            ),
        )
    conn.commit()
    conn.close()
    return db


def test_tabs_from_db_reads_open_sessions(tmp_path):
    db = _make_tabs_db(
        tmp_path,
        [
            [
                {"type": "session", "sessionId": "ses_a"},
                {"type": "home"},
            ],
            [{"type": "session", "sessionId": "ses_b"}],
        ],
    )
    assert _tabs_from_db(db) == {"ses_a", "ses_b"}


def test_tabs_from_db_empty_and_missing(tmp_path):
    empty = _make_tabs_db(tmp_path, [[]])
    assert _tabs_from_db(empty) == set()
    assert _tabs_from_db(tmp_path / "missing.sqlite") is None


def _make_message_db(tmp_path, rows):
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE session_message ("
        "session_id TEXT, type TEXT, seq INTEGER, data TEXT)"
    )
    for seq, kind, data in rows:
        conn.execute(
            "INSERT INTO session_message VALUES (?, ?, ?, ?)",
            ("ses_x", kind, seq, json.dumps(data)),
        )
    conn.commit()
    conn.close()
    return db


def test_opencode_output_text(tmp_path):
    db = _make_message_db(
        tmp_path,
        [
            (
                1,
                "assistant",
                {"content": [{"type": "text", "text": "  Listo:  los tests pasan.  "}]},
            )
        ],
    )
    assert opencode_output("ses_x", db_path=db) == "Listo: los tests pasan."


def test_opencode_output_tool(tmp_path):
    db = _make_message_db(
        tmp_path,
        [
            (
                1,
                "assistant",
                {
                    "content": [
                        {"type": "reasoning", "text": "pienso"},
                        {
                            "type": "tool",
                            "name": "shell",
                            "state": {"input": {"command": "npm test"}},
                        },
                    ]
                },
            )
        ],
    )
    assert opencode_output("ses_x", db_path=db) == "→ shell: npm test"


def test_opencode_output_skips_reasoning(tmp_path):
    db = _make_message_db(
        tmp_path,
        [
            (
                1,
                "assistant",
                {"content": [{"type": "text", "text": "Respuesta anterior"}]},
            ),
            (
                2,
                "assistant",
                {"content": [{"type": "reasoning", "text": "solo razonamiento"}]},
            ),
        ],
    )
    assert opencode_output("ses_x", db_path=db) == "Respuesta anterior"
    assert opencode_output("ses_x", db_path=tmp_path / "missing.db") == ""


def test_opencode_output_prefers_text_over_newer_tool(tmp_path):
    db = _make_message_db(
        tmp_path,
        [
            (
                1,
                "assistant",
                {"content": [{"type": "text", "text": "Respuesta final"}]},
            ),
            (
                2,
                "assistant",
                {
                    "content": [
                        {
                            "type": "tool",
                            "name": "shell",
                            "state": {"input": {"command": "npm test"}},
                        }
                    ]
                },
            ),
        ],
    )
    assert opencode_output("ses_x", db_path=db) == "Respuesta final"


def test_sync_sets_task_and_log(tmp_path):
    settings = Settings(db_path=tmp_path / "output.db")
    audit = AuditLog(settings.db_path)
    store = StateStore()
    discovery = OpenCodeDiscovery(settings, store, audit, lambda: None)

    session = DetectedSession(
        session_id="ses_out",
        name="Entrega",
        model="model",
        cwd="",
        updated_ms=NOW,
        busy_ms=1,
        idle_ms=2,
        cost=0.0,
        tokens=0,
        output="Preparando la entrega",
    )

    try:
        discovery._sync([session])
        agent = store.get("opencode:ses_out")
        assert agent.task == "Preparando la entrega"
        assert any("Preparando la entrega" in line for line in agent.logs)

        before = len(agent.logs)
        discovery._sync([session])
        assert len(agent.logs) == before
    finally:
        audit.close()


class _FakeResponse:
    def __init__(self, items):
        self.status_code = 200
        self._items = items

    def json(self):
        return {"data": self._items}


class _FakeClient:
    def __init__(self, items):
        self.items = items

    async def get(self, path, headers=None):
        return _FakeResponse(self.items)


async def test_poll_permissions_first_dedup_and_next(tmp_path):
    settings = Settings(
        db_path=tmp_path / "permissions.db",
        opencode_password="test",
    )
    discovery = OpenCodeDiscovery(settings, StateStore(), None, lambda: None)
    events: list[tuple[str, dict]] = []

    async def on_approval(agent_id, payload):
        events.append((agent_id, payload))

    discovery._on_approval = on_approval
    session = DetectedSession(
        session_id="ses_p",
        name="Permisos",
        model="model",
        cwd=r"C:\dev",
        updated_ms=NOW,
        busy_ms=1,
        idle_ms=2,
        cost=0.0,
        tokens=0,
    )
    client = _FakeClient(
        [
            {
                "id": "per_1",
                "action": "bash",
                "resources": ["rm -rf build"],
                "message": "Permiso de shell",
            },
            {
                "id": "per_2",
                "action": "edit",
                "resources": ["src/app.py"],
                "message": "Permiso de edición",
            },
        ]
    )

    await discovery._poll_permissions(client, "http://x", session)
    assert len(events) == 1
    agent_id, payload = events[0]
    assert agent_id == "opencode:ses_p"
    assert payload["approval_id"] == "oc_per_1"
    assert payload["kind"] == "bash"
    assert payload["command"] == "rm -rf build"
    assert payload["risk"] == "high"

    # La primera sigue pendiente: no se adelanta la segunda.
    await discovery._poll_permissions(client, "http://x", session)
    assert len(events) == 1

    # Al desaparecer, se puede emitir la siguiente.
    client.items = []
    await discovery._poll_permissions(client, "http://x", session)
    client.items = [
        {
            "id": "per_3",
            "action": "bash",
            "resources": ["ls"],
            "message": "Permiso de shell",
        }
    ]
    await discovery._poll_permissions(client, "http://x", session)
    assert len(events) == 2
    assert events[1][1]["approval_id"] == "oc_per_3"
