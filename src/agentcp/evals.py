"""Regression gate over a golden set.

The gate's job is to stop a change that makes answers worse. Everything
here follows from that:

- **Several metrics, each with its own threshold.** One blended score hides
  which property regressed.
- **One metric deliberately has no threshold.** ``context_fallback_rate`` is
  diagnostic: it says how much of ``citation_accuracy`` came from loose
  substring matching rather than real citations. A high value means the
  accuracy number is partly fictional. It explains another metric, so
  gating on it would be gating on an explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: metric -> minimum acceptable value.
THRESHOLDS: dict[str, float] = {
    "pass_rate": 0.85,
    "citation_accuracy": 0.90,
}

#: Measured, reported, never gated. See the module docstring.
UNGATED: frozenset[str] = frozenset({"context_fallback_rate"})


@dataclass(frozen=True)
class GoldenCase:
    """One benchmark case."""

    case_id: str
    question: str
    expected_refs: tuple[str, ...]


@dataclass
class GateResult:
    """Outcome of one gate run."""

    passed: bool
    metrics: dict[str, float]
    regressions: list[dict] = field(default_factory=list)

    def explain(self) -> str:
        if self.passed:
            return "gate passed"
        return "; ".join(
            f"{r['metric']} {r['value']:.3f} < {r['threshold']:.3f}"
            for r in self.regressions
        )


def find_regressions(metrics: dict[str, float]) -> list[dict]:
    """Return every metric below its threshold.

    Reports *which* metric, its value and the bar — "it failed" is not
    actionable. Metrics in :data:`UNGATED` are skipped however bad they are.
    """
    out = []
    for name, floor in THRESHOLDS.items():
        if name in UNGATED:
            continue
        value = metrics.get(name, 0.0)
        if value < floor:
            out.append({"metric": name, "value": value, "threshold": floor})
    return out


def run_gate(metrics: dict[str, float]) -> GateResult:
    """Evaluate *metrics* against the thresholds."""
    regressions = find_regressions(metrics)
    return GateResult(passed=not regressions, metrics=dict(metrics), regressions=regressions)
