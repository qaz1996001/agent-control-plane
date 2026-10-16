"""Graph construction.

LangGraph supplies the runtime -- node execution, checkpointing, and the
interrupt that makes human approval a first-class pause rather than a
polling loop. What it does not supply is the routing policy, and that is
deliberate: ``router.next_node`` is an ordinary function over state, so the
route is testable without building a graph at all.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentcp import agents, router
from agentcp.state import PipelineState

#: Node names in the order the router may reach them.
NODE_NAMES = ("triage", "planner", "reviewer", "approval_gate", "deployer")


def _edge_target(state: PipelineState) -> str:
    """Adapt :func:`router.next_node` to LangGraph's sentinel."""
    nxt = router.next_node(state)
    return END if nxt == "__end__" else nxt


def build_graph(judge=None, checkpointer=None):
    """Compile the pipeline graph.

    Parameters
    ----------
    judge : callable or None
        Injected into every node that needs a judgement. ``None`` uses the
        deterministic defaults in :mod:`agentcp.agents`.
    checkpointer : BaseCheckpointSaver or None
        Required for interrupt/resume. Defaults to an in-memory saver.

    Returns
    -------
    CompiledStateGraph
        Compiled with ``interrupt_before=["approval_gate"]``, so a run that
        reaches the gate stops and waits instead of deciding for itself.
    """
    g = StateGraph(PipelineState)

    for name in NODE_NAMES:
        fn = agents.NODES[name]
        if name == "approval_gate":
            g.add_node(name, fn)
        else:
            g.add_node(name, lambda s, _fn=fn: _fn(s, judge))

    g.add_conditional_edges(START, lambda s: router.route(s["trigger"]))
    for name in NODE_NAMES:
        g.add_conditional_edges(name, _edge_target)

    return g.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["approval_gate"],
    )
