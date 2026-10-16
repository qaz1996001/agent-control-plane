"""Sliding-window drift detection.

Some metrics are better when they go up, some when they go down. Writing
two code paths for that means two places for the comparison to be wrong, so
direction is normalised once -- ``higher_is_better`` flips the sign of the
deviation and everything downstream compares the same way.

Stateless by design: pure functions over a window the caller supplies, so
the same code runs in a job, a test, or an ad-hoc query.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class MetricConfig:
    """How to read one metric."""

    name: str
    higher_is_better: bool
    z_threshold: float = 2.0


@dataclass(frozen=True)
class DriftVerdict:
    """Result for one metric.

    ``status`` is one of ``"ok"``, ``"drift"`` or ``"insufficient_data"``.
    The third is a first-class answer: a window too short to say anything
    must not be reported as "no drift".
    """

    metric: str
    status: str
    z: float | None = None
    detail: str = ""

    @property
    def drifted(self) -> bool:
        return self.status == "drift"


MIN_WINDOW = 5


def detect(cfg: MetricConfig, window: list[float], current: float) -> DriftVerdict:
    """Compare *current* against the baseline *window*.

    Returns ``insufficient_data`` when the window is too short or flat --
    a zero-variance baseline makes a z-score undefined, and inventing one
    would manufacture an alert out of nothing.
    """
    if len(window) < MIN_WINDOW:
        return DriftVerdict(
            cfg.name,
            "insufficient_data",
            detail=f"window has {len(window)} points, need {MIN_WINDOW}",
        )
    sigma = pstdev(window)
    if sigma == 0:
        return DriftVerdict(
            cfg.name, "insufficient_data", detail="baseline has zero variance"
        )

    raw_z = (current - mean(window)) / sigma
    # One normalisation, one comparison: a negative z always means "worse".
    z = raw_z if cfg.higher_is_better else -raw_z
    if z < -cfg.z_threshold:
        return DriftVerdict(cfg.name, "drift", z=z, detail="moved against the metric")
    return DriftVerdict(cfg.name, "ok", z=z)
