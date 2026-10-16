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

Two surfaces, and nothing crosses between them except through a tool call.

**The state surface** is in-process. Agents never pass values to each
other; they read `payload` and prior reports from `PipelineState` and write
exactly one `*_report` slot each. `completed` is append-only, so the audit
trail cannot be rewritten by a later node.

**The tool surface** is the only way out. Every call goes through `invoke`,
which checks the agent against `ACCESS` before the adapter runs. An adapter
that raises is converted to an error object, so a broken integration
degrades one step.

Source: [`state.py`](../src/agentcp/state.py), [`tools.py`](../src/agentcp/tools.py)

## 3. Data state

![state lifecycle](state.svg)

Each of the 14 fields has one writer, and the diagram names it.

The row that matters is the third: `human_decision` is writable only by
resuming an interrupted run. No agent can set it, which is what makes
"the reviewer cannot approve on the human's behalf" a structural property
rather than a convention.

Source: [`state.py`](../src/agentcp/state.py), [`agents.py`](../src/agentcp/agents.py)

## 4. Usage scenarios

![scenarios](scenarios.svg)

The six scenarios in [`examples/run_pipeline.py`](../examples/run_pipeline.py).
Each is runnable:

```bash
uv run --with langgraph python examples/run_pipeline.py approve
```

Three of the six end in "did not deploy", which is the intended shape: the
interesting cases for a deploy pipeline are the ones where it declines.

---

| View | Tests that pin it |
|---|---|
| Control flow | `test_routing.py`, `test_handoff.py` |
| Data flow | `test_tool_access.py` |
| Data state | `test_hitl.py` |
| Scenarios | all seven test files |
