# shift-planner

Shift planning for field couriers: activity windows, assignment, and cooldown
locks after a refusal.

## Status

Pre-alpha. The public API is not stable yet.

## Installation

```bash
pip install shift-planner
```

## Usage

A shift is a half-open interval `[start, start + length)` at one location. A
roster refuses to be built if a worker ends up with overlapping shifts.

```python
from datetime import datetime, timedelta, timezone

from shift_planner import OverlappingShiftError, Roster, Shift

morning = Shift(
    worker="anna",
    location="depot-north",
    start=datetime(2026, 5, 4, 8, tzinfo=timezone.utc),
    length=timedelta(hours=4),
    capacity=12,
)
afternoon = Shift(
    worker="anna",
    location="depot-north",
    start=datetime(2026, 5, 4, 12, tzinfo=timezone.utc),
    length=timedelta(hours=4),
)

roster = Roster([morning, afternoon])  # touching shifts are fine

try:
    roster.add(morning)
except OverlappingShiftError as error:
    print(error)
```

### Activity window

A courier may report for duty a little before the planned start and only for a
while after it. By default the window is `[start - 15 min, start + 1 hour)`.

```python
from datetime import datetime, timedelta, timezone

from shift_planner import ActivityWindow, Shift, StartVerdict

shift = Shift(
    worker="anna",
    location="depot-north",
    start=datetime(2026, 5, 4, 8, tzinfo=timezone.utc),
    length=timedelta(hours=4),
    window=ActivityWindow(
        early_tolerance=timedelta(minutes=15),
        late_cutoff=timedelta(hours=1),
    ),
)

shift.may_start_at(datetime(2026, 5, 4, 7, 45, tzinfo=timezone.utc))  # True
shift.start_verdict(datetime(2026, 5, 4, 7, 30, tzinfo=timezone.utc))
# StartVerdict.TOO_EARLY
shift.start_verdict(datetime(2026, 5, 4, 9, tzinfo=timezone.utc))
# StartVerdict.TOO_LATE
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## License

MIT, see [LICENSE](LICENSE).

Maintained by [Shipmind Labs](https://shipmindlabs.com).
