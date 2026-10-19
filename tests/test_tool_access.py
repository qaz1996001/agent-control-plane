"""Permission is checked next to the call, not asked for in a prompt."""

import pytest

from agentcp import agents, tools
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


def test_a_tenant_rule_narrows_what_the_role_allows():
    assert "deploy" in tools.allowed("deployer")
    assert "deploy" not in tools.allowed("deployer", "trial")


def test_a_tenant_rule_can_only_subtract_never_grant():
    """No (agent, tenant) pair exceeds what the role itself allows."""
    tenants = ["default", *tools.TENANT_DENY]
    for agent, role_tools in tools.ACCESS.items():
        for tenant in tenants:
            assert tools.allowed(agent, tenant) <= role_tools


def test_schemas_match_the_allow_list_for_every_agent_and_tenant():
    tenants = ["default", *tools.TENANT_DENY]
    for agent in tools.ACCESS:
        for tenant in tenants:
            offered = {s["function"]["name"] for s in tools.schemas_for(agent, tenant)}
            assert offered == tools.allowed(agent, tenant), (agent, tenant)


def test_invoking_a_tool_withheld_from_the_tenant_is_denied():
    with pytest.raises(tools.AccessDenied) as exc:
        tools.invoke("deployer", "deploy", {}, "trial")
    assert "trial" in str(exc.value)


def test_the_deployer_refuses_rather_than_crashing_on_a_tenant_denial():
    """An approval already given must not be lost to a stack trace."""
    from agentcp.state import new_state

    state = new_state("ticket_opened", {"ticket": 1}, tenant="trial")
    state["human_decision"] = {"approve": True}
    patch = agents.deployer_node(state)
    assert patch["deploy_report"]["deployed"] is False
    assert "may not call 'deploy'" in patch["deploy_report"]["reason"]
