# Errata — every place a claim outran its evidence

This page is the audit's record, not its conclusion. It lists each claim in
this repository that promised more than the code delivers, what the code
actually does instead, the experiment that proved the gap, and which of
four kinds of mistake it is.

It is published **before** the repairs, deliberately. Knuth printed all
850-odd errors he found while writing TeX, on the argument that the record
is worth more than the appearance of never having been wrong: once a defect
is fixed it vanishes from the source, and with it the information about how
a careful author came to overstate a guarantee. That information is the
most useful thing this audit produced, so it gets its own file rather than
a line in a commit message.

There is also a plainer reason. A repository that lists its own
exaggerations is easier to trust than one that appears never to have made
any, because the reader can see the standard it holds itself to.

**Line numbers are as of commit `eb66c3d`**, the commit that added
[`fix-plan.md`](fix-plan.md) and the last one before any repair. Every
citation below was checked by opening the file at that line at that commit.
The fixes move the lines; the record should not have to move with them.

## The four classes

Classification is not decoration — in this project it decides the remedy.

| Class | What it means | Remedy |
|---|---|---|
| **A** | **A convention written as a structure.** No code violates it today, and nothing stops code from violating it tomorrow. | Make the mechanism structural, so it does not depend on anyone remembering. |
| **B** | **A decorative test.** The setup looks like it is proving something; remove the mechanism and the assertion still passes. | Rewrite the test so that removing the mechanism turns it red. |
| **C** | **A mechanism nothing reaches.** The code and the test both exist, but no execution path arrives there. | State the scope precisely — say where the seam stops. Wiring it up is scope creep. |
| **D** | **Said more broadly than done.** The claim reads as a general rule; the code holds only in a narrower case. | Narrow the sentence to what the code does. |

The remedy follows from the class, never from how hard the fix is. Which
items are repaired in code and which in prose is argued in
[`fix-plan.md`](fix-plan.md); this page only records what was found.

One entry can appear in several files at once, because the prose is
bilingual and some claims are also drawn in a diagram. Where that happens
every site is listed, because a claim fixed in one language and left
standing in the other is still a false claim.

---

## Class A — a convention written as a structure

### A1. `human_decision` is writable only by resuming a run

**Claim.**

> The row that matters is `human_decision`: it is writable only by resuming
> an interrupted run. No agent can set it, which is what makes "the reviewer
> cannot approve on the human's behalf" a structural property rather than a
> convention.
>
> — `docs/architecture.md:66-69`

