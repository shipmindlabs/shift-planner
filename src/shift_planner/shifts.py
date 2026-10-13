"""Shifts as half-open time intervals and a roster that keeps them apart."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Iterator

from shift_planner.windows import ActivityWindow, StartVerdict

__all__ = [
    "InsufficientRestError",
    "OverlappingShiftError",
    "Roster",
    "Shift",
]


def _span(shift: "Shift") -> str:
    return f"{shift.start.isoformat()}/{shift.end.isoformat()}"


class InsufficientRestError(ValueError):
    """Raised when a worker's next shift starts before they have rested."""

    def __init__(
        self,
        first: "Shift",
        second: "Shift",
        rest: timedelta,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message
            or (
                f"worker {first.worker!r} gets {second.start - first.end} of rest "
                f"between {_span(first)} and {_span(second)}, "
                f"less than the required {rest}"
            )
        )
        self.first = first
        self.second = second
        self.rest = rest


class OverlappingShiftError(InsufficientRestError):
    """Raised when one worker is given two shifts that share time.

    An overlap is the zero-rest case of the rest rule, but it keeps its own
    name: a clash reads differently from a break that is merely too short.
    """

    def __init__(
        self, first: "Shift", second: "Shift", rest: timedelta = timedelta(0)
    ) -> None:
        super().__init__(
            first,
            second,
            rest,
            f"worker {first.worker!r} has overlapping shifts: "
            f"{_span(first)} and {_span(second)}",
        )


@dataclass(frozen=True)
class Shift:
    """A single courier shift at one location.

    The shift covers the half-open interval ``[start, start + length)``, so a
    shift that ends exactly when the next one starts is not an overlap.
    ``capacity`` is the number of jobs the courier can take during the shift.
    ``window`` decides how early and how late the courier may report for duty.
    """

    worker: str
    location: str
    start: datetime
    length: timedelta
    capacity: int = 1
    window: ActivityWindow = field(default_factory=ActivityWindow)

    def __post_init__(self) -> None:
        if not self.worker.strip():
            raise ValueError("worker must be a non-empty string")
        if not self.location.strip():
            raise ValueError("location must be a non-empty string")
        # Naive and aware datetimes cannot be compared, which would turn every
        # overlap check into an opaque TypeError.
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.length <= timedelta(0):
            raise ValueError("length must be positive")
        if self.capacity < 1:
            raise ValueError("capacity must be at least 1")

    @property
    def end(self) -> datetime:
        return self.start + self.length

    @property
    def opens_at(self) -> datetime:
        return self.window.opens_at(self.start)

    @property
    def closes_at(self) -> datetime:
        return self.window.closes_at(self.start)

    def covers(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def overlaps(self, other: "Shift") -> bool:
        return self.start < other.end and other.start < self.end

    def start_verdict(self, moment: datetime) -> StartVerdict:
        return self.window.verdict(self.start, moment)

    def may_start_at(self, moment: datetime) -> bool:
        return self.window.accepts(self.start, moment)


@dataclass(frozen=True)
class Roster:
    """An overlap-free set of shifts, ordered by start time.

    Any iterable of shifts may be passed; it is normalised to a sorted tuple.
    Two shifts of the same worker must leave at least ``rest`` between the end
    of one and the start of the next, so they may touch only while ``rest`` is
    zero and may never share time.
    """

    shifts: tuple[Shift, ...] = ()
    rest: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        if self.rest < timedelta(0):
            raise ValueError("rest must not be negative")
        ordered = tuple(
            sorted(self.shifts, key=lambda shift: (shift.start, shift.end, shift.worker))
        )
        latest: dict[str, Shift] = {}
        for shift in ordered:
            previous = latest.get(shift.worker)
            if previous is not None:
                if previous.overlaps(shift):
                    raise OverlappingShiftError(previous, shift, self.rest)
                if shift.start - previous.end < self.rest:
                    raise InsufficientRestError(previous, shift, self.rest)
            latest[shift.worker] = shift
        object.__setattr__(self, "shifts", ordered)

    def add(self, shift: Shift) -> "Roster":
        return Roster(self.shifts + (shift,), self.rest)

    def extend(self, shifts: Iterable[Shift]) -> "Roster":
        return Roster(self.shifts + tuple(shifts), self.rest)

    def for_worker(self, worker: str) -> tuple[Shift, ...]:
        return tuple(shift for shift in self.shifts if shift.worker == worker)

    def on_duty(self, moment: datetime) -> tuple[Shift, ...]:
        return tuple(shift for shift in self.shifts if shift.covers(moment))

    def startable(self, worker: str, moment: datetime) -> tuple[Shift, ...]:
        return tuple(
            shift
            for shift in self.shifts
            if shift.worker == worker and shift.may_start_at(moment)
        )

    def __iter__(self) -> Iterator[Shift]:
        return iter(self.shifts)

    def __len__(self) -> int:
        return len(self.shifts)
