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

#: The judge every graph-building scenario uses. ``None`` means the
#: deterministic defaults in :mod:`agentcp.agents`. ``--gemma`` replaces it
#: with the real local model, which is the whole claim put to the test: the
#: control plane is supposed not to notice which one it got, so the way to
#: find out is to run all of it both ways and compare.
JUDGE = None


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
        # `provider` is what the rules selected; `provider_used` is what
        # answered. Print both when they differ -- an injected judge may
        # ignore the selection, and reporting the choice as the outcome
        # would make the ledger say something it does not know.
        #
        # `masked`/`unmasked` is printed for every call, not only the
        # masked ones, and borrows the record's own field name so the
        # line maps onto the `masked:` field a reader goes looking for.
        # A mark that appeared only when true would leave the other
        # calls ambiguous: silence would mean both "nothing in this
        # context needed masking" and "nobody checked".
        parts = []
        for c in calls:
            used = c.get("provider_used")
            mask = "masked" if c.get("masked") else "unmasked"
            part = f"{c['agent']}->{c['provider']} {mask}"
            if used and used != c["provider"]:
                part += f" but answered by {used}"
            parts.append(part)
        print(f"  model calls  {len(calls)}  ({', '.join(parts)})")
        settled = sum(1 for c in calls if c.get("tokens_actual") is not None)
        note = f"   ({settled}/{len(calls)} settled against the provider's count)"
        print(f"  tokens       {state.get('tokens_used')} / {state.get('budget_tokens')}{note}")


def pipeline(thread: str):
    adapters.reset()
    app = build_graph(judge=JUDGE)
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
    # The rejecting judge *is* this scenario: the loop only exists because
    # the reviewer keeps saying no. Under --gemma the real model decides
    # instead, and whether the loop happens at all becomes its answer --
    # which is the more honest demonstration, so it wins.
    app = build_graph(
        judge=JUDGE or (lambda prompt, ctx: {"approved": False, "comments": ["add tests"]})
    )
    cfg = {"configurable": {"thread_id": "rework"}}
    out = app.invoke(
        new_state("ticket_opened", {"ticket": 4821, "pr": 318},
                  max_steps=6, trace_id="rework"),
        cfg,
    )
    show(out)
    looped = out.get("completed", []).count("reviewer") > 1
    if looped:
        print()
        print("  the loop did not run forever; max_steps decided when to stop")
    else:
        # Under --gemma the real model approved, so there was no loop to
        # guard. Saying so is the point: this scenario demonstrates a guard
        # on a path the judgement chooses, and claiming the guard fired
        # when it did not is the kind of sentence this repo exists to stop
        # writing.
        print()
        print("  no loop this time -- the reviewer approved, so the run")
        print(f"  went to the gate and stopped at {out.get('step_count')} of"
              f" {out.get('max_steps')} steps. The step guard is still there;")
        print("  nothing asked it to fire.")


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

    # The guard above is the mechanism. What it does to a run is the part
    # worth showing: the budget refuses, and a refusal ends the run the
    # same way an exhausted quota does.
    print("\n  and in a run, at three budgets:")
    for budget in (6, 12, 2000):
        adapters.reset()
        app = build_graph(judge=JUDGE)
        cfg = {"configurable": {"thread_id": f"budget-{budget}"}}
        out = app.invoke(
            new_state("ticket_opened", {"ticket": 4821, "pr": 318},
                      budget_tokens=budget, trace_id=f"budget-{budget}"),
            cfg,
        )
        if app.get_state(cfg).next:
            out = app.invoke(Command(update={"human_decision": {"approve": True}}), cfg)
        stopped = next((c for c in out["calls"] if c["refused"]), None)
        trail = " -> ".join(out.get("completed", []))
        print(f"\n  budget {budget:<5} {trail}")
        if stopped:
            spent = stopped["tokens_estimated"]
            print(f"               {stopped['agent']} refused: {stopped['refused']}")
            print(f"               tokens generated on that call: {spent}"
                  f"   {'(the model was never called)' if spent == 0 else '(already spent)'}")
        print(f"               deployed? {out.get('deploy_report', {}).get('deployed', False)}")

    # Which of the two refusals a budget gets depends on what the calls
    # before it cost, so the reading is computed above rather than
    # asserted here. With the deterministic default, triage's reply is
    # ~6 tokens and a budget of 12 survives it, so the reviewer is
    # called and then cut off. With a real model the first call alone
    # is a few hundred tokens and both small budgets are gone before
    # the reviewer is reached.
    print()
    print("  a refusal before the call is the only one that saves money:")
    print("  the judge is not reached at all. A refusal after it buys")
    print("  correctness, not credit -- a one-shot model bills for the whole")
    print("  reply before anything can count it. Which of the two a given")
    print("  budget gets depends on what the calls before it cost, which is")
    print("  why the lines above print the tokens rather than describing them.")


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
    print("  the fourth row is the point: the only healthy provider was")
    print("  remote, and the answer was still no.")

    # Those four rows call `providers.choose` directly, which shows the
    # rules and nothing about whether a run can reach them. Every model
    # call in every other scenario is ("open", "low", all four healthy),
    # so the veto has never fired on a pipeline path -- and a rule no run
    # reaches is a rule the reader is taking on trust. So here it is at
    # the altitude it is claimed at: through the graph, into a node,
    # through `consult`, which is where the selection actually happens.
    #
    # Getting there means narrowing the health view, and the only way to
    # narrow it is to assign the module constant: `agents.HEALTHY` is
    # hardcoded and `build_graph` takes no health argument. That is a
    # real missing seam, not a shortcut taken for the example -- a
    # deployment with a live health view has nowhere to put it either.
    # Restored in the `finally`, because a scenario that leaves a module
    # global rewritten has broken every scenario that runs after it.
    print("\n  and the same veto on the path a run actually takes:")
    was_healthy = agents.HEALTHY
    agents.HEALTHY = frozenset({"cloud-small"})
    try:
        adapters.reset()
        app = build_graph(judge=JUDGE)
        cfg = {"configurable": {"thread_id": "residency-run"}}
        out = app.invoke(
            new_state("ticket_opened", {"ticket": 4821, "pr": 318},
                      sensitivity="restricted", trace_id="residency-run"),
            cfg,
        )
    finally:
        agents.HEALTHY = was_healthy

    show(out)
    print()
    print(f"  call records {out.get('calls')}")
    print("  triage asked for a judgement, selection refused before any")
    print("  model was reached, and the node reported severity 'unknown'")
    print("  instead of guessing one. The run ends there: no plan, no")
    print("  review, no deploy. `provider: 'none'` is the record of a")
    print("  call that was never placed -- the refusal is auditable, which")
    print("  is the difference between declining and silently coping.")


