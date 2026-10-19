"""One record per model call.

``completed`` says which nodes ran. That is not enough to answer the
questions asked after something goes wrong: which provider saw this, was
it masked first, how many tokens did it actually cost, why was that
provider chosen. Those are properties of a *call*, not of a node, so
they need their own ledger.

Two rules the ledger follows:

- **A failed call is still a call.** A response cut off by the budget
  writes a record with ``truncated=True``. A ledger that only records
  successes answers "what did we spend" wrongly and "what went wrong"
  not at all.
- **The estimate does not survive.** The budget guard has to decide
  before the provider reports usage, so it estimates. Once the real
  count arrives, :func:`settle` replaces it. An audit trail left holding
  an approximation invites someone to reconcile against it later and
  find it does not add up.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class CallRecord:
    """What one model call did.

    ``tokens_actual`` is ``None`` until :func:`settle` applies the
    provider's count, which makes "never settled" visible rather than
    indistinguishable from "settled at the estimate".

    ``refused`` is non-empty when no call was made -- no eligible
    provider, or no quota left. A refusal is recorded for the same
    reason a failure is: "nothing happened" and "we declined to let it
    happen" are different answers to the same question.

    ``provider`` is the provider the rules *selected*; ``provider_used``
    is what actually answered. They are two facts and the ledger keeps
    both, because an injected ``Judge`` is free to ignore the selection --
    and a record that reports the choice as though it were the outcome
    answers "who saw this data" with a guess. Empty ``provider_used``
    means the judge did not say, not that the two agree.
    """

    trace_id: str
    agent: str
    provider: str
    sensitivity: str
    route_reason: str
    tokens_estimated: int
    tokens_actual: int | None = None
    provider_used: str = ""
    masked: bool = False
    truncated: bool = False
    refused: str = ""

    @property
    def tokens_charged(self) -> int:
        """What this call actually cost, best known so far."""
        return self.tokens_estimated if self.tokens_actual is None else self.tokens_actual

    def as_dict(self) -> dict:
        """Plain dict, for storing in graph state."""
        return asdict(self)


def settle(record: CallRecord, provider_tokens: int) -> CallRecord:
    """Return *record* with the provider's real token count applied."""
    return replace(record, tokens_actual=provider_tokens)
