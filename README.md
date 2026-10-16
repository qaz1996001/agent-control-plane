*English ｜ [繁體中文](README.zh-TW.md)*

# agent-control-plane — let the model decide inside a step, never between steps

A runnable demonstration of one position: **an agent pipeline's control
plane should be ordinary code.** Routing, permissions, budget and human
approval are a lookup table, an allow-list, a counter and an interrupt —
not things a model is asked to get right.

```bash
uv run --with pytest --with langgraph pytest -q      # 44 passed
```

Built on LangGraph for the runtime (node execution, checkpointing, and the
interrupt that makes approval a real pause). The routing policy is a plain
function over state, so it is testable without building a graph.

The domain is a software-delivery pipeline — Ticket → Plan → Review →
Deploy — because that is the case where "the agent decided to deploy" is a
bad sentence to have to say.

---

## The problem

Give an LLM the control flow and you get a system where:

- the same input can take a different path tomorrow, so a failed run cannot
  be replayed and compared;
- a wrong route is a prompt bug — you fix it by rewording and re-running
  evals, not by reading one line;
- "which tools may this step use" is a sentence in a prompt, which is a
  request rather than a check;
- a deploy can happen because a model was persuaded that it should.

None of that is an argument against using models. It is an argument about
*where*.

## The decision

| | Model decides the route | Table decides the route |
|---|---|---|
| Same trigger, tomorrow | may differ | identical |
| A wrong route is | a prompt bug | a one-line table bug |
| Replaying a failed run | approximate | exact |
| Proving "no model ran here" | not possible | a test |

The model still does the work that needs judgement — classify this ticket,
review this diff. Those are injected callables (`Judge`), which is also
what makes "the control plane ran with every model entry point poisoned"
an assertion rather than a claim.

### Four properties, four mechanisms

**Routing** — `ROUTE_TABLE` maps trigger → agent. An unknown trigger
raises; it does not fall back to a default. A typo that silently routed to
`deployer` is exactly the failure worth preventing.

**Permissions** — `ACCESS` maps agent → allowed tools, checked in `invoke`
right next to the call. The schemas offered to a model are generated from
the same table, so what is advertised and what is permitted cannot drift
apart. A tool that raises is converted to `{"error": ...}` so one bad tool
degrades a step instead of killing a run that is holding an approval.

**Budget** — `BudgetedStream` counts tokens per chunk and raises the moment
the budget is crossed, mid-stream. It estimates, because it has to decide
before the provider reports; `settle()` then replaces the estimate with the
real count so the audit record is not left holding the approximation.

**Approval** — the graph is compiled with
`interrupt_before=["approval_gate"]`. A run that reaches the gate stops and
is checkpointed. Nothing deploys until someone resumes it with a decision,
and resuming *without* a decision still refuses — absence of a decision is
not consent.

---

## What the tests prove

The tests are the deliverable; the implementation is small on purpose.

**Routing** (`test_routing.py`)
- Every trigger in the `Trigger` type has a route, and every route has a
  trigger — the type and the table cannot drift
- Fifty lookups of the same trigger give one answer
- A typo'd trigger raises and names the valid set
- **The control plane runs with every model entry point monkeypatched to
  raise** — if routing ever consulted a model, this test fails
- The step guard outranks a pending hand-off *and* a pending approval, so a
  cycle cannot out-vote it

**Permissions** (`test_tool_access.py`)
- An agent calling another agent's tool is denied
- `deploy` is reachable from exactly one agent, asserted by inspection
- A raising tool returns `{"error": ...}` instead of propagating
- **Schemas offered to an agent equal its allow-list, for every agent**
- An unknown agent is offered nothing

**Approval** (`test_hitl.py`)
- The run genuinely stops: `snapshot.next == ("approval_gate",)` and no
  `deploy_report` exists yet
- Approve → deploys; reject → finishes without deploying, with a reason
- **Resuming with no decision still refuses**
- A machine-approved review sets `requires_approval` and never writes
  `human_decision` — the reviewer cannot approve on the human's behalf

**Hand-off** (`test_handoff.py`)
- Each agent writes exactly one `*_report` key and no other agent's
- A rejecting review hands back to the planner
- A planner ↔ reviewer cycle stops at exactly `max_steps`
- State is still coherent and inspectable after the guard fires

**Budget** (`test_budget.py`)
- The stream stops **on the chunk that crosses**, not at the end
- The exception carries used and budget so the caller can emit a terminal
  frame and release its slot
- `settle()` overwrites the estimate with the provider's real count
- A one-character chunk is never free (the estimate rounds up)

**Eval gate** (`test_evals.py`)
- A metric below threshold blocks, and the failure names the metric and the
  bar it missed
- A *missing* metric counts as zero rather than passing by omission
- **The diagnostic metric never blocks, even at its worst value**, and is
  asserted to have no threshold entry at all

**Drift** (`test_drift.py`)
- Higher-is-better and lower-is-better go through one comparison; "worse"
  is always a negative z for both
- A short window reports `insufficient_data`, not `ok`
- A flat baseline reports `insufficient_data` rather than an infinite z

---

## Limitations

- **No real model is called.** Judgement points are injected callables with
  deterministic fakes. That keeps the suite offline and makes the
  "no model in the control plane" test meaningful, but it means nothing
  here exercises prompt behaviour, token accounting against a real
  tokenizer, or provider failure modes.
- **In-memory checkpointing.** `MemorySaver` is enough to show
  interrupt/resume; a real deployment needs a durable checkpointer for a
  pause to survive a restart.
- **No sandboxing.** Tools run in-process. Real agent execution needs
  process or container isolation and a network policy; the allow-list here
  is an authorisation model, not a containment one.
- **The eval gate has no scorer.** It takes metrics as input and decides.
  Producing those numbers from a golden set against a live system is the
  larger half and is out of scope.
- **Single-threaded, single-run.** No concurrency, no queue, no retry with
  backoff. Retry semantics are demonstrated in a companion repository
  (`idemingest`) rather than duplicated here.

---

## Where this came from

I built an agent platform at work — seven agents behind a deterministic
supervisor, a tool layer with per-tenant access, an approval gate, an eval
gate and drift detection — and that code is private. This repository is a
from-scratch reimplementation of the *decisions*, in a different domain, to
make them inspectable.

**No code from that system is used here.** What carries over is the
reasoning, written up in [docs/design.md](docs/design.md).

Work used LangGraph, and so does this, for the same reason: the interrupt
is the part worth not reinventing.

MIT licensed.
