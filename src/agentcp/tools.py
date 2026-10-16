"""Tool registry with per-agent access control.

Two rules the registry enforces, both of which exist because the alternative
has a failure mode worse than a wrong answer:

- **An agent may call only the tools on its allow-list.** Permission lives
  here, next to the call, not in whatever prompt happened to be assembled.
  A prompt that says "do not use deploy" is a request; this is a check.
- **A tool never raises into the graph.** ``invoke`` converts any exception
  into ``{"error": ...}``, so a broken tool degrades one step instead of
  killing a run that may be holding a human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ToolFn = Callable[[dict], dict]


@dataclass(frozen=True)
class Tool:
    """One callable the agents can select.

    Attributes
    ----------
    name : str
        Stable identifier; appears in the allow-lists and the audit trail.
    description : str
        One line, shown to whatever selects tools.
    parameters : dict
        JSON-schema-shaped argument spec.
    fn : ToolFn
        ``(args) -> dict``. May raise; ``invoke`` contains it.
    """

    name: str
    description: str
    parameters: dict
    fn: ToolFn


REGISTRY: dict[str, Tool] = {}

#: agent -> tools it may call. Absent agent means "no tools".
ACCESS: dict[str, frozenset[str]] = {
    "triage": frozenset({"read_ticket", "label_ticket"}),
    "planner": frozenset({"read_ticket", "write_plan"}),
    "reviewer": frozenset({"read_diff", "post_comment"}),
    "deployer": frozenset({"read_plan", "deploy"}),
}


class ToolNotFound(KeyError):
    """No tool registered under that name."""


class AccessDenied(PermissionError):
    """The agent is not on that tool's allow-list."""


def register(tool: Tool) -> None:
    """Add or replace a tool."""
    REGISTRY[tool.name] = tool


def schemas_for(agent: str) -> list[dict]:
    """OpenAI-style tool schemas for exactly what *agent* may call.

    Generated from the registry and the allow-list, so a tool cannot be
    offered to a model that is not permitted to run it. One source, so the
    offer and the check cannot drift apart.
    """
    allowed = ACCESS.get(agent, frozenset())
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in REGISTRY.values()
        if t.name in allowed
    ]


def invoke(agent: str, name: str, args: dict) -> dict:
    """Run *name* on behalf of *agent*, checking permission first.

    Returns
    -------
    dict
        The tool's result, or ``{"error": ...}`` if the tool raised.

    Raises
    ------
    ToolNotFound, AccessDenied
        These are caller bugs, not tool failures, so they are not swallowed.
    """
    if name not in REGISTRY:
        raise ToolNotFound(f"no tool {name!r}")
    if name not in ACCESS.get(agent, frozenset()):
        raise AccessDenied(
            f"{agent!r} may not call {name!r}; allowed: {sorted(ACCESS.get(agent, []))}"
        )
    try:
        return REGISTRY[name].fn(args)
    except Exception as exc:  # noqa: BLE001 — containment is the point
        return {"error": f"{type(exc).__name__}: {exc}"}
