"""Human approval is a pause in the graph, not a flag someone remembers."""

from langgraph.types import Command

from agentcp.graph import build_graph
from agentcp.state import new_state

CFG = {"configurable": {"thread_id": "t1"}}


def _run_to_gate(app, cfg):
    app.invoke(new_state("document_submitted", {"document": 42, "draft": 7}), cfg)
    return app.get_state(cfg)


def test_run_actually_stops_at_the_gate():
    app = build_graph()
    snap = _run_to_gate(app, CFG)
    assert snap.next == ("approval_gate",), snap.next
    assert "publisher" not in snap.values["completed"]


def test_nothing_is_published_while_the_run_is_paused():
    app = build_graph()
    snap = _run_to_gate(app, CFG)
    assert "publish_report" not in snap.values


def test_approval_lets_the_run_finish_and_publish():
    app = build_graph()
    cfg = {"configurable": {"thread_id": "approve"}}
    _run_to_gate(app, cfg)
    out = app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
    assert out["publish_report"]["published"] is True
    assert out["completed"].count("approval_gate") == 1


def test_rejection_finishes_the_run_without_publishing():
    app = build_graph()
    cfg = {"configurable": {"thread_id": "reject"}}
    _run_to_gate(app, cfg)
    out = app.invoke(
        Command(update={"human_decision": {"approve": False, "reason": "needs tests"}}), cfg
    )
    assert out["publish_report"]["published"] is False
    assert "no human approval" in out["publish_report"]["reason"]


def test_resuming_with_no_decision_still_refuses_to_publish():
    """Absence of a decision is not consent.

    Resuming with ``None`` is LangGraph's "continue, no changes" form -- the
    operator clicked through without deciding. The publisher must still refuse.
    """
    app = build_graph()
    cfg = {"configurable": {"thread_id": "empty"}}
    _run_to_gate(app, cfg)
    out = app.invoke(None, cfg)
    assert out["publish_report"]["published"] is False
    assert "no human approval" in out["publish_report"]["reason"]


def test_the_assessor_cannot_approve_on_the_humans_behalf():
    """A machine-approved review sets requires_approval, never human_decision."""
    from agentcp.agents import assessor_node
    patch = assessor_node(new_state("assessment_requested", {"draft": 7}))
    assert patch["requires_approval"] is True
    assert "human_decision" not in patch
