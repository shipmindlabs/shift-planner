"""The activity window: how early a shift may be started and when it lapses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

__all__ = ["ActivityWindow", "StartVerdict"]


class StartVerdict(Enum):
    """Outcome of checking a reported start against an activity window."""

    TOO_EARLY = "too_early"
    ACCEPTED = "accepted"
    TOO_LATE = "too_late"

    @property
    def accepted(self) -> bool:
        return self is StartVerdict.ACCEPTED


@dataclass(frozen=True)
class ActivityWindow:
    """How far around a planned start a courier may report for duty.

    The window is the half-open interval
    ``[start - early_tolerance, start + late_cutoff)``: reporting exactly
    ``early_tolerance`` ahead of the planned start is still accepted, while
    reporting exactly ``late_cutoff`` after it is already too late.
    """

    early_tolerance: timedelta = timedelta(minutes=15)
    late_cutoff: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if self.early_tolerance < timedelta(0):
            raise ValueError("early_tolerance must not be negative")
        if self.late_cutoff <= timedelta(0):
            raise ValueError("late_cutoff must be positive")

    def opens_at(self, start: datetime) -> datetime:
        return start - self.early_tolerance

    def closes_at(self, start: datetime) -> datetime:
        return start + self.late_cutoff

    def verdict(self, start: datetime, moment: datetime) -> StartVerdict:
        if moment < self.opens_at(start):
            return StartVerdict.TOO_EARLY
        if moment >= self.closes_at(start):
            return StartVerdict.TOO_LATE
        return StartVerdict.ACCEPTED

    def accepts(self, start: datetime, moment: datetime) -> bool:
        return self.verdict(start, moment) is StartVerdict.ACCEPTED
