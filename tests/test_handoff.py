"""Hand-off is explicit, and the step guard cannot be out-voted."""

from agentcp import router
from agentcp.agents import deployer_node, planner_node, reviewer_node, triage_node
from agentcp.state import new_state


def test_each_agent_writes_only_its_own_report():
    reports = {"triage_report", "plan_report", "review_report", "deploy_report"}
    for fn, own in [
        (triage_node, "triage_report"),
        (planner_node, "plan_report"),
        (reviewer_node, "review_report"),
        (deployer_node, "deploy_report"),
    ]:
        patch = fn(new_state("ticket_opened", {"ticket": 1, "pr": 2}))
        assert reports & patch.keys() == {own}, fn.__name__


def test_every_node_advances_the_step_count_and_trail():
    s = new_state("ticket_opened", {"ticket": 1, "pr": 2})
    patch = triage_node(s)
    assert patch["step_count"] == 1
    assert patch["completed"] == ["triage"]


def test_a_rejecting_review_hands_back_to_the_planner():
    patch = reviewer_node(
        new_state("review_requested", {"pr": 7}),
        judge=lambda p, c: {"approved": False, "comments": ["missing tests"]},
    )
    assert patch["next_agent"] == "planner"
    assert not patch.get("requires_approval")


def test_a_cycle_cannot_run_forever():
    """planner <-> reviewer would loop; max_steps ends it."""
    s = new_state("ticket_opened", {"ticket": 1, "pr": 2}, max_steps=4)
    s["next_agent"] = "planner"
    seen = []
    for _ in range(20):
        if router.next_node(s) == "__end__":
            break
        s["step_count"] += 1
        seen.append(s["step_count"])
        s["next_agent"] = "reviewer" if s["step_count"] % 2 else "planner"
    assert len(seen) == 4


def test_state_is_still_coherent_after_hitting_the_guard():
    s = new_state("ticket_opened", max_steps=2)
    s["step_count"] = 2
    s["next_agent"] = "planner"
    assert router.next_node(s) == "__end__"
    assert s["next_agent"] == "planner"      # untouched, inspectable afterwards
