"""A document registered without a file can have its file attached later."""

from tests.test_document_edit import client, document, edit, headers_for  # noqa: F401  (fixtures)

PDF = b"%PDF-1.4 the signed ordinance"


def attach(client, document, content=PDF, name="Ordinance No. 7.pdf", username="admin"):
    return client.post(f"/documents/{document['id']}/attachments", files={"file": (name, content, "application/pdf")},
                       headers=headers_for(client, username))


def files_of(client, document):
    return client.get(f"/documents/{document['id']}", headers=headers_for(client)).json()["attachments"]


def test_a_file_is_attached_to_a_document_without_one(client, document):
    assert files_of(client, document) == []

    response = attach(client, document)

    assert response.status_code == 200, response.text
    assert [a["original_filename"] for a in files_of(client, document)] == ["Ordinance No. 7.pdf"]


def test_a_document_that_has_a_file_must_use_replace(client, document):
    assert attach(client, document).status_code == 200
    response = attach(client, document, content=b"%PDF-1.4 another")
    assert response.status_code == 409 and "Replace file" in response.json()["detail"]
    assert len(files_of(client, document)) == 1


def test_attaching_refuses_a_wrong_type_an_empty_file_a_copy_and_a_user_who_cannot_edit(client, document):
    assert attach(client, document, name="notes.txt", content=b"hello").status_code == 400
    assert attach(client, document, content=b"").status_code == 400
    assert attach(client, document, username="clerk").status_code == 403

    other = client.post("/documents/register", data={
        "title": "Resolution No. 2", "series_year": "2025", "document_type": "Ordinance", "assigned_to": "SB Secretary",
        "action_required": "For Agenda", "author": "Hon. Cruz",
    }, headers=headers_for(client)).json()
    assert attach(client, other).status_code == 200
    response = attach(client, document)  # the same content is already another document's file
    assert response.status_code == 409 and other["tracking_number"] in response.json()["detail"]
    assert files_of(client, document) == []


def staged(client, content=PDF, name="Ordinance No. 7.pdf", username="admin"):
    """Stage a file the way the browser app does: a temporary upload, then use it by name."""
    headers = headers_for(client, username)
    item = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": name, "size": len(content)}]},
                       headers=headers).json()["files"][0]
    assert item["ok"], item
    url = item["upload_url"]
    put = client.put(url[url.index("/documents/"):], content=content)
    assert put.status_code == 200, put.text
    return item["tmp_name"]


def test_the_browser_app_attaches_and_replaces_through_a_staged_upload(client, document):
    response = client.post(f"/documents/{document['id']}/attachments", data={"tmp_name": staged(client)}, headers=headers_for(client))
    assert response.status_code == 200, response.text
    [attached] = files_of(client, document)

    tmp_name = staged(client, content=b"%PDF-1.4 the corrected copy", name="Corrected.pdf")
    response = client.post(f"/documents/{document['id']}/attachments/{attached['id']}/replace", data={"tmp_name": tmp_name},
                           headers=headers_for(client))
    assert response.status_code == 200, response.text
    assert [a["original_filename"] for a in files_of(client, document)] == ["Corrected.pdf"]
    # the staged file was used up
    again = client.post(f"/documents/{document['id']}/attachments/{attached['id']}/replace", data={"tmp_name": tmp_name},
                        headers=headers_for(client))
    assert again.status_code == 404


def test_a_staged_upload_is_only_usable_by_whoever_uploaded_it(client, document):
    from Backends.backend.database import SessionLocal
    from Backends.backend import models
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="clerk").one().permissions = "['view_documents', 'edit_documents']"
        db.commit()

    response = client.post(f"/documents/{document['id']}/attachments", data={"tmp_name": staged(client)},
                           headers=headers_for(client, "clerk"))
    assert response.status_code == 404
    assert files_of(client, document) == []
    assert client.post(f"/documents/{document['id']}/attachments", headers=headers_for(client)).status_code == 400
