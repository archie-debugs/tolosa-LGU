"""Photos or scans (JPG, PNG) of a document's pages are stored as one PDF."""

import io

from PIL import Image

from Backends.backend import models
from Backends.backend.database import SessionLocal
from tests.test_attach_file import files_of, staged
from tests.test_document_edit import client, document, edit, headers_for  # noqa: F401  (fixtures)

DETAILS = {"document_type": "Ordinance", "assigned_to": "SB Secretary", "action_required": "None", "author": "Hon. Cruz"}


def photo(size=(3000, 1500), fmt="JPEG", color="white", **save):
    out = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size, color).save(out, fmt, **save)
    return out.getvalue()


def sideways_photo():
    """A phone photo stored landscape, with the camera's note that it was held upright."""
    image = Image.new("RGB", (3000, 1500), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # Orientation: turn 90 degrees to show it upright
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def stored_pdf(attachment_id):
    with SessionLocal() as db:
        path = db.get(models.Attachment, attachment_id).stored_path
    with open(path, "rb") as handle:
        return handle.read()


def pages_of(pdf):
    return pdf.count(b"/Type /Page\n") or pdf.count(b"/Type /Page ") or pdf.count(b"/Type/Page")


def register(client, tmp_names, combine=False, title="Ordinance No. 9"):
    body = {"tmp_names": tmp_names, "documents": [{"tmp_name": tmp_names[0], "series_year": 2026, "title": title}], **DETAILS}
    if combine:
        body["combine_images"] = True
    response = client.post("/documents/bulk-register/confirm_tmp", json=body, headers=headers_for(client))
    assert response.status_code == 200, response.text
    return response.json()


def test_one_photo_registers_as_a_pdf_named_after_it(client):
    result = register(client, [staged(client, content=photo(), name="Ordinance No. 9.jpg")])

    [created] = result["documents"]
    [attachment] = files_of(client, created)
    assert attachment["original_filename"] == "Ordinance No. 9.pdf"
    assert attachment["mime_type"] == "application/pdf"
    pdf = stored_pdf(attachment["id"])
    assert pdf.startswith(b"%PDF") and pages_of(pdf) == 1


def test_several_page_photos_join_into_one_pdf_in_the_order_picked(client):
    pages = [staged(client, content=photo(color=color), name=f"page {n}.jpg") for n, color in enumerate(("white", "gray", "black"), 1)]

    result = register(client, pages, combine=True)

    [created] = result["documents"]
    assert result["registered"] == 1 and result["total"] == 1
    [attachment] = files_of(client, created)
    assert attachment["original_filename"] == "page 1.pdf"
    assert pages_of(stored_pdf(attachment["id"])) == 3


def test_a_document_file_cannot_be_joined_with_photos(client):
    tmp_names = [staged(client, content=photo(), name="page 1.jpg"), staged(client, content=b"%PDF-1.4 x", name="Ordinance.pdf")]

    result = register(client, tmp_names, combine=True)

    assert result["registered"] == 0
    assert "Only photos or scans" in result["errors"][0]["reason"]


def test_a_photo_is_turned_upright_and_shrunk(client, document):
    from Backends.backend.routes.documents import IMAGE_MAX_SIDE, _images_to_pdf

    pdf = _images_to_pdf([sideways_photo()])
    assert b"/Width 1000" in pdf and f"/Height {IMAGE_MAX_SIDE}".encode() in pdf  # upright, longest side 2000


def test_a_see_through_png_attaches_as_a_pdf_and_a_broken_image_is_refused(client, document):
    response = client.post(f"/documents/{document['id']}/attachments",
                           data={"tmp_name": staged(client, content=photo(fmt="PNG", color=(0, 0, 0, 0)), name="scan.png")},
                           headers=headers_for(client))
    assert response.status_code == 200, response.text
    assert [a["original_filename"] for a in files_of(client, document)] == ["scan.pdf"]

    [attached] = files_of(client, document)
    response = client.post(f"/documents/{document['id']}/attachments/{attached['id']}/replace",
                           data={"tmp_name": staged(client, content=b"not an image", name="broken.jpg")}, headers=headers_for(client))
    assert response.status_code == 400 and "could not be read" in response.json()["detail"]
