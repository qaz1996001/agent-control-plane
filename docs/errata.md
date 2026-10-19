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

Each entry's **"How it was fixed"** slot is the exception, and says so: its
citations are to the files as they stand now, and were checked the same
way. Every slot names which of three things happened — a mechanism was
strengthened so the original claim became true, a claim was narrowed to
what the code does, or nothing was done. The third is not a failure of the
list; an errata file that quietly marked its own entries done would be the
defect it exists to catch. D11 and D12 were added after the first
twenty-five and are pinned to their own commit.

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

**How it was fixed.** **Mechanism strengthened.** `87d0e06`, merged as
`b2bd411`. `state.PROTECTED` (`src/agentcp/state.py:47-49`; line numbers
in this slot and every other "How it was fixed" are current, not pinned to
`eb66c3d`) names the five keys no node may write, and `_guarded`
(`src/agentcp/graph.py:43-62`) wraps every node registered by
`build_graph` (`:123`) and raises `ProtectedFieldWritten` if a patch names
one of them. It raises rather than dropping, for the reason the commit
gives: a node writing `human_decision` "is a bug in that node, and
dropping the key would leave the bug in place and invisible" — the same
judgement `router.route` already makes about an unknown trigger. The gate
goes through the wrapper too, being "the one node registered without a
judge, which is exactly the kind of special case that used to mean
'without the wrapper' as well".

Red when removed: the commit records seven tests going red when the
wrapper is deleted. The two that pin this entry are
`test_a_node_cannot_forge_the_human_decision_and_deploy`
(`tests/test_state_protection.py:68`), which runs the experiment above as
the attack rather than describing it, and
`test_the_gate_goes_through_the_same_guard_as_every_other_node` (`:168`).

Not closed, deliberately: the second probe still works. `next_agent` is
not in `PROTECTED`, because handing off is what a node is *for*, so a node
can still route straight to the deployer — and what refuses is the
deployer, not the gate.
`test_routing_straight_to_the_deployer_still_does_not_deploy` (`:88`)
asserts that outcome rather than leaving it for a reader to find.

The prose caught up at `docs/architecture.md:75-93` and
`docs/architecture.zh-TW.md:43-47`, in two passes on purpose: `d54af5a`
first narrowed every site to "a convention of the nodes, not a property of
the state", so the record of the claim being ahead of the code survives in
the history rather than only here. One site did not catch up:
`README.md:356-359` still reads "The state type does not yet stop a node
that tries", which is true of the type and false of the graph.

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

**How it was fixed.** **Mechanism strengthened.** Same guard, same
commit (`87d0e06`), which is the shape this entry predicted: the gap was
structural and shared, so the remedy was too. All four constants sit in
`PROTECTED` alongside the decision (`src/agentcp/state.py:47-49`,
current), so `max_steps`, `sensitivity`, `tenant` and `trace_id` are
refused by `_guarded` on the same line. The commit names each consequence
it closes: relaxing the runaway guard, "drop[ping] the residency veto by
rewriting sensitivity", escaping "its tenant's allow-list and quota", and
rebinding "the mask namespace via trace_id".

Red when removed: `test_a_node_cannot_write_a_protected_field`
(`tests/test_state_protection.py:50-51`) is parametrised over
`sorted(PROTECTED)`, so the list and the test cannot drift — "a guard that
covers four of five fields is the same bug in a smaller place, and a
hand-written test per field would be the thing that gets forgotten when
the list grows". Remove the wrapper and all five parametrisations go red.

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

**How it was fixed.** **Mechanism strengthened.** `87d0e06`. `completed`
and `calls` are now `Annotated[list[...], operator.add]`
(`src/agentcp/state.py:104` and `:110`, current), so append-only is the
channel's property rather than each node remembering to splice instead of
assign. `_advance` (`src/agentcp/agents.py:270-273`) and `_bill`
(`:276-280`) return only their own contribution.

