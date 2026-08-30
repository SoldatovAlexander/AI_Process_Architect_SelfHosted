from __future__ import annotations

import base64
import binascii
import re
from io import BytesIO
from pathlib import PurePath
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

import httpx


MAX_SOURCE_BYTES = 10_000_000
MAX_TEXT_CHARS = 500_000
GOOGLE_DOCUMENT = re.compile(r"^/document/d/([A-Za-z0-9_-]+)(?:/|$)")


class InterviewSourceInvalid(RuntimeError):
    pass


def _bounded_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        raise InterviewSourceInvalid("The document does not contain readable text.")
    if len(value) > MAX_TEXT_CHARS:
        raise InterviewSourceInvalid("The document contains more than 500,000 characters.")
    return value


def _decode_file(content_base64: str | None) -> bytes:
    if not content_base64:
        raise InterviewSourceInvalid("Document content is required.")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InterviewSourceInvalid("Document content is not valid base64.") from error
    if not content or len(content) > MAX_SOURCE_BYTES:
        raise InterviewSourceInvalid("Document must be between 1 byte and 10 MB.")
    return content


def _zip_xml(content: bytes, member: str) -> ElementTree.Element:
    try:
        with ZipFile(BytesIO(content)) as archive:
            if member not in archive.namelist():
                raise InterviewSourceInvalid("The document package is missing its text content.")
            if archive.getinfo(member).file_size > MAX_SOURCE_BYTES:
                raise InterviewSourceInvalid("The document text XML is larger than 10 MB.")
            xml = archive.read(member)
    except (BadZipFile, OSError) as error:
        raise InterviewSourceInvalid("The document package is damaged or unsupported.") from error
    try:
        return ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise InterviewSourceInvalid("The document text XML is invalid.") from error


def extract_docx(content: bytes) -> str:
    root = _zip_xml(content, "word/document.xml")
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines = []
    for paragraph in root.iter(f"{ns}p"):
        text = "".join((node.text or "") if node.tag == f"{ns}t" else "\t" if node.tag == f"{ns}tab" else "\n" if node.tag == f"{ns}br" else "" for node in paragraph.iter()).strip()
        if text:
            lines.append(text)
    return _bounded_text("\n".join(lines))


def extract_odt(content: bytes) -> str:
    root = _zip_xml(content, "content.xml")
    text_ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    lines = []
    for paragraph in root.iter():
        if paragraph.tag not in {f"{text_ns}p", f"{text_ns}h"}:
            continue
        value = "".join(paragraph.itertext()).strip()
        if value:
            lines.append(value)
    return _bounded_text("\n".join(lines))


def _title(filename: str | None, fallback: str) -> str:
    value = PurePath(filename or fallback).stem.strip()
    return value[:200] or fallback


def validate_source_url(source_type: str, url: str | None) -> str | None:
    if source_type not in {"google_docs", "yandex_docs"}:
        return None
    if not url:
        raise InterviewSourceInvalid("A public document link is required.")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise InterviewSourceInvalid("Only public HTTPS document links are supported.")
    allowed = {"docs.google.com"} if source_type == "google_docs" else {"disk.yandex.ru", "yadi.sk", "docs.yandex.ru"}
    if parsed.hostname not in allowed:
        raise InterviewSourceInvalid("The document link uses an unsupported host.")
    if source_type == "google_docs" and not GOOGLE_DOCUMENT.match(parsed.path):
        raise InterviewSourceInvalid("The Google Docs link does not contain a document ID.")
    return url.strip()


def resolve_file(*, source_type: str, content_base64: str | None, filename: str | None) -> tuple[str, str]:
    content = _decode_file(content_base64)
    if source_type == "docx":
        return _title(filename, "Microsoft Word document"), extract_docx(content)
    if source_type == "odt":
        return _title(filename, "OpenDocument document"), extract_odt(content)
    raise InterviewSourceInvalid("Unsupported document file type.")


async def resolve_link(*, source_type: str, url: str | None) -> tuple[str, str]:
    url = validate_source_url(source_type, url)
    assert url is not None
    parsed = urlparse(url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False) as client:
        if source_type == "google_docs":
            match = GOOGLE_DOCUMENT.match(parsed.path)
            assert match is not None
            response = await client.get(f"https://docs.google.com/document/d/{match.group(1)}/export", params={"format": "txt"})
            if response.status_code != 200:
                raise InterviewSourceInvalid("Google Docs did not allow export. Enable access by link.")
            if len(response.content) > MAX_SOURCE_BYTES:
                raise InterviewSourceInvalid("The document is larger than 10 MB.")
            return "Google Docs", _bounded_text(response.text)
        if source_type == "yandex_docs":
            metadata = await client.get("https://cloud-api.yandex.net/v1/disk/public/resources", params={"public_key": url})
            if metadata.status_code != 200:
                raise InterviewSourceInvalid("Yandex did not allow this public document to be read.")
            payload = metadata.json()
            download_url = payload.get("file")
            download_host = urlparse(download_url or "").hostname or ""
            if not download_url or urlparse(download_url).scheme != "https" or not (download_host.endswith(".yandex.ru") or download_host.endswith(".yandex.net")):
                raise InterviewSourceInvalid("Yandex did not provide a safe downloadable URL.")
            response = await client.get(download_url)
            if response.status_code != 200 or len(response.content) > MAX_SOURCE_BYTES:
                raise InterviewSourceInvalid("The Yandex document could not be downloaded or is larger than 10 MB.")
            name = str(payload.get("name") or "Yandex document")
            suffix = PurePath(name).suffix.lower()
            if suffix == ".docx":
                return _title(name, "Yandex document"), extract_docx(response.content)
            if suffix == ".odt":
                return _title(name, "Yandex document"), extract_odt(response.content)
            if suffix in {".txt", ".md"}:
                return _title(name, "Yandex document"), _bounded_text(response.text)
            raise InterviewSourceInvalid("Yandex document must be DOCX, ODT, TXT, or MD.")
    raise InterviewSourceInvalid("Unsupported document link type.")
