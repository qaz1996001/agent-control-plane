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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agentcp import privacy, providers, quota, tools
from agentcp.audit import CallRecord, settle
from agentcp.budget import BudgetedStream, BudgetExceeded
from agentcp.state import PROTECTED, PipelineState

#: Chunk size the budget guard counts in. Nothing here streams: ``_chunks``
#: re-slices a reply that has already arrived whole, so the guard cuts the
#: accounting part-way, never the generation. The size is what a live
#: stream would be fed in, if one were ever wired to this seam.
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

#: Dropped from a verdict on the way out. A judge is free to *return*
#: these -- it is an injected callable and nothing can stop it naming a
#: control-plane field -- and the graph's guard already means the value
#: cannot reach state. But the verdict becomes the node's report, and a
#: report that carries ``human_decision: {"approve": true}`` as inert
#: payload reads alarming to the next person to open a checkpoint. The
#: field names are the control plane's, so they do not travel in an
#: answer.
_NOT_A_VERDICT: frozenset[str] = PROTECTED | {"next_agent", "requires_approval"}


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

    Refuses in five ways, and all five leave a record: the context is an
    upstream tool's error, no eligible provider, no tenant quota, no run
    budget left, and a response the budget cut short. The tool-error case
    comes first because there is nothing to judge: ``tools.invoke``
    converts an exception into ``{"error": ...}`` so a broken tool cannot
    kill a run holding an approval, but that only contains the failure --
    asking a model to review an error string gets an answer, and the
    answer reads exactly like a review of a real draft.

    The last two refusals are the same guard at two points. The budget is
    checked *before* the judge is called, because that is the only moment
    a refusal still saves money -- a one-shot judge has generated and been
    billed for its whole answer by the time it returns. Checking again
    afterwards cannot unspend those tokens, so what it does instead is
    refuse to *use* a half-finished answer.

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

    # Nothing to judge. The tool already degraded into an error object
    # rather than raising; this is the other half of that bargain --
    # containing a failure is not the same as proceeding past it.
    upstream = context.get("error") if isinstance(context, dict) else None
    if upstream:
        return refusal(f"upstream tool failed: {upstream}")

    try:
        choice = providers.choose(sensitivity, complexity, HEALTHY)
    except providers.NoEligibleProvider as exc:
        return refusal(str(exc))

    if LEDGER.remaining(tenant) <= 0:
        return refusal(f"tenant {tenant!r} has no quota left", choice.provider.name)

    # The only check that can still save money. Past this line the judge
    # has been called, and a judge that answers in one shot has already
    # generated -- and been billed for -- every token it is going to.
    # Counting afterwards can refuse the *answer*; only refusing here
    # refuses the *spend*.
    remaining = max(0, state.get("budget_tokens", 0) - state.get("tokens_used", 0))
    if remaining <= 0:
        return refusal(
            f"run has no token budget left ({state.get('tokens_used', 0)}"
            f"/{state.get('budget_tokens', 0)} used)",
            choice.provider.name,
        )

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

    if truncated and not refused:
        # A truncated judgement is not a judgement. Letting the verdict
        # through because its structured fields happen to be intact would
        # accept an answer the model had not finished giving -- and it
        # would read exactly like one it had. Same reason `restore`
        # refuses outright rather than restoring the part it can.
        refused = (
            f"response cut by the run's token budget at {record.tokens_charged} tokens"
        )

    if refused:
        record = CallRecord(**{**record.as_dict(), "refused": refused})
        # One contract for all four refusals: a refused call has no
        # verdict. The callers check ``refused`` first, but leaving a
        # usable-looking answer here for them to find anyway is how the
        # next node ends up using one.
        return Consultation(verdict={}, record=record, mapping=mapping, refused=refused)

    # The meta keys are facts about the *call*, and the record is where
    # call facts live. Leaving them in the verdict would copy them into
    # the node's report as well, where they would be a second, staler
    # answer to a question the ledger already answers.
    verdict = {k: v for k, v in verdict.items()
               if k not in _JUDGE_META and k not in _NOT_A_VERDICT}
    if "text" in verdict:
        # Only rewrite prose the judge actually returned; a structured
        # answer must not grow a field it never had.
        verdict["text"] = "".join(emitted)
    return Consultation(verdict=verdict, record=record, mapping=mapping, refused=refused)


