"""A session's order of business: its fixed sections, the outcomes an item can have, and the stages
each outcome moves a measure through (GLOSSARY.md: Order of business, Outcome).

The section order is the usual SB order of business; check it against Tolosa's Internal Rules of
Procedure before relying on it. An outcome's stages are entered when the session is marked Held,
so outcomes can be changed freely until then; afterwards a change is a correction (docs/adr/0003).
"""

from . import stages

SECTIONS = [
    ("call_to_order", "Call to order"),
    ("roll_call", "Roll call"),
    ("minutes", "Approval of the previous minutes"),
    ("first_reading", "First reading and referral"),
    ("committee_reports", "Committee reports"),
    ("unfinished", "Unfinished business"),
    ("second_third", "Business for second and third reading"),
    ("other", "Other matters and communications"),
    ("adjournment", "Adjournment"),
]
SECTION_LABELS = dict(SECTIONS)

REFERRED = "Referred to committee"
REPORT_READ = "Committee report read"
SECOND = "Passed on second reading"
THIRD = "Approved on third reading"
ADOPTED = "Adopted"
REFERRED_BACK = "Referred back to committee"
DEFERRED = "Deferred"
NOTED = "Noted"
APPROVED = "Approved"

# The stages each outcome enters, per kind of measure; a kind that is missing can't have that outcome.
MEASURE_OUTCOMES = {
    REFERRED: {stages.ORDINANCE: [stages.FIRST_READING, stages.IN_COMMITTEE], stages.RESOLUTION: [stages.IN_COMMITTEE]},
    REPORT_READ: {stages.ORDINANCE: [stages.COMMITTEE_REPORT], stages.RESOLUTION: [stages.COMMITTEE_REPORT]},
    SECOND: {stages.ORDINANCE: [stages.SECOND_READING]},
    THIRD: {stages.ORDINANCE: [stages.THIRD_READING, stages.APPROVED]},
    ADOPTED: {stages.RESOLUTION: [stages.ADOPTED]},
    REFERRED_BACK: {stages.ORDINANCE: [stages.IN_COMMITTEE], stages.RESOLUTION: [stages.IN_COMMITTEE]},
    stages.TABLED: {stages.ORDINANCE: [stages.TABLED], stages.RESOLUTION: [stages.TABLED]},
    stages.WITHDRAWN: {stages.ORDINANCE: [stages.WITHDRAWN], stages.RESOLUTION: [stages.WITHDRAWN]},
    stages.LOST: {stages.ORDINANCE: [stages.LOST], stages.RESOLUTION: [stages.LOST]},
    DEFERRED: {stages.ORDINANCE: [], stages.RESOLUTION: []},
}
# Items that are not measures (minutes, letters, a privilege speech) only get a recorded outcome.
OTHER_OUTCOMES = [NOTED, APPROVED, REFERRED, DEFERRED]

# Measures suggested for a section by their stage; Unfinished business comes from earlier sessions.
SUGGESTED_BY_STAGE = {
    "first_reading": [stages.FILED, stages.FIRST_READING],
    "second_third": [stages.COMMITTEE_REPORT, stages.SECOND_READING, stages.THIRD_READING],
}

VOTE_METHODS = ("Voice", "Nominal")
VOTES = ("Yes", "No", "Abstain")
RESULTS = ("Carried", "Lost")


def outcome_choices(kind: str | None) -> list[str]:
    if kind is None:
        return list(OTHER_OUTCOMES)
    return [name for name, by_kind in MEASURE_OUTCOMES.items() if kind in by_kind]


def needs_committee(kind: str | None, outcome: str) -> bool:
    return kind is not None and stages.IN_COMMITTEE in MEASURE_OUTCOMES.get(outcome, {}).get(kind, [])


def needs_number(kind: str | None, outcome: str) -> bool:
    return kind is not None and any(stages.is_enacted(kind, stage) for stage in MEASURE_OUTCOMES.get(outcome, {}).get(kind, []))


def plan(kind: str, current: str | None, outcome: str, note: str | None = None) -> list[str]:
    """The stages to enter, in order, for a measure at `current` given `outcome`; raises ValueError if it can't.

    Stages the measure has already passed are skipped, so a measure read on first reading at an
    earlier session is simply referred.
    """
    wanted = MEASURE_OUTCOMES.get(outcome, {}).get(kind)
    if wanted is None:
        raise ValueError(f"A {kind} can't be {outcome.lower()}.")
    path = stages.path_stages(kind)
    entered, at = [], current
    for index, stage in enumerate(wanted):
        if stage == at:
            continue
        if stage in stages.allowed_next(kind, at):
            if stages.is_referral_back(kind, at, stage) and not (note or "").strip():
                raise ValueError("Add a note saying why it was referred back to committee.")
            entered.append(stage)
            at = stage
        elif index < len(wanted) - 1 and stage in path and at in path and path.index(stage) < path.index(at):
            continue  # already past this step
        else:
            raise ValueError(f"It is at {current or 'no stage'}, so it can't be {outcome.lower()}.")
    if wanted and not entered:
        raise ValueError(f"It is already at {current}.")
    return entered
