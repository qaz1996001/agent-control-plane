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
mask      what the model is shown, and who may see it unmasked again
residency restricted content refuses rather than leaving the deployment
quota     a tenant runs out of allowance; the run refuses and records it
gemma     the same run as `approve`, with a real local model judging

The first nine need no model and no network. `gemma` wants a local Ollama
serving Gemma 4 E4B (`ollama pull gemma4:e4b`); without it the scenario
explains what is missing and skips, so the default run still works offline.
"""

from __future__ import annotations

import sys

from langgraph.types import Command

import adapters
import gemma_judge
from agentcp import agents, drift, evals, privacy, providers, quota
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
    calls = state.get("calls") or []
    if calls:
        routed = ", ".join(f"{c['agent']}->{c['provider']}" for c in calls)
        print(f"  model calls  {len(calls)}  ({routed})")
        print(f"  tokens       {state.get('tokens_used')} / {state.get('budget_tokens')}")


def pipeline(thread: str):
    adapters.reset()
    app = build_graph()
    cfg = {"configurable": {"thread_id": thread}}
    app.invoke(new_state("ticket_opened", {"ticket": 4821, "pr": 318}, trace_id=thread), cfg)
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
        new_state("ticket_opened", {"ticket": 4821, "pr": 318},
                  max_steps=6, trace_id="rework"),
        cfg,
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


def scenario_mask() -> None:
    head("mask -- the model sees placeholders; restoring takes a permission")
    text = ("reporter sam.okafor@example.com hit a 500 on db-prod-3.internal; "
            "@rhea-ops is on call")
    masked, mapping = privacy.mask(text, "run-7")
    print(f"  original     {text}")
    print(f"  to the model {masked}")
    print(f"  leaks?       {privacy.leaks(masked, mapping)}   <- checked over the whole string")

    ops = privacy.Viewer("ops", may_unmask=True)
    print()
    print(f"  as ops       {privacy.restore(masked, mapping, trace_id='run-7', viewer=ops)}")
    try:
        privacy.restore(masked, mapping, trace_id="run-7", viewer=privacy.Viewer("anon"))
    except privacy.RestoreDenied as exc:
        print(f"  as anon      refused: {exc}")
    try:
        privacy.restore(masked, mapping, trace_id="run-9", viewer=ops)
    except privacy.TraceMismatch as exc:
        print(f"  wrong run    refused: {exc}")
    print()
    print("  the map stays in process -- it is never written into state,")
    print("  because state gets checkpointed and a checkpoint holding the")
    print("  real values would undo the masking at rest.")


def scenario_residency() -> None:
    head("residency -- sensitivity is a veto, not a preference")
    for sensitivity, healthy, label in [
        ("open", providers.ALL_HEALTHY, "everything up"),
        ("restricted", providers.ALL_HEALTHY, "everything up"),
        ("open", {"cloud-small"}, "only remote up"),
        ("restricted", {"cloud-small"}, "only remote up"),
    ]:
        try:
            choice = providers.choose(sensitivity, "low", healthy)
            print(f"  {sensitivity:<11}{label:<17} -> {choice.provider.name}")
        except providers.NoEligibleProvider as exc:
            print(f"  {sensitivity:<11}{label:<17} -> refused: {exc}")
    print()
    print("  the last row is the point: the only healthy provider was")
    print("  remote, and the answer was still no.")


def scenario_quota() -> None:
    head("quota -- a tenant runs out; the run declines and says so")
    adapters.reset()
    agents.LEDGER = quota.Ledger()
    agents.LEDGER.charge("trial", quota.limit_for("trial"))
    print(f"  tenant       'trial', limit {quota.limit_for('trial')} tokens, already spent")

    app = build_graph()
    cfg = {"configurable": {"thread_id": "quota"}}
    out = app.invoke(
        new_state("ticket_opened", {"ticket": 4821, "pr": 318},
                  tenant="trial", trace_id="quota"),
        cfg,
    )
    show(out)
    print()
    print(f"  call records {out.get('calls')}")
    print("  the attempt is in the ledger even though no model ran --")
    print("  \"nothing happened\" and \"we declined\" are different answers.")
    agents.LEDGER = quota.Ledger()


def _run_approving(thread: str, judge=None) -> dict:
    """Drive one run, approving at the gate if it gets that far.

    It may not: a judge that rejects the diff sends the run back to the
    planner and it ends at the step guard with no gate to approve at. That
    is a legitimate outcome, so this checks for a pending interrupt rather
    than assuming one.
    """
    adapters.reset()
    app = build_graph(judge=judge)
    cfg = {"configurable": {"thread_id": thread}}
    out = app.invoke(
        new_state("ticket_opened", {"ticket": 4821, "pr": 318}, trace_id=thread), cfg
    )
    if app.get_state(cfg).next:
        out = app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
    return out


def scenario_gemma() -> None:
    head("gemma -- a real model judges, and the control plane does not notice")
    judge = gemma_judge.make_gemma_judge()
    print(f"  model        {judge.model} via {judge.base_url}")
    print("  loading      (first call pulls ~6.6 GB into memory; give it a minute)")
    try:
        gemma_judge.probe(model=judge.model, base_url=judge.base_url)
    except gemma_judge.OllamaUnavailable as exc:
        print(f"  skipped      {exc}")
        return
    print("  loaded       ok\n")

    try:
        offline = _run_approving("gemma-offline")
        live = _run_approving("gemma-live", judge=judge)
    except gemma_judge.OllamaUnavailable as exc:
        # Reachable at probe time, gone by the time a node asked. Worth a
        # clean message: a run that dies mid-graph is exactly the failure
        # the interrupt/checkpoint machinery exists to survive.
        print(f"\n  aborted      the model became unavailable mid-run: {exc}")
        return

    print("\n  with the model:")
    show(live)

    verdict = live.get("review_report", {})
    print(f"\n  severity     {offline['triage_report']['severity']!r} (default)"
          f"  ->  {live['triage_report']['severity']!r} (Gemma)")
    print(f"  approved     {verdict.get('approved')!r}")
    print(f"  comments     {verdict.get('comments')}")

    same_trail = offline.get("completed") == live.get("completed")
    print(f"\n  same trail?  {same_trail}", end="")
    if same_trail:
        print("        <- routing is code, not a prompt")
    else:
        # Not a failure. The reviewer is *allowed* to send a PR back; what
        # matters is that the route it took is one the table permits, chosen
        # by `router.route`, not by the model.
        print(f"\n               default: {' -> '.join(offline.get('completed', []))}")
        print(f"               Gemma:   {' -> '.join(live.get('completed', []))}")
        print("               Gemma rejected the diff, so the reviewer sent it")
        print("               back -- an edge the route table already has.")
    print(f"  same steps?  {offline.get('step_count')} vs {live.get('step_count')}")

    deployed = live.get("deploy_report", {}).get("deployed")
    if deployed is None:
        print("  deployed?    never reached the deployer")
    else:
        print(f"  deployed?    {deployed}         <- still only because a human said yes")

    print(f"\n  model calls  {judge.calls}")
    if judge.fallbacks:
        print(f"  rejected     {len(judge.fallbacks)} reply/replies failed validation:")
        for reason in judge.fallbacks:
            print(f"                 {reason}")
        print("               the step degraded to a default; the route did not move")
    else:
        print("  rejected     0   every reply matched the schema")


SCENARIOS = {
    "approve": scenario_approve,
    "reject": scenario_reject,
    "ignore": scenario_ignore,
    "rework": scenario_rework,
    "budget": scenario_budget,
    "gate": scenario_gate,
    "mask": scenario_mask,
    "residency": scenario_residency,
    "quota": scenario_quota,
    "gemma": scenario_gemma,
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
