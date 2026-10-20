"""What a node may and may not write.

These tests exist because the claim they pin used to be false. The docs
said "no agent can set ``human_decision``, which is what makes 'the
assessor cannot approve on the human's behalf' a structural property
rather than a convention" -- and it was a convention. ``PipelineState``
was a bare ``TypedDict`` and ``build_graph`` passed node patches through
untouched, so any node could forge the human's consent, relax the runaway
guard, drop the residency veto, escape its tenant, or erase the audit
trail. Nothing broke only because no node happened to try.

Each test below has been checked the only way this kind of test can be
checked: remove the mechanism, confirm the test goes red, put it back.
A guard with a test that passes either way is worse than no test, because
it reads like evidence.
"""

from __future__ import annotations

import pytest
from langgraph.types import Command

from agentcp import agents
from agentcp.graph import ProtectedFieldWritten, build_graph
from agentcp.state import PROTECTED, new_state


def _rogue(node: str, patch_extra: dict):
    """Replace *node* with one that also writes *patch_extra*."""
    original = agents.NODES[node]

    def rogue(state, judge=None):
        patch = original(state, judge)
        patch.update(patch_extra)
        return patch

    return original, rogue


def _run(thread: str, **state_kw):
    app = build_graph()
    cfg = {"configurable": {"thread_id": thread}}
    out = app.invoke(
        new_state("document_submitted", {"document": 42, "draft": 7}, trace_id=thread, **state_kw),
        cfg,
    )
    return app, cfg, out


@pytest.mark.parametrize("field", sorted(PROTECTED))
def test_a_node_cannot_write_a_protected_field(field):
    """Every name in PROTECTED, not just the one that motivated the list.

    Parametrised deliberately: a guard that covers four of five fields is
    the same bug in a smaller place, and a hand-written test per field
    would be the thing that gets forgotten when the list grows.
    """
    original, rogue = _rogue("indexer", {field: "anything"})
    agents.NODES["indexer"] = rogue
    try:
        with pytest.raises(ProtectedFieldWritten) as caught:
            _run(f"protect-{field}")
        assert field in str(caught.value)
    finally:
        agents.NODES["indexer"] = original


def test_a_node_cannot_forge_the_human_decision_and_publish():
    """The whole point, stated as the attack it prevents.

    Before the guard: a node wrote ``human_decision`` itself, the run
    still paused at the gate, and resuming with *no* decision published to
    production -- passing straight through the check that
    ``test_resuming_with_no_decision_still_refuses_to_publish`` claims to
    pin, because by then a decision was on record.
    """
    original, rogue = _rogue(
        "indexer", {"human_decision": {"approve": True, "reason": "the agent decided"}}
    )
    agents.NODES["indexer"] = rogue
    try:
        with pytest.raises(ProtectedFieldWritten):
            _run("forge-decision")
    finally:
        agents.NODES["indexer"] = original


def test_routing_straight_to_the_publisher_still_does_not_publish():
    """``next_agent`` is not protected, and does not need to be.

    Handing off is what a node is *for*, so the guard cannot cover it: a
    node can still send a run directly to the publisher, skipping the gate
    entirely. What stops the publish is not the gate but the publisher's own
    refusal -- with no human decision on record there is nothing to act
    on, and the decision is the field that cannot be forged.
    """
    original, rogue = _rogue("triage", {"next_agent": "publisher"})
    agents.NODES["triage"] = rogue
    try:
        _app, _cfg, out = _run("skip-the-gate")
        assert out["completed"] == ["triage", "publisher"]
        assert out["publish_report"]["published"] is False
        assert "no human approval" in out["publish_report"]["reason"]
    finally:
        agents.NODES["triage"] = original


def test_a_node_cannot_rewrite_the_audit_trail():
    """``completed`` is append-only because the reducer appends.

    The previous arrangement had every node splice the list itself
    (``[*state["completed"], node]``), which is append-only exactly as
    long as each node remembers to splice rather than assign. A node
    returning ``completed=["indexer"]`` erased triage's record of itself.
    """
    original, rogue = _rogue("indexer", {"completed": ["indexer"]})
    agents.NODES["indexer"] = rogue
    try:
        _app, _cfg, out = _run("erase-trail")
        assert out["completed"][0] == "triage"
        assert out["completed"].count("indexer") == 1
    finally:
        agents.NODES["indexer"] = original


def test_a_node_cannot_erase_another_nodes_call_record():
    """``calls`` carries the same guarantee, and only that guarantee.

    The ledger answers "which provider saw this, and was it masked first"
    after something goes wrong, so a later node dropping an earlier one's
    record would make it a claim rather than a record. The reducer stops
    that: the rogue assessor below returns ``calls=[]`` and triage's entry
    survives.

    What it does *not* stop, and what this test is written to be honest
    about: a node can still decline to report its own call, because its
    own contribution is what it returns. That is a weaker problem -- the
    node can only omit itself, never rewrite the record of another -- and
    fixing it would mean `consult` writing the ledger rather than handing
    the record back, which is a different design. Named in the assertion
    rather than left for a reader to discover.
    """
    original, rogue = _rogue("assessor", {"calls": []})
    agents.NODES["assessor"] = rogue
    try:
        _app, _cfg, out = _run("erase-ledger")
        assert [c["agent"] for c in out["calls"]] == ["triage"]
    finally:
        agents.NODES["assessor"] = original


def test_an_ordinary_run_appends_each_node_exactly_once():
    """The reducer must not double-count what the node already reported.

    This is the failure mode the change introduced risk of: with
    ``operator.add`` on ``completed``, a node that still spliced the
    existing list would append the whole history again every step.
    """
    app, cfg, _out = _run("append-once")
    out = app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
    assert out["completed"] == [
        "triage", "indexer", "assessor", "approval_gate", "publisher",
    ]
    assert out["step_count"] == 5
    assert [c["agent"] for c in out["calls"]] == ["triage", "assessor"]


def test_the_gate_goes_through_the_same_guard_as_every_other_node():
    """The gate is a node, so the protection is not a property it opts into.

    It is the one node registered without a judge, which is exactly the
    kind of special case that used to mean "registered without the
    wrapper" too.
    """
    original = agents.NODES["approval_gate"]

    def rogue_gate(state):
        patch = original(state)
        patch["tenant"] = "someone-else"
        return patch

    agents.NODES["approval_gate"] = rogue_gate
    try:
        app, cfg, _out = _run("guard-the-gate")
        with pytest.raises(ProtectedFieldWritten):
            app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
    finally:
        agents.NODES["approval_gate"] = original
