"""Per-tenant token quota.

One tenant's runaway run must not spend another tenant's allowance, so
the counter is keyed by tenant rather than being global.

The exception carries ``retry_after``. An over-quota error that does not
say when to come back forces the caller to choose between hammering and
giving up, and callers reliably pick hammering.

Fixed window, in process. Stated plainly because it matters: two workers
each get their own allowance, so the real ceiling is the limit times the
worker count. Shared enforcement needs a shared counter, which needs a
store, which is out of scope here -- see ``docs/scope.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Tokens per window, per tenant.
DEFAULT_LIMIT = 10_000

#: Tenants with a limit other than the default.
LIMITS: dict[str, int] = {
    "trial": 500,
}

#: Seconds in one window; also what an over-quota caller should wait.
WINDOW_SECONDS = 60


class QuotaExceeded(RuntimeError):
    """The tenant has spent its allowance for this window."""

    def __init__(self, tenant: str, used: int, limit: int, retry_after: int) -> None:
        super().__init__(
            f"tenant {tenant!r} over quota: {used} > {limit} tokens; "
            f"retry after {retry_after}s"
        )
        self.tenant = tenant
        self.used = used
        self.limit = limit
        self.retry_after = retry_after


def limit_for(tenant: str) -> int:
    """Tokens this tenant may spend per window."""
    return LIMITS.get(tenant, DEFAULT_LIMIT)


@dataclass
class Ledger:
    """Tokens spent per tenant in the current window."""

    spent: dict[str, int] = field(default_factory=dict)

    def used(self, tenant: str) -> int:
        return self.spent.get(tenant, 0)

    def remaining(self, tenant: str) -> int:
        return max(0, limit_for(tenant) - self.used(tenant))

    def charge(self, tenant: str, tokens: int) -> int:
        """Charge *tokens* to *tenant*, or raise.

        Charges before raising is deliberate: the tokens were spent, and
        a ledger that forgets the spend that broke the limit understates
        exactly the usage worth seeing.
        """
        total = self.used(tenant) + tokens
        self.spent[tenant] = total
        limit = limit_for(tenant)
        if total > limit:
            raise QuotaExceeded(tenant, total, limit, WINDOW_SECONDS)
        return total

    def reset(self, tenant: str | None = None) -> None:
        """Start a new window, for one tenant or all of them."""
        if tenant is None:
            self.spent.clear()
        else:
            self.spent.pop(tenant, None)
