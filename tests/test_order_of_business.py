from datetime import date

import pytest

from Backends.backend import business, models, stages
from Backends.backend.database import SessionLocal
from Backends.backend.routes import measure_stages
from tests.test_council_sessions import client, council_term, mark, new_session, set_status  # noqa: F401
from tests.test_settings_pages import headers_for


@pytest.fixture
def clerk(client):
    return headers_for(client, "clerk")


def add_document(tracking, document_type, stage, *, entered_on=date(2026, 10, 1), number=None):
    with SessionLocal() as db:
        doc = models.Document(tracking_number=tracking, title=f"{document_type} {tracking}", document_type=document_type, stage=stage,
                              document_number=number, series_year=2026 if number else None, status="Pending", created_by="admin")
        db.add(doc)
        db.flush()
        if stage:
            db.add(models.DocumentStageChange(document_id=doc.id, stage=stage, effective_on=entered_on, changed_by="admin"))
        db.commit()
        return doc.id


def add_committee(name="Committee on Health"):
    with SessionLocal() as db:
        committee = models.Committee(name=name)
        db.add(committee)
        db.commit()
        return committee.id


def stage_rows(document_id):
    with SessionLocal() as db:
        doc = db.get(models.Document, document_id)
        rows = (db.query(models.DocumentStageChange).filter(models.DocumentStageChange.document_id == document_id)
                .order_by(models.DocumentStageChange.id).all())
        return doc.stage, [(row.stage, row.session_id, row.is_correction) for row in rows]


def add_item(client, headers, session, section, document_id=None, title=None):
    return client.post(f"/council/sessions/{session['id']}/business/items", headers=headers,
                       json={"section": section, "document_id": document_id, "title": title})


def items_of(business_json, section):
    return next(entry["items"] for entry in business_json["sections"] if entry["key"] == section)


def set_outcome(client, headers, session, item, outcome, **fields):
    return client.put(f"/council/sessions/{session['id']}/business/items/{item['id']}/outcome", headers=headers,
                      json={"outcome": outcome, **fields})


def audit_actions():
    with SessionLocal() as db:
        actions = [row.action for row in db.query(models.AuditLog).order_by(models.AuditLog.id).all()]
    return [action for action in actions if action.startswith(("AGENDA_", "OUTCOME_", "VOTE_", "STAGE_"))]


# The rules on their own.

def test_outcomes_plan_the_stages_and_skip_steps_already_taken():
    assert business.plan(stages.ORDINANCE, stages.FILED, business.REFERRED) == [stages.FIRST_READING, stages.IN_COMMITTEE]
    assert business.plan(stages.ORDINANCE, stages.FIRST_READING, business.REFERRED) == [stages.IN_COMMITTEE]
    assert business.plan(stages.RESOLUTION, stages.FILED, business.REFERRED) == [stages.IN_COMMITTEE]
    assert business.plan(stages.ORDINANCE, stages.SECOND_READING, business.THIRD) == [stages.THIRD_READING, stages.APPROVED]
    assert business.plan(stages.ORDINANCE, stages.COMMITTEE_REPORT, business.DEFERRED) == []
    with pytest.raises(ValueError, match="note"):
        business.plan(stages.ORDINANCE, stages.SECOND_READING, business.REFERRED_BACK)
    with pytest.raises(ValueError):
        business.plan(stages.ORDINANCE, stages.FILED, business.ADOPTED)
    assert business.outcome_choices(None) == business.OTHER_OUTCOMES
    assert business.needs_number(stages.ORDINANCE, business.THIRD) and business.needs_committee(stages.RESOLUTION, business.REFERRED)


# Building the order of business.

