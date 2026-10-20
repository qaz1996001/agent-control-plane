*English ｜ [繁體中文](design.zh-TW.md)*

# Design notes

Four diagrams for four claims: routing is a table, permission is a
check, masking is one mechanism with three endpoints, and sensitivity
is a veto rather than a weight.

---

## 1. The control plane is a table, and approval is a real stop

`route()` picks the entry node from `trigger`. After every node,
`next_node()` applies a fixed precedence — the step guard first, then a
pending approval, then an explicit hand-off. The guard is first so that a
cycle cannot out-vote it.

```mermaid
flowchart TD
    T(["trigger"]) --> R{"ROUTE_TABLE<br/>lookup"}
    R -->|unknown| X["UnknownTrigger<br/>raised, no default"]
    R -->|document_submitted| A["triage"]
    R -->|index_ready| B["indexer"]
    R -->|assessment_requested| C["assessor"]
    R -->|assessment_passed| D["publisher"]

    A --> N{"next_node"}
    B --> N
    C --> N
    D --> N

    N -->|"step_count >= max_steps"| E1(["END — guard wins"])
    N -->|"requires_approval"| G["approval_gate"]
    N -->|"next_agent set"| L["that agent"]
    N -->|"nothing pending"| E2(["END"])

    G -.->|"interrupt_before:<br/>run stops and is checkpointed"| H(["waiting for a human"])
    H -->|"resume with approve=True"| D
    H -->|"resume with approve=False<br/>or with nothing"| D
    D -.->|"no approval on record"| E3(["END — the publisher refused"])

    style X fill:#fce8e6,stroke:#a50e0e
    style H fill:#fff7ed,stroke:#f97316
    style E3 fill:#fce8e6,stroke:#a50e0e
    style G fill:#eff6ff,stroke:#3b82f6
```

The dashed edge is the only place the system waits for a person, and it is
enforced by the runtime rather than by a node remembering to check.

Both resume paths run the publisher; the refusal lives *inside* it. That is
why "resume with nothing" cannot publish — there is no separate decline
branch to get wrong — and it is also why `approval_gate` decides nothing:
it does not read `human_decision` at all, it clears the pending flag and
returns. A rejection is declined by the publisher, not at the gate.

**Precedence matters, and is tested:** `test_step_budget_outranks_a_pending_handoff`
sets `next_agent` *and* `requires_approval` on an over-budget state and
asserts the run still ends.

---

## 2. Permission is checked at the call, and would be advertised from the same table

A prompt saying "do not publish" is a request. `ACCESS` is a check.
`allowed()` is the single source for both readings of that table —
`invoke` checks it, `schemas_for` renders it — so a tool cannot be
advertised to an agent that is forbidden to run it. No node here lets a
model pick a tool, so the rendering is the seam a tool-calling loop would
attach to; pinning the agreement before anything depends on it is the
cheap half of that work, and the only half that transfers.

```mermaid
flowchart LR
    subgraph reg["REGISTRY — every tool"]
        direction TB
        T1["read_document"]
        T2["write_index"]
        T3["read_draft"]
        T4["publish"]
    end

    subgraph acc["ACCESS — agent to allow-list"]
        direction TB
        P1["triage → read_document, tag_document"]
        P2["indexer → read_document, write_index"]
        P3["assessor → read_draft, post_finding"]
        P4["publisher → read_index, publish"]
    end

    reg --> S["schemas_for(agent)"]
    acc --> S
    acc --> I["invoke(agent, name, args)"]

    S --> M["what a model would be offered<br/>(no node offers them yet)"]
    I --> K{"on the allow-list?"}
    K -->|no| DEN["AccessDenied"]
    K -->|yes| RUN["tool runs"]
    RUN -->|raises| ERR["{'error': ...}<br/>never raises into the graph"]
    RUN -->|returns| OK["result"]

    style DEN fill:#fce8e6,stroke:#a50e0e
    style ERR fill:#fff7ed,stroke:#f97316
    style OK fill:#e6f4ea,stroke:#1e7e34
```

`test_schemas_offered_match_the_allow_list` asserts the two outputs of that
shared table agree, for every agent. Without it, the offer and the check
drift the first time someone adds a tool.

---

## 3. Masking, restoring and the permission are one mechanism

The model is shown `<EMAIL_1>`. The person reading the answer needs the
real address back, or the answer is not actionable. So the value has to
return for *someone*, which makes the question "who", which means there
has to be a check — and the check belongs next to the mapping, not in
whatever layer happens to render the response.

Split these three across a gateway, a view and a template and nothing
can assert that a value masked on the way out is restorable only to
someone entitled to it. That is how the guarantee is lost.

```mermaid
flowchart LR
    C["context<br/>real values"] --> M["privacy.mask"]
    M --> P["&lt;EMAIL_1&gt; &lt;HOST_1&gt;"]
    M -.-> MAP[["Mapping<br/>bound to trace_id"]]
    P --> J["the Judge<br/>sees only this"]
    J --> R["the verdict<br/>the model's own words"]

    R -.->|"no run takes this edge"| RS{"privacy.restore"}
    MAP -.-> RS
    RS -->|"viewer.may_unmask"| OK["real values back"]
    RS -->|"no permission"| D1["RestoreDenied<br/>nothing restored"]
    RS -->|"mapping from another run"| D2["TraceMismatch"]

    MAP -.->|"never written"| ST["graph state<br/>(checkpointed)"]

    style D1 fill:#fce8e6,stroke:#a50e0e
    style D2 fill:#fce8e6,stroke:#a50e0e
    style OK fill:#e6f4ea,stroke:#1e7e34
    style RS fill:#eff6ff,stroke:#3b82f6
    style ST fill:#fff7ed,stroke:#f97316
```

