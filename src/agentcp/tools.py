"""Tool registry with per-agent access control.

Two rules the registry enforces, both of which exist because the alternative
has a failure mode worse than a wrong answer:

- **An agent may call only the tools on its allow-list.** Permission lives
  here, next to the call, not in whatever prompt happened to be assembled.
  A prompt that says "do not use publish" is a request; this is a check.
- **A tool never raises into the graph.** ``invoke`` converts any exception
  into ``{"error": ...}``, so a broken tool degrades one step instead of
  killing a run that may be holding a human approval.

Permission has two dimensions, and they compose in one direction only.
``ACCESS`` says what a role may ever do; ``TENANT_DENY`` subtracts from
that per tenant. Subtraction rather than a second grant table, so a
tenant rule can only ever narrow a role -- there is no combination of
the two tables that gives a tenant something the role itself lacks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    "triage": frozenset({"read_document", "tag_document"}),
    "indexer": frozenset({"read_document", "write_index"}),
    "assessor": frozenset({"read_draft", "post_finding"}),
    "publisher": frozenset({"read_index", "publish"}),
}

#: tenant -> tools withheld from it, whatever the agent's role allows.
#: Absent tenant means "nothing withheld".
TENANT_DENY: dict[str, frozenset[str]] = {
    "trial": frozenset({"publish"}),
}

#: The tenant used when a caller does not name one.
DEFAULT_TENANT = "default"


class ToolNotFound(KeyError):
    """No tool registered under that name."""


class AccessDenied(PermissionError):
    """The agent is not on that tool's allow-list."""


def register(tool: Tool) -> None:
    """Add or replace a tool."""
    REGISTRY[tool.name] = tool


def allowed(agent: str, tenant: str = DEFAULT_TENANT) -> frozenset[str]:
    """What *agent* may call on behalf of *tenant*.

    The single source both the offer and the check read. If these ever
    became two computations, the schemas advertised to a model and the
    permissions enforced at the call would drift the first time someone
    edited one table.
    """
    return ACCESS.get(agent, frozenset()) - TENANT_DENY.get(tenant, frozenset())


def schemas_for(agent: str, tenant: str = DEFAULT_TENANT) -> list[dict]:
    """OpenAI-style tool schemas for exactly what *agent* may call.

    Generated from the registry and the allow-list, so a tool cannot be
    offered to a model that is not permitted to run it. One source, so the
    offer and the check cannot drift apart.
    """
    allowed_names = allowed(agent, tenant)
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
        if t.name in allowed_names
    ]


def invoke(agent: str, name: str, args: dict, tenant: str = DEFAULT_TENANT) -> dict:
    """Run *name* on behalf of *agent*, checking permission first.

    Returns
    -------
    dict
        The tool's result, or ``{"error": ...}`` if the tool raised.

    Raises
    ------
    ToolNotFound, AccessDenied
        These are caller bugs or policy refusals, not tool failures, so
        they are not swallowed into an error object.
    """
    if name not in REGISTRY:
        raise ToolNotFound(f"no tool {name!r}")
    permitted = allowed(agent, tenant)
    if name not in permitted:
        raise AccessDenied(
            f"{agent!r} may not call {name!r} for tenant {tenant!r}; "
            f"allowed: {sorted(permitted)}"
        )
    try:
        return REGISTRY[name].fn(args)
    except Exception as exc:  # noqa: BLE001 - containment is the point
        return {"error": f"{type(exc).__name__}: {exc}"}
