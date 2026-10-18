"""Shift planning for field couriers."""

from shift_planner.assignment import (
    AssignmentPolicy,
    AssignmentReason,
    AssignmentVerdict,
    Candidate,
    Dispatcher,
    EarliestStart,
    Job,
    LeastLoaded,
)
from shift_planner.cooldowns import Cooldown, CooldownBoard, CooldownLock
from shift_planner.plans import Holidays, Horizon, Plan, ShiftPattern
from shift_planner.shifts import (
    InsufficientRestError,
    OverlappingShiftError,
    Roster,
    Shift,
)
from shift_planner.windows import ActivityWindow, StartVerdict

__all__ = [
    "ActivityWindow",
    "AssignmentPolicy",
    "AssignmentReason",
    "AssignmentVerdict",
    "Candidate",
    "Cooldown",
    "CooldownBoard",
    "CooldownLock",
    "Dispatcher",
    "EarliestStart",
    "Holidays",
    "Horizon",
    "InsufficientRestError",
    "Job",
    "LeastLoaded",
    "OverlappingShiftError",
    "Plan",
    "Roster",
    "Shift",
    "ShiftPattern",
    "StartVerdict",
    "__version__",
]

__version__ = "0.1.0"
