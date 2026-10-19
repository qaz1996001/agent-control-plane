"""Graph construction.

LangGraph supplies the runtime -- node execution, checkpointing, and the
interrupt that makes human approval a first-class pause rather than a
polling loop. What it does not supply is the routing policy, and that is
deliberate: ``router.next_node`` is an ordinary function over state, so the
route is testable without building a graph at all.

Durability is opt-in and, when asked for, fails loudly. The default
in-memory saver is fine for a demo and useless for a pause that has to
survive a restart -- but a silent fallback to it would make "I forgot to
configure a store" and "I chose the in-memory store" look identical from
outside. Every class of bug worth preventing here has that shape.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentcp import agents, router
from agentcp.state import PipelineState

#: Node names in the order the router may reach them.
NODE_NAMES = ("triage", "planner", "reviewer", "approval_gate", "deployer")


class DurabilityNotConfigured(RuntimeError):
    """``durability="require"`` without a checkpointer that can deliver it."""


def _edge_target(state: PipelineState) -> str:
    """Adapt :func:`router.next_node` to LangGraph's sentinel."""
    nxt = router.next_node(state)
    return END if nxt == "__end__" else nxt


def build_graph(judge=None, checkpointer=None, durability: str = "memory"):
    """Compile the pipeline graph.

    Parameters
    ----------
    judge : callable or None
        Injected into every node that needs a judgement. ``None`` uses the
        deterministic defaults in :mod:`agentcp.agents`.
    checkpointer : BaseCheckpointSaver or None
        Required for interrupt/resume. Defaults to an in-memory saver.
    durability : {"memory", "require"}
        ``"require"`` refuses to compile unless *checkpointer* can outlive
        the process. Passing a :class:`MemorySaver` explicitly does not
        satisfy it -- the point is whether a pause survives a restart, not
        whether the caller supplied an object.

    Returns
    -------
    CompiledStateGraph
        Compiled with ``interrupt_before=["approval_gate"]``, so a run that
        reaches the gate stops and waits instead of deciding for itself.

    Raises
    ------
    DurabilityNotConfigured
        Durability was required and is not available.
    """
    if durability not in ("memory", "require"):
        raise ValueError(f"durability must be 'memory' or 'require', got {durability!r}")
    if durability == "require":
        if checkpointer is None:
            raise DurabilityNotConfigured(
                "durability='require' needs a checkpointer that survives a "
                "restart; refusing to fall back to MemorySaver"
            )
        if isinstance(checkpointer, MemorySaver):
            raise DurabilityNotConfigured(
                "MemorySaver cannot survive a restart, so it does not "
                "satisfy durability='require'"
            )

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
