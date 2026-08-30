import base64
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx

from process_architect_api.services.interview_sources import extract_docx, extract_odt
from test_analyst_api import create_session
from test_api import request


def package(member: str, content: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(member, content)
    return output.getvalue()


DOCX = package("word/document.xml", """<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Заказчик: Заявка приходит с сайта.</w:t></w:r></w:p><w:p><w:r><w:t>Аналитик: Кто её проверяет?</w:t></w:r></w:p></w:body></w:document>""")
ODT = package("content.xml", """<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Customer: Lead arrives.</text:p><text:p>Analyst: Who reviews it?</text:p></office:text></office:body></office:document-content>""")


def test_extracts_docx_and_odt_without_office_runtime():
    assert extract_docx(DOCX).splitlines() == ["Заказчик: Заявка приходит с сайта.", "Аналитик: Кто её проверяет?"]
    assert extract_odt(ODT).splitlines() == ["Customer: Lead arrives.", "Analyst: Who reviews it?"]


def test_resolves_office_file_into_reviewable_text():
    headers, _, session = create_session()
    resolved = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/resolve-source", headers=headers, json={"source_type": "docx", "filename": "Интервью.docx", "content_base64": base64.b64encode(DOCX).decode()})
    assert resolved.status_code == 200
    assert resolved.json() == {"title": "Интервью", "source_format": "docx", "content": "Заказчик: Заявка приходит с сайта.\nАналитик: Кто её проверяет?"}


def test_link_provenance_is_saved_only_for_allowed_public_source():
    headers, _, session = create_session()
    url = "https://docs.google.com/document/d/abc_DEF-123/edit"
    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Public interview", "source_format": "google_docs", "source_url": url, "content": "Customer: Lead arrives"})
    assert imported.status_code == 201
    assert imported.json()["source_url"] == url

    denied = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/preview", headers=headers, json={"title": "Unsafe", "source_format": "google_docs", "source_url": "https://example.com/document/d/abc/edit", "content": "Customer: Lead arrives"})
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "invalid_interview_transcript"


def test_google_docs_uses_canonical_export_and_rejects_arbitrary_hosts(monkeypatch):
    headers, _, session = create_session()
    requested = []
    original_send = httpx.AsyncClient.send

    async def send(self, request, **kwargs):
        if request.url.host != "docs.google.com":
            return await original_send(self, request, **kwargs)
        requested.append(str(request.url))
        return httpx.Response(200, request=request, content="Customer: Public document".encode())

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    resolved = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/resolve-source", headers=headers, json={"source_type": "google_docs", "url": "https://docs.google.com/document/d/abc_DEF-123/edit"})
    assert resolved.status_code == 200
    assert requested == ["https://docs.google.com/document/d/abc_DEF-123/export?format=txt"]

    denied = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/resolve-source", headers=headers, json={"source_type": "google_docs", "url": "https://example.com/document/d/abc/edit"})
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "invalid_interview_source"


def test_yandex_public_document_uses_disk_metadata_and_docx_content(monkeypatch):
    headers, _, session = create_session()
    original_send = httpx.AsyncClient.send

    async def send(self, request, **kwargs):
        if request.url.host == "cloud-api.yandex.net":
            return httpx.Response(200, request=request, json={"name": "Interview.docx", "file": "https://downloader.disk.yandex.ru/disk/public-file"})
        if request.url.host == "downloader.disk.yandex.ru":
            return httpx.Response(200, request=request, content=DOCX)
        return await original_send(self, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    resolved = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/resolve-source", headers=headers, json={"source_type": "yandex_docs", "url": "https://disk.yandex.ru/i/public-key"})
    assert resolved.status_code == 200
    assert resolved.json()["title"] == "Interview"
    assert "Заказчик" in resolved.json()["content"]
