"""The activity window and its two edges."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shift_planner import ActivityWindow, StartVerdict

START = datetime(2026, 5, 4, 8, tzinfo=timezone.utc)
WINDOW = ActivityWindow(early_tolerance=timedelta(minutes=15), late_cutoff=timedelta(hours=1))


def test_default_window_is_a_quarter_hour_early_and_an_hour_late():
    default = ActivityWindow()
    assert default.early_tolerance == timedelta(minutes=15)
    assert default.late_cutoff == timedelta(hours=1)


def test_window_spans_from_the_tolerance_to_the_cutoff():
    assert WINDOW.opens_at(START) == datetime(2026, 5, 4, 7, 45, tzinfo=timezone.utc)
    assert WINDOW.closes_at(START) == datetime(2026, 5, 4, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "offset, expected",
    [
        (timedelta(hours=-2), StartVerdict.TOO_EARLY),
        (timedelta(minutes=-16), StartVerdict.TOO_EARLY),
        (timedelta(minutes=-15), StartVerdict.ACCEPTED),
        (timedelta(minutes=-14), StartVerdict.ACCEPTED),
        (timedelta(0), StartVerdict.ACCEPTED),
        (timedelta(minutes=59, seconds=59), StartVerdict.ACCEPTED),
        (timedelta(hours=1), StartVerdict.TOO_LATE),
        (timedelta(hours=2), StartVerdict.TOO_LATE),
    ],
)
def test_verdict_on_both_edges(offset, expected):
    moment = START + offset
    assert WINDOW.verdict(START, moment) is expected
    assert WINDOW.accepts(START, moment) is (expected is StartVerdict.ACCEPTED)


def test_only_the_accepted_verdict_reads_as_accepted():
    assert StartVerdict.ACCEPTED.accepted
    assert not StartVerdict.TOO_EARLY.accepted
    assert not StartVerdict.TOO_LATE.accepted


def test_zero_tolerance_opens_exactly_at_the_planned_start():
    tight = ActivityWindow(early_tolerance=timedelta(0), late_cutoff=timedelta(minutes=10))
    assert tight.opens_at(START) == START
    assert tight.verdict(START, START - timedelta(seconds=1)) is StartVerdict.TOO_EARLY
    assert tight.verdict(START, START) is StartVerdict.ACCEPTED


def test_moments_are_read_as_instants_not_as_wall_clocks():
    east = timezone(timedelta(hours=3))
    assert WINDOW.verdict(START, datetime(2026, 5, 4, 11, tzinfo=east)) is StartVerdict.ACCEPTED
    assert (
        WINDOW.verdict(START, datetime(2026, 5, 4, 10, 30, tzinfo=east))
        is StartVerdict.TOO_EARLY
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"early_tolerance": timedelta(minutes=-1)},
        {"late_cutoff": timedelta(0)},
        {"late_cutoff": timedelta(minutes=-5)},
    ],
)
def test_window_rejects_impossible_bounds(kwargs):
    with pytest.raises(ValueError):
        ActivityWindow(**kwargs)
