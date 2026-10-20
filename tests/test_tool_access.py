"""Permission is checked next to the call, not asked for in a prompt."""

import pytest

from agentcp import agents, tools
from agentcp.graph import build_graph
from agentcp.state import new_state
from agentcp.tools import AccessDenied, ToolNotFound


def test_agent_can_call_its_own_tools():
    assert tools.invoke("triage", "read_document", {})["title"] == "calibration procedure"


def test_agent_cannot_call_another_agents_tool():
    with pytest.raises(AccessDenied) as e:
        tools.invoke("assessor", "publish", {})
    assert "publish" in str(e.value)


def test_deploy_is_reachable_only_by_the_deployer():
    allowed = [a for a, t in tools.ACCESS.items() if "publish" in t]
    assert allowed == ["publisher"]


def test_unknown_tool_raises():
    with pytest.raises(ToolNotFound):
        tools.invoke("triage", "no_such_tool", {})


def test_a_raising_tool_degrades_instead_of_crashing(exploding_tool):
    exploding_tool("read_document")
    out = tools.invoke("triage", "read_document", {})
    assert "error" in out and "upstream down" in out["error"]


def test_schemas_offered_match_the_allow_list():
    """A tool must never be advertised to an agent that cannot run it."""
    for agent, allowed in tools.ACCESS.items():
        offered = {s["function"]["name"] for s in tools.schemas_for(agent)}
        assert offered == set(allowed), agent


def test_unknown_agent_is_offered_nothing():
    assert tools.schemas_for("intruder") == []


def test_a_tenant_rule_narrows_what_the_role_allows():
    assert "publish" in tools.allowed("publisher")
    assert "publish" not in tools.allowed("publisher", "trial")


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
        tools.invoke("publisher", "publish", {}, "trial")
    assert "trial" in str(exc.value)


def test_the_deployer_refuses_rather_than_crashing_on_a_tenant_denial():
    """An approval already given must not be lost to a stack trace."""
    from agentcp.state import new_state

    state = new_state("document_submitted", {"document": 1}, tenant="trial")
    state["human_decision"] = {"approve": True}
    patch = agents.publisher_node(state)
    assert patch["publish_report"]["published"] is False
    assert "may not call 'publish'" in patch["publish_report"]["reason"]


def test_a_tools_error_is_not_handed_to_a_model_as_if_it_were_data(exploding_tool):
    """Containing a failure is not the same as proceeding past it.

    ``invoke`` converts an exception into ``{"error": ...}`` so a broken
    tool degrades one step instead of killing a run that may be holding
    an approval. But nothing read that key, so the error object became
    the judge's context: asked to review ``error: RuntimeError: ...``,
    the model answered, the answer looked exactly like a review of a real
    draft, and the run published to production on zero data.

    ``consult`` now refuses first, which is why the spy below is never
    called at all.
    """
    exploding_tool("read_draft")
    asked = []

    def spy(prompt, context):
        asked.append(prompt)
        return {"approved": True, "comments": [], "text": "looks fine"}

    app = build_graph(judge=spy)
    cfg = {"configurable": {"thread_id": "tool-error"}}
    out = app.invoke(
        new_state("document_submitted", {"document": 42, "draft": 7}, trace_id="tool-error"), cfg
    )

    assert "review draft" not in asked, "the model was asked to judge an error string"
    assert out["assessment_report"]["approved"] is False
    assert "upstream tool failed" in out["assessment_report"]["refused"]
    assert "publish_report" not in out
    assert app.get_state(cfg).next == ()

    refused = [c for c in out["calls"] if c["refused"]]
    assert [c["agent"] for c in refused] == ["assessor"]
    assert refused[0]["tokens_estimated"] == 0
