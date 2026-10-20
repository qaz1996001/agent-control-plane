*English ｜ [繁體中文](scope.zh-TW.md)*

# Scope — what is here, what is not, and why

This repository reimplements the decisions of a larger agent platform I
built at work. That system's capability surface is considerably wider
than this one's. Writing down the difference is the point of this page.

A demo that lists only what it does is hard to read as engineering
judgement, because the interesting question is never "what did you
build" — it is "what did you decline to build, and could you say why at
the time". Everything below was a decision, not an omission. Where
something is missing because it is genuinely hard to demonstrate
offline, that is stated as the reason rather than dressed up as taste.

The grouping is deliberate: the things this implements are all
*control-plane* properties — who may do what, where data may go, when
the run stops. The things it does not implement are mostly *data-plane*
concerns — what to retrieve, what to remember, how to score an answer.
That line is where I drew the repository's boundary.

---

## What this implements

Each row is a mechanism, not a feature, and each is pinned by tests that
fail if the property stops holding.

| Property | Mechanism | Pinned by |
|---|---|---|
| A trigger routes the same way every time | `ROUTE_TABLE` lookup, no default | `test_routing.py` |
| No model is reachable from the routing decision | injected `Judge`, poisoned in the test | `test_routing.py` |
| A cycle cannot outlast the step guard | fixed precedence in `next_node` | `test_routing.py`, `test_handoff.py` |
| An agent calls only its own tools | `ACCESS` checked inside `invoke` | `test_tool_access.py` |
| The two readings of the tool table cannot drift | `schemas_for` and `invoke` share `allowed()` | `test_tool_access.py` |
| A tenant rule can narrow a role, never widen it | `TENANT_DENY` subtracts from `ACCESS` | `test_tool_access.py` |
| Nothing publishes without a human | `interrupt_before=["approval_gate"]` | `test_hitl.py` |
| Absence of a decision is not consent | refusal lives inside the publisher | `test_hitl.py` |
| The model never sees real identifiers | `privacy.mask` before the call | `test_privacy.py`, `test_audit.py` |
| Unmasking is a permission, not a step | `privacy.restore` refuses outright | `test_privacy.py` |
| Restricted content does not leave the deployment | locality veto in `providers.choose` | `test_providers.py` |
| Failover may cross cost, never locality | filter order in `providers.choose` | `test_providers.py` |
| Every model call goes through one door | `agents.consult` | `test_audit.py` |
| Every call leaves a record, refusals included | `audit.CallRecord` | `test_audit.py`, `test_quota.py` |
| The estimate never survives in the ledger | `BudgetedStream.settle` → `audit.settle` | `test_budget.py`, `test_audit.py` |
| The budget cuts a stream on the chunk that crosses | per-chunk counting in `BudgetedStream` | `test_budget.py` |
| One tenant cannot spend another's allowance | `quota.Ledger` keyed by tenant | `test_quota.py` |
| An over-quota error says when to retry | `QuotaExceeded.retry_after` | `test_quota.py` |
| A gate blocks per metric, not on a blend | `THRESHOLDS` | `test_evals.py` |
| A diagnostic metric never gates | `UNGATED` | `test_evals.py` |
| A missing metric fails rather than passing | `metrics.get(name, 0.0)` | `test_evals.py` |
| Raising a bar does not rewrite old verdicts | policy snapshot in `GateResult` | `test_evals.py` |
| "Not enough data" is a third answer, not "ok" | `MIN_WINDOW`, zero-variance guard | `test_drift.py` |
| Required durability fails loudly | `build_graph(durability="require")` | `test_durability.py` |

Two of those deserve a note, because they are the ones that changed the
shape of the code rather than adding to it.

**One door to the model.** `agents.consult` is the only place a `Judge`
is called, and a test asserts it. Masking, provider selection, the
budget, the quota and the audit record all live behind that one call, so
a new node gets them by construction. The alternative — each node
remembering to mask, then remembering to charge the quota — is a rule
every node must follow, which is a rule some node eventually will not.
The same reasoning produced the single-egress gateway in the original
system; it is the decision I would keep if I could keep only one.

**The unmasking map never enters state.** Graph state is checkpointed.
A checkpoint holding the mapping from `<EMAIL_1>` back to a real address
would undo the masking at rest, which is where data actually sits. So
`Consultation.mapping` is returned in process and dropped; restoring is
something the caller does for a viewer it has authorised, at the moment
of display.

---

## What it deliberately does not implement

### Guardrails: injection detection, output filtering, prompt-leak checks

The original system had all three, and the numbers that justified them
came from measuring catch rate against real traffic.

Offline, with no model and no adversary, a filter can only be tested
against the examples its own patterns were written from. That test
always passes, and it means nothing. Shipping one here would add the
most reassuring-looking directory in the repository and the least
honest one.

This is the clearest case on the page of something left out because the
demonstration would be fake, not because the capability is unimportant.

### A scorer behind the eval gate

`run_gate` takes metrics and decides. It does not produce them.

Producing them — a golden set, a retrieval run, faithfulness scoring —
is the larger half of the work and needs a live system to score against.
What is portable without one is the gate's *policy*: thresholds per
metric, one metric deliberately ungated, a missing metric counting as
zero, and the policy snapshotted into the verdict. Those are the parts
that were decided rather than measured, so those are the parts here.

