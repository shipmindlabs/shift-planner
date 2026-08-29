"""Timed cooldowns that follow a refusal and lift themselves."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Iterator

__all__ = ["Cooldown", "CooldownBoard", "CooldownLock"]


@dataclass(frozen=True)
class Cooldown:
    """How long a courier stays out of the queue after declining a job."""

    duration: timedelta = timedelta(minutes=20)

    def __post_init__(self) -> None:
        if self.duration <= timedelta(0):
            raise ValueError("duration must be positive")

    def lock(self, worker: str, moment: datetime) -> "CooldownLock":
        return CooldownLock(worker=worker, since=moment, until=moment + self.duration)


@dataclass(frozen=True)
class CooldownLock:
    """A worker held back over the half-open interval ``[since, until)``.

    The lock carries its own end, so it stops holding by the passing of time;
    there is no way to lift it early and none is needed.
    """

    worker: str
    since: datetime
    until: datetime

    def __post_init__(self) -> None:
        if not self.worker.strip():
            raise ValueError("worker must be a non-empty string")
        for name, moment in (("since", self.since), ("until", self.until)):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.until <= self.since:
            raise ValueError("until must be after since")

    @property
    def duration(self) -> timedelta:
        return self.until - self.since

    def holds_at(self, moment: datetime) -> bool:
        return self.since <= moment < self.until

    def remaining(self, moment: datetime) -> timedelta:
        return max(timedelta(0), self.until - moment)


@dataclass(frozen=True)
class CooldownBoard:
    """The refusal locks on record, at most one per worker.

    A board is immutable: recording a refusal returns a new board. Expiry is
    read off the clock, so an untouched board unlocks everyone on its own.
    """

    locks: tuple[CooldownLock, ...] = ()
    cooldown: Cooldown = field(default_factory=Cooldown)

    def __post_init__(self) -> None:
        latest: dict[str, CooldownLock] = {}
        for lock in self.locks:
            previous = latest.get(lock.worker)
            if previous is None or lock.until > previous.until:
                latest[lock.worker] = lock
        object.__setattr__(
            self,
            "locks",
            tuple(sorted(latest.values(), key=lambda lock: (lock.until, lock.worker))),
        )

    def lock_for(self, worker: str) -> CooldownLock | None:
        for lock in self.locks:
            if lock.worker == worker:
                return lock
        return None

    def refuse(self, worker: str, moment: datetime) -> "CooldownBoard":
        fresh = self.cooldown.lock(worker, moment)
        current = self.lock_for(worker)
        # Refusing again while a lock still holds must not cut it short.
        if current is not None and current.holds_at(moment) and current.until > fresh.until:
            fresh = replace(fresh, until=current.until)
        kept = tuple(lock for lock in self.locks if lock.worker != worker)
        return CooldownBoard(kept + (fresh,), self.cooldown)

    def locked(self, worker: str, moment: datetime) -> bool:
        lock = self.lock_for(worker)
        return lock is not None and lock.holds_at(moment)

    def lifts_at(self, worker: str, moment: datetime) -> datetime | None:
        lock = self.lock_for(worker)
        return lock.until if lock is not None and lock.holds_at(moment) else None

    def remaining(self, worker: str, moment: datetime) -> timedelta:
        lock = self.lock_for(worker)
        return lock.remaining(moment) if lock is not None else timedelta(0)

    def active(self, moment: datetime) -> tuple[CooldownLock, ...]:
        return tuple(lock for lock in self.locks if lock.holds_at(moment))

    def purged(self, moment: datetime) -> "CooldownBoard":
        """Drop the locks that have already run out; holding ones stay."""
        return CooldownBoard(self.active(moment), self.cooldown)

    def __iter__(self) -> Iterator[CooldownLock]:
        return iter(self.locks)

    def __len__(self) -> int:
        return len(self.locks)