Red when removed: four tests, by the commit's count.
`test_a_node_cannot_rewrite_the_audit_trail`
(`tests/test_state_protection.py:108`) runs this entry's probe — a rogue
planner returning `completed=["planner"]` — and
`test_a_node_cannot_erase_another_nodes_call_record` (`:126`) does the
same for the ledger. The risk the change introduced is double-counting a
contribution the node already reported, and
`test_an_ordinary_run_appends_each_node_exactly_once` (`:152`) is the test
for it.

What the reducer does not buy is named in the test rather than left for a
reader to discover (`:136-141`): a node can still decline to report *its
own* call, because its own contribution is what it returns. That is the
weaker problem — a node can omit itself, never rewrite another's record —
and closing it would mean `consult` writing the ledger instead of handing
the record back, which is a different design.

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

**How it was fixed.** **Claim narrowed, both halves.** `0e16832`. The
sentence is now a count and a correction rather than a guarantee
(`docs/architecture.md:67-73`, current):

> There are 18 fields. One writer each holds for the four `*_report` slots
> and for `human_decision`; it does not hold for the rest. `next_agent` is
> written by four nodes, `step_count` and `completed` by five (every node
> goes through `_advance`), `calls` and `tokens_used` by two, and
> `requires_approval` by two — the reviewer sets it and the gate clears
> it. The diagram groups those under "written by nodes" rather than naming
> each, so it shows *when* a field is written rather than by whom.

Same at `docs/architecture.zh-TW.md:41`. The diagram half was fixed in the
diagram and not only in the prose about it: `docs/src/state.json:11` is
now subtitled 「18 個欄位，依『什麼時候被寫』分組」 and node `f2`
(`:106-107`) is labelled 「節點寫入（分組，非逐格指名）」 with the
per-field counts as its sublabel. The claim the diagram makes is now one
it can keep — what it shows is *when* a field is written, "which is a
useful thing to show -- it just is not the claim that was made for it".

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

**How it was fixed.** **Mechanism strengthened in the suite; still open
in the prose.** `f09da29` deleted `test_routing_touches_no_model` rather
than repairing it, because the assertion cannot be made to depend on the
monkeypatches: `route()` calls nothing. The honest replacement is
behavioural and lands in `5cbad3f` —
`test_the_judge_is_consulted_twice_and_the_route_does_not_depend_on_it`
(`tests/test_judgement_boundary.py:84`, current) injects a spy, asserts
the model is asked exactly two named questions at two sites, and asserts a
run *with* a judge walks the same trail as a run with none; and
`test_the_router_imports_nothing_that_can_reach_a_model` (`:117`) is a
tripwire on `router.py`'s imports, "deliberately not written for
`graph.py`, whose job is to hand the judge to the nodes". In the deleted
test's place `f09da29` put the seam no test had ever looked at:
`graph.NODE_NAMES`, `router.ROUTE_TABLE` and `agents.NODES` are now pinned
to each other (`tests/test_routing.py:27`, `:37`, `:42`), so a route
naming an agent the graph does not build fails in CI rather than at
`invoke`.

What is red when the mechanism is removed is weaker here than for the
class-A entries, and worth saying: the two replacements go red for a
second judge call site and for a router import respectively, but neither
commit records a removal check the way `87d0e06` does.

Still open, and created by the repair: ten sites advertise a test that no
longer exists. `README.md:339-340` still promises "**The control plane
runs with every model entry point monkeypatched to raise** — if routing
ever consulted a model, this test fails"; `README.md:59` and `:503`,
`README.zh-TW.md:326`, `docs/scope.md:32` and `:188`,
`docs/scope.zh-TW.md:20` and `:106` repeat it, and `docs/design.md:217`
with `docs/design.zh-TW.md:167` name `test_routing_touches_no_model` in
the claim/test table. Closing it means pointing those sentences at the two
`test_judgement_boundary.py` assertions, which claim less and are true, or
deleting them.

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

**How it was fixed.** **Mechanism strengthened.** `23601bb`. The
substring is gone: `_functions_calling_the_injected_judge`
(`tests/test_audit.py:55-72`, current) parses `agents.py` and walks it for
any `ast.Call` whose callee expression mentions the name `judge`, so it
sees `(judge or default)(...)`, a bare `judge(...)`, "and anything else
whose callee expression mentions the injected judge". The test is renamed
to what it checks —
`test_only_consult_contains_a_call_to_the_injected_judge` (`:273`). A
behavioural complement, `test_every_judge_call_in_a_run_went_through_consult`
(`:278`), wraps `agents.consult` in a counter and the judge in a spy and
asserts the two counts are equal, "because same-count is the real claim".

