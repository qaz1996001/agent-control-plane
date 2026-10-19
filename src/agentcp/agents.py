"""The four agent nodes, and the one door they use to reach a model.

Each node is a plain function with the same shape: read state, do work,
return a patch containing its own report and an optional handoff. Nothing
here decides the route; that lives in the router.

A node that needs judgement does not call a model and does not call the
injected ``Judge`` directly -- it goes through :func:`consult`. That
function is the only model entry point in the package, which is what
makes masking, provider selection, the token budget, the quota and the
audit record *unavoidable* rather than conventions each node is trusted
to remember. A rule that every node must remember to follow is a rule
that a new node will not follow.

Injection is also what lets the tests assert that the control plane runs
with no model reachable at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from agentcp import privacy, providers, quota, tools
from agentcp.audit import CallRecord, settle
from agentcp.budget import BudgetExceeded, BudgetedStream
from agentcp.state import PipelineState

#: Chunk size the provider's prose is streamed in. Small enough that the
#: budget guard bites part-way through a response rather than after it.
CHUNK_CHARS = 20

#: Above this many characters of context, the work is treated as needing
#: the capable model. A crude proxy, and deliberately a visible one.
HIGH_COMPLEXITY_CHARS = 200

#: Per-tenant spend for this process. Reset between tests.
LEDGER = quota.Ledger()

#: Providers believed to be up. A real deployment replaces this with a
#: health view; the selection rules it feeds do not change.
HEALTHY: frozenset[str] = providers.ALL_HEALTHY

#: Keys a ``Judge`` may return to report on the call rather than answer
#: it: ``tokens`` is the provider's real usage count, which :func:`consult`
#: settles the estimate against, and ``provider`` is what actually
#: answered. Both land in the :class:`~agentcp.audit.CallRecord` and are
#: stripped from the verdict, so a node's report stays a report.
_JUDGE_META: frozenset[str] = frozenset({"tokens", "provider"})


class Judge(Protocol):
    """A model-backed decision. Injected so it can be faked in tests."""

    def __call__(self, prompt: str, context: dict) -> dict: ...


@dataclass
class Consultation:
    """The outcome of one trip through :func:`consult`.

    ``mapping`` deliberately does not go into graph state. State is
    checkpointed, and a checkpoint holding the real values behind the
    placeholders would undo the masking at rest. It lives in process,
    for as long as the caller needs to restore the answer for someone
    entitled to see it.
    """

    verdict: dict
    record: CallRecord
    mapping: privacy.Mapping
    refused: str = ""


def _chunks(text: str, size: int = CHUNK_CHARS):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _flatten(context: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in context.items())


def consult(
    state: PipelineState,
    agent: str,
    prompt: str,
    context: dict,
    judge: Judge | None,
    default: Callable[[str, dict], dict],
) -> Consultation:
    """The only way a node reaches a model.

    Masks the context, picks a provider, runs the judgement under the
    run's remaining token budget, settles the estimate against the
    provider's count, charges the tenant's quota and writes one audit
    record -- in that order, every time.

    Never raises for a refusal. A refused call still produces a record,
    so the ledger shows the attempt; the caller reads ``refused``.
    """
    trace_id = state.get("trace_id", "")
    tenant = state.get("tenant", tools.DEFAULT_TENANT)
    sensitivity = state.get("sensitivity", "open")

    blob = _flatten(context)
    masked_blob, mapping = privacy.mask(blob, trace_id)
    complexity = "high" if len(masked_blob) > HIGH_COMPLEXITY_CHARS else "low"

    def refusal(reason: str, provider_name: str = "none") -> Consultation:
        return Consultation(
            verdict={},
            record=CallRecord(
                trace_id=trace_id,
                agent=agent,
                provider=provider_name,
                sensitivity=sensitivity,
                route_reason=reason,
                tokens_estimated=0,
                masked=bool(mapping),
                refused=reason,
            ),
            mapping=mapping,
            refused=reason,
        )

    try:
        choice = providers.choose(sensitivity, complexity, HEALTHY)
    except providers.NoEligibleProvider as exc:
        return refusal(str(exc))

    if LEDGER.remaining(tenant) <= 0:
        return refusal(f"tenant {tenant!r} has no quota left", choice.provider.name)

    # The judge only ever sees the masked text.
    verdict = (judge or default)(prompt, {"text": masked_blob})

    # What the budget is charged for. A judge that answers in structured
    # fields and no prose still cost tokens to produce, so bill the
    # serialised answer rather than recording the call as free.
    text = verdict.get("text")
    if text is None:
        text = json.dumps(
            {k: v for k, v in verdict.items() if k not in _JUDGE_META}, ensure_ascii=False
        )
    text = str(text)

    remaining = max(0, state.get("budget_tokens", 0) - state.get("tokens_used", 0))
    stream = BudgetedStream(_chunks(text), remaining)
    emitted: list[str] = []
    truncated = False
    try:
        for chunk in stream:
            emitted.append(chunk)
    except BudgetExceeded:
        truncated = True

    record = CallRecord(
        trace_id=trace_id,
        agent=agent,
        provider=choice.provider.name,
        sensitivity=sensitivity,
        route_reason=choice.reason,
        tokens_estimated=stream.used,
        provider_used=str(verdict.get("provider") or ""),
        masked=bool(mapping),
        truncated=truncated,
    )

    reported = verdict.get("tokens")
    if isinstance(reported, int):
        stream.settle(reported)
        record = settle(record, reported)

    refused = ""
    try:
        LEDGER.charge(tenant, record.tokens_charged)
    except quota.QuotaExceeded as exc:
        refused = str(exc)
        record = CallRecord(**{**record.as_dict(), "refused": refused})

    # The meta keys are facts about the *call*, and the record is where
    # call facts live. Leaving them in the verdict would copy them into
    # the node's report as well, where they would be a second, staler
    # answer to a question the ledger already answers.
    verdict = {k: v for k, v in verdict.items() if k not in _JUDGE_META}
    if "text" in verdict:
        # Only rewrite prose the judge actually returned; a structured
        # answer must not grow a field it never had.
        verdict["text"] = "".join(emitted)
    return Consultation(verdict=verdict, record=record, mapping=mapping, refused=refused)


def _advance(state: PipelineState, node: str) -> dict:
    """Common bookkeeping: count the step, append to the audit trail."""
    return {
        "step_count": state.get("step_count", 0) + 1,
        "completed": [*state.get("completed", []), node],
    }


def _bill(patch: dict, state: PipelineState, call: Consultation) -> dict:
    """Append the call record and charge its tokens to the run."""
    patch["calls"] = [*state.get("calls", []), call.record.as_dict()]
    patch["tokens_used"] = state.get("tokens_used", 0) + call.record.tokens_charged
    return patch


def triage_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Classify the ticket and decide whether it needs a plan."""
    patch = _advance(state, "triage")
    ticket = tools.invoke(
        "triage", "read_ticket", {"id": state["payload"].get("ticket")},
        state.get("tenant", tools.DEFAULT_TENANT),
    )
    call = consult(state, "triage", "classify severity", ticket, judge, _default_severity)
    _bill(patch, state, call)
    if call.refused:
        patch["triage_report"] = {"severity": "unknown", "refused": call.refused}
        patch["next_agent"] = None
        return patch
    patch["triage_report"] = {
        "severity": call.verdict.get("severity", "normal"),
        "ticket": ticket,
    }
    patch["next_agent"] = "planner"
    return patch


