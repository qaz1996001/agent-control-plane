"""Hand-off is explicit, and the step guard cannot be out-voted."""

from agentcp import router
from agentcp.agents import assessor_node, indexer_node, publisher_node, triage_node
from agentcp.state import new_state


def test_each_agent_writes_only_its_own_report():
    reports = {"triage_report", "index_report", "assessment_report", "publish_report"}
    for fn, own in [
        (triage_node, "triage_report"),
        (indexer_node, "index_report"),
        (assessor_node, "assessment_report"),
        (publisher_node, "publish_report"),
    ]:
        patch = fn(new_state("document_submitted", {"document": 1, "draft": 2}))
        assert reports & patch.keys() == {own}, fn.__name__


def test_every_node_advances_the_step_count_and_trail():
    s = new_state("document_submitted", {"document": 1, "draft": 2})
    patch = triage_node(s)
    assert patch["step_count"] == 1
    assert patch["completed"] == ["triage"]


def test_a_rejecting_assessment_hands_back_to_the_indexer():
    patch = assessor_node(
        new_state("assessment_requested", {"draft": 7}),
        judge=lambda p, c: {"approved": False, "comments": ["missing tests"]},
    )
    assert patch["next_agent"] == "indexer"
    assert not patch.get("requires_approval")


def test_a_cycle_cannot_run_forever():
    """indexer <-> assessor would loop; max_steps ends it."""
    s = new_state("document_submitted", {"document": 1, "draft": 2}, max_steps=4)
    s["next_agent"] = "indexer"
    seen = []
    for _ in range(20):
        if router.next_node(s) == "__end__":
            break
        s["step_count"] += 1
        seen.append(s["step_count"])
        s["next_agent"] = "assessor" if s["step_count"] % 2 else "indexer"
    assert len(seen) == 4


def test_state_is_still_coherent_after_hitting_the_guard():
    s = new_state("document_submitted", max_steps=2)
    s["step_count"] = 2
    s["next_agent"] = "indexer"
    assert router.next_node(s) == "__end__"
    assert s["next_agent"] == "indexer"      # untouched, inspectable afterwards
