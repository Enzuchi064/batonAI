from baton.claude_usage import normalize as normalize_claude
from baton.limits import LimitsService
from baton.opencode_usage import normalize as normalize_opencode


def test_opencode_normalizes_go_windows():
    payload = {
        "data": {
            "workspace": {"id": "org_1", "name": "Personal"},
            "go": {
                "rolling": {
                    "percent": 11,
                    "limited": False,
                    "resetsAt": 1793970897000,
                },
                "weekly": {
                    "percent": 13,
                    "limited": False,
                    "resetsAt": 1794182400000,
                },
                "monthly": {
                    "percent": 20,
                    "limited": True,
                    "resetsAt": 1794859691000,
                },
            },
            "budgets": [],
        }
    }

    body = normalize_opencode(payload)

    assert body["ok"] is True
    assert body["plan"] == "Go"
    assert body["workspace"] == "Personal"
    assert [window["id"] for window in body["windows"]] == [
        "rolling",
        "weekly",
        "monthly",
    ]
    assert [window["used_percent"] for window in body["windows"]] == [11, 13, 20]
    assert [window["remaining_percent"] for window in body["windows"]] == [
        89,
        87,
        80,
    ]
    assert body["windows"][0]["resets_at"] == 1793970897
    assert body["windows"][2]["limited"] is True


def test_opencode_null_data_means_not_signed_in():
    body = normalize_opencode({"data": None})

    assert body["ok"] is False
    assert body["error"] == "not_signed_in"
    assert body["windows"] == []


def test_opencode_normalizes_console_budgets():
    payload = {
        "data": {
            "workspace": {"id": "org_1", "name": "Personal"},
            "budgets": [
                {
                    "id": "b1",
                    "limit": 10,
                    "spent": 2.5,
                    "scope": "combined",
                    "per": "set",
                    "coverage": "all",
                    "models": [],
                    "vendors": [],
                    "picked": True,
                    "shared": False,
                    "resetsAt": 1794859691000,
                }
            ],
        }
    }

    body = normalize_opencode(payload)

    assert body["ok"] is True
    assert body["plan"] == "Console"
    assert body["windows"] == []
    budget = body["budgets"][0]
    assert budget["used_percent"] == 25
    assert budget["remaining_percent"] == 75
    assert budget["limit_usd"] == 10
    assert budget["spent_usd"] == 2.5
    assert budget["resets_at"] == 1794859691


def test_claude_normalizes_session_and_week():
    payload = {
        "five_hour": {"utilization": 10, "resets_at": 1793970897},
        "seven_day": {
            "utilization": 42.4,
            "resets_at": "2026-11-13T00:00:00Z",
        },
    }

    body = normalize_claude(payload)

    assert body["ok"] is True
    assert [window["id"] for window in body["windows"]] == ["rolling", "weekly"]
    assert body["windows"][0]["used_percent"] == 10
    assert body["windows"][1]["used_percent"] == 42
    assert body["windows"][1]["resets_at"] == 1794528000


class FakeSource:
    def __init__(self, provider_id: str, *, ok: bool = True) -> None:
        self.id = provider_id
        self.label = provider_id.title()
        self.poll_s = 60.0
        self._ok = ok

    def snapshot(self):
        return {
            "id": self.id,
            "label": self.label,
            "installed": True,
            "ok": self._ok,
            "plan": "test",
            "workspace": None,
            "windows": [
                {
                    "id": "rolling",
                    "label": "Rolling",
                    "used_percent": 10,
                    "remaining_percent": 90,
                    "resets_at": None,
                    "duration_minutes": 300,
                }
            ],
            "budgets": [],
            "error": None if self._ok else "unreachable",
            "read_at": None,
        }


def test_limits_service_marks_selected_providers():
    service = LimitsService([FakeSource("opencode"), FakeSource("codex")])

    body = service.snapshot(period="weekly", selected=["opencode"])

    assert body["period"] == "weekly"
    assert body["selected_providers"] == ["opencode"]
    by_id = {item["id"]: item for item in body["providers"]}
    assert by_id["opencode"]["selected"] is True
    assert by_id["codex"]["selected"] is False


def test_limits_service_none_selection_selects_all():
    service = LimitsService([FakeSource("opencode"), FakeSource("codex")])

    body = service.snapshot(selected=None)

    assert all(item["selected"] for item in body["providers"])
    assert body["ok"] is True


def test_limits_service_marks_selected_windows():
    service = LimitsService([FakeSource("opencode"), FakeSource("codex")])

    body = service.snapshot(selected_windows=["codex:rolling"])

    assert body["selected_windows"] == ["codex:rolling"]
    by_id = {item["id"]: item for item in body["providers"]}
    assert by_id["opencode"]["windows"][0]["selected"] is False
    assert by_id["codex"]["windows"][0]["selected"] is True
    assert by_id["codex"]["windows"][0]["key"] == "codex:rolling"
