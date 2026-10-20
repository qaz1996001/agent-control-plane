"""Where the real world gets wired in.

Every tool here is a stub that records the call it *would* make. That is the
point of the file: it marks each integration seam explicitly, so swapping
a stub for a real client is a one-function change and you can see exactly
how many of them there are.

In a real deployment:

====================  =============================================
stub                  what replaces it
====================  =============================================
read_document           Jira / Linear REST client
tag_document          Jira / Linear REST client
read_draft             GitHub / GitLab compare API
post_finding          GitHub review-comment API
write_index            your own store (a table, a wiki page)
read_index             the same store
publish                CI trigger (Actions dispatch, Argo, Jenkins)
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
        ("read_document", "Jira/Linear: fetch issue",
         {"id": 4821, "title": "Calibration procedure, revision C", "submitter": "support"}),
        ("tag_document", "Jira/Linear: set labels",
         {"tagged": ["procedure", "calibration"]}),
        ("write_index", "Store: persist the plan",
         {"chunks": ["split by section", "strip boilerplate", "attach source refs"]}),
        # The author address and the build host are here so that masking is
        # exercised by a real run, not only by the `mask` scenario calling
        # privacy.mask directly. The draft is the right fixture to carry
        # them: assessor_node puts only the *verdict* into state, so these
        # values reach the model's context and never reach a checkpoint.
        # (triage_report, by contrast, stores the whole document, so PII in
        # the document fixture would be written into checkpointed state.)
        ("read_draft", "GitHub: compare base..head",
         {"draft": 318, "sections": 2, "added": 34, "removed": 6,
          "author": "sam.okafor@example.com", "built_on": "ci-runner-4.internal"}),
        ("post_finding", "GitHub: create review comment",
         {"filed": True}),
        ("read_index", "Store: load the plan",
         {"chunks": ["split by section", "strip boilerplate", "attach source refs"]}),
        ("publish", "CI: dispatch publish workflow",
         {"index": "corpus-live", "revision": 99214, "tier": "published"}),
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
