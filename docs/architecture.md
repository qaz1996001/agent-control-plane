*English ｜ [繁體中文](architecture.zh-TW.md)*

# Architecture — four views

[`design.md`](design.md) argues *why* the control plane is ordinary code.
This page shows *what the code actually does*, in four views.

Diagrams are generated from JSON in [`src/`](src); edit the JSON and
re-render rather than hand-editing the SVG.

---

## 1. Control flow

![control flow](flow.svg)

`route()` turns a trigger into an entry node. After every node,
`next_node()` applies a fixed precedence: the step guard first, then a
pending approval, then an explicit hand-off, then stop. The guard is first
so a cycle cannot out-vote it.

`approval_gate` is compiled with `interrupt_before`, so reaching it stops
the run and checkpoints it. The deployer is reached on both the approved
and the unapproved path — the refusal lives *inside* the deployer, which
is why "resume with no decision" still cannot deploy.

Source: [`router.py`](../src/agentcp/router.py), [`graph.py`](../src/agentcp/graph.py)

## 2. Data flow

![data flow](dataflow.svg)

Three surfaces, and a node reaches the outside world through exactly
two of them — each a single function.

**The state surface** is in-process. Agents never pass values to each
other; they read `payload` and prior reports from `PipelineState` and write
exactly one `*_report` slot each. `completed` and `calls` are append-only,
so the audit trail cannot be rewritten by a later node.

**The tool surface** is one way out. Every call goes through `invoke`,
which checks the agent against `allowed(agent, tenant)` before the adapter
runs. An adapter that raises is converted to an error object, so an
exception never reaches the graph and a broken integration cannot kill a
run that is holding an approval. Whether the *step* degrades is the
caller's half of that bargain, and no caller here inspects the key yet —
[`errata.md`](errata.md), D4.

**The model surface** is the other, and it is `consult` — the only place
in the package a `Judge` is called. Masking, provider selection, the
budget, the quota and the audit record all sit behind that one function,
so they are not things a node has to remember. A second entry point would
make every one of them optional, which is why
`test_consult_is_the_only_place_a_judge_is_called` exists.

What does *not* cross any surface is the unmasking map. It is returned to
the caller in process and never written to state, because state is
checkpointed and a checkpoint holding real values would undo the masking
exactly where the data rests.

Source: [`state.py`](../src/agentcp/state.py), [`tools.py`](../src/agentcp/tools.py), [`agents.py`](../src/agentcp/agents.py), [`privacy.py`](../src/agentcp/privacy.py), [`providers.py`](../src/agentcp/providers.py)

## 3. Data state

![state lifecycle](state.svg)

Each of the 18 fields has one writer, and the diagram names it.

The row that matters is `human_decision`: the only thing that writes it
today is a resume carrying a decision, and no node writes it. That is a
convention of the nodes, not yet a property of the state — `PipelineState`
is a bare `TypedDict` and `graph.py` merges a node's patch into state
unchanged, so a node that returned `human_decision` would forge a human
approval and nothing would reject it. The gap, and the reducer that is to
close it, are entry A1 in [`errata.md`](errata.md).

Four fields are set once at `new_state` and only read afterwards —
`trace_id`, `tenant`, `sensitivity`, `max_steps`. They are the run's
identity and its constraints, and nothing during the run may relax them.
Giving each an explicit value at creation rather than defaulting it at the
point of use is deliberate: "unset" and "set to the default" should not
read the same.

Source: [`state.py`](../src/agentcp/state.py), [`agents.py`](../src/agentcp/agents.py), [`audit.py`](../src/agentcp/audit.py)

## 4. Usage scenarios

![scenarios](scenarios.svg)

The scenarios in [`examples/run_pipeline.py`](../examples/run_pipeline.py).
Each is runnable:

```bash
uv run --with langgraph python examples/run_pipeline.py approve
```

Most of them end in "did not deploy", which is the intended shape: the
interesting cases for a deploy pipeline are the ones where it declines,
and there are more ways to decline than to proceed.

---

| View | Tests that pin it |
|---|---|
| Control flow | `test_routing.py`, `test_handoff.py` |
| Data flow | `test_tool_access.py`, `test_privacy.py`, `test_providers.py` |
| Data state | `test_hitl.py`, `test_audit.py` |
| Scenarios | all twelve test files |

What this page does not cover is the boundary itself — which
capabilities of the original system are here, which were left out, and
why. That is [`scope.md`](scope.md).
