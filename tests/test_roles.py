"""Tests for scope of practice: who may do what, and where."""

import pytest

from app.roles import (
    CATALOGUES,
    DEFAULT_TASK_PROFILE,
    UK,
    Role,
    RoleCatalogue,
    Task,
    catalogue,
    from_regulator,
    task_demand,
)


# --- the task profile -------------------------------------------------------

def test_task_profile_is_a_complete_distribution():
    assert sum(DEFAULT_TASK_PROFILE.values()) == pytest.approx(1.0)
    assert set(DEFAULT_TASK_PROFILE) == set(Task)


def test_task_demand_splits_hours_without_losing_any():
    split = task_demand(250.0)
    assert sum(split.values()) == pytest.approx(250.0)


def test_a_profile_that_does_not_sum_to_one_is_rejected():
    with pytest.raises(ValueError, match="must sum to 1"):
        task_demand(250.0, {Task.MEDICATION: 0.5})


# --- scope of practice ------------------------------------------------------

def test_an_assistant_cannot_give_medication():
    """The defect this module exists to fix. Counting every care hour alike let
    the solver buy a cheap, assistant-heavy plan that could not be delivered."""
    assert not UK["hca"].can_cover(Task.MEDICATION)
    assert not UK["porter"].can_cover(Task.MEDICATION)
    assert UK["sn"].can_cover(Task.MEDICATION)


def test_only_a_registered_nurse_may_lead_clinical_assessment():
    assert UK.leading(Task.CLINICAL_ASSESSMENT) == ("sn",)


def test_a_nursing_associate_may_assist_with_medication_but_not_lead_it():
    assert UK["pn"].can_cover(Task.MEDICATION)
    assert not UK["pn"].can_lead(Task.MEDICATION)


def test_a_porter_can_take_the_second_pair_of_hands():
    """Repositioning and transfers are commonly two-person tasks. Those hours
    are real, and currently get charged to an HCA who is then not elsewhere."""
    assert UK["porter"].can_cover(Task.REPOSITIONING)
    assert not UK["porter"].can_lead(Task.REPOSITIONING)
    assert UK["porter"].can_lead(Task.ESCORT_TRANSPORT)


def test_every_task_has_someone_who_may_lead_it_in_the_uk():
    for task in Task:
        assert not UK.unstaffable(task), f"nobody may lead {task.value}"


def test_unregulated_roles_are_marked_as_such():
    assert UK["sn"].regulated and UK["pn"].regulated
    assert not UK["hca"].regulated and not UK["porter"].regulated


# --- jurisdictions ----------------------------------------------------------

def test_non_uk_catalogues_are_empty_stubs_not_uk_copies():
    """Silently planning a Spanish or Emirati ward with British grades would be
    worse than refusing to plan it."""
    for code in ("ES", "US", "CA", "AE", "SA"):
        assert CATALOGUES[code].roles == {}, f"{code} quietly inherited UK roles"
        assert CATALOGUES[code].notes, f"{code} stub carries no explanation"


def test_no_catalogue_claims_to_be_verified():
    """Including the UK one — it is a considered reading, not a citation-backed
    extract, and must not present itself as more than that."""
    for code, cat in CATALOGUES.items():
        assert not cat.verified, f"{code} marked verified without a human check"


def test_an_unknown_jurisdiction_fails_loudly():
    with pytest.raises(KeyError, match="no role catalogue"):
        catalogue("ZZ")


def test_catalogue_defaults_to_the_uk():
    assert catalogue().jurisdiction == "UK"


def test_the_regulator_import_is_declared_not_faked():
    """A stub that raises is honest; one that returns plausible defaults is not."""
    with pytest.raises(NotImplementedError, match="regulator"):
        from_regulator("AE")


# --- catalogue mechanics ----------------------------------------------------

def test_covering_includes_assistants_and_leading_does_not():
    assert set(UK.covering(Task.REPOSITIONING)) > set(UK.leading(Task.REPOSITIONING))


def test_a_task_nobody_can_lead_is_reported_as_unstaffable():
    lonely = RoleCatalogue(
        jurisdiction="TEST",
        roles={"porter": Role("porter", "Porter", performs=frozenset(),
                              assists=frozenset({Task.REPOSITIONING}))},
    )
    assert lonely.unstaffable(Task.REPOSITIONING)
    assert lonely.unstaffable(Task.MEDICATION)
