import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from baton.api import create_app
from baton.config import Settings


def hello(token: str, device_id: str = "baton-test") -> dict:
    return {
        "type": "hello",
        "proto": 1,
        "device_id": device_id,
        "fw": "test",
        "token": token,
    }


def recv_until(ws, kind: str, limit: int = 80) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message.get("type") == kind:
            return message
    raise AssertionError(f"no llegó ningún mensaje {kind}")


def bootstrap(client: TestClient) -> dict:
    response = client.get("/api/dev/bootstrap")
    assert response.status_code == 200
    return response.json()


def test_bootstrap_is_local_only(app):
    with TestClient(app, client=("10.0.0.7", 1234)) as remote:
        response = remote.get("/api/dev/bootstrap")
        assert response.status_code == 403


def test_bootstrap_default_device_id(client):
    body = client.get("/api/dev/bootstrap").json()
    assert body["device_id"].startswith("baton-web-")


def test_bootstrap_unique_panels(client):
    first = client.get("/api/dev/bootstrap?device_id=baton-web-aaa").json()
    second = client.get("/api/dev/bootstrap?device_id=baton-web-bbb").json()

    assert first["device_id"] == "baton-web-aaa"
    assert second["device_id"] == "baton-web-bbb"
    assert first["token"] != second["token"]

    devices = {device["device_id"] for device in client.get("/api/devices").json()}
    assert {"baton-web-aaa", "baton-web-bbb"} <= devices


def test_bootstrap_sanitizes_device_id(client):
    body = client.get("/api/dev/bootstrap?device_id=../../evil<baton>").json()
    assert body["device_id"].startswith("baton-web-")