def planner_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Turn a triaged ticket into a plan.

    Takes no judgement: the plan is whatever the store says it is. The
    ``judge`` parameter is kept so every node has one shape.
    """
    patch = _advance(state, "planner")
    tenant = state.get("tenant", tools.DEFAULT_TENANT)
    plan = tools.invoke("planner", "write_plan", {"ticket": state["payload"].get("ticket")}, tenant)
    patch["plan_report"] = {"plan": plan}
    patch["next_agent"] = "reviewer"
    return patch


def reviewer_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Review the diff and decide whether it may proceed to deploy."""
    patch = _advance(state, "reviewer")
    tenant = state.get("tenant", tools.DEFAULT_TENANT)
    diff = tools.invoke("reviewer", "read_diff", {"pr": state["payload"].get("pr")}, tenant)
    call = consult(state, "reviewer", "review diff", diff, judge, _default_verdict)
    _bill(patch, state, call)
    if call.refused:
        patch["review_report"] = {"approved": False, "refused": call.refused}
        patch["next_agent"] = None
        return patch
    patch["review_report"] = call.verdict
    if call.verdict.get("approved"):
        # A machine-approved review still does not deploy by itself.
        patch["requires_approval"] = True
        patch["next_agent"] = "deployer"
    else:
        patch["next_agent"] = "planner"
    return patch


def deployer_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Deploy. Refuses unless a human approved this run.

    Takes no judgement. Whether to deploy is settled before this node
    runs, by a person.
    """
    patch = _advance(state, "deployer")
    decision = state.get("human_decision") or {}
    if not decision.get("approve"):
        patch["deploy_report"] = {"deployed": False, "reason": "no human approval on record"}
        patch["next_agent"] = None
        return patch
    try:
        result = tools.invoke(
            "deployer", "deploy", {"plan": state.get("plan_report", {})},
            state.get("tenant", tools.DEFAULT_TENANT),
        )
    except tools.AccessDenied as exc:
        # A tenant-level withholding is policy, not a caller bug: refuse
        # the deploy and say so, rather than ending the run in a stack
        # trace that loses the approval that was already given.
        patch["deploy_report"] = {"deployed": False, "reason": str(exc)}
        patch["next_agent"] = None
        return patch
    patch["deploy_report"] = {"deployed": True, "result": result}
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
    return {"severity": "normal", "text": "severity looks routine."}


def _default_verdict(prompt: str, context: dict) -> dict:
    return {"approved": True, "comments": [], "text": "diff reviewed, no blocking issues."}


NODES: dict[str, Callable[..., dict]] = {
    "triage": triage_node,
    "planner": planner_node,
    "reviewer": reviewer_node,
    "deployer": deployer_node,
    "approval_gate": approval_gate_node,
}
