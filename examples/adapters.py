"""Where the real world gets wired in.

Every tool here is a stub that prints what it *would* call. That is the
point of the file: it marks each integration seam explicitly, so swapping
a stub for a real client is a one-function change and you can see exactly
how many of them there are.

In a real deployment:

====================  =============================================
stub                  what replaces it
====================  =============================================
read_ticket           Jira / Linear REST client
label_ticket          Jira / Linear REST client
read_diff             GitHub / GitLab compare API
post_comment          GitHub review-comment API
write_plan            your own store (a table, a wiki page)
read_plan             the same store
deploy                CI trigger (Actions dispatch, Argo, Jenkins)
====================  =============================================

None of them get credentials from this file. A real adapter reads them
from the environment or a secret manager; the registry neither knows nor
cares.
"""

from __future__ import annotations

from agentcp import tools

CALLS: list[tuple[str, dict]] = []


def _stub(name: str, result: dict):
    """Build a tool that records the call and returns a canned result."""

    def fn(args: dict) -> dict:
        CALLS.append((name, args))
        return dict(result)

    return fn


def register_stubs() -> None:
    """Register one stub per integration seam."""
    seams = [
        ("read_ticket", "Jira/Linear: fetch issue",
         {"id": 4821, "title": "Login returns 500 on submit", "reporter": "support"}),
        ("label_ticket", "Jira/Linear: set labels",
         {"labelled": ["bug", "auth"]}),
        ("write_plan", "Store: persist the plan",
         {"steps": ["reproduce locally", "fix null session", "add regression test"]}),
        # The author address and the build host are here so that masking is
        # exercised by a real run, not only by the `mask` scenario calling
        # privacy.mask directly. The diff is the right fixture to carry
        # them: reviewer_node puts only the *verdict* into state, so these
        # values reach the model's context and never reach a checkpoint.
        # (triage_report, by contrast, stores the whole ticket, so PII in
        # the ticket fixture would be written into checkpointed state.)
        ("read_diff", "GitHub: compare base..head",
         {"pr": 318, "files": 2, "additions": 34, "deletions": 6,
          "author": "sam.okafor@example.com", "built_on": "ci-runner-4.internal"}),
        ("post_comment", "GitHub: create review comment",
         {"posted": True}),
        ("read_plan", "Store: load the plan",
         {"steps": ["reproduce locally", "fix null session", "add regression test"]}),
        ("deploy", "CI: dispatch deploy workflow",
         {"workflow": "deploy.yml", "run_id": 99214, "env": "production"}),
    ]
    for name, desc, result in seams:
        tools.register(
            tools.Tool(
                name=name,
                description=desc,
                parameters={"type": "object", "additionalProperties": True},
                fn=_stub(name, result),
            )
        )


def reset() -> None:
    CALLS.clear()
