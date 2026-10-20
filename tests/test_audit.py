import ast
import inspect

from langgraph.types import Command

from agentcp import agents, privacy, tools
from agentcp.graph import build_graph
from agentcp.state import new_state

CFG = {"configurable": {"thread_id": "audit-1"}}

#: Real values planted in a tool's output, so the judge's context and the
#: checkpoint both have something worth leaking.
REAL_EMAIL = "sam.okafor@example.com"
REAL_HOST = "db-prod-3.internal"


def run_to_gate(**kw):
    app = build_graph()
    app.invoke(new_state("document_submitted", {"document": 42, "draft": 7}, **kw), CFG)
    return app


def plant_pii_in_the_ticket():
    """Make ``read_document`` return PII, the way a real document store would.

    The PII enters through the tool rather than through ``payload``,
    because ``payload`` is caller-supplied identification that is
    checkpointed verbatim by design -- the masking boundary is the model,
    not our own datastore.
    """
    tools.register(
        tools.Tool(
            "read_document", "fake read_document", {"type": "object"},
            lambda a: {"title": "calibration procedure",
                       "body": f"ping {REAL_EMAIL} on {REAL_HOST}"},
        )
    )


def _everything_in(obj, path="state"):
    """Yield ``(path, value)`` for *obj* and everything nested inside it."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _everything_in(v, f"{path}[{k!r}]")
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for i, v in enumerate(obj):
            yield from _everything_in(v, f"{path}[{i}]")
    elif hasattr(obj, "__dataclass_fields__"):
        for f in obj.__dataclass_fields__:
            yield from _everything_in(getattr(obj, f), f"{path}.{f}")


def _functions_calling_the_injected_judge(module) -> list[str]:
    """Names of functions in *module* containing a call to ``judge``.

    An AST walk rather than a substring match, so it sees
    ``(judge or default)(...)``, a bare ``judge(...)``, and anything else
    whose callee expression mentions the injected judge.
    """
    tree = ast.parse(inspect.getsource(module))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            if any(isinstance(x, ast.Name) and x.id == "judge"
                   for x in ast.walk(call.func)):
                found.append(node.name)
                break
    return found


def test_every_model_consulting_node_leaves_exactly_one_record():
    app = run_to_gate()
    state = app.get_state(CFG).values
    assert [c["agent"] for c in state["calls"]] == ["triage", "assessor"]


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
    state = new_state("document_submitted", {"document": 1}, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x" * 60},
        lambda prompt, ctx: {"text": "y" * 60, "tokens": 7},
        agents._default_severity,
    )
    assert call.record.tokens_actual == 7
    assert call.record.tokens_charged == 7
    assert call.record.tokens_estimated != 7


def test_an_unsettled_record_is_distinguishable_from_a_settled_one():
    state = new_state("document_submitted", {"document": 1}, trace_id="t-1")
    call = agents.consult(
        state, "triage", "p", {"a": "x"},
        lambda prompt, ctx: {"text": "short"},
        agents._default_severity,
    )
    assert call.record.tokens_actual is None
    assert call.record.tokens_charged == call.record.tokens_estimated


def test_a_response_cut_by_the_budget_still_leaves_a_record():
    state = new_state("document_submitted", {"document": 1}, budget_tokens=2, trace_id="t-1")
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
    state = new_state("document_submitted", {"document": 1}, budget_tokens=2, trace_id="t-1")
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
        "document_submitted", {"document": 1},
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


def test_a_budget_refusal_stops_the_run_rather_than_publishing():
    app = build_graph()
    cfg = {"configurable": {"thread_id": "audit-budget"}}
    out = app.invoke(
        new_state("document_submitted", {"document": 42, "draft": 7},
                  budget_tokens=1, trace_id="t-budget"),
        cfg,
    )
    assert out["triage_report"]["severity"] == "unknown"
    assert "budget" in out["triage_report"]["refused"]
    assert "publish_report" not in out
    assert app.get_state(cfg).next == ()


def test_a_refused_call_still_leaves_a_record():
    state = new_state("document_submitted", {"document": 1}, sensitivity="restricted", trace_id="t-1")
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

    state = new_state("document_submitted", {"document": 1}, trace_id="t-1")
    agents.consult(
        state, "triage", "p",
        {"body": "ping sam.okafor@example.com on db-prod-3.internal"},
        spy, agents._default_severity,
    )
    assert "sam.okafor@example.com" not in seen["text"]
    assert "db-prod-3.internal" not in seen["text"]
    assert "<EMAIL_1>" in seen["text"]


def test_the_unmasking_map_never_reaches_checkpointed_state():
    """State is persisted; a map of real values in it would undo masking.

    The run really does build such a map -- the ``masked`` flag on its
    records is the proof, and it is asserted first so this cannot pass by
    there being nothing to leak. What the assertion then looks for is the
    map itself, anywhere in the checkpoint: a :class:`privacy.Mapping`,
    or any dict keyed by the placeholders it hands out.
    """
    plant_pii_in_the_ticket()
    app = build_graph()
    cfg = {"configurable": {"thread_id": "audit-leak"}}
    app.invoke(new_state("document_submitted", {"document": 42, "draft": 7}, trace_id="t-leak"), cfg)
    values = app.get_state(cfg).values

    assert any(c["masked"] for c in values["calls"]), "nothing was masked to leak"
    leaked = [
        path
        for path, obj in _everything_in(values)
        if isinstance(obj, privacy.Mapping)
        or (isinstance(obj, dict)
            and any(privacy.PLACEHOLDER.fullmatch(str(k)) for k in obj))
    ]
    assert leaked == [], leaked


def test_the_judge_sees_only_masked_context_for_every_call_in_a_run():
    """Masking is on the path to the model, not bolted onto one call site.

    Asserted over a whole graph run rather than a direct ``consult``, so
    it covers every node that consults rather than the one the test
    happened to pick.
    """
    plant_pii_in_the_ticket()
    seen: list[str] = []

    def spy(prompt, context):
        seen.append(context["text"])
        return {"severity": "normal", "approved": True, "comments": [], "text": "ok"}

    build_graph(judge=spy).invoke(
        new_state("document_submitted", {"document": 42, "draft": 7}, trace_id="t-mask"),
        {"configurable": {"thread_id": "audit-mask"}},
    )

    assert len(seen) == 2
    assert not [t for t in seen if REAL_EMAIL in t or REAL_HOST in t]
    assert "<EMAIL_1>" in seen[0] and "<HOST_1>" in seen[0]


def test_only_consult_contains_a_call_to_the_injected_judge():
    """A second model entry point would bypass mask, budget and audit."""
    assert _functions_calling_the_injected_judge(agents) == ["consult"]


def test_every_judge_call_in_a_run_went_through_consult():
    """The source check says where the door is; this says nobody climbed in.

    Counting both sides is the real claim: a node that reached a judge
    without going through :func:`agents.consult` would make the judge's
    count exceed the door's.
    """
    consults = []
    judgements = []
    real_consult = agents.consult

    def counting_consult(*a, **k):
        consults.append(1)
        return real_consult(*a, **k)

    def spy(prompt, context):
        judgements.append(prompt)
        return {"severity": "normal", "approved": True, "comments": [], "text": "ok"}

    agents.consult = counting_consult
    try:
        build_graph(judge=spy).invoke(
            new_state("document_submitted", {"document": 42, "draft": 7}, trace_id="t-door"),
            {"configurable": {"thread_id": "audit-door"}},
        )
    finally:
        agents.consult = real_consult

    assert judgements, "the judge was never called, so there is nothing to account for"
    assert len(judgements) == len(consults)


def test_approve_path_records_no_call_for_the_gate_or_publisher():
    app = run_to_gate()
    app.invoke(Command(update={"human_decision": {"approve": True}}), CFG)
    state = app.get_state(CFG).values
    assert {c["agent"] for c in state["calls"]} == {"triage", "assessor"}
    assert state["publish_report"]["published"] is True
