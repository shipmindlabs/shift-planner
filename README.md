# shift-planner

Shift planning for field couriers: activity windows, assignment, and cooldown
locks after a refusal.

## Status

Pre-alpha. The public API is not stable yet.

## Installation

```bash
pip install shift-planner
```

## The model

| Piece | What it is |
| --- | --- |
| `Shift` | one worker at one location over the half-open interval `[start, start + length)`, with a job `capacity` and an `ActivityWindow` |
| `Roster` | shifts sorted by start; two shifts of one worker may touch but never share time |
| `ActivityWindow`, `StartVerdict` | how early and how late a courier may report for duty, and the answer to a reported start |
| `Job`, `Candidate` | a job to hand out at one location and moment; a shift that could take it, together with its current load |
| `Dispatcher`, `AssignmentPolicy` | the filter that finds eligible shifts and the order imposed on what survives |
| `Cooldown`, `CooldownLock`, `CooldownBoard` | the lock a refusal puts on a worker, and the record of such locks |
| `ShiftPattern`, `Horizon`, `Holidays`, `Plan` | a weekly pattern, the span it is drawn over, the days it skips, and the roster it unrolls to |

Three properties hold throughout:

- **Everything is frozen.** `Roster.add`, `CooldownBoard.refuse` and
  `Dispatcher.refuse` return a new object; the one you held keeps its state.
- **Every interval is half-open.** A shift that ends when the next one starts is
  no overlap, a window is shut at its cutoff, a lock is lifted at its `until`.
- **No moment comes from the wall clock.** Every check takes the moment as an
  argument. That is what makes the behaviour testable, and what makes the
  timezone rules below observable rather than a matter of when you run.

Two things that read as related but are not: the window decides whether a
courier may *report for duty* (`Shift.start_verdict`, `Roster.startable`),
while assignment asks only whether a shift `covers` the job's moment. Refusing
a job to a courier who never showed up is outside the library.

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

## Policies

A `Dispatcher` does two separate things. It filters first: the shift must be at
the job's location, must cover the job's moment, must have spare capacity, and
its worker must not be cooling down. Only then does the policy order what
survived. The first candidate takes the job, and `assign` returns `None` when
nobody survived the filter.

The filter is fixed; the order is yours. A policy is any object with a
`sort_key(candidate)` method returning a tuple:

| Policy | Key | Reads as |
| --- | --- | --- |
| `LeastLoaded` (default) | `(taken, shift.start, worker)` | spread the work |
| `EarliestStart` | `(shift.start, taken, worker)` | whoever has been on duty longest |

Both keys end in the worker name, so an otherwise exact tie resolves the same
way on every machine and every run. Keep the habit in your own policies —
without a final tiebreaker, equal candidates swap places between processes and
the roster stops being reproducible.

```python
from dataclasses import dataclass
from typing import Any, Mapping

from shift_planner import Candidate, Dispatcher


@dataclass(frozen=True)
class PreferHomeDepot:
    """Sends a job to the courier whose home depot it is, if one is free."""

    home: Mapping[str, str]

    def sort_key(self, candidate: Candidate) -> tuple[Any, ...]:
        away = self.home.get(candidate.worker) != candidate.shift.location
        return (away, candidate.taken, candidate.worker)


dispatcher = Dispatcher(roster, policy=PreferHomeDepot({"anna": "depot-north"}))
```

Load lives outside the shift. `assign(job, taken={"anna": 3})` maps a worker to
the jobs already handed to them, and a worker who is absent counts as zero.
Nothing in the library increments that mapping: only the caller knows what a
finished, cancelled or requeued job should do to a count. Capacity is per
shift — `Candidate.spare_capacity` is `shift.capacity - taken` floored at zero,
and a used-up shift is dropped before the policy ever sees it.

## Timezone rules that bite

### Aware moments only