Red when removed: this entry's own experiment. A node written
`verdict = judge(state, {})` now appears in the AST walk's list, and makes
the judge's count exceed the door's in the behavioural test.

Still open, small: four pages still name the old test —
`docs/architecture.md:54`, `docs/architecture.zh-TW.md:31`,
`docs/design.md:236` and `docs/design.zh-TW.md:186`. The test they point
at is the right one; its name is three months stale.

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

**How it was fixed.** **Mechanism strengthened.** `23601bb`. The test
now asserts the run really did mask something before it looks for a leak —
`assert any(c["masked"] for c in values["calls"]), "nothing was masked to
leak"` (`tests/test_audit.py:238`, current) — so it cannot pass by there
being nothing to find. It then walks the entire checkpoint through
`_everything_in` (`:41-52`) for a `privacy.Mapping` **or** any dict keyed
by a placeholder (`:239-246`), which is what a map smuggled out flattened
looks like. The companion
`test_the_judge_sees_only_masked_context_for_every_call_in_a_run` (`:249`)
asserts the same property over a whole graph run rather than one
hand-picked `consult`, "so it covers every node that consults rather than
the one the test happened to pick".

Red when removed: replace `privacy.mask` with a no-op and the first
assertion goes red. That is precisely what the old pair of assertions did
not do.

The fixture's own violation was dealt with by moving the PII rather than
deleting it: `plant_pii_in_the_ticket` (`:24-38`) registers a `read_ticket`
returning an address and an internal hostname, "because `payload` is
caller-supplied identification that is checkpointed verbatim by design --
the masking boundary is the model, not our own datastore". That argument is
the resolution this entry's split half asked for; where it did *not* get
written is D9, which is still open.

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

**How it was fixed.** **Claim narrowed.** `87d0e06`. No mechanism was
added, because none can be — see D8. The test is still a tautology and now
says so, which is all it can honestly claim. It is renamed
`test_a_saver_that_is_not_a_memorysaver_is_accepted_on_trust`
(`tests/test_durability.py:35-45`, current), and the fake saver's
docstring is the narrowing:

> It stores nothing and cannot actually checkpoint -- running against it
> raises `NotImplementedError`. That is the point: the guard accepts it,
> which is exactly what "blocklist of known process-local stores" means
> and all this test can claim.
>
> — `tests/test_durability.py:39-42`

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

**How it was fixed.** **Claim narrowed.** `f209d35`. "What is
advertised" is gone; what is left is the agreement that is actually pinned
(`README.md:72-77`, current):

> `allowed()` is the single source for two readings of that table:
> `invoke` checks it, `schemas_for` renders it, and a test pins that the
> two agree for every agent and tenant. No node here lets a model pick a
> tool, so the rendering is the seam a tool-calling loop would attach to
> rather than something this pipeline exercises -- the agreement is pinned
> in advance because that is the cheap half.

Same at `docs/design.md:63-71`, whose section heading now reads
"Permission is checked at the call, and **would be** advertised from the
same table"; same at `docs/architecture.md:41-47` and
`README.md:510-512`. The zh-TW sites were rewritten once rather than
twice, because `README.zh-TW.md:50` compresses several English paragraphs
into one line and shares it with D4. Deliberately left standing:
`README.md:348` and the `design.md`/`scope.md` rows describing
`test_schemas_offered_match_the_allow_list`, because "those state exactly
what the test asserts, and the evidence does not ask for less".

Still open, and intended to stay open: the mechanism has no consumer. This
entry's grep repeated today gives the same six lines —
`src/agentcp/tools.py:94`, `src/agentcp/__init__.py:26` and `:40`,
`tests/test_tool_access.py:40`, `:45` and `:65`. What would close it is a
node that offers the schemas and lets a model choose, which is the scope
creep the class-C remedy exists to refuse.

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

