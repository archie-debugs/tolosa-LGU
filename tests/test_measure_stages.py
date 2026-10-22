from datetime import date

import pytest

import Backends.backend.routes.documents as documents_routes
import Backends.backend.routes.measure_stages as measure_stages
from Backends.backend import models, stages
from Backends.backend.database import SessionLocal
from tests.test_registration import PDF, client as registration_client, confirm, headers_for, register, upload  # noqa: F401

TODAY = date(2026, 10, 22)


@pytest.fixture
def client(registration_client, monkeypatch):
    monkeypatch.setattr(measure_stages, "lgu_today", lambda: TODAY)
    monkeypatch.setattr(documents_routes, "lgu_today", lambda: TODAY)
    with SessionLocal() as db:
        db.add_all([models.DocumentType(name="Memorandum"), models.Committee(name="Committee on Health"),
                    models.Committee(name="Old Committee", is_active=False)])
        db.add(models.User(username="reader", hashed_password=db.query(models.User).first().hashed_password, role="Employee",
                           permissions="['view_documents', 'view_document_details']", status="Active", is_active=True))
        db.commit()
    return registration_client


def committee_id(name):
    with SessionLocal() as db:
        return db.query(models.Committee.id).filter(models.Committee.name == name).scalar()


def change(client, headers, doc, stage, **fields):
    return client.post(f"/documents/{doc['id']}/stage", headers=headers, json={"stage": stage, **fields})


def audit_actions():
    with SessionLocal() as db:
        return [row.action for row in db.query(models.AuditLog).order_by(models.AuditLog.id) if row.action.startswith("STAGE_")]


# The rules on their own.

def test_measure_kinds_come_from_the_document_type():
    assert stages.measure_kind("Ordinance") == stages.ORDINANCE
    assert stages.measure_kind("Appropriation Ordinance") == stages.ORDINANCE
    assert stages.measure_kind("resolution") == stages.RESOLUTION
    assert stages.measure_kind("Memorandum") is None and stages.measure_kind(None) is None


def test_measures_move_forward_can_skip_and_can_end_before_enactment():
    allowed = stages.allowed_next(stages.ORDINANCE, stages.FIRST_READING)
    assert allowed[:2] == [stages.IN_COMMITTEE, stages.COMMITTEE_REPORT]
    assert stages.THIRD_READING in allowed and stages.WITHDRAWN in allowed
    assert stages.FILED not in allowed


def test_outcomes_of_the_same_step_are_not_normal_moves_and_enacted_measures_cannot_end():
    after_signing = stages.allowed_next(stages.ORDINANCE, stages.SIGNED)
    assert stages.VETOED not in after_signing and stages.LAPSED not in after_signing
    assert after_signing == [stages.PROVINCIAL_REVIEW, stages.POSTED]
    assert stages.WITHDRAWN not in stages.allowed_next(stages.ORDINANCE, stages.APPROVED)
    assert stages.allowed_next(stages.ORDINANCE, stages.LOST) == []


def test_readings_can_go_back_to_committee_and_tabled_measures_can_be_taken_up_again():
    assert stages.allowed_next(stages.ORDINANCE, stages.SECOND_READING)[0] == stages.IN_COMMITTEE
    assert stages.is_referral_back(stages.ORDINANCE, stages.SECOND_READING, stages.IN_COMMITTEE)
    assert not stages.is_referral_back(stages.ORDINANCE, stages.FIRST_READING, stages.IN_COMMITTEE)
    assert stages.IN_COMMITTEE not in stages.allowed_next(stages.ORDINANCE, stages.APPROVED)
    assert stages.allowed_next(stages.ORDINANCE, stages.TABLED) == [
        stages.FILED, stages.FIRST_READING, stages.IN_COMMITTEE, stages.COMMITTEE_REPORT,
        stages.SECOND_READING, stages.THIRD_READING,
    ]


def test_a_resolution_can_be_adopted_straight_from_filing():
    assert stages.ADOPTED in stages.allowed_next(stages.RESOLUTION, stages.FILED)
    assert stages.FIRST_READING not in stages.all_stages(stages.RESOLUTION)


