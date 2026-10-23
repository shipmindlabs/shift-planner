"""What a plan's limits cap: a count of shifts or a sum of hours."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from shift_planner import Horizon, Plan, ShiftPattern

# Monday 2026-05-04 through Sunday 2026-05-10.
HORIZON = Horizon(date(2026, 5, 4), days=7)
WEEKDAYS = {0, 1, 2, 3, 4}
FORTY = timedelta(hours=40)


def plan_for(length: timedelta, limit=None, worker: str = "anna") -> Plan:
    pattern = ShiftPattern(worker, "depot-north", time(8), length, weekdays=WEEKDAYS)
    return Plan(
        horizon=HORIZON,
        patterns=[pattern],
        limits={} if limit is None else {worker: limit},
    )


def test_a_forty_hour_cap_keeps_five_eight_hour_days():
    roster = plan_for(timedelta(hours=8), FORTY).roster()

    assert len(roster) == 5
    assert sum((shift.length for shift in roster), timedelta(0)) == FORTY


def test_the_same_cap_stops_ten_hour_days_after_four():
    roster = plan_for(timedelta(hours=10), FORTY).roster()

    assert [shift.start.date() for shift in roster] == [
        date(2026, 5, 4),
        date(2026, 5, 5),
        date(2026, 5, 6),
        date(2026, 5, 7),
    ]


def test_an_int_cap_still_counts_shifts_whatever_they_are_long():
    roster = plan_for(timedelta(hours=10), 5).roster()

    assert len(roster) == 5
    assert sum((shift.length for shift in roster), timedelta(0)) == timedelta(hours=50)


def test_a_pattern_that_would_cross_the_cap_is_skipped_and_a_shorter_one_fits():
    plan = Plan(
        horizon=HORIZON,
        patterns=[
            ShiftPattern(
                "anna", "depot-north", time(8), timedelta(hours=10), weekdays={0, 1, 2}
            ),
            ShiftPattern(
                "anna", "depot-north", time(20), timedelta(hours=2), weekdays={2}
            ),
        ],
        limits={"anna": timedelta(hours=22)},
    )

    roster = plan.roster()
    assert [(shift.start.date(), shift.length) for shift in roster] == [
        (date(2026, 5, 4), timedelta(hours=10)),
        (date(2026, 5, 5), timedelta(hours=10)),
        (date(2026, 5, 6), timedelta(hours=2)),
    ]
    assert plan.applied_to(roster) == roster


@pytest.mark.parametrize("limit", [0, timedelta(0), timedelta(hours=7)])
def test_a_cap_too_small_for_one_shift_draws_nothing(limit):
    assert len(plan_for(timedelta(hours=8), limit).roster()) == 0


def test_caps_are_counted_per_worker():
    plan = Plan(
        horizon=HORIZON,
        patterns=[
            ShiftPattern(
                "anna", "depot-north", time(8), timedelta(hours=8), weekdays=WEEKDAYS
            ),
            ShiftPattern(
                "boris", "depot-north", time(16), timedelta(hours=8), weekdays=WEEKDAYS
            ),
        ],
        limits={"anna": timedelta(hours=16)},
    )

    roster = plan.roster()
    assert len(roster.for_worker("anna")) == 2
    assert len(roster.for_worker("boris")) == 5


@pytest.mark.parametrize("limit", [-1, timedelta(hours=-1)])
def test_plan_rejects_a_negative_cap(limit):
    with pytest.raises(ValueError):
        plan_for(timedelta(hours=8), limit)


@pytest.mark.parametrize("limit", ["40h", 3.5, None])
def test_plan_rejects_a_cap_that_is_neither_a_count_nor_a_duration(limit):
    with pytest.raises(TypeError):
        Plan(
            horizon=HORIZON,
            patterns=[
                ShiftPattern("anna", "depot-north", time(8), timedelta(hours=8))
            ],
            limits={"anna": limit},
        )