**How it was fixed.** **Claim narrowed.** `a2f195c`. Both halves of the
gap are now stated at all three sites. The module docstring's opening
sentence keeps its argument and adds where it stops — "in this repository
only the first is on the pipeline's path" (`src/agentcp/privacy.py:3-5`,
current) — and the paragraph that spells it out
(`src/agentcp/privacy.py:27-33`):

> What this repository does not demonstrate is a pipeline run that
> restores. `mask` covers the *context* sent to the judge; a verdict comes
> back in the model's own words, so a run's answer holds no placeholder of
> ours to put back, and `Consultation.mapping` is returned in process and
> dropped.

`README.md:118-128` and `README.zh-TW.md:64` say the same. The design
diagram was the worse offender and is fixed as a diagram: the edge into
`restore` is now dotted and labelled 「no run takes this edge」
(`docs/design.md:133`), with a paragraph at `:153-162` arguing why
narrowing it does not weaken the case for keeping three endpoints in one
module — "it is an argument about where the check belongs *if* the value
comes back".

`Consultation.mapping` still has no consumer. `grep -rn '\.mapping'` over
`src/ tests/ examples/` now returns exactly one hit, and it is the prose
above.

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

**How it was fixed.** **Claim narrowed.** `a2f195c`. `build_graph`'s
signature is unchanged (`src/agentcp/graph.py:71`); the sentence moved
instead. `README.md:457-462` (current) keeps "`choose` takes the set its
caller believes is up" and finishes it — "but `agents.HEALTHY` is a
module-level constant and `build_graph` has no parameter that injects one,
so a pipeline caller cannot pass a health view at all — that constant is
the seam". `docs/scope.md:162-171` carries the long form under the heading
"**Provider health is a module constant, not an input and not a
measurement.**"; same at `README.zh-TW.md:306` and
`docs/scope.zh-TW.md:100`.

The part worth recording is what the fix added beyond the narrowing: a
reopening condition, `docs/scope.md:212`, under which the health view
becomes a `build_graph` parameter "the moment a hard-coded `HEALTHY` is
*wrong* rather than merely fixed". The commit's reason is the standard the
rest of that table is held to — a non-goal without its reopening condition
is a preference.

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

**How it was fixed.** **Mechanism strengthened for two of the three
filters; the third is still open.** `a1c1e92`. The `residency` scenario
keeps its four direct `providers.choose` rows and then runs the same veto
"on the path a run actually takes" (`examples/run_pipeline.py:290-313`,
current): `sensitivity="restricted"`, `agents.HEALTHY` narrowed to
`{"cloud-small"}`, through the graph into `triage_node` and into
`consult`, where selection refuses before a model is reached. The run
reports `severity: 'unknown'`, stops at one step with no plan, review or
deploy, and leaves a call record with `provider: 'none'` — "the refusal is
auditable, which is the difference between declining and silently coping".
Narrowing the health view means assigning the module constant, and the
comment at `:283-289` says so where it does it rather than hiding the
reach behind a helper, because "a deployment with a live health view has
the same nowhere to put it". Restored in a `finally` (`:302-303`), so the
`quota` scenario that runs next still selects `local-small`.

So the locality veto and the health filter now fire on a pipeline path.
The capable tier still does not. `HIGH_COMPLEXITY_CHARS` is still 200
(`src/agentcp/agents.py:38`), the complexity read is still the length of
the masked blob (`:137`), and no scenario's context comes near it, so
`cost_tier == 2` has never been selected inside a run. What would close it
is a scenario whose masked context crosses 200 characters, or an assertion
on the chosen tier taken from a run's call record rather than from
`providers.choose` directly. Nor is the new run pinned: scenario output is
not a test.

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

**How it was fixed.** **Claim narrowed, incompletely.** `ced66dd`. The
limitation is now stated in three places: `docs/scope.md:173-181`, under
the heading "**Nothing here streams, so no spend check can be
mid-flight.**"; `README.md:105-107` — "`BudgetedStream`'s per-chunk guard
is written for a live stream it has not been handed -- `_chunks` re-slices
a reply that arrived whole"; and `README.zh-TW.md:58`.

