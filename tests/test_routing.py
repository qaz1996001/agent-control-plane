"""Routing is a table lookup, and that is the whole point."""

import pytest

from agentcp import agents, graph, router
from agentcp.router import ROUTE_TABLE, UnknownTrigger, route
from agentcp.state import Agent, new_state


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


def test_every_route_points_at_a_node_the_graph_actually_has():
    """A route to a non-node must fail in CI, not at ``invoke``.

    The table and the graph are declared in different modules, so nothing
    but this stops one from naming an agent the other does not build.
    """
    unknown = set(ROUTE_TABLE.values()) - set(graph.NODE_NAMES)
    assert not unknown, unknown


def test_the_node_registry_and_the_graph_agree_on_which_nodes_exist():
    """``agents.NODES`` is what gets built; ``NODE_NAMES`` is what gets wired."""
    assert set(agents.NODES) == set(graph.NODE_NAMES)


def test_the_agent_type_and_the_graph_agree_on_which_nodes_exist():
    """A handoff is typed ``Agent``, so the type must name exactly the nodes."""
    assert set(Agent.__args__) == set(graph.NODE_NAMES)


def test_step_budget_outranks_a_pending_handoff():
    s = new_state("document_submitted", max_steps=3)
    s["step_count"] = 3
    s["next_agent"] = "indexer"
    s["requires_approval"] = True          # even this loses to the guard
    assert router.next_node(s) == "__end__"


def test_approval_outranks_handoff():
    s = new_state("document_submitted")
    s["next_agent"] = "publisher"
    s["requires_approval"] = True
    assert router.next_node(s) == "approval_gate"


def test_no_handoff_means_stop():
    assert router.next_node(new_state("document_submitted")) == "__end__"
