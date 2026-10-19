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
- **A result keeps the policy it was judged under.** Thresholds get
  raised as a system matures. If a stored result only holds the verdict,
  raising a bar silently rewrites history: last quarter's passes start
  looking like they were judged against today's bar. Snapshotting the
  thresholds into the result is what keeps "this passed" a statement
  about a specific moment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Bumped by hand whenever THRESHOLDS changes, so two results are
#: comparable only when their versions match.
POLICY_VERSION = "1"

#: metric -> minimum acceptable value.
THRESHOLDS: dict[str, float] = {
    "pass_rate": 0.85,
    "citation_accuracy": 0.90,
}

#: Measured, reported, never gated. See the module docstring.
UNGATED: frozenset[str] = frozenset({"context_fallback_rate"})


@dataclass
class GateResult:
    """Outcome of one gate run, with the policy that produced it.

    ``policy`` is a copy, not a reference. A later edit to
    :data:`THRESHOLDS` must not reach back into a decision already made.
    """

    passed: bool
    metrics: dict[str, float]
    regressions: list[dict] = field(default_factory=list)
    policy: dict[str, float] = field(default_factory=dict)
    policy_version: str = ""

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
    """Evaluate *metrics* against the thresholds in force right now."""
    regressions = find_regressions(metrics)
    return GateResult(
        passed=not regressions,
        metrics=dict(metrics),
        regressions=regressions,
        policy=dict(THRESHOLDS),
        policy_version=POLICY_VERSION,
    )
