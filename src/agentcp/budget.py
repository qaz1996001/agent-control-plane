"""Output-token budget, enforced while the stream is still running.

Checking usage after a response completes tells you what you already spent.
The check has to happen per chunk, which means estimating before the
provider's real count arrives -- and then correcting the audit record when
it does, so the ledger is accurate even though the guard was approximate.
"""

from __future__ import annotations

#: Rough chars-per-token used only until the provider reports real usage.
CHARS_PER_TOKEN = 4


class BudgetExceeded(RuntimeError):
    """Raised mid-stream when the output budget is crossed.

    Carries the counts so the caller can emit a terminal error frame and
    release any rate-limit slot it holds.
    """

    def __init__(self, used: int, budget: int) -> None:
        super().__init__(f"output budget exceeded: {used} > {budget} tokens")
        self.used = used
        self.budget = budget


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


class BudgetedStream:
    """Wrap a chunk iterator and stop it the moment the budget is crossed.

    Parameters
    ----------
    chunks : iterable of str
        The provider's output stream.
    budget : int
        Maximum output tokens for this call.

    Attributes
    ----------
    used : int
        Running estimate, replaced by the real count via :meth:`settle`.
    settled : bool
        True once the provider's authoritative usage has been applied.
    """

    def __init__(self, chunks, budget: int) -> None:
        self._chunks = iter(chunks)
        self.budget = budget
        self.used = 0
        self.settled = False
        self.emitted: list[str] = []

    def __iter__(self):
        for chunk in self._chunks:
            self.used += estimate_tokens(chunk)
            if self.used > self.budget:
                raise BudgetExceeded(self.used, self.budget)
            self.emitted.append(chunk)
            yield chunk

    def settle(self, provider_tokens: int) -> int:
        """Replace the estimate with the provider's real count.

        The guard runs on an estimate because it has to decide before the
        truth is available; the audit log should not inherit that error.
        """
        self.used = provider_tokens
        self.settled = True
        return self.used
