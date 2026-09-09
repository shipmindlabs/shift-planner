"""Daylight-saving boundaries, spelled out.

The library compares and subtracts moments as instants, so a shift or a lock
built from absolute times behaves the same across a transition. Arithmetic
*inside* a zone follows Python's rule instead: adding a ``timedelta`` moves the
wall clock, not the instant. Both halves are pinned down below.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from shift_planner import (
    ActivityWindow,
    Cooldown,
    CooldownBoard,
    OverlappingShiftError,
    Roster,
    Shift,
    StartVerdict,
)

try:
    BERLIN = ZoneInfo("Europe/Berlin")
except ZoneInfoNotFoundError:
    pytest.skip("IANA timezone database unavailable", allow_module_level=True)

UTC = timezone.utc

# 2026-03-29: Berlin skips 02:00-03:00 local. 2026-10-25: it repeats 02:00-03:00.


def test_a_zone_local_shift_measures_its_length_on_the_wall_clock():
    shift = Shift(
        "anna",
        "depot-north",
        datetime(2026, 3, 29, 1, 30, tzinfo=BERLIN),
        timedelta(hours=2),
    )
    assert shift.start.utcoffset() == timedelta(hours=1)
    assert shift.end == datetime(2026, 3, 29, 3, 30, tzinfo=BERLIN)
    assert shift.end.utcoffset() == timedelta(hours=2)
    # Two hours on the clock, one hour of real duty: the skipped hour never was.
    assert shift.end.astimezone(UTC) - shift.start.astimezone(UTC) == timedelta(hours=1)


def test_a_shift_pinned_to_utc_keeps_its_real_length_over_the_gap():
    shift = Shift(
        "anna",
        "depot-north",
        datetime(2026, 3, 29, 0, 30, tzinfo=UTC),
        timedelta(hours=2),
    )
    assert shift.end == datetime(2026, 3, 29, 2, 30, tzinfo=UTC)

    local_start = shift.start.astimezone(BERLIN)
    local_end = shift.end.astimezone(BERLIN)
    assert (local_start.hour, local_start.minute) == (1, 30)
    assert (local_end.hour, local_end.minute) == (4, 30)

    assert shift.covers(datetime(2026, 3, 29, 3, 30, tzinfo=BERLIN))
    assert not shift.covers(datetime(2026, 3, 29, 4, 30, tzinfo=BERLIN))


def test_the_window_judges_a_report_made_after_the_clocks_jumped():
    window = ActivityWindow(early_tolerance=timedelta(minutes=15), late_cutoff=timedelta(hours=1))
    start = datetime(2026, 3, 29, 0, 45, tzinfo=UTC)  # 01:45 local, still on winter time

    reported = datetime(2026, 3, 29, 3, 30, tzinfo=BERLIN)  # 01:30 UTC, 45 minutes later
    assert window.verdict(start, reported) is StartVerdict.ACCEPTED

    too_late = datetime(2026, 3, 29, 4, tzinfo=BERLIN)  # 02:00 UTC, past the cutoff
    assert window.verdict(start, too_late) is StartVerdict.TOO_LATE


def test_the_repeated_hour_holds_two_shifts_with_the_same_wall_clock():
    first = Shift("anna", "depot-north", datetime(2026, 10, 25, 0, tzinfo=UTC), timedelta(hours=1))
    second = Shift("anna", "depot-north", datetime(2026, 10, 25, 1, tzinfo=UTC), timedelta(hours=1))

    local_firsts = first.start.astimezone(BERLIN)
    local_second = second.start.astimezone(BERLIN)
    assert (local_firsts.hour, local_firsts.minute) == (2, 0)
    assert (local_second.hour, local_second.minute) == (2, 0)

    assert not first.overlaps(second)
    assert len(Roster([first, second])) == 2


def test_shifts_that_read_apart_on_the_wall_clock_still_clash():
    # 02:30 summer time to 02:30 winter time, and 02:00 to 02:30 winter time.
    first = Shift("anna", "depot-north", datetime(2026, 10, 25, 0, 30, tzinfo=UTC), timedelta(hours=1))
    second = Shift("anna", "depot-north", datetime(2026, 10, 25, 1, tzinfo=UTC), timedelta(minutes=30))

    assert first.overlaps(second)
    with pytest.raises(OverlappingShiftError):
        Roster([first, second])


def test_a_cooldown_lifts_once_even_though_the_hour_comes_twice():
    board = CooldownBoard(cooldown=Cooldown(timedelta(hours=1)))
    board = board.refuse("anna", datetime(2026, 10, 25, 0, 30, tzinfo=UTC))

    summer_pass = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=0)
    winter_pass = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=1)

    assert board.locked("anna", summer_pass)
    assert board.remaining("anna", summer_pass) == timedelta(hours=1)
    assert not board.locked("anna", winter_pass)
    assert board.remaining("anna", winter_pass) == timedelta(0)


def test_a_zone_local_cooldown_counts_its_minutes_on_the_wall_clock():
    lock = Cooldown(timedelta(minutes=90)).lock("anna", datetime(2026, 3, 29, 1, 30, tzinfo=BERLIN))

    assert lock.until == datetime(2026, 3, 29, 3, tzinfo=BERLIN)
    assert lock.duration == timedelta(minutes=90)
    # Half an hour of real waiting: the rest of the span fell into the gap.
    assert lock.until.astimezone(UTC) - lock.since.astimezone(UTC) == timedelta(minutes=30)
    assert not lock.holds_at(datetime(2026, 3, 29, 1, tzinfo=UTC))