Still standing: the headline sentence this entry quotes.
`README.md:87-88` still reads "counts tokens per chunk and raises the
moment the budget is crossed, mid-stream", unqualified, eighteen lines
above the paragraph that withdraws it; `README.zh-TW.md:54` is the same.
A reader who stops at the bold **Budget** paragraph gets the original
claim, and the entry is not closed until that clause is narrowed too.
`docs/design.md:224` was left alone on purpose and correctly: that row
describes `test_stream_is_cut_mid_way_not_after_the_fact`, and of
`BudgetedStream` in isolation the row is true.

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

**How it was fixed.** **Mechanism strengthened — by deletion, and then
by one restoration.** `87d0e06` removed all three names and their exports;
`d618639` put one back, and that is this entry's real resolution.
`BudgetedStream.emitted` and `evals.GoldenCase` are gone and the greps
above now return nothing for either.

`privacy.PLACEHOLDER` was deleted in the same pass and was dead code —
until the masking test being rewritten on another branch needed it.
Walking checkpointed state for a leaked unmasking map takes two checks:
the `Mapping` dataclass itself, and a dict keyed by placeholders, which is
"what a map smuggled out flattened looks like". The second check is this
regex, read at `tests/test_audit.py:244`. So it was restored mid-merge,
with the history kept in the comment above it
(`src/agentcp/privacy.py:52-56`, current): "Deleted once as dead code,
which it was until a test needed to walk checkpointed state looking for a
leaked mapping".

Red when removed: delete `PLACEHOLDER` now and
`test_the_unmasking_map_never_reaches_checkpointed_state` fails outright.
The entry is worth keeping for the lesson rather than the lines — "unused"
is a measurement of one repository at one instant, and two branches of the
same repair disagreed about it inside a day.

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

**How it was fixed.** **Still open.** Nothing in the four merges or the
direct commits on `main` touches it. `docs/scope.md:49-53` still lists
five gate and drift rows in the table of implemented *control-plane*
properties; `docs/scope.md:16-20` still draws the repository's boundary at
"who may do what, where data may go, when the run stops"; and
`README.md:174` still lists `gate` among the ten scenarios that
demonstrate the six properties. The code is unchanged: `drift.detect` and
`evals.run_gate` have no caller under `src/` beyond their re-exports, and
the only call sites remain `examples/run_pipeline.py:214`, `:223` and
`:228`.

What would close it is the sentence `fix-plan.md` left to the author: say
in `scope.md` that those rows are release-gate policy rather than
execution-gate policy and that the table mixes the two deliberately — or
delete the two modules. Either is one commit; neither was made. The
qualification this entry already records — a well-founded irrelevance
rather than an unfounded claim — is an argument for keeping the modules,
not a substitute for saying so on the page that draws the boundary.

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

**How it was fixed.** **Claim narrowed.** `ced66dd`. The sentence that
"was itself written to correct an earlier exaggeration" is replaced by a
symmetric one (`README.md:98-107`, current):

> **One thing neither the budget nor the quota can do**, and the scenario
> says so: a judge that answers in one shot has generated -- and been
> billed for -- its whole reply before anything can count it. [...] The
> two are structurally symmetric, checked within a few lines of each other
> in `consult`, and both are gates *before* the call: the ledger is
> charged only once the judge has returned, so an exhausted quota refuses
> the *next* call rather than this one. Nothing here stops a reply already
> in flight.

Same at `README.zh-TW.md:58`. The commit's argument for why this third
version should hold where two did not: against a `Judge` contract of
`(prompt, context) -> dict` neither gate can refuse a reply already
generated, so this "is a property of the contract, not a gap in a
mechanism -- which is why the fix is a sentence and not a feature".

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

**How it was fixed.** **Claim narrowed.** `ced66dd`. The row now names
the object the property holds for (`docs/scope.md:46`, current):

> | The budget cuts a stream on the chunk that crosses | per-chunk
> counting in `BudgetedStream` | `test_budget.py` |

and the limitation went into the stop-short section
(`docs/scope.md:173-181`), "which is where a reader looking for the edges
will find it". Same at `docs/scope.zh-TW.md:34`. `docs/design.md:224` is
deliberately unchanged — see C5 — and the two README sites are the part of
C5 that is still open.

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

