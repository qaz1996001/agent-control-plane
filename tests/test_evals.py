"""The gate blocks on quality, and never on its own diagnostics."""

from agentcp import evals
from agentcp.evals import THRESHOLDS, UNGATED, find_regressions, run_gate


def test_all_metrics_above_threshold_passes():
    assert run_gate({"pass_rate": 0.9, "citation_accuracy": 0.95}).passed


def test_one_metric_below_threshold_blocks():
    r = run_gate({"pass_rate": 0.50, "citation_accuracy": 0.95})
    assert not r.passed
    assert [x["metric"] for x in r.regressions] == ["pass_rate"]


def test_the_failure_says_which_metric_and_by_how_much():
    r = run_gate({"pass_rate": 0.50, "citation_accuracy": 0.95})
    assert "pass_rate" in r.explain() and "0.850" in r.explain()


def test_a_missing_metric_counts_as_zero_not_as_a_pass():
    r = run_gate({"citation_accuracy": 0.99})
    assert not r.passed and r.regressions[0]["metric"] == "pass_rate"


def test_the_diagnostic_metric_never_blocks_however_bad():
    r = run_gate({"pass_rate": 0.99, "citation_accuracy": 0.99,
                  "context_fallback_rate": 1.0})
    assert r.passed
    assert "context_fallback_rate" in r.metrics       # measured and reported
    assert all(x["metric"] != "context_fallback_rate" for x in r.regressions)


def test_the_ungated_metric_has_no_threshold_entry():
    """Belt and braces: it must not even be gateable by accident."""
    assert not (UNGATED & set(THRESHOLDS))


def test_find_regressions_is_pure():
    m = {"pass_rate": 0.1}
    find_regressions(m)
    assert m == {"pass_rate": 0.1}


def test_a_result_records_the_policy_it_was_judged_under():
    result = evals.run_gate({"pass_rate": 0.9, "citation_accuracy": 0.95})
    assert result.policy == evals.THRESHOLDS
    assert result.policy_version == evals.POLICY_VERSION


def test_raising_the_bar_later_does_not_rewrite_an_earlier_verdict():
    """Otherwise last quarter's passes look judged against today's bar."""
    result = evals.run_gate({"pass_rate": 0.9, "citation_accuracy": 0.95})
    before = dict(result.policy)
    original = evals.THRESHOLDS["pass_rate"]
    evals.THRESHOLDS["pass_rate"] = 0.99
    try:
        assert result.policy == before
        assert result.policy["pass_rate"] == original
        assert result.passed is True
    finally:
        evals.THRESHOLDS["pass_rate"] = original


def test_the_snapshot_is_a_copy_not_a_live_reference():
    result = evals.run_gate({"pass_rate": 0.9, "citation_accuracy": 0.95})
    result.policy["pass_rate"] = 0.1
    assert evals.THRESHOLDS["pass_rate"] != 0.1
