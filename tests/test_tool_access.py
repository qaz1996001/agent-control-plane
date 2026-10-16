"""Permission is checked next to the call, not asked for in a prompt."""

import pytest

from agentcp import tools
from agentcp.tools import AccessDenied, ToolNotFound


def test_agent_can_call_its_own_tools():
    assert tools.invoke("triage", "read_ticket", {})["title"] == "login fails"


def test_agent_cannot_call_another_agents_tool():
    with pytest.raises(AccessDenied) as e:
        tools.invoke("reviewer", "deploy", {})
    assert "deploy" in str(e.value)


def test_deploy_is_reachable_only_by_the_deployer():
    allowed = [a for a, t in tools.ACCESS.items() if "deploy" in t]
    assert allowed == ["deployer"]


def test_unknown_tool_raises():
    with pytest.raises(ToolNotFound):
        tools.invoke("triage", "no_such_tool", {})


def test_a_raising_tool_degrades_instead_of_crashing(exploding_tool):
    exploding_tool("read_ticket")
    out = tools.invoke("triage", "read_ticket", {})
    assert "error" in out and "upstream down" in out["error"]


def test_schemas_offered_match_the_allow_list():
    """A tool must never be advertised to an agent that cannot run it."""
    for agent, allowed in tools.ACCESS.items():
        offered = {s["function"]["name"] for s in tools.schemas_for(agent)}
        assert offered == set(allowed), agent


def test_unknown_agent_is_offered_nothing():
    assert tools.schemas_for("intruder") == []
