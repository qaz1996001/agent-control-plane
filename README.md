*English ｜ [繁體中文](README.zh-TW.md)*

# agent-control-plane — let the model decide inside a step, never between steps

A runnable demonstration of one position: **an agent pipeline's control
plane should be ordinary code.** Routing, permissions, budget, masking,
provider choice and human approval are a lookup table, an allow-list, a
counter, a substitution, a veto and an interrupt — not things a model is
asked to get right.

```bash
uv run --with pytest --with langgraph pytest -q                    # 116 passed
uv run --with langgraph python examples/run_pipeline.py            # 10 scenarios
```

Every claim below is one of those ten scenarios, and each prints what
actually happened. Most of them end in *did not publish*. That is the
intended shape: in a publishing pipeline the interesting cases are the
ones where it declines, and there are more ways to decline than to
proceed.

Built on LangGraph for the runtime (node execution, checkpointing, and the
interrupt that makes approval a real pause). The routing policy is a plain
function over state, so it is testable without building a graph.

Four views of what the code does -- control flow, data flow, state lifecycle and usage scenarios -- are in [docs/architecture.md](docs/architecture.md). What is deliberately *not* here, and why, is in [docs/scope.md](docs/scope.md).

The domain is a retrieval-corpus publishing pipeline — a document is
triaged, indexed, assessed, held at a human gate, and published to a live
index — because that is the case where "the agent decided to publish it"
is a bad sentence to have to say. It is also pitched at a deliberately
generic altitude, for a reason set out in
[Where this came from](#where-this-came-from).

---

## The problem

Give an LLM the control flow and you get a system where:

- the same input can take a different path tomorrow, so a failed run cannot
  be replayed and compared;
- a wrong route is a prompt bug — you fix it by rewording and re-running
  evals, not by reading one line;
- "which tools may this step use" is a sentence in a prompt, which is a
  request rather than a check;
- a publish can happen because a model was persuaded that it should.

None of that is an argument against using models. It is an argument about
*where*.

## The decision

| | Model decides the route | Table decides the route |
|---|---|---|
| Same trigger, tomorrow | may differ | identical |
| A wrong route is | a prompt bug | a one-line table bug |
| Replaying a failed run | approximate | exact |
| Proving "no model ran here" | not possible | a test |

The model still does the work that needs judgement — classify this
document, assess this draft. Those are injected callables (`Judge`), which is also
what makes "the control plane ran with every model entry point poisoned"
an assertion rather than a claim.

### Six properties, six mechanisms

**Routing** — `ROUTE_TABLE` maps trigger → agent. An unknown trigger
raises; it does not fall back to a default. A typo that silently routed to
`publisher` is exactly the failure worth preventing.

> Seen in `rework`, where the trail is the route the table chose and the
> loop ends at the step guard. Pinned by `test_routing.py`, `test_handoff.py`.

**Permissions** — `ACCESS` maps agent → allowed tools, checked in `invoke`
right next to the call. `allowed()` is the single source for two readings
of that table: `invoke` checks it, `schemas_for` renders it, and a test
pins that the two agree for every agent and tenant. No node here lets a
model pick a tool, so the rendering is the seam a tool-calling loop would
attach to rather than something this pipeline exercises -- the agreement
is pinned in advance because that is the cheap half. A tool that raises is
converted to `{"error": ...}`, so an exception never reaches the graph and
a broken integration cannot kill a run that is holding an approval.
Whether the *step* degrades is a separate claim and not yet true: no
caller inspects that key, so the error object travels on as data. See
[docs/errata.md](docs/errata.md), D4.

> Seen in `approve`, which prints the `tools called` list -- four tools for
> four agents. Pinned by `test_tool_access.py`.

**Budget** — `BudgetedStream` counts tokens per chunk and raises the moment
the budget is crossed, mid-stream. It estimates, because it has to decide
before the provider reports; `settle()` then replaces the estimate with the
real count so the audit record is not left holding the approximation.
Crossing the budget is a refusal, not a note in the margin: the run stops
the same way an exhausted quota stops it, and a cut answer is discarded
rather than used because its fields happen to have survived.

> Run `budget`, which shows the guard and then what it does to a run at
> three budget levels. Pinned by `test_budget.py`, `test_audit.py`.

**One thing neither the budget nor the quota can do**, and the scenario
says so: a judge that answers in one shot has generated -- and been billed
for -- its whole reply before anything can count it. Refusing at that
point buys correctness, not credit. The two are structurally symmetric,
checked within a few lines of each other in `consult`, and both are gates
*before* the call: the ledger is charged only once the judge has returned,
so an exhausted quota refuses the *next* call rather than this one.
Nothing here stops a reply already in flight. `BudgetedStream`'s per-chunk
guard is written for a live stream it has not been handed -- `_chunks`
re-slices a reply that arrived whole.

**Approval** — the graph is compiled with
`interrupt_before=["approval_gate"]`. A run that reaches the gate stops and
is checkpointed. Nothing is published until someone resumes it with a decision,
and resuming *without* a decision still refuses — absence of a decision is
not consent.

> Three scenarios, one mechanism: `approve`, `reject`, and `ignore` -- the
> last being the resume that carries no decision. Pinned by `test_hitl.py`.

**Masking** — `privacy.mask` replaces addresses, internal hostnames and
handles with placeholders before the model sees them, and that half runs
in every pipeline run. `restore` is the other half of the same mechanism,
and it is the half this pipeline does not reach: what gets masked is the
*context* sent to the judge, and a verdict comes back in the model's own
words, so a run's answer holds no placeholder of ours to put back.
`consult` returns the mapping and the run drops it. `restore` puts values
back only for a viewer holding the permission, and refuses outright rather
than restoring what it can — a partial restore still leaks and reads as
though nothing was withheld. The mapping is bound to the run and never
written into state, because state is checkpointed.

> Run `mask`, which shows the placeholder text and both ways `restore`
> refuses. It also fires in an ordinary run: the draft fixture carries an
> author address and a build host, so the assessor's call record reads
> `masked: True` in `approve` and `gemma` too. Pinned by `test_privacy.py`.

**Provider choice** — `providers.choose` applies three filters in order:
health, then a locality **veto**, then a cost preference. Restricted
content cannot reach a remote provider even when that is the only healthy
one — the answer is "no provider", not "just this once". Failover may
cross the cost preference; it may never cross the veto.

> Run `residency`. Its last row is the point: the only healthy provider was
> remote and the answer was still no. Pinned by `test_providers.py`.

All six meet in one place. `agents.consult` is the only function in the
package that calls a `Judge`, so masking, provider selection, the budget,
the tenant's quota and the audit record are reached by construction
rather than by every node remembering to reach them. A test asserts there
is no second door.

> `quota` is what that single door looks like when a tenant is out of
> allowance: the run declines and the attempt is still recorded
> (`test_quota.py`). `gate` is the other gate -- an eval threshold and
> drift on the same metric (`test_evals.py`, `test_drift.py`). The tenth,
> `gemma`, puts a real model behind the door; see below.

---

## Running it

```bash
uv run --with langgraph python examples/run_pipeline.py            # all ten
uv run --with langgraph python examples/run_pipeline.py approve    # just one
```

Ten scenarios, each printing what actually happened:

| scenario | shows |
|---|---|
| `approve` | the run pauses, a human approves, and only then does it publish |
| `reject`  | a human declines -- the publisher refuses, `publish` is never called |
| `ignore`  | resumed with no decision -- still refuses |
| `rework`  | assessor sends it back; the loop ends at the step guard |
| `budget`  | a long response cut mid-stream, then the real count replaces the estimate |
| `gate`    | a publish blocked by the eval gate, then allowed; drift on the same metric |
| `mask`    | what the model is shown, and the two ways restoring is refused |
| `residency` | the only healthy provider is remote, the content is restricted, and the answer is still no |
| `quota`   | a tenant out of allowance -- the run declines, and the attempt is still recorded |
| `gemma`   | a real local model does the judging; the route does not change |

Abridged output of `approve`:

```
--------------------------------------------------------------------------
approve -- a human says yes, and only then does it publish
--------------------------------------------------------------------------
  paused at    ('approval_gate',)          <- the run is stopped, not polling
  published?   False

  ...a curator approves in Slack / the web UI...

  trail        triage -> indexer -> assessor -> approval_gate -> publisher
  steps        5 / 8
  triage_report      {'severity': 'normal', 'document': {'id': 4821, 'title': 'Calibration procedure, revision C', 'submitter': 'support'}}
  index_report       {'entry': {'chunks': ['split by section', 'strip boilerplate', 'attach source refs']}}
  assessment_report  {'approved': True, 'comments': [], 'text': 'draft assessed, no blocking findings.'}
  publish_report     {'published': True, 'result': {'index': 'corpus-live', 'revision': 99214, 'tier': 'published'}}
  model calls  2  (triage->local-small unmasked, assessor->local-small masked)
  tokens       16 / 2000   (0/2 settled against the provider's count)

  tools called ['read_document', 'write_index', 'read_draft', 'publish']
```

And `rework`, where the assessor keeps rejecting:

```
  trail        triage -> indexer -> assessor -> indexer -> assessor -> indexer
  steps        6 / 6
  triage_report      {'severity': 'normal', 'document': {'id': 4821, 'title': 'Calibration procedure, revision C', 'submitter': 'support'}}
  index_report       {'entry': {'chunks': ['split by section', 'strip boilerplate', 'attach source refs']}}
  assessment_report  {'approved': False, 'comments': ['add tests']}
  model calls  3  (triage->local-small unmasked, assessor->local-small masked, assessor->local-small masked)
  tokens       36 / 2000   (0/3 settled against the provider's count)

  the loop did not run forever; max_steps decided when to stop
```

### The last one: a real model in the judgement seam

The nine scenarios above need no model and no network. The tenth, `gemma`,
runs the same pipeline as `approve` with a real model doing the judging --
Gemma 4 E4B on a local Ollama:

```bash
ollama pull gemma4:e4b                                           # ~6.6 GB
uv run --with langgraph python examples/run_pipeline.py gemma
```

It runs as part of the default set. The first nine still need no model and
no network, and if Gemma is not being served this one prints what is
missing and skips rather than failing -- so a clone with no Ollama behaves
exactly as before.

The adapter is [`examples/gemma_judge.py`](examples/gemma_judge.py), about
200 lines of standard library -- there is no new dependency, because
`Judge` is `(prompt, context) -> dict` and that is the entire contract.
**The adapter lives in `examples/`, not in `src/agentcp`, deliberately.**
A provider import under `src/` would retract the claim the test suite makes
about the control plane; the model belongs with the other integration seams
in `adapters.py`.

Abridged output, with Gemma 4 E4B actually answering:

```
  model said  '{"severity": "low"}'
  model said  '{\n  "approved": true,\n  "comments": [\n    "The change is
                small and localized (2 sections, low diff), which is
                good.", ... ]\n}'

  with the model:
  trail        triage -> indexer -> assessor -> approval_gate -> publisher
  steps        5 / 8
  triage_report      {'severity': 'low', 'document': {'id': 4821, ...}}
  publish_report     {'published': True, 'result': {'index': 'corpus-live', 'revision': 99214, 'tier': 'published'}}
  model calls  2  (triage->local-small unmasked but answered by ollama:gemma4:e4b, ...)
  tokens       1084 / 2000   (2/2 settled against the provider's count)

  severity     'normal' (default)  ->  'low' (Gemma)
  same trail?  True        <- routing is code, not a prompt
  same steps?  5 vs 5
  published?    True         <- still only because a human said yes

  estimated    73 tokens   <- the char heuristic, from the visible reply
  provider     1084 tokens   <- eval_count, which includes Gemma's
               hidden reasoning: 15x the estimate.

  rejected     0   every reply matched the schema
```

The model disagreed with the default about severity -- it read a routine
procedure revision as `low` rather than `normal` -- and the route did not
change by one step, because nothing asked it to. The reply is also the
model's own prose rather than ours, which is the point of the seam and
also its honest edge: the judgement is whatever the model says, and the
only thing the control plane does with it is type-check it.

Three things the scenario is built to show:

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
- **It is what finally made `settle()` demonstrable.** The budget guard has
  to decide before the provider reports, so it estimates from the characters
  it can see. Gemma 4 E4B reasons before it answers, and `eval_count` bills
  that reasoning: on this run, 1084 tokens against an estimate of 73. The
  estimate is not slightly off, it is off by an order of magnitude, and it
  is wrong in the direction that matters. A ledger that kept the estimate
  would under-report the bill by that much -- which is why the record
  carries `tokens_actual` separately and leaves it `None` until a real
  count arrives.

## Operating it for real

`examples/adapters.py` is the integration surface. Every tool there is a
stub that records the call it would have made, which makes the seams
countable -- there are seven registered, of which the node implementations
currently reach four. The other three (`tag_document`, `post_finding`,
`read_index`) are permitted and wired but unused; `tools called` in the
output below is the honest list.

| stub | what replaces it |
|---|---|
| `read_document`, `tag_document` | whatever holds intake -- a tracker's REST client, a document store |
| `read_draft`, `post_finding` | wherever drafts and findings live -- a Git host's review API, a CMS |
| `write_index`, `read_index` | your own store -- a table, a vector index |
| `publish` | the index build: a CI dispatch, an indexing job, an alias swap |

Swapping one is a single function; the registry neither knows nor wants to
know where credentials come from.

**What drives a run.** A webhook maps an inbound event to a `Trigger` and
calls `invoke` with a thread id -- typically the document or draft id, so a
re-delivered webhook resumes the same run rather than starting a second
one. The trigger vocabulary is a closed set precisely so that mapping is a
dictionary you can read, not a prompt.

**Where a human sees the pause.** When a run stops,
`app.get_state(cfg).next` is `("approval_gate",)` and the state holds the
assessing agent's report. That is enough to render a Slack message or a web
page with the evidence and two buttons; the buttons call `invoke` with
`Command(update={"human_decision": ...})` on the same thread id. Nothing
polls, and a pause costs nothing while it waits.

**What to change before production.** A durable checkpointer, so a pause
survives a restart -- `MemorySaver` loses it. The hook is already there
and already refuses to pretend: `build_graph(durability="require")`
raises rather than falling back, and passing a `MemorySaver` explicitly
does not satisfy it. Process or container isolation for tools, because
the allow-list authorises but does not contain. A shared quota counter,
because the ledger here is per process and two workers each get a full
allowance. And a real scorer behind the eval gate, which currently takes
metrics as input rather than producing them.

The full list of what is here, what is not, and the condition that would
reopen each omission is [docs/scope.md](docs/scope.md).


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
- `publish` is reachable from exactly one agent, asserted by inspection
- A raising tool returns `{"error": ...}` instead of propagating
- **Schemas offered to an agent equal its allow-list, for every agent**
- An unknown agent is offered nothing

**Approval** (`test_hitl.py`)
- The run genuinely stops: `snapshot.next == ("approval_gate",)` and no
  `publish_report` exists yet
- Approve → publishes; reject → finishes without publishing, with a reason
- **Resuming with no decision still refuses**
- A machine-approved assessment sets `requires_approval` and does not write
  `human_decision` — so the assessor does not approve on the human's
  behalf. **A node that tries raises**, because `build_graph` refuses a
  patch naming a field in `state.PROTECTED`; four tests go red if that
  wrapper is removed. It was a convention until it was not — entry A1 in
  [docs/errata.md](docs/errata.md)

**Hand-off** (`test_handoff.py`)
- Each agent writes exactly one `*_report` key and no other agent's
- A rejecting assessment hands back to the indexer
- An indexer ↔ assessor cycle stops at exactly `max_steps`
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

**Masking** (`test_privacy.py`)
- The masked text contains no real value **anywhere** -- asserted over the
  whole string, not the positions the substitution touched
- Repeats of one value share a placeholder, so the model can still tell
  two mentions are the same entity
- **Restoring without the permission refuses outright** rather than
  restoring what it can
- One run's mapping cannot resolve another run's placeholders
- A placeholder the model invented stays literal instead of resolving

**Provider choice** (`test_providers.py`)
- **Restricted content never reaches a remote provider, even when the
  remote one is the only healthy provider left**
- Failover crosses the cost preference and never the locality veto
- The refusal says why, rather than just failing
- Every choice carries the reason the audit record stores

**Audit and the single door** (`test_audit.py`)
- **`consult` is the only place a `Judge` is called** -- a second entry
  point would make masking, budget and audit optional
- The judge only ever sees masked text
- **The unmasking map never reaches checkpointed state**
- Every model-consulting node leaves exactly one record
- The run's token counter equals the sum of its call records
- A response cut by the budget, and a call refused outright, both still
  leave a record
- An unsettled record is distinguishable from one settled at the estimate

**Tenancy and quota** (`test_tool_access.py`, `test_quota.py`)
- A tenant rule can narrow a role and **never widen it**, checked across
  every (agent, tenant) pair
- Offered schemas equal the allow-list for every (agent, tenant) pair
- One tenant running out does not touch another's allowance
- The over-quota error carries `retry_after`
- The spend that broke the limit is still counted
- A tenant denied `publish` makes the publisher refuse with a reason rather
  than crash and lose an approval already given

**Durability** (`test_durability.py`)
- `durability="require"` without a store **raises instead of silently
  falling back** to the in-memory saver
- Passing a `MemorySaver` explicitly does not satisfy the requirement --
  the question is whether a pause survives a restart
- **Any other saver is accepted on trust**, and the test says so in its
  name: the guard is a blocklist of what is known to be process-local, and
  a type cannot tell you whether a store outlives the process

**Policy snapshots** (`test_evals.py`)
- A result records the thresholds it was judged under
- **Raising a bar later does not rewrite an earlier verdict**

---

## Limitations

- **No real model is called by the test suite.** Judgement points are
  injected callables with deterministic fakes. That keeps the suite offline
  and makes the "no model in the control plane" test meaningful. The
  `gemma` scenario does call a real local model, but it is a demonstration
  of the seam, not coverage: nothing here exercises token accounting
  against a real tokenizer, or provider failure modes beyond "unreachable"
  and "malformed reply".
- **In-memory checkpointing by default.** `MemorySaver` is enough to show
  interrupt/resume. `durability="require"` exists for the case where a
  pause must survive a restart, and refuses the two ways of not having a
  store: none at all, and a `MemorySaver` passed explicitly. It is a
  blocklist of what is known to be process-local, **not** a verification
  that a store survives a restart — nothing in the type says whether it
  does, so any other saver is accepted on trust. No durable store ships
  here.
- **Masking is rule matching, not NER.** Addresses, internal hostnames and
  handles, by pattern. Structured identifiers are covered; names and
  free-text identifiers are not. The mechanism does not change when the
  detector improves — only recall does.
- **The quota ledger is per process.** Two workers each get a full
  allowance, so the real ceiling is the limit times the worker count.
  Shared enforcement needs a shared counter and a store.
- **Provider health is a hard-coded constant.** `choose` takes the set its
  caller believes is up, but `agents.HEALTHY` is a module-level constant
  and `build_graph` has no parameter that injects one, so a pipeline
  caller cannot pass a health view at all — that constant is the seam. A
  real version tracks failures per provider and half-opens after a
  cooldown; the ordering rules are the part that transfers.
- **No guardrails.** No injection detection, output filtering or
  prompt-leak checks. Offline they could only be tested against the
  examples their own patterns were written from, which is a test that
  always passes and proves nothing. See [docs/scope.md](docs/scope.md).
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
from-scratch reimplementation of the *decisions*, to make them
inspectable.

**No code from that system is used here.** What carries over is the
reasoning, written up in [docs/design.md](docs/design.md), and the
boundary — which of that system's capabilities are reproduced and which
were deliberately left out — in [docs/scope.md](docs/scope.md).

**Why this domain.** It is pitched at a deliberately generic altitude:
triage, index, assess, gate, publish is the shape any team running a
knowledge base already has, so the decisions can be read without the
source being identifiable. The protection is that the vocabulary is
ordinary, not that the domain is distant. That is a smaller claim than
it may look, and worth stating at its real size: it lowers how
identifying the *words* are, and it does nothing about the structural
resemblance — four agents behind one deterministic router, a single
model entry point, a gate a human has to pass, an audit record. That
structure is the whole value of the repository, so it is not something
I could remove and still have anything to show. The vocabulary is
generic on purpose; the shape is not, and is not meant to be.

### Where this is stricter than what it came from

Two of the four properties are not reproductions. They are arguments with
the original, and saying so is better than letting a demo imply the
production system already behaves this way.

- **Routing never reaches a model.** The original routes an *unknown*
  trigger by asking a model which agent should handle it — behind a feature
  flag, with the answer validated against the list of agents. That is a
  defensible escape hatch, and it is also the exact thing this repository
  argues against. Here an unknown trigger raises, and a test asserts the
  control plane runs with every model entry point poisoned. An event nobody
  wrote a route for should become visible, not quietly assigned.
- **Tool permissions are a checked table.** The original has no per-agent
  allow-list. Each node imports the functions it needs, so which tools a
  step may use is a convention about imports rather than a check at the
  call site. `ACCESS` is what that convention looks like once it is written
  down and enforced — with the same table generating the schemas a model
  would be offered, so what is advertised and what is permitted cannot
  drift apart. Nothing here offers them yet; the agreement is pinned
  before anything depends on it.

The approval gate, by contrast, *is* a reproduction: same
`interrupt_before` on the gate node, same `human_decision` carried in
state, same answer when a run is resumed without one.

Work used LangGraph, and so does this, for the same reason: the interrupt
is the part worth not reinventing.

MIT licensed.