def _advance(state: PipelineState, node: str) -> dict:
    """Common bookkeeping: count the step, append to the audit trail.

    ``completed`` carries only this node's name. The append is the
    reducer's job (``state.PipelineState``), not this function's -- which
    is the difference between a trail that *is* append-only and one that
    is append-only because every node remembers to splice rather than
    assign. ``step_count`` has no reducer and is still computed here,
    because a counter and a log want different merge rules.
    """
    return {
        "step_count": state.get("step_count", 0) + 1,
        "completed": [node],
    }


def _bill(patch: dict, state: PipelineState, call: Consultation) -> dict:
    """Add the call record to the ledger and charge its tokens to the run."""
    patch["calls"] = [call.record.as_dict()]
    patch["tokens_used"] = state.get("tokens_used", 0) + call.record.tokens_charged
    return patch


def triage_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Classify the document and decide whether it needs indexing."""
    patch = _advance(state, "triage")
    document = tools.invoke(
        "triage", "read_document", {"id": state["payload"].get("document")},
        state.get("tenant", tools.DEFAULT_TENANT),
    )
    call = consult(state, "triage", "classify severity", document, judge, _default_severity)
    _bill(patch, state, call)
    if call.refused:
        patch["triage_report"] = {"severity": "unknown", "refused": call.refused}
        patch["next_agent"] = None
        return patch
    patch["triage_report"] = {
        "severity": call.verdict.get("severity", "normal"),
        "document": document,
    }
    patch["next_agent"] = "indexer"
    return patch


def indexer_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Turn a triaged document into an index entry.

    Takes no judgement: the entry is whatever the store says it is. The
    ``judge`` parameter is kept so every node has one shape.
    """
    patch = _advance(state, "indexer")
    tenant = state.get("tenant", tools.DEFAULT_TENANT)
    entry = tools.invoke(
        "indexer", "write_index", {"document": state["payload"].get("document")}, tenant,
    )
    patch["index_report"] = {"entry": entry}
    patch["next_agent"] = "assessor"
    return patch


def assessor_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Review the draft and decide whether it may proceed to publish."""
    patch = _advance(state, "assessor")
    tenant = state.get("tenant", tools.DEFAULT_TENANT)
    draft = tools.invoke("assessor", "read_draft", {"draft": state["payload"].get("draft")}, tenant)
    call = consult(state, "assessor", "review draft", draft, judge, _default_verdict)
    _bill(patch, state, call)
    if call.refused:
        patch["assessment_report"] = {"approved": False, "refused": call.refused}
        patch["next_agent"] = None
        return patch
    patch["assessment_report"] = call.verdict
    if call.verdict.get("approved"):
        # A machine-approved review still does not publish by itself.
        patch["requires_approval"] = True
        patch["next_agent"] = "publisher"
    else:
        patch["next_agent"] = "indexer"
    return patch


def publisher_node(state: PipelineState, judge: Judge | None = None) -> dict:
    """Publish to the live index. Refuses unless a human approved this run.

    Takes no judgement. Whether to publish is settled before this node
    runs, by a person.
    """
    patch = _advance(state, "publisher")
    decision = state.get("human_decision") or {}
    if not decision.get("approve"):
        patch["publish_report"] = {"published": False, "reason": "no human approval on record"}
        patch["next_agent"] = None
        return patch
    try:
        result = tools.invoke(
            "publisher", "publish", {"entry": state.get("index_report", {})},
            state.get("tenant", tools.DEFAULT_TENANT),
        )
    except tools.AccessDenied as exc:
        # A tenant-level withholding is policy, not a caller bug: refuse
        # the publish and say so, rather than ending the run in a stack
        # trace that loses the approval that was already given.
        patch["publish_report"] = {"published": False, "reason": str(exc)}
        patch["next_agent"] = None
        return patch
    patch["publish_report"] = {"published": True, "result": result}
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
    return {"approved": True, "comments": [], "text": "draft assessed, no blocking findings."}


NODES: dict[str, Callable[..., dict]] = {
    "triage": triage_node,
    "indexer": indexer_node,
    "assessor": assessor_node,
    "publisher": publisher_node,
    "approval_gate": approval_gate_node,
}
