"""Fixtures for a suite that never reads the wall clock.

Every moment a test hands to the library is either a literal or comes from a
:class:`Clock` the test winds forward itself, so results do not depend on when
the suite runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

NOON = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)


@dataclass
class Clock:
    """A hand-wound clock: it moves only when a test winds it forward."""

    now: datetime

    def tick(self, amount: timedelta) -> datetime:
        self.now += amount
        return self.now


@pytest.fixture
def noon() -> datetime:
    return NOON


@pytest.fixture
def clock() -> Clock:
    return Clock(NOON)
