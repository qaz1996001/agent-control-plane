import pytest

from agentcp import privacy

TEXT = (
    "reporter sam.okafor@example.com says db-prod-3.internal returns 500; "
    "@rhea-ops confirmed, mail sam.okafor@example.com again"
)


def test_masked_text_contains_no_real_value_anywhere():
    """Asserted over the whole output, not the positions we substituted."""
    masked, mapping = privacy.mask(TEXT, "t-1")
    assert privacy.leaks(masked, mapping) == []


def test_the_same_value_gets_the_same_placeholder():
    masked, _ = privacy.mask(TEXT, "t-1")
    assert masked.count("<EMAIL_1>") == 2
    assert "<EMAIL_2>" not in masked


def test_each_kind_is_numbered_separately():
    masked, _ = privacy.mask(TEXT, "t-1")
    assert "<EMAIL_1>" in masked
    assert "<HOST_1>" in masked
    assert "<USER_1>" in masked


def test_an_address_is_not_eaten_by_the_handle_pattern():
    masked, _ = privacy.mask("write to sam.okafor@example.com", "t-1")
    assert masked == "write to <EMAIL_1>"
    assert "USER" not in masked


def test_restore_round_trips_for_an_entitled_viewer():
    masked, mapping = privacy.mask(TEXT, "t-1")
    back = privacy.restore(
        masked, mapping, trace_id="t-1", viewer=privacy.Viewer("ops", may_unmask=True)
    )
    assert back == TEXT


def test_restore_refuses_outright_rather_than_restoring_part():
    """No partial restore: it would still leak and would read as complete."""
    masked, mapping = privacy.mask(TEXT, "t-1")
    with pytest.raises(privacy.RestoreDenied):
        privacy.restore(
            masked, mapping, trace_id="t-1", viewer=privacy.Viewer("anon")
        )


def test_a_mapping_from_another_run_cannot_resolve_this_one():
    _, mapping = privacy.mask(TEXT, "t-1")
    with pytest.raises(privacy.TraceMismatch):
        privacy.restore(
            "<EMAIL_1>", mapping, trace_id="t-2",
            viewer=privacy.Viewer("ops", may_unmask=True),
        )


def test_a_placeholder_the_model_invented_stays_literal():
    """Restoring resolves what was masked, not what looks like a mask."""
    masked, mapping = privacy.mask("contact sam.okafor@example.com", "t-1")
    text = masked + " and <EMAIL_9>"
    back = privacy.restore(
        text, mapping, trace_id="t-1", viewer=privacy.Viewer("ops", may_unmask=True)
    )
    assert back.endswith("and <EMAIL_9>")


def test_text_with_nothing_to_mask_yields_an_empty_mapping():
    masked, mapping = privacy.mask("no entities here", "t-1")
    assert masked == "no entities here"
    assert not mapping
