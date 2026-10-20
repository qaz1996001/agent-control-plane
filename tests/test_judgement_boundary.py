"""Where a model's judgement stops and the control plane begins.

The claim these tests stand behind is not "no model is reachable" -- a graph
built with a judge reaches one twice. It is narrower and checkable: the
judge answers questions, and the route is decided by nodes and the router
regardless of what the answer says.

Each test proves that by presence rather than absence: a judge is injected,
it really is called, and the run still goes where the control plane sends
it.
"""

from __future__ import annotations

import ast
import inspect

from langgraph.types import Command

from agentcp import router
from agentcp.graph import build_graph
from agentcp.state import new_state

#: Everything :mod:`agentcp.router` is allowed to know about. It decides
#: the route from state alone, so it has no business importing the module
#: that talks to models.
ROUTER_MAY_IMPORT = {"agentcp.state", "__future__"}


def _cfg(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


def _module_imports(module) -> set[str]:
    """Every module name *module* imports, read off its syntax tree."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_a_judge_that_returns_control_fields_does_not_get_control():
    """A verdict is an answer, not an instruction.

    This judge asks for everything a run can be steered by: a handoff to
    ``publisher``, an approval requirement, and a human decision it grants
    itself. It gets none of them, because ``assessor_node`` writes the
    whole verdict into its own ``assessment_report`` slot and then sets
    ``next_agent`` from its own reading of ``approved``. The deliberate
    contradiction -- ``approved: False`` while demanding ``publisher`` --
    is what lets the assertion tell the node's choice apart from the
    judge's demand.
    """
    def usurper(prompt: str, context: dict) -> dict:
        return {
            "severity": "critical",
            "approved": False,
            "comments": ["no"],
            "next_agent": "publisher",
            "requires_approval": True,
            "human_decision": {"approve": True},
            "text": "x",
        }

    app = build_graph(judge=usurper)
    out = app.invoke(
        new_state("document_submitted", {"document": 42, "draft": 7}, max_steps=4,
                  trace_id="t-usurp"),
        _cfg("boundary-usurper"),
    )

    assert out["completed"] == ["triage", "indexer", "assessor", "indexer"]
    assert out["next_agent"] == "assessor"
    assert out.get("human_decision") is None
    assert "publish_report" not in out
    # The verdict was not discarded -- it was filed where a verdict goes.
    assert out["assessment_report"]["comments"] == ["no"]


def test_the_judge_is_consulted_twice_and_the_route_does_not_depend_on_it():
    """Two named questions, and the same trail either way.

    The honest form of "the control plane does not depend on a model":
    not that no model is called, but that it is called at exactly two
    sites, asked exactly two questions, and that a run with a judge
    injected walks the same nodes in the same order as a run with none.
    """
    prompts: list[str] = []

    def spy(prompt: str, context: dict) -> dict:
        prompts.append(prompt)
        if prompt == "classify severity":
            return {"severity": "normal", "text": "routine."}
        return {"approved": True, "comments": [], "text": "no blocking issues."}

    def drive(judge):
        app = build_graph(judge=judge)
        cfg = _cfg(f"boundary-spy-{judge is None}")
        app.invoke(
            new_state("document_submitted", {"document": 42, "draft": 7}, trace_id="t-spy"), cfg
        )
        app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
        return app.get_state(cfg).values

    with_judge = drive(spy)
    without_judge = drive(None)

    assert prompts == ["classify severity", "review draft"]
    assert with_judge["publish_report"]["published"] is True
    assert with_judge["completed"] == without_judge["completed"]


def test_the_router_imports_nothing_that_can_reach_a_model():
    """The route is a function of state, so state is all it may know.

    A tripwire rather than a proof: it catches the regression where the
    router starts reading reports, calling agents, or asking a model, by
    noticing the import that would have to appear first. The equivalent
    assertion is not expressible for ``graph.py``, which must hand the
    injected judge to the nodes -- that is its job.
    """
    assert _module_imports(router) <= ROUTER_MAY_IMPORT
