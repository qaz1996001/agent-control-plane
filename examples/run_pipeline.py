"""Run the pipeline end to end and print what happened.

    python examples/run_pipeline.py              # all scenarios
    python examples/run_pipeline.py approve      # just one

Scenarios
---------
approve   a ticket goes all the way to deploy, pausing for a human
reject    the same run, rejected at the gate -- nothing deploys
ignore    resumed with no decision at all -- still nothing deploys
rework    the reviewer sends it back; the loop ends at the step guard
budget    an over-long model response is cut off mid-stream
gate      a release is blocked by the eval gate, then allowed
"""

from __future__ import annotations

import sys

from langgraph.types import Command

import adapters
from agentcp import drift, evals
from agentcp.budget import BudgetedStream, BudgetExceeded
from agentcp.graph import build_graph
from agentcp.state import new_state

W = 74


def head(title: str) -> None:
    print(f"\n{'-' * W}\n{title}\n{'-' * W}")


def show(state: dict) -> None:
    print(f"  trail        {' -> '.join(state.get('completed', [])) or '(none)'}")
    print(f"  steps        {state.get('step_count', 0)} / {state.get('max_steps')}")
    for key in ("triage_report", "plan_report", "review_report", "deploy_report"):
        if key in state:
            print(f"  {key:<12} {state[key]}")


def pipeline(thread: str):
    adapters.reset()
    app = build_graph()
    cfg = {"configurable": {"thread_id": thread}}
    app.invoke(new_state("ticket_opened", {"ticket": 4821, "pr": 318}), cfg)
    return app, cfg


def scenario_approve() -> None:
    head("approve -- a human says yes, and only then does it deploy")
    app, cfg = pipeline("approve")
    snap = app.get_state(cfg)
    print(f"  paused at    {snap.next}          <- the run is stopped, not polling")
    print(f"  deployed?    {'deploy_report' in snap.values}")
    print("\n  ...a reviewer approves in Slack / the web UI...\n")
    out = app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
    show(out)
    print(f"\n  tools called {[n for n, _ in adapters.CALLS]}")


def scenario_reject() -> None:
    head("reject -- same run, declined at the gate")
    app, cfg = pipeline("reject")
    out = app.invoke(
        Command(update={"human_decision": {"approve": False, "reason": "no tests"}}), cfg
    )
    show(out)
    print(f"\n  deploy called? {'deploy' in [n for n, _ in adapters.CALLS]}")


def scenario_ignore() -> None:
    head("ignore -- resumed with no decision; absence of consent is not consent")
    app, cfg = pipeline("ignore")
    out = app.invoke(None, cfg)
    show(out)


def scenario_rework() -> None:
    head("rework -- reviewer sends it back; the step guard ends the loop")
    adapters.reset()
    app = build_graph(judge=lambda prompt, ctx: {"approved": False, "comments": ["add tests"]})
    cfg = {"configurable": {"thread_id": "rework"}}
    out = app.invoke(
        new_state("ticket_opened", {"ticket": 4821, "pr": 318}, max_steps=6), cfg
    )
    show(out)
    print("\n  the loop did not run forever; max_steps decided when to stop")


def scenario_budget() -> None:
    head("budget -- a long response is cut mid-stream, not billed and then regretted")
    chunks = ["lorem ipsum dolor sit " * 2] * 20          # ~11 tokens each
    stream = BudgetedStream(chunks, budget=30)
    emitted = 0
    try:
        for _ in stream:
            emitted += 1
    except BudgetExceeded as exc:
        print(f"  emitted      {emitted} chunks before the cut")
        print(f"  raised       {exc}")
    print(f"  estimate     {stream.used} tokens")
    stream.settle(27)
    print(f"  provider     {stream.used} tokens   <- real count replaces the estimate")


def scenario_gate() -> None:
    head("gate -- a release is blocked, fixed, then allowed")
    bad = {"pass_rate": 0.62, "citation_accuracy": 0.94, "context_fallback_rate": 0.55}
    res = evals.run_gate(bad)
    print(f"  metrics      {bad}")
    print(f"  passed       {res.passed}")
    print(f"  why          {res.explain()}")
    print("  note         context_fallback_rate is 0.55 and did NOT block --")
    print("               it explains citation_accuracy, so gating on it would")
    print("               be gating on an explanation.")

    good = {**bad, "pass_rate": 0.91}
    print(f"\n  after fix    passed={evals.run_gate(good).passed}")

    cfg = drift.MetricConfig("pass_rate", higher_is_better=True)
    window = [0.90, 0.91, 0.89, 0.90, 0.92, 0.90]
    for current in (0.91, 0.55):
        v = drift.detect(cfg, window, current)
        print(f"  drift @{current:<5} {v.status:<18} z={v.z if v.z is None else round(v.z, 2)}")


SCENARIOS = {
    "approve": scenario_approve,
    "reject": scenario_reject,
    "ignore": scenario_ignore,
    "rework": scenario_rework,
    "budget": scenario_budget,
    "gate": scenario_gate,
}


def main() -> None:
    adapters.register_stubs()
    wanted = sys.argv[1:] or list(SCENARIOS)
    for name in wanted:
        if name not in SCENARIOS:
            raise SystemExit(f"unknown scenario {name!r}; pick from {list(SCENARIOS)}")
        SCENARIOS[name]()
    print()


if __name__ == "__main__":
    main()
