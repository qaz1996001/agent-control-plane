import pytest

from agentcp import providers


def test_low_complexity_prefers_the_cheap_tier():
    assert providers.choose("open", "low").provider.name == "local-small"


def test_high_complexity_prefers_the_capable_tier():
    assert providers.choose("open", "high").provider.name == "local-large"


def test_restricted_content_never_reaches_a_remote_provider():
    """The veto applies even when every local provider is down."""
    with pytest.raises(providers.NoEligibleProvider):
        providers.choose("restricted", "low", healthy={"cloud-small", "cloud-large"})


def test_the_refusal_says_why_rather_than_just_failing():
    with pytest.raises(providers.NoEligibleProvider) as exc:
        providers.choose("restricted", "low", healthy={"cloud-large"})
    assert "off-site" in str(exc.value)


def test_restricted_content_still_gets_a_local_provider():
    choice = providers.choose("restricted", "high", healthy={"local-large", "cloud-large"})
    assert choice.provider.local is True
    assert choice.provider.name == "local-large"


def test_failover_may_cross_the_cost_preference():
    """Cost is a preference, so losing the preferred tier degrades."""
    choice = providers.choose("open", "low", healthy={"local-large"})
    assert choice.provider.name == "local-large"
    assert "fell back" in choice.reason


def test_failover_may_not_cross_the_locality_veto():
    """Same degraded situation, restricted content: refuse instead."""
    with pytest.raises(providers.NoEligibleProvider):
        providers.choose("restricted", "low", healthy={"cloud-small"})


def test_no_healthy_provider_at_all_refuses():
    with pytest.raises(providers.NoEligibleProvider):
        providers.choose("open", "low", healthy=set())


def test_every_choice_carries_a_reason_for_the_audit_record():
    for sensitivity in ("open", "restricted"):
        for complexity in ("low", "high"):
            assert providers.choose(sensitivity, complexity).reason
