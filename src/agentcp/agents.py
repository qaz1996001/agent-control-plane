"""The four agent nodes.

Each node is a plain function with the same shape: read state, do work,
return a patch containing its own report and an optional handoff. Nothing
here decides the route; that lives in the router.

A node that needs judgement takes a ``Judge`` callable instead of calling a
model directly. Injection is what lets the tests assert that the control
plane runs with no model reachable at all.
"""

from __future__ import annotations

from typing import Callable, Protocol

from agentcp import tools
from agentcp.state import PipelineState


class Judge(Protocol):
    """A model-backed decision. Injected so it can be faked in tests."""

    def __call__(self, prompt: str, context: dict) -> dict: ...


def _advance(state: PipelineState, node: str) -> dict:
    """Common bookkeeping: count the step, append to the audit trail."""
    return {
        "step_count": state.get("step_count", 0) + 1,
        "completed": [*state.get("completed", []), node],
    }


def triage_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Classify the ticket and decide whether it needs a plan."""
    patch = _advance(state, "triage")
    ticket = tools.invoke("triage", "read_ticket", {"id": state["payload"].get("ticket")})
    severity = (judge or _default_severity)("classify severity", ticket).get("severity", "normal")
    patch["triage_report"] = {"severity": severity, "ticket": ticket}
    patch["next_agent"] = "planner"
    return patch


def planner_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Turn a triaged ticket into a plan."""
    patch = _advance(state, "planner")
    plan = tools.invoke("planner", "write_plan", {"ticket": state["payload"].get("ticket")})
    patch["plan_report"] = {"plan": plan}
    patch["next_agent"] = "reviewer"
    return patch


def reviewer_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Review the diff and decide whether it may proceed to deploy."""
    patch = _advance(state, "reviewer")
    diff = tools.invoke("reviewer", "read_diff", {"pr": state["payload"].get("pr")})
    verdict = (judge or _default_verdict)("review diff", diff)
    patch["review_report"] = verdict
    if verdict.get("approved"):
        # A machine-approved review still does not deploy by itself.
        patch["requires_approval"] = True
        patch["next_agent"] = "deployer"
    else:
        patch["next_agent"] = "planner"
    return patch


def deployer_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Deploy. Refuses unless a human approved this run."""
    patch = _advance(state, "deployer")
    decision = state.get("human_decision") or {}
    if not decision.get("approve"):
        patch["deploy_report"] = {"deployed": False, "reason": "no human approval on record"}
        patch["next_agent"] = None
        return patch
    patch["deploy_report"] = {
        "deployed": True,
        "result": tools.invoke("deployer", "deploy", {"plan": state.get("plan_report", {})}),
    }
    patch["next_agent"] = None
    return patch


def approval_gate_node(state: PipelineState) -> dict:
    """Consume the human decision and clear the pending flag.

    The graph is compiled with ``interrupt_before`` on this node, so it does
    not execute until the run is resumed with a decision.
    """
    patch = _advance(state, "approval_gate")
    patch["requires_approval"] = False
    return patch


# -- defaults used when no judge is injected -------------------------------

def _default_severity(prompt: str, context: dict) -> dict:
    return {"severity": "normal"}


def _default_verdict(prompt: str, context: dict) -> dict:
    return {"approved": True, "comments": []}


NODES: dict[str, Callable[..., dict]] = {
    "triage": triage_node,
    "planner": planner_node,
    "reviewer": reviewer_node,
    "deployer": deployer_node,
    "approval_gate": approval_gate_node,
}
