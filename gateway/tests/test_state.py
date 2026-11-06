from baton.protocol import AgentStatus, Risk
from baton.state import InvalidTransition, StateStore


def make_store() -> StateStore:
    store = StateStore(log_buffer=10, log_tail=3)
    store.register("a1", "Agente", provider="test", model="m")
    return store


def test_same_status_keeps_since():
    store = make_store()
    store.set_status("a1", AgentStatus.RUNNING)
    since = store.get("a1").since
    store.set_status("a1", AgentStatus.RUNNING, task="nueva tarea")
    assert store.get("a1").since == since
    assert store.get("a1").task == "nueva tarea"


def test_transition_is_validated():
    store = make_store()
    store.set_status("a1", AgentStatus.DONE)
    try:
        store.set_status("a1", AgentStatus.WAITING_INPUT)
    except InvalidTransition:
        pass
    else:  # pragma: no cover
        raise AssertionError("DONE -> WAITING_INPUT debería ser inválida")


def test_leaving_waiting_input_clears_approval():
    store = make_store()
    store.set_status("a1", AgentStatus.WAITING_INPUT)
    store.attach_approval("a1", "apr_1", "rm -rf build", Risk.HIGH)
    store.set_status("a1", AgentStatus.RUNNING)
    agent = store.get("a1")
    assert agent.approval_id is None
    assert agent.prompt is None
    assert agent.risk is None


def test_clear_approval_falls_back_to_idle():
    store = make_store()
    store.set_status("a1", AgentStatus.WAITING_INPUT)
    store.attach_approval("a1", "apr_1", "test", Risk.NORMAL)
    store.clear_approval("a1")
    assert store.get("a1").status is AgentStatus.IDLE


def test_snapshot_includes_risk_details():
    store = make_store()
    store.set_status("a1", AgentStatus.WAITING_INPUT)
    store.attach_approval(
        "a1",
        "apr_1",
        "git clean -fdx",
        Risk.HIGH,
        ["borrado de ficheros no versionados"],
        ["Borra archivos que no están en Git."],
    )
    view = store.snapshot().agents[0]
    assert view.risk_reasons == ["borrado de ficheros no versionados"]
    assert view.risk_details == ["Borra archivos que no están en Git."]


def test_snapshot_orders_waiting_first_and_counts():
    store = StateStore(log_buffer=10, log_tail=2)
    store.register("run", "Run")
    store.register("wait", "Wait")
    store.register("err", "Err")
    store.set_status("run", AgentStatus.RUNNING)
    store.set_status("wait", AgentStatus.WAITING_INPUT)
    store.set_status("err", AgentStatus.ERROR)
    store.set_usage("run", cost_session=0.25, tokens_session=1000)

    snapshot = store.snapshot()
    assert [a.id for a in snapshot.agents] == ["wait", "err", "run"]
    assert snapshot.system.waiting_agents == 1
    assert snapshot.system.active_agents == 2
    assert snapshot.system.total_cost == 0.25
    assert snapshot.system.total_tokens == 1000
    assert snapshot.seq == 1


def test_snapshot_seq_is_monotonic():
    store = make_store()
    assert store.snapshot().seq == 1
    assert store.snapshot().seq == 2


def test_log_tail_is_bounded():
    store = StateStore(log_buffer=10, log_tail=2)
    store.register("a1", "Agente")
    for i in range(5):
        store.log("a1", f"linea {i}")
    assert list(store.get("a1").view(2).log_tail) == ["linea 3", "linea 4"]
