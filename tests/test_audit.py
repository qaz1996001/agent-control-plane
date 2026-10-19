import inspect

from langgraph.types import Command

from agentcp import agents, privacy
from agentcp.graph import build_graph
from agentcp.state import new_state

CFG = {"configurable": {"thread_id": "audit-1"}}


def run_to_gate(**kw):
    app = build_graph()
    app.invoke(new_state("ticket_opened", {"ticket": 42, "pr": 7}, **kw), CFG)
    return app


def test_every_model_consulting_node_leaves_exactly_one_record():
    app = run_to_gate()
    state = app.get_state(CFG).values
    assert [c["agent"] for c in state["calls"]] == ["triage", "reviewer"]


def test_a_record_names_the_provider_and_why_it_was_chosen():
    app = run_to_gate()
    record = app.get_state(CFG).values["calls"][0]
    assert record["provider"] == "local-small"
    assert record["route_reason"]


def test_the_run_token_counter_is_actually_charged():
    """budget_tokens / tokens_used are live, not decorative."""
    app = run_to_gate()
    state = app.get_state(CFG).values
    assert state["tokens_used"] == sum(
        c["tokens_actual"] if c["tokens_actual"] is not None else c["tokens_estimated"]
        for c in state["calls"]
    )
    assert state["tokens_used"] > 0


def test_the_estimate_is_replaced_by_the_providers_count():
    state = new_state("ticket_opened", {"ticket": 1}, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x" * 60},
        lambda prompt, ctx: {"text": "y" * 60, "tokens": 7},
        agents._default_severity,
    )
    assert call.record.tokens_actual == 7
    assert call.record.tokens_charged == 7
    assert call.record.tokens_estimated != 7


def test_an_unsettled_record_is_distinguishable_from_a_settled_one():
    state = new_state("ticket_opened", {"ticket": 1}, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x"},
        lambda prompt, ctx: {"text": "short"},
        agents._default_severity,
    )
    assert call.record.tokens_actual is None
    assert call.record.tokens_charged == call.record.tokens_estimated


def test_a_response_cut_by_the_budget_still_leaves_a_record():
    state = new_state("ticket_opened", {"ticket": 1}, budget_tokens=2, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x"},
        lambda prompt, ctx: {"text": "z" * 400},
        agents._default_severity,
    )
    assert call.record.truncated is True
    assert call.record.tokens_estimated > 0


def test_a_cut_response_is_refused_not_used():
    """A truncated judgement is not a judgement.

    Its structured fields survive the cut, so nothing stops the verdict
    being used -- except this. An answer the model had not finished
    giving reads exactly like one it had.
    """
    state = new_state("ticket_opened", {"ticket": 1}, budget_tokens=2, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x"},
        lambda prompt, ctx: {"severity": "critical", "text": "z" * 400},
        agents._default_severity,
    )
    assert call.record.truncated is True
    assert call.refused
    assert call.verdict == {}   # refused means there is no answer to use


def test_an_exhausted_budget_refuses_before_the_judge_is_called():
    """The only refusal that saves money, so it has to come first.

    A one-shot judge has generated and been billed for its whole answer
    by the time it returns. Refusing afterwards refuses the answer;
    refusing here refuses the spend.
    """
    called = []
    state = new_state(
        "ticket_opened", {"ticket": 1},
        budget_tokens=10, tokens_used=10, trace_id="t-1",
    )
    call = agents.consult(
        state, "triage", "p", {"a": "x"},
        lambda prompt, ctx: called.append(1) or {"text": "never generated"},
        agents._default_severity,
    )
    assert called == []
    assert "no token budget left" in call.refused
    assert call.record.tokens_estimated == 0
    assert call.record.truncated is False


def test_a_budget_refusal_stops_the_run_rather_than_deploying():
    app = build_graph()
    cfg = {"configurable": {"thread_id": "audit-budget"}}
    out = app.invoke(
        new_state("ticket_opened", {"ticket": 42, "pr": 7},
                  budget_tokens=1, trace_id="t-budget"),
        cfg,
    )
    assert out["triage_report"]["severity"] == "unknown"
    assert "budget" in out["triage_report"]["refused"]
    assert "deploy_report" not in out
    assert app.get_state(cfg).next == ()


def test_a_refused_call_still_leaves_a_record():
    state = new_state("ticket_opened", {"ticket": 1}, sensitivity="restricted", trace_id="t-1")
    original = agents.HEALTHY
    agents.HEALTHY = frozenset({"cloud-small"})
    try:
        call = agents.consult(
            state, "triage", "p", {"a": "x"},
            lambda prompt, ctx: {"text": "never runs"},
            agents._default_severity,
        )
    finally:
        agents.HEALTHY = original
    assert call.refused
    assert call.record.refused == call.refused
    assert call.record.provider == "none"


def test_the_judge_only_ever_sees_masked_text():
    seen = {}

    def spy(prompt, context):
        seen["text"] = context["text"]
        return {"text": "ok"}

    state = new_state("ticket_opened", {"ticket": 1}, trace_id="t-1")
    agents.consult(
        state, "triage", "p",
        {"body": "ping sam.okafor@example.com on db-prod-3.internal"},
        spy, agents._default_severity,
    )
    assert "sam.okafor@example.com" not in seen["text"]
    assert "db-prod-3.internal" not in seen["text"]
    assert "<EMAIL_1>" in seen["text"]


def test_the_unmasking_map_never_reaches_checkpointed_state():
    """State is persisted; a map of real values in it would undo masking."""
    app = build_graph()
    cfg = {"configurable": {"thread_id": "audit-leak"}}
    app.invoke(
        new_state(
            "ticket_opened",
            {"ticket": 42, "pr": 7, "reporter": "sam.okafor@example.com"},
            trace_id="t-leak",
        ),
        cfg,
    )
    blob = repr(app.get_state(cfg).values)
    _, mapping = privacy.mask("sam.okafor@example.com", "t-leak")
    assert "pairs" not in blob
    assert not any(k.startswith("<EMAIL") for k in blob.split())


def test_consult_is_the_only_place_a_judge_is_called():
    """A second model entry point would bypass mask, budget and audit."""
    callers = [
        name
        for name, fn in vars(agents).items()
        if callable(fn) and getattr(fn, "__module__", "") == agents.__name__
        and "(judge or " in inspect.getsource(fn)
    ]
    assert callers == ["consult"]


def test_approve_path_records_no_call_for_the_gate_or_deployer():
    app = run_to_gate()
    app.invoke(Command(update={"human_decision": {"approve": True}}), CFG)
    state = app.get_state(CFG).values
    assert {c["agent"] for c in state["calls"]} == {"triage", "reviewer"}
    assert state["deploy_report"]["deployed"] is True
