import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from baton.audit import AuditLog
from baton.config import Settings
from baton.discovery import agent_id_for
from baton.local_agents import (
    AntigravitySource,
    ClaudeCodeSource,
    CodexSource,
    CopilotSource,
    CursorSource,
    GeminiSource,
    LocalAgentDiscovery,
    _ms_from_value,
)
from baton.protocol import AgentStatus
from baton.state import StateStore


def now_ms() -> int:
    return int(time.time() * 1000)


def scan(source, *, recency_s: int = 3600):
    return source.scan(
        now_ms=now_ms(),
        recency_ms=recency_s * 1000,
        limit=8,
        active_s=120,
    )


def test_ms_from_value_variants():
    assert _ms_from_value(1_700_000_000) == 1_700_000_000_000
    assert _ms_from_value(1_700_000_000_000) == 1_700_000_000_000
    assert _ms_from_value("2026-11-05T10:00:00Z") > 0
    assert _ms_from_value("2026-11-05 10:00:00") > 0
    assert _ms_from_value(None) == 0


def test_agent_id_uses_provider():
    assert agent_id_for("ses_1") == "opencode:ses_1"
    assert agent_id_for("ses_1", "openai") == "openai:ses_1"


def test_claude_code_source(tmp_path):
    project = tmp_path / "C--dev-demo"
    project.mkdir()
    session = project / "ses_claude.jsonl"
    lines = [
        {
            "type": "summary",
            "summary": "Refactor del login",
            "sessionId": "ses_claude",
            "cwd": r"C:\dev\demo",
            "timestamp": "2026-11-05T10:00:00Z",
        },
        {
            "type": "user",
            "sessionId": "ses_claude",
            "cwd": r"C:\dev\demo",
            "timestamp": "2026-11-05T10:00:01Z",
            "message": {"role": "user", "content": "Arregla el login"},
        },
        {
            "type": "assistant",
            "sessionId": "ses_claude",
            "timestamp": "2026-11-05T10:00:02Z",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "content": [{"type": "text", "text": "Voy a revisarlo"}],
            },
        },
    ]
    session.write_text(
        "\n".join(json.dumps(line) for line in lines), encoding="utf-8"
    )

    sessions = scan(ClaudeCodeSource(root=tmp_path))

    assert len(sessions) == 1
    found = sessions[0]
    assert found.agent_id == "anthropic:ses_claude"
    assert found.name == "Refactor del login"
    assert found.model == "claude-sonnet-4-5"
    assert found.cwd == r"C:\dev\demo"
    assert found.tokens == 120
    assert found.status is AgentStatus.RUNNING


def test_claude_code_ignores_subagents(tmp_path):
    subagents = tmp_path / "project" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-1.jsonl").write_text(
        json.dumps({"type": "user", "sessionId": "agent", "message": {"content": "x"}}),
        encoding="utf-8",
    )
    assert scan(ClaudeCodeSource(root=tmp_path)) == []


def make_codex_catalog(home: Path):
    sqlite_dir = home / "sqlite"
    sqlite_dir.mkdir(parents=True)
    db = sqlite_dir / "codex.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE local_thread_catalog ("
        "thread_id TEXT, display_title TEXT, source_created_at REAL,"
        "source_updated_at REAL, cwd TEXT, source_kind TEXT, host_id TEXT,"
        "missing_candidate INTEGER, model_provider TEXT)"
    )
    current = time.time()
    conn.executemany(
        "INSERT INTO local_thread_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "th_local",
                "Arreglar parser",
                current - 60,
                current - 5,
                r"C:\dev\parser",
                "local",
                "local",
                0,
                "openai",
            ),
            (
                "th_cloud",
                "Chat de ChatGPT",
                current - 60,
                current - 5,
                None,
                "chatgpt",
                "chatgpt:user",
                0,
                None,
            ),
            (
                "th_missing",
                "Hilo desaparecido",
                current - 60,
                current - 5,
                None,
                "local",
                "local",
                1,
                None,
            ),
            (
                "th_old",
                "Viejo",
                current - 9000,
                current - 9000,
                None,
                "local",
                "local",
                0,
                None,
            ),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_codex_catalog_only_local_recent(tmp_path):
    home = tmp_path / ".codex"
    make_codex_catalog(home)

    sessions = scan(CodexSource(home=home))

    assert [session.agent_id for session in sessions] == ["openai:th_local"]
    found = sessions[0]
    assert found.name == "Arreglar parser"
    assert found.cwd == r"C:\dev\parser"
    assert found.model == "codex"
    assert found.status is AgentStatus.RUNNING


def test_codex_legacy_state_db(tmp_path):
    home = tmp_path / ".codex"
    home.mkdir()
    db = home / "state_5.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE threads ("
        "id TEXT, title TEXT, name TEXT, preview TEXT, cwd TEXT, model TEXT,"
        "updated_at_ms INTEGER, updated_at INTEGER, tokens_used INTEGER,"
        "archived INTEGER)"
    )
    current = now_ms()
    conn.execute(
        "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "th_state",
            "Migrar cliente",
            None,
            None,
            r"C:\dev\client",
            "gpt-5-codex",
            current,
            current / 1000,
            1234,
            0,
        ),
    )
    conn.commit()
    conn.close()

    sessions = scan(CodexSource(home=home))

    assert len(sessions) == 1
    assert sessions[0].agent_id == "openai:th_state"
    assert sessions[0].model == "gpt-5-codex"
    assert sessions[0].tokens == 1234