### Knowledge lifecycle and tiering

The original had a multi-state lifecycle for knowledge items, with only
the canonical tier retrievable and the rule enforced at the gateway
rather than in the application.

That enforcement point is a control-plane decision and a good one, and
it is the half that is here: "the guard belongs where it cannot be
bypassed, not where each caller is trusted to apply it" is what `ACCESS`
and the locality veto are. The lifecycle itself is not here, and this
page cannot wave that away by saying the domain has no use for one —
this domain plainly does. It is left out for a narrower reason. The
pipeline has the lifecycle in miniature already: a document is held at
the gate and then written to one live tier, which is one transition, not
a modelled state machine. The states the original adds exist to control
what a query can see, and nothing here issues a query — so "only the
canonical tier is retrievable" would be a rule with no observable
consequence, pinned by a test that exercised nothing. Offline, that
demonstration would be empty.

### Retrieval: hybrid search, rank fusion, reranking

Genuinely interesting, and not control plane. Which documents come back
for a query does not change who may publish.

### Fine-tuning and few-shot libraries

Out of scope in the original too, for a reason that still applies: in a
domain where a wrong answer is expensive, traceability is worth more
than marginal accuracy, and tuned weights make "why did it say that"
harder to answer.

### Sandboxing

The allow-list authorises; it does not contain. A tool that is permitted
runs in process with everything the process can reach. Real isolation is
a container or a separate process plus a network policy — an operational
concern this repository has no way to demonstrate and should not pretend
to cover.

### Concurrency, queueing, retry with backoff

Single run, single thread. Retry and idempotent replay are the subject
of a companion repository (`idemingest`) and duplicating them here would
make both worse.

---

## Where the implementations stop short

Stated here rather than in a footnote, because a demo that hides its
edges is not useful.

**Masking is rule matching, not NER.** Addresses, internal hostnames and
handles, by pattern. A real deployment needs a model-based detector for
names and free-text identifiers. The *mechanism* — mask before, restore
after, permission in between — does not change when the detector gets
better; only recall does.

**The quota ledger is per process.** Two workers each get a full
allowance, so the real ceiling is the limit times the worker count.
Shared enforcement needs a shared counter, which needs a store. The
exception shape and the per-tenant keying are the parts worth showing;
the store is not.

**Provider health is a module constant, not an input and not a
measurement.** `providers.choose` does take the set of providers its
caller believes are up — but the pipeline's caller cannot supply one.
`agents.HEALTHY` is a module-level constant and `build_graph` has no
parameter that injects a health view, so the set is a parameter of
`choose` alone, which `test_providers.py` and the `residency` scenario
call directly. That constant is where a real deployment attaches its own
health view, and a production version also tracks failures per provider
and half-opens after a cooldown. The simplification is in where health
comes from, not in the ordering rules.

**Nothing here streams, so no spend check can be mid-flight.**
`BudgetedStream`'s per-chunk guard is correct and pinned, but `consult`
receives a complete `dict` from the `Judge` and `_chunks` re-slices it, so
the guard counts a reply that has already arrived. The budget and the
quota are both pre-call gates — symmetric by construction, and the ledger
is charged after the judge returns — which means an exhausted allowance
refuses the next call, not the one in flight. That is a property of a
one-shot `Judge` contract, not a gap in either mechanism: the only check
that can save money is the one before the call.

**Complexity routing uses context length as a proxy.** Crude, and
visible in one constant (`HIGH_COMPLEXITY_CHARS`) rather than buried.

**No real model is called in the test suite.** `examples/gemma_judge.py`
puts a local model behind the judgement seam, but the suite stays offline
so that "the control plane runs with every model entry point poisoned"
remains assertable.

**The diagrams are Chinese-only.** `docs/architecture.md` is in English
and embeds the same four SVGs as its Chinese counterpart. The prose and
the Mermaid diagrams are bilingual; the generated SVGs are not. This is
an inconsistency, not a decision — it is recorded here so it stops being
an invisible one.

---

## What would change these answers

Non-goals should come with the condition that reopens them, or they are
just preferences.

| Not done | Would reconsider when |
|---|---|
| Guardrail filters | There is a live endpoint and real traffic to measure catch rate against — the number is the deliverable, not the regex |
| A scorer | There is a golden set worth more than the effort of hand-curating it, which in practice means real queries to sample from |
| Shared quota | More than one worker, which is the first moment the per-process ceiling becomes wrong rather than merely approximate |
| Durable checkpointing by default | Any deployment where a pause outlives a process — the hook (`durability="require"`) is already there and already refuses to pretend |
| NER-based masking | Free-text identifiers appear in the inputs; patterns cover structured ones adequately and nothing else |
| Sandboxing | A tool does anything but read, or a tool's arguments come from outside the control plane |
| An injectable provider health view | Any provider can actually go down — the moment a hard-coded `HEALTHY` is *wrong* rather than merely fixed, it becomes a `build_graph` parameter, for the same reason the quota counter becomes shared: the process has stopped being the whole system |

---

## Provenance

The system this draws on is private and none of its code is here. What
carried over is the reasoning, written up in [`design.md`](design.md).
Two of the decisions above — single egress for model calls, and a
locality veto that refuses rather than degrades — came out of
requirements I can describe but not show: a deployment where some data
was not permitted to leave the site at all.
