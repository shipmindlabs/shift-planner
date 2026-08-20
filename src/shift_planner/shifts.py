"""Shifts as half-open time intervals and a roster that keeps them apart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Iterator

__all__ = ["OverlappingShiftError", "Roster", "Shift"]


class OverlappingShiftError(ValueError):
    """Raised when one worker is given two shifts that share time."""

    def __init__(self, first: "Shift", second: "Shift") -> None:
        super().__init__(
            f"worker {first.worker!r} has overlapping shifts: "
            f"{first.start.isoformat()}/{first.end.isoformat()} and "
            f"{second.start.isoformat()}/{second.end.isoformat()}"
        )
        self.first = first
        self.second = second


@dataclass(frozen=True)
class Shift:
    """A single courier shift at one location.

    The shift covers the half-open interval ``[start, start + length)``, so a
    shift that ends exactly when the next one starts is not an overlap.
    ``capacity`` is the number of jobs the courier can take during the shift.
    """

    worker: str
    location: str
    start: datetime
    length: timedelta
    capacity: int = 1

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

    def covers(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def overlaps(self, other: "Shift") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Roster:
    """An overlap-free set of shifts, ordered by start time.

    Any iterable of shifts may be passed; it is normalised to a sorted tuple.
    Two shifts of the same worker that share time make construction fail.
    """

    shifts: tuple[Shift, ...] = ()

    def __post_init__(self) -> None:
        ordered = tuple(
            sorted(self.shifts, key=lambda shift: (shift.start, shift.end, shift.worker))
        )
        latest: dict[str, Shift] = {}
        for shift in ordered:
            previous = latest.get(shift.worker)
            if previous is not None and previous.overlaps(shift):
                raise OverlappingShiftError(previous, shift)
            latest[shift.worker] = shift
        object.__setattr__(self, "shifts", ordered)

    def add(self, shift: Shift) -> "Roster":
        return Roster(self.shifts + (shift,))

    def extend(self, shifts: Iterable[Shift]) -> "Roster":
        return Roster(self.shifts + tuple(shifts))

    def for_worker(self, worker: str) -> tuple[Shift, ...]:
        return tuple(shift for shift in self.shifts if shift.worker == worker)

    def on_duty(self, moment: datetime) -> tuple[Shift, ...]:
        return tuple(shift for shift in self.shifts if shift.covers(moment))

    def __iter__(self) -> Iterator[Shift]:
        return iter(self.shifts)

    def __len__(self) -> int:
        return len(self.shifts)