**How it was fixed.** **Claim narrowed.** `ced66dd`. Both false
sentences are gone, and what replaces them says what the constant is for
(`src/agentcp/agents.py:30-34`, current):

> ```python
> #: Chunk size the budget guard counts in. Nothing here streams: ``_chunks``
> #: re-slices a reply that has already arrived whole, so the guard cuts the
> #: accounting part-way, never the generation. The size is what a live
> #: stream would be fed in, if one were ever wired to this seam.
> CHUNK_CHARS = 20
> ```

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

**How it was fixed.** **Mechanism strengthened, after the two claims
were separated.** The prose split landed first (`f209d35`): "an exception
never reaches the graph, and a broken integration cannot kill a run that is
holding an approval" is what `invoke` guarantees on its own and keeps the
paragraph it had, while "whether the *step* degrades" became a sentence
saying it is not yet true and pointing here (`README.md:77-82`,
`docs/architecture.md:41-47`, `README.zh-TW.md:50`,
`docs/architecture.zh-TW.md:29`). Then `87d0e06` made it true: `consult`
refuses on an upstream tool error before the judge is reached
(`src/agentcp/agents.py:156-161`, current), "as a fifth refusal with the
same record-keeping as the other four", so the error object is never
handed to a model as data and the nodes' existing `call.refused` branches
(`:292-295` and `:325-328`) carry it.

Red when removed: one test, by the commit's count —
`test_a_tools_error_is_not_handed_to_a_model_as_if_it_were_data`
(`tests/test_tool_access.py:86-120`), which runs this entry's experiment
and asserts the opposite ending: `"review diff" not in asked`, so the spy
judge is never called at all; `review_report["refused"]` naming the
upstream failure; no `deploy_report`; the run stopped; and the refused
record carrying `tokens_estimated == 0`.

`src/agentcp/tools.py:9-11` still carries the "degrades one step" wording
this entry flagged, and it is now defensible — the reviewer's step degrades
into a refusal and the run ends there rather than deploying on zero data.

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

**How it was fixed.** **Claim narrowed, and the contradiction resolved
in the architecture page's favour.** `0e16832`. The diagram now routes both
resumes into the deployer (`docs/design.md:38-39`, current) with the
refusal as a dotted edge out of it (`:40`), and the paragraph underneath
says why that is the shape worth drawing (`:51-55`):

> Both resume paths run the deployer; the refusal lives *inside* it. That
> is why "resume with nothing" cannot deploy — there is no separate decline
> branch to get wrong — and it is also why `approval_gate` decides nothing:
> it does not read `human_decision` at all, it clears the pending flag and
> returns. A rejection is declined by the deployer, not at the gate.

Same at `docs/design.zh-TW.md:33-35`. "Declined at the gate" is gone from
both READMEs: `README.md:170` now reads "a human declines -- the deployer
refuses, `deploy` is never called", and `README.zh-TW.md:90` matches.
Worth recording what the fix chose to say out loud rather than smooth over:
for the repository's headline mechanism, the gate node turning out to be a
flag-clearer is now stated in the design document.

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

**How it was fixed.** **Claim narrowed.** `0e16832`.
`examples/adapters.py:3` (current) now reads "Every tool here is a stub
that records the call it *would* make", which is what `README.md:284-285`
had said all along. One word, in the first file a reader opens to find out
how to wire this up.

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

**How it was fixed.** **Claim narrowed.** `0e16832`. The docstring now
names the reading the design actually supports, which is the one this entry
argued for (`src/agentcp/state.py:3-7`, current):

> Each agent writes exactly one `*_report` key, and those reports are the
> only channel between agents -- `deployer_node` reads `plan_report`, so a
> report is a published contract rather than an internal. A reviewer can
> tell from this file alone what any node is allowed to produce.

Stronger than the sentence it replaces, as the commit argues, "because it
explains why there is exactly one slot each".

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

**How it was fixed.** **Claim narrowed.** `87d0e06`. The parameter's
docstring now describes a blocklist and names what it cannot buy
(`src/agentcp/graph.py:81-90`, current):

