"""The legislative stages of a measure and which moves between them are allowed (GLOSSARY.md: Stage).

Fixed in code on purpose (docs/adr/0001): the order of business and deadlines depend on what
each stage means. A measure is a document whose type is an ordinance or a resolution.

Moves:
- forward along the measure's path, skipping stages if needed (not to a sibling outcome:
  a Signed ordinance can't become Vetoed by a normal change);
- back to In Committee (re-referral) from the readings;
- to an ending (Withdrawn, Tabled, Lost) any time before it is enacted;
- from Tabled to any stage before enactment (taken from the table).
Anything else is a correction, which needs a reason (docs/adr/0003).
"""

FILED = "Filed"
FIRST_READING = "First Reading"
IN_COMMITTEE = "In Committee"
COMMITTEE_REPORT = "Committee Report"
SECOND_READING = "Second Reading"
THIRD_READING = "Third Reading"
APPROVED = "Approved"
ADOPTED = "Adopted"
SENT_TO_MAYOR = "Sent to the Mayor"
SIGNED = "Signed"
VETOED = "Vetoed"
LAPSED = "Lapsed into Law"
PROVINCIAL_REVIEW = "Provincial Review"
POSTED = "Posted"
WITHDRAWN = "Withdrawn"
TABLED = "Tabled"
LOST = "Lost"

ORDINANCE = "ordinance"
RESOLUTION = "resolution"

# Each path is a list of ranks; stages sharing a rank are alternative outcomes of the same step.
PATHS = {
    ORDINANCE: [
        [FILED], [FIRST_READING], [IN_COMMITTEE], [COMMITTEE_REPORT], [SECOND_READING], [THIRD_READING],
        [APPROVED], [SENT_TO_MAYOR], [SIGNED, VETOED, LAPSED], [PROVINCIAL_REVIEW], [POSTED],
    ],
    RESOLUTION: [
        [FILED], [IN_COMMITTEE], [COMMITTEE_REPORT], [ADOPTED], [SENT_TO_MAYOR], [SIGNED, VETOED],
    ],
}
ENDINGS = [WITHDRAWN, TABLED, LOST]
ENACTED = {ORDINANCE: APPROVED, RESOLUTION: ADOPTED}
READINGS = {FIRST_READING, COMMITTEE_REPORT, SECOND_READING, THIRD_READING}


def measure_kind(document_type: str | None) -> str | None:
    """ORDINANCE or RESOLUTION for a measure's document type, or None for any other document."""
    name = (document_type or "").strip().lower()
    if "ordinance" in name:
        return ORDINANCE
    if "resolution" in name:
        return RESOLUTION
    return None


def path_stages(kind: str) -> list[str]:
    return [stage for rank in PATHS[kind] for stage in rank]


def all_stages(kind: str) -> list[str]:
    return path_stages(kind) + ENDINGS


def _rank(kind: str, stage: str) -> int | None:
    for index, rank in enumerate(PATHS[kind]):
        if stage in rank:
            return index
    return None


def is_enacted(kind: str, stage: str | None) -> bool:
    """True once the measure has been approved (ordinance) or adopted (resolution), or later."""
    rank = _rank(kind, stage) if stage else None
    return rank is not None and rank >= _rank(kind, ENACTED[kind])


def allowed_next(kind: str, current: str | None) -> list[str]:
    """Stages a normal (non-correction) change may move a measure to, in path order."""
    if current is None:
        return [FILED]
    if current in (WITHDRAWN, LOST):
        return []
    before_enactment = [stage for stage in path_stages(kind) if not is_enacted(kind, stage)]
    if current == TABLED:
        return before_enactment
    rank = _rank(kind, current)
    if rank is None:
        return []
    allowed = [stage for later in PATHS[kind][rank + 1:] for stage in later]
    if current in READINGS and _rank(kind, IN_COMMITTEE) < rank:
        allowed.insert(0, IN_COMMITTEE)
    if not is_enacted(kind, current):
        allowed += ENDINGS
    return allowed


def is_referral_back(kind: str, current: str | None, target: str) -> bool:
    """True when a reading sends the measure back to committee, which needs a note saying why."""
    current_rank = _rank(kind, current) if current else None
    return target == IN_COMMITTEE and current_rank is not None and current_rank > _rank(kind, IN_COMMITTEE)


def registration_stages(kind: str) -> list[str]:
    """Stages a measure may be registered at: anywhere on its path, so existing measures can be entered."""
    return path_stages(kind)
