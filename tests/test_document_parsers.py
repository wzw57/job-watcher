from __future__ import annotations

import io
import zipfile

import pytest

from job_watcher.parsers.documents import DocumentParseError, parse_document
from job_watcher.parsers.html import discover_attachments, extract_readable_text


def zipped(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_discovers_and_deduplicates_document_links() -> None:
    html = '<a href="/files/jobs.xlsx#sheet">岗位表</a><a href="/files/jobs.xlsx">重复</a><a href="/files/notice.jpg">图片公告</a><a href="note.html">说明</a>'
    links = discover_attachments(html, "https://example.com/news/1")
    assert links == (
        {"url":"https://example.com/files/jobs.xlsx","label":"岗位表","extension":".xlsx"},
        {"url":"https://example.com/files/notice.jpg","label":"图片公告","extension":".jpg"},
    )


def test_parses_docx_text() -> None:
    data = zipped({"word/document.xml": '<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>网络安全工程师</w:t></w:r></w:p></w:body></w:document>'})
    assert parse_document(data, "jobs.docx") == "网络安全工程师"


def test_parses_xlsx_shared_strings() -> None:
    data = zipped({
        "xl/sharedStrings.xml": '<sst xmlns="x"><si><t>岗位</t></si><si><t>青岛</t></si></sst>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row></sheetData></worksheet>',
    })
    assert parse_document(data, "jobs.xlsx") == "岗位 青岛"


def test_readable_text_prefers_main_and_ignores_navigation() -> None:
    main = "青岛网络安全校园招聘岗位说明" * 10
    title, text, metadata = extract_readable_text(f"<title>招聘</title><nav>首页 招聘 联系</nav><main><p>{main}</p></main><footer>版权</footer>")
    assert title == "招聘" and main in text and "首页" not in text and metadata["used_main_content"] is True


def test_legacy_office_requires_explicit_conversion() -> None:
    with pytest.raises(DocumentParseError) as error:
        parse_document(b"legacy", "jobs.xls")
    assert error.value.code == "legacy_office_conversion_required"


def test_empty_pdf_requires_ocr(monkeypatch) -> None:
    class Page:
        def extract_text(self) -> str:
            return ""

    class Reader:
        def __init__(self, _stream) -> None:
            self.pages = [Page()]

    monkeypatch.setattr("pypdf.PdfReader", Reader)
    with pytest.raises(DocumentParseError) as error:
        parse_document(b"scan", "scan.pdf")
    assert error.value.code == "ocr_required"


def test_image_attachment_requires_ocr() -> None:
    with pytest.raises(DocumentParseError) as error:
        parse_document(b"image", "notice.png", "image/png")
    assert error.value.code == "ocr_required"