> `"require"` refuses the two ways of not having a durable store: no
> checkpointer at all, and a `MemorySaver` passed explicitly. It is a
> blocklist of what is known to be process-local, **not** a verification
> that the store survives a restart -- nothing in the type says whether it
> does, so an arbitrary `BaseCheckpointSaver` subclass is accepted on
> trust. What the flag buys is that "I forgot to configure a store" and "I
> chose the in-memory one" stop looking identical from outside; what it
> cannot buy is proof.

The test was renamed with it — see B4. `docs/scope.md:54` and `:209` were
left as they stood and are fine: "fails loudly" and "refuses to pretend"
are the half that is true. `README.md:447-449` was not revisited and still
says `durability="require"` "refuses to compile without a store that can
deliver it", which reads as exactly the verification the docstring above
now denies.

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

**How it was fixed.** **Still open**, and the repair work found a
second instance of it.

The claim is unchanged at both sites: `docs/architecture.md:56-59` and
`docs/architecture.zh-TW.md:33` still say the mapping is never written to
state "because state is checkpointed and a checkpoint holding real values
would undo the masking exactly where the data rests". The argument this
entry asked for was written — in the test. `23601bb` moved the fixture's
PII out of `payload` and into the `read_ticket` tool on exactly these
grounds: `payload` "is caller-supplied identification that is checkpointed
verbatim by design -- the masking boundary is the model, not our own
datastore" (`tests/test_audit.py:24-31`). That is the right argument in
the wrong file. Nothing on the architecture page says it.

What the move then exposed is that the general rule is now false in two
ways rather than one. `triage_node` files the raw tool result into its
report:

```python
patch["triage_report"] = {
    "severity": call.verdict.get("severity", "normal"),
    "ticket": ticket,
}
```

> — `src/agentcp/agents.py:296-299`

So with the planted ticket, the address and the internal hostname are
checkpointed inside `triage_report` as well as inside `payload` — tool
output, not caller input, which is the half the "your own database already
holds it" argument does not cover.
`test_the_unmasking_map_never_reaches_checkpointed_state` does not notice
and should not: it looks for the mapping, which is the narrower and
defensible property. Closing this entry means writing that narrower
sentence on the architecture page, in both languages, and deciding whether
a report slot holding unmasked tool output is intended.

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

**How it was fixed.** **Mechanism strengthened.** `b71c94c`. `show()`
now prints the record's own masking field for every call
(`examples/run_pipeline.py:70-78`, current), so the exhibit the README
sends the reader to says something:

```python
mask = "masked" if c.get("masked") else "unmasked"
part = f"{c['agent']}->{c['provider']} {mask}"
```

Printed for every call rather than only the masked ones, and borrowing the
record's field name "so the line maps onto the field a reader goes looking
for. A mark that appeared only when true would make silence mean both
'nothing here needed masking' and 'nobody checked'." Visible in the
abridged output at `README.md:194` as `model calls  2  (triage->local-small
unmasked, reviewer->local-small masked)`.

Nothing pins it. `show()` is example output rather than a test, so the
README sentence this entry was about now rests on a print statement no
assertion defends.

---

### D11. `rework` closes by saying the step guard decided when to stop

**Claim.**

> ```python
> print("\n  the loop did not run forever; max_steps decided when to stop")
> ```
>
> — `examples/run_pipeline.py:125`

This entry and D12 were found after the twenty-five above were written, so
their claims are pinned to `f224cd7^` — the commit before their fix —
rather than to `eb66c3d`.

**What the code does.** Prints unconditionally, closing a run whose loop
exists only because the scenario's own judge is a lambda returning
`approved: False` every time. Swap the judge and the sentence keeps
printing. Under `--gemma` the real model approved the diff on the first
pass, so there was no loop and nothing for the guard to decide: the run
went to the gate and stopped at 3 of 6 steps, under a line saying the guard
had ended it.

**Experiment.** `f224cd7` added `--gemma`, which replaces the judge
everywhere a scenario builds a graph
(`examples/run_pipeline.py:39-44` and `:444-452`). Running every
graph-building scenario against the real model is what exposed this; while
only `gemma` did so, the claim that the control plane cannot tell which
judge it was given rested on the one path chosen to demonstrate it.

