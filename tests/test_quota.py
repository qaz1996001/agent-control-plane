import pytest

from agentcp import agents, quota
from agentcp.state import new_state


def test_one_tenant_running_out_does_not_touch_another():
    ledger = quota.Ledger()
    with pytest.raises(quota.QuotaExceeded):
        ledger.charge("trial", quota.limit_for("trial") + 1)
    assert ledger.used("default") == 0
    assert ledger.remaining("default") == quota.DEFAULT_LIMIT


def test_the_error_says_when_to_come_back():
    """Without retry_after a caller picks between hammering and giving up."""
    ledger = quota.Ledger()
    with pytest.raises(quota.QuotaExceeded) as exc:
        ledger.charge("trial", 10_000)
    assert exc.value.retry_after == quota.WINDOW_SECONDS
    assert exc.value.tenant == "trial"
    assert exc.value.limit == quota.limit_for("trial")


def test_the_spend_that_broke_the_limit_is_still_counted():
    ledger = quota.Ledger()
    with pytest.raises(quota.QuotaExceeded):
        ledger.charge("trial", 600)
    assert ledger.used("trial") == 600
    assert ledger.remaining("trial") == 0


def test_a_tenant_with_no_override_gets_the_default_limit():
    assert quota.limit_for("some-new-tenant") == quota.DEFAULT_LIMIT


def test_reset_starts_a_new_window_for_one_tenant_only():
    ledger = quota.Ledger()
    ledger.charge("a", 10)
    ledger.charge("b", 10)
    ledger.reset("a")
    assert ledger.used("a") == 0
    assert ledger.used("b") == 10


def test_a_node_refuses_once_the_tenant_has_nothing_left():
    agents.LEDGER.charge("default", quota.DEFAULT_LIMIT)
    state = new_state("ticket_opened", {"ticket": 1}, trace_id="t-1")
    patch = agents.triage_node(state)
    assert patch["triage_report"]["refused"]
    assert patch["next_agent"] is None


def test_the_refusal_is_recorded_rather_than_raised_into_the_graph():
    agents.LEDGER.charge("default", quota.DEFAULT_LIMIT)
    state = new_state("ticket_opened", {"ticket": 1}, trace_id="t-1")
    patch = agents.triage_node(state)
    assert len(patch["calls"]) == 1
    assert patch["calls"][0]["refused"]
