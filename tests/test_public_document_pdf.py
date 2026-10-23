from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal, engine
from tests.test_settings_pages import reset_db

models.Base.metadata.create_all(bind=engine)

PDF = b"%PDF-1.4 public ordinance"


def seed(tmp_path):
    """1: public with a PDF (and an older Word file)   2: private with a PDF
    3: public, archived, with a PDF                    4: public with only a Word file
    5: public, its PDF missing from disk"""
    reset_db()
    pdf = tmp_path / "ordinance.pdf"
    pdf.write_bytes(PDF)
    word = tmp_path / "notes.docx"
    word.write_bytes(b"word")
    ids = {}
    with SessionLocal() as db:
        for number, is_public, archived in [(1, True, False), (2, False, False), (3, True, True), (4, True, False), (5, True, False)]:
            doc = models.Document(tracking_number=f"DOC-00000{number}", title=f"Document {number}", is_public=is_public, archived=archived)
            db.add(doc)
            db.flush()
            ids[number] = doc.id
            if number in (1, 4):
                db.add(models.Attachment(document_id=doc.id, original_filename="notes.docx", stored_path=str(word),
                                         mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            if number in (1, 2, 3):
                db.add(models.Attachment(document_id=doc.id, original_filename="ordinance.pdf", stored_path=str(pdf), mime_type="application/pdf"))
            if number == 5:
                db.add(models.Attachment(document_id=doc.id, original_filename="gone.pdf", stored_path=str(tmp_path / "gone.pdf"), mime_type="application/pdf"))
        db.commit()
    return ids


def test_a_public_document_opens_as_its_pdf_in_the_browser(tmp_path):
    ids = seed(tmp_path)
    client = TestClient(main.app)

    response = client.get(f"/public/documents/{ids[1]}/pdf")

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")


def test_private_archived_and_pdf_less_documents_are_not_found(tmp_path):
    ids = seed(tmp_path)
    client = TestClient(main.app)

    for number in (2, 3, 4, 5):
        response = client.get(f"/public/documents/{ids[number]}/pdf")
        assert response.status_code == 404, number
        assert response.json()["detail"] == "No public PDF for this document"
    assert client.get("/public/documents/999999/pdf").status_code == 404


def test_the_public_list_says_which_documents_have_a_pdf(tmp_path):
    ids = seed(tmp_path)
    client = TestClient(main.app)

    items = client.get("/public/documents").json()["items"]

    assert {item["id"]: item["has_pdf"] for item in items} == {ids[1]: True, ids[4]: False, ids[5]: False}
