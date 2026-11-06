from baton.adapters.opencode import OpenCodeAdapter


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def reply_permission(self, session_id, request_id, decision):
        self.calls.append(("reply", session_id, request_id, decision))
        return True

    async def prompt(self, session_id, text):
        self.calls.append(("prompt", session_id, text))
        return True

    async def interrupt(self, session_id):
        self.calls.append(("interrupt", session_id))
        return True


def make_adapter():
    adapter = OpenCodeAdapter(
        session_id="ses_1",
        name="Sesión",
        model="model",
        cwd=r"C:\dev",
        endpoint=lambda: ("http://127.0.0.1:1234", {}),
    )
    client = FakeClient()
    adapter._client = lambda: client
    return adapter, client


async def test_adapter_maps_permission_decisions():
    adapter, client = make_adapter()

    await adapter.respond("oc_per_1", "allow")
    await adapter.respond("oc_per_2", "deny")

    assert client.calls == [
        ("reply", "ses_1", "per_1", "once"),
        ("reply", "ses_1", "per_2", "reject"),
    ]


async def test_adapter_sends_prompt_and_interrupts():
    adapter, client = make_adapter()

    assert await adapter.send_text("hola") is True
    assert await adapter.interrupt() is True

    assert client.calls == [
        ("prompt", "ses_1", "hola"),
        ("interrupt", "ses_1"),
    ]
