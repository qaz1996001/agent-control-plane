"""agent-control-plane — a deterministic control plane for agent pipelines.

The thesis: let a model decide *within* a step, never *between* steps.
Routing, permissions, budget and approval are ordinary code, so a run is
replayable and a wrong decision is findable by reading a table.
"""

from agentcp.budget import BudgetedStream, BudgetExceeded
from agentcp.drift import DriftVerdict, MetricConfig, detect
from agentcp.evals import GateResult, GoldenCase, run_gate
from agentcp.router import ROUTE_TABLE, UnknownTrigger, next_node, route
from agentcp.state import PipelineState, new_state
from agentcp.tools import AccessDenied, Tool, ToolNotFound, invoke, register, schemas_for

__all__ = [
    "BudgetedStream", "BudgetExceeded",
    "DriftVerdict", "MetricConfig", "detect",
    "GateResult", "GoldenCase", "run_gate",
    "ROUTE_TABLE", "UnknownTrigger", "next_node", "route",
    "PipelineState", "new_state",
    "AccessDenied", "Tool", "ToolNotFound", "invoke", "register", "schemas_for",
]
