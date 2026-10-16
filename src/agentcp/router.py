"""Deterministic routing.

The control plane does not ask a model what to do next. ``trigger`` maps to
an agent through a table, and that is the whole decision.

Two consequences worth stating, because they are the reason for the design:

- A run is replayable. The same trigger lands on the same agent every time,
  so a failed run can be re-driven and compared against the original.
- A wrong route is a table bug, not a prompt bug. It is findable by reading
  one dict, and fixable without evals.

An unknown trigger raises. Guessing a default is how a typo silently becomes
a deploy.
"""

from __future__ import annotations

from agentcp.state import Agent, PipelineState, Trigger

ROUTE_TABLE: dict[str, Agent] = {
    "ticket_opened": "triage",
    "ticket_reopened": "triage",
    "plan_ready": "planner",
    "code_pushed": "reviewer",
    "review_requested": "reviewer",
    "review_changes_requested": "planner",
    "review_passed": "deployer",
    "deploy_requested": "deployer",
    "deploy_failed": "triage",
}


class UnknownTrigger(KeyError):
    """Raised for a trigger with no table entry."""


def route(trigger: Trigger | str) -> Agent:
    """Return the agent for *trigger*.

    Raises
    ------
    UnknownTrigger
        No entry exists. Deliberately not a default — an unrecognised
        trigger is a contract violation, not a routing preference.
    """
    try:
        return ROUTE_TABLE[trigger]
    except KeyError:
        raise UnknownTrigger(
            f"no route for {trigger!r}; known triggers: {sorted(ROUTE_TABLE)}"
        ) from None


def next_node(state: PipelineState) -> str:
    """Decide where the graph goes after the current node.

    Precedence, highest first:

    1. ``step_count >= max_steps`` -> stop. The guard outranks everything,
       including a pending handoff, so a cycle cannot outvote it.
    2. ``requires_approval`` -> the human gate.
    3. ``next_agent`` -> explicit handoff set by the agent that just ran.
    4. otherwise -> stop.
    """
    if state.get("step_count", 0) >= state.get("max_steps", 8):
        return "__end__"
    if state.get("requires_approval"):
        return "approval_gate"
    nxt = state.get("next_agent")
    return nxt if nxt else "__end__"
