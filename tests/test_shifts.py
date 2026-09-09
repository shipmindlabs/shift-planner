"""Shift coverage, overlap and the roster's overlap guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shift_planner import (
    ActivityWindow,
    OverlappingShiftError,
    Roster,
    Shift,
    StartVerdict,
)

MORNING = datetime(2026, 5, 4, 8, tzinfo=timezone.utc)


def make_shift(
    worker="anna",
    location="depot-north",
    start=MORNING,
    length=timedelta(hours=4),
    **kwargs,
) -> Shift:
    return Shift(worker=worker, location=location, start=start, length=length, **kwargs)


def test_shift_covers_its_start_but_not_its_end():
    duty = make_shift()
    assert duty.end == datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
    assert duty.covers(duty.start)
    assert duty.covers(duty.end - timedelta(microseconds=1))
    assert not duty.covers(duty.end)
    assert not duty.covers(duty.start - timedelta(microseconds=1))


@pytest.mark.parametrize(
    "offset, length, overlapping",
    [
        (timedelta(hours=4), timedelta(hours=4), False),
        (timedelta(hours=-4), timedelta(hours=4), False),
        (timedelta(hours=5), timedelta(hours=1), False),
        (timedelta(hours=3, minutes=59), timedelta(hours=4), True),
        (timedelta(hours=1), timedelta(hours=1), True),
        (timedelta(hours=-1), timedelta(hours=6), True),
        (timedelta(0), timedelta(hours=4), True),
    ],
)
def test_overlap_is_half_open_and_symmetric(offset, length, overlapping):
    first = make_shift()
    second = make_shift(worker="boris", start=MORNING + offset, length=length)
    assert first.overlaps(second) is overlapping
    assert second.overlaps(first) is overlapping


def test_roster_orders_shifts_by_start():
    late = make_shift(start=MORNING + timedelta(hours=6))
    early = make_shift(worker="boris")
    roster = Roster([late, early])
    assert [shift.start for shift in roster] == [early.start, late.start]
    assert len(roster) == 2


def test_roster_takes_touching_shifts_of_one_worker():
    morning = make_shift()
    afternoon = make_shift(start=MORNING + timedelta(hours=4))
    assert len(Roster([morning, afternoon])) == 2


def test_roster_takes_overlapping_shifts_of_different_workers():
    anna = make_shift()
    boris = make_shift(worker="boris", start=MORNING + timedelta(hours=1))
    assert len(Roster([anna, boris])) == 2


def test_roster_rejects_two_shifts_of_one_worker_that_share_time():
    morning = make_shift()
    clashing = make_shift(start=MORNING + timedelta(hours=3))
    with pytest.raises(OverlappingShiftError) as caught:
        Roster([morning, clashing])
    assert caught.value.first == morning
    assert caught.value.second == clashing
    assert "anna" in str(caught.value)


def test_roster_rejects_a_shift_swallowed_by_a_longer_one():
    short = make_shift(start=MORNING + timedelta(hours=1), length=timedelta(hours=1))
    long = make_shift(length=timedelta(hours=8))
    with pytest.raises(OverlappingShiftError):
        Roster([short, long])


def test_add_and_extend_leave_the_original_roster_alone():
    roster = Roster([make_shift()])
    grown = roster.add(make_shift(worker="boris"))
    extended = grown.extend([make_shift(worker="clara")])
    assert len(roster) == 1
    assert len(grown) == 2
    assert len(extended) == 3


def test_add_refuses_a_clash_and_keeps_the_roster_intact():
    roster = Roster([make_shift()])
    with pytest.raises(OverlappingShiftError):
        roster.add(make_shift(start=MORNING + timedelta(hours=2)))
    assert len(roster) == 1


def test_for_worker_and_on_duty_select_by_worker_and_moment():
    anna = make_shift()
    boris = make_shift(worker="boris", start=MORNING + timedelta(hours=6))
    roster = Roster([anna, boris])
    assert roster.for_worker("anna") == (anna,)
    assert roster.for_worker("nobody") == ()
    assert roster.on_duty(MORNING + timedelta(hours=1)) == (anna,)
    assert roster.on_duty(MORNING + timedelta(hours=5)) == ()


def test_startable_uses_the_window_of_each_shift():
    morning = make_shift()
    evening = make_shift(start=MORNING + timedelta(hours=10))
    roster = Roster([morning, evening])
    assert roster.startable("anna", MORNING - timedelta(minutes=10)) == (morning,)
    assert roster.startable("anna", MORNING + timedelta(hours=2)) == ()


def test_shift_reports_its_window_edges_and_verdicts():
    duty = make_shift(
        window=ActivityWindow(early_tolerance=timedelta(minutes=30), late_cutoff=timedelta(hours=2))
    )
    assert duty.opens_at == MORNING - timedelta(minutes=30)
    assert duty.closes_at == MORNING + timedelta(hours=2)
    assert duty.may_start_at(MORNING - timedelta(minutes=30))
    assert duty.start_verdict(MORNING - timedelta(minutes=31)) is StartVerdict.TOO_EARLY
    assert duty.start_verdict(MORNING + timedelta(hours=2)) is StartVerdict.TOO_LATE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"worker": "   "},
        {"location": ""},
        {"start": datetime(2026, 5, 4, 8)},
        {"length": timedelta(0)},
        {"length": timedelta(hours=-1)},
        {"capacity": 0},
    ],
)
def test_shift_rejects_nonsense(kwargs):
    with pytest.raises(ValueError):
        make_shift(**kwargs)
