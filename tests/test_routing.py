"""Routing is a table lookup, and that is the whole point."""

import pytest

from agentcp import router
from agentcp.router import ROUTE_TABLE, UnknownTrigger, route
from agentcp.state import new_state


def test_same_trigger_always_routes_to_same_agent():
    for trigger in ROUTE_TABLE:
        assert len({route(trigger) for _ in range(50)}) == 1


def test_every_trigger_in_the_type_has_a_route():
    from agentcp.state import Trigger
    declared = set(Trigger.__args__)
    assert declared == set(ROUTE_TABLE), declared ^ set(ROUTE_TABLE)


def test_unknown_trigger_raises_instead_of_defaulting():
    with pytest.raises(UnknownTrigger) as e:
        route("ticket_opend")           # typo
    assert "ticket_opend" in str(e.value)


def test_routing_touches_no_model(monkeypatch):
    """The control plane must work with every model entry point poisoned."""
    def forbidden(*a, **k):
        raise AssertionError("control flow called a model")

    import agentcp.agents as agents_mod
    monkeypatch.setattr(agents_mod, "_default_severity", forbidden)
    monkeypatch.setattr(agents_mod, "_default_verdict", forbidden)

    for trigger in ROUTE_TABLE:
        assert route(trigger) in {"triage", "planner", "reviewer", "deployer"}


def test_step_budget_outranks_a_pending_handoff():
    s = new_state("ticket_opened", max_steps=3)
    s["step_count"] = 3
    s["next_agent"] = "planner"
    s["requires_approval"] = True          # even this loses to the guard
    assert router.next_node(s) == "__end__"


def test_approval_outranks_handoff():
    s = new_state("ticket_opened")
    s["next_agent"] = "deployer"
    s["requires_approval"] = True
    assert router.next_node(s) == "approval_gate"


def test_no_handoff_means_stop():
    assert router.next_node(new_state("ticket_opened")) == "__end__"
