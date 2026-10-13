"""The minimum rest a roster demands between two shifts of one worker."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from shift_planner import (
    Horizon,
    InsufficientRestError,
    OverlappingShiftError,
    Plan,
    Roster,
    Shift,
    ShiftPattern,
)

EIGHT = timedelta(hours=8)
EVENING = datetime(2026, 5, 4, 16, tzinfo=timezone.utc)
SEVEN = datetime(2026, 5, 5, 7, tzinfo=timezone.utc)
EIGHT_AM = datetime(2026, 5, 5, 8, tzinfo=timezone.utc)


def make_shift(worker="anna", start=EVENING, length=EIGHT, location="depot-north") -> Shift:
    return Shift(worker=worker, location=location, start=start, length=length)


def test_eight_hours_of_rest_refuse_an_early_start_after_a_night_shift():
    night = make_shift()
    early = make_shift(start=SEVEN, length=timedelta(hours=4))

    with pytest.raises(InsufficientRestError) as caught:
        Roster([night, early], rest=EIGHT)

    assert caught.value.first == night
    assert caught.value.second == early
    assert caught.value.rest == EIGHT
    assert "anna" in str(caught.value)


def test_the_same_pair_an_hour_later_rests_long_enough():
    night = make_shift()
    late_enough = make_shift(start=EIGHT_AM, length=timedelta(hours=4))
    assert len(Roster([night, late_enough], rest=EIGHT)) == 2


def test_without_rest_the_early_start_is_fine():
    night = make_shift()
    early = make_shift(start=SEVEN, length=timedelta(hours=4))
    assert len(Roster([night, early])) == 2


def test_touching_shifts_are_legal_only_at_zero_rest():
    first = make_shift()
    second = make_shift(start=first.end)

    assert len(Roster([first, second])) == 2
    with pytest.raises(InsufficientRestError):
        Roster([first, second], rest=timedelta(minutes=1))


def test_an_overlap_is_the_zero_rest_case_of_the_same_rule():
    first = make_shift()
    clashing = make_shift(start=EVENING + timedelta(hours=4))

    with pytest.raises(OverlappingShiftError) as caught:
        Roster([first, clashing], rest=EIGHT)

    assert isinstance(caught.value, InsufficientRestError)
    assert "overlapping" in str(caught.value)


def test_rest_is_counted_per_worker():
    night = make_shift()
    other = make_shift(worker="boris", start=SEVEN, length=timedelta(hours=4))
    assert len(Roster([night, other], rest=EIGHT)) == 2


def test_add_and_extend_keep_the_rest_rule():
    roster = Roster([make_shift()], rest=EIGHT)
    early = make_shift(start=SEVEN, length=timedelta(hours=4))

    with pytest.raises(InsufficientRestError):
        roster.add(early)
    with pytest.raises(InsufficientRestError):
        roster.extend([early])

    grown = roster.add(make_shift(start=EIGHT_AM, length=timedelta(hours=4)))
    assert grown.rest == EIGHT
    assert len(roster) == 1


def test_roster_rejects_a_negative_rest():
    with pytest.raises(ValueError):
        Roster([make_shift()], rest=timedelta(hours=-1))


def test_a_plan_hands_its_rest_to_the_roster_it_draws():
    plan = Plan(
        horizon=Horizon(date(2026, 5, 4), days=2),
        patterns=[
            ShiftPattern("anna", "depot-north", time(8), timedelta(hours=8), weekdays={0, 1})
        ],
        rest=EIGHT,
    )

    roster = plan.roster()
    assert roster.rest == EIGHT
    assert len(roster) == 2
    assert plan.applied_to(roster) == roster


def test_a_plan_that_leaves_too_little_rest_refuses_to_draw():
    plan = Plan(
        horizon=Horizon(date(2026, 5, 4), days=2),
        patterns=[
            ShiftPattern("anna", "depot-north", time(16), timedelta(hours=8), weekdays={0}),
            ShiftPattern("anna", "depot-north", time(7), timedelta(hours=4), weekdays={1}),
        ],
        rest=EIGHT,
    )

    assert len(Plan(plan.horizon, plan.patterns).roster()) == 2
    with pytest.raises(InsufficientRestError):
        plan.roster()
