"""Shift planning for field couriers."""

from shift_planner.assignment import (
    AssignmentPolicy,
    Candidate,
    Dispatcher,
    EarliestStart,
    Job,
    LeastLoaded,
)
from shift_planner.cooldowns import Cooldown, CooldownBoard, CooldownLock
from shift_planner.shifts import OverlappingShiftError, Roster, Shift
from shift_planner.windows import ActivityWindow, StartVerdict

__all__ = [
    "ActivityWindow",
    "AssignmentPolicy",
    "Candidate",
    "Cooldown",
    "CooldownBoard",
    "CooldownLock",
    "Dispatcher",
    "EarliestStart",
    "Job",
    "LeastLoaded",
    "OverlappingShiftError",
    "Roster",
    "Shift",
    "StartVerdict",
    "__version__",
]

__version__ = "0.1.0"
