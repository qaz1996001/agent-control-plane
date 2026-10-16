"""Both metric directions go through one comparison."""

from agentcp.drift import MIN_WINDOW, MetricConfig, detect

HIGHER = MetricConfig("pass_rate", higher_is_better=True)
LOWER = MetricConfig("p95_latency_ms", higher_is_better=False)
STABLE = [0.90, 0.91, 0.89, 0.90, 0.92, 0.90]
LAT = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0]


def test_higher_is_better_flags_a_drop():
    assert detect(HIGHER, STABLE, 0.40).drifted


def test_higher_is_better_ignores_a_rise():
    assert detect(HIGHER, STABLE, 0.99).status == "ok"


def test_lower_is_better_flags_a_rise():
    assert detect(LOWER, LAT, 400.0).drifted


def test_lower_is_better_ignores_a_drop():
    assert detect(LOWER, LAT, 20.0).status == "ok"


def test_both_directions_report_negative_z_when_worse():
    """The normalisation is the point: 'worse' is always a negative z."""
    assert detect(HIGHER, STABLE, 0.40).z < 0
    assert detect(LOWER, LAT, 400.0).z < 0


def test_short_window_is_insufficient_data_not_ok():
    v = detect(HIGHER, STABLE[: MIN_WINDOW - 1], 0.10)
    assert v.status == "insufficient_data"
    assert not v.drifted
    assert "need" in v.detail


def test_flat_baseline_is_insufficient_data_not_infinite_z():
    v = detect(HIGHER, [0.9] * 10, 0.1)
    assert v.status == "insufficient_data"
    assert "zero variance" in v.detail