`Shift.start`, `Job.at` and both ends of a `CooldownLock` are rejected unless
they carry a `tzinfo` with a real offset. A naive datetime would pass
construction happily and then fail much later, as a bare `TypeError` from
inside an overlap check, where the cause is no longer visible.

### Comparison goes by the instant, arithmetic by the wall clock

`covers`, `overlaps`, `holds_at` and the window verdicts compare datetimes, so
the zone a moment is written in does not change the answer: `11:00+03:00` and
`08:00Z` are the same instant and are treated as one.

Adding a length is a different operation. `start + length` and
`moment + duration` follow Python's rule — a `timedelta` moves the wall clock
and keeps the zone:

```python
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from shift_planner import Cooldown, Shift

berlin = ZoneInfo("Europe/Berlin")  # skips 02:00-03:00 local on 2026-03-29

shift = Shift(
    "anna",
    "depot-north",
    datetime(2026, 3, 29, 1, 30, tzinfo=berlin),
    timedelta(hours=2),
)
shift.end  # 03:30 local
shift.end.astimezone(timezone.utc) - shift.start.astimezone(timezone.utc)
# timedelta(hours=1): two hours on the clock, one hour of real duty

lock = Cooldown(timedelta(minutes=90)).lock(
    "anna", datetime(2026, 3, 29, 1, 30, tzinfo=berlin)
)
lock.until  # 03:00 local, half an hour of real waiting
```

So pick the meaning you need. If a length has to be elapsed time — pay,
throughput, an SLA — build starts in UTC or another fixed offset and convert to
local only for display. If it has to be the clock on the courier's wall, a
zone-local start is already right.

### The repeated hour needs `fold`

On 2026-10-25 Berlin passes 02:30 twice. Which pass you mean is `fold`, and the
library takes it at face value:

```python
from shift_planner import Cooldown, CooldownBoard

board = CooldownBoard(cooldown=Cooldown(timedelta(hours=1)))
board = board.refuse("anna", datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))

board.locked("anna", datetime(2026, 10, 25, 2, 30, tzinfo=berlin, fold=0))  # True
board.locked("anna", datetime(2026, 10, 25, 2, 30, tzinfo=berlin, fold=1))  # False
```

Two shifts an hour apart in UTC both read 02:00 local that night and do not
overlap — rightly so, the courier really works both. A roster rendered in local
time will look like it holds one shift twice; that is the rendering, not the
roster. The converse bites harder: two shifts that read an hour apart locally
can still clash, because one of them is on the other side of the change.

### A plan's zone decides more than the hour

`ShiftPattern.at` is a plain `time` and `Plan.zone` reads it, so the same
pattern can serve several regions. Two consequences follow.

**Day boundaries are drawn in the plan's zone.** `Horizon`, `Holidays` and
`Plan.claims` work on the date of `shift.start.astimezone(plan.zone)`. One
instant at 23:00 UTC is a Monday shift for a UTC plan and a Tuesday shift for a
Berlin plan — different weekday, possibly a different holiday, and a different
slot against `limits`. It also decides what `applied_to` replaces, so two plans
over the same workers in different zones do not cleanly overwrite each other.

**A pattern on the transition hour drifts.** The local start is built with
`fold=0` and nothing raises. On 2026-03-29 a Berlin pattern at 02:30 names a
local time that never happened; Python reads it with the offset in force before
the gap, so duty really begins at 03:30 local. On 2026-10-25 the same pattern
takes the first pass through 02:30. Keep patterns clear of the transition hour,
or plan in UTC, when that hour matters. And note that a wall-clock pattern
holds the same local hour all year by design: the instant it lands on moves by
an hour twice a year, which is usually what field work wants and never what a
UTC-denominated contract wants.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

The tests never read the wall clock: every moment is passed in, and the
daylight-saving boundaries are covered explicitly — `tests/test_dst.py` pins
down each rule in the section above.

## License

MIT, see [LICENSE](LICENSE).

Maintained by [Shipmind Labs](https://shipmindlabs.com).