**Class.** D. A scenario that demonstrates a guard on a path the judgement
chooses cannot assert the guard fired.

**How it was fixed.** **Mechanism strengthened.** `f224cd7`. The closing
line is now conditional on whether the reviewer was actually visited twice
— `looped = out.get("completed", []).count("reviewer") > 1`
(`examples/run_pipeline.py:138`, current) — and the other branch says what
happened instead, naming the step count the run stopped at and that the
guard was never asked to fire (`:142-152`). Red when removed is not
available: like D10 this is example output, and the guard against it is the
flag that found it.

---

### D12. `budget` closes by naming which refusal each budget got

**Claim.**

> ```python
> print("\n  budget 6 is the one that saves money: nothing was left, so the")
> print("  judge was not called at all. At 12 the reviewer's answer was")
> print("  generated and then refused -- a one-shot model bills for the")
> print("  whole reply before anything can count it, so that refusal buys")
> print("  correctness, not credit. Neither run deployed.")
> ```
>
> — `examples/run_pipeline.py:168-172`, as of `f224cd7^`

**What the code does.** Which of the two refusals a budget gets depends on
what the calls before it cost, and the paragraph hard-codes the answer for
one judge. With the deterministic default, triage's reply is about 6
tokens, so a budget of 12 survives it, the reviewer is called and then cut
off, and the sentence is right. With Gemma the first call alone costs 292,
so both small budgets are gone before the reviewer is reached and both
refusals are the pre-call one — the paragraph then describes a
post-generation refusal that did not happen, three lines under the printed
token counts that contradict it.

**Experiment.** `--gemma`, as for D11. The rows above the paragraph already
print `tokens generated on that call` and either `(the model was never
called)` or `(already spent)`, so the output carried its own refutation and
nobody had read the two together.

**Class.** D. The distinction between the two refusals is the real point
and is true; which one a given budget gets is a fact about one judge,
stated as a fact about the mechanism.

**How it was fixed.** **Mechanism strengthened.** `f224cd7`. The closing
paragraph now explains the two kinds and points at the figures instead of
asserting which happened — "Which of the two a given budget gets depends on
what the calls before it cost, which is why the lines above print the
tokens rather than describing them" (`examples/run_pipeline.py:202-208`,
current) — with the reading left to the computed rows at `:188-193`.
Unpinned, as D10 and D11 are.

---

## What this list is for

Twenty-seven entries, from one repository whose tests were all green and
whose ten scenarios all ran. That is the point worth taking away: none of
the first twenty-five was found by running the suite, because a suite can
only check the claims someone thought to encode. They were found by reading
each sentence of the documentation as if it were an assertion and then
trying to make it fail.

D11 and D12 were found afterwards, and differently: by `--gemma`, which
runs every graph-building scenario against a real model instead of the one
scenario written to show the seam. Both were sentences a scenario prints
about its own run, true of the judge it was written against and false of
another. The two are in this file rather than only in `f224cd7` for the
reason the file exists: the list of ways a claim outruns its evidence is
not closed, and an audit that stopped counting when it published would be
making the same mistake in a different place.

The repairs are recorded above in one of three shapes, said explicitly in
each slot. Twelve entries were closed by strengthening a mechanism,
thirteen by narrowing a sentence to what the code does, and two — C7 and
D9 — were not addressed at all. Four of the twenty-five are only partly
closed, and each says where it stops: B1 and B2 left ten pages and four
pages respectively advertising a test that no longer exists under that
name, C5's narrowing never reached the sentence the entry quotes, and C4
reached two of the three provider filters. C1, C2 and C3 carry scopes that
are now stated precisely and deliberately left unwired, which is what a
class-C remedy is.

That two of the repairs created fresh instances of the original defect —
prose pointing at a test that was renamed or deleted under it — is the
least surprising result here, and the one most worth the record.

If documentation is part of the program, a sentence that overstates a
guarantee is a defect of the same kind as a wrong branch — and the harder
kind to find, because nothing goes red.