def test_gemini_source(tmp_path):
    root = tmp_path / "tmp"
    chats = root / "hash" / "chats"
    chats.mkdir(parents=True)
    (chats.parent / ".project_root").write_text(r"C:\dev\web", encoding="utf-8")
    session = chats / "session-2026-11-05-abc.json"
    session.write_text(
        json.dumps(
            {
                "sessionId": "gem_1",
                "startTime": "2026-11-05T10:00:00Z",
                "lastUpdated": "2026-11-05T10:00:03Z",
                "messages": [
                    {
                        "type": "user",
                        "content": "Haz una landing",
                        "timestamp": "2026-11-05T10:00:01Z",
                    },
                    {
                        "type": "gemini",
                        "model": "gemini-3-pro",
                        "content": "Vale",
                        "tokens": {"input": 10, "output": 5},
                        "timestamp": "2026-11-05T10:00:02Z",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    sessions = scan(GeminiSource(root=root))

    assert len(sessions) == 1
    found = sessions[0]
    assert found.agent_id == "google:gem_1"
    assert found.name == "Haz una landing"
    assert found.model == "gemini-3-pro"
    assert found.cwd == r"C:\dev\web"
    assert found.tokens == 15
    assert found.status is AgentStatus.RUNNING


def test_antigravity_source(tmp_path):
    db = tmp_path / "conversation_summaries.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT, title TEXT, preview TEXT, step_count INTEGER,"
        "last_modified_time TEXT, workspace_uris TEXT, status TEXT,"
        "agent_name TEXT, parent_conversation_id TEXT, not_fully_idle NUMERIC,"
        "killed NUMERIC, last_user_input_time TEXT)"
    )
    conn.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "conv_1",
            "Panel de control",
            None,
            3,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(["file:///C:/dev/baton"]),
            "active",
            "Gemini 3 Pro",
            None,
            1,
            0,
            None,
        ),
    )
    conn.commit()
    conn.close()

    sessions = scan(AntigravitySource(db_path=db))

    assert len(sessions) == 1
    found = sessions[0]
    assert found.agent_id == "antigravity:conv_1"
    assert found.name == "Panel de control"
    assert found.model == "Gemini 3 Pro"
    assert "baton" in found.cwd
    assert found.status is AgentStatus.RUNNING


def test_cursor_composer_source(tmp_path):
    db = tmp_path / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
    payload = {
        "allComposers": [
            {
                "composerId": "comp_1",
                "name": "Refactor UI",
                "lastUpdatedAt": now_ms(),
                "workspaceIdentifier": {"uri": "file:///C:/dev/ui"},
            }
        ]
    }
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("composer.composerData", json.dumps(payload).encode("utf-8")),
    )
    conn.commit()
    conn.close()

    sessions = scan(CursorSource(db_path=db))

    assert len(sessions) == 1
    assert sessions[0].agent_id == "cursor:comp_1"
    assert sessions[0].name == "Refactor UI"
    assert sessions[0].cwd == r"C:\dev\ui"
    assert sessions[0].status is AgentStatus.RUNNING


def test_cursor_chatdata_source(tmp_path):
    db = tmp_path / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
    payload = {
        "tabs": [
            {
                "tabId": "tab_1",
                "chatTitle": "Arreglar build",
                "lastSendTime": now_ms(),
                "bubbles": [{"modelType": "claude-3.5"}],
            }
        ]
    }
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        (
            "workbench.panel.aichat.view.aichat.chatdata",
            json.dumps(payload).encode("utf-8"),
        ),
    )
    conn.commit()
    conn.close()

    sessions = scan(CursorSource(db_path=db))

    assert len(sessions) == 1
    assert sessions[0].agent_id == "cursor:tab_1"
    assert sessions[0].name == "Arreglar build"
    assert sessions[0].model == "claude-3.5"


def test_copilot_source(tmp_path):
    root = tmp_path / "copilot"
    root.mkdir()
    (root / "session-1.json").write_text(
        json.dumps(
            {
                "sessionId": "cop_1",
                "title": "Revisar PR",
                "cwd": r"C:\dev\pr",
                "model": "gpt-5",
                "updatedAt": now_ms(),
                "messages": [],
            }
        ),
        encoding="utf-8",
    )

    sessions = scan(CopilotSource(roots=[root]))

    assert len(sessions) == 1
    assert sessions[0].agent_id == "github:cop_1"
    assert sessions[0].name == "Revisar PR"
    assert sessions[0].cwd == r"C:\dev\pr"


async def test_local_manager_syncs_and_removes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    session = project / "ses_manager.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "ses_manager",
                "cwd": r"C:\dev\m",
                "message": {"content": "Trabaja"},
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(db_path=tmp_path / "manager.db")
    audit = AuditLog(settings.db_path)
    store = StateStore()
    notifications: list[int] = []
    discovery = LocalAgentDiscovery(
        settings,
        store,
        audit,
        lambda: notifications.append(1),
        sources=[ClaudeCodeSource(root=tmp_path)],
    )

    try:
        await discovery._poll()
        agent = store.get("anthropic:ses_manager")
        assert agent.name == "Trabaja"
        assert agent.provider == "anthropic"
        assert notifications

        session.unlink()
        await discovery._poll()
        assert store.maybe_get("anthropic:ses_manager") is None
    finally:
        audit.close()