Two refusals rather than one best effort. A partial restore is the worst
available outcome: it still leaks, and it reads as though nothing was
withheld. `test_restore_refuses_outright_rather_than_restoring_part`
pins that.

The dotted edge into `restore` is the honest part of the diagram. A
pipeline run masks and never restores: `mask` covers the context sent to
the judge, the verdict comes back in the model's own words, and
`Consultation.mapping` is returned in process and dropped — which
[`scope.md`](scope.md) has always said. `restore` is reached by
`test_privacy.py` and by the `mask` scenario calling it directly. The
argument for keeping the three endpoints together does not need a run that
exercises all three; it is an argument about where the check belongs *if*
the value comes back. But the diagram should not imply a path no run
takes. See [`errata.md`](errata.md), entry C2.

The dotted edge to state is the one that is *not* there. State gets
checkpointed; a checkpoint holding the mapping would undo the masking at
rest, so the mapping stays in process and
`test_the_unmasking_map_never_reaches_checkpointed_state` asserts it.

---

## 4. Sensitivity is a veto; cost is a preference

Three axes decide which provider sees a call, and they are not peers.
Order of application is the entire policy, which is why `choose` is
written as three filters in sequence rather than a score.

```mermaid
flowchart TD
    S(["call needs a provider"]) --> H["drop unhealthy"]
    H --> V{"restricted?"}
    V -->|no| CO["all remaining eligible"]
    V -->|yes| LO["keep local only"]
    LO --> E{"any left?"}
    E -->|no| X["NoEligibleProvider<br/>refuse, do not send off-site"]
    E -->|yes| CO

    CO --> T{"preferred cost tier<br/>available?"}
    T -->|yes| P1["use it"]
    T -->|no| P2["fall back across tiers<br/>— never across the veto"]

    style X fill:#fce8e6,stroke:#a50e0e
    style V fill:#eff6ff,stroke:#3b82f6
    style P2 fill:#fff7ed,stroke:#f97316
    style P1 fill:#e6f4ea,stroke:#1e7e34
```

The branch worth reading is `E -->|no| X`. When the only healthy
provider is remote and the content is restricted, the answer is "no
provider", not "just this once". A veto that bends under load is a
preference with better marketing —
`test_failover_may_not_cross_the_locality_veto` is the test that keeps
it one.

Every `Choice` also carries the reason it was made, which is what the
audit record stores. "Which provider" without "why that provider" is
not answerable after the fact once the health picture has changed.

---

## 5. Where each claim is tested

| Claim | Test |
|---|---|
| Same trigger always routes the same way | `test_same_trigger_always_routes_to_same_agent` |
| The trigger type and the route table cannot drift | `test_every_trigger_in_the_type_has_a_route` |
| An unknown trigger raises rather than defaulting | `test_unknown_trigger_raises_instead_of_defaulting` |
| A judge cannot move the route | `test_a_judge_that_returns_control_fields_does_not_get_control`, `test_the_judge_is_consulted_twice_and_the_route_does_not_depend_on_it` |
| The step guard beats a hand-off and an approval | `test_step_budget_outranks_a_pending_handoff` |
| The run genuinely pauses at the gate | `test_run_actually_stops_at_the_gate` |
| Absence of a decision is not consent | `test_resuming_with_no_decision_still_refuses_to_deploy` |
| The assessor does not write `human_decision` | `test_the_reviewer_cannot_approve_on_the_humans_behalf` |
| Offered schemas equal the allow-list | `test_schemas_offered_match_the_allow_list` |
| A raising tool returns an error object instead of raising | `test_a_raising_tool_degrades_instead_of_crashing` |
| The budget bites mid-stream | `test_stream_is_cut_mid_way_not_after_the_fact` |
| The real count replaces the estimate | `test_real_usage_overwrites_the_estimate` |
| A diagnostic metric never gates | `test_the_diagnostic_metric_never_blocks_however_bad` |
| Both metric directions share one comparison | `test_both_directions_report_negative_z_when_worse` |
| A short window is not "ok" | `test_short_window_is_insufficient_data_not_ok` |
| The masked text leaks nothing, checked whole | `test_masked_text_contains_no_real_value_anywhere` |
| Restoring refuses rather than restoring part | `test_restore_refuses_outright_rather_than_restoring_part` |
| One run's mapping cannot resolve another's | `test_a_mapping_from_another_run_cannot_resolve_this_one` |
| The judge only ever sees masked text | `test_the_judge_only_ever_sees_masked_text` |
| The unmasking map never reaches state | `test_the_unmasking_map_never_reaches_checkpointed_state` |
| Restricted content never reaches a remote provider | `test_restricted_content_never_reaches_a_remote_provider` |
| Failover crosses cost but not locality | `test_failover_may_not_cross_the_locality_veto` |
| Every model call goes through one door | `test_only_consult_contains_a_call_to_the_injected_judge` |
| A refused call still leaves a record | `test_a_refused_call_still_leaves_a_record` |
| The run's token counter is actually charged | `test_the_run_token_counter_is_actually_charged` |
| A tenant rule narrows, never grants | `test_a_tenant_rule_can_only_subtract_never_grant` |
| Schemas match the allow-list per agent *and* tenant | `test_schemas_match_the_allow_list_for_every_agent_and_tenant` |
| One tenant's exhaustion does not touch another | `test_one_tenant_running_out_does_not_touch_another` |
| An over-quota error says when to retry | `test_the_error_says_when_to_come_back` |
| Raising a bar does not rewrite old verdicts | `test_raising_the_bar_later_does_not_rewrite_an_earlier_verdict` |
| Required durability refuses MemorySaver | `test_passing_memorysaver_does_not_satisfy_the_requirement` |