def test_items_are_added_by_section_reordered_and_removed_before_the_session_is_held(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    first = add_document("DOC-000001", "Ordinance", stages.FILED)
    second = add_document("DOC-000002", "Resolution", stages.FILED)

    add_item(client, clerk, session, "first_reading", first)
    add_item(client, clerk, session, "first_reading", second)
    speech = add_item(client, clerk, session, "other", title="Privilege speech of Hon. Cruz").json()
    again = add_item(client, clerk, session, "first_reading", first)
    blank = add_item(client, clerk, session, "other", title=" ")
    reading = items_of(speech, "first_reading")
    reordered = client.put(f"/council/sessions/{session['id']}/business/order", headers=clerk,
                           json={"section": "first_reading", "item_ids": [reading[1]["id"], reading[0]["id"]]}).json()
    removed = client.delete(f"/council/sessions/{session['id']}/business/items/{items_of(speech, 'other')[0]['id']}", headers=clerk).json()

    assert again.status_code == 409 and blank.status_code == 400
    assert [item["document"]["tracking_number"] for item in items_of(reordered, "first_reading")] == ["DOC-000002", "DOC-000001"]
    assert items_of(removed, "other") == []
    assert [entry["label"] for entry in removed["sections"]][3] == "First reading and referral"


def test_suggestions_come_from_stages_and_from_unfinished_business(client, council_term, clerk):
    term, _ = council_term
    earlier = new_session(client, clerk, term, held_on="2026-10-13").json()
    deferred = add_document("DOC-000003", "Ordinance", stages.COMMITTEE_REPORT)
    add_item(client, clerk, earlier, "second_third", deferred)
    item = items_of(client.get(f"/council/sessions/{earlier['id']}/business", headers=clerk).json(), "second_third")[0]
    set_outcome(client, clerk, earlier, item, business.DEFERRED)
    set_status(client, clerk, earlier, "Held")
    filed = add_document("DOC-000004", "Resolution", stages.FILED)
    add_document("DOC-000005", "Ordinance", stages.IN_COMMITTEE)
    add_document("DOC-000006", "Memorandum", None)
    session = new_session(client, clerk, term).json()

    suggested = client.get(f"/council/sessions/{session['id']}/business/suggestions", headers=clerk).json()

    assert [(row["document"]["tracking_number"], row["section"]) for row in suggested] == [
        ("DOC-000003", "unfinished"), ("DOC-000004", "first_reading")]
    assert suggested[0]["reason"] == "Deferred at the 1st Regular Session of 2026-10-13"
    add_item(client, clerk, session, "first_reading", filed)
    assert len(client.get(f"/council/sessions/{session['id']}/business/suggestions", headers=clerk).json()) == 1


# Outcomes and stages.

def test_outcomes_move_measure_stages_only_when_the_session_is_held_and_link_to_it(client, council_term, clerk):
    term, _ = council_term
    health = add_committee()
    session = new_session(client, clerk, term).json()
    ordinance = add_document("DOC-000010", "Ordinance", stages.FILED)
    approved = add_document("DOC-000011", "Ordinance", stages.SECOND_READING)
    add_item(client, clerk, session, "first_reading", ordinance)
    listing = add_item(client, clerk, session, "second_third", approved).json()
    referral, third = items_of(listing, "first_reading")[0], items_of(listing, "second_third")[0]

    no_committee = set_outcome(client, clerk, session, referral, business.REFERRED)
    no_number = set_outcome(client, clerk, session, third, business.THIRD)
    set_outcome(client, clerk, session, referral, business.REFERRED, committee_id=health)
    recorded = set_outcome(client, clerk, session, third, business.THIRD, document_number="15").json()

    assert no_committee.status_code == 400 and no_number.status_code == 400
    assert recorded["without_outcome"] == 0
    assert stage_rows(ordinance)[0] == stages.FILED  # nothing moves before the session is held
    assert set_status(client, clerk, session, "Held").status_code == 200
    assert stage_rows(ordinance) == (stages.IN_COMMITTEE, [(stages.FILED, None, False), (stages.FIRST_READING, session["id"], False),
                                                           (stages.IN_COMMITTEE, session["id"], False)])
    with SessionLocal() as db:
        doc = db.get(models.Document, approved)
        assert (doc.stage, doc.document_number, doc.series_year) == (stages.APPROVED, "15", 2026)
    history = client.get(f"/documents/{ordinance}/stage", headers=headers_for(client, "admin")).json()["history"]
    assert history[0]["session"] == "1st Regular Session, 2026-10-20" and history[0]["committee"] == "Committee on Health"


def test_marking_held_is_refused_when_an_outcome_no_longer_fits_and_nothing_moves(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    fine = add_document("DOC-000020", "Ordinance", stages.SECOND_READING)
    stale = add_document("DOC-000021", "Ordinance", stages.COMMITTEE_REPORT)
    add_item(client, clerk, session, "second_third", fine)
    listing = add_item(client, clerk, session, "second_third", stale).json()
    first, second = items_of(listing, "second_third")
    assert set_outcome(client, clerk, session, first, stages.TABLED).status_code == 200
    assert set_outcome(client, clerk, session, second, business.SECOND).status_code == 200
    with SessionLocal() as db:  # the measure moved on elsewhere after the outcome was recorded
        measure_stages.add_stage_change(db, db.get(models.Document, stale), stages.THIRD_READING, user=None, effective_on=date(2026, 10, 21))
        db.commit()

    refused = set_status(client, clerk, session, "Held")

    assert refused.status_code == 400 and "DOC-000021" in refused.json()["detail"]
    assert stage_rows(fine)[0] == stages.SECOND_READING
    assert client.get(f"/council/sessions/{session['id']}", headers=clerk).json()["status"] == "Draft"


def test_after_held_an_outcome_is_corrected_with_a_reason_and_its_stages_are_corrected(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    measure = add_document("DOC-000030", "Ordinance", stages.COMMITTEE_REPORT)
    item = items_of(add_item(client, clerk, session, "second_third", measure).json(), "second_third")[0]
    set_outcome(client, clerk, session, item, business.SECOND)
    set_status(client, clerk, session, "Held")
    base = f"/council/sessions/{session['id']}/business/items/{item['id']}/outcome"

    edited = set_outcome(client, clerk, session, item, business.DEFERRED)
    corrected = client.post(f"{base}/corrections", headers=clerk, json={"outcome": business.DEFERRED, "reason": "It was deferred, not passed"})

    assert edited.status_code == 409
    current = items_of(corrected.json(), "second_third")[0]
    assert [(entry["outcome"], entry["is_correction"]) for entry in current["outcome_history"]] == [
        (business.DEFERRED, True), (business.SECOND, False)]
    assert stage_rows(measure) == (stages.COMMITTEE_REPORT, [
        (stages.COMMITTEE_REPORT, None, False), (stages.SECOND_READING, session["id"], False), (stages.COMMITTEE_REPORT, session["id"], True)])
    again = client.post(f"{base}/corrections", headers=clerk, json={"outcome": business.SECOND, "reason": "The minutes say it passed"})
    assert again.status_code == 200 and stage_rows(measure)[0] == stages.SECOND_READING
    assert audit_actions().count("OUTCOME_CORRECTED") == 2


def test_a_correction_is_refused_once_the_measure_has_moved_on(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    measure = add_document("DOC-000031", "Ordinance", stages.COMMITTEE_REPORT)
    item = items_of(add_item(client, clerk, session, "second_third", measure).json(), "second_third")[0]
    set_outcome(client, clerk, session, item, business.SECOND)
    set_status(client, clerk, session, "Held")
    with SessionLocal() as db:
        measure_stages.add_stage_change(db, db.get(models.Document, measure), stages.THIRD_READING, user=None, effective_on=date(2026, 10, 21))
        db.commit()

    refused = client.post(f"/council/sessions/{session['id']}/business/items/{item['id']}/outcome/corrections", headers=clerk,
                          json={"outcome": business.DEFERRED, "reason": "Misrecorded"})

    assert refused.status_code == 409 and "moved on" in refused.json()["detail"]


# Votes.

def test_a_voice_vote_keeps_the_tally_and_a_nominal_vote_counts_each_members_vote(client, council_term, clerk):
    term, ids = council_term
    session = new_session(client, clerk, term).json()
    item = items_of(add_item(client, clerk, session, "other", title="Approval of the 2027 budget calendar").json(), "other")[0]
    base = f"/council/sessions/{session['id']}/business/items/{item['id']}/vote"

    voice = client.put(base, headers=clerk, json={"method": "Voice", "yes": 3, "no": 1, "abstain": 0, "result": "Carried"}).json()
    left = client.put(base, headers=clerk, json={"method": "Nominal", "result": "Carried",
                                                 "members": [{"member_id": ids["Hon. Reyes"], "vote": "Yes"}]})
    nominal = client.put(base, headers=clerk, json={"method": "Nominal", "result": "Lost", "yes": 9, "members": [
        {"member_id": ids["Hon. Santos"], "vote": "Yes"}, {"member_id": ids["Hon. Cruz"], "vote": "No"},
        {"member_id": ids["Hon. Lim"], "vote": "No"}]}).json()

    assert items_of(voice, "other")[0]["vote"]["yes"] == 3
    assert left.status_code == 400
    vote = items_of(nominal, "other")[0]["vote"]
    assert (vote["method"], vote["yes"], vote["no"], vote["abstain"], vote["result"]) == ("Nominal", 1, 2, 0, "Lost")
    assert [row["full_name"] for row in vote["members"]] == ["Hon. Santos", "Hon. Cruz", "Hon. Lim"]
    assert len(items_of(nominal, "other")[0]["vote_history"]) == 1


def test_after_held_a_vote_is_corrected_and_the_original_stays(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    item = items_of(add_item(client, clerk, session, "other", title="Letter from the DILG").json(), "other")[0]
    base = f"/council/sessions/{session['id']}/business/items/{item['id']}/vote"
    client.put(base, headers=clerk, json={"method": "Voice", "yes": 3, "result": "Carried"})
    set_status(client, clerk, session, "Held")

    edited = client.put(base, headers=clerk, json={"method": "Voice", "yes": 2, "no": 2, "result": "Lost"})
    corrected = client.post(f"{base}/corrections", headers=clerk,
                            json={"method": "Voice", "yes": 2, "no": 2, "result": "Lost", "reason": "Recount from the recording"}).json()

    assert edited.status_code == 409
    history = items_of(corrected, "other")[0]["vote_history"]
    assert [(entry["result"], entry["is_correction"]) for entry in history] == [("Lost", True), ("Carried", False)]
    assert "VOTE_CORRECTED" in audit_actions()


def test_readers_can_see_the_order_of_business_but_not_change_it_and_drafts_delete_with_their_items(client, council_term, clerk):
    term, _ = council_term
    session = new_session(client, clerk, term).json()
    add_item(client, clerk, session, "other", title="Privilege speech")
    member = headers_for(client, "member")

    assert client.get(f"/council/sessions/{session['id']}/business", headers=member).status_code == 200
    assert add_item(client, member, session, "other", title="Another").status_code == 403
    assert client.get(f"/council/sessions/{session['id']}/business/suggestions", headers=member).status_code == 403
    assert client.delete(f"/council/sessions/{session['id']}", headers=clerk).status_code == 200
    with SessionLocal() as db:
        assert db.query(models.SessionItem).count() == 0
    assert audit_actions()[0] == "AGENDA_ITEM_ADDED"
