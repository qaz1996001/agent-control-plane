import pytest
from langgraph.checkpoint.memory import MemorySaver

from agentcp.graph import DurabilityNotConfigured, build_graph


def test_the_default_is_memory_and_compiles():
    assert build_graph() is not None


def test_requiring_durability_without_a_checkpointer_fails_loudly():
    """A silent fallback makes "unconfigured" and "memory" look alike."""
    with pytest.raises(DurabilityNotConfigured):
        build_graph(durability="require")


def test_passing_memorysaver_does_not_satisfy_the_requirement():
    """The question is whether a pause survives a restart, not whether
    the caller supplied an object."""
    with pytest.raises(DurabilityNotConfigured):
        build_graph(checkpointer=MemorySaver(), durability="require")


def test_the_refusal_names_what_is_missing():
    with pytest.raises(DurabilityNotConfigured) as exc:
        build_graph(durability="require")
    assert "MemorySaver" in str(exc.value)


def test_an_unknown_durability_mode_is_rejected_not_guessed():
    with pytest.raises(ValueError):
        build_graph(durability="maybe")


def test_a_durable_checkpointer_satisfies_the_requirement():
    class FakeDurableSaver(MemorySaver.__bases__[0]):
        """Stands in for a store that outlives the process."""

    assert build_graph(checkpointer=FakeDurableSaver(), durability="require") is not None
