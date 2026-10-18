"""Assignment verdicts: why each shift did or did not get the job."""

from __future__ import annotations

from datetime import timedelta

import pytest

from shift_planner import (
    AssignmentReason,
    Cooldown,
    CooldownBoard,
    Dispatcher,
    EarliestStart,
    Job,
    Roster,
    Shift,
)

FOUR_HOURS = timedelta(hours=4)
TAKEN = {"clara": 2, "elena": 1}


def reasons(verdicts) -> dict[str, AssignmentReason]:
    return {verdict.worker: verdict.reason for verdict in verdicts}


@pytest.fixture
def roster(noon) -> Roster:
    return Roster(
        [
            Shift("anna", "depot-south", noon, FOUR_HOURS, capacity=5),
            Shift("boris", "depot-north", noon + timedelta(hours=5), FOUR_HOURS, capacity=5),
            Shift("clara", "depot-north", noon, FOUR_HOURS, capacity=2),
            Shift("dmitri", "depot-north", noon, FOUR_HOURS, capacity=5),
            Shift("elena", "depot-north", noon - timedelta(hours=1), FOUR_HOURS, capacity=5),
            Shift("fedor", "depot-north", noon, FOUR_HOURS, capacity=5),
        ]
    )


@pytest.fixture
def dispatcher(roster, noon) -> Dispatcher:
    board = CooldownBoard(cooldown=Cooldown(timedelta(minutes=20)))
    return Dispatcher(roster, cooldowns=board).refuse("dmitri", noon)


def test_every_roster_shift_gets_its_own_verdict(dispatcher, roster, noon):
    verdicts = dispatcher.explain(Job("depot-north", noon), TAKEN)

    assert len(verdicts) == len(roster)
    assert reasons(verdicts) == {
        "anna": AssignmentReason.WRONG_LOCATION,
        "boris": AssignmentReason.OFF_DUTY,
        "clara": AssignmentReason.NO_CAPACITY,
        "dmitri": AssignmentReason.COOLING_DOWN,
        "elena": AssignmentReason.ELIGIBLE,
        "fedor": AssignmentReason.ELIGIBLE,
    }


def test_the_eligible_verdicts_are_the_candidates_in_policy_order(dispatcher, noon):
    job = Job("depot-north", noon)
    verdicts = dispatcher.explain(job, TAKEN)

    eligible = tuple(verdict.candidate for verdict in verdicts if verdict.eligible)
    assert eligible == dispatcher.candidates(job, TAKEN)
    assert [candidate.worker for candidate in eligible] == ["fedor", "elena"]
    assert dispatcher.assign(job, TAKEN).worker == "fedor"


def test_another_policy_reorders_the_eligible_verdicts(dispatcher, noon):
    job = Job("depot-north", noon)
    by_start = Dispatcher(dispatcher.roster, EarliestStart(), dispatcher.cooldowns)

    verdicts = by_start.explain(job, TAKEN)
    assert [verdict.worker for verdict in verdicts if verdict.eligible] == [
        "elena",
        "fedor",
    ]
    assert tuple(verdict.candidate for verdict in verdicts if verdict.eligible) == (
        by_start.candidates(job, TAKEN)
    )


def test_the_rejected_verdicts_follow_in_roster_order(dispatcher, noon):
    verdicts = dispatcher.explain(Job("depot-north", noon), TAKEN)
    assert [verdict.worker for verdict in verdicts] == [
        "fedor",
        "elena",
        "anna",
        "clara",
        "dmitri",
        "boris",
    ]


def test_a_none_from_assign_has_a_stated_reason(dispatcher, noon):
    job = Job("depot-west", noon)

    assert dispatcher.assign(job) is None
    verdicts = dispatcher.explain(job)
    assert not any(verdict.eligible for verdict in verdicts)
    assert {verdict.reason for verdict in verdicts} == {
        AssignmentReason.WRONG_LOCATION
    }


def test_a_missing_load_counts_as_no_jobs_yet(dispatcher, noon):
    verdicts = reasons(dispatcher.explain(Job("depot-north", noon)))
    assert verdicts["clara"] is AssignmentReason.ELIGIBLE
    assert verdicts["dmitri"] is AssignmentReason.COOLING_DOWN


def test_the_reason_is_the_first_filter_the_shift_fails(noon):
    roster = Roster(
        [
            Shift("anna", "depot-south", noon + timedelta(hours=5), FOUR_HOURS),
            Shift("boris", "depot-north", noon, FOUR_HOURS, capacity=1),
        ]
    )
    dispatcher = Dispatcher(roster).refuse("boris", noon)

    verdicts = reasons(dispatcher.explain(Job("depot-north", noon), {"boris": 1}))
    assert verdicts["anna"] is AssignmentReason.WRONG_LOCATION
    assert verdicts["boris"] is AssignmentReason.NO_CAPACITY


def test_only_the_eligible_reason_reads_as_eligible():
    assert AssignmentReason.ELIGIBLE.eligible
    assert not AssignmentReason.OFF_DUTY.eligible
    assert not AssignmentReason.COOLING_DOWN.eligible


def test_a_cooldown_that_lifted_turns_the_verdict_around(dispatcher, noon):
    later = Job("depot-north", noon + timedelta(minutes=20))
    assert reasons(dispatcher.explain(later))["dmitri"] is AssignmentReason.ELIGIBLE
