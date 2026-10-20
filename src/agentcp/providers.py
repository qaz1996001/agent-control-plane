"""Which model gets the call -- a second table, on three axes.

``router.py`` decides *which agent* runs. This decides *which provider*
the agent's judgement call is allowed to reach. They are separate tables
because they answer to different pressures: the route changes when the
workflow changes, the provider changes when a contract, a price or a
data-residency rule changes.

The three axes are not peers:

- **Sensitivity is a veto.** Restricted content may not leave the local
  deployment. If the only healthy provider is remote, the answer is "no
  provider", not "well, just this once". A veto that bends under load is
  a preference.
- **Cost is a preference.** Cheap model for low-complexity work, capable
  model for the rest. Being wrong here costs money or quality, not a
  disclosure.
- **Health is a fallback.** Unhealthy providers are skipped. Failing over
  may cross the cost preference; it may never cross the veto.

Simplified from the real thing: health here is a set of names the caller
believes are up. A production version tracks failures per provider and
half-opens after a cooldown. The simplification is in the health input,
not in the ordering rules -- those are the part worth showing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Sensitivity = Literal["open", "restricted"]
Complexity = Literal["low", "high"]


class NoEligibleProvider(RuntimeError):
    """Nothing satisfies the constraints. Deliberately not a fallback."""


@dataclass(frozen=True)
class Provider:
    """One place a model call can go.

    Attributes
    ----------
    name : str
        Appears in the audit record.
    local : bool
        True if calling it keeps the data inside the deployment.
    cost_tier : int
        1 is small and cheap, 2 is large and expensive.
    """

    name: str
    local: bool
    cost_tier: int


#: Preference order within a tier. First healthy match wins.
PROVIDERS: tuple[Provider, ...] = (
    Provider("local-small", local=True, cost_tier=1),
    Provider("local-large", local=True, cost_tier=2),
    Provider("cloud-small", local=False, cost_tier=1),
    Provider("cloud-large", local=False, cost_tier=2),
)

#: Every provider, assumed up. Callers pass their own health view.
ALL_HEALTHY: frozenset[str] = frozenset(p.name for p in PROVIDERS)


@dataclass(frozen=True)
class Choice:
    """The selected provider and the one-line reason it was selected."""

    provider: Provider
    reason: str


def choose(
    sensitivity: Sensitivity = "open",
    complexity: Complexity = "low",
    healthy: Iterable[str] = ALL_HEALTHY,
) -> Choice:
    """Pick a provider, or refuse.

    Order of operations is the whole policy: veto, then preference, then
    fallback. Written as three separate filters so that reading the
    function tells you which one rejected a provider.
    """
    up = frozenset(healthy)
    eligible = [p for p in PROVIDERS if p.name in up]

    if sensitivity == "restricted":
        eligible = [p for p in eligible if p.local]
        if not eligible:
            raise NoEligibleProvider(
                "restricted content and no healthy local provider; "
                "refusing rather than sending it off-site"
            )

    if not eligible:
        raise NoEligibleProvider("no healthy provider")

    want = 1 if complexity == "low" else 2
    preferred = [p for p in eligible if p.cost_tier == want]
    if preferred:
        return Choice(preferred[0], f"{sensitivity}/{complexity}: preferred tier {want}")

    # Falling back across the cost preference is allowed. Note that the
    # veto has already been applied, so this cannot reach a remote
    # provider for restricted content.
    return Choice(
        eligible[0],
        f"{sensitivity}/{complexity}: tier {want} unavailable, fell back",
    )
