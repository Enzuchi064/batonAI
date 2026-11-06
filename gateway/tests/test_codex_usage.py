from baton.codex_usage import normalize


def rate_window(used: int, minutes: int, resets: int = 1_800_000_000) -> dict:
    return {
        "usedPercent": used,
        "windowDurationMins": minutes,
        "resetsAt": resets,
    }


def payload(primary: dict | None, secondary: dict | None, **extra) -> dict:
    rate = {
        "planType": "go",
        "primary": primary,
        "secondary": secondary,
        "credits": {"hasCredits": False, "unlimited": False, "balance": None},
        "individualLimit": None,
    }
    rate.update(extra)
    return {"result": {"rateLimits": rate, "rateLimitsByLimitId": {"codex": rate}}}


def test_normalize_rolling_and_weekly_windows():
    body = normalize(payload(rate_window(38, 300), rate_window(12, 10_080)))

    assert body["ok"] is True
    assert body["plan"] == "go"
    assert [window["id"] for window in body["windows"]] == ["rolling", "weekly"]
    assert [window["label"] for window in body["windows"]] == [
        "Rolling",
        "Semanal",
    ]
    assert body["windows"][0]["used_percent"] == 38
    assert body["windows"][0]["remaining_percent"] == 62


def test_normalize_monthly_window_for_free_plan():
    body = normalize(payload(rate_window(0, 43_200), None))

    assert len(body["windows"]) == 1
    window = body["windows"][0]
    assert window["id"] == "monthly"
    assert window["label"] == "Mensual"
    assert window["duration_minutes"] == 43_200
    assert window["remaining_percent"] == 100


def test_normalize_sorts_windows_by_period():
    body = normalize(payload(rate_window(0, 43_200), rate_window(20, 10_080)))

    assert [window["id"] for window in body["windows"]] == [
        "weekly",
        "monthly",
    ]


def test_normalize_does_not_treat_spend_control_as_monthly():
    individual = {
        "limit": "100.00",
        "remainingPercent": 73,
        "resetsAt": 1_800_000_000,
        "used": "27.00",
    }
    body = normalize(
        payload(
            rate_window(10, 300),
            None,
            individualLimit=individual,
        )
    )

    assert [window["id"] for window in body["windows"]] == ["rolling"]
    assert body["spend_control"] == {
        "remaining_percent": 73,
        "used_percent": 27,
        "limit": "100.00",
        "used": "27.00",
        "resets_at": 1_800_000_000,
    }


def test_normalize_deduplicates_multi_bucket_windows():
    primary = rate_window(5, 300, resets=111)
    secondary = rate_window(15, 10_080, resets=222)
    body = normalize(payload(primary, secondary))

    assert len(body["windows"]) == 2
    assert [window["resets_at"] for window in body["windows"]] == [111, 222]


def test_normalize_handles_missing_result():
    body = normalize({"error": "boom"})

    assert body["ok"] is False
    assert body["error"] == "invalid_response"