def scenario_quota() -> None:
    head("quota -- a tenant runs out; the run declines and says so")
    adapters.reset()
    agents.LEDGER = quota.Ledger()
    agents.LEDGER.charge("trial", quota.limit_for("trial"))
    print(f"  tenant       'trial', limit {quota.limit_for('trial')} tokens, already spent")

    app = build_graph(judge=JUDGE)
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
    judge = JUDGE if isinstance(JUDGE, gemma_judge.GemmaJudge) else gemma_judge.make_gemma_judge()
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

    est = sum(c["tokens_estimated"] for c in live.get("calls", []))
    act = sum(c["tokens_actual"] or 0 for c in live.get("calls", []))
    if act:
        print(f"\n  estimated    {est} tokens   <- the char heuristic, from the visible reply")
        print(f"  provider     {act} tokens   <- eval_count, which includes Gemma's")
        print(f"               hidden reasoning: {act / est:.0f}x the estimate.")
        print("               This is what settle() is for. A ledger left holding")
        print("               the estimate would under-report the bill by that much.")

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
    global JUDGE
    adapters.register_stubs()
    args = sys.argv[1:]
    if "--gemma" in args:
        args.remove("--gemma")
        gemma_judge.probe()
        JUDGE = gemma_judge.make_gemma_judge(verbose=False)
        print()
        print(f"  every judgement below is answered by {JUDGE.model}.")
        print("  `gate` and `mask` build no graph, so they are unchanged --")
        print("  said here rather than left for the reader to notice.")
    wanted = args or list(SCENARIOS)
    for name in wanted:
        if name not in SCENARIOS:
            raise SystemExit(f"unknown scenario {name!r}; pick from {list(SCENARIOS)}")
        SCENARIOS[name]()
    print()


if __name__ == "__main__":
    main()
