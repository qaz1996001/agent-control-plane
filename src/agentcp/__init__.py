"""agent-control-plane — a deterministic control plane for agent pipelines.

The thesis: let a model decide *within* a step, never *between* steps.
Routing, permissions, budget, pseudonymisation, provider choice and
approval are ordinary code, so a run is replayable and a wrong decision
is findable by reading a table.
"""

from agentcp.audit import CallRecord, settle
from agentcp.budget import BudgetedStream, BudgetExceeded
from agentcp.drift import DriftVerdict, MetricConfig, detect
from agentcp.evals import GateResult, run_gate
from agentcp.graph import DurabilityNotConfigured, build_graph
from agentcp.privacy import Mapping, RestoreDenied, TraceMismatch, Viewer, mask, restore
from agentcp.providers import Choice, NoEligibleProvider, Provider, choose
from agentcp.quota import Ledger, QuotaExceeded
from agentcp.router import ROUTE_TABLE, UnknownTrigger, next_node, route
from agentcp.state import PipelineState, new_state
from agentcp.tools import (
    AccessDenied,
    Tool,
    ToolNotFound,
    allowed,
    invoke,
    register,
    schemas_for,
)

__all__ = [
    "ROUTE_TABLE",
    "AccessDenied",
    "BudgetExceeded",
    "BudgetedStream",
    "CallRecord",
    "Choice",
    "DriftVerdict",
    "DurabilityNotConfigured",
    "GateResult",
    "Ledger",
    "Mapping",
    "MetricConfig",
    "NoEligibleProvider",
    "PipelineState",
    "Provider",
    "QuotaExceeded",
    "RestoreDenied",
    "Tool",
    "ToolNotFound",
    "TraceMismatch",
    "UnknownTrigger",
    "Viewer",
    "allowed",
    "build_graph",
    "choose",
    "detect",
    "invoke",
    "mask",
    "new_state",
    "next_node",
    "register",
    "restore",
    "route",
    "run_gate",
    "schemas_for",
    "settle",
]