# Registration.

def test_a_new_measure_starts_at_filed_and_a_number_in_its_title_is_not_kept(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Proposed Ordinance No. 9 on markets", document_type="Ordinance", stage="Filed").json()

    assert doc["stage"] == "Filed" and doc["document_number"] is None
    history = client.get(f"/documents/{doc['id']}/stage", headers=admin).json()["history"]
    assert [(h["stage"], h["effective_on"], h["note"]) for h in history] == [("Filed", "2026-10-22", "Registered at this stage")]


def test_a_typed_number_needs_an_enacted_stage(client):
    admin = headers_for(client, "admin")

    refused = register(client, admin, title="Market ordinance", document_type="Ordinance", stage="Second Reading", document_number="12")
    enacted = register(client, admin, title="Market ordinance", document_type="Ordinance", stage="Posted", document_number="12")

    assert refused.status_code == 400 and "gets its number when it is approved" in refused.json()["detail"]
    assert enacted.status_code == 200 and (enacted.json()["stage"], enacted.json()["document_number"]) == ("Posted", "12")


def test_without_a_stage_a_numbered_measure_starts_enacted_and_other_documents_have_none(client):
    admin = headers_for(client, "admin")
    numbered = register(client, admin, title="Ordinance No. 7", document_type="Ordinance").json()
    resolution = register(client, admin, title="A resolution", document_type="Resolution").json()
    memo = register(client, admin, title="Office memo", document_type="Memorandum", document_number="3", stage="Filed").json()

    assert numbered["stage"] == "Approved" and numbered["document_number"] == "7"
    assert resolution["stage"] == "Filed"
    assert memo["stage"] is None
    assert client.get(f"/documents/{memo['id']}/stage", headers=admin).json() == {
        "is_measure": False, "stage": None, "allowed": [], "stages": [], "history": []}


def test_a_file_registered_on_the_form_keeps_its_stage_and_bulk_import_infers_it(client):
    admin = headers_for(client, "admin")
    form = confirm(client, admin, [{"tmp_name": upload(client, admin, "Ordinance No. 3.pdf", PDF + b"%1\n"), "series_year": 2026}],
                   document_type="Ordinance", stage="First Reading").json()
    bulk = confirm(client, admin, [{"tmp_name": upload(client, admin, "Ordinance No. 4.pdf", PDF + b"%2\n"), "series_year": 2026}],
                   document_type="Ordinance").json()
    refused = confirm(client, admin, [{"tmp_name": upload(client, admin, "draft.pdf", PDF + b"%3\n"), "series_year": 2026,
                                       "document_number": "9"}], document_type="Ordinance", stage="Filed").json()

    with SessionLocal() as db:
        first, second = (db.get(models.Document, result["documents"][0]["id"]) for result in (form, bulk))
        assert (first.stage, first.document_number) == ("First Reading", None)
        assert (second.stage, second.document_number) == ("Approved", "4")
    assert refused["registered"] == 0 and "gets its number when it is approved" in refused["errors"][0]["reason"]


def test_the_registration_form_is_offered_each_measure_s_stages(client):
    options = client.get("/documents/registration/options", headers=headers_for(client, "admin")).json()

    assert options["measure_stages"]["resolution"] == stages.path_stages(stages.RESOLUTION)
    assert options["measure_stages"]["ordinance"][0] == "Filed"


# Changing the stage.

def test_referral_needs_an_active_committee_and_is_recorded_with_it(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Health ordinance", document_type="Ordinance", stage="First Reading").json()

    assert change(client, admin, doc, "In Committee").status_code == 400
    assert change(client, admin, doc, "In Committee", committee_id=committee_id("Old Committee")).status_code == 400
    referred = change(client, admin, doc, "In Committee", committee_id=committee_id("Committee on Health"))

    assert referred.status_code == 200
    latest = referred.json()["history"][0]
    assert (latest["stage"], latest["committee"], latest["effective_on"], latest["is_correction"]) == (
        "In Committee", "Committee on Health", "2026-10-22", False)
    assert audit_actions() == ["STAGE_CHANGED"]


def test_moves_outside_the_rules_dates_out_of_order_and_future_dates_are_refused(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Parking ordinance", document_type="Ordinance", stage="Second Reading").json()

    backwards = change(client, admin, doc, "First Reading")
    future = change(client, admin, doc, "Third Reading", effective_on="2026-10-23")
    before_filing = change(client, admin, doc, "Third Reading", effective_on="2026-10-01")

    assert backwards.status_code == 400 and "Use a correction" in backwards.json()["detail"]
    assert future.status_code == 400
    assert before_filing.status_code == 400 and "2026-10-22" in before_filing.json()["detail"]


def test_referral_back_from_a_reading_needs_a_note(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Zoning ordinance", document_type="Ordinance", stage="Second Reading").json()
    health = committee_id("Committee on Health")

    assert change(client, admin, doc, "In Committee", committee_id=health).status_code == 400
    assert change(client, admin, doc, "In Committee", committee_id=health, note="Amendments raised on the floor").status_code == 200


def test_approval_sets_the_enacted_number_and_refuses_one_already_taken(client):
    admin = headers_for(client, "admin")
    register(client, admin, title="Ordinance No. 5", document_type="Ordinance", series_year="2026")
    doc = register(client, admin, title="Tax ordinance", document_type="Ordinance", stage="Third Reading").json()

    assert change(client, admin, doc, "Approved").status_code == 400
    assert change(client, admin, doc, "Approved", document_number="5").status_code == 409
    approved = change(client, admin, doc, "Approved", document_number="6")

    assert approved.status_code == 200
    assert (approved.json()["document_number"], approved.json()["series_year"]) == ("6", 2026)


def test_only_the_permission_can_change_stages_and_readers_still_see_them(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Ordinance on noise", document_type="Ordinance", stage="Filed").json()
    reader = headers_for(client, "reader")

    assert change(client, reader, doc, "First Reading").status_code == 403
    assert client.get(f"/documents/{doc['id']}/stage", headers=reader).json()["stage"] == "Filed"


# Corrections.

def test_a_correction_can_go_anywhere_needs_a_reason_and_keeps_the_original(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Ordinance on fees", document_type="Ordinance", stage="Third Reading").json()

    no_reason = client.post(f"/documents/{doc['id']}/stage/corrections", headers=admin, json={"stage": "Second Reading", "reason": " "})
    corrected = client.post(f"/documents/{doc['id']}/stage/corrections", headers=admin,
                            json={"stage": "Second Reading", "reason": "Registered at the wrong reading"})

    assert no_reason.status_code in (400, 422)
    history = corrected.json()["history"]
    assert [(h["stage"], h["is_correction"]) for h in history] == [("Second Reading", True), ("Third Reading", False)]
    assert history[0]["note"] == "Registered at the wrong reading"
    assert corrected.json()["stage"] == "Second Reading"
    assert audit_actions() == ["STAGE_CORRECTED"]


# What the public sees.

def test_the_public_qr_lookup_shows_the_stage_and_the_dates(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Ordinance on markets", document_type="Ordinance", stage="Filed").json()
    change(client, admin, doc, "First Reading")

    lookup = client.get(f"/qr/{doc['qr_token']}", headers={"Accept": "application/json"}).json()

    assert lookup["stage"] == {"stage": "First Reading", "entered_on": "2026-10-22",
                               "dates": [{"stage": "Filed", "date": "2026-10-22"}, {"stage": "First Reading", "date": "2026-10-22"}]}


def test_the_public_list_shows_the_stage_of_public_measures(client):
    admin = headers_for(client, "admin")
    doc = register(client, admin, title="Ordinance on lighting", document_type="Ordinance", stage="Filed").json()
    with SessionLocal() as db:
        db.get(models.Document, doc["id"]).is_public = True
        db.commit()

    items = client.get("/public/documents").json()["items"]

    assert [item["stage"]["stage"] for item in items] == ["Filed"]
