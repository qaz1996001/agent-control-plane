"""The budget has to bite while the stream is still open."""

import pytest

from agentcp.budget import BudgetedStream, BudgetExceeded, estimate_tokens


def test_stream_under_budget_passes_through():
    s = BudgetedStream(["abcd", "efgh"], budget=100)
    assert list(s) == ["abcd", "efgh"]
    assert s.used == 2


def test_stream_is_cut_mid_way_not_after_the_fact():
    chunks = ["x" * 40] * 10          # 10 tokens each
    s = BudgetedStream(chunks, budget=25)
    got = []
    with pytest.raises(BudgetExceeded) as e:
        for c in s:
            got.append(c)
    assert len(got) == 2, "should stop on the chunk that crosses, not at the end"
    assert e.value.budget == 25 and e.value.used > 25


def test_the_exception_carries_what_the_caller_needs():
    s = BudgetedStream(["y" * 400], budget=10)
    with pytest.raises(BudgetExceeded) as e:
        list(s)
    assert e.value.used == 100 and e.value.budget == 10


def test_real_usage_overwrites_the_estimate():
    s = BudgetedStream(["hello world"], budget=100)
    list(s)
    estimated = s.used
    s.settle(7)
    assert estimated != 7
    assert s.used == 7 and s.settled is True


def test_estimate_rounds_up_so_a_short_chunk_is_never_free():
    assert estimate_tokens("a") == 1
    assert estimate_tokens("") == 0
