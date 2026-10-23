"""Turning recurring patterns into a roster over a planning horizon."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Iterator, Mapping

from shift_planner.shifts import Roster, Shift
from shift_planner.windows import ActivityWindow

__all__ = ["Holidays", "Horizon", "Plan", "ShiftPattern"]

ZERO = timedelta(0)


@dataclass(frozen=True)
class Horizon:
    """The span a plan is drawn for: the half-open range ``[start, start + days)``."""

    start: date
    days: int = 7

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError("days must be at least 1")

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days)

    def covers(self, day: date) -> bool:
        return self.start <= day < self.end

    def __iter__(self) -> Iterator[date]:
        for offset in range(self.days):
            yield self.start + timedelta(days=offset)

    def __len__(self) -> int:
        return self.days


@dataclass(frozen=True)
class Holidays:
    """Days on which no pattern produces a shift."""

    days: frozenset[date] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "days", frozenset(self.days))

    def __contains__(self, day: date) -> bool:
        return day in self.days

    def __iter__(self) -> Iterator[date]:
        return iter(sorted(self.days))

    def __len__(self) -> int:
        return len(self.days)


@dataclass(frozen=True)
class ShiftPattern:
    """A shift that repeats on chosen weekdays at the same place and hour.

    ``at`` is a plain wall-clock time; the plan decides which timezone it is
    read in. Weekdays follow ``date.weekday()``: 0 is Monday, 6 is Sunday.
    """

    worker: str
    location: str
    at: time
    length: timedelta
    weekdays: frozenset[int] = frozenset(range(5))
    capacity: int = 1
    window: ActivityWindow = field(default_factory=ActivityWindow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "weekdays", frozenset(self.weekdays))
        if not self.worker.strip():
            raise ValueError("worker must be a non-empty string")
        if not self.location.strip():
            raise ValueError("location must be a non-empty string")
        if self.at.tzinfo is not None:
            raise ValueError("at must be a plain time; the plan carries the timezone")
        if not self.weekdays:
            raise ValueError("weekdays must not be empty")
        if any(weekday not in range(7) for weekday in self.weekdays):
            raise ValueError("weekdays must be between 0 (Monday) and 6 (Sunday)")
        if self.length <= ZERO:
            raise ValueError("length must be positive")
        if self.capacity < 1:
            raise ValueError("capacity must be at least 1")

    def occurs_on(self, day: date) -> bool:
        return day.weekday() in self.weekdays

    def shift_on(self, day: date, zone: tzinfo = timezone.utc) -> Shift:
        return Shift(
            worker=self.worker,
            location=self.location,
            start=datetime.combine(day, self.at, tzinfo=zone),
            length=self.length,
            capacity=self.capacity,
            window=self.window,
        )


@dataclass(frozen=True)
class Plan:
    """Patterns unrolled over a horizon, minus holidays and beyond limits.

    ``limits`` caps a worker across the whole horizon: an ``int`` caps the
    number of shifts, a ``timedelta`` caps their summed length. Days are walked
    in order, and a pattern that would carry its worker past the cap is skipped
    while the walk goes on, so a shorter pattern later in the span may still
    fit. ``rest`` is the break the drawn roster demands between two shifts of
    one worker. The result is a function of the plan alone, which is what makes
    redrawing it safe: :meth:`applied_to` replaces exactly what the plan owns
    and leaves every other shift of the roster where it is.
    """

    horizon: Horizon
    patterns: tuple[ShiftPattern, ...] = ()
    holidays: Holidays = field(default_factory=Holidays)
    limits: Mapping[str, int | timedelta] = field(default_factory=dict)
    zone: tzinfo = timezone.utc
    rest: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        unique: dict[ShiftPattern, None] = {}
        for pattern in self.patterns:
            unique.setdefault(pattern, None)
        object.__setattr__(self, "patterns", tuple(unique))
        limits = dict(self.limits)
        for worker, limit in limits.items():
            if not isinstance(limit, (int, timedelta)):
                raise TypeError(f"limit for {worker!r} must be an int or a timedelta")
            if limit < (ZERO if isinstance(limit, timedelta) else 0):
                raise ValueError(f"limit for {worker!r} must not be negative")
        object.__setattr__(self, "limits", limits)
        if self.rest < ZERO:
            raise ValueError("rest must not be negative")

    @property
    def workers(self) -> frozenset[str]:
        return frozenset(pattern.worker for pattern in self.patterns)

    def shifts(self) -> tuple[Shift, ...]:
        planned: list[Shift] = []
        counts: dict[str, int] = {}
        worked: dict[str, timedelta] = {}
        for day in self.horizon:
            if day in self.holidays:
                continue
            for pattern in self.patterns:
                if not pattern.occurs_on(day):
                    continue
                worker = pattern.worker
                limit = self.limits.get(worker)
                if isinstance(limit, timedelta):
                    if worked.get(worker, ZERO) + pattern.length > limit:
                        continue
                elif limit is not None and counts.get(worker, 0) >= limit:
                    continue
                planned.append(pattern.shift_on(day, self.zone))
                counts[worker] = counts.get(worker, 0) + 1
                worked[worker] = worked.get(worker, ZERO) + pattern.length
        return tuple(planned)

    def roster(self) -> Roster:
        return Roster(self.shifts(), self.rest)

    def claims(self, shift: Shift) -> bool:
        """Whether the shift falls in the part of a roster this plan speaks for."""
        if shift.worker not in self.workers:
            return False
        return self.horizon.covers(shift.start.astimezone(self.zone).date())

    def applied_to(self, roster: Roster) -> Roster:
        kept = tuple(shift for shift in roster if not self.claims(shift))
        # Drawing a plan may tighten the rest rule of a roster, never loosen it.
        return Roster(kept + self.shifts(), max(roster.rest, self.rest))
