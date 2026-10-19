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

Four views of what the code does -- control flow, data flow, state lifecycle and usage scenarios -- are in [docs/architecture.md](docs/architecture.md).

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

## Running it

```bash
uv run --with langgraph python examples/run_pipeline.py            # all six
uv run --with langgraph python examples/run_pipeline.py approve    # just one
```

Six scenarios, each printing what actually happened:

| scenario | shows |
|---|---|
| `approve` | the run pauses, a human approves, and only then does it deploy |
| `reject`  | declined at the gate -- `deploy` is never called |
| `ignore`  | resumed with no decision -- still refuses |
| `rework`  | reviewer sends it back; the loop ends at the step guard |
| `budget`  | a long response cut mid-stream, then the real count replaces the estimate |
| `gate`    | a release blocked by the eval gate, then allowed; drift on the same metric |

Abridged output of `approve`:

```
--------------------------------------------------------------------------
approve -- a human says yes, and only then does it deploy
--------------------------------------------------------------------------
  paused at    ('approval_gate',)          <- the run is stopped, not polling
  deployed?    False

  ...a reviewer approves in Slack / the web UI...

  trail        triage -> planner -> reviewer -> approval_gate -> deployer
  steps        5 / 8
  deploy_report {'deployed': True, 'result': {'workflow': 'deploy.yml', 'run_id': 99214, ...}}

  tools called ['read_ticket', 'write_plan', 'read_diff', 'deploy']
```

And `rework`, where the reviewer keeps rejecting:

```
  trail        triage -> planner -> reviewer -> planner -> reviewer -> planner
  steps        6 / 6
  the loop did not run forever; max_steps decided when to stop
```

### Optional: a real model in the judgement seam

The six scenarios above need no model and no network. A seventh, `gemma`,
runs the same pipeline as `approve` with a real model doing the judging --
Gemma 4 E4B on a local Ollama:

```bash
ollama pull gemma4:e4b                                           # ~6.6 GB
uv run --with langgraph python examples/run_pipeline.py gemma
```

It is excluded from the default run, and if the model is not there the
scenario says so and skips rather than failing.

The adapter is [`examples/gemma_judge.py`](examples/gemma_judge.py), about
200 lines of standard library -- there is no new dependency, because
`Judge` is `(prompt, context) -> dict` and that is the entire contract.
**The adapter lives in `examples/`, not in `src/agentcp`, deliberately.**
A provider import under `src/` would retract the claim the test suite makes
about the control plane; the model belongs with the other integration seams
in `adapters.py`.

Abridged output, with Gemma 4 E4B actually answering:

```
  model said  '{"severity": "critical"}'
  model said  '{"approved": true, "comments": ["Small, focused change across
                only two files. Looks ready to merge."]}'

  trail        triage -> planner -> reviewer -> approval_gate -> deployer
  steps        5 / 8

  severity     'normal' (default)  ->  'critical' (Gemma)
  same trail?  True        <- routing is code, not a prompt
  same steps?  5 vs 5
  deployed?    True         <- still only because a human said yes

  model calls  2
  rejected     0   every reply matched the schema
```

The model disagreed with the default about severity -- a 500 on login is
indeed not `normal` -- and the route did not change by one step, because
nothing asked it to.

Two things the scenario is built to show:

- **It runs the pipeline twice** -- once with the deterministic default,
  once with Gemma -- and compares. The trail and the step count are
  identical; only the content of the judgement changes. Routing is a lookup
  table either way.
- **The reply is type-checked at the boundary.** The two call sites have
  known output shapes, so they are sent as a JSON schema and the answer is
  validated against it. A severity outside the enum, a non-boolean verdict,
  an empty reply: rejected, counted, and replaced with the default. The step
  degrades; the route does not move. That is the difference between a model
  deciding *inside* a step and a model deciding *between* steps.

## Operating it for real

`examples/adapters.py` is the integration surface. Every tool there is a
stub that records the call it would have made, which makes the seams
countable -- there are seven.

| stub | what replaces it |
|---|---|
| `read_ticket`, `label_ticket` | Jira / Linear REST client |
| `read_diff`, `post_comment` | GitHub / GitLab API |
| `write_plan`, `read_plan` | your own store -- a table, a wiki page |
| `deploy` | CI trigger: Actions dispatch, Argo, Jenkins |

Swapping one is a single function; the registry neither knows nor wants to
know where credentials come from.

**What drives a run.** A webhook maps an inbound event to a `Trigger` and
calls `invoke` with a thread id -- typically the ticket or PR number, so a
re-delivered webhook resumes the same run rather than starting a second
one. The trigger vocabulary is a closed set precisely so that mapping is a
dictionary you can read, not a prompt.

**Where a human sees the pause.** When a run stops,
`app.get_state(cfg).next` is `("approval_gate",)` and the state holds the
reviewing agent's report. That is enough to render a Slack message or a web
page with the evidence and two buttons; the buttons call `invoke` with
`Command(update={"human_decision": ...})` on the same thread id. Nothing
polls, and a pause costs nothing while it waits.

**Three things to change before production.** A durable checkpointer, so a
pause survives a restart -- `MemorySaver` loses it. Process or container
isolation for tools, because the allow-list authorises but does not
contain. And a real scorer behind the eval gate, which currently takes
metrics as input rather than producing them.


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

- **No real model is called by the test suite.** Judgement points are
  injected callables with deterministic fakes. That keeps the suite offline
  and makes the "no model in the control plane" test meaningful. The
  `gemma` scenario does call a real local model, but it is a demonstration
  of the seam, not coverage: nothing here exercises token accounting
  against a real tokenizer, or provider failure modes beyond "unreachable"
  and "malformed reply".
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
