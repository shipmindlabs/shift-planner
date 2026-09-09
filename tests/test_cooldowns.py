"""Refusal locks: they hold by the clock and lift by the clock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shift_planner import Cooldown, CooldownBoard, CooldownLock

TWENTY = Cooldown(timedelta(minutes=20))


def test_a_refusal_locks_only_the_worker_who_refused(clock):
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", clock.now)
    assert board.locked("anna", clock.now)
    assert not board.locked("boris", clock.now)
    assert board.remaining("boris", clock.now) == timedelta(0)


def test_the_lock_holds_from_the_refusal_and_lifts_on_its_own(clock):
    refused_at = clock.now
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", refused_at)

    assert board.remaining("anna", clock.now) == timedelta(minutes=20)
    assert board.lifts_at("anna", clock.now) == refused_at + timedelta(minutes=20)

    clock.tick(timedelta(minutes=19, seconds=59))
    assert board.locked("anna", clock.now)
    assert board.remaining("anna", clock.now) == timedelta(seconds=1)

    clock.tick(timedelta(seconds=1))
    assert not board.locked("anna", clock.now)
    assert board.remaining("anna", clock.now) == timedelta(0)
    assert board.lifts_at("anna", clock.now) is None


def test_refusing_again_while_the_lock_holds_pushes_its_end_out(clock):
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", clock.now)
    again = board.refuse("anna", clock.tick(timedelta(minutes=5)))
    assert again.lifts_at("anna", clock.now) == clock.now + timedelta(minutes=20)
    assert len(again) == 1


def test_a_shorter_cooldown_cannot_cut_a_holding_lock_short(clock):
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", clock.now)
    ends_at = board.lifts_at("anna", clock.now)

    impatient = CooldownBoard(board.locks, Cooldown(timedelta(minutes=5)))
    again = impatient.refuse("anna", clock.tick(timedelta(minutes=5)))

    assert again.lifts_at("anna", clock.now) == ends_at


def test_refusing_after_the_lock_lifted_starts_a_fresh_one(clock):
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", clock.now)
    clock.tick(timedelta(minutes=20))
    again = board.refuse("anna", clock.now)
    assert again.lifts_at("anna", clock.now) == clock.now + timedelta(minutes=20)


def test_refuse_returns_a_new_board_and_leaves_the_old_one_untouched(clock):
    board = CooldownBoard(cooldown=TWENTY)
    after = board.refuse("anna", clock.now)
    assert len(board) == 0
    assert not board.locked("anna", clock.now)
    assert len(after) == 1


def test_a_board_keeps_the_longest_lock_per_worker(clock):
    short = CooldownLock("anna", clock.now, clock.now + timedelta(minutes=5))
    long = CooldownLock("anna", clock.now, clock.now + timedelta(minutes=30))
    board = CooldownBoard((short, long))
    assert len(board) == 1
    assert board.lock_for("anna") == long


def test_locks_are_ordered_by_their_end(clock):
    late = CooldownLock("anna", clock.now, clock.now + timedelta(minutes=30))
    early = CooldownLock("boris", clock.now, clock.now + timedelta(minutes=10))
    board = CooldownBoard((late, early))
    assert [lock.worker for lock in board] == ["boris", "anna"]


def test_active_and_purged_drop_the_locks_that_ran_out(clock):
    board = CooldownBoard(cooldown=TWENTY).refuse("anna", clock.now)
    board = board.refuse("boris", clock.tick(timedelta(minutes=10)))

    clock.tick(timedelta(minutes=15))
    assert [lock.worker for lock in board.active(clock.now)] == ["boris"]

    purged = board.purged(clock.now)
    assert len(purged) == 1
    assert purged.lock_for("anna") is None
    assert purged.cooldown == board.cooldown


def test_lock_reports_its_span_and_clamps_what_is_left(clock):
    lock = TWENTY.lock("anna", clock.now)
    assert lock.since == clock.now
    assert lock.duration == timedelta(minutes=20)
    assert lock.holds_at(lock.since)
    assert not lock.holds_at(lock.until)
    assert lock.remaining(lock.until + timedelta(hours=3)) == timedelta(0)


@pytest.mark.parametrize(
    "worker, since, until",
    [
        ("  ", datetime(2026, 5, 4, 12, tzinfo=timezone.utc), datetime(2026, 5, 4, 13, tzinfo=timezone.utc)),
        ("anna", datetime(2026, 5, 4, 12), datetime(2026, 5, 4, 13, tzinfo=timezone.utc)),
        ("anna", datetime(2026, 5, 4, 12, tzinfo=timezone.utc), datetime(2026, 5, 4, 13)),
        ("anna", datetime(2026, 5, 4, 12, tzinfo=timezone.utc), datetime(2026, 5, 4, 12, tzinfo=timezone.utc)),
        ("anna", datetime(2026, 5, 4, 12, tzinfo=timezone.utc), datetime(2026, 5, 4, 11, tzinfo=timezone.utc)),
    ],
)
def test_lock_rejects_nonsense(worker, since, until):
    with pytest.raises(ValueError):
        CooldownLock(worker, since, until)


@pytest.mark.parametrize("duration", [timedelta(0), timedelta(minutes=-1)])
def test_cooldown_rejects_a_non_positive_duration(duration):
    with pytest.raises(ValueError):
        Cooldown(duration)
