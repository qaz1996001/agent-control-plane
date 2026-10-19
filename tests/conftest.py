import pytest

from agentcp import agents, quota, tools
from agentcp.state import new_state


@pytest.fixture(autouse=True)
def registry():
    """A clean registry of fake tools for every test."""
    tools.REGISTRY.clear()
    for name, result in [
        ("read_ticket", {"title": "login fails", "body": "500 on submit"}),
        ("label_ticket", {"labelled": True}),
        ("write_plan", {"steps": ["reproduce", "fix", "test"]}),
        ("read_diff", {"files": 3, "additions": 40}),
        ("post_comment", {"posted": True}),
        ("read_plan", {"steps": ["reproduce", "fix", "test"]}),
        ("deploy", {"release": "r-123"}),
    ]:
        tools.register(
            tools.Tool(name, f"fake {name}", {"type": "object"}, lambda a, r=result: dict(r))
        )
    yield tools.REGISTRY
    tools.REGISTRY.clear()


@pytest.fixture(autouse=True)
def ledger():
    """A fresh per-tenant quota ledger for every test."""
    agents.LEDGER = quota.Ledger()
    yield agents.LEDGER
    agents.LEDGER = quota.Ledger()


@pytest.fixture
def exploding_tool():
    """Replace a tool with one that raises, to test containment."""
    def _install(name):
        tools.register(
            tools.Tool(name, "boom", {"type": "object"},
                       lambda a: (_ for _ in ()).throw(RuntimeError("upstream down")))
        )
    return _install


@pytest.fixture
def state():
    return new_state("ticket_opened", {"ticket": 42, "pr": 7}, trace_id="t-run-1")