def test_info_endpoint(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    body = response.json()
    assert body["version"]
    assert body["max_pinned"] == 2
    assert body["opencode_enabled"] is False
    assert body["local_agents_enabled"] is False
    assert body["agents"] == 1
    assert body["sources"] == []


def test_devices_include_connected_flag(client):
    issued = bootstrap(client)
    devices = client.get("/api/devices").json()
    device = next(
        item for item in devices if item["device_id"] == issued["device_id"]
    )
    assert device["connected"] is False


def test_virtual_device_info(client):
    body = client.get("/api/dev/virtual").json()
    assert body["virtual"] is True
    assert body["device_id"].startswith("baton-")
    assert body["qr_svg"].startswith("<svg")
    assert len(body["code"]) == 6
    assert "otpauth://totp/" in body["otpauth"]


def test_virtual_device_pair_and_confirm(client):
    info = client.get("/api/dev/virtual").json()
    response = client.post(
        "/api/dev/virtual/pair",
        json={"code": info["code"], "pc_name": "TEST-PC"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_confirm"
    assert len(body["sas"]) == 4

    confirmed = client.post(
        "/api/dev/virtual/confirm", json={"pair_id": body["pair_id"]}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "paired"

    devices = client.get("/api/devices").json()
    virtual = next(item for item in devices if item["virtual"])
    assert virtual["device_id"] == info["device_id"]
    assert virtual["connected"] is False

    token = client.get("/api/dev/virtual/panel-token")
    assert token.status_code == 200
    assert token.json()["device_id"] == info["device_id"]
    assert token.json()["token"]


def test_virtual_device_cancel_clears_pending(client):
    info = client.get("/api/dev/virtual").json()
    response = client.post(
        "/api/dev/virtual/pair",
        json={"code": info["code"], "pc_name": "TEST-PC"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "needs_confirm"

    cancelled = client.post("/api/dev/virtual/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    after = client.get("/api/dev/virtual").json()
    assert after["needs_confirm"] is False
    assert after["paired"] is False


def test_virtual_device_bad_code_returns_401(client):
    info = client.get("/api/dev/virtual").json()
    bad = "000000" if info["code"] != "000000" else "000001"
    response = client.post(
        "/api/dev/virtual/pair", json={"code": bad, "pc_name": "TEST-PC"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "bad_code"


def test_virtual_device_reset_changes_id(client):
    before = client.get("/api/dev/virtual").json()["device_id"]
    after = client.post("/api/dev/virtual/reset").json()["device_id"]
    assert after != before


def test_agent_interrupt_endpoint(client):
    response = client.post("/api/agents/claude-code/interrupt")
    assert response.status_code == 200
    assert response.json()["ok"] is True

    missing = client.post("/api/agents/no-existe/interrupt")
    assert missing.status_code == 404


def test_agent_message_endpoint(client):
    response = client.post(
        "/api/agents/claude-code/message", json={"text": "hola"}
    )
    assert response.status_code == 200
    assert response.json()["chars"] == 4

    blank = client.post("/api/agents/claude-code/message", json={"text": "   "})
    assert blank.status_code == 422

    missing = client.post(
        "/api/agents/no-existe/message", json={"text": "hola"}
    )
    assert missing.status_code == 404


def test_rest_config_endpoint(client):
    assert client.get("/api/config/rest").json()["rest_after_s"] == 300

    updated = client.patch(
        "/api/config/rest", json={"rest_after_s": 600}
    )
    assert updated.status_code == 200
    assert updated.json()["rest_after_s"] == 600
    assert client.get("/api/info").json()["rest_after_s"] == 600

    invalid = client.patch(
        "/api/config/rest", json={"rest_after_s": 99999}
    )
    assert invalid.status_code == 422


def test_rest_config_persists(tmp_path):
    db_path = tmp_path / "persist.db"

    def make_app() -> TestClient:
        return TestClient(
            create_app(
                Settings(
                    db_path=db_path,
                    fake_autostart=True,
                    fake_agents=1,
                    opencode_enabled=False,
                    local_agents_enabled=False,
                )
            )
        )

    with make_app() as first:
        assert first.patch(
            "/api/config/rest", json={"rest_after_s": 420}
        ).status_code == 200

    with make_app() as second:
        assert second.get("/api/config/rest").json()["rest_after_s"] == 420


def test_control_pair_with_google_code(app):
    from baton import totp

    device = app.state.services.virtual_device
    assert device is not None
    code = totp.totp(device.secret)

    bad_code = "000000" if code != "000000" else "111111"
    with TestClient(app, client=("10.0.0.7", 1234)) as remote:
        bad = remote.post("/api/control/pair", json={"code": bad_code})
        assert bad.status_code == 401

        good = remote.post("/api/control/pair", json={"code": code})
        assert good.status_code == 200
        assert good.json()["token"] == app.state.services.remote_token

        # Un código ya usado no se puede reutilizar.
        replay = remote.post("/api/control/pair", json={"code": code})
        assert replay.status_code == 401
        assert replay.json()["detail"] == "replay"


def test_remote_control_requires_token(app):
    token = app.state.services.remote_token

    with TestClient(app, client=("10.0.0.7", 1234)) as remote:
        assert remote.get("/api/state").status_code == 403
        response = remote.get(
            "/api/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "agents" in response.json()
        assert remote.get("/api/config/remote").status_code == 403

    with TestClient(app, client=("127.0.0.1", 1234)) as local:
        body = local.get("/api/config/remote").json()
        assert body["ok"] is True
        assert body["token"] == token


def test_provider_budgets_endpoint(client):
    assert client.get("/api/config/budgets").json()["budgets"] == {}

    updated = client.patch(
        "/api/config/budgets",
        json={"budgets": {"anthropic": 2_000_000, "opencode": 0}},
    )
    assert updated.status_code == 200
    assert updated.json()["budgets"] == {
        "anthropic": 2_000_000,
        "opencode": 0,
    }
    assert client.get("/api/info").json()["provider_budgets"] == {
        "anthropic": 2_000_000,
        "opencode": 0,
    }

    invalid = client.patch(
        "/api/config/budgets", json={"budgets": {"anthropic": -1}}
    )
    assert invalid.status_code == 422


def test_provider_budgets_persist(tmp_path):
    db_path = tmp_path / "budgets.db"

    def make_app() -> TestClient:
        return TestClient(
            create_app(
                Settings(
                    db_path=db_path,
                    fake_autostart=True,
                    fake_agents=1,
                    opencode_enabled=False,
                    local_agents_enabled=False,
                )
            )
        )

    with make_app() as first:
        assert first.patch(
            "/api/config/budgets",
            json={"budgets": {"openai": 1_500_000}},
        ).status_code == 200

    with make_app() as second:
        assert second.get("/api/config/budgets").json()["budgets"] == {
            "openai": 1_500_000
        }


def test_agent_limits_endpoint(client):
    period = client.patch(
        "/api/config/limits", json={"period": "weekly"}
    )
    assert period.status_code == 200
    assert period.json()["period"] == "weekly"

    saved = client.patch(
        "/api/config/limits/claude-code",
        json={"daily": 1_000_000, "weekly": 4_000_000, "monthly": 10_000_000},
    )
    assert saved.status_code == 200
    assert saved.json()["limits"]["weekly"] == 4_000_000

    body = client.get("/api/config/limits").json()
    assert body["period"] == "weekly"
    agent = next(item for item in body["agents"] if item["id"] == "claude-code")
    assert agent["limits"] == {
        "daily": 1_000_000,
        "weekly": 4_000_000,
        "monthly": 10_000_000,
    }
    assert "usage" in agent
    assert client.get("/api/info").json()["ticker_period"] == "weekly"


def test_pair_with_valid_code(client):
    code = client.app.state.services.pairing.code
    response = client.post(
        "/api/pair", json={"code": code, "device_name": "mando de prueba"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["device_id"].startswith("baton-")
    assert len(body["token"]) > 20


def test_pair_rejects_wrong_code(client):
    code = client.app.state.services.pairing.code
    wrong = "000000" if code != "000000" else "111111"
    response = client.post("/api/pair", json={"code": wrong, "device_name": "x"})
    assert response.status_code == 401


def test_ws_rejects_invalid_token(client):
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello("token-invalido-123"))
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4401


def test_ws_rejects_missing_hello(client):
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json({"type": "ping", "seq": 1})
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4400


def test_ws_ping_pong(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")
        ws.send_json({"type": "ping", "seq": 7})
        pong = recv_until(ws, "pong")
        assert pong["seq"] == 7


def test_ws_sends_state_with_fake_agent(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        welcome = recv_until(ws, "welcome")
        assert welcome["proto"] == 1
        state = recv_until(ws, "state")
        assert [agent["id"] for agent in state["agents"]] == ["claude-code"]
        assert state["agents"][0]["name"] == "Auth refactor"
        assert state["seq"] >= 1


def test_force_approval_and_allow(client):
    issued = bootstrap(client)
    token = issued["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")

        forced = client.post("/api/dev/approval", json={"risk": "high"})
        assert forced.status_code == 200

        request = recv_until(ws, "approval_request")
        assert request["risk"] == "high"
        assert request["hold_ms"] == 1500
        assert request["agent_id"] == "claude-code"
        assert request["command"]
        assert request["expires_at"].endswith("Z")

        ws.send_json(
            {
                "type": "approval_response",
                "approval_id": request["approval_id"],
                "option_id": "allow",
                "source": "button",
            }
        )

        seen = {}
        for _ in range(40):
            message = ws.receive_json()
            if message.get("type") in {"approval_result", "ack"}:
                seen[message["type"]] = message
            if len(seen) == 2:
                break

        assert seen["approval_result"]["status"] == "accepted"
        assert seen["approval_result"]["accepted"] is True
        assert seen["ack"]["ok"] is True

    audit = client.get("/api/audit").json()
    assert audit["approvals"][0]["status"] == "accepted"
    assert audit["approvals"][0]["device_id"] == issued["device_id"]


def test_reject_flow(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")

        client.post("/api/dev/approval", json={"risk": "normal"})
        request = recv_until(ws, "approval_request")
        ws.send_json(
            {
                "type": "approval_response",
                "approval_id": request["approval_id"],
                "option_id": "deny",
            }
        )
        result = recv_until(ws, "approval_result")
        assert result["status"] == "rejected"
        assert result["accepted"] is False


def test_duplicate_response_is_idempotent(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")

        client.post("/api/dev/approval", json={"risk": "normal"})
        request = recv_until(ws, "approval_request")
        payload = {
            "type": "approval_response",
            "approval_id": request["approval_id"],
            "option_id": "allow",
        }
        ws.send_json(payload)
        recv_until(ws, "approval_result")
        recv_until(ws, "ack")

        ws.send_json(payload)
        seen = {}
        for _ in range(20):
            message = ws.receive_json()
            if message.get("type") in {"approval_result", "ack"}:
                seen[message["type"]] = message
            if len(seen) == 2:
                break
        assert seen["approval_result"]["duplicate"] is True
        assert seen["approval_result"]["status"] == "accepted"
        assert seen["ack"]["ok"] is True
        assert "ya resuelta" in seen["ack"]["detail"]


def test_unknown_approval_is_not_accepted(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")
        ws.send_json(
            {
                "type": "approval_response",
                "approval_id": "apr_does_not_exist",
                "option_id": "allow",
            }
        )
        error = recv_until(ws, "error")
        assert error["code"] == "unknown"


def test_interrupt(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")
        ws.send_json({"type": "interrupt", "agent_id": "claude-code"})
        ack = recv_until(ws, "ack")
        assert ack["ref"] == "interrupt"
        assert ack["ok"] is True


def test_audio_end_reports_missing_stt(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/audio") as ws:
        ws.send_json(hello(token, device_id="baton-audio"))
        recv_until(ws, "ack")
        ws.send_text(
            json.dumps(
                {
                    "type": "audio_end",
                    "seq": 1,
                    "duration_ms": 1200,
                }
            )
        )
        error = recv_until(ws, "error")
        assert error["code"] == "stt_not_configured"


def test_reconnect_resyncs_pending_approval(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")
        client.post("/api/dev/approval", json={"risk": "normal"})
        request = recv_until(ws, "approval_request")

        # Un segundo dispositivo (token distinto) se conecta con la petición
        # todavía pendiente: debe recibirla, no solo el estado.
        code = client.app.state.services.pairing.code
        paired = client.post("/api/pair", json={"code": code, "device_name": "segundo"})
        with client.websocket_connect("/ws/control") as ws2:
            ws2.send_json(hello(paired.json()["token"], device_id="baton-2"))
            recv_until(ws2, "welcome")
            recv_until(ws2, "state")
            resent = recv_until(ws2, "approval_request")
            assert resent["approval_id"] == request["approval_id"]
            assert resent["command"] == request["command"]


def test_visibility_defaults_empty(client):
    response = client.get("/api/config/visibility")
    assert response.status_code == 200
    assert response.json()["hidden_agents"] == []


def test_visibility_patch_and_get(client):
    response = client.patch(
        "/api/config/visibility/claude-code", json={"hidden": True}
    )
    assert response.status_code == 200
    assert response.json()["hidden_agents"] == ["claude-code"]
    assert client.get("/api/config/visibility").json()["hidden_agents"] == ["claude-code"]

    response = client.patch(
        "/api/config/visibility/claude-code", json={"hidden": False}
    )
    assert response.json()["hidden_agents"] == []


def test_visibility_unknown_agent(client):
    response = client.patch("/api/config/visibility/no-such-agent", json={"hidden": True})
    assert response.status_code == 404


def test_visibility_in_welcome(client):
    token = bootstrap(client)["token"]
    client.patch("/api/config/visibility/claude-code", json={"hidden": True})

    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        welcome = recv_until(ws, "welcome")
        assert welcome["config"]["hidden_agents"] == ["claude-code"]


def test_visibility_broadcast(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")

        response = client.patch(
            "/api/config/visibility/claude-code", json={"hidden": True}
        )
        assert response.status_code == 200
        message = recv_until(ws, "visibility")
        assert message["hidden_agents"] == ["claude-code"]


def test_pins_default_empty(client):
    assert client.get("/api/config/pins").json()["pinned_agents"] == []


def test_pin_and_unpin(client):
    pinned = client.patch(
        "/api/config/pins/claude-code", json={"pinned": True}
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned_agents"] == ["claude-code"]
    assert client.get("/api/config/pins").json()["pinned_agents"] == [
        "claude-code"
    ]

    unpinned = client.patch(
        "/api/config/pins/claude-code", json={"pinned": False}
    )
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned_agents"] == []


def test_pin_unknown_agent(client):
    response = client.patch(
        "/api/config/pins/no-such-agent", json={"pinned": True}
    )
    assert response.status_code == 404


def test_pin_limit(tmp_path):
    settings = Settings(
        db_path=tmp_path / "pins.db",
        fake_autostart=True,
        fake_agents=3,
        opencode_enabled=False,
        local_agents_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.patch(
            "/api/config/pins/claude-code", json={"pinned": True}
        ).status_code == 200
        assert client.patch(
            "/api/config/pins/codex", json={"pinned": True}
        ).status_code == 200
        third = client.patch(
            "/api/config/pins/antigravity", json={"pinned": True}
        )
        assert third.status_code == 409
        assert third.json()["detail"] == "pin_limit"
        assert client.get("/api/config/pins").json()["pinned_agents"] == [
            "claude-code",
            "codex",
        ]


def test_pins_in_welcome(client):
    token = bootstrap(client)["token"]
    client.patch("/api/config/pins/claude-code", json={"pinned": True})

    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        welcome = recv_until(ws, "welcome")
        assert welcome["config"]["pinned_agents"] == ["claude-code"]


def test_pins_broadcast(client):
    token = bootstrap(client)["token"]
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json(hello(token))
        recv_until(ws, "welcome")
        recv_until(ws, "state")

        response = client.patch(
            "/api/config/pins/claude-code", json={"pinned": True}
        )
        assert response.status_code == 200
        message = recv_until(ws, "pinned")
        assert message["pinned_agents"] == ["claude-code"]


def test_pins_persist_across_restart(settings):
    first = create_app(settings)
    with TestClient(first) as client:
        assert client.patch(
            "/api/config/pins/claude-code", json={"pinned": True}
        ).status_code == 200

    second = create_app(settings)
    with TestClient(second) as client:
        assert client.get("/api/config/pins").json()["pinned_agents"] == [
            "claude-code"
        ]


def test_visibility_persists_across_restart(settings):
    first = create_app(settings)
    with TestClient(first) as client:
        response = client.patch(
            "/api/config/visibility/claude-code", json={"hidden": True}
        )
        assert response.status_code == 200

    second = create_app(settings)
    with TestClient(second) as client:
        assert client.get("/api/config/visibility").json()["hidden_agents"] == [
            "claude-code"
        ]


def test_approval_expires_without_response(tmp_path):
    settings = Settings(
        db_path=tmp_path / "expire.db",
        fake_autostart=True,
        fake_agents=1,
        approval_timeout_s=0.4,
        opencode_enabled=False,
        local_agents_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        token = bootstrap(client)["token"]
        with client.websocket_connect("/ws/control") as ws:
            ws.send_json(hello(token))
            recv_until(ws, "welcome")
            recv_until(ws, "state")
            client.post("/api/dev/approval", json={"risk": "normal"})
            request = recv_until(ws, "approval_request")
            result = recv_until(ws, "approval_result", limit=120)
            assert result["approval_id"] == request["approval_id"]
            assert result["status"] == "expired"
            assert result["accepted"] is False
