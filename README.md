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

### Assignment

A job goes to a courier who is on duty **at the job's own location**. The
candidates are ordered by a policy; `LeastLoaded` is the default, and any
object with a `sort_key(candidate)` method can replace it.

```python
from datetime import datetime, timedelta, timezone

from shift_planner import Dispatcher, EarliestStart, Job, Roster, Shift

noon = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
roster = Roster(
    [
        Shift("anna", "depot-north", noon - timedelta(hours=1), timedelta(hours=4), 5),
        Shift("boris", "depot-north", noon, timedelta(hours=4), capacity=5),
        Shift("clara", "depot-south", noon, timedelta(hours=4), capacity=5),
    ]
)

dispatcher = Dispatcher(roster)
job = Job(location="depot-north", at=noon)

dispatcher.assign(job, taken={"anna": 3}).worker  # 'boris'
dispatcher.assign(job).worker  # 'anna', nobody has a job yet

Dispatcher(roster, policy=EarliestStart()).assign(job, taken={"anna": 3}).worker
# 'anna', on duty since 11:00

dispatcher.assign(Job(location="depot-west", at=noon))  # None
```

### Refusal cooldown

Declining a job puts a courier on a cooldown of a fixed length instead of
marking them down. The lock carries its own end, so it expires by the clock
alone: no unlock call, no dispatcher intervention.

```python
from datetime import datetime, timedelta, timezone

from shift_planner import Cooldown, CooldownBoard, Dispatcher, Job, Roster, Shift

noon = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
roster = Roster(
    [
        Shift("anna", "depot-north", noon, timedelta(hours=4), capacity=5),
        Shift("boris", "depot-north", noon, timedelta(hours=4), capacity=5),
    ]
)

dispatcher = Dispatcher(
    roster,
    cooldowns=CooldownBoard(cooldown=Cooldown(timedelta(minutes=20))),
)
job = Job(location="depot-north", at=noon)

dispatcher.assign(job).worker  # 'anna'

after_refusal = dispatcher.refuse("anna", noon)
after_refusal.assign(job).worker  # 'boris', anna is cooling down
after_refusal.cooldowns.remaining("anna", noon + timedelta(minutes=5))
# timedelta(minutes=15)

later = Job(location="depot-north", at=noon + timedelta(minutes=20))
after_refusal.assign(later).worker  # 'anna', the lock lifted on its own
```

### Plans over a horizon

A `ShiftPattern` repeats on chosen weekdays; a `Plan` unrolls the patterns over
a `Horizon`, dropping holidays and stopping once a worker reaches their limit
for the span. The roster it yields depends on the plan alone, so drawing the
plan again is a no-op: `applied_to` replaces exactly what the plan speaks for
(its own workers inside the horizon) and leaves the rest of the roster alone.

```python
from datetime import date, time, timedelta

from shift_planner import Holidays, Horizon, Plan, ShiftPattern

plan = Plan(
    horizon=Horizon(date(2026, 5, 4), days=7),
    patterns=[
        ShiftPattern(
            "anna",
            "depot-north",
            time(8),
            timedelta(hours=8),
            weekdays={0, 1, 2, 3, 4},
            capacity=12,
        ),
        ShiftPattern(
            "boris",
            "depot-north",
            time(16),
            timedelta(hours=8),
            weekdays={0, 2, 4, 5},
        ),
    ],
    holidays=Holidays([date(2026, 5, 6)]),
    limits={"anna": 3},
)

roster = plan.roster()
len(roster)  # 6

[shift.start.date() for shift in roster.for_worker("anna")]
# [date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 7)]
# Wednesday is a holiday, and the limit ends the week early

plan.applied_to(roster) == roster  # True, redrawing adds nothing
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

The tests never read the wall clock: every moment is passed in, and the
daylight-saving boundaries are covered explicitly.

## License

MIT, see [LICENSE](LICENSE).

Maintained by [Shipmind Labs](https://shipmindlabs.com).
