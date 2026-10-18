"""Choosing the courier who takes the next job."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from shift_planner.cooldowns import CooldownBoard
from shift_planner.shifts import Roster, Shift

__all__ = [
    "AssignmentPolicy",
    "AssignmentReason",
    "AssignmentVerdict",
    "Candidate",
    "Dispatcher",
    "EarliestStart",
    "Job",
    "LeastLoaded",
]


@dataclass(frozen=True)
class Job:
    """A job waiting to be handed out at one location at a given moment."""

    location: str
    at: datetime

    def __post_init__(self) -> None:
        if not self.location.strip():
            raise ValueError("location must be a non-empty string")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")


@dataclass(frozen=True)
class Candidate:
    """A shift that could take a job, together with its current load."""

    shift: Shift
    taken: int = 0

    def __post_init__(self) -> None:
        if self.taken < 0:
            raise ValueError("taken must not be negative")

    @property
    def worker(self) -> str:
        return self.shift.worker

    @property
    def spare_capacity(self) -> int:
        return max(0, self.shift.capacity - self.taken)


class AssignmentReason(Enum):
    """Why a shift did or did not get the job."""

    WRONG_LOCATION = "wrong_location"
    OFF_DUTY = "off_duty"
    NO_CAPACITY = "no_capacity"
    COOLING_DOWN = "cooling_down"
    ELIGIBLE = "eligible"

    @property
    def eligible(self) -> bool:
        return self is AssignmentReason.ELIGIBLE


@dataclass(frozen=True)
class AssignmentVerdict:
    """What the dispatcher made of one shift when handing out a job."""

    candidate: Candidate
    reason: AssignmentReason

    @property
    def shift(self) -> Shift:
        return self.candidate.shift

    @property
    def worker(self) -> str:
        return self.candidate.worker

    @property
    def eligible(self) -> bool:
        return self.reason.eligible


class AssignmentPolicy(Protocol):
    """Orders the candidates for a job; the first one gets it."""

    def sort_key(self, candidate: Candidate) -> tuple[Any, ...]:
        ...


@dataclass(frozen=True)
class LeastLoaded:
    """Prefers the courier with the fewest jobs so far, then the earlier shift."""

    def sort_key(self, candidate: Candidate) -> tuple[Any, ...]:
        return (candidate.taken, candidate.shift.start, candidate.worker)


@dataclass(frozen=True)
class EarliestStart:
    """Prefers the courier who has been on duty the longest."""

    def sort_key(self, candidate: Candidate) -> tuple[Any, ...]:
        return (candidate.shift.start, candidate.taken, candidate.worker)


@dataclass(frozen=True)
class Dispatcher:
    """Hands jobs to couriers on duty at the job's own location.

    ``taken`` maps a worker to the number of jobs already given to them; a
    shift drops out once its capacity is used up. A courier who declined a job
    is skipped while their cooldown holds and comes back once it runs out.
    """

    roster: Roster
    policy: AssignmentPolicy = field(default_factory=LeastLoaded)
    cooldowns: CooldownBoard = field(default_factory=CooldownBoard)

    def refuse(self, worker: str, moment: datetime) -> "Dispatcher":
        return replace(self, cooldowns=self.cooldowns.refuse(worker, moment))

    def _reason(self, job: Job, candidate: Candidate) -> AssignmentReason:
        shift = candidate.shift
        if shift.location != job.location:
            return AssignmentReason.WRONG_LOCATION
        if not shift.covers(job.at):
            return AssignmentReason.OFF_DUTY
        if candidate.spare_capacity <= 0:
            return AssignmentReason.NO_CAPACITY
        if self.cooldowns.locked(shift.worker, job.at):
            return AssignmentReason.COOLING_DOWN
        return AssignmentReason.ELIGIBLE

    def explain(
        self, job: Job, taken: Mapping[str, int] | None = None
    ) -> tuple[AssignmentVerdict, ...]:
        """One verdict per roster shift, so a refused job states its reason.

        The eligible shifts come first in the order the policy put them, the
        rejected ones after them in roster order. A rejected shift carries the
        first filter it failed.
        """
        loads = taken or {}
        eligible: list[AssignmentVerdict] = []
        rejected: list[AssignmentVerdict] = []
        for shift in self.roster:
            candidate = Candidate(shift, loads.get(shift.worker, 0))
            verdict = AssignmentVerdict(candidate, self._reason(job, candidate))
            (eligible if verdict.eligible else rejected).append(verdict)
        eligible.sort(key=lambda verdict: self.policy.sort_key(verdict.candidate))
        return tuple(eligible) + tuple(rejected)

    def candidates(
        self, job: Job, taken: Mapping[str, int] | None = None
    ) -> tuple[Candidate, ...]:
        return tuple(
            verdict.candidate
            for verdict in self.explain(job, taken)
            if verdict.eligible
        )

    def assign(
        self, job: Job, taken: Mapping[str, int] | None = None
    ) -> Candidate | None:
        ordered = self.candidates(job, taken)
        return ordered[0] if ordered else None
