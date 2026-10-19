"""Pipeline state — the I/O contract every agent shares.

The contract is explicit on purpose. Each agent writes exactly one
``*_report`` key and never reads another agent's internals, so a reviewer
can tell from this file alone what any node is allowed to produce.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

Trigger = Literal[
    "ticket_opened",
    "ticket_reopened",
    "plan_ready",
    "code_pushed",
    "review_requested",
    "review_passed",
    "review_changes_requested",
    "deploy_requested",
    "deploy_failed",
]

Agent = Literal["triage", "planner", "reviewer", "deployer", "approval_gate"]

#: Keys no node may write. Four of them are the run's constraints, fixed
#: at :func:`new_state`; the fifth is the human's decision, which may only
#: arrive by resuming an interrupted run.
#:
#: This is a list of names because the enforcement is one check at one
#: place -- :func:`agentcp.graph.build_graph` wraps every node and raises
#: if a patch names one of these. Before that wrapper existed, every
#: field here was writable by any node, and "no agent can set
#: ``human_decision``" was a description of the nodes that happened to
#: exist rather than a property of the graph. ``agents`` says it plainly:
#: a rule that every node must remember to follow is a rule that a new
#: node will not follow.
#:
#: ``next_agent`` is deliberately absent. Handing off is what a node is
#: *for*, so it cannot be protected; the gate is not what stops a node
#: routing straight to the deployer -- the deployer's own refusal is,
#: because without a human decision on record there is nothing to act on.
PROTECTED: frozenset[str] = frozenset(
    {"human_decision", "max_steps", "sensitivity", "tenant", "trace_id"}
)


class PipelineState(TypedDict, total=False):
    """State flowing through the graph.

    Attributes
    ----------
    trigger : Trigger
        The event that started this run. The router reads only this.
    payload : dict
        Event-specific data. Agents read it; the router never does.
    triage_report, plan_report, review_report, deploy_report : dict
        One slot per agent. An agent writes only its own slot.
    next_agent : Agent or None
        Set by an agent to hand off. Absent means "stop after me".
    requires_approval : bool
        Set by an agent that wants a human to look before the next step.
    human_decision : dict or None
        ``{"approve": bool, "reason": str}``. Populated only by resuming
        an interrupted run — never by an agent.
    step_count, max_steps : int
        Runaway guard. The graph stops when step_count reaches max_steps.
    completed : list[str]
        Append-only audit trail of node names, in execution order.
    budget_tokens, tokens_used : int
        Output-token budget for the whole run, charged by every model
        call the run makes.
    trace_id : str
        Ties this run's call records, mask mappings and logs together.
    tenant : str
        Whose run this is. Narrows the tool allow-list and picks the
        quota the run is charged against.
    sensitivity : str
        ``"open"`` or ``"restricted"``. Restricted runs may not reach a
        remote provider; see :mod:`agentcp.providers`.
    calls : list[dict]
        Append-only ledger, one entry per model call. Same shape of
        guarantee as ``completed``: later nodes add, never rewrite.
    """

    trigger: Trigger
    payload: dict
    triage_report: dict
    plan_report: dict
    review_report: dict
    deploy_report: dict
    next_agent: Agent | None
    requires_approval: bool
    human_decision: dict | None
    step_count: int
    max_steps: int
    completed: Annotated[list[str], operator.add]
    budget_tokens: int
    tokens_used: int
    trace_id: str
    tenant: str
    sensitivity: str
    calls: Annotated[list[dict], operator.add]


def new_state(trigger: Trigger, payload: dict | None = None, **kw) -> PipelineState:
    """Build a run's initial state with the guards already set.

    Every guard gets a value here rather than being defaulted at the
    point of use. A guard that is absent and a guard that is set to its
    default should not be the same thing to read.
    """
    base: PipelineState = {
        "trigger": trigger,
        "payload": payload or {},
        "step_count": 0,
        "max_steps": kw.pop("max_steps", 8),
        "completed": [],
        "budget_tokens": kw.pop("budget_tokens", 2000),
        "tokens_used": 0,
        "trace_id": kw.pop("trace_id", None) or uuid4().hex[:12],
        "tenant": kw.pop("tenant", "default"),
        "sensitivity": kw.pop("sensitivity", "open"),
        "calls": [],
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base