Same claim, other sites: `docs/architecture.zh-TW.md:43`
(「任何代理都設不了它——這就是為什麼⋯⋯是一個**結構性質**」),
`src/agentcp/state.py:43-45` ("Populated only by resuming an interrupted
run — never by an agent"), `README.md:337-338`,
`README.zh-TW.md:233`, `docs/design.md:199`, `docs/design.zh-TW.md:166`,
and the generated state diagram — `docs/src/state.json` nodes `f3`
("只有 resume 寫入") and `f4` ("代理不得寫別人的報告，也不得寫
`human_decision`").

**What the code does.** `PipelineState` (`src/agentcp/state.py:28`) is a
bare `TypedDict` with no reducers and no validation, and
`src/agentcp/graph.py:86` passes each node's patch into state untouched:

```python
g.add_node(name, lambda s, _fn=fn: _fn(s, judge))
```

A node that returns `{"human_decision": {"approve": True}}` has forged a
human approval. Nothing rejects it, nothing strips it, and `deployer_node`
(`src/agentcp/agents.py:311`) cannot tell a forged decision from one that
arrived through `Command(update=...)`, because by the time it reads
`state.get("human_decision")` both look identical. What is true today is
only that no node in `agents.py` happens to write that key.

**Experiment.** A node writes `human_decision` into its own patch; the run
is then resumed on the path that carries *no* decision — the path the
`ignore` scenario exists to demonstrate — via `app.invoke(None, cfg)`.
Recorded in `fix-plan.md` §1.1:

```
paused at      : ('approval_gate',)
resumed with   : None
human_decision : {'approve': True, 'reason': 'the agent decided'}
deploy_report  : {'deployed': True, ... 'env': 'production'}
```

A second probe shows the gate can be skipped rather than forged. A node
sets `next_agent = 'deployer'`, and one `invoke()` deploys without ever
pausing:

```
trail         : triage -> deployer
ever paused   : ()
deploy_report : {'deployed': True, ... 'env': 'production'}
```

**Class.** A. The sentence the author meant was "no node does this"; the
sentence written was "no node can do this".

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### A2. The run's four constants cannot be relaxed during the run

**Claim.**

> Four fields are set once at `new_state` and only read afterwards —
> `trace_id`, `tenant`, `sensitivity`, `max_steps`. They are the run's
> identity and its constraints, and nothing during the run may relax them.
>
> — `docs/architecture.md:71-73`

Same claim: `docs/architecture.zh-TW.md:45`
(「執行過程中沒有任何東西可以放寬它們」).

**What the code does.** The same hole as A1, and this is where it costs
most. All four are ordinary `TypedDict` keys, so a node patch can rewrite
any of them: `max_steps` loosens the runaway guard, `sensitivity` discards
the locality veto, `tenant` escapes both `TENANT_DENY` and the quota
ledger, and `trace_id` rebinds the masking namespace. Four of this
repository's six headline mechanisms are reachable around one gap.

**Experiment.** Same mechanism as A1 — `graph.py:86` merges a node patch
verbatim, and no key is privileged — so the A1 probes demonstrate it. The
field-by-field version is listed as acceptance criteria in `fix-plan.md`
§4.1 rather than as a finding, because the gap is structural and shared.

**Class.** A.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### A3. `completed` and `calls` are append-only

**Claim.**

> `completed` and `calls` are append-only, so the audit trail cannot be
> rewritten by a later node.
>
> — `docs/architecture.md:38-39`

Same claim: `docs/architecture.zh-TW.md:27`, `src/agentcp/state.py:48-49`
("Append-only audit trail of node names, in execution order"),
`src/agentcp/state.py:61-63` ("Same shape of guarantee as `completed`:
later nodes add, never rewrite"), and `docs/src/dataflow.json:90`
(「兩條軌跡都只增不改」).

**What the code does.** Append-only is a habit of two private helpers, not
a property of the state. `_advance` and `_bill` in
`src/agentcp/agents.py` each write `[*state.get(...), x]`; a node that
returns `completed=["planner"]` *replaces* the trail, because a bare
`TypedDict` key has no reducer and LangGraph's default for an
un-annotated key is last-write-wins.

**Experiment.** Static: `PipelineState` declares `completed: list[str]`
and `calls: list[dict]` with no `Annotated[..., operator.add]`
(`src/agentcp/state.py:77`, `:83`), which is what would make the merge an
append. The behavioural probe is listed as acceptance criteria in
`fix-plan.md` §4.1.

**Class.** A.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### A4. Every field has one writer, and the diagram names it

**Claim.**

> Each of the 18 fields has one writer, and the diagram names it.
>
> — `docs/architecture.md:64`

Same claim: `docs/architecture.zh-TW.md:41`
(「18 個欄位，每一格都只有一個寫入者，圖上把它標出來」) and the state
diagram's subtitle, `docs/src/state.json:11`
(「每一格都有明確的寫入者」).

**What the code does.** The count of 18 is right. The claim of one writer
each is not: `next_agent` is written by four nodes, `step_count` and
`completed` by five, and `calls` and `tokens_used` by two. Nor does the
diagram name them — `docs/src/state.json` node `f2` groups seven fields
under the single label 「節點寫入」 ("written by nodes"), which is a
category, not a writer. So the second half of the sentence overstates the
diagram in the same breath as the first half overstates the code.

**Experiment.**

```
$ grep -c '"next_agent"\]' src/agentcp/agents.py
```

Reading the node bodies in `src/agentcp/agents.py` is the honest form of
this check: `triage_node`, `planner_node`, `reviewer_node` and
`deployer_node` all assign `patch["next_agent"]`, and every node reaches
`_advance`, which writes `step_count` and `completed`.

**Class.** A for the code half (a convention about which node touches
which field, described as a structure), D for the diagram half (the
diagram groups where the prose says it names).

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

## Class B — decorative tests

A test in this class is worse than no test, because it occupies the place
where a reader looks for the proof. The check each of these had to pass and
did not: **remove the mechanism and the test must go red.**

### B1. `test_routing_touches_no_model`

**Claim.** The test's own docstring, and the README sentence it backs:

> """The control plane must work with every model entry point poisoned."""
>
> — `tests/test_routing.py:27-28`

> **The control plane runs with every model entry point monkeypatched to
> raise** — if routing ever consulted a model, this test fails
>
> — `README.md:320-321`; same in `README.zh-TW.md:219`

**What the code does.** The test replaces `agents._default_severity` and
`agents._default_verdict` with functions that raise, then calls
`route(trigger)` for every entry in `ROUTE_TABLE`. `route()` is a
three-line dictionary lookup in `src/agentcp/router.py`; it calls nothing.
The poison is never near the needle.

**Experiment.** Delete the two `monkeypatch.setattr` lines and run the
test:

```
$ uv run --with pytest --with langgraph pytest -q tests/test_routing.py
```

It passes either way. The assertion that survives removing the mechanism is
not testing the mechanism.

**Class.** B. The claim it was written to defend is a real and important
one — it simply cannot be expressed as a static check on `router.py`,
because `graph.py:86` *must* hand the judge to the nodes; that is the
graph's job.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### B2. `test_consult_is_the_only_place_a_judge_is_called`

**Claim.**

> """A second model entry point would bypass mask, budget and audit."""
>
> — `tests/test_audit.py:184-185`

This is the test the scope page singles out: `docs/scope.md:66` calls the
single-door decision "the decision I would keep if I could keep only one",
and `docs/scope.zh-TW.md:46` says the same.

**What the code does.** The test collects every callable in `agents` whose
source contains the substring `"(judge or "` and asserts the list equals
`["consult"]` (`tests/test_audit.py:186-192`). A substring is not a call
graph.

**Experiment.** Copy `agents.py`, add a node containing
`verdict = judge(state, {})`, and run the test. Recorded in `fix-plan.md`
§2.2: `callers == ['consult']` still passes. A second door spelled any way
other than `(judge or ` is invisible to it.

**Class.** B.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### B3. `test_the_unmasking_map_never_reaches_checkpointed_state`

**Claim.**

> """State is persisted; a map of real values in it would undo masking."""
>
> — `tests/test_audit.py:166-167`

> **The unmasking map never reaches checkpointed state**
>
> — `README.md:387`; same in `README.zh-TW.md:274`

**What the code does.** Two assertions, both weak
(`tests/test_audit.py:181-182`): `"pairs" not in blob` checks for the
absence of the `Mapping` dataclass's field name, and no token in the
`repr` starts with `<EMAIL`. But `Consultation` never puts the mapping
into a patch in the first place, so the first assertion is about a thing
no code path produces. Replace `privacy.mask` with a no-op and both
assertions still hold.

Worse, the property the docs actually care about — a checkpoint must not
hold real values — is violated by the test's own fixture, which
checkpoints `{"ticket": 42, "pr": 7, "reporter": "sam.okafor@example.com"}`
verbatim.

**Experiment.** Recorded in `fix-plan.md` §3.2:

```
測試的兩條斷言:
   "pairs" not in blob        -> True
   no token starts with <EMAIL -> True
但真實 email 在 checkpoint 裡嗎 -> True
它在哪                        -> {'ticket': 42, 'pr': 7, 'reporter': 'sam.okafor@example.com'}
```

The irony is on the record too: `examples/adapters.py:58-59` warns in a
comment that PII in a ticket fixture ends up in the checkpoint, and this
test's fixture does exactly that.

**Class.** B for the test. The claim behind it splits in two — "the
restore mapping is never checkpointed" is true and worth asserting; "a
checkpoint never holds real values" is false, and is filed below as D9.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### B4. `test_a_durable_checkpointer_satisfies_the_requirement`

**Claim.**

> ```python
> class FakeDurableSaver(MemorySaver.__bases__[0]):
>     """Stands in for a store that outlives the process."""
> ```
>
> — `tests/test_durability.py:35-38`

**What the code does.** `FakeDurableSaver` is a bare `BaseCheckpointSaver`
subclass with no body: it stores nothing and would raise
`NotImplementedError` if a run actually used it. The assertion is
`build_graph(...) is not None` (`tests/test_durability.py:39`). Against a
guard that rejects `None` and `MemorySaver` instances and nothing else,
that is a tautology — it asserts that an object which is neither of those
two things is not one of those two things.

**Experiment.** Read the guard at `src/agentcp/graph.py:67-77`. It is a
blacklist with one entry. Any object that is not `None` and not a
`MemorySaver` satisfies it, so the positive test cannot fail for any reason
related to durability.

**Class.** B. See D8 for the prose claim it props up.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

## Class C — a mechanism nothing reaches

Each of these is real code with real tests and no caller on any execution
path. The remedy is a precise sentence, not a wire: a demonstration
repository that grows a half-finished feature so a sentence comes true has
traded away the thing it exists to provide.

### C1. `schemas_for`

**Claim.**

> The schemas offered to a model are generated from the same table, so what
> is advertised and what is permitted cannot drift apart.
>
> — `README.md:72-74`

Same claim: `README.md:329`, `README.md:486-487`, `README.zh-TW.md:50`,
`README.zh-TW.md:226`, `README.zh-TW.md:325`, `docs/scope.md:35`,
`docs/scope.zh-TW.md:23`, `docs/design.md:56-60` and `:84` and `:96-98`,
`docs/design.zh-TW.md:50` and `:74` and `:86`.

**What the code does.** `tools.schemas_for` and `tools.invoke` do share
`allowed()`, and the equality is genuinely pinned. But nothing is ever
*offered* to a model: no node in this repository lets a model choose a
tool. The nodes call `invoke` directly with a fixed tool name.

**Experiment.**

```
$ grep -rn --include=*.py 'schemas_for' src/ tests/ examples/
src/agentcp/tools.py:94:def schemas_for(agent: str, tenant: str = DEFAULT_TENANT) -> list[dict]:
src/agentcp/__init__.py:26:    schemas_for,
src/agentcp/__init__.py:40:    "AccessDenied", "Tool", ... "invoke", "register", "schemas_for",
tests/test_tool_access.py:38:        offered = {s["function"]["name"] for s in tools.schemas_for(agent)}
tests/test_tool_access.py:43:    assert tools.schemas_for("intruder") == []
tests/test_tool_access.py:63:            offered = {s["function"]["name"] for s in tools.schemas_for(agent, tenant)}
```

A declaration, an export, and three lines of test. No production caller.

**Class.** C. "Cannot drift apart" is true of the two readings of one
table; "what is advertised" describes an advertisement nobody makes.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C2. `restore`, `Viewer` and `Consultation.mapping`

**Claim.**

> Three endpoints of one mechanism, and they only work as a set
>
> — `src/agentcp/privacy.py:3`

> `privacy.mask` replaces addresses, internal hostnames and handles with
> placeholders before the model sees them, and `restore` puts them back
> only for a viewer holding the permission.
>
> — `README.md:106-108`; same in `README.zh-TW.md:64`

Also the masking flowchart, `docs/design.md:102-135` and
`docs/design.zh-TW.md:90-117`, which draws `masked answer → restore → real
values back` as the pipeline's path.

**What the code does.** Two distinct gaps. First,
`Consultation.mapping` (`src/agentcp/agents.py:72`) has no consumer
anywhere — the pipeline receives the mapping and drops it. Second, and
more interesting: there is nothing in a pipeline answer to restore. What
`mask` processes is the *context* sent to the judge; the verdict is the
model's own words and contains no placeholder of ours unless the model
invents one — which `test_privacy.py` asserts stays literal. So the
diagram's `masked answer → restore` edge does not describe a run.

`docs/scope.md:71` is already honest about the first half
("`Consultation.mapping` is returned in process and dropped"); the README
and the design diagram were never aligned to it.

**Experiment.**

```
$ grep -rn --include=*.py '\.mapping' src/ tests/ examples/
$
```

No hits. The only callers of `restore` are `tests/test_privacy.py` and the
`mask` scenario in `examples/run_pipeline.py:197-205`, which calls
`privacy.mask` and `privacy.restore` directly — no graph, no node, no
`consult`.

**Class.** C.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C3. The provider health view

**Claim.**

> `choose` takes the set the caller believes is up.
>
> — `README.md:436-437`

Same claim: `docs/scope.md:162-163`, `README.zh-TW.md:306`,
`docs/scope.zh-TW.md:100`.

**What the code does.** `agents.HEALTHY` (`src/agentcp/agents.py:43`) is a
hard-coded module constant set to `providers.ALL_HEALTHY`, and `consult`
reads it from module scope. `build_graph` takes `judge`, `checkpointer`
and `durability` and has no parameter through which a caller could inject a
health view. So for the pipeline's caller — the only caller the README
describes — the sentence is not true: there is no set to pass.

The sentence *is* true of `providers.choose` called directly, which is what
`test_providers.py` and the `residency` scenario do.

**Experiment.** Read the signature at `src/agentcp/graph.py:38`:

```python
def build_graph(judge=None, checkpointer=None, durability: str = "memory"):
```

**Class.** C.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C4. Provider choice on the pipeline path

**Claim.** `README.md:118-125` presents provider choice as one of the six
properties each demonstrated by one of the ten scenarios, with
`residency` named as its scenario.

**What the code does.** The mechanism works; it is verified end to end
under forced conditions (`restricted` sensitivity plus only the remote
provider healthy yields `severity: unknown` and `provider: 'none'` through
the graph). What no scenario does is reach it on a pipeline path. Every
call in every scenario is `("open", "low", all four healthy)` and resolves
to `local-small`: the veto never fires, the health filter never excludes
anything, and the capable tier is never selected, because
`HIGH_COMPLEXITY_CHARS` is 200 while `approve`'s masked contexts are 61 and
105 characters. `scenario_residency` calls `providers.choose` directly.

**Experiment.** Recorded in `fix-plan.md` §3.3. The two context lengths
and the uniform `local-small` outcome are visible in the `model calls`
rows of every scenario's output.

**Class.** C — on the layer the README claims it on. The mechanism is not
unreachable, but the abstraction level where the README promises a
demonstration has none.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C5. `BudgetedStream`'s per-chunk guard

**Claim.**

> `BudgetedStream` counts tokens per chunk and raises the moment the budget
> is crossed, mid-stream.
>
> — `README.md:80-82`

Same claim: `README.zh-TW.md:54`, `docs/scope.md:46`
("The budget bites mid-response"), `docs/scope.zh-TW.md:34`,
`docs/design.md:202`, `docs/design.zh-TW.md:169`.

**What the code does.** The guard is correct and genuinely per chunk. But
no stream reaches it. `consult` receives a complete `dict` from the judge,
serialises it, and feeds `_chunks` (`src/agentcp/agents.py:76`), which
re-slices an already-arrived string into 20-character pieces. The "stream"
is a loop over a finished answer. See D3 for the comment that says
otherwise.

**Experiment.** Read `src/agentcp/agents.py:159-171`: the judge is called
at line 159 and returns a `dict`; `BudgetedStream(_chunks(text),
remaining)` is constructed at line 171 from that dict's serialisation.

**Class.** C. `BudgetedStream` is a guard written for a live stream it has
not yet been given.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C6. Three exported names with no readers

**Claim.** Each is in the package's public surface, which advertises it as
something a caller uses.

**What the code does.**

- `BudgetedStream.emitted` — declared at `src/agentcp/budget.py:56`,
  written at `:63`, read nowhere. `consult` keeps its own list
  (`src/agentcp/agents.py:172`).
- `evals.GoldenCase` — `src/agentcp/evals.py:39-45`, exported in
  `src/agentcp/__init__.py:12` and `:33`, zero consumers and zero tests.
  Its presence implies a golden set, which `docs/scope.md:93-102`
  correctly places out of scope.
- `privacy.PLACEHOLDER` — `src/agentcp/privacy.py:43`, zero consumers,
  zero tests.

**Experiment.**

```
$ grep -rn --include=*.py 'GoldenCase' src/ tests/ examples/
src/agentcp/evals.py:40:class GoldenCase:
src/agentcp/__init__.py:12:from agentcp.evals import GateResult, GoldenCase, run_gate
src/agentcp/__init__.py:33:    "GateResult", "GoldenCase", "run_gate",

$ grep -rn --include=*.py 'PLACEHOLDER' src/ tests/ examples/
src/agentcp/privacy.py:43:PLACEHOLDER = re.compile(r"<(EMAIL|HOST|USER)_(\d+)>")

$ grep -rn --include=*.py 'emitted' src/agentcp/
src/agentcp/agents.py:172:    emitted: list[str] = []
src/agentcp/agents.py:176:            emitted.append(chunk)
src/agentcp/agents.py:229:        verdict["text"] = "".join(emitted)
src/agentcp/budget.py:56:        self.emitted: list[str] = []
src/agentcp/budget.py:63:            self.emitted.append(chunk)
```

**Class.** C. The cost is specific: a reader checking whether a mechanism
is real, who finds a field that is written and never read, pays more in
trust than the two lines are worth.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### C7. `drift.detect` and `evals.run_gate`

**Claim.** `README.md:133-137` lists `gate` among the ten scenarios that
demonstrate the six properties, and `docs/scope.md:49-53` lists five gate
and drift rows in the table of implemented *control-plane* properties.

**What the code does.** Neither is wired into the pipeline.
`drift.detect` has no caller under `src/` other than its re-export in
`src/agentcp/__init__.py`; the only call site is
`examples/run_pipeline.py:184`. `docs/scope.md:16-20` defines this
repository's boundary as control-plane properties — who may do what, where
data may go, when the run stops — and drift detection is none of the
three.

**Experiment.**

```
$ grep -rn --include=*.py 'detect' src/ examples/
src/agentcp/drift.py:49:def detect(cfg: MetricConfig, window: list[float], current: float) -> DriftVerdict:
src/agentcp/__init__.py:11:from agentcp.drift import DriftVerdict, MetricConfig, detect
src/agentcp/__init__.py:32:    "DriftVerdict", "MetricConfig", "detect",
examples/run_pipeline.py:184:        v = drift.detect(cfg, window, current)
```

**Class.** C, with a qualification worth recording: this is not an
unfounded claim but a **well-founded irrelevance**. Both modules do what
they say. They are release-gate policy, not execution-gate policy, and the
page that draws this repository's boundary does not say so. `fix-plan.md`
leaves the choice between deleting them and saying so in one sentence open
for the author.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

## Class D — said more broadly than done

### D1. "The tenant quota is what actually caps spend"

**Claim.**

> The check that saves money is the one *before* the call, when the budget
> is already gone; the tenant quota is what actually caps spend.
>
> — `README.md:94-95`

Same claim: `README.zh-TW.md:58` (「而真正能限制花費的是租戶配額」).

**What the code does.** `LEDGER.charge` runs *after* the judge returns
(`src/agentcp/agents.py:199`), so an over-quota tenant is refused for the
*next* call, not this one. Budget and quota are structurally symmetric:
both are pre-call gates, checked eleven lines apart
(`src/agentcp/agents.py:142` and `:150-151`), and neither can stop a reply
that is already in flight.

This sentence was itself written to correct an earlier exaggeration about
the budget. It replaced one overstatement with another.

**Experiment.** The `trial` tenant has a 500-token limit; one call reports
1,000,000 tokens. Recorded in `fix-plan.md` §1.2:

```
這一次呼叫計費   : 1000000
ledger 事後餘額  : 0
這一次被拒絕了嗎 : True（事後）
```

The call was billed in full and the refusal is retrospective.

**Class.** D.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D2. "The budget bites mid-response"

**Claim.**

> | The budget bites mid-response | per-chunk counting | `test_budget.py` |
>
> — `docs/scope.md:46`

Same claim: `docs/scope.zh-TW.md:34`, `docs/design.md:202`,
`docs/design.zh-TW.md:169`, `README.md:80-82`, `README.zh-TW.md:54`.

**What the code does.** True of `BudgetedStream` in isolation, which is
what `test_budget.py` exercises. False of a response, because nothing in
this repository produces a response incrementally — see C5 and D3.

**Experiment.** See C5.

**Class.** D. The row claims a property of the system; the mechanism cited
holds it only for an input the system does not supply.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D3. "Chunk size the provider's prose is streamed in"

**Claim.**

> ```python
> #: Chunk size the provider's prose is streamed in. Small enough that the
> #: budget guard bites part-way through a response rather than after it.
> CHUNK_CHARS = 20
> ```
>
> — `src/agentcp/agents.py:30-32`

**What the code does.** The prose is not streamed. `_chunks`
(`src/agentcp/agents.py:76-78`) re-slices a reply that has already arrived
complete. Both sentences of the comment are wrong in the same way: the
first asserts a stream that does not exist, the second a guard that cannot
bite part-way through an answer that is already finished.

This is the single most misleading line of comment in `src/`, because it
is the line a reader consults to find out what the budget guard is for.

**Experiment.** See C5.

**Class.** D.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D4. "One bad tool degrades a step"

**Claim.**

> A tool that raises is converted to `{"error": ...}` so one bad tool
> degrades a step instead of killing a run that is holding an approval.
>
> — `README.md:74-75`

Same claim: `README.zh-TW.md:50`, `docs/architecture.md:43-44`,
`docs/architecture.zh-TW.md:29`, `docs/design.md:88`
(`ERR["{'error': ...}<br/>one step degrades"]`),
`docs/design.zh-TW.md:78`, `docs/design.md:201` and
`docs/design.zh-TW.md:168` (the claim column for
`test_a_raising_tool_degrades_instead_of_crashing`), and
`src/agentcp/tools.py:9-10`.

**What the code does.** `invoke` does convert the exception
(`src/agentcp/tools.py:139-141`). What no caller does is look at the
result. The step does not degrade — it reports success on zero data and
then deploys.

**Experiment.** `read_diff` is made to raise `RuntimeError('GitHub 503')`
and the `approve` scenario is run. Recorded in `fix-plan.md` §1.3:

```
judge 被要求審查的內容 : {'text': 'error: RuntimeError: GitHub 503'}
review_report         : {'approved': True, 'comments': [], ...}
deployed              : True
tools actually called : ['read_ticket', 'write_plan', 'deploy']
```

The error object is handed to the judge as the diff to review, the judge
approves it, and the pipeline deploys. The static half:

```
$ grep -rn '"error"' src/ examples/
src/agentcp/tools.py:10:  into ``{"error": ...}``, so a broken tool degrades one step instead of
src/agentcp/tools.py:122:        The tool's result, or ``{"error": ...}`` if the tool raised.
src/agentcp/tools.py:141:        return {"error": f"{type(exc).__name__}: {exc}"}
```

Three hits: a docstring, a docstring, and the producer. No consumer.

**Class.** D. What `invoke` guarantees is that an exception does not
propagate into the graph — a real and useful property. That a step
*degrades* is a different claim, and it needs a caller to cooperate.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D5. The reject path, and "declined at the gate"

**Claim.**

> ```
> H -->|"resume with approve=False<br/>or with nothing"| E3(["END — no deploy"])
> ```
>
> — `docs/design.md:39`; same in `docs/design.zh-TW.md:34`

> | `reject`  | declined at the gate -- `deploy` is never called |
>
> — `README.md:153`; same in `README.zh-TW.md:90`

**What the code does.** Rejection does not end at the gate. Both the
approved and the unapproved path run `deployer`, and the refusal lives
*inside* it (`src/agentcp/agents.py:311-315`) — which is precisely why
"resume with no decision" cannot deploy, and is the stronger design. The
`reject` and `ignore` scenario outputs both show `deployer` in the trail.
`docs/architecture.md:23-25` describes it correctly; the design diagram
contradicts the architecture page.

The same correction applies to "declined at the gate". The gate declines
nothing: `approval_gate_node` (`src/agentcp/agents.py:333-341`) does not
read `human_decision` at all — it clears `requires_approval` and returns.

**Experiment.**

```
$ uv run --with langgraph python examples/run_pipeline.py reject
```

The trail reaches `deployer`, and `deploy_report` reads
`{'deployed': False, 'reason': 'no human approval on record'}` — the
reason string is written by `deployer_node`, not by the gate.

**Class.** D for the README's wording; a straight contradiction between
two documents for the diagram.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D6. "Every tool here is a stub that prints what it would call"

**Claim.**

> Every tool here is a stub that prints what it *would* call.
>
> — `examples/adapters.py:3`

**What the code does.** It appends to `CALLS` and prints nothing. The
README has it right — "a stub that records the call it would have made"
(`README.md:265-266`) — so the file and the page that describes it
disagree, and the file is the one that is wrong.

**Experiment.**

```
$ grep -n 'print' examples/adapters.py
```

No hits.

**Class.** D. Small, and worth recording anyway: the integration surface
is the first file a reader opens to find out how to use this, and its
second sentence is false.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D7. "Never reads another agent's internals"

**Claim.**

> Each agent writes exactly one `*_report` key and never reads another
> agent's internals, so a reviewer can tell from this file alone what any
> node is allowed to produce.
>
> — `src/agentcp/state.py:3-5`

**What the code does.** `deployer_node` reads
`state.get("plan_report", {})` and passes it to the `deploy` tool
(`src/agentcp/agents.py:318`). Either that is reading another agent's
internals, or a `*_report` slot is a published contract rather than an
internal — which is the reading the design supports, since the reports are
the only channel between agents. The docstring should say which.

**Experiment.**

```
$ grep -n 'state.get("plan_report"' src/agentcp/agents.py
318:            "deployer", "deploy", {"plan": state.get("plan_report", {})},
```

**Class.** D. The sentence is not describing a defect — it is describing
the right design with the wrong word.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D8. `durability="require"` verifies durability

**Claim.**

> `"require"` refuses to compile unless *checkpointer* can outlive the
> process.
>
> — `src/agentcp/graph.py:49-52`

Same claim: `README.md:296-299`, `README.zh-TW.md:204`,
`docs/scope.md:54` and `:193`, `docs/scope.zh-TW.md:42` and `:119`.

**What the code does.** It rejects `None` and instances of `MemorySaver`
(`src/agentcp/graph.py:67-77`). That is a blacklist with one entry, not a
verification — no type-level check can establish that a store survives a
restart. The half that is true, and is worth keeping, is that it refuses
to *pretend*: it will not silently fall back, and an explicit
`MemorySaver` does not buy its way past.

**Experiment.** See B4, whose positive test passes a store that does not
store anything.

**Class.** D.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D9. "A checkpoint holding real values would undo the masking at rest"

**Claim.**

> What does *not* cross any surface is the unmasking map. It is returned to
> the caller in process and never written to state, because state is
> checkpointed and a checkpoint holding real values would undo the masking
> exactly where the data rests.
>
> — `docs/architecture.md:53-56`; same in `docs/architecture.zh-TW.md:33`

**What the code does.** The first half is true: the mapping is never
written to state. The second half states a general rule the code does not
keep — `payload` is checkpointed verbatim, real values and all, as B3's
own fixture demonstrates.

It is also the wrong rule to want. The masking boundary is the *model*,
not storage: a ticket comes from Jira, so your own database already holds
it, and what masking exists to prevent is sending identifiers to a third
party. The defensible claim is the narrower one — the restore mapping must
never be checkpointed — which is exactly what `Consultation`'s design
backs up.

**Experiment.** See B3.

**Class.** D.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

### D10. The reader is sent to look at `masked: True`

**Claim.**

> It also fires in an ordinary run: the diff fixture carries an author
> address and a build host, so the reviewer's call record reads
> `masked: True` in `approve` and `gemma` too.
>
> — `README.md:114-116`; same in `README.zh-TW.md:66`

**What the code does.** The fact is true — the reviewer's call record is
`('reviewer', 'local-small', True, ...)`. But `run_pipeline.show()`
(`examples/run_pipeline.py:44-66`) prints the trail, the steps, the
reports, `model calls` and `tokens`, and never prints `masked`. The reader
is sent to an exhibit that stays silent.

Measured against `README.md:16` — "Every claim below is one of those ten
scenarios, and each prints what actually happened" — this is the one place
the README points at evidence that is not in the output.

**Experiment.**

```
$ uv run --with langgraph python examples/run_pipeline.py approve | grep -i masked
```

No output.

**Class.** D.

**How it was fixed.** *(empty — filled in when the fix lands.)*

---

## What this list is for

Twenty-five entries, from one repository whose tests were all green and
whose ten scenarios all ran. That is the point worth taking away: none of
these was found by running the suite, because a suite can only check the
claims someone thought to encode. They were found by reading each sentence
of the documentation as if it were an assertion and then trying to make it
fail.

If documentation is part of the program, a sentence that overstates a
guarantee is a defect of the same kind as a wrong branch — and the harder
kind to find, because nothing goes red.
